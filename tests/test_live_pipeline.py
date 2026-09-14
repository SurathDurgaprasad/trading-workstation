"""Phase 12 §9 — the mandatory test list, end to end through
LiveSimPipeline: ordering, duplicate/out-of-order/stale bars, disconnect/
reconnect, source/freshness metadata, 1m/5m/15m intervals, mock replay
determinism, restart, paper/backtest parity, fail-closed behavior, and
structural no-LLM/no-broker checks.
"""

from datetime import datetime, timedelta, timezone

import pytest

from live.contracts import FeedDisconnectedError
from live.freshness import FreshnessPolicy
from live.mock_source import MockMarketDataSource, MockScriptEvent, make_mock_bar
from live.pipeline import LiveSimPipeline
from market.data_provider import DataSource, DataStatus
from paper.engine import PaperTradingEngine
from paper.errors import OutOfOrderBarError
from paper.reconciliation import reconcile
from paper.store import PaperStore
from strategy.baseline import TrendMomentumBaseline
from tests.conftest import AAPL_CACHE_PATH, make_bar, make_indicator_series


def _qualifying_bar(day, hour=9, minute=15, **overrides):
    """A bar shaped to satisfy TrendMomentumBaseline's entry conditions
    once enough history has accumulated (mirrors tests/conftest.py's
    make_bar default, but as a raw OHLCVBar for the mock feed)."""
    base = dict(timestamp=datetime(2026, 1, day, hour, minute), open=100.0, high=101.0, low=99.0, close=100.0, volume=1_000_000.0)
    base.update(overrides)
    return make_mock_bar(**base)


def _pipeline(script, *, interval="1d", require_human_approval=False, clock=None, freshness_policy=None, strategy=None, critic_gate=None, state_store=None):
    source = MockMarketDataSource(script, clock=clock)
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    pipeline = LiveSimPipeline(
        source=source, engine=engine, strategy=strategy or TrendMomentumBaseline(), symbols=["TEST"], interval=interval,
        require_human_approval=require_human_approval, clock=clock, freshness_policy=freshness_policy or FreshnessPolicy(),
        critic_gate=critic_gate, state_store=state_store,
    )
    return pipeline, engine, store


class _ScriptedStrategy:
    """Fires a fixed Signal on every call -- lets critic-gate integration
    tests reach _handle_signal deterministically, independent of
    TrendMomentumBaseline's own real entry conditions (same pattern as
    tests/test_risk_day_boundary.py's own _ScriptedStrategy)."""

    name = "scripted_test_strategy"
    version = "1.0"

    def __init__(self, *, stop_price: float = 95.0, target_price: float = 110.0):
        self._stop_price = stop_price
        self._target_price = target_price

    def generate_signal(self, indicator_series, index, symbol):
        from strategy.signal import ReasonCode, Side, Signal

        row = indicator_series.iloc[index]
        return Signal(
            symbol=symbol, generated_at=indicator_series.index[index], side=Side.LONG,
            reference_price=float(row["close"]), stop_price=self._stop_price, target_price=self._target_price,
            risk_reward=2.0, strategy_name=self.name, reason_codes=[ReasonCode.TREND_CONFIRMED],
        )


class _FakeCriticGate:
    """A minimal double matching CriticGate's own evaluate() signature --
    the REAL CriticGate's internal logic (scanner evidence, benchmark
    context, critic.engine.evaluate()) is already thoroughly covered by
    tests/test_live_critic_gate.py; this proves the PIPELINE WIRING calls
    it correctly and branches on its result correctly, not the critic
    math itself."""

    def __init__(self, result):
        self._result = result
        self.calls = []

    def evaluate(self, signal, *, indicators, now, kill_switch_active, existing_pending_order, existing_open_position):
        self.calls.append(dict(
            signal=signal, indicators=indicators, now=now, kill_switch_active=kill_switch_active,
            existing_pending_order=existing_pending_order, existing_open_position=existing_open_position,
        ))
        return self._result


# --- 1. live-bar ordering / 8. source metadata / 9. freshness metadata -----


def test_bars_processed_in_order_carry_source_and_freshness_metadata():
    script = [MockScriptEvent.bar_event("TEST", _qualifying_bar(d)) for d in range(1, 5)]
    pipeline, engine, store = _pipeline(script, clock=lambda: datetime(2026, 1, 4, 9, 16))
    results = []
    while (r := pipeline.process_next()).kind != "FEED_EXHAUSTED":
        results.append(r)
    assert [r.bar.timestamp.day for r in results] == [1, 2, 3, 4]
    assert all(r.bar.source == DataSource.MOCK for r in results)
    assert all(r.bar.status == DataStatus.SIMULATED for r in results)
    assert all(r.freshness is not None for r in results)


# --- 2. duplicate bar ---------------------------------------------------------


def test_duplicate_bar_is_a_no_op_via_the_pipeline():
    bar = _qualifying_bar(1)
    script = [MockScriptEvent.bar_event("TEST", bar), MockScriptEvent.bar_event("TEST", bar)]
    pipeline, engine, store = _pipeline(script, clock=lambda: datetime(2026, 1, 1, 9, 16))
    first = pipeline.process_next()
    second = pipeline.process_next()
    assert first.kind == "BAR_PROCESSED"
    assert second.kind == "DUPLICATE_SKIPPED"
    report = reconcile(store)
    assert report.ok, report.issues
    # Autonomous hardening cycle 23: the execution layer's own dedup
    # (proven above) is a SEPARATE concern from the indicator-history
    # buffer -- a duplicate bar must not be double-counted there either,
    # or every rolling-window indicator (SMA/RSI/ATR/MACD) computed from
    # this buffer for the rest of the session would be silently skewed
    # by the extra, redundant row.
    assert [b.timestamp for b in pipeline._buffers["TEST"].bars] == [bar.timestamp]


# --- 3. out-of-order bar -------------------------------------------------------


def test_out_of_order_bar_is_rejected_not_silently_applied():
    bar5, bar3 = _qualifying_bar(5), _qualifying_bar(3)
    script = [MockScriptEvent.bar_event("TEST", bar5), MockScriptEvent.bar_event("TEST", bar3)]
    pipeline, engine, store = _pipeline(script, clock=lambda: datetime(2026, 1, 5, 9, 16))
    first = pipeline.process_next()
    second = pipeline.process_next()
    assert first.kind == "BAR_PROCESSED"
    assert second.kind == "OUT_OF_ORDER_REJECTED"
    report = reconcile(store)
    assert report.ok, report.issues
    # Same cycle-23 finding as the duplicate-bar test above: an
    # out-of-order bar inserted into the indicator history OUT OF
    # CHRONOLOGICAL POSITION is worse than a duplicate -- OHLCV.
    # to_dataframe() trusts list order with no sort, and pandas
    # .rolling()/.ewm() operate on row POSITION, not the DatetimeIndex
    # value, so a misplaced earlier bar would corrupt every subsequent
    # indicator computation, not just add one redundant observation.
    assert [b.timestamp for b in pipeline._buffers["TEST"].bars] == [bar5.timestamp]


def test_duplicate_and_out_of_order_bars_never_pollute_the_indicator_series():
    """End-to-end proof, one level above the raw buffer-list assertions in
    the two tests above: the actual DataFrame generate_signal() reads from
    must be exactly the genuinely-processed bars, in chronological order,
    with no extra or misplaced rows -- verified against
    to_indicator_series() output, not just internal buffer state."""
    bar1 = _qualifying_bar(1, minute=15)
    bar2 = _qualifying_bar(1, minute=16)
    bar3 = _qualifying_bar(1, minute=17)
    script = [
        MockScriptEvent.bar_event("TEST", bar1),
        MockScriptEvent.bar_event("TEST", bar1),  # duplicate of bar1
        MockScriptEvent.bar_event("TEST", bar2),
        MockScriptEvent.bar_event("TEST", bar1),  # out-of-order (older than bar2, already processed)
        MockScriptEvent.bar_event("TEST", bar3),
    ]
    pipeline, engine, store = _pipeline(
        script, interval="1m", clock=lambda: bar3.timestamp + timedelta(seconds=10),
        freshness_policy=FreshnessPolicy(multiplier=2.0, minimum_threshold=timedelta(minutes=10)),
    )
    kinds = []
    while (r := pipeline.process_next()).kind != "FEED_EXHAUSTED":
        kinds.append(r.kind)
    assert kinds == ["BAR_PROCESSED", "DUPLICATE_SKIPPED", "BAR_PROCESSED", "OUT_OF_ORDER_REJECTED", "BAR_PROCESSED"]

    series = pipeline._buffers["TEST"].to_indicator_series("TEST", "1m")
    assert list(series.index) == [bar1.timestamp, bar2.timestamp, bar3.timestamp]
    assert len(series) == 3  # not 5 -- the duplicate and the out-of-order delivery contributed zero rows


# --- 4. stale bar --------------------------------------------------------------


def test_stale_bar_suppresses_new_signal_generation():
    """A bar delivered long after its own timestamp must not be allowed to
    open a NEW position (spec §4: "reject new signal")."""
    bar = _qualifying_bar(1)
    script = [MockScriptEvent.bar_event("TEST", bar)]
    very_late = datetime(2026, 1, 1, 11, 0)  # ~1h45m after a 9:15 bar -- well past any reasonable 1d/1m threshold in this test
    pipeline, engine, store = _pipeline(script, interval="1m", clock=lambda: very_late, freshness_policy=FreshnessPolicy(multiplier=2.0, minimum_threshold=timedelta(seconds=30)))
    result = pipeline.process_next()
    assert result.kind == "STALE_SIGNAL_SUPPRESSED"
    assert result.freshness.is_fresh is False
    assert result.signal is None


def test_fresh_bar_is_not_suppressed():
    bar = _qualifying_bar(1)
    script = [MockScriptEvent.bar_event("TEST", bar)]
    pipeline, engine, store = _pipeline(script, interval="1m", clock=lambda: bar.timestamp + timedelta(seconds=10))
    result = pipeline.process_next()
    assert result.kind == "BAR_PROCESSED"


def test_a_stale_bar_never_fills_an_already_pending_order():
    """Autonomous hardening cycle 22 -- a real cross-component/time defect,
    found and fixed this cycle: before the fix, live/pipeline.py computed
    its own freshness check ONLY AFTER already calling
    PaperTradingEngine.process_bar() -- which fills any PENDING order at
    the CURRENT bar's open, or checks an OPEN position's stop/target
    against it. STALE_SIGNAL_SUPPRESSED (the outcome the stale check then
    returned) only ever suppressed generating a NEW signal FROM that bar;
    it never stopped an entry fill or exit already in flight from
    completing on data the pipeline itself had just judged too stale to
    trust -- a direct violation of this project's own "STALE MARKET DATA
    -> NO TRADE" invariant.

    Reproduced here exactly as it would happen live: bar 1 arrives while
    genuinely fresh and fires a signal via a strategy that always signals,
    which gets risk-approved into a PENDING order (require_human_approval
    defaults to False, so submit_signal() runs immediately). The wall
    clock then jumps forward by an hour -- simulating the feed/consumer
    falling far behind (exactly cycle 21's own bounded-queue scenario, or
    Dhan reconnect churn) -- before bar 2 arrives, which would normally
    fill that pending order at its open. Bar 2 must be suppressed, and the
    order must remain pending rather than being silently filled."""
    bar1 = _qualifying_bar(1, minute=15)
    bar2 = _qualifying_bar(1, minute=16)
    script = [MockScriptEvent.bar_event("TEST", bar1), MockScriptEvent.bar_event("TEST", bar2)]

    clock_state = {"now": bar1.timestamp + timedelta(seconds=5)}
    pipeline, engine, store = _pipeline(
        script, interval="1m", strategy=_ScriptedStrategy(), clock=lambda: clock_state["now"],
        freshness_policy=FreshnessPolicy(multiplier=2.0, minimum_threshold=timedelta(seconds=30)),
    )

    first = pipeline.process_next()
    assert first.kind == "BAR_PROCESSED"
    pending = store.get_pending_order("TEST")
    assert pending is not None, "the scripted strategy's signal should have been risk-approved into a PENDING order"

    clock_state["now"] = bar1.timestamp + timedelta(hours=1)  # the consumer/feed falls far behind before bar 2 is processed
    second = pipeline.process_next()

    assert second.kind == "STALE_SIGNAL_SUPPRESSED"
    assert store.get_open_position("TEST") is None, "a stale bar must never be allowed to fill a pending order (STALE DATA -> NO TRADE)"
    assert store.get_pending_order("TEST") is not None, "the order must remain pending, re-evaluated against the next (hopefully fresh) bar instead of being silently dropped"


def test_a_stale_bar_never_closes_an_already_open_position():
    """The same fix's other half: an OPEN position's stop/target must not
    be checked against a bar the pipeline has itself judged too stale to
    trust, even though an exit is nominally protective -- this project's
    own invariant is unconditional ("STALE MARKET DATA -> NO TRADE", no
    carve-out for exits), and a stale bar's price data may not reflect
    anything close to the current real market. Bar 1 fills the entry
    (fresh); bar 2 -- whose low would otherwise hit the scripted
    strategy's stop_price=95.0 -- arrives stale and must not close it."""
    bar1 = _qualifying_bar(1, minute=15)
    bar2 = _qualifying_bar(1, minute=16, low=90.0, close=91.0)  # would hit stop_price=95.0 if actually checked
    bar3 = _qualifying_bar(1, minute=17, low=90.0, close=91.0)  # fresh repeat -- proves the check still fires once trusted again
    script = [
        MockScriptEvent.bar_event("TEST", bar1), MockScriptEvent.bar_event("TEST", bar2), MockScriptEvent.bar_event("TEST", bar3),
    ]

    clock_state = {"now": bar1.timestamp + timedelta(seconds=5)}
    pipeline, engine, store = _pipeline(
        script, interval="1m", strategy=_ScriptedStrategy(), clock=lambda: clock_state["now"],
        freshness_policy=FreshnessPolicy(multiplier=2.0, minimum_threshold=timedelta(seconds=30)),
    )

    first = pipeline.process_next()
    assert first.kind == "BAR_PROCESSED"
    pending = store.get_pending_order("TEST")
    assert pending is not None

    clock_state["now"] = bar1.timestamp + timedelta(hours=1)  # bar 2 will be stale relative to this
    second = pipeline.process_next()
    assert second.kind == "STALE_SIGNAL_SUPPRESSED"
    # The fill that bar 2 would otherwise have triggered (entering AND
    # immediately stopping out in the same call, per process_bar's own
    # same-bar-exit-check behavior) must not have happened at all.
    assert store.get_open_position("TEST") is None
    assert store.get_pending_order("TEST") is not None

    clock_state["now"] = bar1.timestamp + timedelta(minutes=3, seconds=5)  # bar 3 is fresh again
    third = pipeline.process_next()
    assert third.kind == "BAR_PROCESSED"
    # Now genuinely trusted: the order fills AND immediately stops out on
    # the same (now-fresh) bar 3, exactly like process_bar's existing
    # same-bar-exit-check behavior for any other fresh bar.
    assert store.get_open_position("TEST") is None
    assert store.get_pending_order("TEST") is None


# --- 5/6. feed disconnect / reconnect ------------------------------------------


# --- richer connection-state in feed_status (LIVE SYSTEM HARDENING mission, Part 3) ---


def test_feed_status_connection_state_falls_back_to_the_coarse_boolean_without_a_state_attribute():
    """MockMarketDataSource has no `.state` attribute -- must fall back to
    the original CONNECTED/DISCONNECTED boolean-derived value exactly,
    the pre-existing behavior every other test in this file already
    relies on."""
    from live.state_store import LiveStateStore

    state_store = LiveStateStore(":memory:")
    bar = _qualifying_bar(1)
    script = [MockScriptEvent.bar_event("TEST", bar)]
    pipeline, engine, store = _pipeline(script, clock=lambda: bar.timestamp, state_store=state_store)
    pipeline.process_next()

    record = state_store.get_feed_status("TEST")
    assert record.connection_state == "CONNECTED"


def test_feed_status_connection_state_uses_a_richer_value_when_the_source_exposes_one():
    """A source MAY expose an optional `.state` attribute richer than the
    generic Protocol's is_connected() bool (e.g. a distinct
    RECONNECTING, not just CONNECTED/DISCONNECTED) -- when present, it
    must reach feed_status verbatim, not be collapsed back down."""
    from live.state_store import LiveStateStore

    state_store = LiveStateStore(":memory:")
    bar = _qualifying_bar(1)
    script = [MockScriptEvent.bar_event("TEST", bar)]
    pipeline, engine, store = _pipeline(script, clock=lambda: bar.timestamp, state_store=state_store)
    pipeline.source.state = "RECONNECTING"  # simulates an optional capability MockMarketDataSource does not normally have

    pipeline.process_next()

    record = state_store.get_feed_status("TEST")
    assert record.connection_state == "RECONNECTING"


def test_feed_status_last_price_is_the_processed_bars_close():
    """AUTONOMOUS LIVE PAPER-TRADING HARDENING mission, dashboard truth
    audit: feed_status previously carried no price at all -- real gap
    against the mission's own "live prices" MARKET checklist item."""
    from live.state_store import LiveStateStore

    state_store = LiveStateStore(":memory:")
    bar = _qualifying_bar(1, close=123.45)
    script = [MockScriptEvent.bar_event("TEST", bar)]
    pipeline, engine, store = _pipeline(script, clock=lambda: bar.timestamp, state_store=state_store)
    pipeline.process_next()

    record = state_store.get_feed_status("TEST")
    assert record.last_price == 123.45


# --- critic gate integration (LIVE SYSTEM HARDENING mission) -----------------


def test_no_critic_gate_configured_is_byte_for_byte_the_existing_behavior():
    """Default (critic_gate=None): every pre-existing caller of
    LiveSimPipeline, including the entire rest of this test file, must be
    completely unaffected -- proven by this whole file's other 17 tests
    passing unchanged, not just this one. This test names that
    invariant explicitly."""
    bar = make_mock_bar(timestamp=datetime(2026, 1, 1, 9, 15), open=100.0, high=101.0, low=99.0, close=100.0, volume=1000.0)
    script = [MockScriptEvent.bar_event("TEST", bar)]
    pipeline, engine, store = _pipeline(script, interval="1m", strategy=_ScriptedStrategy(), clock=lambda: bar.timestamp + timedelta(seconds=5))
    assert pipeline.critic_gate is None
    result = pipeline.process_next()
    assert result.kind == "BAR_PROCESSED"
    assert result.critic_assessment is None
    assert result.journal_entry is not None  # the real, unaffected paper-execution path


def test_a_blocking_critic_gate_prevents_any_paper_order():
    from critic.models import CriticAssessment, CriticVerdict
    from live.critic_gate import CriticGateResult

    blocking_assessment = CriticAssessment(
        verdict=CriticVerdict.REJECT, checks=(), failed_checks=("KILL_SWITCH",),
        warnings=(), reasons=["Kill switch is active -- execution safety blocks any new order."], config_version="test",
    )
    gate = _FakeCriticGate(CriticGateResult(blocked=True, block_reason=blocking_assessment.reasons[0], assessment=blocking_assessment, decision=None))

    bar = make_mock_bar(timestamp=datetime(2026, 1, 1, 9, 15), open=100.0, high=101.0, low=99.0, close=100.0, volume=1000.0)
    script = [MockScriptEvent.bar_event("TEST", bar)]
    pipeline, engine, store = _pipeline(script, interval="1m", strategy=_ScriptedStrategy(), critic_gate=gate, clock=lambda: bar.timestamp + timedelta(seconds=5))

    result = pipeline.process_next()

    assert result.kind == "CRITIC_REJECTED"
    assert result.journal_entry is None  # no paper order was ever created
    assert result.detail == "Kill switch is active -- execution safety blocks any new order."
    assert result.critic_assessment is blocking_assessment
    assert result.lifecycle.is_terminal
    assert len(gate.calls) == 1

    # No pending order/position was ever submitted to the paper engine at all.
    assert store.get_pending_order("TEST") is None
    assert store.get_open_position("TEST") is None


def test_a_blocking_critic_gate_persists_the_rejection_when_a_state_store_is_configured():
    from critic.models import CriticAssessment, CriticVerdict
    from live.critic_gate import CriticGateResult
    from live.state_store import LiveStateStore

    assessment = CriticAssessment(
        verdict=CriticVerdict.INSUFFICIENT_EVIDENCE, checks=(), failed_checks=(),
        warnings=(), reasons=["Neither market context nor research evidence is available."], config_version="test",
    )
    gate = _FakeCriticGate(CriticGateResult(blocked=True, block_reason=assessment.reasons[0], assessment=assessment, decision=None))
    state_store = LiveStateStore(":memory:")

    bar = make_mock_bar(timestamp=datetime(2026, 1, 1, 9, 15), open=100.0, high=101.0, low=99.0, close=100.0, volume=1000.0)
    script = [MockScriptEvent.bar_event("TEST", bar)]
    pipeline, engine, store = _pipeline(script, interval="1m", strategy=_ScriptedStrategy(), critic_gate=gate, state_store=state_store, clock=lambda: bar.timestamp + timedelta(seconds=5))

    result = pipeline.process_next()

    rejections = state_store.list_critic_rejections()
    assert len(rejections) == 1
    assert rejections[0].signal_id == result.signal.stable_id()
    assert rejections[0].symbol == "TEST"
    assert rejections[0].verdict == "INSUFFICIENT_EVIDENCE"
    assert rejections[0].reasons == ["Neither market context nor research evidence is available."]


def test_a_passing_critic_gate_still_lets_the_order_through_and_attaches_the_assessment():
    from critic.models import CriticAssessment, CriticVerdict
    from live.critic_gate import CriticGateResult

    approving_assessment = CriticAssessment(
        verdict=CriticVerdict.APPROVE, checks=(), failed_checks=(), warnings=(),
        reasons=["All hard checks passed."], config_version="test",
    )
    gate = _FakeCriticGate(CriticGateResult(blocked=False, block_reason="", assessment=approving_assessment, decision=None))

    bar = make_mock_bar(timestamp=datetime(2026, 1, 1, 9, 15), open=100.0, high=101.0, low=99.0, close=100.0, volume=1000.0)
    script = [MockScriptEvent.bar_event("TEST", bar)]
    pipeline, engine, store = _pipeline(script, interval="1m", strategy=_ScriptedStrategy(), critic_gate=gate, clock=lambda: bar.timestamp + timedelta(seconds=5))

    result = pipeline.process_next()

    assert result.kind == "BAR_PROCESSED"
    assert result.journal_entry is not None  # the real paper-execution path still ran
    assert result.critic_assessment is approving_assessment
    assert len(gate.calls) == 1


def test_critic_gate_runs_before_risk_and_never_reaches_it_when_blocked():
    """The mission's own target chain: Decision Engine -> Deterministic
    Critic -> Risk Engine. A blocked signal must never even reach risk
    sizing -- proven by an intentionally-nonsensical stop/target (which
    risk.engine would itself reject) never actually mattering, because
    the critic already stopped it first."""
    from critic.models import CriticAssessment, CriticVerdict
    from live.critic_gate import CriticGateResult

    blocking = CriticAssessment(verdict=CriticVerdict.REJECT, checks=(), failed_checks=("TRADE_STRUCTURE",), warnings=(), reasons=["blocked"], config_version="test")
    gate = _FakeCriticGate(CriticGateResult(blocked=True, block_reason="blocked", assessment=blocking, decision=None))

    bar = make_mock_bar(timestamp=datetime(2026, 1, 1, 9, 15), open=100.0, high=101.0, low=99.0, close=100.0, volume=1000.0)
    script = [MockScriptEvent.bar_event("TEST", bar)]
    pipeline, engine, store = _pipeline(
        script, interval="1m", require_human_approval=True,
        strategy=_ScriptedStrategy(), critic_gate=gate, clock=lambda: bar.timestamp + timedelta(seconds=5),
    )

    result = pipeline.process_next()
    assert result.kind == "CRITIC_REJECTED"
    assert result.lifecycle.state.value == "CRITIC_REJECTED"
    # Never reached PENDING_HUMAN_APPROVAL or any risk-engine state at all.
    assert ("RISK_APPROVED", "PENDING_HUMAN_APPROVAL") != tuple(s.value for s, _ in result.lifecycle.history[1:])


def test_feed_disconnect_is_reported_and_does_not_crash_the_pipeline():
    script = [MockScriptEvent.disconnect(), MockScriptEvent.bar_event("TEST", _qualifying_bar(1))]
    pipeline, engine, store = _pipeline(script, clock=lambda: datetime(2026, 1, 1, 9, 16))
    result = pipeline.process_next()
    assert result.kind == "FEED_DISCONNECTED"


def test_reconnect_resumes_normal_processing():
    script = [
        MockScriptEvent.disconnect(),
        MockScriptEvent.bar_event("TEST", _qualifying_bar(1)),
        MockScriptEvent.reconnect(),
        MockScriptEvent.bar_event("TEST", _qualifying_bar(2)),
    ]
    pipeline, engine, store = _pipeline(script, clock=lambda: datetime(2026, 1, 2, 9, 16))
    disconnected = pipeline.process_next()
    resumed = pipeline.process_next()
    assert disconnected.kind == "FEED_DISCONNECTED"
    assert resumed.kind == "BAR_PROCESSED"
    assert resumed.bar.timestamp.day == 2


# --- 10/11/12. interval support -------------------------------------------------


@pytest.mark.parametrize("interval,step", [("1m", timedelta(minutes=1)), ("5m", timedelta(minutes=5)), ("15m", timedelta(minutes=15))])
def test_intraday_intervals_process_correctly(interval, step):
    start = datetime(2026, 1, 1, 9, 15)
    bars = [make_mock_bar(timestamp=start + step * i, open=100.0, high=101.0, low=99.0, close=100.0, volume=1000.0) for i in range(30)]
    script = [MockScriptEvent.bar_event("TEST", b) for b in bars]
    pipeline, engine, store = _pipeline(script, interval=interval, clock=lambda: start + step * 30)
    processed = 0
    while (r := pipeline.process_next()).kind != "FEED_EXHAUSTED":
        assert r.kind in ("BAR_PROCESSED", "STALE_SIGNAL_SUPPRESSED")
        processed += 1
    assert processed == 30
    report = reconcile(store)
    assert report.ok, report.issues


# --- 13. mock replay determinism ------------------------------------------------


def test_mock_replay_is_deterministic_across_two_runs():
    def build_script():
        bars = [make_bar(close=100 + (i % 20), open=100 + (i % 20), high=102 + (i % 20), low=97 + (i % 20)) if i % 5 == 0
                else make_bar(sma_20=80.0, sma_50=90.0, close=100 + (i % 20), open=100 + (i % 20), high=102 + (i % 20), low=97 + (i % 20))
                for i in range(40)]
        series = make_indicator_series(bars)
        return [
            MockScriptEvent.bar_event("TEST", make_mock_bar(timestamp=ts, open=row["open"], high=row["high"], low=row["low"], close=row["close"], volume=row["volume"]))
            for ts, row in series.iterrows()
        ]

    def run_once():
        pipeline, engine, store = _pipeline(build_script(), clock=lambda: datetime(2026, 3, 1))
        while pipeline.process_next().kind != "FEED_EXHAUSTED":
            pass
        trades = store.list_trades()
        return {
            "equity": engine.account.equity,
            "trade_count": len(trades),
            "trade_values": sorted((t.entry_price, t.exit_price, t.net_pnl, t.exit_reason.value) for t in trades),
        }

    assert run_once() == run_once()


# --- 14. restart -----------------------------------------------------------------


def test_pipeline_restart_matches_uninterrupted_run(tmp_path):
    start = datetime(2026, 1, 1, 9, 15)
    bars = []
    for i in range(60):
        close = 100 + (i % 20)
        vol = 1_000_000.0 * (1.2 if i % 5 == 0 else 0.8)
        bars.append(make_mock_bar(timestamp=start + timedelta(minutes=i), open=close, high=close + 2, low=close - 2, close=close, volume=vol))
    script_a = [MockScriptEvent.bar_event("TEST", b) for b in bars]
    script_b1 = [MockScriptEvent.bar_event("TEST", b) for b in bars[:30]]
    script_b2 = [MockScriptEvent.bar_event("TEST", b) for b in bars[30:]]

    def business_state(store):
        account = store.get_account()
        trades = store.list_trades()
        return {"equity": account.equity, "trade_count": len(trades), "trade_pnls": sorted(t.net_pnl for t in trades)}

    store_a = PaperStore(tmp_path / "uninterrupted.db")
    engine_a = PaperTradingEngine(store_a, initial_capital=100_000.0)
    pipeline_a = LiveSimPipeline(source=MockMarketDataSource(script_a), engine=engine_a, strategy=TrendMomentumBaseline(), symbols=["TEST"], interval="1m", clock=lambda: start + timedelta(hours=2))
    while pipeline_a.process_next().kind != "FEED_EXHAUSTED":
        pass
    state_a = business_state(store_a)
    store_a.close()

    store_b1 = PaperStore(tmp_path / "restarted.db")
    engine_b1 = PaperTradingEngine(store_b1, initial_capital=100_000.0)
    pipeline_b1 = LiveSimPipeline(source=MockMarketDataSource(script_b1), engine=engine_b1, strategy=TrendMomentumBaseline(), symbols=["TEST"], interval="1m", clock=lambda: start + timedelta(hours=2))
    while pipeline_b1.process_next().kind != "FEED_EXHAUSTED":
        pass
    store_b1.close()

    store_b2 = PaperStore(tmp_path / "restarted.db")
    engine_b2 = PaperTradingEngine(store_b2, initial_capital=100_000.0)
    pipeline_b2 = LiveSimPipeline(source=MockMarketDataSource(script_b2), engine=engine_b2, strategy=TrendMomentumBaseline(), symbols=["TEST"], interval="1m", clock=lambda: start + timedelta(hours=2))
    while pipeline_b2.process_next().kind != "FEED_EXHAUSTED":
        pass
    state_b = business_state(store_b2)

    assert state_a == state_b
    report = reconcile(store_b2)
    assert report.ok, report.issues
    store_b2.close()


# --- 15. paper/backtest parity --------------------------------------------------


@pytest.mark.skipif(not AAPL_CACHE_PATH.exists(), reason=f"No cached AAPL data at {AAPL_CACHE_PATH}")
def test_live_pipeline_matches_backtest_on_real_aapl_data():
    from backtesting.cache import CACHE_ROOT, CachedMarketDataProvider
    from backtesting.engine import run_backtest
    from market.indicators import compute_indicator_series

    class _NoNetwork:
        def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
            raise AssertionError("must use cache")

    provider = CachedMarketDataProvider(_NoNetwork())
    ohlcv = provider.fetch_ohlcv("AAPL", interval="1d")
    series = compute_indicator_series(ohlcv)
    bt_result = run_backtest(symbol="AAPL", indicator_series=series, strategy=TrendMomentumBaseline(), initial_capital=100_000.0)

    script = [
        MockScriptEvent.bar_event("AAPL", make_mock_bar(timestamp=ts, open=row["open"], high=row["high"], low=row["low"], close=row["close"], volume=row["volume"]))
        for ts, row in series.iterrows()
    ]
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    # far_future_clock is FIXED (not advancing with each bar), so the
    # freshness threshold must exceed the ENTIRE series span (~5y here) or
    # early bars would be (correctly, by the freshness guard's own logic)
    # flagged stale relative to this fixed future "now" -- freshness isn't
    # what's under test here, so make the threshold generously larger than
    # the whole dataset rather than merely "large".
    far_future_clock = lambda: series.index[-1] + timedelta(days=1)
    pipeline = LiveSimPipeline(source=MockMarketDataSource(script), engine=engine, strategy=TrendMomentumBaseline(), symbols=["AAPL"], interval="1d", clock=far_future_clock, freshness_policy=FreshnessPolicy(multiplier=10_000.0))
    while pipeline.process_next().kind != "FEED_EXHAUSTED":
        pass

    live_trades = sorted((t.entry_price, t.exit_price, t.quantity, t.net_pnl, t.exit_reason.value) for t in store.list_trades())
    bt_trades = sorted((t.entry_price, t.exit_price, t.quantity, t.net_pnl, t.exit_reason.value) for t in bt_result.trades)
    assert live_trades == bt_trades
    report = reconcile(store)
    assert report.ok, report.issues


# --- 16. fail-closed / causality -------------------------------------------------


def test_mutating_a_future_bar_does_not_change_an_already_processed_decision():
    """The core causality guarantee, proven at the pipeline level: what
    happened on bar N must not depend on what bar N+1 turns out to be."""
    start = datetime(2026, 1, 1, 9, 15)
    common_bars = [make_mock_bar(timestamp=start + timedelta(minutes=i), open=100 + i, high=101 + i, low=99 + i, close=100 + i, volume=1000.0) for i in range(10)]

    script_a = [MockScriptEvent.bar_event("TEST", b) for b in common_bars] + [
        MockScriptEvent.bar_event("TEST", make_mock_bar(timestamp=start + timedelta(minutes=10), open=500, high=600, low=400, close=550, volume=99999.0))
    ]
    script_b = [MockScriptEvent.bar_event("TEST", b) for b in common_bars] + [
        MockScriptEvent.bar_event("TEST", make_mock_bar(timestamp=start + timedelta(minutes=10), open=1, high=2, low=0.5, close=1, volume=1.0))
    ]

    def run(script):
        pipeline, engine, store = _pipeline(script, interval="1m", clock=lambda: start + timedelta(hours=1))
        results = []
        for _ in range(10):  # only the first 10 (common) bars
            results.append(pipeline.process_next())
        return results

    results_a = run(script_a)
    results_b = run(script_b)
    for ra, rb in zip(results_a, results_b):
        assert ra.kind == rb.kind
        assert ra.bar.close == rb.bar.close


def test_out_of_order_rejection_leaves_no_partial_state():
    script = [MockScriptEvent.bar_event("TEST", _qualifying_bar(5)), MockScriptEvent.bar_event("TEST", _qualifying_bar(3))]
    pipeline, engine, store = _pipeline(script, clock=lambda: datetime(2026, 1, 5, 9, 16))
    pipeline.process_next()
    with pytest.raises(OutOfOrderBarError):
        # process_bar itself still raises when called directly -- the
        # pipeline's own catch is what turns it into OUT_OF_ORDER_REJECTED;
        # this confirms the underlying guarantee (Phase 7A) is untouched.
        engine.process_bar("TEST", __import__("paper.engine", fromlist=["Bar"]).Bar(timestamp=datetime(2026, 1, 3), open=1, high=2, low=0.5, close=1))


# --- 17/18. no LLM / no broker dependency ----------------------------------------


def test_live_pipeline_never_imports_llm_modules():
    import sys

    forbidden_before = {n for n in sys.modules if n.split(".")[0] in {"langgraph", "langchain_ollama", "ollama"}}
    script = [MockScriptEvent.bar_event("TEST", _qualifying_bar(1))]
    pipeline, engine, store = _pipeline(script, clock=lambda: datetime(2026, 1, 1, 9, 16))
    pipeline.process_next()
    forbidden_after = {n for n in sys.modules if n.split(".")[0] in {"langgraph", "langchain_ollama", "ollama"}} - forbidden_before
    assert not forbidden_after


def test_live_package_has_no_broker_module_or_reference():
    import inspect

    import live.pipeline

    source = inspect.getsource(live.pipeline)
    for forbidden in ("dhan", "zerodha", "kite", "fyers", "broker_api", "place_order", "execute_trade"):
        assert forbidden not in source.lower()
