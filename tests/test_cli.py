import pytest

from main import (
    parse_args,
    run_backtest_universe_command,
    run_cache_status_command,
    run_decide_command,
    run_evaluate_command,
    run_fleet_summary_command,
    run_fleet_supervise_command,
    run_hypothesis_registry_command,
    run_learn_command,
    run_live_sim_command,
    run_paper_command,
    run_paper_live_command,
    run_predict_command,
    run_readiness_check_command,
    run_research_command,
    run_review_command,
    run_scan_command,
    run_size_command,
)
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


def test_backtest_universe_subcommand_defaults():
    args = parse_args(["backtest-universe", "--symbols", "AAPL,MSFT"])
    assert args.command == "backtest-universe"
    assert args.symbols == "AAPL,MSFT"
    assert args.watchlist_file is None
    assert args.period == "5y"
    assert args.interval == "1d"
    assert args.initial_capital == 100_000.0
    assert args.strategy == "trend_momentum_baseline"
    assert args.cost_model == "default"
    assert args.random_baseline_iterations == 0
    assert args.regime_analysis is False
    assert args.temporal_robustness is False
    assert args.compare_baselines is False
    assert args.promotion_gate is False
    assert args.promotion_gate_db is None
    assert args.walk_forward_folds == 0
    assert args.execution_robustness_iterations == 0
    assert args.multiple_testing_correction is False


def test_backtest_universe_subcommand_accepts_multiple_testing_correction_flag():
    args = parse_args(["backtest-universe", "--symbols", "AAPL", "--multiple-testing-correction"])
    assert args.multiple_testing_correction is True


def test_backtest_universe_subcommand_accepts_execution_robustness_iterations():
    args = parse_args(["backtest-universe", "--symbols", "AAPL", "--execution-robustness-iterations", "50"])
    assert args.execution_robustness_iterations == 50


def test_backtest_universe_subcommand_accepts_promotion_gate_flag():
    args = parse_args(["backtest-universe", "--symbols", "AAPL", "--promotion-gate"])
    assert args.promotion_gate is True


def test_backtest_universe_subcommand_accepts_promotion_gate_db_override():
    args = parse_args(["backtest-universe", "--symbols", "AAPL", "--promotion-gate-db", "custom.db"])
    assert args.promotion_gate_db == "custom.db"


def test_backtest_universe_subcommand_accepts_walk_forward_folds():
    args = parse_args(["backtest-universe", "--symbols", "AAPL", "--walk-forward-folds", "6"])
    assert args.walk_forward_folds == 6


def test_backtest_universe_subcommand_accepts_compare_baselines_flag():
    args = parse_args(["backtest-universe", "--symbols", "AAPL", "--compare-baselines"])
    assert args.compare_baselines is True


def test_backtest_universe_subcommand_accepts_regime_analysis_flag():
    args = parse_args(["backtest-universe", "--symbols", "AAPL", "--regime-analysis"])
    assert args.regime_analysis is True


def test_backtest_universe_subcommand_accepts_temporal_robustness_flag():
    args = parse_args(["backtest-universe", "--symbols", "AAPL", "--temporal-robustness"])
    assert args.temporal_robustness is True


def test_backtest_universe_subcommand_accepts_random_baseline_iterations():
    args = parse_args(["backtest-universe", "--symbols", "AAPL", "--random-baseline-iterations", "50"])
    assert args.random_baseline_iterations == 50


def test_backtest_universe_subcommand_accepts_nse_cost_model():
    args = parse_args(["backtest-universe", "--symbols", "RELIANCE.NS", "--cost-model", "india_nse_intraday_2026"])
    assert args.cost_model == "india_nse_intraday_2026"


def test_backtest_universe_subcommand_rejects_an_unknown_cost_model():
    with pytest.raises(SystemExit):
        parse_args(["backtest-universe", "--symbols", "AAPL", "--cost-model", "made_up"])


def test_backtest_universe_subcommand_accepts_watchlist_file():
    args = parse_args(["backtest-universe", "--watchlist-file", "watchlist.yaml"])
    assert args.watchlist_file == "watchlist.yaml"
    assert args.symbols is None


def test_backtest_universe_command_requires_symbols_or_watchlist_file():
    args = parse_args(["backtest-universe"])
    with pytest.raises(SystemExit):
        run_backtest_universe_command(args)


def test_cache_status_subcommand_defaults():
    args = parse_args(["cache-status"])
    assert args.command == "cache-status"
    assert args.symbols is None
    assert args.interval == "1d"
    assert args.stale_after_days == 30.0


def test_cache_status_subcommand_accepts_symbols_and_overrides():
    args = parse_args(["cache-status", "--symbols", "AAPL,RELIANCE.NS", "--interval", "1h", "--stale-after-days", "7"])
    assert args.symbols == "AAPL,RELIANCE.NS"
    assert args.interval == "1h"
    assert args.stale_after_days == 7.0


def test_cache_status_command_reports_a_real_cached_symbols_age(capsys):
    args = parse_args(["cache-status", "--symbols", "AAPL"])
    run_cache_status_command(args)
    captured = capsys.readouterr()
    assert "AAPL" in captured.out
    assert "CACHE STALENESS" in captured.out


def test_cache_status_command_reports_never_cached_for_an_unknown_symbol(capsys):
    args = parse_args(["cache-status", "--symbols", "TOTALLY_MADE_UP_SYMBOL"])
    run_cache_status_command(args)
    captured = capsys.readouterr()
    assert "never cached" in captured.out


def test_readiness_check_subcommand_defaults():
    args = parse_args(["readiness-check"])
    assert args.command == "readiness-check"
    assert args.symbols is None


def test_readiness_check_command_fails_when_credentials_are_missing(monkeypatch, capsys):
    monkeypatch.delenv("DHAN_CLIENT_ID", raising=False)
    monkeypatch.delenv("DHAN_ACCESS_TOKEN", raising=False)
    args = parse_args(["readiness-check"])

    with pytest.raises(SystemExit) as exc_info:
        run_readiness_check_command(args)

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "[FAIL]" in captured.out


def test_readiness_check_command_passes_credentials_check_when_configured(monkeypatch, capsys, tmp_path):
    import live.workstation as workstation_module

    monkeypatch.setenv("DHAN_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "fake-access-token")
    monkeypatch.setattr(workstation_module, "LIVE_STATE_DB_PATH", tmp_path / "live_state.db")
    args = parse_args(["readiness-check"])

    run_readiness_check_command(args)  # must not raise/exit

    captured = capsys.readouterr()
    assert "[PASS] Dhan credentials" in captured.out
    assert "[PASS] Kill switch is INACTIVE." in captured.out
    assert "[PASS] No unresolved pending approvals" in captured.out


def test_readiness_check_command_warns_on_an_active_kill_switch(monkeypatch, capsys, tmp_path):
    import live.workstation as workstation_module

    monkeypatch.setenv("DHAN_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "fake-access-token")
    monkeypatch.setattr(workstation_module, "LIVE_STATE_DB_PATH", tmp_path / "live_state.db")
    state_store = workstation_module.new_live_state_store()
    state_store.activate_kill_switch(reason="left on from last session")
    state_store.close()

    args = parse_args(["readiness-check"])
    run_readiness_check_command(args)  # must not raise -- an active kill switch is a WARN, not a FAIL

    captured = capsys.readouterr()
    assert "[WARN] Kill switch is currently ACTIVE" in captured.out
    assert "left on from last session" in captured.out


# --- readiness-check: LIVE SYSTEM HARDENING mission additions ---------------


def test_readiness_check_reports_disk_write_db_reachability_and_strategy_version(monkeypatch, capsys, tmp_path):
    import main as main_module

    monkeypatch.setenv("DHAN_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "fake-access-token")
    monkeypatch.setattr(main_module, "DEFAULT_LIVE_SIM_DB_PATH", tmp_path / "live_sim.db")
    monkeypatch.setattr(main_module, "DEFAULT_SCHEDULER_DB_PATH", tmp_path / "scheduler_runs.db")
    import live.workstation as workstation_module

    monkeypatch.setattr(workstation_module, "LIVE_STATE_DB_PATH", tmp_path / "live_state.db")
    args = parse_args(["readiness-check"])

    run_readiness_check_command(args)

    captured = capsys.readouterr()
    assert "[PASS] Disk write capability confirmed" in captured.out
    assert f"[PASS] Database reachable: {tmp_path / 'live_sim.db'}" in captured.out
    assert "Active strategy: trend_momentum_baseline" in captured.out
    assert "SCIENTIFIC VERDICT: NO DEMONSTRATED EDGE" in captured.out
    assert "[INFO] No scheduler run history found yet" in captured.out


def test_readiness_check_deep_flag_reports_missing_credentials_gracefully(monkeypatch, capsys, tmp_path):
    # --deep must never crash the whole command even if it can't run --
    # a clean [FAIL] line, not a traceback.
    import main as main_module

    monkeypatch.delenv("DHAN_CLIENT_ID", raising=False)
    monkeypatch.delenv("DHAN_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(main_module, "DEFAULT_LIVE_SIM_DB_PATH", tmp_path / "live_sim.db")
    monkeypatch.setattr(main_module, "DEFAULT_SCHEDULER_DB_PATH", tmp_path / "scheduler_runs.db")
    import live.workstation as workstation_module

    monkeypatch.setattr(workstation_module, "LIVE_STATE_DB_PATH", tmp_path / "live_state.db")
    args = parse_args(["readiness-check", "--deep"])

    with pytest.raises(SystemExit):  # top-level credentials FAIL still exits 1, same as without --deep
        run_readiness_check_command(args)

    captured = capsys.readouterr()
    assert "DEEP CHECK (--deep)" in captured.out
    assert "[FAIL] Cannot run deep checks:" in captured.out


def test_readiness_check_without_deep_flag_never_attempts_network_calls(monkeypatch, capsys, tmp_path):
    # The default (no --deep) behavior must stay exactly what it always
    # was: structural only, zero network calls, zero risk of hanging on
    # a slow/unavailable connection.
    import main as main_module

    monkeypatch.setenv("DHAN_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "fake-access-token")
    monkeypatch.setattr(main_module, "DEFAULT_LIVE_SIM_DB_PATH", tmp_path / "live_sim.db")
    monkeypatch.setattr(main_module, "DEFAULT_SCHEDULER_DB_PATH", tmp_path / "scheduler_runs.db")
    monkeypatch.setattr(main_module, "_run_deep_readiness_checks", lambda **_: pytest.fail("must not be called without --deep"))
    import live.workstation as workstation_module

    monkeypatch.setattr(workstation_module, "LIVE_STATE_DB_PATH", tmp_path / "live_state.db")
    args = parse_args(["readiness-check"])

    run_readiness_check_command(args)  # must not raise via the monkeypatched fail()

    captured = capsys.readouterr()
    assert "This is a STRUCTURAL check only." in captured.out


# --- readiness-check: holiday-calendar cross-check (live-market-readiness audit) ---


def test_readiness_check_with_no_holiday_config_discloses_the_gap_honestly(monkeypatch, capsys, tmp_path):
    import live.workstation as workstation_module
    import main as main_module

    monkeypatch.setenv("DHAN_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "fake-access-token")
    monkeypatch.setattr(workstation_module, "LIVE_STATE_DB_PATH", tmp_path / "live_state.db")
    monkeypatch.setattr(main_module, "DEFAULT_SCHEDULE_CONFIG_PATH", tmp_path / "does_not_exist.yaml")
    args = parse_args(["readiness-check"])

    run_readiness_check_command(args)

    captured = capsys.readouterr()
    assert "No holiday calendar was supplied" in captured.out


def test_readiness_check_cross_checks_an_explicit_schedule_config(monkeypatch, capsys, tmp_path):
    import live.workstation as workstation_module

    monkeypatch.setenv("DHAN_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "fake-access-token")
    monkeypatch.setattr(workstation_module, "LIVE_STATE_DB_PATH", tmp_path / "live_state.db")
    config_path = tmp_path / "schedule.yaml"
    config_path.write_text("holidays:\n  - \"2026-01-26\"\n")
    args = parse_args(["readiness-check", "--schedule-config", str(config_path)])

    run_readiness_check_command(args)

    captured = capsys.readouterr()
    assert "cross-checked against 1 configured holiday date(s)" in captured.out


def test_readiness_check_uses_the_default_schedule_config_path_when_present(monkeypatch, capsys, tmp_path):
    import live.workstation as workstation_module
    import main as main_module

    monkeypatch.setenv("DHAN_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "fake-access-token")
    monkeypatch.setattr(workstation_module, "LIVE_STATE_DB_PATH", tmp_path / "live_state.db")
    default_path = tmp_path / "config" / "schedule.yaml"
    default_path.parent.mkdir(parents=True)
    default_path.write_text("holidays: []\n")
    monkeypatch.setattr(main_module, "DEFAULT_SCHEDULE_CONFIG_PATH", default_path)
    args = parse_args(["readiness-check"])  # no --schedule-config passed -- must still find the default path

    run_readiness_check_command(args)

    captured = capsys.readouterr()
    assert "cross-checked against 0 configured holiday date(s)" in captured.out


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
    assert args.initial_capital == 100_000.0


def test_paper_initial_capital_override(tmp_path, capsys):
    """Phase 42+ mission: simulated starting capital must be configurable,
    never hardcoded -- proves it end-to-end, not just argparse plumbing:
    a fresh `paper status` with --initial-capital creates an account with
    exactly that capital, and the value is visible in the printed status."""
    args = parse_args(["paper", "--db", str(tmp_path / "paper.db"), "--initial-capital", "20000", "status"])
    assert args.initial_capital == 20_000.0

    run_paper_command(args)
    output = capsys.readouterr().out
    assert "Initial Capital:     20,000.00" in output
    assert "Equity:              20,000.00" in output
    assert "Cash:                20,000.00" in output

    from paper.store import PaperStore

    store = PaperStore(tmp_path / "paper.db")
    account = store.get_account()
    store.close()
    assert account.initial_capital == 20_000.0
    assert account.cash == 20_000.0


def test_paper_initial_capital_only_applies_on_first_creation(tmp_path, capsys):
    """A second `paper status` against the SAME db with a DIFFERENT
    --initial-capital must not reset the already-persisted account --
    restart-safe, matching every other store in this project."""
    db_path = str(tmp_path / "paper.db")
    run_paper_command(parse_args(["paper", "--db", db_path, "--initial-capital", "20000", "status"]))
    capsys.readouterr()

    run_paper_command(parse_args(["paper", "--db", db_path, "--initial-capital", "999999", "status"]))
    output = capsys.readouterr().out
    assert "Initial Capital:     20,000.00" in output  # unchanged, NOT 999,999


def _capture_engine_cost_model(monkeypatch):
    """Real-time strategy validation mission, Phase 8: monkeypatches
    paper.engine.PaperTradingEngine.__init__ to record the exact
    `cost_model` kwarg it was constructed with, then delegates to the
    real __init__ -- proves the CLI layer's --cost-model selection
    actually reaches the engine, not just that argparse parses the flag.
    """
    import paper.engine as paper_engine_module

    captured: dict = {}
    real_init = paper_engine_module.PaperTradingEngine.__init__

    def _capturing_init(self, *args, **kwargs):
        captured["cost_model"] = kwargs.get("cost_model")
        return real_init(self, *args, **kwargs)

    monkeypatch.setattr(paper_engine_module.PaperTradingEngine, "__init__", _capturing_init)
    return captured


def test_run_paper_command_defaults_to_the_generic_cost_model(tmp_path, monkeypatch):
    """FINAL_FAILURE_MODE_ANALYSIS.md entry #43: `paper` previously always
    constructed PaperTradingEngine with no cost_model at all, silently
    defaulting to CostModel()'s generic placeholder (zero STT/exchange
    charges for every NSE symbol). This proves the new --cost-model
    default ("default") is wired through as the SAME generic CostModel()
    -- byte-for-byte unchanged behavior for every existing caller."""
    from backtesting.costs import CostModel

    captured = _capture_engine_cost_model(monkeypatch)
    run_paper_command(parse_args(["paper", "--db", str(tmp_path / "paper.db"), "status"]))
    assert captured["cost_model"] == CostModel()


def test_run_paper_command_cost_model_flag_selects_the_india_preset(tmp_path, monkeypatch):
    from backtesting.costs import CostModel

    captured = _capture_engine_cost_model(monkeypatch)
    run_paper_command(parse_args(["paper", "--db", str(tmp_path / "paper.db"), "--cost-model", "india_nse_intraday_2026", "status"]))
    assert captured["cost_model"] == CostModel.india_nse_intraday_2026()


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
    assert args.initial_capital == 100_000.0


def test_live_sim_subcommand_overrides():
    args = parse_args([
        "live-sim", "--symbol", "AAPL", "--interval", "5m", "--period", "1d",
        "--max-bars", "10", "--freshness-multiplier", "5.0", "--require-human-approval",
        "--initial-capital", "20000",
    ])
    assert args.interval == "5m"
    assert args.period == "1d"
    assert args.max_bars == 10
    assert args.freshness_multiplier == 5.0
    assert args.require_human_approval is True
    assert args.initial_capital == 20_000.0


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
    assert args.source == "mock"  # real Dhan connection is opt-in, never the default
    assert args.refresh_instrument_map is False
    assert args.initial_capital == 100_000.0
    assert args.skip_critic is False  # the deterministic critic runs by default for --source dhan
    assert args.benchmark == "^NSEI"
    assert args.critic_refresh_seconds is None  # resolved to live.critic_gate.DEFAULT_REFRESH_SECONDS at run time


def test_paper_live_source_dhan_flag():
    args = parse_args(["paper-live", "--symbol", "RELIANCE.NS", "--source", "dhan", "--refresh-instrument-map"])
    assert args.source == "dhan"
    assert args.refresh_instrument_map is True


# --- _build_critic_gate_for_paper_live (LIVE SYSTEM HARDENING mission) -------


def test_critic_gate_is_none_for_source_mock_regardless_of_skip_critic():
    from main import _build_critic_gate_for_paper_live

    args = parse_args(["paper-live", "--symbol", "AAPL"])  # --source mock (default)
    assert _build_critic_gate_for_paper_live(args) is None


def test_critic_gate_is_none_when_skip_critic_is_passed():
    from main import _build_critic_gate_for_paper_live

    args = parse_args(["paper-live", "--symbol", "RELIANCE.NS", "--source", "dhan", "--skip-critic"])
    assert _build_critic_gate_for_paper_live(args) is None


def test_critic_gate_is_built_for_source_dhan_by_default():
    from live.critic_gate import CriticGate, DEFAULT_REFRESH_SECONDS
    from main import _build_critic_gate_for_paper_live

    args = parse_args(["paper-live", "--symbol", "RELIANCE.NS", "--source", "dhan"])
    gate = _build_critic_gate_for_paper_live(args)
    assert isinstance(gate, CriticGate)
    assert gate._symbol == "RELIANCE.NS"  # noqa: SLF001 -- read-only introspection for this test only
    assert gate._benchmark_symbol == "^NSEI"  # noqa: SLF001
    assert gate._refresh_seconds == DEFAULT_REFRESH_SECONDS  # noqa: SLF001


def test_critic_gate_respects_a_disabled_benchmark_and_custom_refresh():
    from main import _build_critic_gate_for_paper_live

    args = parse_args([
        "paper-live", "--symbol", "RELIANCE.NS", "--source", "dhan",
        "--benchmark", "", "--critic-refresh-seconds", "60",
    ])
    gate = _build_critic_gate_for_paper_live(args)
    assert gate._benchmark_symbol is None  # noqa: SLF001
    assert gate._refresh_seconds == 60.0  # noqa: SLF001


def test_critic_gate_provider_is_timeout_protected_not_a_bare_unbounded_fetch():
    """2026-09-21 CriticGate adversarial audit, real finding: this used to
    be CachedMarketDataProvider(get_market_data_provider()) with NO
    timeout -- an unbounded Yahoo hang on a cache miss (a new symbol, or
    a deleted/corrupted data/market/<SYMBOL>/1d.csv) would freeze this
    always-on live critic path indefinitely. Proves the provider
    CriticGate actually receives is timeout-protected (a
    ResilientMarketDataProvider under the cache), matching
    shadow-run/schedule's own --resilient pattern, but unconditional
    here since there is no operator present to notice a live hang."""
    from market_data.resilience import ResilientMarketDataProvider
    from main import _build_critic_gate_for_paper_live

    args = parse_args(["paper-live", "--symbol", "RELIANCE.NS", "--source", "dhan"])
    gate = _build_critic_gate_for_paper_live(args)

    assert isinstance(gate._provider._inner, ResilientMarketDataProvider)  # noqa: SLF001 -- read-only introspection for this test only


def test_critic_gate_refresh_fails_closed_on_a_provider_timeout_not_an_unbounded_hang():
    """End-to-end proof (not just a type check): a provider fetch that
    never returns must not hang CriticGate's own refresh. run_scan()'s
    own per-symbol exclusion handling (it already catches MarketDataError
    per symbol -- see ResilientMarketDataProvider's own docstring) absorbs
    the timeout as an excluded-symbol reason rather than raising out of
    _refresh_if_needed itself; either way the observable, load-bearing
    contract is the same fail-closed one evaluate() already promises: no
    real candidate -> blocked, and -- the actual point of this test --
    bounded by the timeout, never by the simulated 5s hang."""
    import time as time_module

    from backtesting.cache import CachedMarketDataProvider
    from live.critic_gate import CriticGate
    from datetime import datetime, timezone

    from market_data.resilience import ResilientMarketDataProvider, RetryPolicy
    from strategy.signal import ReasonCode, Side, Signal

    class _HangingProvider:
        def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
            time_module.sleep(5)  # far longer than the tiny timeout below -- must never actually be awaited
            raise AssertionError("should have been abandoned by the timeout, never reached")

    resilient = ResilientMarketDataProvider(_HangingProvider(), timeout_seconds=0.1, retry_policy=RetryPolicy(max_attempts=1))
    provider = CachedMarketDataProvider(resilient, cache_root=__import__("pathlib").Path("/nonexistent-cache-dir-for-this-test"))
    gate = CriticGate(symbol="RELIANCE.NS", provider=provider, benchmark_symbol=None)
    signal = Signal(
        symbol="RELIANCE.NS", generated_at=datetime.now(timezone.utc), side=Side.LONG,
        reference_price=100.0, stop_price=95.0, target_price=110.0, risk_reward=2.0,
        strategy_name="trend_momentum_baseline", reason_codes=[ReasonCode.TREND_CONFIRMED],
    )

    started = time_module.monotonic()
    result = gate.evaluate(
        signal, indicators=None, kill_switch_active=False, existing_pending_order=False, existing_open_position=False,
    )
    elapsed = time_module.monotonic() - started

    assert elapsed < 2.0  # bounded by the timeout, not the simulated 5s hang
    assert result.blocked is True  # no real evidence could be fetched -- fails closed, never a silent pass


def test_paper_live_source_rejects_unknown_values():
    with pytest.raises(SystemExit):
        parse_args(["paper-live", "--symbol", "RELIANCE.NS", "--source", "zerodha"])


def test_paper_live_subcommand_overrides():
    args = parse_args([
        "paper-live", "--symbol", "AAPL", "--interval", "1d", "--period", "1y",
        "--no-human-approval", "--approval-timeout-seconds", "30", "--no-ai-explanation",
        "--auto-approve", "--freshness-multiplier", "10.0", "--initial-capital", "20000",
    ])
    assert args.interval == "1d"
    assert args.period == "1y"
    assert args.no_human_approval is True
    assert args.approval_timeout_seconds == 30.0
    assert args.no_ai_explanation is True
    assert args.auto_approve is True
    assert args.freshness_multiplier == 10.0
    assert args.initial_capital == 20_000.0


def test_dashboard_subcommand_defaults():
    args = parse_args(["dashboard"])
    assert args.command == "dashboard"
    assert args.host == "127.0.0.1"
    assert args.port == 8765


def test_dashboard_subcommand_overrides():
    args = parse_args(["dashboard", "--host", "0.0.0.0", "--port", "9000"])
    assert args.host == "0.0.0.0"
    assert args.port == 9000


def test_dashboard_command_warns_on_non_loopback_host(monkeypatch, capsys):
    import uvicorn

    import main as main_module

    # uvicorn is imported locally inside run_dashboard_command -- patch the real module directly.
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)

    args = parse_args(["dashboard", "--host", "0.0.0.0", "--port", "9000"])
    main_module.run_dashboard_command(args)

    captured = capsys.readouterr()
    assert "WARNING: binding the dashboard to '0.0.0.0'" in captured.out
    assert "no authentication or CSRF protection" in captured.out


def test_dashboard_command_does_not_warn_on_the_default_loopback_host(monkeypatch, capsys):
    import uvicorn

    import main as main_module

    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)

    args = parse_args(["dashboard"])
    main_module.run_dashboard_command(args)

    captured = capsys.readouterr()
    assert "WARNING" not in captured.out


def test_scan_subcommand_defaults():
    args = parse_args(["scan", "--symbols", "AAPL,MSFT"])
    assert args.command == "scan"
    assert args.symbols == "AAPL,MSFT"
    assert args.watchlist_file is None
    assert args.period == "1y"
    assert args.interval == "1d"
    assert args.benchmark == "^NSEI"
    assert args.db is None
    assert args.top == 10


def test_scan_subcommand_overrides():
    args = parse_args([
        "scan", "--watchlist-file", "watchlist.yaml", "--period", "2y", "--interval", "1wk",
        "--benchmark", "", "--db", "/tmp/scanner.db", "--top", "5",
    ])
    assert args.watchlist_file == "watchlist.yaml"
    assert args.symbols is None
    assert args.period == "2y"
    assert args.interval == "1wk"
    assert args.benchmark == ""
    assert args.db == "/tmp/scanner.db"
    assert args.top == 5


def test_scan_command_requires_symbols_or_watchlist_file():
    args = parse_args(["scan"])
    with pytest.raises(SystemExit):
        run_scan_command(args)


def test_research_subcommand_defaults():
    args = parse_args(["research", "--symbol", "AAPL"])
    assert args.command == "research"
    assert args.symbol == "AAPL"
    assert args.news_limit == 10
    assert args.no_ai_summary is False
    assert args.db is None


def test_research_subcommand_overrides():
    args = parse_args(["research", "--symbol", "RELIANCE.NS", "--news-limit", "3", "--no-ai-summary", "--db", "/tmp/research.db"])
    assert args.symbol == "RELIANCE.NS"
    assert args.news_limit == 3
    assert args.no_ai_summary is True
    assert args.db == "/tmp/research.db"


def test_run_research_command_end_to_end_with_fake_providers(tmp_path, capsys, monkeypatch):
    from datetime import datetime, timezone

    from research import news as research_news
    from research import sector as research_sector
    from research.models import NewsItem, SectorInfo

    class _FakeNewsProvider:
        def fetch_news(self, symbol, *, limit=10):
            return [
                NewsItem(
                    title="A real-shaped headline", summary="Summary text.", source="Yahoo Finance",
                    url="https://example.com/a", published_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
                )
            ]

    class _FakeSectorProvider:
        def fetch_sector_info(self, symbol):
            return SectorInfo(symbol=symbol, sector="Technology", industry="Consumer Electronics", as_of=datetime.now(timezone.utc))

    monkeypatch.setattr(research_news, "YahooNewsProvider", _FakeNewsProvider)
    monkeypatch.setattr(research_sector, "YahooSectorInfoProvider", _FakeSectorProvider)

    args = parse_args(["research", "--symbol", "AAPL", "--no-ai-summary", "--db", str(tmp_path / "research.db")])
    run_research_command(args)

    output = capsys.readouterr().out
    assert "RESEARCH REPORT -- EVIDENCE ONLY (no recommendation, no buy/sell)" in output
    assert "A real-shaped headline" in output
    assert "Technology" in output
    assert "AI SUMMARY: not available" in output

    from research.store import ResearchStore

    store = ResearchStore(tmp_path / "research.db")
    assert store.latest_report_for_symbol("AAPL") is not None
    store.close()


def test_decide_subcommand_defaults():
    args = parse_args(["decide", "--symbol", "AAPL"])
    assert args.command == "decide"
    assert args.symbol == "AAPL"
    assert args.scanner_db is None
    assert args.research_db is None
    assert args.paper_db is None
    assert args.no_narrative is False
    assert args.db is None


def test_decide_subcommand_overrides():
    args = parse_args([
        "decide", "--symbol", "RELIANCE.NS", "--scanner-db", "/tmp/scanner.db", "--research-db", "/tmp/research.db",
        "--paper-db", "/tmp/paper.db", "--no-narrative", "--db", "/tmp/decisions.db",
    ])
    assert args.symbol == "RELIANCE.NS"
    assert args.scanner_db == "/tmp/scanner.db"
    assert args.research_db == "/tmp/research.db"
    assert args.paper_db == "/tmp/paper.db"
    assert args.no_narrative is True
    assert args.db == "/tmp/decisions.db"


def test_run_decide_command_end_to_end_with_real_scanner_and_research_stores(tmp_path, capsys):
    from datetime import datetime, timezone

    from market_intelligence.models import CandidateScore, ScanReport
    from market_intelligence.store import ScanHistoryStore
    from research.models import ResearchReport
    from research.store import ResearchStore

    scanner_db = tmp_path / "scanner.db"
    scan_store = ScanHistoryStore(scanner_db)
    candidate = CandidateScore(
        symbol="AAPL", as_of=datetime(2024, 6, 1), last_close=190.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.1, trend_score=1.0, momentum_score=0.5, breakout_score=0.01,
        relative_strength_score=0.02, sector_strength_score=None, composite_score=1.5,
        explanation=["Trend: uptrend -> score +1.00"],
    )
    scan_store.save_report(ScanReport(
        scan_id="scan-1", as_of=datetime(2024, 6, 1, tzinfo=timezone.utc), universe_mode="watchlist",
        universe_size=1, benchmark_symbol=None, benchmark_unavailable_reason=None, config_version="cfg1",
        candidates=[candidate], excluded=[],
    ))
    scan_store.close()

    research_db = tmp_path / "research.db"
    research_store = ResearchStore(research_db)
    research_store.save_report(ResearchReport(
        report_id="report-1", symbol="AAPL", as_of=datetime(2024, 6, 1, tzinfo=timezone.utc),
        news=[], sector=None, ai_summary=None, ai_summary_unavailable_reason="skipped",
    ))
    research_store.close()

    args = parse_args([
        "decide", "--symbol", "AAPL", "--scanner-db", str(scanner_db), "--research-db", str(research_db),
        "--no-narrative", "--db", str(tmp_path / "decisions.db"),
    ])
    run_decide_command(args)

    output = capsys.readouterr().out
    assert "DECISION -- LABEL ONLY, NOT AN ORDER (no trade is placed by this command)" in output
    assert "LABEL:          BUY" in output
    assert "Confidence:     100% " in output  # trend/momentum/breakout/relative_strength all agree, sector_strength is None
    assert "Scanner evidence: none found" not in output
    assert "Research evidence: none found" not in output

    from decision_engine.store import DecisionStore

    store = DecisionStore(tmp_path / "decisions.db")
    assert store.latest_decision_for_symbol("AAPL") is not None
    store.close()


def test_run_decide_command_reports_missing_evidence_honestly(tmp_path, capsys):
    args = parse_args([
        "decide", "--symbol", "ZZZZ", "--scanner-db", str(tmp_path / "no-such-scanner.db"),
        "--research-db", str(tmp_path / "no-such-research.db"), "--no-narrative", "--db", str(tmp_path / "decisions.db"),
    ])
    run_decide_command(args)

    output = capsys.readouterr().out
    assert "LABEL:          NO_ACTION" in output
    assert "Scanner evidence: none found for ZZZZ" in output
    assert "Research evidence: none found for ZZZZ" in output


def test_size_subcommand_defaults():
    args = parse_args(["size", "--symbol", "AAPL"])
    assert args.command == "size"
    assert args.symbol == "AAPL"
    assert args.decision_db is None
    assert args.period == "6mo"
    assert args.interval == "1d"
    assert args.initial_capital == 100_000.0
    assert args.risk_per_trade == pytest.approx(0.5)
    assert args.max_daily_loss == pytest.approx(3.0)
    assert args.max_drawdown == pytest.approx(10.0)
    assert args.max_exposure == pytest.approx(25.0)
    assert args.max_consecutive_losses == 3
    assert args.min_risk_reward == pytest.approx(1.5)


def test_size_subcommand_overrides():
    args = parse_args([
        "size", "--symbol", "RELIANCE.NS", "--decision-db", "/tmp/decisions.db", "--period", "1y",
        "--interval", "1wk", "--initial-capital", "50000", "--risk-per-trade", "1.0", "--max-exposure", "40",
    ])
    assert args.symbol == "RELIANCE.NS"
    assert args.decision_db == "/tmp/decisions.db"
    assert args.period == "1y"
    assert args.interval == "1wk"
    assert args.initial_capital == 50_000.0
    assert args.risk_per_trade == pytest.approx(1.0)
    assert args.max_exposure == pytest.approx(40.0)


def test_run_size_command_reports_missing_decision_honestly(tmp_path):
    args = parse_args(["size", "--symbol", "ZZZZ", "--decision-db", str(tmp_path / "no-such-decisions.db")])
    with pytest.raises(SystemExit):
        run_size_command(args)


def test_run_size_command_end_to_end_with_a_real_decision_store(tmp_path, capsys, monkeypatch):
    from datetime import datetime

    import market.context as market_context_module
    from decision_engine.models import Decision, DecisionLabel, RiskContext
    from decision_engine.store import DecisionStore
    from market.context import MarketContext
    from market_intelligence.models import CandidateScore

    decision_db = tmp_path / "decisions.db"
    store = DecisionStore(decision_db)
    candidate = CandidateScore(
        symbol="AAPL", as_of=datetime(2024, 6, 1), last_close=190.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.1, trend_score=1.0, momentum_score=0.5, breakout_score=0.01,
        relative_strength_score=0.02, sector_strength_score=None, composite_score=1.5,
        explanation=["fake"],
    )
    store.save_decision(Decision(
        decision_id="dec-1", symbol="AAPL", as_of=datetime(2024, 6, 1, 12, 0, 0), label=DecisionLabel.BUY,
        rationale=["all factors agree"], config_version="cfg1", scanner_evidence=candidate, research_evidence=None,
        market_context=None, risk_context=RiskContext.unknown(), narrative=None, narrative_unavailable_reason=None,
    ))
    store.close()

    fake_market_context = MarketContext(symbol="AAPL", as_of=datetime(2024, 6, 1), price=200.0, atr_14=5.0)
    monkeypatch.setattr(market_context_module, "get_market_context", lambda symbol, **kw: fake_market_context)

    args = parse_args(["size", "--symbol", "AAPL", "--decision-db", str(decision_db), "--initial-capital", "100000"])
    run_size_command(args)

    output = capsys.readouterr().out
    assert "POSITION SIZING PREVIEW -- NOT AN ORDER (no real or paper trade is placed)" in output
    assert "Decision:       BUY" in output
    assert "Approved:       True" in output
    assert "Quantity:" in output


def test_predict_subcommand_defaults():
    args = parse_args(["predict", "--symbol", "AAPL"])
    assert args.command == "predict"
    assert args.symbol == "AAPL"
    assert args.decision_db is None
    assert args.period == "6mo"
    assert args.interval == "1d"
    assert args.horizon_bars == 20
    assert args.db is None
    assert args.initial_capital is None  # sentinel: no capital given, no sizing computed -- prior behavior exactly


def test_predict_subcommand_initial_capital_override():
    args = parse_args(["predict", "--symbol", "AAPL", "--initial-capital", "20000"])
    assert args.initial_capital == 20_000.0


def test_predict_subcommand_overrides():
    args = parse_args([
        "predict", "--symbol", "RELIANCE.NS", "--decision-db", "/tmp/decisions.db", "--period", "1y",
        "--interval", "1wk", "--horizon-bars", "10", "--db", "/tmp/predictions.db",
    ])
    assert args.symbol == "RELIANCE.NS"
    assert args.decision_db == "/tmp/decisions.db"
    assert args.period == "1y"
    assert args.interval == "1wk"
    assert args.horizon_bars == 10
    assert args.db == "/tmp/predictions.db"


def test_run_predict_command_reports_missing_decision_honestly(tmp_path):
    args = parse_args(["predict", "--symbol", "ZZZZ", "--decision-db", str(tmp_path / "no-such-decisions.db")])
    with pytest.raises(SystemExit):
        run_predict_command(args)


def test_run_predict_command_end_to_end_with_a_real_decision_store(tmp_path, capsys, monkeypatch):
    from datetime import datetime

    import market.context as market_context_module
    from decision_engine.models import Decision, DecisionLabel, RiskContext
    from decision_engine.store import DecisionStore
    from market.context import MarketContext
    from market_intelligence.models import CandidateScore

    decision_db = tmp_path / "decisions.db"
    store = DecisionStore(decision_db)
    candidate = CandidateScore(
        symbol="AAPL", as_of=datetime(2024, 6, 1), last_close=190.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.1, trend_score=1.0, momentum_score=0.5, breakout_score=0.01,
        relative_strength_score=0.02, sector_strength_score=None, composite_score=1.5,
        explanation=["fake"],
    )
    store.save_decision(Decision(
        decision_id="dec-1", symbol="AAPL", as_of=datetime(2024, 6, 1, 12, 0, 0), label=DecisionLabel.BUY,
        rationale=["all factors agree"], config_version="cfg1", scanner_evidence=candidate, research_evidence=None,
        market_context=None, risk_context=RiskContext.unknown(), narrative=None, narrative_unavailable_reason=None,
    ))
    store.close()

    fake_market_context = MarketContext(symbol="AAPL", as_of=datetime(2024, 6, 1), price=200.0, atr_14=5.0)
    monkeypatch.setattr(market_context_module, "get_market_context", lambda symbol, **kw: fake_market_context)

    args = parse_args(["predict", "--symbol", "AAPL", "--decision-db", str(decision_db), "--db", str(tmp_path / "predictions.db")])
    run_predict_command(args)

    output = capsys.readouterr().out
    assert "SHADOW PREDICTION RECORDED -- NOT AN ORDER (tracked for later evaluation only)" in output
    assert "Symbol:         AAPL" in output

    from predictions.store import PredictionStore

    prediction_store = PredictionStore(tmp_path / "predictions.db")
    predictions = prediction_store.list_predictions()
    assert len(predictions) == 1
    assert predictions[0].symbol == "AAPL"
    assert predictions[0].risk_decision is None  # no --initial-capital given -- unchanged from before this flag existed
    prediction_store.close()


def test_run_predict_command_persists_a_trade_plan_when_initial_capital_is_given(tmp_path, capsys, monkeypatch):
    """Mission auditability requirement: entry/stop/target alone are not
    a trade plan -- quantity/capital/risk amount must be persisted too,
    not just printed and lost, when the caller supplies capital to size
    against."""
    from datetime import datetime

    import market.context as market_context_module
    from decision_engine.models import Decision, DecisionLabel, RiskContext
    from decision_engine.store import DecisionStore
    from market.context import MarketContext
    from market_intelligence.models import CandidateScore

    decision_db = tmp_path / "decisions.db"
    store = DecisionStore(decision_db)
    candidate = CandidateScore(
        symbol="AAPL", as_of=datetime(2024, 6, 1), last_close=190.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.1, trend_score=1.0, momentum_score=0.5, breakout_score=0.01,
        relative_strength_score=0.02, sector_strength_score=None, composite_score=1.5,
        explanation=["fake"],
    )
    store.save_decision(Decision(
        decision_id="dec-1", symbol="AAPL", as_of=datetime(2024, 6, 1, 12, 0, 0), label=DecisionLabel.BUY,
        rationale=["all factors agree"], config_version="cfg1", scanner_evidence=candidate, research_evidence=None,
        market_context=None, risk_context=RiskContext.unknown(), narrative=None, narrative_unavailable_reason=None,
    ))
    store.close()

    fake_market_context = MarketContext(symbol="AAPL", as_of=datetime(2024, 6, 1), price=200.0, atr_14=5.0)
    monkeypatch.setattr(market_context_module, "get_market_context", lambda symbol, **kw: fake_market_context)

    args = parse_args([
        "predict", "--symbol", "AAPL", "--decision-db", str(decision_db), "--db", str(tmp_path / "predictions.db"),
        "--initial-capital", "20000",
    ])
    run_predict_command(args)

    output = capsys.readouterr().out
    assert "Trade plan (persisted with this prediction -- NOT an order):" in output
    assert "Capital:        20,000.00" in output
    assert "Approved:       True" in output

    from predictions.store import PredictionStore

    prediction_store = PredictionStore(tmp_path / "predictions.db")
    predictions = prediction_store.list_predictions()
    prediction_store.close()
    assert len(predictions) == 1
    rd = predictions[0].risk_decision
    assert rd is not None
    assert rd.approved is True
    assert rd.account_equity == 20_000.0
    assert rd.position_size is not None
    assert rd.position_size.quantity > 0
    assert rd.risk_amount is not None and rd.risk_amount > 0


def test_run_predict_command_still_persists_the_prediction_when_capital_is_too_small_to_size(tmp_path, capsys, monkeypatch):
    """Fail-closed, not fail-crashed: an --initial-capital too small to
    size even 1 unit must still record the underlying price-level
    prediction (the prediction is valid regardless of capital), with an
    honestly rejected (approved=False, position_size=None) risk_decision
    -- never silently dropped, never a crash."""
    from datetime import datetime

    import market.context as market_context_module
    from decision_engine.models import Decision, DecisionLabel, RiskContext
    from decision_engine.store import DecisionStore
    from market.context import MarketContext
    from market_intelligence.models import CandidateScore

    decision_db = tmp_path / "decisions.db"
    store = DecisionStore(decision_db)
    candidate = CandidateScore(
        symbol="AAPL", as_of=datetime(2024, 6, 1), last_close=190.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.1, trend_score=1.0, momentum_score=0.5, breakout_score=0.01,
        relative_strength_score=0.02, sector_strength_score=None, composite_score=1.5,
        explanation=["fake"],
    )
    store.save_decision(Decision(
        decision_id="dec-1", symbol="AAPL", as_of=datetime(2024, 6, 1, 12, 0, 0), label=DecisionLabel.BUY,
        rationale=["all factors agree"], config_version="cfg1", scanner_evidence=candidate, research_evidence=None,
        market_context=None, risk_context=RiskContext.unknown(), narrative=None, narrative_unavailable_reason=None,
    ))
    store.close()

    fake_market_context = MarketContext(symbol="AAPL", as_of=datetime(2024, 6, 1), price=200.0, atr_14=5.0)
    monkeypatch.setattr(market_context_module, "get_market_context", lambda symbol, **kw: fake_market_context)

    args = parse_args([
        "predict", "--symbol", "AAPL", "--decision-db", str(decision_db), "--db", str(tmp_path / "predictions.db"),
        "--initial-capital", "1",  # far too small to ever size 1 unit at any realistic risk_per_trade
    ])
    run_predict_command(args)  # must not raise

    output = capsys.readouterr().out
    assert "Approved:       False" in output
    assert "ZERO_POSITION_SIZE" in output

    from predictions.store import PredictionStore

    prediction_store = PredictionStore(tmp_path / "predictions.db")
    predictions = prediction_store.list_predictions()
    prediction_store.close()
    assert len(predictions) == 1  # the prediction itself was still recorded
    rd = predictions[0].risk_decision
    assert rd is not None
    assert rd.approved is False
    assert rd.position_size is None


def test_run_predict_command_skips_a_duplicate_for_the_same_entry_bar(tmp_path, capsys, monkeypatch):
    """Phase 36: running `predict` twice against an unchanged entry bar
    must not silently create a second, redundant PredictionRecord."""
    from datetime import datetime

    import market.context as market_context_module
    from decision_engine.models import Decision, DecisionLabel, RiskContext
    from decision_engine.store import DecisionStore
    from market.context import MarketContext
    from market_intelligence.models import CandidateScore

    decision_db = tmp_path / "decisions.db"
    store = DecisionStore(decision_db)
    candidate = CandidateScore(
        symbol="AAPL", as_of=datetime(2024, 6, 1), last_close=190.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.1, trend_score=1.0, momentum_score=0.5, breakout_score=0.01,
        relative_strength_score=0.02, sector_strength_score=None, composite_score=1.5,
        explanation=["fake"],
    )
    store.save_decision(Decision(
        decision_id="dec-1", symbol="AAPL", as_of=datetime(2024, 6, 1, 12, 0, 0), label=DecisionLabel.BUY,
        rationale=["all factors agree"], config_version="cfg1", scanner_evidence=candidate, research_evidence=None,
        market_context=None, risk_context=RiskContext.unknown(), narrative=None, narrative_unavailable_reason=None,
    ))
    store.close()

    fake_market_context = MarketContext(symbol="AAPL", as_of=datetime(2024, 6, 1), price=200.0, atr_14=5.0)
    monkeypatch.setattr(market_context_module, "get_market_context", lambda symbol, **kw: fake_market_context)

    args = parse_args(["predict", "--symbol", "AAPL", "--decision-db", str(decision_db), "--db", str(tmp_path / "predictions.db")])
    run_predict_command(args)
    capsys.readouterr()

    with pytest.raises(SystemExit):
        run_predict_command(args)

    err = capsys.readouterr().err
    assert "already recorded -- skipping duplicate" in err

    from predictions.store import PredictionStore

    prediction_store = PredictionStore(tmp_path / "predictions.db")
    assert len(prediction_store.list_predictions()) == 1  # still just one, not two
    prediction_store.close()


def test_evaluate_subcommand_defaults():
    args = parse_args(["evaluate"])
    assert args.command == "evaluate"
    assert args.db is None
    assert args.period == "1y"


def test_evaluate_subcommand_overrides():
    args = parse_args(["evaluate", "--db", "/tmp/predictions.db", "--period", "2y"])
    assert args.db == "/tmp/predictions.db"
    assert args.period == "2y"


def test_run_evaluate_command_with_no_predictions_reports_zero_cleanly(tmp_path, capsys):
    args = parse_args(["evaluate", "--db", str(tmp_path / "predictions.db")])
    run_evaluate_command(args)

    output = capsys.readouterr().out
    assert "SHADOW PREDICTION EVALUATION -- NOT AN ORDER (outcome monitoring only)" in output
    assert "Predictions needing evaluation: 0" in output
    assert "Total:             0" in output
    assert "n/a" in output


def test_learn_subcommand_defaults():
    args = parse_args(["learn"])
    assert args.command == "learn"
    assert args.predictions_db is None
    assert args.decision_db is None


def test_learn_subcommand_overrides():
    args = parse_args(["learn", "--predictions-db", "/tmp/predictions.db", "--decision-db", "/tmp/decisions.db"])
    assert args.predictions_db == "/tmp/predictions.db"
    assert args.decision_db == "/tmp/decisions.db"


def test_run_learn_command_with_no_predictions_reports_zero_cleanly(tmp_path, capsys):
    args = parse_args(["learn", "--predictions-db", str(tmp_path / "no-such-predictions.db")])
    run_learn_command(args)

    output = capsys.readouterr().out
    assert "PERFORMANCE LEARNING REPORT -- READ-ONLY (no configuration changed, no order placed)" in output
    assert "Predictions considered: 0" in output
    assert "Experiment Tracking" in output


def test_run_learn_command_end_to_end_with_real_stores(tmp_path, capsys, monkeypatch):
    from datetime import datetime, timezone

    import backtesting.cache as cache_module
    import market.data_provider as market_data_provider_module
    from decision_engine.models import Decision, DecisionLabel, RiskContext
    from decision_engine.store import DecisionStore
    from market.data_provider import MarketDataError
    from market_intelligence.models import CandidateScore
    from predictions.models import PredictionEvaluation, PredictionOutcomeState, PredictionRecord
    from predictions.store import PredictionStore

    decision_db = tmp_path / "decisions.db"
    decision_store = DecisionStore(decision_db)
    candidate = CandidateScore(
        symbol="AAPL", as_of=datetime(2024, 1, 2), last_close=100.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.1, trend_score=1.0, momentum_score=0.5, breakout_score=0.01,
        relative_strength_score=0.02, sector_strength_score=None, composite_score=1.5, explanation=["fake"],
    )
    decision_store.save_decision(Decision(
        decision_id="dec-1", symbol="AAPL", as_of=datetime(2024, 1, 2, tzinfo=timezone.utc), label=DecisionLabel.BUY,
        rationale=["fake"], config_version="cfg1", scanner_evidence=candidate, research_evidence=None,
        market_context=None, risk_context=RiskContext.unknown(), narrative=None, narrative_unavailable_reason=None,
    ))
    decision_store.close()

    predictions_db = tmp_path / "predictions.db"
    prediction_store = PredictionStore(predictions_db)
    prediction_store.save_prediction(PredictionRecord(
        prediction_id="pred-1", decision_id="dec-1", symbol="AAPL", created_at=datetime.now(timezone.utc),
        label=DecisionLabel.BUY, entry_price=100.0, stop_price=95.0, target_price=110.0, entry_time=datetime(2024, 1, 2),
        horizon_bars=20, interval="1d",
    ))
    prediction_store.save_evaluation(PredictionEvaluation(
        evaluation_id="eval-1", prediction_id="pred-1", evaluated_at=datetime.now(timezone.utc),
        outcome=PredictionOutcomeState.TARGET_HIT, bars_observed=5, exit_time=datetime(2024, 1, 9),
        exit_price=110.0, actual_return=0.10, max_favorable_excursion=0.10, max_adverse_excursion=0.01, detail="test",
    ))
    prediction_store.close()

    class _FakeProvider:
        def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
            raise MarketDataError("no regime data in this test")

    # Avoid any real network/cache-file I/O: replace the provider factory with a
    # fake, and replace CachedMarketDataProvider with an identity pass-through
    # so no data/market/ cache file is ever written by this test.
    monkeypatch.setattr(market_data_provider_module, "get_market_data_provider", lambda: _FakeProvider())
    monkeypatch.setattr(cache_module, "CachedMarketDataProvider", lambda inner: inner)

    args = parse_args(["learn", "--predictions-db", str(predictions_db), "--decision-db", str(decision_db)])
    run_learn_command(args)

    output = capsys.readouterr().out
    assert "PERFORMANCE LEARNING REPORT -- READ-ONLY (no configuration changed, no order placed)" in output
    assert "Predictions considered: 1" in output
    assert "cfg1" in output


def test_review_subcommand_defaults():
    args = parse_args(["review", "--symbol", "AAPL"])
    assert args.command == "review"
    assert args.symbol == "AAPL"
    assert args.decision_db is None


def test_review_subcommand_overrides():
    args = parse_args(["review", "--symbol", "RELIANCE.NS", "--decision-db", "/tmp/decisions.db"])
    assert args.symbol == "RELIANCE.NS"
    assert args.decision_db == "/tmp/decisions.db"


def test_run_review_command_reports_missing_decision_honestly(tmp_path):
    args = parse_args(["review", "--symbol", "ZZZZ", "--decision-db", str(tmp_path / "no-such-decisions.db")])
    with pytest.raises(SystemExit):
        run_review_command(args)


def test_run_review_command_end_to_end_with_a_real_decision_store(tmp_path, capsys, monkeypatch):
    from datetime import datetime, timezone

    from agents import analyst
    from decision_engine.models import Decision, DecisionLabel, DecisionReview, RiskContext
    from decision_engine.store import DecisionStore
    from llm import provider as llm_provider
    from market_intelligence.models import CandidateScore
    from tests.conftest import FakeChatModel

    decision_db = tmp_path / "decisions.db"
    store = DecisionStore(decision_db)
    candidate = CandidateScore(
        symbol="AAPL", as_of=datetime(2024, 6, 1), last_close=190.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.1, trend_score=1.0, momentum_score=0.5, breakout_score=0.01,
        relative_strength_score=0.02, sector_strength_score=None, composite_score=1.5,
        explanation=["fake"],
    )
    store.save_decision(Decision(
        decision_id="dec-1", symbol="AAPL", as_of=datetime(2024, 6, 1, tzinfo=timezone.utc), label=DecisionLabel.BUY,
        rationale=["all factors agree"], config_version="cfg1", scanner_evidence=candidate, research_evidence=None,
        market_context=None, risk_context=RiskContext.unknown(), narrative=None, narrative_unavailable_reason=None,
    ))
    store.close()

    fake_review = DecisionReview(
        concerns=["Un-tuned composite weights."], supporting_points=["Trend and momentum corroborate."],
        overall_assessment="Defensible given the recorded evidence.",
    )
    monkeypatch.setattr(analyst, "get_analyst_llm", lambda role: FakeChatModel({DecisionReview: fake_review}))
    monkeypatch.setattr(llm_provider, "check_ollama_availability", lambda **kwargs: None)

    args = parse_args(["review", "--symbol", "AAPL", "--decision-db", str(decision_db)])
    run_review_command(args)

    output = capsys.readouterr().out
    assert "INDEPENDENT DECISION REVIEW -- AI CRITIQUE ONLY, CANNOT CHANGE THE LABEL" in output
    assert "Label:   BUY" in output
    assert "Un-tuned composite weights." in output
    assert "Defensible given the recorded evidence." in output


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
def test_run_live_sim_command_cost_model_flag_selects_the_india_preset(tmp_path, monkeypatch):
    from backtesting.costs import CostModel

    captured = _capture_engine_cost_model(monkeypatch)
    args = parse_args([
        "live-sim", "--symbol", "AAPL", "--interval", "1d", "--period", "1y",
        "--db", str(tmp_path / "live_sim.db"), "--max-bars", "1", "--freshness-multiplier", "1000000",
        "--cost-model", "india_nse_intraday_2026",
    ])
    run_live_sim_command(args)
    assert captured["cost_model"] == CostModel.india_nse_intraday_2026()


@pytestmark_paper_live
def test_run_paper_live_command_defaults_to_the_generic_cost_model(tmp_path, monkeypatch):
    """The command this mission is centered on -- previously always
    silently used CostModel()'s generic placeholder here too (zero STT/
    exchange charges), even though this is the intended real-money-shaped
    proving ground. Default unchanged for backward compatibility."""
    from backtesting.costs import CostModel

    captured = _capture_engine_cost_model(monkeypatch)
    args = parse_args([
        "paper-live", "--symbol", "AAPL", "--interval", "1d", "--period", "1y",
        "--db", str(tmp_path / "paper.db"), "--state-db", str(tmp_path / "state.db"),
        "--max-bars", "1", "--auto-approve", "--no-ai-explanation", "--freshness-multiplier", "1000000",
    ])
    run_paper_live_command(args)
    assert captured["cost_model"] == CostModel()


@pytestmark_paper_live
def test_run_paper_live_command_cost_model_flag_selects_the_india_preset(tmp_path, monkeypatch, capsys):
    from backtesting.costs import CostModel

    captured = _capture_engine_cost_model(monkeypatch)
    args = parse_args([
        "paper-live", "--symbol", "AAPL", "--interval", "1d", "--period", "1y",
        "--db", str(tmp_path / "paper.db"), "--state-db", str(tmp_path / "state.db"),
        "--max-bars", "1", "--auto-approve", "--no-ai-explanation", "--freshness-multiplier", "1000000",
        "--cost-model", "india_nse_intraday_2026",
    ])
    run_paper_live_command(args)
    assert captured["cost_model"] == CostModel.india_nse_intraday_2026()
    output = capsys.readouterr().out
    assert "Cost model: india_nse_intraday_2026" in output
    assert "APPROXIMATE" in output


@pytestmark_paper_live
def test_run_scan_command_end_to_end_against_cached_data(tmp_path, capsys):
    args = parse_args([
        "scan", "--symbols", "AAPL", "--period", "1y", "--interval", "1d",
        "--benchmark", "", "--db", str(tmp_path / "scanner.db"), "--top", "5",
    ])
    run_scan_command(args)
    output = capsys.readouterr().out
    assert "MARKET SCANNER -- CANDIDATE DISCOVERY (no recommendation, no buy/sell)" in output
    assert "AAPL" in output

    from market_intelligence.store import ScanHistoryStore

    store = ScanHistoryStore(tmp_path / "scanner.db")
    assert store.latest_report() is not None
    store.close()


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
def test_run_paper_live_command_runtime_dir_derives_the_documented_layout(tmp_path, capsys):
    """Real-time strategy validation mission, multi-symbol hardening pass
    -- proves --runtime-dir through the REAL CLI entrypoint (not just
    live/runtime_layout.py's own unit tests): the exact
    {runtime-dir}/{symbol}/{paper.db,state.db,predictions.db,logs/}
    layout is created and genuinely used, real trading path unaffected."""
    runtime_dir = tmp_path / "runtime"
    args = parse_args([
        "paper-live", "--symbol", "AAPL", "--interval", "1d", "--period", "1y",
        "--runtime-dir", str(runtime_dir),
        "--record-predictions", "--max-bars", "70", "--auto-approve", "--no-ai-explanation",
        "--freshness-multiplier", "1000000",
    ])
    run_paper_live_command(args)
    output = capsys.readouterr().out

    symbol_dir = runtime_dir / "AAPL"
    assert f"RUNTIME DIR: {symbol_dir}" in output
    assert (symbol_dir / "paper.db").exists()
    assert (symbol_dir / "state.db").exists()
    assert (symbol_dir / "predictions.db").exists()
    assert (symbol_dir / "logs").is_dir()
    assert "SIGNAL DETECTED" in output
    assert "-> APPROVED" in output


def test_run_paper_live_command_writes_a_heartbeat_and_a_graceful_shutdown_marker(tmp_path, capsys):
    """Operational-reliability mission: real forensic gap found and
    root-caused 2026-09-16 -- an entire 15-symbol fleet stopped
    simultaneously with zero error in any log; the only way to find out
    why was manual Windows Event Log archaeology (a real OS reboot).
    Proves live/heartbeat.py's wiring through the REAL CLI entrypoint: a
    normal (max-bars-reached) run leaves BOTH files, and a SECOND
    invocation against the same runtime-dir correctly reports the first
    run as GRACEFUL_SHUTDOWN."""
    runtime_dir = tmp_path / "runtime"
    base_args = [
        "paper-live", "--symbol", "AAPL", "--interval", "1d", "--period", "1y",
        "--runtime-dir", str(runtime_dir),
        "--max-bars", "70", "--auto-approve", "--no-ai-explanation",
        "--freshness-multiplier", "1000000",
    ]

    run_paper_live_command(parse_args(base_args))
    first_output = capsys.readouterr().out
    assert "PREVIOUS SESSION" not in first_output  # first-ever run for this symbol/runtime-dir

    symbol_dir = runtime_dir / "AAPL"
    heartbeat_path = symbol_dir / "heartbeat.json"
    shutdown_path = symbol_dir / "graceful_shutdown.json"
    assert heartbeat_path.exists()
    assert shutdown_path.exists()

    run_paper_live_command(parse_args(base_args))
    second_output = capsys.readouterr().out
    assert "PREVIOUS SESSION: GRACEFUL_SHUTDOWN" in second_output


def test_run_paper_live_command_reports_abnormal_termination_when_the_shutdown_marker_is_missing(tmp_path, capsys):
    # Simulates exactly the 2026-09-16 incident's own signature: a real
    # heartbeat from a prior run, but no graceful-shutdown marker (as a
    # SIGKILL/power-loss/OS-reboot would leave it) -- the NEXT invocation
    # against the same runtime-dir must say so plainly, not silently.
    runtime_dir = tmp_path / "runtime"
    base_args = [
        "paper-live", "--symbol", "AAPL", "--interval", "1d", "--period", "1y",
        "--runtime-dir", str(runtime_dir),
        "--max-bars", "70", "--auto-approve", "--no-ai-explanation",
        "--freshness-multiplier", "1000000",
    ]
    run_paper_live_command(parse_args(base_args))
    capsys.readouterr()

    symbol_dir = runtime_dir / "AAPL"
    (symbol_dir / "graceful_shutdown.json").unlink()

    run_paper_live_command(parse_args(base_args))
    output = capsys.readouterr().out
    assert "PREVIOUS SESSION: ABNORMAL_TERMINATION" in output
    assert "crash, kill, power loss, or OS reboot" in output


def test_run_paper_live_command_runtime_dir_requires_symbol():
    args = parse_args(["paper-live", "--runtime-dir", "runtime", "--interval", "1d"])
    with pytest.raises(SystemExit, match="requires --symbol"):
        run_paper_live_command(args)


def test_run_paper_live_command_runtime_dir_rejects_combination_with_explicit_db(tmp_path):
    args = parse_args([
        "paper-live", "--symbol", "AAPL", "--runtime-dir", str(tmp_path / "runtime"),
        "--db", str(tmp_path / "paper.db"), "--interval", "1d",
    ])
    with pytest.raises(SystemExit, match="cannot be combined"):
        run_paper_live_command(args)


@pytestmark_paper_live
def test_run_paper_live_command_refuses_to_start_against_a_contaminated_store(tmp_path, capsys):
    """The real, mission-required safety guard: a store that already
    holds another symbol's trades must refuse to be used by a DIFFERENT
    symbol's paper-live process -- proven against the real PaperStore
    the CLI itself opens, not a mock."""
    from datetime import datetime

    from paper.models import Position, PositionStatus
    from paper.store import PaperStore

    db_path = tmp_path / "paper.db"
    seed_store = PaperStore(db_path)
    seed_store.save_position(Position(
        position_id="pos-1", symbol="TCS.NS", status=PositionStatus.OPEN,
        signal_id="sig-1", entry_order_id="order-1", entry_fill_id="fill-1",
        quantity=1, entry_price=100.0, entry_time=datetime(2024, 1, 1),
        stop_price=95.0, target_price=110.0,
    ))
    seed_store.close()

    args = parse_args([
        "paper-live", "--symbol", "AAPL", "--interval", "1d", "--period", "1y",
        "--db", str(db_path), "--state-db", str(tmp_path / "state.db"),
        "--max-bars", "5", "--auto-approve", "--no-ai-explanation",
    ])
    from live.runtime_layout import CrossSymbolContaminationError

    with pytest.raises(CrossSymbolContaminationError, match="TCS.NS"):
        run_paper_live_command(args)


@pytestmark_paper_live
def test_run_paper_live_command_refuses_to_start_against_a_contaminated_predictions_store(tmp_path):
    """Same guard, the predictions-db path: a predictions.db that
    already holds another symbol's predictions must refuse a DIFFERENT
    symbol's --record-predictions session."""
    from datetime import datetime, timezone

    from decision_engine.models import DecisionLabel
    from predictions.models import PredictionRecord
    from predictions.store import PredictionStore

    predictions_db = tmp_path / "predictions.db"
    seed_store = PredictionStore(predictions_db)
    seed_store.save_prediction(PredictionRecord(
        prediction_id=PredictionRecord.new_id(), decision_id="dec-1", symbol="TCS.NS",
        created_at=datetime.now(timezone.utc), label=DecisionLabel.BUY,
        entry_price=100.0, stop_price=95.0, target_price=110.0, entry_time=datetime(2024, 1, 2),
        horizon_bars=20, interval="1d",
    ))
    seed_store.close()

    args = parse_args([
        "paper-live", "--symbol", "AAPL", "--interval", "1d", "--period", "1y",
        "--db", str(tmp_path / "paper.db"), "--state-db", str(tmp_path / "state.db"),
        "--record-predictions", "--predictions-db", str(predictions_db),
        "--max-bars", "5", "--auto-approve", "--no-ai-explanation",
    ])
    from live.runtime_layout import CrossSymbolContaminationError

    with pytest.raises(CrossSymbolContaminationError, match="TCS.NS"):
        run_paper_live_command(args)


@pytestmark_paper_live
def test_run_paper_live_command_wires_the_gap_monitor_correctly(tmp_path, monkeypatch, capsys):
    """Real-time strategy validation mission, multi-symbol hardening pass
    -- integration/wiring test for the new BarGapMonitor plumbing in
    _run_paper_live_loop. BarGapMonitor's own timing logic is already
    thoroughly unit-tested in isolation (tests/test_gap_monitor.py,
    mutation-tested); this proves the CLI loop actually calls .check()
    on every iteration and .record_new_bar() whenever a genuine new bar
    was processed, and prints the gap line when check() reports one --
    without needing to force a real multi-minute wall-clock wait."""
    import live.gap_monitor as gap_monitor_module
    from datetime import timedelta

    from live.gap_monitor import GapStatus

    calls = {"check": 0, "record_new_bar": 0}

    class _FakeGapMonitor:
        def __init__(self, *, expected_interval):
            self.expected_interval = expected_interval

        def check(self, *, now):
            calls["check"] += 1
            if calls["check"] == 3:  # force exactly one gap report, deterministically
                return GapStatus(elapsed=timedelta(seconds=999), threshold=timedelta(seconds=180), is_new=True)
            return None

        def record_new_bar(self, *, now):
            calls["record_new_bar"] += 1

    monkeypatch.setattr(gap_monitor_module, "BarGapMonitor", _FakeGapMonitor)

    args = parse_args([
        "paper-live", "--symbol", "AAPL", "--interval", "1d", "--period", "1y",
        "--db", str(tmp_path / "paper.db"), "--state-db", str(tmp_path / "state.db"),
        "--max-bars", "10", "--auto-approve", "--no-ai-explanation", "--freshness-multiplier", "1000000",
    ])
    run_paper_live_command(args)
    output = capsys.readouterr().out

    assert calls["check"] >= 3, "gap_monitor.check() must be called on every loop iteration, including before the first bar"
    assert calls["record_new_bar"] == 10, "gap_monitor.record_new_bar() must be called exactly once per genuinely new bar processed"
    assert "[GAP DETECTED]" in output
    assert "999s" in output
    assert "expected within ~180s" in output
    assert "not necessarily disconnected" in output


# --- fleet-supervise -- real-time strategy validation mission, multi-symbol hardening pass -----


def test_fleet_supervise_subcommand_is_recognized_without_the_analyze_default_prefix():
    """Regression test for a real bug found while implementing this
    subcommand: parse_args() prepends the implicit `analyze` default
    subcommand whenever argv[0] is not in the module-level
    _KNOWN_COMMANDS tuple -- adding a NEW subparser without also adding
    its name to that tuple silently mis-parses every invocation (e.g.
    `fleet-supervise --help` printed `analyze`'s help instead of
    fleet-supervise's own, with no error at all)."""
    args = parse_args(["fleet-supervise", "--symbols", "AAPL", "--runtime-dir", "runtime"])
    assert args.command == "fleet-supervise"
    assert args.symbols == "AAPL"


def test_fleet_supervise_subcommand_defaults():
    args = parse_args(["fleet-supervise", "--symbols", "AAPL,MSFT", "--runtime-dir", "runtime"])
    assert args.watchlist_file is None
    assert args.source == "dhan", "the only real production value -- never silently mock"
    assert args.interval == "1m"
    assert args.cost_model == "india_nse_intraday_2026", "a multi-symbol NSE session must never silently use the generic zero-cost placeholder"
    assert args.evaluate_every_n_bars == 20
    assert args.max_bars is None
    assert args.max_restarts == 2
    assert args.poll_interval_seconds == 30.0
    assert args.max_polls is None
    assert args.launch_stagger_seconds == 1.5, "real, observed evidence: simultaneous launch hit Dhan's documented 5-connection cap"


def test_run_fleet_supervise_command_runs_two_mock_workers_to_clean_completion(tmp_path, capsys):
    """Real end-to-end test: launches two REAL `paper-live` subprocesses
    (one per symbol, --source mock, no live dependency), supervises them
    to natural completion, and verifies the isolated runtime-dir layout
    (live/runtime_layout.py) came out right for BOTH symbols -- proving
    the fleet-supervise orchestration itself (argument wiring, process
    launch, health polling, clean shutdown) works, not just its
    individual pieces in isolation (already covered by
    tests/test_fleet_supervisor.py)."""
    args = parse_args([
        "fleet-supervise", "--symbols", "AAPL,MSFT", "--runtime-dir", str(tmp_path),
        "--source", "mock", "--max-bars", "3", "--poll-interval-seconds", "1", "--max-polls", "10", "--launch-stagger-seconds", "0",
    ])
    run_fleet_supervise_command(args)
    output = capsys.readouterr().out

    assert "FLEET SUPERVISE: 2 symbol(s)" in output
    assert "every worker has exited" in output
    assert "all workers stopped" in output
    assert "EXITED_ERROR" not in output
    assert "EXHAUSTED" not in output

    for symbol in ("AAPL", "MSFT"):
        symbol_dir = tmp_path / symbol
        assert (symbol_dir / "paper.db").exists()
        assert (symbol_dir / "state.db").exists()
        assert (symbol_dir / "predictions.db").exists()
        log_text = (symbol_dir / "logs" / "session.log").read_text(encoding="utf-8", errors="replace")
        assert "bar#" in log_text


def test_launch_stagger_seconds_actually_delays_between_initial_launches(tmp_path, capsys):
    """Adversarial hardening pass (2026-09-18): real, observed evidence
    (docs/LIVE_SYSTEM_HARDENING_FINAL_REPORT.md Part VI) showed 4 of 15
    symbols hit a genuine Dhan code=805 'too many connections' disconnect
    when all 15 workers connected within the same ~1-3s window under one
    shared client ID -- every one self-healed via the existing reconnect
    machinery, so this was never a currently-broken failure, but real,
    avoidable startup churn. This test proves the mechanism (launches are
    actually spaced in real wall-clock time) -- NOT a claim that this
    eliminates every 805 against a real Dhan account, which has not been
    live-validated. Real subprocess launches throughout; a COMPARATIVE
    measurement against a stagger=0 baseline (rather than an absolute
    floor) so real subprocess spawn/run overhead -- which alone can
    exceed a small absolute threshold and mask a completely disabled
    stagger, a real gap this test's own first draft had until the
    mutation pass caught it -- can never produce a false pass."""
    import time as time_module_for_test

    def _run(stagger: str) -> float:
        start = time_module_for_test.monotonic()
        args = parse_args([
            "fleet-supervise", "--symbols", "AAPL,MSFT,GOOG", "--runtime-dir", str(tmp_path / stagger),
            "--source", "mock", "--max-bars", "3", "--poll-interval-seconds", "1", "--max-polls", "10",
            "--launch-stagger-seconds", stagger,
        ])
        run_fleet_supervise_command(args)
        elapsed = time_module_for_test.monotonic() - start
        assert "every worker has exited" in capsys.readouterr().out
        return elapsed

    baseline = _run("0")
    staggered = _run("3.0")
    # 3 symbols -> 2 stagger gaps of 3.0s each = 6.0s expected extra;
    # a conservative 3.0s minimum absorbs real subprocess timing variance
    # while remaining impossible to satisfy if staggering silently did
    # nothing (which is exactly what the mutation pass proved: without
    # this comparison, a completely disabled stagger still passed).
    assert staggered - baseline >= 3.0


def test_run_fleet_supervise_command_writes_a_supervisor_heartbeat_and_graceful_marker(tmp_path, capsys):
    """Operational-reliability mission: the SAME heartbeat/graceful-
    shutdown pattern proven for individual paper-live workers, extended
    to the fleet-supervise process itself -- a future incident needs to
    be able to tell "the supervisor died" apart from "every worker died
    independently," previously indistinguishable from worker-side
    evidence alone. A real two-invocation sequence: the first run
    completes normally and leaves both files under runtime/_supervisor/;
    the second run reports the first as GRACEFUL_SHUTDOWN."""
    base_args = [
        "fleet-supervise", "--symbols", "AAPL,MSFT", "--runtime-dir", str(tmp_path),
        "--source", "mock", "--max-bars", "3", "--poll-interval-seconds", "1", "--max-polls", "10", "--launch-stagger-seconds", "0",
    ]

    run_fleet_supervise_command(parse_args(base_args))
    first_output = capsys.readouterr().out
    assert "PREVIOUS SUPERVISOR SESSION" not in first_output

    supervisor_dir = tmp_path / "_supervisor"
    heartbeat_path = supervisor_dir / "heartbeat.json"
    shutdown_path = supervisor_dir / "graceful_shutdown.json"
    assert heartbeat_path.exists()
    assert shutdown_path.exists()

    run_fleet_supervise_command(parse_args(base_args))
    second_output = capsys.readouterr().out
    assert "PREVIOUS SUPERVISOR SESSION: GRACEFUL_SHUTDOWN" in second_output


def test_run_fleet_supervise_command_reports_abnormal_termination_when_the_supervisor_marker_is_missing(tmp_path, capsys):
    # Simulates a supervisor that was itself killed abruptly (crash,
    # SIGKILL, or an OS reboot like the real 2026-09-16 incident) --
    # a real heartbeat exists from the prior run but no graceful marker.
    base_args = [
        "fleet-supervise", "--symbols", "AAPL,MSFT", "--runtime-dir", str(tmp_path),
        "--source", "mock", "--max-bars", "3", "--poll-interval-seconds", "1", "--max-polls", "10", "--launch-stagger-seconds", "0",
    ]
    run_fleet_supervise_command(parse_args(base_args))
    capsys.readouterr()

    (tmp_path / "_supervisor" / "graceful_shutdown.json").unlink()

    run_fleet_supervise_command(parse_args(base_args))
    output = capsys.readouterr().out
    assert "PREVIOUS SUPERVISOR SESSION: ABNORMAL_TERMINATION" in output


def test_run_fleet_supervise_command_requires_symbols_or_watchlist_file(tmp_path):
    args = parse_args(["fleet-supervise", "--runtime-dir", str(tmp_path)])
    with pytest.raises(SystemExit):
        run_fleet_supervise_command(args)


def test_fleet_summary_subcommand_is_recognized_without_the_analyze_default_prefix():
    """Same regression class as fleet-supervise's own equivalent test --
    a new subparser silently gets misrouted through the implicit
    `analyze` default unless its name is also added to the module-level
    _KNOWN_COMMANDS tuple."""
    args = parse_args(["fleet-summary", "--symbols", "AAPL", "--runtime-dir", "runtime"])
    assert args.command == "fleet-summary"


def test_run_fleet_summary_command_reports_a_real_fleet_supervise_session(tmp_path, capsys):
    """Real end-to-end: runs an actual two-symbol fleet-supervise
    session (mock source), then proves fleet-summary reads the SAME
    runtime-dir back correctly, including a THIRD symbol that never
    ran (must appear with all-zero counts and a [missing log/db] flag,
    not be silently dropped or raise)."""
    supervise_args = parse_args([
        "fleet-supervise", "--symbols", "AAPL,MSFT", "--runtime-dir", str(tmp_path),
        "--source", "mock", "--max-bars", "3", "--poll-interval-seconds", "1", "--max-polls", "10", "--launch-stagger-seconds", "0",
    ])
    run_fleet_supervise_command(supervise_args)
    capsys.readouterr()  # discard fleet-supervise's own output

    summary_args = parse_args(["fleet-summary", "--symbols", "AAPL,MSFT,RELIANCE.NS", "--runtime-dir", str(tmp_path)])
    run_fleet_summary_command(summary_args)
    output = capsys.readouterr().out

    assert "FLEET SUMMARY: runtime-dir=" in output
    assert "3 symbol(s)" in output
    assert "AAPL" in output
    assert "MSFT" in output
    assert "RELIANCE.NS" in output
    assert "[missing log/db]" in output
    assert "TOTAL" in output


def test_run_fleet_summary_command_requires_symbols_or_watchlist_file(tmp_path):
    args = parse_args(["fleet-summary", "--runtime-dir", str(tmp_path)])
    with pytest.raises(SystemExit):
        run_fleet_summary_command(args)


@pytestmark_paper_live
def test_run_paper_live_command_records_predictions_end_to_end(tmp_path, capsys):
    """Autonomous hardening cycle 36 -- proves the new --record-predictions
    wiring through the REAL CLI entrypoint (parse_args -> run_paper_live_
    command -> _run_paper_live_loop -> live/prediction_recorder.py), not
    just live/prediction_recorder.py's own unit tests. Real cached AAPL
    data, the real strategy, the real risk engine, the real
    PredictionStore -- only network access is faked (cached data)."""
    from predictions.store import PredictionStore

    predictions_db = tmp_path / "predictions.db"
    args = parse_args([
        "paper-live", "--symbol", "AAPL", "--interval", "1d", "--period", "1y",
        "--db", str(tmp_path / "paper.db"), "--state-db", str(tmp_path / "state.db"),
        "--max-bars", "70", "--auto-approve", "--no-ai-explanation", "--freshness-multiplier", "1000000",
        "--record-predictions", "--predictions-db", str(predictions_db), "--prediction-horizon-bars", "15",
    ])
    run_paper_live_command(args)
    output = capsys.readouterr().out
    assert f"PREDICTIONS: recording to {predictions_db}" in output

    store = PredictionStore(predictions_db)
    recorded = store.list_predictions()
    store.close()
    assert len(recorded) >= 1, "at least one BUY signal over 70 real AAPL bars must have been recorded as a prediction"
    for prediction in recorded:
        assert prediction.symbol == "AAPL"
        assert prediction.horizon_bars == 15
        assert prediction.interval == "1d"
        assert prediction.risk_decision is not None  # a real, freshly-computed RiskEngine snapshot
        assert prediction.stop_price < prediction.entry_price < prediction.target_price


@pytestmark_paper_live
def test_run_paper_live_command_without_the_flag_never_touches_predictions_db(tmp_path, capsys):
    """Control case: --record-predictions is explicit opt-in -- omitting
    it must leave existing paper-live behavior byte-for-byte unaffected,
    including never creating a predictions.db file at all."""
    predictions_db = tmp_path / "predictions.db"
    args = parse_args([
        "paper-live", "--symbol", "AAPL", "--interval", "1d", "--period", "1y",
        "--db", str(tmp_path / "paper.db"), "--state-db", str(tmp_path / "state.db"),
        "--max-bars", "70", "--auto-approve", "--no-ai-explanation", "--freshness-multiplier", "1000000",
    ])
    run_paper_live_command(args)
    output = capsys.readouterr().out
    assert "PREDICTIONS:" not in output
    assert not predictions_db.exists()


@pytestmark_paper_live
def test_run_paper_live_command_auto_evaluates_predictions_periodically_end_to_end(tmp_path, capsys):
    """Real-time strategy validation mission, Phase C -- proves predictions
    recorded during a paper-live run get resolved WITHOUT a separate
    `python main.py evaluate` invocation, through the real CLI entrypoint
    (--evaluate-every-n-bars, default 20). Real cached AAPL data end to
    end; only network access is faked (cached data), matching every other
    test in this file gated on pytestmark_paper_live."""
    from predictions.store import PredictionStore

    predictions_db = tmp_path / "predictions.db"
    args = parse_args([
        "paper-live", "--symbol", "AAPL", "--interval", "1d", "--period", "1y",
        "--db", str(tmp_path / "paper.db"), "--state-db", str(tmp_path / "state.db"),
        "--max-bars", "70", "--auto-approve", "--no-ai-explanation", "--freshness-multiplier", "1000000",
        "--record-predictions", "--predictions-db", str(predictions_db), "--prediction-horizon-bars", "15",
        "--evaluate-every-n-bars", "20",
    ])
    run_paper_live_command(args)
    output = capsys.readouterr().out
    assert "PREDICTIONS: auto-evaluating every 20 bars." in output

    store = PredictionStore(predictions_db)
    recorded = store.list_predictions()
    all_evaluations = store.list_all_evaluations()
    store.close()
    assert len(recorded) >= 1
    assert len(all_evaluations) >= 1, "at least one automatic evaluation must have been persisted without a separate `evaluate` invocation"


@pytestmark_paper_live
def test_run_paper_live_command_evaluate_every_n_bars_zero_disables_auto_evaluation(tmp_path, capsys):
    """--evaluate-every-n-bars 0 is the documented opt-out -- predictions
    are still recorded, but never automatically evaluated."""
    from predictions.store import PredictionStore

    predictions_db = tmp_path / "predictions.db"
    args = parse_args([
        "paper-live", "--symbol", "AAPL", "--interval", "1d", "--period", "1y",
        "--db", str(tmp_path / "paper.db"), "--state-db", str(tmp_path / "state.db"),
        "--max-bars", "70", "--auto-approve", "--no-ai-explanation", "--freshness-multiplier", "1000000",
        "--record-predictions", "--predictions-db", str(predictions_db),
        "--evaluate-every-n-bars", "0",
    ])
    run_paper_live_command(args)
    output = capsys.readouterr().out
    assert "auto-evaluating" not in output
    assert "auto-evaluated" not in output

    store = PredictionStore(predictions_db)
    recorded = store.list_predictions()
    all_evaluations = store.list_all_evaluations()
    store.close()
    assert len(recorded) >= 1, "recording itself must be unaffected by disabling auto-evaluation"
    assert all_evaluations == []


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


@pytestmark_paper_live
def test_run_paper_live_command_closes_the_market_data_source_on_normal_completion(tmp_path, monkeypatch):
    """Phase 17 lifecycle fix (found via code review, no live network
    involved): source.close() was previously never called on ANY exit
    path, including normal completion -- for --source dhan this left a
    real WebSocket connection open, relying entirely on daemon-thread/
    process teardown rather than a deliberate close()."""
    from live.mock_source import MockMarketDataSource

    close_calls = []
    original_close = MockMarketDataSource.close

    def _tracked_close(self):
        close_calls.append(self)
        original_close(self)

    monkeypatch.setattr(MockMarketDataSource, "close", _tracked_close)

    args = parse_args([
        "paper-live", "--symbol", "AAPL", "--interval", "1d", "--period", "1y",
        "--db", str(tmp_path / "paper.db"), "--state-db", str(tmp_path / "state.db"),
        "--max-bars", "5", "--auto-approve", "--no-ai-explanation", "--freshness-multiplier", "1000000",
    ])
    run_paper_live_command(args)
    assert len(close_calls) == 1


@pytestmark_paper_live
def test_run_paper_live_command_closes_the_market_data_source_on_keyboard_interrupt(tmp_path, monkeypatch):
    """Same fix, the other exit path: Ctrl+C must not leave the market
    data source open, and must not crash with a raw traceback."""
    from live.mock_source import MockMarketDataSource
    from live.pipeline import LiveSimPipeline

    close_calls = []
    original_close = MockMarketDataSource.close

    def _tracked_close(self):
        close_calls.append(self)
        original_close(self)

    def _raising_process_next(self):
        raise KeyboardInterrupt()

    monkeypatch.setattr(MockMarketDataSource, "close", _tracked_close)
    monkeypatch.setattr(LiveSimPipeline, "process_next", _raising_process_next)

    args = parse_args([
        "paper-live", "--symbol", "AAPL", "--interval", "1d", "--period", "1y",
        "--db", str(tmp_path / "paper.db"), "--state-db", str(tmp_path / "state.db"),
        "--auto-approve", "--no-ai-explanation",
    ])
    run_paper_live_command(args)  # must not raise -- KeyboardInterrupt is caught and handled cleanly
    assert len(close_calls) == 1


# --- Phase 15: --source dhan --------------------------------------------------


def test_paper_live_source_dhan_fails_cleanly_without_credentials(monkeypatch, tmp_path):
    """No DhanCredentialsMissingError traceback should ever reach the
    operator -- run_paper_live_command must raise a controlled error that
    main()'s own exception handler already knows how to report cleanly."""
    from live.dhan.config import DhanCredentialsMissingError

    monkeypatch.delenv("DHAN_CLIENT_ID", raising=False)
    monkeypatch.delenv("DHAN_ACCESS_TOKEN", raising=False)
    args = parse_args([
        "paper-live", "--symbol", "RELIANCE.NS", "--source", "dhan",
        "--db", str(tmp_path / "paper.db"), "--state-db", str(tmp_path / "state.db"),
    ])
    with pytest.raises(DhanCredentialsMissingError):
        run_paper_live_command(args)


def test_build_market_data_source_mock_is_labeled_simulated():
    from main import _build_market_data_source

    args = parse_args(["paper-live", "--symbol", "AAPL", "--interval", "1d", "--period", "1y"])
    source, source_label, status_label = _build_market_data_source(args)
    assert "MOCK" in source_label
    assert status_label == "SIMULATED"


def test_build_market_data_source_dhan_is_labeled_live(monkeypatch):
    """Wires real DhanMarketDataSource construction using fake credentials
    and a fake DhanInstrumentMap.download() -- no real network call and no
    dependency on any local cache file's presence."""
    import io

    import pandas as pd

    from live.dhan.instruments import DhanInstrumentMap

    fixture_csv = (
        "SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_INSTRUMENT_NAME,SEM_EXPIRY_CODE,SEM_TRADING_SYMBOL,"
        "SEM_LOT_UNITS,SEM_CUSTOM_SYMBOL,SEM_EXPIRY_DATE,SEM_STRIKE_PRICE,SEM_OPTION_TYPE,SEM_TICK_SIZE,"
        "SEM_EXPIRY_FLAG,SEM_EXCH_INSTRUMENT_TYPE,SEM_SERIES,SM_SYMBOL_NAME\n"
        "NSE,E,2885,EQUITY,0,RELIANCE,1.0,Reliance Industries,,,,10.0000,NA,ES,EQ,RELIANCE INDUSTRIES LTD\n"
    )
    fake_map = DhanInstrumentMap(pd.read_csv(io.StringIO(fixture_csv), dtype=str, keep_default_na=False))
    monkeypatch.setattr(DhanInstrumentMap, "download", classmethod(lambda cls, *a, **kw: fake_map))
    monkeypatch.setenv("DHAN_CLIENT_ID", "1000000001")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "fake-token-for-tests")

    from main import _build_market_data_source

    args = parse_args(["paper-live", "--symbol", "RELIANCE.NS", "--source", "dhan"])
    source, source_label, status_label = _build_market_data_source(args)
    assert "DHAN" in source_label
    assert status_label == "LIVE"


def test_hypothesis_registry_subcommand_defaults():
    args = parse_args(["hypothesis-registry"])
    assert args.command == "hypothesis-registry"
    assert args.status is None


def test_hypothesis_registry_subcommand_accepts_status_filter():
    args = parse_args(["hypothesis-registry", "--status", "SUPPORTED"])
    assert args.status == "SUPPORTED"


def test_hypothesis_registry_subcommand_rejects_an_unknown_status():
    with pytest.raises(SystemExit):
        parse_args(["hypothesis-registry", "--status", "MADE_UP"])


def test_hypothesis_registry_command_prints_every_hypothesis(capsys):
    args = parse_args(["hypothesis-registry"])
    run_hypothesis_registry_command(args)

    output = capsys.readouterr().out
    assert "H_ENTRY_001" in output
    assert "H_EXIT_001" in output
    assert "Summary:" in output


def test_hypothesis_registry_command_filters_by_status(capsys):
    args = parse_args(["hypothesis-registry", "--status", "SUPPORTED"])
    run_hypothesis_registry_command(args)

    output = capsys.readouterr().out
    assert "H_ENTRY_001" in output  # the one SUPPORTED hypothesis
    assert "H_EXIT_001" not in output  # OPEN, must be excluded
