"""Phase 13 §17 — THE critical security test: a client cannot force
quantity/stop/target values into execution through the approval API.

The proof is structural, not behavioral: approve_pending()/reject_pending()
do not have a parameter that could carry such a value in the first place --
calling with one raises TypeError before any of this module's logic even
runs. This mirrors the exact pattern Phase 6/9 already established
(Signal/FilteredStrategy have no field a caller could use to override
price/quantity).
"""
import inspect

import pytest

from live.pipeline import LiveSimPipeline


def test_approve_pending_signature_has_no_execution_override_parameters():
    sig = inspect.signature(LiveSimPipeline.approve_pending)
    param_names = set(sig.parameters) - {"self"}
    assert param_names == {"signal_id", "reason"}
    for forbidden in ("quantity", "stop", "target", "price", "approved", "size"):
        assert forbidden not in param_names


def test_reject_pending_signature_has_no_execution_override_parameters():
    sig = inspect.signature(LiveSimPipeline.reject_pending)
    param_names = set(sig.parameters) - {"self"}
    assert param_names == {"signal_id", "reason"}


def test_calling_approve_pending_with_a_quantity_kwarg_raises_typeerror():
    """The literal attack this test proves impossible: approve(quantity=100000, stop=0, target=999999)."""
    with pytest.raises(TypeError):
        LiveSimPipeline.approve_pending(
            object(), signal_id="anything", quantity=100_000, stop=0, target=999_999,  # type: ignore[call-arg]
        )


def test_calling_reject_pending_with_execution_kwargs_raises_typeerror():
    with pytest.raises(TypeError):
        LiveSimPipeline.reject_pending(object(), signal_id="anything", quantity=100_000)  # type: ignore[call-arg]


def test_approved_execution_uses_the_signals_own_immutable_price_levels(tmp_path):
    """End-to-end reinforcement: even with a fully real pending approval,
    the executed order's stop/target come from the ORIGINAL frozen Signal
    -- there is no code path between PENDING_HUMAN_APPROVAL and EXECUTED
    that reads a stop/target/quantity from anywhere other than that Signal
    and a fresh RiskEngine evaluation."""
    from datetime import datetime

    from live.freshness import FreshnessPolicy
    from live.mock_source import MockMarketDataSource
    from live.state_store import LiveStateStore
    from paper.engine import PaperTradingEngine
    from paper.store import PaperStore
    from strategy.baseline import TrendMomentumBaseline
    from tests.conftest import AAPL_CACHE_PATH, real_aapl_mock_script

    if not AAPL_CACHE_PATH.exists():
        pytest.skip(f"No cached AAPL data at {AAPL_CACHE_PATH}")

    script = real_aapl_mock_script()
    store = PaperStore(tmp_path / "p.db")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    pipeline = LiveSimPipeline(
        source=MockMarketDataSource(script), engine=engine, strategy=TrendMomentumBaseline(), symbols=["AAPL"], interval="1d",
        require_human_approval=True, state_store=LiveStateStore(tmp_path / "s.db"),
        freshness_policy=FreshnessPolicy(multiplier=1_000_000.0), clock=lambda: datetime(2026, 8, 26),
    )
    result = None
    while True:
        result = pipeline.process_next()
        if result.kind in ("PENDING_HUMAN_APPROVAL", "FEED_EXHAUSTED"):
            break
    assert result.kind == "PENDING_HUMAN_APPROVAL"
    original_signal = result.signal

    action = pipeline.approve_pending(original_signal.stable_id())
    assert action.outcome.value == "APPROVED"

    order = store.get_pending_order("AAPL")
    assert order.stop_price == original_signal.stop_price
    assert order.target_price == original_signal.target_price
    assert order.requested_price == original_signal.reference_price


def test_approve_pending_never_calls_submit_signal_when_the_claim_is_already_lost(tmp_path):
    """Autonomous hardening cycle 20 -- a DETERMINISTIC proof of the actual
    fix mechanism, complementing the probabilistic thread-race test below.

    The real bug this pins: a first attempt at this fix only guarded the
    LATER write (recording EXECUTED/RISK_REJECTED) -- but by the time that
    write ran, submit_signal() had ALREADY executed unconditionally,
    already creating a real PaperOrder regardless of who "won." Cycle 19's
    own concurrent-thread test caught this the moment it was implemented
    (a genuinely useful regression, not a hypothetical one). The corrected
    fix moves the guarded CLAIM write to happen FIRST, before
    submit_signal runs at all -- this test proves that ordering directly,
    deterministically, without depending on real thread-scheduling luck:
    pre-set the persisted state to already-decided (simulating "someone
    else's decision already won"), then call approve_pending and assert
    submit_signal was never reached."""
    from datetime import datetime
    from unittest.mock import MagicMock

    from live.state_store import LiveStateStore
    from paper.engine import PaperTradingEngine
    from paper.store import PaperStore
    from live.freshness import FreshnessPolicy
    from live.mock_source import MockMarketDataSource
    from strategy.baseline import TrendMomentumBaseline
    from tests.conftest import AAPL_CACHE_PATH, real_aapl_mock_script

    if not AAPL_CACHE_PATH.exists():
        pytest.skip(f"No cached AAPL data at {AAPL_CACHE_PATH}")

    script = real_aapl_mock_script()
    store = PaperStore(tmp_path / "p.db")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    state_store = LiveStateStore(tmp_path / "s.db")
    pipeline = LiveSimPipeline(
        source=MockMarketDataSource(script), engine=engine, strategy=TrendMomentumBaseline(), symbols=["AAPL"], interval="1d",
        require_human_approval=True, state_store=state_store,
        freshness_policy=FreshnessPolicy(multiplier=1_000_000.0), clock=lambda: datetime(2026, 8, 26),
    )
    result = None
    while True:
        result = pipeline.process_next()
        if result.kind in ("PENDING_HUMAN_APPROVAL", "FEED_EXHAUSTED"):
            break
    assert result.kind == "PENDING_HUMAN_APPROVAL"
    signal_id = result.signal.stable_id()

    # Simulate "someone else's reject already won" by directly moving the
    # persisted row out of PENDING_HUMAN_APPROVAL, exactly as reject_pending
    # itself would have -- without going through the pipeline's own
    # in-memory pending_approvals dict at all (that dict still (wrongly, in
    # a real race) believes the signal is actionable, matching the real
    # multi-process scenario this defends against).
    state_store._conn.execute("UPDATE pending_approvals SET state='HUMAN_REJECTED' WHERE signal_id=?", (signal_id,))

    original_submit_signal = engine.submit_signal
    mock_submit_signal = MagicMock(side_effect=AssertionError("submit_signal must never be called once the claim is already lost"))
    engine.submit_signal = mock_submit_signal
    try:
        action = pipeline.approve_pending(signal_id)
    finally:
        engine.submit_signal = original_submit_signal

    assert action.outcome.value == "ALREADY_DECIDED"
    mock_submit_signal.assert_not_called()
    assert store.get_pending_order("AAPL") is None  # no order was ever created


def test_concurrent_approve_and_reject_of_the_same_signal_never_produces_inconsistent_state(tmp_path):
    """Autonomous hardening cycle 19 -- a real concurrency attack on
    live/pipeline.py itself (one of this campaign's 8 sacred live-
    execution-safety files, deliberately left untouched by cycle 15's
    submit_signal fix, disclosed as unaudited in FINAL_FAILURE_MODE_
    ANALYSIS.md entry #28). Proves, rather than assumes, the narrowest
    real race this architecture allows: dashboard/app.py's approve/
    reject routes (via live/workstation.py::approve_pending_signal/
    reject_pending_signal) build a BRAND NEW LiveSimPipeline + a BRAND
    NEW LiveStateStore connection on EVERY single call -- so two
    genuinely concurrent HTTP requests (e.g. an operator double-clicking
    both Approve and Reject on the same still-open browser tab, or two
    tabs open on the same stale page) each restore pending-approval
    state independently from the SAME underlying store, and could both
    see the signal as actionable before either has written a decision.

    This test reproduces exactly that: two real threads, each building
    its own fresh LiveSimPipeline/LiveStateStore/PaperStore connection
    to the SAME temp files (the faithful simulation of two independent
    dashboard requests), racing approve_pending vs reject_pending for
    the IDENTICAL signal_id.

    The property under test is NOT "only one of the two wins" (both
    genuinely CAN act, since each restores its own in-memory state
    independently -- that asymmetry is real and not something this test
    pretends away). The property is the one that actually matters for
    safety: if a real PaperOrder was created (the APPROVE path actually
    ran RiskEngine.evaluate and created state), the FINAL recorded
    decision in live_state.db must say APPROVED, never REJECTED --
    because paper/engine.py::submit_signal's own cycle-15 idempotency
    fix means at most ONE PaperOrder can ever exist for this signal_id
    regardless of how many times/threads call submit_signal on it, so
    "an order exists" and "the decision says APPROVED" must never
    disagree."""
    import threading

    from live.freshness import FreshnessPolicy
    from live.mock_source import MockMarketDataSource
    from live.state_store import LiveStateStore
    from paper.engine import PaperTradingEngine
    from paper.store import PaperStore
    from strategy.baseline import TrendMomentumBaseline
    from tests.conftest import AAPL_CACHE_PATH, real_aapl_mock_script

    if not AAPL_CACHE_PATH.exists():
        pytest.skip(f"No cached AAPL data at {AAPL_CACHE_PATH}")

    paper_db = tmp_path / "p.db"
    state_db = tmp_path / "s.db"

    script = real_aapl_mock_script()
    setup_store = PaperStore(paper_db)
    setup_engine = PaperTradingEngine(setup_store, initial_capital=100_000.0)
    setup_state_store = LiveStateStore(state_db)
    # Deliberately the REAL default clock (datetime.now(timezone.utc), aware)
    # here and in every racing pipeline below -- not a fixed/naive clock
    # override, since mixing a naive test-only clock with the real aware
    # default (as production always uses) would raise its own unrelated
    # TypeError comparing naive vs. aware datetimes, an artifact of test
    # setup, not the race this test exists to attack.
    setup_pipeline = LiveSimPipeline(
        source=MockMarketDataSource(script), engine=setup_engine, strategy=TrendMomentumBaseline(),
        symbols=["AAPL"], interval="1d", require_human_approval=True, state_store=setup_state_store,
        freshness_policy=FreshnessPolicy(multiplier=1_000_000.0),
    )
    result = None
    while True:
        result = setup_pipeline.process_next()
        if result.kind in ("PENDING_HUMAN_APPROVAL", "FEED_EXHAUSTED"):
            break
    assert result.kind == "PENDING_HUMAN_APPROVAL"
    signal_id = result.signal.stable_id()
    setup_state_store.close()  # simulates the setup process finishing, e.g. paper-live persisting to disk and returning

    outcomes: dict[str, str] = {}
    barrier = threading.Barrier(2)

    def _race(action: str) -> None:
        state_store = LiveStateStore(state_db)
        engine = PaperTradingEngine(PaperStore(paper_db), initial_capital=100_000.0)
        pipeline = LiveSimPipeline(
            source=MockMarketDataSource([]), engine=engine, strategy=TrendMomentumBaseline(),
            symbols=[], interval="1d", require_human_approval=True, state_store=state_store,
        )
        try:
            barrier.wait()
            if action == "approve":
                outcomes["approve"] = pipeline.approve_pending(signal_id).outcome.value
            else:
                outcomes["reject"] = pipeline.reject_pending(signal_id).outcome.value
        finally:
            state_store.close()

    t1 = threading.Thread(target=_race, args=("approve",))
    t2 = threading.Thread(target=_race, args=("reject",))
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    assert set(outcomes.keys()) == {"approve", "reject"}, f"one side crashed instead of returning gracefully: {outcomes}"

    final_store = PaperStore(paper_db)
    order_exists = final_store.get_pending_order("AAPL") is not None
    final_store.close()

    final_state_store = LiveStateStore(state_db)
    record = final_state_store.get(signal_id)
    final_state_store.close()

    if order_exists:
        assert record.decision == "APPROVE", (
            f"a real PaperOrder exists but the recorded decision says {record.decision!r} -- "
            "the audit trail must never contradict what actually happened at the execution layer"
        )


def test_concurrent_approve_and_expire_of_the_same_signal_never_produces_inconsistent_state(tmp_path):
    """Autonomous hardening cycle 23 -- the same architectural question as
    the approve-vs-reject race above, attacked from the angle this cycle's
    own mission named explicitly: approve() racing expire_pending_
    approvals() across two independently-restored pipeline instances
    (simulating a restart -- e.g. the continuously-running paper-live
    process's own expiry check firing at the exact moment an operator
    clicks Approve in the dashboard), each with its own fresh
    LiveSimPipeline/LiveStateStore/PaperStore connection to the SAME
    underlying files.

    A deliberately tiny approval_timeout_seconds plus a real sleep means
    the signal is GENUINELY past its expiry, by real wall-clock time,
    before either thread races -- not a simulated/mocked clock. Both
    threads independently restore the same still-PENDING_HUMAN_APPROVAL
    persisted row (its expires_at is immutable, set once at signal-
    approval time) and independently compute now > expires_at as True --
    so this exercises TWO CONCURRENT WRITERS both attempting to persist
    the SAME terminal APPROVAL_EXPIRED transition (approve_pending's own
    _check_actionable calls expire_pending_approvals() internally the
    moment it sees an expired pending entry), a genuinely different
    SQLite-concurrency shape than the approve-vs-reject test above (two
    DIFFERENT terminal states racing) even though the same CAS guard in
    LiveStateStore.update_decision protects both.

    Safety property: regardless of which write wins, no PaperOrder may
    ever be created for an already-expired signal, and the final
    persisted record must land on APPROVAL_EXPIRED, not be left corrupted
    or duplicated by the losing writer's InvalidDecisionTransitionError
    path."""
    import threading
    import time

    from live.freshness import FreshnessPolicy
    from live.mock_source import MockMarketDataSource
    from live.state_store import LiveStateStore
    from paper.engine import PaperTradingEngine
    from paper.store import PaperStore
    from strategy.baseline import TrendMomentumBaseline
    from tests.conftest import AAPL_CACHE_PATH, real_aapl_mock_script

    if not AAPL_CACHE_PATH.exists():
        pytest.skip(f"No cached AAPL data at {AAPL_CACHE_PATH}")

    paper_db = tmp_path / "p.db"
    state_db = tmp_path / "s.db"

    script = real_aapl_mock_script()
    setup_store = PaperStore(paper_db)
    setup_engine = PaperTradingEngine(setup_store, initial_capital=100_000.0)
    setup_state_store = LiveStateStore(state_db)
    setup_pipeline = LiveSimPipeline(
        source=MockMarketDataSource(script), engine=setup_engine, strategy=TrendMomentumBaseline(),
        symbols=["AAPL"], interval="1d", require_human_approval=True, state_store=setup_state_store,
        freshness_policy=FreshnessPolicy(multiplier=1_000_000.0), approval_timeout_seconds=0.01,
    )
    result = None
    while True:
        result = setup_pipeline.process_next()
        if result.kind in ("PENDING_HUMAN_APPROVAL", "FEED_EXHAUSTED"):
            break
    assert result.kind == "PENDING_HUMAN_APPROVAL"
    signal_id = result.signal.stable_id()
    setup_state_store.close()  # simulates the setup process finishing

    time.sleep(0.1)  # guarantee genuine expiry by real wall-clock time before either thread races

    outcomes: dict[str, object] = {}
    barrier = threading.Barrier(2)

    def _race(action: str) -> None:
        state_store = LiveStateStore(state_db)
        engine = PaperTradingEngine(PaperStore(paper_db), initial_capital=100_000.0)
        pipeline = LiveSimPipeline(
            source=MockMarketDataSource([]), engine=engine, strategy=TrendMomentumBaseline(),
            symbols=[], interval="1d", require_human_approval=True, state_store=state_store,
            approval_timeout_seconds=0.01,
        )
        try:
            barrier.wait()
            if action == "approve":
                outcomes["approve"] = pipeline.approve_pending(signal_id).outcome.value
            else:
                outcomes["expire"] = pipeline.expire_pending_approvals()
        finally:
            state_store.close()

    t1 = threading.Thread(target=_race, args=("approve",))
    t2 = threading.Thread(target=_race, args=("expire",))
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    assert set(outcomes.keys()) == {"approve", "expire"}, f"one side crashed instead of returning gracefully: {outcomes}"
    # The signal is already genuinely expired by real wall-clock time for
    # BOTH independently-restored pipelines -- approve_pending's own
    # _check_actionable must itself detect this (it is not required to
    # "lose" against the other thread's explicit expire_pending_approvals()
    # call to reach the correct outcome; either path reaching the
    # persisted EXPIRED state first is a legitimate, safe result).
    assert outcomes["approve"] == "EXPIRED"

    final_store = PaperStore(paper_db)
    order_exists = final_store.get_pending_order("AAPL") is not None
    final_store.close()
    assert not order_exists, "an already-expired signal must never result in a real PaperOrder, regardless of race timing"

    final_state_store = LiveStateStore(state_db)
    record = final_state_store.get(signal_id)
    final_state_store.close()
    assert record.state == "APPROVAL_EXPIRED"
    assert record.decision == "EXPIRED"


def test_approve_pending_never_calls_submit_signal_when_the_kill_switch_activates_between_the_claim_and_the_risk_check(tmp_path):
    """Autonomous hardening cycle 25 -- a real TOCTOU window closed, found
    by tracing approve_pending()'s exact temporal sequence rather than
    re-testing any single check in isolation.

    is_kill_switch_active() was previously checked ONLY ONCE, inside
    _check_actionable() at the very TOP of approve_pending() -- before the
    CAS claim write (LiveStateStore.update_decision, cycle 20) and before
    submit_signal() (which actually creates the real PaperOrder).
    RiskEngine.evaluate() -- "the mandatory second risk check" the
    original code comment already names -- has NO kill-switch awareness
    at all (verified directly against risk/engine.py's full source during
    cycle 24's mutation audit: kill switch is a live-system-only concept
    living in LiveStateStore, deliberately kept out of the pure,
    backtest-reusable RiskEngine). So nothing between the initial check
    and submit_signal() actually creating an order would ever catch a
    kill switch activated in that window -- e.g. a human hits the
    emergency stop in the moment between clicking Approve and the call
    actually reaching submit_signal().

    This test forces that EXACT interleaving deterministically (not a
    timing-dependent race): LiveStateStore.update_decision (the CAS claim
    write) is wrapped so that the instant it returns -- i.e. the instant
    this call has won exclusive ownership of signal_id, but BEFORE
    approve_pending's own next line runs -- the kill switch is activated.
    A losing race is impossible to construct any other way with 100%
    reliability; this is the same deterministic-injection technique cycle
    20's own test used for the equivalent approve/reject claim race."""
    from datetime import datetime
    from unittest.mock import MagicMock

    from live.freshness import FreshnessPolicy
    from live.mock_source import MockMarketDataSource
    from live.state_store import LiveStateStore
    from paper.engine import PaperTradingEngine
    from paper.store import PaperStore
    from strategy.baseline import TrendMomentumBaseline
    from tests.conftest import AAPL_CACHE_PATH, real_aapl_mock_script

    if not AAPL_CACHE_PATH.exists():
        pytest.skip(f"No cached AAPL data at {AAPL_CACHE_PATH}")

    script = real_aapl_mock_script()
    store = PaperStore(tmp_path / "p.db")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    state_store = LiveStateStore(tmp_path / "s.db")
    pipeline = LiveSimPipeline(
        source=MockMarketDataSource(script), engine=engine, strategy=TrendMomentumBaseline(), symbols=["AAPL"], interval="1d",
        require_human_approval=True, state_store=state_store,
        freshness_policy=FreshnessPolicy(multiplier=1_000_000.0), clock=lambda: datetime(2026, 8, 26),
    )
    result = None
    while True:
        result = pipeline.process_next()
        if result.kind in ("PENDING_HUMAN_APPROVAL", "FEED_EXHAUSTED"):
            break
    assert result.kind == "PENDING_HUMAN_APPROVAL"
    signal_id = result.signal.stable_id()

    original_update_decision = state_store.update_decision

    def _claim_then_activate_kill_switch(*args, **kwargs):
        original_update_decision(*args, **kwargs)  # the real CAS claim write -- must commit first
        state_store.activate_kill_switch(reason="test: activated in the exact window between the CAS claim and submit_signal")

    state_store.update_decision = _claim_then_activate_kill_switch

    original_submit_signal = engine.submit_signal
    mock_submit_signal = MagicMock(side_effect=AssertionError("submit_signal must never be called once the kill switch has activated"))
    engine.submit_signal = mock_submit_signal
    try:
        action = pipeline.approve_pending(signal_id)
    finally:
        engine.submit_signal = original_submit_signal
        state_store.update_decision = original_update_decision

    assert action.outcome.value == "KILL_SWITCH_ACTIVE"
    mock_submit_signal.assert_not_called()
    assert store.get_pending_order("AAPL") is None  # no order was ever created

    record = state_store.get(signal_id)
    assert record.state == "RISK_REJECTED"
    assert record.final_execution_result == "KILL_SWITCH_ACTIVE"


def test_a_real_concurrent_kill_switch_activation_during_approve_pending_never_creates_an_order(tmp_path):
    """Real-thread confirmation of the deterministic proof above, using a
    threading.Barrier so the exact ordering is controlled rather than
    timing-dependent luck: thread A calls approve_pending(); thread B is
    released from the barrier the INSTANT thread A's CAS claim commits
    (via the same update_decision wrapping technique, now signaling a
    real second thread instead of acting inline), and immediately
    activates the kill switch on a genuinely separate LiveStateStore
    connection to the same file -- the faithful simulation of an operator
    hitting the emergency-stop button in a different browser tab/process
    at that exact moment."""
    import threading
    from datetime import datetime

    from live.freshness import FreshnessPolicy
    from live.mock_source import MockMarketDataSource
    from live.state_store import LiveStateStore
    from paper.engine import PaperTradingEngine
    from paper.store import PaperStore
    from strategy.baseline import TrendMomentumBaseline
    from tests.conftest import AAPL_CACHE_PATH, real_aapl_mock_script

    if not AAPL_CACHE_PATH.exists():
        pytest.skip(f"No cached AAPL data at {AAPL_CACHE_PATH}")

    paper_db = tmp_path / "p.db"
    state_db = tmp_path / "s.db"

    script = real_aapl_mock_script()
    store = PaperStore(paper_db)
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    state_store = LiveStateStore(state_db)
    pipeline = LiveSimPipeline(
        source=MockMarketDataSource(script), engine=engine, strategy=TrendMomentumBaseline(), symbols=["AAPL"], interval="1d",
        require_human_approval=True, state_store=state_store,
        freshness_policy=FreshnessPolicy(multiplier=1_000_000.0), clock=lambda: datetime(2026, 8, 26),
    )
    result = None
    while True:
        result = pipeline.process_next()
        if result.kind in ("PENDING_HUMAN_APPROVAL", "FEED_EXHAUSTED"):
            break
    assert result.kind == "PENDING_HUMAN_APPROVAL"
    signal_id = result.signal.stable_id()

    claim_committed = threading.Event()
    kill_switch_activated = threading.Event()
    original_update_decision = state_store.update_decision

    def _claim_then_wait_for_the_kill_switch(*args, **kwargs):
        original_update_decision(*args, **kwargs)  # the real CAS claim write -- must commit first
        claim_committed.set()
        # Block here -- deliberately -- until the OTHER thread's own,
        # genuinely separate connection has ACTUALLY committed the kill
        # switch activation. Without this wait, the two threads merely
        # race (the activator's own connection-open overhead alone is
        # enough to usually lose), which proves nothing about the
        # property under test; this forces the exact interleaving the
        # mission asks for -- "use synchronization barriers/events so the
        # test controls exact ordering" -- while still exercising a real
        # second thread and a real second SQLite connection, not a
        # single-threaded shortcut.
        assert kill_switch_activated.wait(timeout=15), "the activator thread never completed -- test infrastructure failure, not the property under test"

    state_store.update_decision = _claim_then_wait_for_the_kill_switch

    def _activate_kill_switch_the_instant_the_claim_commits():
        claim_committed.wait(timeout=15)
        activating_store = LiveStateStore(state_db)  # a genuinely separate connection -- a different process/thread
        try:
            activating_store.activate_kill_switch(reason="test: real second thread, real second connection")
        finally:
            activating_store.close()
        kill_switch_activated.set()

    activator = threading.Thread(target=_activate_kill_switch_the_instant_the_claim_commits)
    activator.start()
    try:
        action = pipeline.approve_pending(signal_id)
    finally:
        activator.join(timeout=15)
        state_store.update_decision = original_update_decision

    assert action.outcome.value == "KILL_SWITCH_ACTIVE"

    final_store = PaperStore(paper_db)
    order_exists = final_store.get_pending_order("AAPL") is not None
    final_store.close()
    assert not order_exists, "a kill switch activated during approve_pending's own CAS-claim-to-execution window must never let an order through"
