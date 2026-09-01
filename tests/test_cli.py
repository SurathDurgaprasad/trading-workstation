import pytest

from main import parse_args, run_paper_live_command
from tests.conftest import AAPL_CACHE_PATH


def test_bare_symbol_invocation_stays_backward_compatible_with_phase_2():
    # `python main.py --symbol AAPL` (no subcommand) was the entire Phase 1/2
    # interface — it must keep working exactly as before.
    args = parse_args(["--symbol", "AAPL"])
    assert args.command == "analyze"
    assert args.symbol == "AAPL"
    assert args.question is None


def test_explicit_analyze_subcommand():
    args = parse_args(["analyze", "--symbol", "AAPL", "--question", "custom question"])
    assert args.command == "analyze"
    assert args.symbol == "AAPL"
    assert args.question == "custom question"


def test_backtest_subcommand_defaults():
    args = parse_args(["backtest", "--symbol", "RELIANCE.NS"])
    assert args.command == "backtest"
    assert args.symbol == "RELIANCE.NS"
    assert args.period == "5y"
    assert args.interval == "1d"
    assert args.initial_capital == 100_000.0
    assert args.strategy == "trend_momentum_baseline"


def test_backtest_subcommand_overrides():
    args = parse_args(
        [
            "backtest",
            "--symbol",
            "AAPL",
            "--period",
            "2y",
            "--interval",
            "1wk",
            "--initial-capital",
            "50000",
            "--strategy",
            "trend_momentum_baseline",
        ]
    )
    assert args.period == "2y"
    assert args.interval == "1wk"
    assert args.initial_capital == 50_000.0


def test_paper_status_subcommand():
    args = parse_args(["paper", "status"])
    assert args.command == "paper"
    assert args.paper_command == "status"
    assert args.db is None


def test_paper_run_subcommand_defaults():
    args = parse_args(["paper", "run", "--symbol", "AAPL"])
    assert args.paper_command == "run"
    assert args.symbol == "AAPL"
    assert args.period == "5y"
    assert args.interval == "1d"
    assert args.strategy == "trend_momentum_baseline"


def test_paper_trades_and_journal_subcommands():
    assert parse_args(["paper", "trades"]).paper_command == "trades"
    assert parse_args(["paper", "journal"]).paper_command == "journal"


def test_paper_db_override():
    args = parse_args(["paper", "--db", "/tmp/custom.db", "status"])
    assert args.db == "/tmp/custom.db"


def test_live_sim_subcommand_defaults():
    args = parse_args(["live-sim", "--symbol", "RELIANCE.NS"])
    assert args.command == "live-sim"
    assert args.symbol == "RELIANCE.NS"
    assert args.interval == "1m"
    assert args.period == "5d"
    assert args.strategy == "trend_momentum_baseline"
    assert args.db is None
    assert args.max_bars is None
    assert args.freshness_multiplier == 2.0
    assert args.require_human_approval is False


def test_live_sim_subcommand_overrides():
    args = parse_args([
        "live-sim", "--symbol", "AAPL", "--interval", "5m", "--period", "1d",
        "--max-bars", "10", "--freshness-multiplier", "5.0", "--require-human-approval",
    ])
    assert args.interval == "5m"
    assert args.period == "1d"
    assert args.max_bars == 10
    assert args.freshness_multiplier == 5.0
    assert args.require_human_approval is True


def test_paper_live_subcommand_defaults():
    args = parse_args(["paper-live", "--symbol", "RELIANCE.NS"])
    assert args.command == "paper-live"
    assert args.symbol == "RELIANCE.NS"
    assert args.interval == "1m"
    assert args.period == "1d"
    assert args.strategy == "trend_momentum_baseline"
    assert args.db is None
    assert args.state_db is None
    assert args.max_bars is None
    assert args.freshness_multiplier == 2.0
    assert args.no_human_approval is False  # human approval required by default
    assert args.approval_timeout_seconds is None  # resolved to DEFAULT_APPROVAL_TIMEOUT_SECONDS at run time
    assert args.no_ai_explanation is False
    assert args.auto_approve is False
    assert args.auto_reject is False
    assert args.kill_switch is False
    assert args.reset_kill_switch is False


def test_paper_live_subcommand_overrides():
    args = parse_args([
        "paper-live", "--symbol", "AAPL", "--interval", "1d", "--period", "1y",
        "--no-human-approval", "--approval-timeout-seconds", "30", "--no-ai-explanation",
        "--auto-approve", "--freshness-multiplier", "10.0",
    ])
    assert args.interval == "1d"
    assert args.period == "1y"
    assert args.no_human_approval is True
    assert args.approval_timeout_seconds == 30.0
    assert args.no_ai_explanation is True
    assert args.auto_approve is True
    assert args.freshness_multiplier == 10.0


def test_dashboard_subcommand_defaults():
    args = parse_args(["dashboard"])
    assert args.command == "dashboard"
    assert args.host == "127.0.0.1"
    assert args.port == 8765


def test_dashboard_subcommand_overrides():
    args = parse_args(["dashboard", "--host", "0.0.0.0", "--port", "9000"])
    assert args.host == "0.0.0.0"
    assert args.port == 9000


def test_paper_live_kill_switch_flags_parse_without_a_symbol():
    args = parse_args(["paper-live", "--kill-switch", "--kill-switch-reason", "halting for the day"])
    assert args.kill_switch is True
    assert args.kill_switch_reason == "halting for the day"
    assert args.symbol is None

    args = parse_args(["paper-live", "--reset-kill-switch"])
    assert args.reset_kill_switch is True


# --- functional (executes run_paper_live_command against real cached data) ---

pytestmark_paper_live = pytest.mark.skipif(not AAPL_CACHE_PATH.exists(), reason=f"No cached AAPL data at {AAPL_CACHE_PATH}")


@pytestmark_paper_live
def test_run_paper_live_command_auto_approve_end_to_end(tmp_path, capsys):
    args = parse_args([
        "paper-live", "--symbol", "AAPL", "--interval", "1d", "--period", "1y",
        "--db", str(tmp_path / "paper.db"), "--state-db", str(tmp_path / "state.db"),
        "--max-bars", "70", "--auto-approve", "--no-ai-explanation", "--freshness-multiplier", "1000000",
    ])
    run_paper_live_command(args)
    output = capsys.readouterr().out
    assert "HUMAN-OPERATED PAPER TRADING WORKSTATION -- NOT LIVE TRADING" in output
    assert "SIGNAL DETECTED" in output
    assert "-> APPROVED" in output
    assert "This is still simulated trading. No real broker is connected. No real order can be placed." in output


@pytestmark_paper_live
def test_run_paper_live_command_kill_switch_activate_and_reset(tmp_path, capsys):
    state_db = tmp_path / "state.db"

    activate_args = parse_args(["paper-live", "--kill-switch", "--kill-switch-reason", "test halt", "--state-db", str(state_db)])
    run_paper_live_command(activate_args)
    assert "KILL SWITCH ACTIVATED" in capsys.readouterr().out

    blocked_args = parse_args([
        "paper-live", "--symbol", "AAPL", "--interval", "1d", "--period", "3mo",
        "--db", str(tmp_path / "paper.db"), "--state-db", str(state_db),
        "--max-bars", "3", "--auto-approve", "--no-ai-explanation", "--freshness-multiplier", "1000000",
    ])
    run_paper_live_command(blocked_args)
    assert "KILL SWITCH ACTIVE" in capsys.readouterr().out

    reset_args = parse_args(["paper-live", "--reset-kill-switch", "--state-db", str(state_db)])
    run_paper_live_command(reset_args)
    assert "KILL SWITCH RESET" in capsys.readouterr().out
