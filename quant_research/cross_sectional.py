"""EDGE DISCOVERY mission: cross-sectional ranking -- the genuinely
missing piece this project's own H_RELSTRENGTH_001 already flagged
(quant_research/relative_strength_signal.py's own module docstring):
"A true cross-sectional ranking/selection backtest needs a portfolio-
level engine that rebalances across the whole universe on a shared
calendar... building one was judged out of proportion to test ONE
hypothesis first... if it shows promise, the cross-sectional engine
becomes a justified follow-up, not a speculative one."

This is that follow-up, built as narrowly as the question requires:
NOT a portfolio/rebalancing engine (no position sizing, no capital
allocation, no simulated fills) -- a pure MEASUREMENT tool, exactly
matching quant_research/market_behavior.py's own posture ("no
signal is generated here, no trade is simulated; this is pure
measurement"). On each shared calendar date, rank every symbol with a
valid score that day, bucket into quantiles, and measure each
bucket's pooled forward return -- reusing SymbolDataset's own
fwd_return_h columns unchanged.

Reuses, never recomputes:
  - quant_research.market_behavior.build_universe_datasets/SymbolDataset
    -- the same causal per-symbol frame (indicators + alpha features +
    forward-return labels + regime columns) every other hypothesis in
    this project's history already relies on.
  - backtesting.splits.split_periods -- the SAME 60/20/20 dev/val/oos
    convention, applied ONCE to the shared universe calendar (not
    per-symbol independently, since cross-sectional ranking is
    meaningless without a shared reference date).
"""

from dataclasses import dataclass, field

import pandas as pd

from quant_research.market_behavior import ForwardReturnSummary, SymbolDataset, summarize_forward_returns

DEFAULT_LOOKBACKS = (5, 20, 60)
"""Bars, matching the mission's own explicit example matrix."""


def add_lookback_return_columns(dataset: SymbolDataset, lookbacks: tuple[int, ...] = DEFAULT_LOOKBACKS) -> None:
    """Mutates dataset.frame in place, adding trailing_return_{N} for
    each lookback -- close.pct_change(N), causal (uses only the
    preceding N bars, never a future one). Distinct from
    quant_research.alpha_features.add_alpha_features's own
    trailing_return_20 (hardcoded to 20 bars, benchmark-relative
    variant computed separately there) -- this adds the RAW,
    absolute-return version for an arbitrary set of lookbacks, the
    building block cross-sectional ranking needs."""
    for lookback in lookbacks:
        dataset.frame[f"trailing_return_{lookback}"] = dataset.frame["close"].pct_change(lookback)


def shared_period_boundaries(datasets: dict[str, SymbolDataset]) -> tuple[pd.Timestamp, pd.Timestamp]:
    """One (development_end, validation_end) pair for the WHOLE universe,
    not per-symbol -- cross-sectional ranking compares symbols to each
    other on the same date, so the dev/val/oos split must be a property
    of the shared calendar, not of any one symbol. In practice every
    symbol in this project's NSE universe shares within 1-2 bars of the
    same 10-year span (confirmed via cache-status), so any one symbol's
    own boundaries are representative -- this takes the FIRST dataset's
    own boundaries rather than silently assuming, so a caller can see
    immediately if that assumption ever stops holding (a large mismatch
    would show up as a visibly wrong sample-size split downstream)."""
    first = next(iter(datasets.values()))
    if first.development_end is None or first.validation_end is None:
        raise ValueError("shared_period_boundaries: the reference dataset has no development/validation split (too little history).")
    return first.development_end, first.validation_end


def _period_for_date(date: pd.Timestamp, development_end: pd.Timestamp, validation_end: pd.Timestamp) -> str:
    if date <= development_end:
        return "development"
    if date <= validation_end:
        return "validation"
    return "out_of_sample"


@dataclass(frozen=True)
class QuantileBucketResult:
    """Forward-return summaries for one quantile bucket, one horizon,
    one period -- mirrors ForwardReturnSummary's own shape/fields so
    downstream reporting code needs no new formatting logic."""

    bucket: str
    """e.g. 'Q1_TOP' / 'Q5_BOTTOM' / 'Q2' .. -- caller-defined labels,
    never fabricated as 'quintile N' when the caller asked for
    terciles or another split count."""
    summary: ForwardReturnSummary


def rank_cross_sectionally(
    datasets: dict[str, SymbolDataset],
    *,
    score_column: str,
    horizons: tuple[int, ...],
    n_buckets: int = 5,
    period: str = "full",
    min_symbols_per_date: int = 10,
) -> dict[str, dict[int, ForwardReturnSummary]]:
    """For every date where at least `min_symbols_per_date` symbols have
    a non-NaN `score_column` value, rank them cross-sectionally (highest
    score = bucket 1) and assign each to one of `n_buckets` equal-sized
    quantile buckets. Pools each bucket's `fwd_return_{h}` values across
    ALL dates and ALL symbols, filtered to `period` (development/
    validation/out_of_sample/full) using shared_period_boundaries.

    `min_symbols_per_date` guards against a date where only a handful of
    symbols have a valid score (e.g. very early in a 60-bar lookback's
    own warm-up) producing a degenerate, meaningless "quantile" -- such
    dates are skipped entirely, never padded or guessed.

    Returns {bucket_label: {horizon: ForwardReturnSummary}}, bucket
    labels "Q1" (highest score) .. "Q{n_buckets}" (lowest score) --
    caller interprets Q1 as "leaders"/"top decile"/etc. per context.
    """
    development_end, validation_end = shared_period_boundaries(datasets)

    all_dates: set[pd.Timestamp] = set()
    for dataset in datasets.values():
        all_dates.update(dataset.frame.index)

    pooled: dict[str, dict[int, list[float]]] = {f"Q{i+1}": {h: [] for h in horizons} for i in range(n_buckets)}

    for date in sorted(all_dates):
        row_period = _period_for_date(date, development_end, validation_end)
        if period != "full" and row_period != period:
            continue

        scores: dict[str, float] = {}
        for symbol, dataset in datasets.items():
            if date not in dataset.frame.index:
                continue
            value = dataset.frame.loc[date, score_column]
            if pd.notna(value):
                scores[symbol] = float(value)

        if len(scores) < min_symbols_per_date:
            continue

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        bucket_size = len(ranked) / n_buckets

        for rank, (symbol, _score) in enumerate(ranked):
            bucket_index = min(int(rank / bucket_size), n_buckets - 1)
            bucket_label = f"Q{bucket_index + 1}"
            row = datasets[symbol].frame.loc[date]
            for h in horizons:
                col = f"fwd_return_{h}"
                if col in row.index and pd.notna(row[col]):
                    pooled[bucket_label][h].append(float(row[col]))

    return {
        bucket_label: {
            h: summarize_forward_returns(pooled[bucket_label][h], condition=f"cross_sectional_{score_column}_{bucket_label}", market="NSE", horizon_bars=h)
            for h in horizons
        }
        for bucket_label in pooled
    }
