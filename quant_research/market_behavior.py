"""TRADING BRAIN EXECUTION LOOP mission -- the Market Behavior Research
Engine Part D asks for: "what actually happens after condition X," not
"what strategy should we build." This module measures CONDITIONAL
FORWARD RETURNS -- for a boolean condition evaluated at each historical
bar, what did price actually do over the following 1/2/3/5/10/20 bars --
completely independent of any stop/target/position-sizing/strategy
concept. No signal is generated here, no trade is simulated; this is
pure measurement.

Deliberately outside strategy/, risk/, paper/, backtesting/, and never
imported by any of them, the MCP server, or main.py -- same posture as
quant_research/alpha_features.py's own module docstring ("research-only
... nothing here is reachable from live/paper execution").

Reuses, never recomputes:
  - market.indicators.compute_indicator_series -- causal OHLCV+indicators.
  - quant_research.alpha_features.add_alpha_features /
    add_forward_return_targets -- causal features (zscore_close_20,
    relative_strength_20, atr_pct_of_price, volume_ratio) and the
    forward-return LABEL columns this module's entire purpose depends
    on (fwd_return_h = close.shift(-h)/close - 1 -- deliberately the
    only look-ahead in this module, and only ever used as a label to
    MEASURE, never fed into any condition or signal).
  - backtesting.regime.classify_trend_at / classify_volatility_at --
    causal per-bar regime classification, for Part E's regime slicing.
  - backtesting.splits.split_periods -- the same 60/20/20 chronological
    dev/val/oos convention every hypothesis in this project's history
    uses, for Part G's discovery/validation/OOS discipline.
  - market_data.universe.exchange_for_symbol -- NSE/BSE/OTHER
    classification, for Part D's "never pool NSE and US" requirement.

This module's own new work is narrow: a general-purpose
"summarize this list of forward returns" statistics function (mean,
median, win rate, std dev, a CI on the mean, and upside/downside tail
percentiles -- NOT a trade-oriented ProfitabilityReport, since there is
no stop/target/win/loss structure here, just a continuous return
distribution) and a driver that builds one enriched, precomputed
per-symbol dataset ONCE and lets many different conditions be measured
against it cheaply (fetch/compute is the expensive part; evaluating a
boolean mask against an already-built DataFrame is not).
"""

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

FORWARD_HORIZONS = (1, 2, 3, 5, 10, 20)
"""Bars, matching this mission's own explicit list ('1 day, 2 days, 3
days, 5 days, 10 days, 20 days where sufficient data exists')."""

DEFAULT_REGIME_SLOPE_LOOKBACK = 10
DEFAULT_REGIME_VOLATILITY_LOOKBACK = 60
"""Reuses backtesting.regime's own defaults verbatim -- not a new
threshold choice, this module's regime slicing IS that module's own
classifier, just applied to raw forward returns instead of trade
returns."""


@dataclass(frozen=True)
class ForwardReturnSummary:
    """A pure statistical summary of one list of forward returns -- no
    stop/target/win-loss trade structure assumed, unlike
    learning.profitability.ProfitabilityReport (built for realized
    trade returns, a different question)."""

    condition: str
    market: str
    """"NSE", "US", or a caller-defined label (e.g. a regime bucket
    name) -- never "POOLED" unless the caller explicitly asked to pool,
    per this mission's own "do not pool markets unless explicitly
    testing pooled behavior" instruction."""
    horizon_bars: int
    sample_size: int
    mean_return: float | None
    median_return: float | None
    win_rate: float | None
    """Fraction of returns > 0. None if sample_size == 0."""
    std_dev: float | None
    mean_ci_low: float | None
    mean_ci_high: float | None
    """95% CI on the mean via normal approximation (same
    _CONFIDENCE_Z=1.9599... this project's own learning.profitability
    module uses elsewhere, not reimplemented differently here) -- None
    if sample_size < 2."""
    p5: float | None
    """5th percentile -- the downside tail."""
    p95: float | None
    """95th percentile -- the upside tail."""


_CONFIDENCE_Z = 1.959963984540054
"""learning.profitability's own hardcoded 95% two-sided normal-
approximation z-score, matched here so every confidence interval in
this project means the same thing -- not reimported directly to avoid
this research-only module depending on the live/paper-adjacent
learning/ package for one float constant."""


def summarize_forward_returns(returns: list[float], *, condition: str, market: str, horizon_bars: int) -> ForwardReturnSummary:
    """Pure function: no I/O, no look-ahead of its own (the caller
    already decided which returns belong in this list)."""
    n = len(returns)
    if n == 0:
        return ForwardReturnSummary(
            condition=condition, market=market, horizon_bars=horizon_bars, sample_size=0,
            mean_return=None, median_return=None, win_rate=None, std_dev=None,
            mean_ci_low=None, mean_ci_high=None, p5=None, p95=None,
        )

    series = pd.Series(returns)
    mean_return = float(series.mean())
    median_return = float(series.median())
    win_rate = float((series > 0).mean())
    std_dev = float(series.std(ddof=1)) if n >= 2 else None
    if std_dev is not None and n >= 2:
        margin = _CONFIDENCE_Z * std_dev / (n**0.5)
        mean_ci_low, mean_ci_high = mean_return - margin, mean_return + margin
    else:
        mean_ci_low = mean_ci_high = None
    p5 = float(series.quantile(0.05))
    p95 = float(series.quantile(0.95))

    return ForwardReturnSummary(
        condition=condition, market=market, horizon_bars=horizon_bars, sample_size=n,
        mean_return=mean_return, median_return=median_return, win_rate=win_rate, std_dev=std_dev,
        mean_ci_low=mean_ci_low, mean_ci_high=mean_ci_high, p5=p5, p95=p95,
    )


@dataclass
class SymbolDataset:
    """One symbol's fully-precomputed, causal dataset: raw indicators +
    alpha features + forward-return labels + regime columns, all
    computed ONCE so many different conditions can be measured against
    it cheaply. `market` is "NSE", "BSE", or "OTHER" (matches
    market_data.universe.exchange_for_symbol -- "OTHER" covers US and
    any other non-Indian symbol; this module treats OTHER as "US" for
    reporting purposes since that is this project's only current
    non-Indian universe, but keeps the real classification in
    `raw_market` for honesty if that ever stops being true)."""

    symbol: str
    market: str
    raw_market: str
    frame: pd.DataFrame
    development_end: datetime | None
    validation_end: datetime | None


def build_symbol_dataset(
    symbol: str, *, period: str = "5y", interval: str = "1d", horizons: tuple[int, ...] = FORWARD_HORIZONS,
    use_cache: bool = True,
) -> "SymbolDataset | None":
    """Fetches (cached), computes every reusable column ONCE. Returns
    None (never raises) on a market-data failure -- the caller is
    responsible for the same per-symbol isolation posture every other
    universe-level runner in this project already uses (one bad symbol
    must never abort the rest)."""
    from backtesting.cache import CachedMarketDataProvider
    from backtesting.regime import classify_trend_at, classify_volatility_at
    from backtesting.splits import split_periods
    from market.data_provider import MarketDataError, get_market_data_provider
    from market.indicators import compute_indicator_series
    from market_data.universe import exchange_for_symbol
    from quant_research.alpha_features import add_alpha_features, add_forward_return_targets

    provider = CachedMarketDataProvider(get_market_data_provider()) if use_cache else get_market_data_provider()
    try:
        ohlcv = provider.fetch_ohlcv(symbol, period=period, interval=interval)
        frame = compute_indicator_series(ohlcv)
    except (MarketDataError, ValueError):
        return None
    if len(frame) < DEFAULT_REGIME_VOLATILITY_LOOKBACK:
        return None  # too short for any regime classification or a 20-bar forward horizon to mean anything

    frame = add_alpha_features(frame, market_series=None)
    frame = add_forward_return_targets(frame, horizons=horizons)

    trends, vols = [], []
    for i in range(len(frame)):
        trends.append(classify_trend_at(frame, i, slope_lookback=DEFAULT_REGIME_SLOPE_LOOKBACK).value)
        vols.append(classify_volatility_at(frame, i, lookback=DEFAULT_REGIME_VOLATILITY_LOOKBACK).value)
    frame["trend_regime"] = trends
    frame["volatility_regime"] = vols

    raw_market = exchange_for_symbol(symbol)
    market = "NSE" if raw_market in ("NSE", "BSE") else "US"

    development_end = validation_end = None
    if len(frame) >= 2:
        split = split_periods(frame.index[0], frame.index[-1])
        development_end, validation_end = split.development_end, split.validation_end

    return SymbolDataset(symbol=symbol, market=market, raw_market=raw_market, frame=frame, development_end=development_end, validation_end=validation_end)


def build_universe_datasets(symbols: list[str], *, period: str = "5y", interval: str = "1d", use_cache: bool = True) -> dict[str, SymbolDataset]:
    """symbol -> SymbolDataset, silently excluding (not crashing on) any
    symbol build_symbol_dataset could not build. Fetch once, reuse
    across every condition measured this session -- the whole point of
    this function existing separately from measure_condition below."""
    out: dict[str, SymbolDataset] = {}
    for symbol in symbols:
        dataset = build_symbol_dataset(symbol, period=period, interval=interval, use_cache=use_cache)
        if dataset is not None:
            out[symbol] = dataset
    return out


_PeriodLiteral = str  # "full" | "development" | "validation" | "out_of_sample"


def _period_mask(dataset: SymbolDataset, period: _PeriodLiteral) -> pd.Series:
    index = dataset.frame.index
    if period == "full" or dataset.development_end is None:
        return pd.Series(True, index=index)
    if period == "development":
        return index <= dataset.development_end
    if period == "validation":
        return (index > dataset.development_end) & (index <= dataset.validation_end)
    if period == "out_of_sample":
        return index > dataset.validation_end
    raise ValueError(f"Unknown period: {period!r}")


def measure_condition(
    datasets: dict[str, SymbolDataset], *, condition_name: str, condition_fn,
    horizons: tuple[int, ...] = FORWARD_HORIZONS, period: _PeriodLiteral = "full",
    market_filter: str | None = None, regime_filter: tuple[str | None, str | None] | None = None,
) -> dict[int, ForwardReturnSummary]:
    """Pools forward returns across every symbol in `datasets` whose
    `market` matches `market_filter` (None = no market filter -- used
    internally when the caller has already pre-split datasets by
    market, e.g. measure_condition_by_market below), for every row
    where `condition_fn(row) is True` AND the row falls in `period`
    (dev/val/oos discipline, Part G) AND (if regime_filter is given)
    the row's own trend_regime/volatility_regime match
    (trend, volatility) -- either element None means "don't filter on
    that dimension." Returns one ForwardReturnSummary per horizon.

    `condition_fn` receives a single row (pd.Series) and must return
    bool -- the SAME predicate signature every FilteredStrategy/
    standalone-strategy candidate in this project's hypothesis registry
    already uses, so a promising discovery here can become a real
    Strategy predicate later (Part J) with zero translation cost."""
    pooled: dict[int, list[float]] = {h: [] for h in horizons}

    for dataset in datasets.values():
        if market_filter is not None and dataset.market != market_filter:
            continue
        frame = dataset.frame
        mask = _period_mask(dataset, period)
        sliced = frame.loc[mask]
        if sliced.empty:
            continue

        if regime_filter is not None:
            trend, vol = regime_filter
            if trend is not None:
                sliced = sliced.loc[sliced["trend_regime"] == trend]
            if vol is not None:
                sliced = sliced.loc[sliced["volatility_regime"] == vol]
            if sliced.empty:
                continue

        hits = sliced.apply(condition_fn, axis=1)
        matched = sliced.loc[hits.fillna(False)]
        if matched.empty:
            continue

        for h in horizons:
            col = f"fwd_return_{h}"
            if col not in matched.columns:
                continue
            pooled[h].extend(matched[col].dropna().tolist())

    market_label = market_filter or "POOLED"
    return {h: summarize_forward_returns(pooled[h], condition=condition_name, market=market_label, horizon_bars=h) for h in horizons}


def measure_condition_by_market(
    datasets: dict[str, SymbolDataset], *, condition_name: str, condition_fn,
    horizons: tuple[int, ...] = FORWARD_HORIZONS, period: _PeriodLiteral = "full",
    regime_filter: tuple[str | None, str | None] | None = None,
) -> dict[str, dict[int, ForwardReturnSummary]]:
    """The mission's own explicit default posture: NEVER pool NSE and
    US unless the caller asks for it. Returns {"NSE": {...}, "US":
    {...}} -- one measure_condition() call per market, never mixed."""
    return {
        market: measure_condition(
            datasets, condition_name=condition_name, condition_fn=condition_fn, horizons=horizons,
            period=period, market_filter=market, regime_filter=regime_filter,
        )
        for market in ("NSE", "US")
    }
