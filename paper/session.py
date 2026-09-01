"""Phase 7A — a controlled, bar-by-bar-drivable interface over
PaperTradingEngine. This is NOT a second trading engine and NOT a live feed:
PaperSession only sequences calls into the exact same
PaperTradingEngine.process_bar() / submit_signal() Phase 6 already proved
correct, one bar at a time, instead of replay_historical()'s "hand me a
whole DataFrame and run start to finish" shape.

Why this exists: a real event-driven caller (or the MCP
submit_paper_market_bar_tool, used for controlled manual testing) needs a
"give me bars one at a time, in order, tell me what happened" interface.
replay_historical() already supports a start_index/end_index sub-range (used
by the restart test), which is functionally "start/resume" — PaperSession
just wraps that same capability in start()/process_next_bar()/stop()/
status() calls, and derives its own resume point from the persisted bar
cursor (paper/engine.py's bar_cursor table) instead of requiring the caller
to track and pass an index across a restart.

Both PaperSession and replay_historical share one per-bar step
(paper.replay._process_series_bar) so they can never silently diverge —
verified by tests/test_paper_session_parity.py (spec §18's mandatory test:
"the strongest test is old replay vs new bar-driven replay; results must be
identical").
"""

from dataclasses import dataclass

import pandas as pd

from paper.engine import BarOutcome, PaperTradingEngine
from paper.replay import _process_series_bar
from strategy.contracts import Strategy


@dataclass
class SessionStatus:
    symbol: str
    next_index: int
    total_bars: int
    finished: bool
    bars_processed_this_session: int
    signals_submitted_this_session: int


class PaperSession:
    """One symbol's bar-by-bar paper-trading session over a pre-fetched
    indicator series. `indicator_series` is the same fully-computed
    DataFrame replay_historical() takes — Phase 7A does not add a live/
    streaming indicator computation (see the final report's limitations
    section); this decomposes the existing batch replay into a
    resumable, one-bar-at-a-time-drivable object instead.
    """

    def __init__(self, engine: PaperTradingEngine, *, symbol: str, indicator_series: pd.DataFrame, strategy: Strategy):
        self.engine = engine
        self.symbol = symbol
        self.indicator_series = indicator_series
        self.strategy = strategy
        self._started = False
        self._bars_processed = 0
        self._signals_submitted = 0
        self._index = self._resume_index()

    def _resume_index(self) -> int:
        """Where to continue from: the first row strictly after the last
        bar timestamp persisted for this symbol, or 0 if this symbol has
        never been processed. Reuses process_bar's own bar_cursor — no
        separate "session state" table is needed (spec §5's restart example
        is exactly what this derives)."""
        last_ts = self.engine.store.get_last_bar_timestamp(self.symbol)
        if last_ts is None:
            return 0
        cursor = pd.Timestamp(last_ts)
        if cursor.tzinfo is not None:
            cursor = cursor.tz_localize(None)
        return int(self.indicator_series.index.searchsorted(cursor, side="right"))

    def start(self) -> "PaperSession":
        self._started = True
        return self

    def process_next_bar(self) -> BarOutcome | None:
        """Process exactly one bar and advance. Returns None once the
        session has exhausted its series (nothing left to process)."""
        if not self._started:
            raise RuntimeError("PaperSession.start() must be called before processing bars.")

        n = len(self.indicator_series)
        if self._index >= n:
            return None

        bar, outcome, submitted = _process_series_bar(
            self.engine, symbol=self.symbol, indicator_series=self.indicator_series,
            i=self._index, strategy=self.strategy, n=n,
        )
        self._bars_processed += 1
        if submitted:
            self._signals_submitted += 1

        self._index += 1
        if self._index == n:
            # True end of the whole series — mirrors replay_historical()'s
            # own close_at_end_of_data call when end_index == n. A session
            # merely paused mid-way (stop() before the series ends) must
            # NOT force-close — the position stays open for resume().
            self.engine.close_at_end_of_data(self.symbol, bar)

        return outcome

    def run_to_end(self) -> None:
        while self.process_next_bar() is not None:
            pass

    def process_bars(self, count: int) -> int:
        """Processes up to `count` bars (fewer if the series is exhausted
        first) and returns how many were actually processed. Unlike
        run_to_end(), this is for a session that's meant to be interrupted
        partway through — e.g. simulating "process the first N bars, then
        the process gets killed" for a restart test. Always construct
        PaperSession with the FULL known series, even when only processing
        a prefix of it with this method: close_at_end_of_data is only
        triggered by genuinely reaching the last row of that full series
        (see process_next_bar) — passing a pre-truncated series would make
        an ordinary mid-stream pause look like "no more data ever" and
        wrongly force-close an open position."""
        processed = 0
        for _ in range(count):
            if self.process_next_bar() is None:
                break
            processed += 1
        return processed

    def status(self) -> SessionStatus:
        n = len(self.indicator_series)
        return SessionStatus(
            symbol=self.symbol,
            next_index=self._index,
            total_bars=n,
            finished=self._index >= n,
            bars_processed_this_session=self._bars_processed,
            signals_submitted_this_session=self._signals_submitted,
        )

    def stop(self) -> None:
        """Marks the session as not-accepting-more-bars. Does NOT close the
        store (the caller opened it; PaperSession doesn't own its
        lifecycle) — call store.close() separately to simulate a real
        process termination, as the restart tests do."""
        self._started = False
