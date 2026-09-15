"""Real-time strategy validation mission, multi-symbol hardening pass --
tests for live/fleet_summary.py: Item 4's consolidated session report.
"""
from live.fleet_summary import (
    FleetSessionSummary,
    SymbolSessionSummary,
    format_fleet_summary_table,
    parse_session_log_counts,
    summarize_fleet_session,
    summarize_symbol_session,
)
from live.runtime_layout import ensure_symbol_runtime_dirs, symbol_runtime_paths


# --- parse_session_log_counts --------------------------------------------------


def test_parse_session_log_counts_counts_bars_fresh_stale_and_gaps(tmp_path):
    log_path = tmp_path / "session.log"
    log_path.write_text(
        "[AAPL] bar#   1 2026-09-16T09:15:00  close=1.00  NO_SIGNAL  fresh=True\n"
        "[AAPL] bar#   2 2026-09-16T09:16:00  close=1.01  NO_SIGNAL  fresh=False\n"
        "\n[AAPL] [GAP DETECTED] connected, no new bar for 900s (expected within ~180s) -- feed may be delayed, not necessarily disconnected.\n"
        "[AAPL] bar#   3 2026-09-16T09:31:00  close=1.02  NO_SIGNAL  fresh=True\n"
        "\n[AAPL] bar#   4 2026-09-16T09:32:00  KILL SWITCH ACTIVE -- signal suppressed, no order created.\n",
        encoding="utf-8",
    )
    counts = parse_session_log_counts(log_path)
    assert counts == {"bars_processed": 4, "fresh_bars": 2, "stale_bars": 1, "gap_events": 1}


def test_parse_session_log_counts_a_pending_approval_bar_counts_as_processed_and_fresh(tmp_path):
    """The one branch (PENDING_HUMAN_APPROVAL) that never prints "bar#"
    -- must still be counted as a processed (and fresh) bar via its own
    "SIGNAL DETECTED" line, or a session with any pending-approval
    signal silently undercounts total bars processed. This is a real
    bug this test caught: bars_processed was 66 instead of 70 for a
    real 70-bar session with 4 pending-approval signals, before
    "SIGNAL DETECTED" was added as a second bar marker."""
    log_path = tmp_path / "session.log"
    log_path.write_text(
        "[AAPL] bar#   1 2026-09-16T09:15:00  close=1.00  NO_SIGNAL  fresh=True\n"
        "\nSIGNAL DETECTED\n"
        "  Signal ID: abc123\n"
        "[AAPL] bar#   3 2026-09-16T09:17:00  close=1.02  NO_SIGNAL  fresh=True\n",
        encoding="utf-8",
    )
    counts = parse_session_log_counts(log_path)
    assert counts["bars_processed"] == 3
    assert counts["fresh_bars"] == 3
    assert counts["stale_bars"] == 0


def test_parse_session_log_counts_missing_file_returns_zeros(tmp_path):
    counts = parse_session_log_counts(tmp_path / "does_not_exist.log")
    assert counts == {"bars_processed": 0, "fresh_bars": 0, "stale_bars": 0, "gap_events": 0}


def test_parse_session_log_counts_empty_file_returns_zeros(tmp_path):
    log_path = tmp_path / "session.log"
    log_path.write_text("", encoding="utf-8")
    counts = parse_session_log_counts(log_path)
    assert counts == {"bars_processed": 0, "fresh_bars": 0, "stale_bars": 0, "gap_events": 0}


# --- summarize_symbol_session -- never-launched symbol -------------------------


def test_summarize_symbol_session_for_a_never_launched_symbol_is_all_zero_not_an_error(tmp_path):
    summary = summarize_symbol_session(tmp_path, "RELIANCE.NS")
    assert summary.symbol == "RELIANCE.NS"
    assert summary.bars_processed == 0
    assert summary.signals == 0
    assert summary.trades == 0
    assert summary.net_pnl == 0.0
    assert summary.log_found is False
    assert summary.db_found is False


def test_summarize_symbol_session_finds_a_log_with_no_dbs_yet(tmp_path):
    """A worker that was launched and printed at least one bar but whose
    stores haven't been touched yet (e.g. --record-predictions was
    off) -- log_found True, db_found False, no crash reading a
    nonexistent paper.db/predictions.db."""
    paths = symbol_runtime_paths(tmp_path, "RELIANCE.NS")
    ensure_symbol_runtime_dirs(paths)
    (paths.logs_dir / "session.log").write_text(
        "[RELIANCE.NS] bar#   1 2026-09-16T09:15:00  close=1234.50  NO_SIGNAL  fresh=True\n", encoding="utf-8",
    )
    summary = summarize_symbol_session(tmp_path, "RELIANCE.NS")
    assert summary.bars_processed == 1
    assert summary.log_found is True
    assert summary.db_found is False
    assert summary.signals == 0
    assert summary.trades == 0


# --- summarize_symbol_session / summarize_fleet_session -- real CLI session ----


def test_summarize_symbol_session_reads_a_real_runtime_dir_session(tmp_path):
    """Runs a REAL `paper-live --runtime-dir` session (mock source, real
    cached AAPL data, --record-predictions on) via the actual CLI
    entrypoint -- not a hand-built store fixture, since Trade/Position's
    exact required fields are the pipeline's own concern, not this
    report's. Then proves summarize_symbol_session reads that SAME
    runtime dir back correctly."""
    from main import parse_args, run_paper_live_command

    args = parse_args([
        "paper-live", "--symbol", "AAPL", "--interval", "1d", "--period", "1y",
        "--runtime-dir", str(tmp_path), "--max-bars", "70", "--auto-approve", "--no-ai-explanation",
        "--freshness-multiplier", "1000000", "--record-predictions", "--evaluate-every-n-bars", "0",
    ])
    run_paper_live_command(args)

    summary = summarize_symbol_session(tmp_path, "AAPL")
    assert summary.symbol == "AAPL"
    assert summary.bars_processed == 70
    assert summary.fresh_bars + summary.stale_bars == summary.bars_processed
    assert summary.log_found is True
    assert summary.db_found is True
    assert summary.signals >= 0
    assert summary.trades >= 0
    assert isinstance(summary.net_pnl, float)


def test_summarize_fleet_session_aggregates_a_never_launched_and_a_real_symbol(tmp_path):
    from main import parse_args, run_paper_live_command

    args = parse_args([
        "paper-live", "--symbol", "AAPL", "--interval", "1d", "--period", "1y",
        "--runtime-dir", str(tmp_path), "--max-bars", "70", "--auto-approve", "--no-ai-explanation",
        "--freshness-multiplier", "1000000", "--record-predictions", "--evaluate-every-n-bars", "0",
    ])
    run_paper_live_command(args)

    fleet = summarize_fleet_session(tmp_path, ["AAPL", "RELIANCE.NS"])
    assert len(fleet.per_symbol) == 2
    assert fleet.total_bars == 70  # RELIANCE.NS never ran -- contributes 0
    by_symbol = {s.symbol: s for s in fleet.per_symbol}
    assert by_symbol["RELIANCE.NS"].bars_processed == 0
    assert by_symbol["AAPL"].bars_processed == 70


# --- format_fleet_summary_table -------------------------------------------------


def _summary(symbol, *, bars=0, fresh=0, signals=0, trades=0, net_pnl=0.0, log_found=True, db_found=True):
    return SymbolSessionSummary(
        symbol=symbol, bars_processed=bars, fresh_bars=fresh, stale_bars=bars - fresh, gap_events=0,
        signals=signals, trades=trades, net_pnl=net_pnl, log_found=log_found, db_found=db_found,
    )


def test_format_fleet_summary_table_includes_every_symbol_and_a_correctly_summed_total_row():
    fleet = FleetSessionSummary(per_symbol=[
        _summary("RELIANCE.NS", bars=120, fresh=118, signals=2, trades=1, net_pnl=-45.50),
        _summary("TCS.NS", bars=118, fresh=118, signals=0, trades=0, net_pnl=0.0),
    ])
    table = format_fleet_summary_table(fleet)
    assert "RELIANCE.NS" in table
    assert "TCS.NS" in table
    assert "TOTAL" in table
    total_line = [line for line in table.splitlines() if line.startswith("TOTAL")][0]
    assert "238" in total_line  # 120 + 118 bars
    assert "-45.50" in total_line


def test_format_fleet_summary_table_flags_a_missing_worker():
    fleet = FleetSessionSummary(per_symbol=[_summary("RELIANCE.NS", log_found=False, db_found=False)])
    table = format_fleet_summary_table(fleet)
    assert "[missing log/db]" in table


def test_format_fleet_summary_table_total_row_on_empty_fleet_is_all_zero():
    table = format_fleet_summary_table(FleetSessionSummary(per_symbol=[]))
    total_line = [line for line in table.splitlines() if line.startswith("TOTAL")][0]
    assert "0" in total_line
