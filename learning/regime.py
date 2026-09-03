"""Phase 24 -- market regime classification for performance analysis.

Reuses the SAME broad-trend convention Phase 9's strategy/regime_filters.py
already established and tested (close vs. its own 200-bar SMA) -- not a
new regime methodology invented for this phase. Fails closed (UNKNOWN)
on insufficient history or a fetch failure, never guessing.
"""

from datetime import datetime
from enum import Enum

import pandas as pd

from market.data_provider import MarketDataError, MarketDataProvider
from market.indicators import compute_sma
from strategy.regime_filters import BROAD_TREND_SMA_PERIOD


class MarketRegime(str, Enum):
    UPTREND = "UPTREND"
    DOWNTREND = "DOWNTREND"
    UNKNOWN = "UNKNOWN"


def classify_regime_at(
    symbol: str,
    as_of: datetime,
    *,
    provider: MarketDataProvider,
    period: str = "2y",
    interval: str = "1d",
) -> MarketRegime:
    try:
        ohlcv = provider.fetch_ohlcv(symbol, period=period, interval=interval)
    except MarketDataError:
        return MarketRegime.UNKNOWN

    frame = ohlcv.to_dataframe()
    history = frame[frame.index <= as_of]
    if len(history) < BROAD_TREND_SMA_PERIOD:
        return MarketRegime.UNKNOWN

    sma = compute_sma(history["Close"], BROAD_TREND_SMA_PERIOD).iloc[-1]
    if pd.isna(sma):
        return MarketRegime.UNKNOWN

    last_close = float(history["Close"].iloc[-1])
    return MarketRegime.UPTREND if last_close > float(sma) else MarketRegime.DOWNTREND
