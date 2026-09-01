"""Phase 13 §2/§3/§7/§15: the full human-approval workflow through
LiveSimPipeline -- persistence, expiry, idempotency, and the mandatory
second risk check.
"""
from datetime import datetime, timedelta

import pytest

from live.approval import SignalLifecycleState
from live.freshness import FreshnessPolicy
from live.mock_source import MockMarketDataSource
from live.pipeline import ApprovalActionOutcome, LiveSimPipeline
from live.state_store import LiveStateStore
from paper.engine import PaperTradingEngine
from paper.store import PaperStore
from strategy.baseline import TrendMomentumBaseline
from tests.conftest import AAPL_CACHE_PATH, real_aapl_mock_script

pytestmark = pytest.mark.skipif(not AAPL_CACHE_PATH.exists(), reason=f"No cached AAPL data at {AAPL_CACHE_PATH}")

# Real AAPL history spans 2021-2026; freshness isn't what these tests are
# about, so use a generous multiplier -- the same fix Phase 12's own AAPL
# parity test needed (a fixed clock far from early bars would otherwise
# mark them all stale and no signal would ever fire).
_GENEROUS_FRESHNESS = FreshnessPolicy(multiplier=1_000_000.0)


def _pipeline_with_pending_signal(tmp_path, *, approval_timeout_seconds=120.0, clock=None):
    """Drives REAL cached AAPL history through until exactly one
    PENDING_HUMAN_APPROVAL signal exists -- a synthetic flat-price series
    never satisfies TrendMomentumBaseline's SMA20>SMA50 condition, so real
    historical price movement is used instead (spec §16G)."""
    script = real_aapl_mock_script()
    source = MockMarketDataSource(script, clock=clock)
    store = PaperStore(tmp_path / "paper.db")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    state_store = LiveStateStore(tmp_path / "state.db")
    pipeline = LiveSimPipeline(
        source=source, engine=engine, strategy=TrendMomentumBaseline(), symbols=["AAPL"], interval="1d",
        require_human_approval=True, approval_timeout_seconds=approval_timeout_seconds, state_store=state_store,
        freshness_policy=_GENEROUS_FRESHNESS, clock=clock or (lambda: datetime(2026, 8, 26)),
    )
    result = None
    while True:
        result = pipeline.process_next()
        if result.kind in ("PENDING_HUMAN_APPROVAL", "FEED_EXHAUSTED"):
            break
    return pipeline, engine, store, state_store, result


# --- basic flow ------------------------------------------------------------------


def test_qualifying_signal_reaches_pending_human_approval(tmp_path):
    pipeline, engine, store, state_store, result = _pipeline_with_pending_signal(tmp_path)
    assert result.kind == "PENDING_HUMAN_APPROVAL"
    assert result.signal is not None
    assert result.lifecycle.state == SignalLifecycleState.PENDING_HUMAN_APPROVAL
    # No order was created yet -- RISK_APPROVED->EXECUTED shortcut is
    # structurally absent while require_human_approval=True.
    assert store.get_pending_order("AAPL") is None


def test_approve_creates_the_order_via_a_second_real_risk_check(tmp_path):
    pipeline, engine, store, state_store, result = _pipeline_with_pending_signal(tmp_path)
    signal_id = result.signal.stable_id()

    action = pipeline.approve_pending(signal_id)
    assert action.outcome == ApprovalActionOutcome.APPROVED
    assert action.journal_entry.outcome.value == "APPROVED_PENDING"
    assert store.get_pending_order("AAPL") is not None
    assert pipeline.lifecycles[signal_id].state == SignalLifecycleState.EXECUTED


def test_reject_creates_no_order(tmp_path):
    pipeline, engine, store, state_store, result = _pipeline_with_pending_signal(tmp_path)
    signal_id = result.signal.stable_id()

    action = pipeline.reject_pending(signal_id, reason="don't like it")
    assert action.outcome == ApprovalActionOutcome.REJECTED
    assert store.get_pending_order("AAPL") is None
    assert pipeline.lifecycles[signal_id].state == SignalLifecycleState.HUMAN_REJECTED


# --- idempotency (spec §15) -------------------------------------------------------


def test_approving_twice_second_call_is_a_no_op_with_explicit_reason(tmp_path):
    pipeline, engine, store, state_store, result = _pipeline_with_pending_signal(tmp_path)
    signal_id = result.signal.stable_id()

    first = pipeline.approve_pending(signal_id)
    second = pipeline.approve_pending(signal_id)
    assert first.outcome == ApprovalActionOutcome.APPROVED
    assert second.outcome == ApprovalActionOutcome.ALREADY_DECIDED
    assert second.reason is not None
    assert len(store.list_journal_entries()) == 1  # not duplicated


def test_rejecting_twice_second_call_is_a_no_op(tmp_path):
    pipeline, engine, store, state_store, result = _pipeline_with_pending_signal(tmp_path)
    signal_id = result.signal.stable_id()

    first = pipeline.reject_pending(signal_id)
    second = pipeline.reject_pending(signal_id)
    assert first.outcome == ApprovalActionOutcome.REJECTED
    assert second.outcome == ApprovalActionOutcome.ALREADY_DECIDED


def test_approving_an_unknown_signal_id_returns_not_found(tmp_path):
    pipeline, engine, store, state_store, result = _pipeline_with_pending_signal(tmp_path)
    action = pipeline.approve_pending("this-signal-id-never-existed")
    assert action.outcome == ApprovalActionOutcome.NOT_FOUND


def test_approving_an_already_executed_signal_is_no_op(tmp_path):
    pipeline, engine, store, state_store, result = _pipeline_with_pending_signal(tmp_path)
    signal_id = result.signal.stable_id()
    pipeline.approve_pending(signal_id)
    action = pipeline.approve_pending(signal_id)
    assert action.outcome == ApprovalActionOutcome.ALREADY_DECIDED


# --- expiration (spec §7) ----------------------------------------------------------


def test_approval_expires_after_the_configured_timeout(tmp_path):
    now_holder = {"now": datetime(2026, 3, 1, 9, 16)}
    pipeline, engine, store, state_store, result = _pipeline_with_pending_signal(
        tmp_path, approval_timeout_seconds=5.0, clock=lambda: now_holder["now"],
    )
    signal_id = result.signal.stable_id()

    now_holder["now"] += timedelta(seconds=10)  # past the 5s timeout
    expired = pipeline.expire_pending_approvals()
    assert signal_id in expired
    assert pipeline.lifecycles[signal_id].state == SignalLifecycleState.APPROVAL_EXPIRED


def test_expired_approval_cannot_be_approved(tmp_path):
    now_holder = {"now": datetime(2026, 3, 1, 9, 16)}
    pipeline, engine, store, state_store, result = _pipeline_with_pending_signal(
        tmp_path, approval_timeout_seconds=5.0, clock=lambda: now_holder["now"],
    )
    signal_id = result.signal.stable_id()

    now_holder["now"] += timedelta(seconds=10)
    action = pipeline.approve_pending(signal_id)
    assert action.outcome == ApprovalActionOutcome.EXPIRED
    assert store.get_pending_order("AAPL") is None


def test_no_configured_timeout_means_no_expiry(tmp_path):
    now_holder = {"now": datetime(2026, 3, 1, 9, 16)}
    pipeline, engine, store, state_store, result = _pipeline_with_pending_signal(
        tmp_path, approval_timeout_seconds=None, clock=lambda: now_holder["now"],
    )
    signal_id = result.signal.stable_id()
    now_holder["now"] += timedelta(days=365)
    expired = pipeline.expire_pending_approvals()
    assert expired == []
    action = pipeline.approve_pending(signal_id)
    assert action.outcome == ApprovalActionOutcome.APPROVED


# --- persistence / restart (spec §14) -----------------------------------------------


def test_pending_approval_survives_a_process_restart(tmp_path):
    pipeline, engine, store, state_store, result = _pipeline_with_pending_signal(tmp_path)
    signal_id = result.signal.stable_id()
    assert signal_id in pipeline.pending_approvals

    store.close()
    state_store.close()

    # "process restarts" -- fresh objects, same db files
    store2 = PaperStore(tmp_path / "paper.db")
    engine2 = PaperTradingEngine(store2, initial_capital=100_000.0)
    state_store2 = LiveStateStore(tmp_path / "state.db")
    empty_source = MockMarketDataSource([])
    pipeline2 = LiveSimPipeline(
        source=empty_source, engine=engine2, strategy=TrendMomentumBaseline(), symbols=["AAPL"], interval="1d",
        require_human_approval=True, state_store=state_store2, clock=lambda: datetime(2026, 3, 1, 9, 16),
    )

    assert signal_id in pipeline2.pending_approvals
    assert pipeline2.lifecycles[signal_id].state == SignalLifecycleState.PENDING_HUMAN_APPROVAL

    action = pipeline2.approve_pending(signal_id)
    assert action.outcome == ApprovalActionOutcome.APPROVED
    assert store2.get_pending_order("AAPL") is not None


def test_expired_approval_state_survives_restart(tmp_path):
    now_holder = {"now": datetime(2026, 3, 1, 9, 16)}
    pipeline, engine, store, state_store, result = _pipeline_with_pending_signal(
        tmp_path, approval_timeout_seconds=5.0, clock=lambda: now_holder["now"],
    )
    signal_id = result.signal.stable_id()
    now_holder["now"] += timedelta(seconds=10)
    pipeline.expire_pending_approvals()
    store.close()
    state_store.close()

    record = LiveStateStore(tmp_path / "state.db").get(signal_id)
    assert record.state == "APPROVAL_EXPIRED"
    assert record.decision == "EXPIRED"
