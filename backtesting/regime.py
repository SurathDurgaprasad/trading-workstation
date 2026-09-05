"""Strategy science, Phase 1 (regime analysis) -- deterministic,
look-ahead-safe market regime classification AT A SPECIFIC BAR INDEX,
using only indicator_series.iloc[:index+1] (rows after `index` are never
read). Reuses columns market.indicators.compute_indicator_series already
computes (sma_20, sma_50, atr_14, close) -- no new indicator introduced,
matching the mission's own "avoid indicator soup" instruction.

Distinct from two existing, unmodified classifiers that answer a
different question each:
  - learning.regime.classify_regime_at -- "what is THE MARKET's broad
    200-bar trend as of NOW", via a fresh provider fetch.
  - market_intelligence.regime.compute_benchmark_context -- "what is a
    BENCHMARK's trend+volatility as of NOW", also a fresh fetch.
This module answers "what was THIS SYMBOL's own regime at bar index i",
from data already in hand (a backtest's own indicator_series) -- built
for after-the-fact analysis of historical trades, where a fresh network/
cache fetch per trade would be wasteful and where "as of now" has no
meaning at all (the question is about a historical entry, not the
present moment).

Composable, two-dimensional (per the mission's own stated preference):
TrendRegime (UP/DOWN/SIDEWAYS) x VolatilityRegime (HIGH/NORMAL/LOW).
"""

from dataclasses import dataclass
from enum import Enum

import pandas as pd

from backtesting.trade import Trade


class TrendRegime(str, Enum):
    UP = "TRENDING_UP"
    DOWN = "TRENDING_DOWN"
    SIDEWAYS = "SIDEWAYS"
    UNKNOWN = "UNKNOWN"


class VolatilityRegime(str, Enum):
    HIGH = "HIGH_VOLATILITY"
    LOW = "LOW_VOLATILITY"
    NORMAL = "NORMAL_VOLATILITY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RegimeClassification:
    trend: TrendRegime
    volatility: VolatilityRegime


DEFAULT_TREND_SLOPE_LOOKBACK = 10
"""Bars back from `index` that sma_20's own slope is measured over --
distinguishes a genuine trend from sideways chop where sma_20 sits
barely above/below sma_50 without actually moving. Not tuned against
historical performance (no such study exists) -- a stated, documented,
explicit default, same "no fabricated threshold" posture
market_intelligence.regime.compute_benchmark_context's own thresholds
already use."""
DEFAULT_TREND_SLOPE_THRESHOLD_PCT = 0.5
DEFAULT_VOLATILITY_LOOKBACK = 60
DEFAULT_HIGH_VOLATILITY_MULTIPLIER = 1.5
DEFAULT_LOW_VOLATILITY_MULTIPLIER = 0.67

_RATIO_EPSILON = 1e-9
"""A ratio that is mathematically exactly at a threshold can still land
a hair on the wrong side of it after floating-point division/averaging
-- found via a genuine test failure, not a hypothetical: pandas.Series.
mean() of 60 identical 0.02 values returns 0.020000000000000004, which
turns an exactly-1.5 ratio into 1.4999999999999996, silently
misclassifying a boundary case as NORMAL instead of HIGH. This epsilon
is a numerical-precision tolerance, not a change to the threshold
itself."""


def classify_trend_at(
    indicator_series: pd.DataFrame, index: int, *,
    slope_lookback: int = DEFAULT_TREND_SLOPE_LOOKBACK,
    slope_threshold_pct: float = DEFAULT_TREND_SLOPE_THRESHOLD_PCT,
) -> TrendRegime:
    """UNKNOWN (never a guess) when `index` is too early for a full
    `slope_lookback` window, or any required value is NaN (indicator
    warm-up not yet complete)."""
    if index < slope_lookback:
        return TrendRegime.UNKNOWN

    row = indicator_series.iloc[index]
    prior_row = indicator_series.iloc[index - slope_lookback]
    sma_20, sma_50, prior_sma_20 = row.get("sma_20"), row.get("sma_50"), prior_row.get("sma_20")
    if pd.isna(sma_20) or pd.isna(sma_50) or pd.isna(prior_sma_20) or float(prior_sma_20) == 0:
        return TrendRegime.UNKNOWN

    slope_pct = (float(sma_20) - float(prior_sma_20)) / abs(float(prior_sma_20)) * 100.0

    if float(sma_20) > float(sma_50) and slope_pct >= slope_threshold_pct:
        return TrendRegime.UP
    if float(sma_20) < float(sma_50) and slope_pct <= -slope_threshold_pct:
        return TrendRegime.DOWN
    return TrendRegime.SIDEWAYS


def classify_volatility_at(
    indicator_series: pd.DataFrame, index: int, *,
    lookback: int = DEFAULT_VOLATILITY_LOOKBACK,
    high_multiplier: float = DEFAULT_HIGH_VOLATILITY_MULTIPLIER,
    low_multiplier: float = DEFAULT_LOW_VOLATILITY_MULTIPLIER,
) -> VolatilityRegime:
    """Current bar's ATR14-as-percent-of-close, compared to its own
    trailing average over the `lookback` bars STRICTLY BEFORE `index`
    (the current bar is excluded from its own baseline -- same
    convention, and same reason, market_intelligence.regime.
    compute_benchmark_context already uses: a single volatile day must
    not partially average itself away)."""
    if index < lookback:
        return VolatilityRegime.UNKNOWN

    row = indicator_series.iloc[index]
    atr, close = row.get("atr_14"), row.get("close")
    if pd.isna(atr) or pd.isna(close) or float(close) <= 0:
        return VolatilityRegime.UNKNOWN

    window = indicator_series.iloc[index - lookback:index]
    window_atr_pct = (window["atr_14"] / window["close"]).dropna()
    if window_atr_pct.empty:
        return VolatilityRegime.UNKNOWN
    trailing_avg = float(window_atr_pct.mean())
    if trailing_avg <= 0:
        return VolatilityRegime.UNKNOWN

    ratio = (float(atr) / float(close)) / trailing_avg
    if ratio >= high_multiplier - _RATIO_EPSILON:
        return VolatilityRegime.HIGH
    if ratio <= low_multiplier + _RATIO_EPSILON:
        return VolatilityRegime.LOW
    return VolatilityRegime.NORMAL


def classify_regime_at_index(indicator_series: pd.DataFrame, index: int) -> RegimeClassification:
    return RegimeClassification(
        trend=classify_trend_at(indicator_series, index),
        volatility=classify_volatility_at(indicator_series, index),
    )


def group_trade_returns_by_regime(
    trades_with_series: list[tuple[Trade, pd.DataFrame]],
) -> dict[RegimeClassification, list[float]]:
    """Groups per-trade returns by the (trend, volatility) regime AT EACH
    TRADE'S OWN entry_time, using that trade's own symbol's indicator
    series -- never a different symbol's, never a later bar than the
    entry itself (entry_time is looked up by exact index match, since
    run_backtest's own fill mechanics set entry_time to one of the
    series' own bar timestamps).

    A trade whose entry_time cannot be found in its own series (should
    not occur for a trade genuinely produced by run_backtest against
    that exact series, but this function makes no assumption about its
    caller) is skipped, never silently miscounted into a bucket it
    doesn't belong to."""
    from backtesting.universe import per_trade_returns

    buckets: dict[RegimeClassification, list[float]] = {}
    for trade, indicator_series in trades_with_series:
        try:
            index = indicator_series.index.get_loc(trade.entry_time)
        except KeyError:
            continue
        if not isinstance(index, int):
            continue  # a non-unique index would return a slice/mask -- skip rather than guess
        classification = classify_regime_at_index(indicator_series, index)
        returns = per_trade_returns([trade])
        if returns:
            buckets.setdefault(classification, []).extend(returns)

    return buckets
