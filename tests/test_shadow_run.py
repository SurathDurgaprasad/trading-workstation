"""Phase 27 -- end-to-end shadow trading validation. `shadow-run` is pure
orchestration over already-tested library functions (market_intelligence.
scanner.run_scan, research.summarizer.build_research_report, decision_engine.
engine.make_decision, risk.sizing.build_signal_for_buy, predictions.tracker.*),
so these tests exercise the WIRING (does each stage's output correctly feed
the next, does one symbol's failure leave the rest of the run intact, are
scan/research/decision/prediction stores all correctly persisted) rather than
re-proving math each underlying module's own test suite already covers.

No real network, Ollama, or cache-file write anywhere in this file:
CachedMarketDataProvider is replaced with an identity pass-through, the
Yahoo-backed provider factory and research providers are replaced with
fakes, and market.context.get_market_context is replaced directly (the
same pattern tests/test_cli.py's own size/predict end-to-end tests use).
`--with-ai` is never passed, so no LLM call is attempted anywhere here
either.
"""

from datetime import datetime, timedelta, timezone

import pytest

from main import parse_args, run_shadow_run_command
from market.context import get_market_context as _real_get_market_context
from market.data_provider import OHLCV, MarketDataError, OHLCVBar

_START = datetime(2023, 1, 2)


def _uptrend_bars(n: int = 100, start: float = 100.0, step: float = 2.0) -> list[OHLCVBar]:
    bars = []
    for i in range(n):
        close = start + step * i
        bars.append(OHLCVBar(
            timestamp=_START + timedelta(days=i), open=close, high=close * 1.001, low=close * 0.999,
            close=close, volume=100_000.0,
        ))
    return bars


class _FakeMarketDataProvider:
    """Serves the SAME uptrend series for any symbol -- used for both the
    scanner's historical fetch and evaluate_prediction's post-entry check."""

    def __init__(self, bars: list[OHLCVBar]):
        self._bars = bars

    def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
        return OHLCV(symbol=symbol, interval=interval, bars=self._bars)


class _FakeNewsProvider:
    def fetch_news(self, symbol, *, limit=10):
        return []


class _FakeSectorProvider:
    def fetch_sector_info(self, symbol):
        from research.models import SectorInfo

        return SectorInfo(symbol=symbol, sector=None, industry=None, as_of=datetime.now(timezone.utc))


def _make_fake_get_market_context(*, price: float, atr_14: float, as_of: datetime, raise_for: frozenset[str] = frozenset()):
    from market.context import MarketContext

    def _fn(symbol, **kwargs):
        if symbol in raise_for:
            raise MarketDataError(f"simulated market-context failure for {symbol}")
        return MarketContext(symbol=symbol, as_of=as_of, price=price, atr_14=atr_14)

    return _fn


@pytest.fixture(autouse=True)
def _wire_fakes(monkeypatch):
    import backtesting.cache as cache_module
    import market.data_provider as market_data_provider_module
    import research.news as research_news_module
    import research.sector as research_sector_module

    bars = _uptrend_bars()
    fake_provider = _FakeMarketDataProvider(bars)

    monkeypatch.setattr(market_data_provider_module, "get_market_data_provider", lambda: fake_provider)
    monkeypatch.setattr(cache_module, "CachedMarketDataProvider", lambda inner: inner)
    monkeypatch.setattr(research_news_module, "YahooNewsProvider", _FakeNewsProvider)
    monkeypatch.setattr(research_sector_module, "YahooSectorInfoProvider", _FakeSectorProvider)

    # Bar 80's close = 100 + 80*2 = 260; 19 bars remain after it in the
    # 100-bar series, enough for the default 20-bar horizon to observe a
    # resolution (the series keeps rising at the same rate).
    entry_as_of = _START + timedelta(days=80)
    monkeypatch.setattr("market.context.get_market_context", _make_fake_get_market_context(price=260.0, atr_14=5.0, as_of=entry_as_of))

    yield {"bars": bars, "entry_as_of": entry_as_of}


# --- arg parsing --------------------------------------------------------------


def test_shadow_run_subcommand_defaults():
    args = parse_args(["shadow-run", "--symbols", "AAPL,MSFT"])
    assert args.command == "shadow-run"
    assert args.symbols == "AAPL,MSFT"
    assert args.period == "1y"
    assert args.interval == "1d"
    assert args.benchmark == "^NSEI"
    assert args.with_ai is False
    assert args.skip_evaluate is False


def test_shadow_run_requires_symbols_or_watchlist_file():
    args = parse_args(["shadow-run"])
    with pytest.raises(SystemExit):
        run_shadow_run_command(args)


# --- end-to-end wiring ----------------------------------------------------------


def test_shadow_run_end_to_end_with_skip_evaluate_persists_every_stage(tmp_path, capsys):
    args = parse_args([
        "shadow-run", "--symbols", "AAPL,MSFT", "--benchmark", "", "--skip-evaluate",
        "--scanner-db", str(tmp_path / "scanner.db"), "--research-db", str(tmp_path / "research.db"),
        "--decision-db", str(tmp_path / "decisions.db"), "--predictions-db", str(tmp_path / "predictions.db"),
    ])
    run_shadow_run_command(args)

    output = capsys.readouterr().out
    assert "SHADOW RUN -- FULL PIPELINE, ONE PASS -- NOT AN ORDER" in output
    assert "[1/4] Scan complete: 2 candidates" in output
    assert "AAPL" in output and "MSFT" in output
    assert "decision=BUY" in output
    assert "prediction recorded" in output
    assert "Evaluation skipped (--skip-evaluate)." in output
    assert "No real or paper order was placed by this command." in output

    from decision_engine.store import DecisionStore
    from market_intelligence.store import ScanHistoryStore
    from predictions.store import PredictionStore
    from research.store import ResearchStore

    scan_store = ScanHistoryStore(tmp_path / "scanner.db")
    assert scan_store.latest_report() is not None
    scan_store.close()

    research_store = ResearchStore(tmp_path / "research.db")
    assert research_store.latest_report_for_symbol("AAPL") is not None
    research_store.close()

    decision_store = DecisionStore(tmp_path / "decisions.db")
    aapl_decision = decision_store.latest_decision_for_symbol("AAPL")
    assert aapl_decision is not None
    assert aapl_decision.label.value == "BUY"
    decision_store.close()

    prediction_store = PredictionStore(tmp_path / "predictions.db")
    predictions = prediction_store.list_predictions()
    assert len(predictions) == 2
    assert {p.symbol for p in predictions} == {"AAPL", "MSFT"}
    prediction_store.close()


def test_shadow_run_full_pipeline_runs_evaluate_and_learn_without_crashing(tmp_path, capsys):
    args = parse_args([
        "shadow-run", "--symbols", "AAPL", "--benchmark", "",
        "--scanner-db", str(tmp_path / "scanner.db"), "--research-db", str(tmp_path / "research.db"),
        "--decision-db", str(tmp_path / "decisions.db"), "--predictions-db", str(tmp_path / "predictions.db"),
    ])
    run_shadow_run_command(args)

    output = capsys.readouterr().out
    assert "[3/4] Evaluating all outstanding predictions:" in output
    assert "[4/4] Learning summary" in output
    # The synthetic series keeps rising well past the recorded target -- expect a real resolution, not a crash.
    assert "TARGET_HIT" in output or "STOP_HIT" in output or "ACTIVE" in output or "EXPIRED" in output


def test_shadow_run_continues_when_one_symbols_decide_stage_fails(tmp_path, capsys, monkeypatch):
    entry_as_of = _START + timedelta(days=80)
    monkeypatch.setattr(
        "market.context.get_market_context",
        _make_fake_get_market_context(price=260.0, atr_14=5.0, as_of=entry_as_of, raise_for=frozenset({"MSFT"})),
    )

    args = parse_args([
        "shadow-run", "--symbols", "AAPL,MSFT", "--benchmark", "", "--skip-evaluate",
        "--scanner-db", str(tmp_path / "scanner.db"), "--research-db", str(tmp_path / "research.db"),
        "--decision-db", str(tmp_path / "decisions.db"), "--predictions-db", str(tmp_path / "predictions.db"),
    ])
    run_shadow_run_command(args)

    output = capsys.readouterr().out
    assert "MSFT" in output and "FAILED" in output
    assert "decision=BUY" in output  # AAPL still succeeded

    from decision_engine.store import DecisionStore

    store = DecisionStore(tmp_path / "decisions.db")
    assert store.latest_decision_for_symbol("AAPL") is not None
    assert store.latest_decision_for_symbol("MSFT") is None  # never reached decide -- failed before it
    store.close()


def test_shadow_run_prints_market_session_and_live_overlay_status(tmp_path, capsys):
    args = parse_args([
        "shadow-run", "--symbols", "AAPL", "--benchmark", "", "--skip-evaluate",
        "--scanner-db", str(tmp_path / "scanner.db"), "--research-db", str(tmp_path / "research.db"),
        "--decision-db", str(tmp_path / "decisions.db"), "--predictions-db", str(tmp_path / "predictions.db"),
    ])
    run_shadow_run_command(args)

    output = capsys.readouterr().out
    assert "Market session:" in output
    assert "Live overlay:    none -- Yahoo historical only" in output


def test_shadow_run_with_live_source_dhan_overlays_every_candidate_and_closes_the_adapter(tmp_path, capsys, monkeypatch):
    """Phase 32: --live-source dhan must build ONE adapter for the whole
    run, pass it to get_market_context for every candidate, and close it
    exactly once at the end -- no real Dhan connection anywhere here."""
    import live.dhan.config as dhan_config_module
    import live.dhan.instruments as dhan_instruments_module
    import market_data.adapters.dhan as dhan_adapter_module
    from market.context import MarketContext
    from market_data.models import InstrumentSnapshot
    from market_data.quality import SourceHealth, SourceStatus

    close_calls = {"count": 0}

    class _FakeLiveAdapter:
        def get_snapshot(self, symbol):
            bar_time = _START + timedelta(days=80)
            from market.data_provider import DataSource, DataStatus, OHLCVBar

            bar = OHLCVBar(timestamp=bar_time, open=999.0, high=999.0, low=999.0, close=999.0, volume=1.0, source=DataSource.DHAN, status=DataStatus.LIVE)
            return InstrumentSnapshot(symbol=symbol, latest_bar=bar, health=SourceHealth(status=SourceStatus.HEALTHY, last_updated=bar_time, age_seconds=1.0), as_of=bar_time)

        def close(self):
            close_calls["count"] += 1

    monkeypatch.setattr(dhan_config_module, "load_dhan_credentials", lambda: object())
    monkeypatch.setattr(dhan_instruments_module.DhanInstrumentMap, "download", classmethod(lambda cls, **kw: object()))
    monkeypatch.setattr(dhan_adapter_module, "build_dhan_adapter", lambda **kw: _FakeLiveAdapter())
    # The file's own autouse _wire_fakes fixture replaces get_market_context
    # itself (to avoid needing a real Yahoo call in every other test in this
    # file) -- THIS test specifically needs the REAL get_market_context, so
    # its live-overlay composition logic actually runs against the fake
    # Dhan adapter above. get_market_data_provider stays faked underneath it.
    monkeypatch.setattr("market.context.get_market_context", _real_get_market_context)

    args = parse_args([
        "shadow-run", "--symbols", "AAPL", "--benchmark", "", "--skip-evaluate", "--live-source", "dhan",
        "--scanner-db", str(tmp_path / "scanner.db"), "--research-db", str(tmp_path / "research.db"),
        "--decision-db", str(tmp_path / "decisions.db"), "--predictions-db", str(tmp_path / "predictions.db"),
    ])
    run_shadow_run_command(args)

    output = capsys.readouterr().out
    assert "Live overlay:    DHAN (--live-source dhan)" in output
    assert close_calls["count"] == 1

    from decision_engine.store import DecisionStore

    store = DecisionStore(tmp_path / "decisions.db")
    decision = store.latest_decision_for_symbol("AAPL")
    store.close()
    assert decision.market_context.data_source == "DHAN"
    assert decision.market_context.data_status == "LIVE"
    assert decision.market_context.price == 999.0


def test_shadow_run_records_no_predictions_for_a_declining_universe(tmp_path, capsys, monkeypatch):
    # start=300 (not 100) so a 100-bar decline at step=-2.0/day never goes
    # non-positive (OHLCVBar requires close > 0): min close = 300 - 99*2 = 102.
    declining_bars = _uptrend_bars(start=300.0, step=-2.0)
    monkeypatch.setattr("market.data_provider.get_market_data_provider", lambda: _FakeMarketDataProvider(declining_bars))
    entry_as_of = _START + timedelta(days=80)
    last_close = 300.0 + (-2.0) * 80
    monkeypatch.setattr(
        "market.context.get_market_context",
        _make_fake_get_market_context(price=last_close, atr_14=5.0, as_of=entry_as_of),
    )

    args = parse_args([
        "shadow-run", "--symbols", "AAPL", "--benchmark", "", "--skip-evaluate",
        "--scanner-db", str(tmp_path / "scanner.db"), "--research-db", str(tmp_path / "research.db"),
        "--decision-db", str(tmp_path / "decisions.db"), "--predictions-db", str(tmp_path / "predictions.db"),
    ])
    run_shadow_run_command(args)

    output = capsys.readouterr().out
    assert "prediction recorded" not in output

    from predictions.store import PredictionStore

    store = PredictionStore(tmp_path / "predictions.db")
    assert store.list_predictions() == []
    store.close()
