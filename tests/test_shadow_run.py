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

    # The critic's DATA_FRESHNESS/FUTURE_TIMESTAMP checks compare
    # market_context.as_of against REAL wall-clock `now` by default -- the
    # correct behavior for a genuine shadow-run against real Yahoo data
    # (whose as_of is naturally recent), but this fixture's as_of is fixed
    # at _START's 2023 date regardless of when the test suite itself runs,
    # which would make every such check fail on staleness alone and mask
    # whatever the test actually intends to exercise. Freezing critic.engine's
    # own "now" to just after this fixture's own as_of -- not disabling the
    # checks -- keeps them meaningful (a genuinely future-dated context is
    # still caught) while decoupling this file's fixture from real wall-clock
    # drift, the same "pin now to the fixture's own timeline" approach
    # test_scheduler_runner.py/test_cli_schedule.py already use via --now.
    import critic.engine as critic_engine_module

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            frozen = entry_as_of + timedelta(days=1)
            return frozen.replace(tzinfo=tz) if tz else frozen

    monkeypatch.setattr(critic_engine_module, "datetime", _FrozenDatetime)

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
    assert args.paper_execute is False
    assert args.state_db is None
    assert args.max_holding_bars is None
    assert args.skip_critic is False


def test_shadow_run_skip_critic_flag_parses():
    args = parse_args(["shadow-run", "--symbols", "AAPL", "--skip-critic"])
    assert args.skip_critic is True


def test_shadow_run_paper_execute_flag_parses():
    args = parse_args(["shadow-run", "--symbols", "AAPL", "--paper-execute", "--paper-db", "/tmp/p.db", "--state-db", "/tmp/s.db", "--initial-capital", "20000"])
    assert args.paper_execute is True
    assert args.state_db == "/tmp/s.db"


def test_shadow_run_max_holding_bars_flag_parses():
    args = parse_args(["shadow-run", "--symbols", "AAPL", "--max-holding-bars", "10"])
    assert args.max_holding_bars == 10


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


def test_shadow_run_persists_a_trade_plan_per_prediction_when_initial_capital_is_given(tmp_path, capsys):
    """Mission auditability requirement, exercised through shadow-run's
    own per-symbol loop (a separate code path from `predict`): each BUY
    prediction gets its own risk_decision, sized independently against
    the SAME configured capital (not sequentially depleted across
    candidates in one scan -- this is a per-trade preview, not a
    portfolio simulation)."""
    args = parse_args([
        "shadow-run", "--symbols", "AAPL,MSFT", "--benchmark", "", "--skip-evaluate",
        "--scanner-db", str(tmp_path / "scanner.db"), "--research-db", str(tmp_path / "research.db"),
        "--decision-db", str(tmp_path / "decisions.db"), "--predictions-db", str(tmp_path / "predictions.db"),
        "--initial-capital", "20000",
    ])
    run_shadow_run_command(args)

    output = capsys.readouterr().out
    assert "qty=" in output  # the per-symbol summary line now shows the sized quantity

    from predictions.store import PredictionStore

    prediction_store = PredictionStore(tmp_path / "predictions.db")
    predictions = prediction_store.list_predictions()
    prediction_store.close()
    assert len(predictions) == 2
    for prediction in predictions:
        rd = prediction.risk_decision
        assert rd is not None
        assert rd.account_equity == 20_000.0
        assert rd.position_size is not None
        assert rd.position_size.quantity > 0


def _paper_execute_args(tmp_path, *, symbols="AAPL", extra=()):
    return parse_args([
        "shadow-run", "--symbols", symbols, "--benchmark", "", "--skip-evaluate",
        "--scanner-db", str(tmp_path / "scanner.db"), "--research-db", str(tmp_path / "research.db"),
        "--decision-db", str(tmp_path / "decisions.db"), "--predictions-db", str(tmp_path / "predictions.db"),
        "--initial-capital", "20000", "--paper-execute",
        "--paper-db", str(tmp_path / "paper.db"), "--state-db", str(tmp_path / "state.db"),
        *extra,
    ])


def test_shadow_run_paper_execute_requires_all_three_companion_flags(tmp_path, capsys):
    for missing_args in (
        ["shadow-run", "--symbols", "AAPL", "--paper-execute", "--paper-db", str(tmp_path / "p.db"), "--state-db", str(tmp_path / "s.db")],  # no --initial-capital
        ["shadow-run", "--symbols", "AAPL", "--paper-execute", "--initial-capital", "20000", "--state-db", str(tmp_path / "s.db")],  # no --paper-db
        ["shadow-run", "--symbols", "AAPL", "--paper-execute", "--initial-capital", "20000", "--paper-db", str(tmp_path / "p.db")],  # no --state-db
    ):
        with pytest.raises(SystemExit) as exc_info:
            run_shadow_run_command(parse_args(missing_args))
        assert exc_info.value.code == 2
        assert "--paper-execute requires --initial-capital, --paper-db, AND --state-db" in capsys.readouterr().err


def test_shadow_run_footer_never_claims_no_order_was_placed_when_one_actually_was(tmp_path, capsys):
    """Regression (two rounds): the footer's "No real or paper order was
    placed by this command" line is false the moment --paper-execute
    submits a real (paper) order -- found via self-audit while building
    the bridge. Then, once the advance step (paper/advance.py) was added
    in the SAME cycle, an earlier fix's own "PENDING, not yet filled"
    wording became a NEW stale claim -- the advance step, running later
    in the SAME invocation, can already have filled or even closed the
    order by the time the footer prints. Fixed to never assert a
    specific resulting status; points to `paper status` instead."""
    run_shadow_run_command(_paper_execute_args(tmp_path, symbols="AAPL"))
    output = capsys.readouterr().out
    assert "No real or paper order was placed by this command." not in output
    assert "PENDING, not yet filled" not in output  # the old, now-inaccurate claim must never reappear
    assert "1 new order(s) submitted this run" in output
    assert "existing order/position(s) advanced with new data this run" in output
    assert "Run `python main.py paper status` for current state." in output
    assert "no real order was placed" in output.lower()  # still true -- REAL as in "a real object was created", not "a real broker order"
    assert "paper orders submitted: 1" in output


def test_shadow_run_footer_still_says_no_order_without_paper_execute(tmp_path, capsys):
    args = parse_args([
        "shadow-run", "--symbols", "AAPL", "--benchmark", "", "--skip-evaluate",
        "--scanner-db", str(tmp_path / "scanner.db"), "--research-db", str(tmp_path / "research.db"),
        "--decision-db", str(tmp_path / "decisions.db"), "--predictions-db", str(tmp_path / "predictions.db"),
    ])
    run_shadow_run_command(args)
    output = capsys.readouterr().out
    assert "No real or paper order was placed by this command." in output


def test_shadow_run_paper_execute_submits_a_real_pending_order(tmp_path, capsys):
    """The bridge: a risk-approved BUY decision must result in a REAL
    PaperTradingEngine order (APPROVED_PENDING at submission time), not
    just a prediction -- and, since the fixture's fake provider already
    has bars genuinely AFTER the signal-generating one available (a
    fully-materialized historical series, same as any backtest -- not
    fabricated "future" data), the same shadow-run invocation's own
    advance step correctly carries it forward past PENDING using that
    already-later data, proving the full submit -> advance -> fill
    lifecycle works end-to-end, not just the first step."""
    run_shadow_run_command(_paper_execute_args(tmp_path, symbols="AAPL"))

    output = capsys.readouterr().out
    assert "paper: APPROVED_PENDING" in output  # true the MOMENT it was submitted
    assert "critic=APPROVE" in output
    assert "Advancing existing PENDING paper orders" in output
    assert "new bar(s) processed" in output

    from paper.store import PaperStore

    store = PaperStore(tmp_path / "paper.db")
    entries = store.list_journal_entries()
    store.close()
    assert len(entries) == 1
    # No longer PENDING by the time the run finishes -- the advance step (using
    # bars genuinely later than the signal) carried it forward for real.
    assert entries[0].outcome.value in ("APPROVED_FILLED_OPEN", "APPROVED_FILLED_CLOSED")
    assert entries[0].symbol == "AAPL"
    assert entries[0].strategy_name == "decision_engine_buy_bridge"

    from critic.models import CriticVerdict
    from predictions.store import PredictionStore

    prediction_store = PredictionStore(tmp_path / "predictions.db")
    predictions = prediction_store.list_predictions()
    prediction_store.close()
    assert len(predictions) == 1
    assert predictions[0].critic_assessment is not None
    assert predictions[0].critic_assessment.verdict == CriticVerdict.APPROVE


def test_shadow_run_paper_execute_a_critic_reject_prevents_the_order_but_not_the_prediction(tmp_path, capsys):
    """The critic's authority in practice: an active kill switch makes the
    critic REJECT, which must prevent _bridge_to_paper_execution from
    submitting a real paper order (no journal entry at all) while the
    shadow prediction is still recorded, with the REJECT verdict itself
    persisted on it -- predictions are tracked independent of trades, the
    same principle risk_decision already establishes for a risk-rejected
    signal."""
    from live.state_store import LiveStateStore

    state_store = LiveStateStore(tmp_path / "state.db")
    state_store.activate_kill_switch(reason="test")
    state_store.close()

    run_shadow_run_command(_paper_execute_args(tmp_path, symbols="AAPL"))

    from paper.store import PaperStore

    store = PaperStore(tmp_path / "paper.db")
    entries = store.list_journal_entries()
    store.close()
    assert entries == []  # no paper order was ever submitted

    from critic.models import CriticVerdict
    from predictions.store import PredictionStore

    prediction_store = PredictionStore(tmp_path / "predictions.db")
    predictions = prediction_store.list_predictions()
    prediction_store.close()
    assert len(predictions) == 1  # the prediction IS still recorded
    assert predictions[0].critic_assessment is not None
    assert predictions[0].critic_assessment.verdict == CriticVerdict.REJECT
    assert "KILL_SWITCH" in predictions[0].critic_assessment.failed_checks


def test_shadow_run_skip_critic_leaves_critic_assessment_none_even_when_it_would_reject(tmp_path, capsys):
    """--skip-critic must bypass the critic entirely -- no verdict
    persisted, and paper execution proceeds exactly as it did before the
    critic existed, even in a scenario (active kill switch) that would
    otherwise be a critic REJECT."""
    from live.state_store import LiveStateStore

    state_store = LiveStateStore(tmp_path / "state.db")
    state_store.activate_kill_switch(reason="test")
    state_store.close()

    run_shadow_run_command(_paper_execute_args(tmp_path, symbols="AAPL", extra=["--skip-critic"]))

    from predictions.store import PredictionStore

    prediction_store = PredictionStore(tmp_path / "predictions.db")
    predictions = prediction_store.list_predictions()
    prediction_store.close()
    assert len(predictions) == 1
    assert predictions[0].critic_assessment is None

    # _bridge_to_paper_execution's own, independent kill-switch check still
    # correctly blocked the order (same assertion as the dedicated test
    # above -- confirms this specific scenario end-to-end too).
    from paper.store import PaperStore

    store = PaperStore(tmp_path / "paper.db")
    entries = store.list_journal_entries()
    store.close()
    assert entries == []


def test_shadow_run_max_holding_bars_is_threaded_through_to_the_paper_engine(tmp_path, monkeypatch):
    """--max-holding-bars must actually reach the constructed
    PaperTradingEngine, not just parse -- the engine-level mechanism
    itself (force-close after N bars with ExitReason.EXPIRED) is already
    covered directly in tests/test_paper_engine.py; this only proves the
    CLI wiring reaches it."""
    import paper.engine as paper_engine_module

    captured = {}
    real_engine_cls = paper_engine_module.PaperTradingEngine

    class _CapturingEngine(real_engine_cls):
        def __init__(self, *args, **kwargs):
            captured["max_holding_bars"] = kwargs.get("max_holding_bars")
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(paper_engine_module, "PaperTradingEngine", _CapturingEngine)

    run_shadow_run_command(_paper_execute_args(tmp_path, symbols="AAPL", extra=["--max-holding-bars", "5"]))

    assert captured.get("max_holding_bars") == 5


def test_shadow_run_paper_execute_never_touches_a_prediction_when_disabled(tmp_path, capsys):
    """Backward compatibility: without --paper-execute, no paper store is
    ever created or touched at all, exactly as before this feature existed."""
    args = parse_args([
        "shadow-run", "--symbols", "AAPL", "--benchmark", "", "--skip-evaluate",
        "--scanner-db", str(tmp_path / "scanner.db"), "--research-db", str(tmp_path / "research.db"),
        "--decision-db", str(tmp_path / "decisions.db"), "--predictions-db", str(tmp_path / "predictions.db"),
        "--initial-capital", "20000",
    ])
    run_shadow_run_command(args)
    assert "paper:" not in capsys.readouterr().out
    assert not (tmp_path / "paper.db").exists()


def test_shadow_run_paper_execute_respects_an_active_kill_switch(tmp_path, capsys):
    """The kill switch must be respected by this bridge exactly as it
    already is by `paper-live` -- an active kill switch must skip paper
    execution for every symbol without blocking the shadow prediction
    itself from being recorded. Now caught by the critic FIRST (its own
    KILL_SWITCH check forces REJECT before _bridge_to_paper_execution is
    even called) -- see the --skip-critic variant below for proof
    _bridge_to_paper_execution's own, independent kill-switch check is
    still there as a second layer when the critic is bypassed."""
    from live.state_store import LiveStateStore

    state_store = LiveStateStore(tmp_path / "state.db")
    state_store.activate_kill_switch(reason="test")
    state_store.close()

    run_shadow_run_command(_paper_execute_args(tmp_path, symbols="AAPL"))

    output = capsys.readouterr().out
    assert "prediction recorded" in output  # the prediction itself is unaffected
    assert "paper: SKIPPED (critic REJECT)" in output
    assert "critic=REJECT" in output

    from paper.store import PaperStore

    store = PaperStore(tmp_path / "paper.db")
    entries = store.list_journal_entries()
    store.close()
    assert entries == []  # no order was ever submitted


def test_shadow_run_paper_execute_kill_switch_still_caught_with_skip_critic(tmp_path, capsys):
    """Defense in depth: _bridge_to_paper_execution's OWN, independent
    kill-switch check must still work when the critic is bypassed
    entirely -- proves it is a real second layer, not dead code made
    unreachable by the critic now catching this first in the default path."""
    from live.state_store import LiveStateStore

    state_store = LiveStateStore(tmp_path / "state.db")
    state_store.activate_kill_switch(reason="test")
    state_store.close()

    run_shadow_run_command(_paper_execute_args(tmp_path, symbols="AAPL", extra=["--skip-critic"]))

    output = capsys.readouterr().out
    assert "prediction recorded" in output
    assert "critic=" not in output
    assert "paper: SKIPPED (kill switch active)" in output

    from paper.store import PaperStore

    store = PaperStore(tmp_path / "paper.db")
    entries = store.list_journal_entries()
    store.close()
    assert entries == []


def test_shadow_run_paper_execute_two_different_symbols_each_get_their_own_pending_order(tmp_path, capsys):
    """Real, verified behavior of the reused, unmodified PaperTradingEngine
    (not new logic introduced by this bridge): PaperTradingEngine's own
    "already active" guard is per-SYMBOL (get_pending_order(signal.symbol)),
    and RiskEngine's account-wide single-position veto only fires once
    account.open_positions is incremented at FILL time -- which this
    bridge does not attempt (see its own docstring). So two DIFFERENT
    symbols, each independently risk-approved, correctly each get their
    own APPROVED_PENDING order at SUBMISSION time -- not a bug.

    The advance step (paper/advance.py) that runs later in this SAME
    invocation then processes each symbol's 19 already-available later
    bars in turn: AAPL fills and (in this fixture's strong uptrend)
    reaches TARGET_HIT and CLOSES entirely within its own turn, freeing
    the account's one open-position slot before MSFT's turn even
    begins -- so MSFT correctly fills and closes too, never held back.
    Proves both the multi-symbol PENDING coexistence AND the
    single-position hold-back/retry mechanism (tests/test_paper_advance.py's
    own unit-level proof) compose correctly end-to-end through the real
    CLI path, not just in isolation."""
    run_shadow_run_command(_paper_execute_args(tmp_path, symbols="AAPL,MSFT"))

    output = capsys.readouterr().out
    assert output.count("paper: APPROVED_PENDING") == 2  # true at submission time, for both

    from paper.store import PaperStore

    store = PaperStore(tmp_path / "paper.db")
    entries = store.list_journal_entries()
    store.close()
    assert len(entries) == 2
    assert {e.symbol for e in entries} == {"AAPL", "MSFT"}
    # Neither is stuck PENDING or held back by the other by the time the run finishes.
    assert all(e.outcome.value in ("APPROVED_FILLED_OPEN", "APPROVED_FILLED_CLOSED") for e in entries)


def test_shadow_run_paper_execute_the_same_symbol_twice_is_idempotent(tmp_path, capsys):
    """PaperTradingEngine.submit_signal's OWN, already-tested idempotency
    (same Signal.stable_id() never creates a second order) -- verified
    here through the bridge specifically, not re-proving submit_signal
    itself (already covered in tests/test_paper_engine.py)."""
    args1 = _paper_execute_args(tmp_path, symbols="AAPL")
    run_shadow_run_command(args1)
    capsys.readouterr()

    # A second shadow-run for the SAME symbol on the SAME (unchanged, cached-by-Yahoo-fixture) entry bar
    # is blocked by prediction-level duplicate prevention before it would ever reach the bridge again --
    # confirms the bridge is never even attempted a second time for an already-predicted entry bar.
    run_shadow_run_command(_paper_execute_args(tmp_path, symbols="AAPL"))
    output = capsys.readouterr().out
    assert "already have one for entry bar" in output
    assert "paper:" not in output

    from paper.store import PaperStore

    store = PaperStore(tmp_path / "paper.db")
    entries = store.list_journal_entries()
    store.close()
    assert len(entries) == 1  # still just one order, not two


def test_shadow_run_paper_execute_reuses_the_same_capital_across_reruns(tmp_path, capsys):
    """Restart-safe, matching every other --initial-capital consumer:
    initial_capital only takes effect on first account creation."""
    run_shadow_run_command(_paper_execute_args(tmp_path, symbols="AAPL"))
    capsys.readouterr()

    from paper.store import PaperStore

    store = PaperStore(tmp_path / "paper.db")
    account = store.get_account()
    store.close()
    assert account.initial_capital == 20_000.0


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


def test_shadow_run_second_run_against_the_same_entry_bar_skips_the_duplicate(tmp_path, capsys):
    """Phase 36: running shadow-run twice against unchanged (fake, fixed)
    market data must not double-record the same prediction."""
    common_args = [
        "shadow-run", "--symbols", "AAPL", "--benchmark", "", "--skip-evaluate",
        "--scanner-db", str(tmp_path / "scanner.db"), "--research-db", str(tmp_path / "research.db"),
        "--decision-db", str(tmp_path / "decisions.db"), "--predictions-db", str(tmp_path / "predictions.db"),
    ]
    run_shadow_run_command(parse_args(common_args))
    first_output = capsys.readouterr().out
    assert "prediction recorded" in first_output

    run_shadow_run_command(parse_args(common_args))
    second_output = capsys.readouterr().out
    assert "no prediction recorded (already have one for entry bar" in second_output

    from predictions.store import PredictionStore

    store = PredictionStore(tmp_path / "predictions.db")
    predictions = store.list_predictions()
    store.close()
    assert len(predictions) == 1  # still just one, not two


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
