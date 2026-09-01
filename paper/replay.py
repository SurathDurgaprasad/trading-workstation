"""Drives PaperTradingEngine over a pre-computed indicator series in the
exact chronological order backtesting.engine.run_backtest() uses: for bar i,
process the bar (fills a pending order at this bar's open, checks an open
position's stop/target against this bar's high/low) BEFORE checking whether
bar i itself produces a new signal (which becomes eligible to fill at bar
i+1). This is the historical-replay counterpart to a live feed calling
submit_signal()/process_bar() as events actually arrive — same engine, same
persistence, same idempotency; only the source of bars differs.

Phase 7A: the per-bar step below (_process_series_bar) is shared verbatim
between this module's all-at-once replay_historical() and
paper.session.PaperSession's one-bar-at-a-time process_next_bar() — so the
two drivers can never silently diverge. Proven by
tests/test_paper_session_parity.py (spec Phase 7A §18's mandatory test).
"""

from dataclasses import dataclass

import pandas as pd

from paper.engine import Bar, BarOutcome, PaperTradingEngine
from strategy.contracts import Strategy


@dataclass
class ReplaySummary:
    symbol: str
    bars_processed: int
    signals_submitted: int


def _process_series_bar(
    engine: PaperTradingEngine,
    *,
    symbol: str,
    indicator_series: pd.DataFrame,
    i: int,
    strategy: Strategy,
    n: int,
) -> tuple[Bar, BarOutcome, bool]:
    """One chronological step: process bar i (fill/exit), then — unless i is
    the very last bar of the WHOLE series (no next bar exists to fill a new
    signal on) — generate and submit a signal from bar i. Returns the Bar
    processed, the engine's BarOutcome, and whether a signal was submitted.

    A DUPLICATE_SKIPPED outcome still attempts signal generation/submission:
    submit_signal() is itself idempotent (Signal.stable_id()), so replaying
    the identical bar twice is always safe, not just for fills/exits.
    """
    row = indicator_series.iloc[i]
    timestamp = indicator_series.index[i]
    bar = Bar(
        timestamp=timestamp,
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]) if "volume" in row else 0.0,
    )

    outcome = engine.process_bar(symbol, bar)

    submitted = False
    if i + 1 < n:
        signal = strategy.generate_signal(indicator_series, i, symbol)
        if signal is not None:
            engine.submit_signal(signal, strategy_version=getattr(strategy, "version", "1.0"))
            submitted = True

    return bar, outcome, submitted


def replay_historical(
    engine: PaperTradingEngine,
    *,
    symbol: str,
    indicator_series: pd.DataFrame,
    strategy: Strategy,
    start_index: int = 0,
    end_index: int | None = None,
) -> ReplaySummary:
    """Replays indicator_series[start_index:end_index] (end_index exclusive,
    defaults to the full series). Passing a sub-range is what the restart
    test (spec §26) uses to simulate "run half, persist, resume the rest"
    without needing two separate DataFrames.
    """
    n = len(indicator_series)
    end_index = n if end_index is None else min(end_index, n)

    signals_submitted = 0
    last_bar: Bar | None = None

    for i in range(start_index, end_index):
        bar, _outcome, submitted = _process_series_bar(engine, symbol=symbol, indicator_series=indicator_series, i=i, strategy=strategy, n=n)
        last_bar = bar
        if submitted:
            signals_submitted += 1

    if end_index == n and last_bar is not None:
        engine.close_at_end_of_data(symbol, last_bar)

    return ReplaySummary(symbol=symbol, bars_processed=end_index - start_index, signals_submitted=signals_submitted)
