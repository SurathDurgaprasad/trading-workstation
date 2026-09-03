import pytest

from main import parse_args, run_decide_command, run_paper_live_command, run_research_command, run_scan_command
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
    assert args.source == "mock"  # real Dhan connection is opt-in, never the default
    assert args.refresh_instrument_map is False


def test_paper_live_source_dhan_flag():
    args = parse_args(["paper-live", "--symbol", "RELIANCE.NS", "--source", "dhan", "--refresh-instrument-map"])
    assert args.source == "dhan"
    assert args.refresh_instrument_map is True


def test_paper_live_source_rejects_unknown_values():
    with pytest.raises(SystemExit):
        parse_args(["paper-live", "--symbol", "RELIANCE.NS", "--source", "zerodha"])


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
