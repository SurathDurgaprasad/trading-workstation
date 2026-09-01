from datetime import datetime
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from market.data_provider import OHLCV

VolumeTrend = Literal["increasing", "decreasing", "neutral"]

SMA_FAST_PERIOD = 20
SMA_SLOW_PERIOD = 50
RSI_PERIOD = 14
MACD_FAST_PERIOD = 12
MACD_SLOW_PERIOD = 26
MACD_SIGNAL_PERIOD = 9
ATR_PERIOD = 14
VOLUME_SMA_PERIOD = 20
VOLUME_TREND_LOOKBACK = 5


class MACDValues(BaseModel):
    model_config = ConfigDict(frozen=True)

    macd: float
    signal: float
    histogram: float


class VolumeAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True)

    current_volume: float = Field(ge=0)
    volume_sma_20: float = Field(ge=0)
    volume_ratio: float = Field(ge=0)
    trend: VolumeTrend


class TechnicalIndicators(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    as_of: datetime
    close: float
    sma_20: float | None = None
    sma_50: float | None = None
    rsi_14: float | None = None
    macd: MACDValues | None = None
    atr_14: float | None = None
    volume: VolumeAnalysis | None = None


def compute_sma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(window=period, min_periods=period).mean()


def compute_rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)

    avg_gain = gains.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    # avg_loss == 0 over the lookback (all gains, e.g. a strict uptrend) makes
    # `rs` NaN via the replace() above even though RSI is well-defined there:
    # conventionally 100 when there were gains, 50 on a completely flat window.
    rsi = rsi.where(avg_loss != 0, np.where(avg_gain > 0, 100.0, 50.0))
    return rsi.replace([np.inf, -np.inf], np.nan)


def compute_macd(
    close: pd.Series,
    *,
    fast_period: int = MACD_FAST_PERIOD,
    slow_period: int = MACD_SLOW_PERIOD,
    signal_period: int = MACD_SIGNAL_PERIOD,
) -> pd.DataFrame:
    ema_fast = close.ewm(span=fast_period, adjust=False).mean()
    ema_slow = close.ewm(span=slow_period, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line

    return pd.DataFrame(
        {
            "macd": macd_line,
            "signal": signal_line,
            "histogram": histogram,
        }
    )


def compute_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = ATR_PERIOD,
) -> pd.Series:
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window=period, min_periods=period).mean()


def compute_volume_analysis(
    volume: pd.Series,
    *,
    sma_period: int = VOLUME_SMA_PERIOD,
    trend_lookback: int = VOLUME_TREND_LOOKBACK,
) -> VolumeAnalysis | None:
    if len(volume) < sma_period:
        return None

    volume_sma = volume.rolling(window=sma_period, min_periods=sma_period).mean()
    current_volume = float(volume.iloc[-1])
    volume_sma_20 = float(volume_sma.iloc[-1])

    if volume_sma_20 == 0:
        volume_ratio = 0.0
    else:
        volume_ratio = current_volume / volume_sma_20

    trend = _volume_trend(volume, lookback=trend_lookback)

    return VolumeAnalysis(
        current_volume=current_volume,
        volume_sma_20=volume_sma_20,
        volume_ratio=volume_ratio,
        trend=trend,
    )


def compute_indicators(ohlcv: OHLCV) -> TechnicalIndicators:
    frame = ohlcv.to_dataframe()
    if frame.empty:
        raise ValueError(f"No OHLCV bars available for {ohlcv.symbol}.")

    close = frame["Close"]
    high = frame["High"]
    low = frame["Low"]
    volume = frame["Volume"]

    sma_20 = compute_sma(close, SMA_FAST_PERIOD)
    sma_50 = compute_sma(close, SMA_SLOW_PERIOD)
    rsi_14 = compute_rsi(close, RSI_PERIOD)
    macd_frame = compute_macd(close)
    atr_14 = compute_atr(high, low, close, ATR_PERIOD)
    volume_analysis = compute_volume_analysis(volume)

    as_of = frame.index[-1]
    if not isinstance(as_of, datetime):
        as_of = pd.Timestamp(as_of).to_pydatetime()
    if as_of.tzinfo is not None:
        as_of = as_of.replace(tzinfo=None)

    macd_values = _latest_macd(macd_frame)
    return TechnicalIndicators(
        symbol=ohlcv.symbol,
        as_of=as_of,
        close=float(close.iloc[-1]),
        sma_20=_latest_value(sma_20),
        sma_50=_latest_value(sma_50),
        rsi_14=_latest_value(rsi_14),
        macd=macd_values,
        atr_14=_latest_value(atr_14),
        volume=volume_analysis,
    )


def _latest_value(series: pd.Series) -> float | None:
    if series.empty:
        return None
    value = series.iloc[-1]
    if pd.isna(value):
        return None
    return float(value)


def _latest_macd(macd_frame: pd.DataFrame) -> MACDValues | None:
    if macd_frame.empty:
        return None

    macd = macd_frame["macd"].iloc[-1]
    signal = macd_frame["signal"].iloc[-1]
    histogram = macd_frame["histogram"].iloc[-1]
    if pd.isna(macd) or pd.isna(signal) or pd.isna(histogram):
        return None

    return MACDValues(
        macd=float(macd),
        signal=float(signal),
        histogram=float(histogram),
    )


def _classify_volume_slope(normalized_slope: float) -> VolumeTrend:
    if normalized_slope > 0.05:
        return "increasing"
    if normalized_slope < -0.05:
        return "decreasing"
    return "neutral"


def _volume_trend(volume: pd.Series, *, lookback: int) -> VolumeTrend:
    if len(volume) < lookback + 1:
        return "neutral"

    recent = volume.iloc[-lookback:]
    x = np.arange(lookback, dtype=float)
    y = recent.to_numpy(dtype=float)
    slope = np.polyfit(x, y, 1)[0]

    average_volume = float(np.mean(y))
    if average_volume == 0:
        return "neutral"

    return _classify_volume_slope(slope / average_volume)


# ---------------------------------------------------------------------------
# Full time-series indicators (backtesting).
#
# compute_indicators()/compute_volume_analysis() above return only the latest
# snapshot value, which is all the live LangGraph pipeline (Phase 2) needs.
# The backtester needs every bar's indicator value, computed using only that
# bar and earlier ones — the functions below reuse the exact same rolling/ewm
# math as the snapshot functions (no new indicator logic), just without
# collapsing the result down to `.iloc[-1]`.
# ---------------------------------------------------------------------------


def compute_volume_ratio_series(
    volume: pd.Series, *, sma_period: int = VOLUME_SMA_PERIOD
) -> pd.Series:
    volume_sma = volume.rolling(window=sma_period, min_periods=sma_period).mean()
    ratio = volume / volume_sma.replace(0, np.nan)
    return ratio.replace([np.inf, -np.inf], np.nan)


def compute_volume_trend_series(
    volume: pd.Series, *, lookback: int = VOLUME_TREND_LOOKBACK
) -> pd.Series:
    def _normalized_slope(window: pd.Series) -> float:
        x = np.arange(len(window), dtype=float)
        y = window.to_numpy(dtype=float)
        slope = np.polyfit(x, y, 1)[0]
        average = float(np.mean(y))
        if average == 0:
            return np.nan
        return slope / average

    normalized_slope = volume.rolling(window=lookback, min_periods=lookback).apply(
        _normalized_slope, raw=False
    )
    return normalized_slope.apply(
        lambda value: _classify_volume_slope(value) if pd.notna(value) else "neutral"
    )


def compute_indicator_series(ohlcv: OHLCV) -> pd.DataFrame:
    """Every indicator, at every bar, using only that bar and earlier ones.

    Each column is produced by the same rolling/ewm functions used for the
    live snapshot above, so a value at row i is — by construction of those
    functions — derived only from rows <= i. This is what makes the
    backtester's no-look-ahead guarantee possible: reading row i here is
    always safe for a signal generated "at bar i".
    """
    frame = ohlcv.to_dataframe()
    if frame.empty:
        raise ValueError(f"No OHLCV bars available for {ohlcv.symbol}.")

    close, high, low, volume = frame["Close"], frame["High"], frame["Low"], frame["Volume"]
    macd_frame = compute_macd(close)

    return pd.DataFrame(
        {
            "open": frame["Open"],
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "sma_20": compute_sma(close, SMA_FAST_PERIOD),
            "sma_50": compute_sma(close, SMA_SLOW_PERIOD),
            "rsi_14": compute_rsi(close, RSI_PERIOD),
            "macd": macd_frame["macd"],
            "macd_signal": macd_frame["signal"],
            "macd_histogram": macd_frame["histogram"],
            "atr_14": compute_atr(high, low, close, ATR_PERIOD),
            "volume_ratio": compute_volume_ratio_series(volume),
            "volume_trend": compute_volume_trend_series(volume),
        },
        index=frame.index,
    )
