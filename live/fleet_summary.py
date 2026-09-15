"""Real-time strategy validation mission, multi-symbol hardening pass --
Item 4: end-of-session consolidated fleet report (Symbol | Bars | Fresh |
Signals | Trades | P&L, plus a TOTAL row), read read-only from each
symbol's own isolated runtime-dir stores (live/runtime_layout.py).

Bars/fresh/stale/gap-event counts are NOT persisted anywhere in
paper.db or predictions.db -- main.py's own _run_paper_live_loop only
ever prints them (see the per-bar `line` in the default branch and the
gap_monitor wiring), it never writes a bar counter to any store. This
module's log-parsing is therefore the only source for those counts, and
deliberately reuses the SAME literal markers live/fleet_supervisor.py's
health check already reads ("bar#", "fresh=True"/"fresh=False",
"[GAP DETECTED]") rather than inventing a second, independently-
drifting way to recognize them.

Never launches a process, never writes to any trading store -- purely
an after-the-fact (or mid-session) READ of what the workers have
already, independently persisted.
"""

from dataclasses import dataclass
from pathlib import Path

from live.runtime_layout import symbol_runtime_paths


@dataclass(frozen=True)
class SymbolSessionSummary:
    symbol: str
    bars_processed: int
    fresh_bars: int
    stale_bars: int
    gap_events: int
    signals: int
    trades: int
    net_pnl: float
    log_found: bool
    db_found: bool


def parse_session_log_counts(log_path: Path) -> dict:
    """Pure-ish (the only I/O is reading log_path). A missing log file
    (worker never launched, or --runtime-dir points somewhere nothing
    has run yet) returns all-zero counts rather than raising -- this is
    a reporting tool, not a startup guard; live/runtime_layout.py's own
    verify_no_cross_symbol_contamination is the place that refuses to
    start against bad state.

    A processed bar is recognized by EITHER "bar#" (the KILL_SWITCH_
    ACTIVE/CRITIC_REJECTED/default per-bar line) OR "SIGNAL DETECTED"
    (_print_signal_block, the one branch -- PENDING_HUMAN_APPROVAL --
    that never prints "bar#"; same two-marker convention
    live/fleet_supervisor.py's health check already uses, found the
    same way: a real --record-predictions session undercounted bars by
    exactly the number of pending-approval signals until this was
    fixed). A signal-detected bar is always counted as fresh -- a stale
    bar reaches the STALE_SIGNAL_SUPPRESSED outcome instead (handled by
    the default "bar#" branch, fresh=False), never PENDING_HUMAN_
    APPROVAL, so a signal could only have been detected on a fresh
    bar."""
    counts = {"bars_processed": 0, "fresh_bars": 0, "stale_bars": 0, "gap_events": 0}
    if not log_path.exists():
        return counts
    with open(log_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if "bar#" in line:
                counts["bars_processed"] += 1
                if "fresh=True" in line:
                    counts["fresh_bars"] += 1
                elif "fresh=False" in line:
                    counts["stale_bars"] += 1
            elif "SIGNAL DETECTED" in line:
                counts["bars_processed"] += 1
                counts["fresh_bars"] += 1
            if "[GAP DETECTED]" in line:
                counts["gap_events"] += 1
    return counts


def summarize_symbol_session(runtime_dir: str | Path, symbol: str) -> SymbolSessionSummary:
    """Reads ONE symbol's isolated runtime-dir stores read-only: its
    session.log for bar/freshness/gap counts, its predictions.db for a
    signal count (every signal generated -- PENDING_HUMAN_APPROVAL,
    CRITIC_REJECTED, KILL_SWITCH_ACTIVE, or auto-approved -- becomes a
    PredictionRecord when --record-predictions is on; this is the
    project's own existing, already-generalized signal ledger, not a
    new count invented here), and its paper.db for realized trades and
    net P&L (paper.store.PaperStore.sum_realized_trade_pnl(), already
    used by the SAME reconciliation logic run_paper_live_command calls
    on every startup)."""
    paths = symbol_runtime_paths(runtime_dir, symbol)
    log_path = paths.logs_dir / "session.log"
    log_counts = parse_session_log_counts(log_path)

    signals = 0
    if paths.predictions_db.exists():
        from predictions.store import PredictionStore

        pred_store = PredictionStore(paths.predictions_db)
        try:
            signals = len(pred_store.list_predictions(limit=1_000_000))
        finally:
            pred_store.close()

    db_found = paths.paper_db.exists()
    trades = 0
    net_pnl = 0.0
    if db_found:
        from paper.store import PaperStore

        store = PaperStore(paths.paper_db)
        try:
            trades = len(store.list_trades())
            net_pnl = store.sum_realized_trade_pnl()
        finally:
            store.close()

    return SymbolSessionSummary(
        symbol=paths.symbol, bars_processed=log_counts["bars_processed"], fresh_bars=log_counts["fresh_bars"],
        stale_bars=log_counts["stale_bars"], gap_events=log_counts["gap_events"], signals=signals,
        trades=trades, net_pnl=net_pnl, log_found=log_path.exists(), db_found=db_found,
    )


@dataclass(frozen=True)
class FleetSessionSummary:
    per_symbol: list[SymbolSessionSummary]

    @property
    def total_bars(self) -> int:
        return sum(s.bars_processed for s in self.per_symbol)

    @property
    def total_fresh(self) -> int:
        return sum(s.fresh_bars for s in self.per_symbol)

    @property
    def total_signals(self) -> int:
        return sum(s.signals for s in self.per_symbol)

    @property
    def total_trades(self) -> int:
        return sum(s.trades for s in self.per_symbol)

    @property
    def total_net_pnl(self) -> float:
        return sum(s.net_pnl for s in self.per_symbol)


def summarize_fleet_session(runtime_dir: str | Path, symbols: list[str]) -> FleetSessionSummary:
    return FleetSessionSummary(per_symbol=[summarize_symbol_session(runtime_dir, symbol) for symbol in symbols])


def format_fleet_summary_table(summary: FleetSessionSummary) -> str:
    """Pure -- Symbol | Bars | Fresh | Signals | Trades | P&L, plus a
    TOTAL row, exactly as this mission's own Item 4 specifies. A symbol
    whose log or db was never found is still listed (0s across the
    board) rather than silently dropped -- a missing worker is
    information, not noise, in a fleet report."""
    header = f"{'SYMBOL':<14}{'BARS':>8}{'FRESH':>8}{'SIGNALS':>9}{'TRADES':>8}{'NET P&L':>14}"
    lines = [header, "-" * len(header)]
    for s in summary.per_symbol:
        flag = "" if (s.log_found and s.db_found) else "  [missing log/db]"
        lines.append(f"{s.symbol:<14}{s.bars_processed:>8}{s.fresh_bars:>8}{s.signals:>9}{s.trades:>8}{s.net_pnl:>14,.2f}{flag}")
    lines.append("-" * len(header))
    lines.append(
        f"{'TOTAL':<14}{summary.total_bars:>8}{summary.total_fresh:>8}"
        f"{summary.total_signals:>9}{summary.total_trades:>8}{summary.total_net_pnl:>14,.2f}"
    )
    return "\n".join(lines)
