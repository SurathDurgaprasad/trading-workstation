"""Phase 13 §8: kill switch integration -- prevents NEW paper orders in
BOTH require_human_approval modes, does not touch existing state, survives
restart, requires explicit reset.
"""
from datetime import datetime

import pytest

from live.freshness import FreshnessPolicy
from live.mock_source import MockMarketDataSource
from live.pipeline import ApprovalActionOutcome, LiveSimPipeline
from live.state_store import LiveStateStore
from paper.engine import PaperTradingEngine
from paper.store import PaperStore
from strategy.baseline import TrendMomentumBaseline
from tests.conftest import AAPL_CACHE_PATH, real_aapl_mock_script

pytestmark = pytest.mark.skipif(not AAPL_CACHE_PATH.exists(), reason=f"No cached AAPL data at {AAPL_CACHE_PATH}")
_GENEROUS_FRESHNESS = FreshnessPolicy(multiplier=1_000_000.0)


def _build(tmp_path, *, require_human_approval, kill_active=False):
    script = real_aapl_mock_script()
    store = PaperStore(tmp_path / "p.db")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    state_store = LiveStateStore(tmp_path / "s.db")
    if kill_active:
        state_store.activate_kill_switch(reason="test")
    pipeline = LiveSimPipeline(
        source=MockMarketDataSource(script), engine=engine, strategy=TrendMomentumBaseline(), symbols=["AAPL"], interval="1d",
        require_human_approval=require_human_approval, state_store=state_store,
        freshness_policy=_GENEROUS_FRESHNESS, clock=lambda: datetime(2026, 8, 26),
    )
    return pipeline, engine, store, state_store


def test_kill_switch_blocks_new_auto_execute_signals(tmp_path):
    pipeline, engine, store, state_store = _build(tmp_path, require_human_approval=False, kill_active=True)
    saw_kill_switch = False
    while True:
        result = pipeline.process_next()
        if result.kind == "FEED_EXHAUSTED":
            break
        if result.kind == "KILL_SWITCH_ACTIVE":
            saw_kill_switch = True
    assert saw_kill_switch
    assert len(store.list_journal_entries()) == 0  # no order ever created


def test_kill_switch_blocks_new_pending_approvals(tmp_path):
    pipeline, engine, store, state_store = _build(tmp_path, require_human_approval=True, kill_active=True)
    saw_kill_switch = False
    while True:
        result = pipeline.process_next()
        if result.kind == "FEED_EXHAUSTED":
            break
        if result.kind == "KILL_SWITCH_ACTIVE":
            saw_kill_switch = True
    assert saw_kill_switch
    assert pipeline.pending_approvals == {}


def test_kill_switch_blocks_approving_an_already_pending_signal(tmp_path):
    pipeline, engine, store, state_store = _build(tmp_path, require_human_approval=True, kill_active=False)
    result = None
    while True:
        result = pipeline.process_next()
        if result.kind in ("PENDING_HUMAN_APPROVAL", "FEED_EXHAUSTED"):
            break
    assert result.kind == "PENDING_HUMAN_APPROVAL"
    signal_id = result.signal.stable_id()

    state_store.activate_kill_switch(reason="halt")
    action = pipeline.approve_pending(signal_id)
    assert action.outcome == ApprovalActionOutcome.KILL_SWITCH_ACTIVE
    assert store.get_pending_order("AAPL") is None


def test_kill_switch_does_not_touch_existing_positions(tmp_path):
    """Does not delete state, does not silently close positions -- only
    blocks NEW entries."""
    pipeline, engine, store, state_store = _build(tmp_path, require_human_approval=False, kill_active=False)
    opened = False
    while True:
        result = pipeline.process_next()
        if result.kind == "FEED_EXHAUSTED":
            break
        if store.get_open_position("AAPL") is not None:
            opened = True
            break
    assert opened
    state_store.activate_kill_switch(reason="halt")
    for _ in range(3):
        pipeline.process_next()
    # still open OR closed via its own stop/target, never silently dropped
    assert store.get_open_position("AAPL") is not None or len(store.list_trades()) > 0


def test_kill_switch_state_visible_and_requires_explicit_reset(tmp_path):
    state_store = LiveStateStore(tmp_path / "s.db")
    assert state_store.is_kill_switch_active() is False
    state_store.activate_kill_switch(reason="manual halt")
    assert state_store.is_kill_switch_active() is True
    assert state_store.is_kill_switch_active() is True  # does NOT auto-clear on its own
    state_store.reset_kill_switch()
    assert state_store.is_kill_switch_active() is False
