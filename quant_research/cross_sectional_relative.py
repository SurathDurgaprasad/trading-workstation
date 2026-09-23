"""EDGE DISCOVERY mission, Family C (cross-sectional/relative information):
H_XMOM_001/H_XVOL_001/H_XVOLATILITY_001 preregistrations
(strategy/hypothesis_registry.py) -- materially different mechanisms from
this project's own already-closed H_XSECT_* (bottom-quintile, short-
lookback LAGGARD REVERSAL) and F_CONTEXT (regime filters on the frozen
baseline) families: cross-sectional MOMENTUM continuation, and abnormal
volume/volatility RELATIVE TO SAME-DATE PEERS (never tested anywhere in
this registry as a standalone forward-looking signal).

Reuses, never recomputes:
  - quant_research.market_behavior.SymbolDataset/build_universe_datasets
    -- the same causal per-symbol frame every hypothesis in this
    project's history already relies on.
  - quant_research.cross_sectional.rank_cross_sectionally/
    shared_period_boundaries/attach_relative_score_column -- the same
    cross-sectional bucketing/ranking machinery H_XSECT_001-006 already
    validated, unmodified.

Deliberately outside strategy/, risk/, paper/, backtesting/, and never
imported by any of them, the MCP server, or main.py.
"""

import pandas as pd

from quant_research.market_behavior import SymbolDataset

REALIZED_VOL_LOOKBACK = 20
"""Trading days, std dev of daily returns -- a plain, standard realized-
volatility window, distinct from H_VOL_001's own ATR-based
atr_pct_of_price (a different volatility DEFINITION already used
elsewhere in this registry; kept separate here rather than reused, so
H_XVOLATILITY_001's own evidence is never confounded with H_VOL_001's)."""


def add_realized_volatility_column(dataset: SymbolDataset, lookback: int = REALIZED_VOL_LOOKBACK) -> None:
    """Mutates dataset.frame in place, adding realized_vol_{lookback} =
    rolling std dev of daily close-to-close returns -- strictly causal
    (a row's value uses only that bar and the `lookback` preceding it)."""
    daily_returns = dataset.frame["close"].pct_change()
    dataset.frame[f"realized_vol_{lookback}"] = daily_returns.rolling(window=lookback, min_periods=lookback).std()


def attach_cross_sectional_zscore_column(
    datasets: dict[str, SymbolDataset],
    *,
    raw_column: str,
    output_column: str,
    min_symbols_per_date: int = 10,
) -> None:
    """Mutates every dataset's frame in place, adding `output_column` =
    (raw_column value - that SAME DATE's cross-sectional mean across all
    symbols) / that SAME DATE's cross-sectional stdev -- generalizes
    quant_research.cross_sectional.attach_bucket_membership_column's own
    per-date, whole-universe pass (same date-by-date iteration structure)
    to a continuous z-score instead of a discrete bucket label, needed
    here because H_XVOL_001/H_XVOLATILITY_001 rank on the z-score itself
    via rank_cross_sectionally (which accepts any continuous
    score_column), not a pre-bucketed label.

    A date with fewer than `min_symbols_per_date` valid readings is
    skipped entirely (output_column left NaN for every symbol on that
    date) -- same safeguard as attach_bucket_membership_column, never a
    degenerate z-score from a handful of symbols."""
    all_dates: set[pd.Timestamp] = set()
    for dataset in datasets.values():
        all_dates.update(dataset.frame.index)

    assignments: dict[str, dict[pd.Timestamp, float]] = {symbol: {} for symbol in datasets}

    for date in sorted(all_dates):
        values: dict[str, float] = {}
        for symbol, dataset in datasets.items():
            if date not in dataset.frame.index:
                continue
            value = dataset.frame.loc[date, raw_column]
            if pd.notna(value):
                values[symbol] = float(value)

        if len(values) < min_symbols_per_date:
            continue

        series = pd.Series(values)
        mean = series.mean()
        stdev = series.std(ddof=1)
        if not stdev or pd.isna(stdev):
            continue

        for symbol, value in values.items():
            assignments[symbol][date] = (value - mean) / stdev

    for symbol, dataset in datasets.items():
        dataset.frame[output_column] = dataset.frame.index.map(assignments[symbol])
