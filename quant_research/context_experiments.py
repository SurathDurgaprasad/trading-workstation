"""BUILD THE REAL INDIAN TRADING DECISION BRAIN mission, Phase 4: the
contextual experiment framework. Reuses quant_research.market_behavior's
measure_condition()/SymbolDataset unchanged -- the only genuinely new
capability needed is merging an EXTERNAL, date-aligned regime series
(NIFTY's own trend, a NIFTY sector index's own trend, India VIX regime)
onto each stock's own SymbolDataset.frame, since measure_condition's
existing regime_filter only ever classifies the STOCK's OWN trend/
volatility (backtesting.regime applied to that stock's own OHLCV), never
an external benchmark's.

Frozen baseline (Phase 2): baseline_buy_condition() is a causal replica
of the trend+momentum corroboration gate that actually drives every real
BUY (decision_engine.rules.classify with require_corroboration_for_buy
requires market_intelligence.scanner's trend_score > 0 AND
momentum_score > 0 -- see market_intelligence/scanner.py's
_score_candidate: trend_score=+1.0 iff close > sma_20 > sma_50,
momentum_score = (rsi_14 - 50) / 50). composite_score's other terms
(breakout/relative-strength/sector-strength) are per-candidate-scan
context not available bar-by-bar in a precomputed indicator series, so
this proxy is intentionally narrower than a literal scanner replay --
disclosed here and in every hypothesis that uses it, never silently
assumed identical. Not modified while contextual effects are measured,
per Phase 2's own explicit instruction.
"""

import pandas as pd

from quant_research.market_behavior import SymbolDataset


def baseline_buy_condition(row: pd.Series) -> bool:
    """See module docstring -- causal proxy for the real BUY
    corroboration gate: uptrend structure (close > sma_20 > sma_50) AND
    bullish momentum (rsi_14 > 50)."""
    close, sma_20, sma_50, rsi = row.get("close"), row.get("sma_20"), row.get("sma_50"), row.get("rsi_14")
    if pd.isna(close) or pd.isna(sma_20) or pd.isna(sma_50) or pd.isna(rsi):
        return False
    uptrend = close > sma_20 > sma_50
    bullish_momentum = rsi > 50.0
    return bool(uptrend and bullish_momentum)


def build_benchmark_regime_series(
    symbol: str, *, period: str = "5y", interval: str = "1d", slope_lookback: int = 10, use_cache: bool = True,
) -> "pd.Series | None":
    """One benchmark/index's own causal trend_regime, one label per bar,
    indexed by date. Reuses backtesting.regime.classify_trend_at exactly
    as quant_research.market_behavior.build_symbol_dataset already does
    for a stock's OWN regime, just applied to an index/benchmark's OHLCV
    instead. Returns None (never raises) on a fetch failure, matching
    build_symbol_dataset's own posture -- one bad benchmark fetch must
    never abort a whole research run."""
    from backtesting.cache import CachedMarketDataProvider
    from backtesting.regime import classify_trend_at
    from market.data_provider import MarketDataError, get_market_data_provider
    from market.indicators import compute_indicator_series

    provider = CachedMarketDataProvider(get_market_data_provider()) if use_cache else get_market_data_provider()
    try:
        ohlcv = provider.fetch_ohlcv(symbol, period=period, interval=interval)
        frame = compute_indicator_series(ohlcv)
    except (MarketDataError, ValueError):
        return None
    if frame.empty:
        return None
    labels = [classify_trend_at(frame, i, slope_lookback=slope_lookback).value for i in range(len(frame))]
    return pd.Series(labels, index=frame.index, name="regime")


def build_benchmark_volatility_series(
    symbol: str, *, period: str = "5y", interval: str = "1d", lookback: int = 60, use_cache: bool = True,
) -> "pd.Series | None":
    """Volatility-regime counterpart to build_benchmark_regime_series --
    reuses backtesting.regime.classify_volatility_at instead of
    classify_trend_at, same fetch/failure posture."""
    from backtesting.cache import CachedMarketDataProvider
    from backtesting.regime import classify_volatility_at
    from market.data_provider import MarketDataError, get_market_data_provider
    from market.indicators import compute_indicator_series

    provider = CachedMarketDataProvider(get_market_data_provider()) if use_cache else get_market_data_provider()
    try:
        ohlcv = provider.fetch_ohlcv(symbol, period=period, interval=interval)
        frame = compute_indicator_series(ohlcv)
    except (MarketDataError, ValueError):
        return None
    if frame.empty:
        return None
    labels = [classify_volatility_at(frame, i, lookback=lookback).value for i in range(len(frame))]
    return pd.Series(labels, index=frame.index, name="regime")


def build_india_vix_regime_series(
    symbol: str = "^INDIAVIX", *, period: str = "5y", interval: str = "1d", use_cache: bool = True,
) -> "pd.Series | None":
    """Historical counterpart to market_intelligence.regime.
    compute_india_vix_context, which only ever classifies the LATEST
    bar. Reuses that function's exact thresholds
    (DEFAULT_VIX_LOOKBACK/ELEVATED/DEPRESSED_MULTIPLIER) and exact
    formula (ratio = last_value / trailing_average of the preceding
    `lookback` closes, excluding the current bar) applied at every bar
    instead of just the last one -- not a new definition of "elevated
    VIX," the same one, made causal-historical."""
    from backtesting.cache import CachedMarketDataProvider
    from market.data_provider import MarketDataError, get_market_data_provider
    from market_intelligence.regime import DEFAULT_VIX_DEPRESSED_MULTIPLIER, DEFAULT_VIX_ELEVATED_MULTIPLIER, DEFAULT_VIX_LOOKBACK, VixRegime

    provider = CachedMarketDataProvider(get_market_data_provider()) if use_cache else get_market_data_provider()
    try:
        ohlcv = provider.fetch_ohlcv(symbol, period=period, interval=interval)
    except (MarketDataError, ValueError):
        return None
    bars = ohlcv.bars
    if len(bars) < DEFAULT_VIX_LOOKBACK + 1:
        return None

    closes = [float(bar.close) for bar in bars]
    dates = [bar.timestamp for bar in bars]
    labels = []
    for i in range(len(closes)):
        if i < DEFAULT_VIX_LOOKBACK:
            labels.append(VixRegime.UNKNOWN.value)
            continue
        trailing_window = closes[i - DEFAULT_VIX_LOOKBACK:i]
        trailing_average = sum(trailing_window) / len(trailing_window)
        if trailing_average <= 0:
            labels.append(VixRegime.UNKNOWN.value)
            continue
        ratio = closes[i] / trailing_average
        if ratio >= DEFAULT_VIX_ELEVATED_MULTIPLIER:
            labels.append(VixRegime.ELEVATED.value)
        elif ratio <= DEFAULT_VIX_DEPRESSED_MULTIPLIER:
            labels.append(VixRegime.DEPRESSED.value)
        else:
            labels.append(VixRegime.NORMAL.value)
    return pd.Series(labels, index=pd.DatetimeIndex(dates), name="regime")


def attach_external_regime(datasets: "dict[str, SymbolDataset]", *, regime_series: pd.Series, column_name: str) -> None:
    """Mutates each dataset's frame in place, adding `column_name`: the
    external regime_series's value AS OF each stock's own bar date,
    forward-filled onto the stock's own calendar -- the identical causal
    cross-market alignment pattern quant_research.alpha_features.
    add_alpha_features already uses for relative_strength_20 (never a
    same-day peek past what the external series' own latest available
    value actually was)."""
    for dataset in datasets.values():
        aligned = regime_series.reindex(dataset.frame.index, method="ffill")
        dataset.frame[column_name] = aligned
