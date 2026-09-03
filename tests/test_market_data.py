from datetime import datetime

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from market.data_provider import OHLCV, MarketDataError
from market.indicators import (
    compute_atr,
    compute_indicators,
    compute_macd,
    compute_rsi,
    compute_sma,
    compute_volume_analysis,
)


def _synthetic_frame(n: int = 80, start_price: float = 100.0) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    # Monotonic-ish uptrend with a little noise, deterministic (fixed seed).
    rng = np.random.default_rng(seed=42)
    noise = rng.normal(0, 0.5, n)
    close = start_price + np.arange(n) * 0.3 + noise
    high = close + np.abs(rng.normal(0.5, 0.2, n))
    low = close - np.abs(rng.normal(0.5, 0.2, n))
    open_ = close - rng.normal(0, 0.2, n)
    volume = rng.integers(1_000_000, 2_000_000, n).astype(float)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=pd.DatetimeIndex(dates, name="Date"),
    )


def test_ohlcv_from_dataframe_round_trip():
    frame = _synthetic_frame(10)
    ohlcv = OHLCV.from_dataframe(symbol="TEST", interval="1d", frame=frame)

    assert ohlcv.symbol == "TEST"
    assert len(ohlcv.bars) == 10

    round_tripped = ohlcv.to_dataframe()
    assert list(round_tripped.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(round_tripped) == 10
    assert round_tripped["Close"].iloc[0] == pytest.approx(frame["Close"].iloc[0])


def test_ohlcv_from_dataframe_filters_nan_rows():
    frame = _synthetic_frame(5)
    frame.iloc[2, frame.columns.get_loc("Close")] = np.nan

    ohlcv = OHLCV.from_dataframe(symbol="TEST", interval="1d", frame=frame)

    assert len(ohlcv.bars) == 4  # the NaN row is dropped, not coerced to 0/None


def test_ohlcv_from_dataframe_missing_columns_raises():
    frame = pd.DataFrame({"Open": [1.0], "High": [2.0]})  # missing Low/Close/Volume

    with pytest.raises(MarketDataError):
        OHLCV.from_dataframe(symbol="TEST", interval="1d", frame=frame)


def test_ohlcv_from_dataframe_empty_is_empty_not_an_error():
    ohlcv = OHLCV.from_dataframe(symbol="TEST", interval="1d", frame=pd.DataFrame())
    assert ohlcv.bars == []


def test_ohlcv_from_dataframe_strips_tzinfo_from_a_tz_aware_index():
    """Regression (Phase 33): `pd.Timestamp` IS a `datetime` subclass, so
    `_to_timestamp`'s `isinstance(value, datetime)` branch previously
    matched every real DataFrame index value and returned it AS-IS,
    silently skipping the tzinfo-stripping logic a few lines below --
    dead code for the one call site that matters. Found via a real scan
    against a live ^NSEI benchmark whose Yahoo data carries an
    Asia/Kolkata-aware index: market_intelligence.scanner's benchmark
    reindex raised `TypeError: Cannot compare dtypes datetime64[us,
    UTC+05:30] and datetime64[us]` because only ^NSEI's bars kept their
    real tzinfo. Every OHLCVBar.timestamp must be naive, per this
    project's own "Yahoo/mock bars are naive by convention" invariant."""
    frame = _synthetic_frame(5)
    frame.index = frame.index.tz_localize("Asia/Kolkata")
    assert frame.index.tz is not None  # sanity: the input really is tz-aware

    ohlcv = OHLCV.from_dataframe(symbol="TEST", interval="1d", frame=frame)

    assert len(ohlcv.bars) == 5
    for bar in ohlcv.bars:
        assert bar.timestamp.tzinfo is None


def test_ohlcv_from_dataframe_naive_index_still_works_unchanged():
    """Non-regression: the already-working naive-index path (the vast
    majority of real Yahoo data) must be completely unaffected."""
    frame = _synthetic_frame(5)
    assert frame.index.tz is None

    ohlcv = OHLCV.from_dataframe(symbol="TEST", interval="1d", frame=frame)

    assert len(ohlcv.bars) == 5
    for bar in ohlcv.bars:
        assert bar.timestamp.tzinfo is None


def test_ohlcv_bar_rejects_non_positive_price():
    with pytest.raises(ValidationError):
        OHLCV(
            symbol="TEST",
            interval="1d",
            bars=[
                {
                    "timestamp": datetime(2026, 1, 1),
                    "open": 0,  # violates gt=0
                    "high": 1,
                    "low": 1,
                    "close": 1,
                    "volume": 1,
                }
            ],
        )


def test_compute_sma_matches_manual_average():
    close = pd.Series([1, 2, 3, 4, 5], dtype=float)
    sma = compute_sma(close, period=3)
    assert sma.iloc[-1] == pytest.approx((3 + 4 + 5) / 3)
    assert pd.isna(sma.iloc[0])  # not enough history yet


def test_compute_rsi_is_100_for_strictly_increasing_series():
    close = pd.Series(range(1, 40), dtype=float)  # always up, never down
    rsi = compute_rsi(close, period=14)
    assert rsi.iloc[-1] == pytest.approx(100.0, abs=0.01)


def test_compute_macd_histogram_is_macd_minus_signal():
    close = pd.Series(np.linspace(100, 150, 60))
    macd_frame = compute_macd(close)
    last = macd_frame.iloc[-1]
    assert last["histogram"] == pytest.approx(last["macd"] - last["signal"])


def test_compute_atr_is_non_negative():
    frame = _synthetic_frame(30)
    atr = compute_atr(frame["High"], frame["Low"], frame["Close"], period=14)
    assert (atr.dropna() >= 0).all()


def test_compute_volume_analysis_needs_minimum_history():
    volume = pd.Series([100.0] * 5)  # fewer than sma_period=20
    assert compute_volume_analysis(volume) is None


def test_compute_indicators_end_to_end_on_synthetic_uptrend():
    frame = _synthetic_frame(80)
    ohlcv = OHLCV.from_dataframe(symbol="SYN", interval="1d", frame=frame)

    indicators = compute_indicators(ohlcv)

    assert indicators.symbol == "SYN"
    assert indicators.sma_20 is not None
    assert indicators.sma_50 is not None
    assert indicators.rsi_14 is not None
    assert indicators.macd is not None
    assert indicators.atr_14 is not None
    # Synthetic series trends up, so short SMA should sit above long SMA.
    assert indicators.sma_20 > indicators.sma_50


def test_compute_indicators_raises_on_empty_ohlcv():
    empty = OHLCV(symbol="EMPTY", interval="1d", bars=[])
    with pytest.raises(ValueError):
        compute_indicators(empty)
