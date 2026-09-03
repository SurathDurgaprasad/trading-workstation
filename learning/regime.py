"""Phase 24 -- market regime classification for performance analysis.

Reuses the SAME broad-trend convention Phase 9's strategy/regime_filters.py
already established and tested (close vs. its own 200-bar SMA) -- not a
new regime methodology invented for this phase. Fails closed (UNKNOWN)
on insufficient history or a fetch failure, never guessing.
"""

from datetime import datetime, timezone
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
    # Phase 33 bug fix -- found via a new caller (market_intelligence.regime,
    # which passes a real, UTC-aware `datetime.now(timezone.utc)`) that
    # Phase 24's own original call site never exercised (it always passed an
    # already-naive `as_of` derived from a Yahoo/mock bar timestamp). This
    # project's bars are a genuine mix -- Yahoo/mock naive, real Dhan bars
    # UTC-aware since the Phase 16 fix -- so `frame.index` can be either;
    # pandas raises TypeError comparing a naive DatetimeIndex against an
    # aware scalar (or vice versa). Normalize `as_of` to match the index's
    # own awareness, never the reverse (never invent a timezone for the bar
    # data itself).
    as_of_for_comparison = as_of
    if frame.index.tz is not None and as_of.tzinfo is None:
        as_of_for_comparison = as_of.replace(tzinfo=timezone.utc)
    elif frame.index.tz is None and as_of.tzinfo is not None:
        as_of_for_comparison = as_of.replace(tzinfo=None)
    history = frame[frame.index <= as_of_for_comparison]
    if len(history) < BROAD_TREND_SMA_PERIOD:
        return MarketRegime.UNKNOWN

    sma = compute_sma(history["Close"], BROAD_TREND_SMA_PERIOD).iloc[-1]
    if pd.isna(sma):
        return MarketRegime.UNKNOWN

    last_close = float(history["Close"].iloc[-1])
    return MarketRegime.UPTREND if last_close > float(sma) else MarketRegime.DOWNTREND
