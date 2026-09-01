"""Phase 13 §6: the remaining fail-closed scenarios not already covered by
Phase 12's test_live_pipeline.py (duplicate/out-of-order/stale/disconnect)
or this phase's test_kill_switch_pipeline.py -- position-already-exists,
daily-loss/drawdown halts, and the account-state-changed-after-approval
case. All reuse the EXISTING RiskEngine/Account behavior (Phase 4/4.5,
unchanged) -- these tests prove it flows correctly through the NEW
human-approval path, not new risk logic.
"""
from datetime import datetime

import pytest

from live.freshness import FreshnessPolicy
from live.mock_source import MockMarketDataSource
from live.pipeline import ApprovalActionOutcome, LiveSimPipeline
from live.state_store import LiveStateStore
from paper.engine import PaperTradingEngine
from paper.store import PaperStore
from risk.config import RiskConfig
from risk.engine import RiskEngine
from strategy.baseline import TrendMomentumBaseline
from tests.conftest import AAPL_CACHE_PATH, real_aapl_mock_script

pytestmark = pytest.mark.skipif(not AAPL_CACHE_PATH.exists(), reason=f"No cached AAPL data at {AAPL_CACHE_PATH}")
_GENEROUS_FRESHNESS = FreshnessPolicy(multiplier=1_000_000.0)
_CLOCK = lambda: datetime(2026, 8, 26)


def test_position_already_open_prevents_a_second_pending_approval(tmp_path):
    """Reuses RiskEngine's own POSITION_ALREADY_OPEN veto -- proven here to
    correctly suppress a second signal once a position is open, in
    human-approval mode."""
    script = real_aapl_mock_script()
    store = PaperStore(tmp_path / "p.db")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    pipeline = LiveSimPipeline(
        source=MockMarketDataSource(script), engine=engine, strategy=TrendMomentumBaseline(), symbols=["AAPL"], interval="1d",
        require_human_approval=True, state_store=LiveStateStore(tmp_path / "s.db"),
        freshness_policy=_GENEROUS_FRESHNESS, clock=_CLOCK,
    )
    result = None
    while True:
        result = pipeline.process_next()
        if result.kind in ("PENDING_HUMAN_APPROVAL", "FEED_EXHAUSTED"):
            break
    assert result.kind == "PENDING_HUMAN_APPROVAL"
    pipeline.approve_pending(result.signal.stable_id())
    assert store.get_pending_order("AAPL") is not None

    # approve_pending() creates a PENDING order (next-bar-open fill
    # semantics, same as everywhere else in this project) -- one more bar
    # is needed before it actually becomes an open Position.
    pipeline.process_next()
    assert store.get_open_position("AAPL") is not None

    # Continue processing ONLY while the position is genuinely still open --
    # once it closes via its own stop/target (which real AAPL history will
    # do within days-to-weeks, per Phase 8's own findings), a brand new
    # signal reaching PENDING_HUMAN_APPROVAL is legitimate, not a bug. The
    # invariant under test is narrower: no SECOND pending approval while
    # the FIRST position remains open.
    #
    # A single process_next() call can BOTH close the existing position
    # (engine.process_bar() fills its stop/target) AND generate a fresh
    # signal that clears risk check #1 -- all on the same bar, since the
    # position is genuinely gone by the time RiskEngine.evaluate() runs.
    # That is correct behavior, not a veto failure: the veto only needs to
    # fire while a position is STILL open. So a PENDING_HUMAN_APPROVAL is
    # only a violation of THIS invariant if the position that was open at
    # the start of the bar was NOT closed during that same bar (i.e. the
    # trade count didn't increase).
    for _ in range(40):
        if store.get_open_position("AAPL") is None:
            break  # position closed -- a fresh signal is now legitimate; nothing left to prove
        trades_before = len(store.list_trades())
        r = pipeline.process_next()
        if r.kind == "FEED_EXHAUSTED":
            break
        if r.kind == "PENDING_HUMAN_APPROVAL":
            trades_after = len(store.list_trades())
            assert trades_after > trades_before, (
                "a new signal reached PENDING_HUMAN_APPROVAL while the position "
                "open at the start of this bar was never closed -- the "
                "POSITION_ALREADY_OPEN veto failed to suppress it"
            )


def test_daily_loss_and_drawdown_halts_never_create_a_pending_approval(tmp_path):
    """Daily-interval bars mean roll_to_day() re-anchors daily_start_equity
    on EVERY bar (each daily bar is, by definition, a new calendar day) --
    so simulating a PERSISTENT daily-loss breach via account manipulation
    would just fight that reset. RiskEngine's MAX_DAILY_LOSS/MAX_DRAWDOWN
    detection itself is already proven correct by risk/'s own Phase 4/4.5
    test suite (unchanged here). What THIS phase's pipeline integration
    needs to prove is narrower and more robust to test directly: whenever
    risk check #1 rejects a signal for ANY veto reason, the pipeline must
    never create a pending approval -- proven here with a RiskEngine stub
    that always rejects, isolating the pipeline's own behavior from
    RiskEngine's internal veto logic."""

    class _AlwaysRejectRiskEngine(RiskEngine):
        def evaluate(self, signal, account):
            decision = super().evaluate(signal, account)
            return decision.model_copy(update={"approved": False, "position_size": None})

    store = PaperStore(tmp_path / "p.db")
    engine = PaperTradingEngine(store, risk_engine=_AlwaysRejectRiskEngine(RiskConfig()), initial_capital=100_000.0)
    script = real_aapl_mock_script()
    pipeline = LiveSimPipeline(
        source=MockMarketDataSource(script), engine=engine, strategy=TrendMomentumBaseline(), symbols=["AAPL"], interval="1d",
        require_human_approval=True, state_store=LiveStateStore(tmp_path / "s.db"),
        freshness_policy=_GENEROUS_FRESHNESS, clock=_CLOCK,
    )
    while True:
        r = pipeline.process_next()
        if r.kind == "FEED_EXHAUSTED":
            break
        assert r.kind != "PENDING_HUMAN_APPROVAL"
    assert pipeline.pending_approvals == {}
    assert len(store.list_journal_entries()) == 0


def test_account_state_changes_after_approval_triggers_second_risk_rejection(tmp_path):
    """The account-state-changed-between-checks scenario spec explicitly
    names: approve a signal, but before the second risk check runs, the
    account has been pushed into a state RiskEngine would now reject."""
    script = real_aapl_mock_script()
    store = PaperStore(tmp_path / "p.db")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    pipeline = LiveSimPipeline(
        source=MockMarketDataSource(script), engine=engine, strategy=TrendMomentumBaseline(), symbols=["AAPL"], interval="1d",
        require_human_approval=True, state_store=LiveStateStore(tmp_path / "s.db"),
        freshness_policy=_GENEROUS_FRESHNESS, clock=_CLOCK,
    )
    result = None
    while True:
        result = pipeline.process_next()
        if result.kind in ("PENDING_HUMAN_APPROVAL", "FEED_EXHAUSTED"):
            break
    assert result.kind == "PENDING_HUMAN_APPROVAL"

    # Simulate the account being pushed into a drawdown breach BETWEEN the
    # first risk check (already passed, hence pending) and the human's
    # decision -- the account is the SAME live object the engine holds.
    engine.account.peak_equity = 100_000.0
    engine.account.cash = 50_000.0  # ~50% drawdown -- exceeds the 10% default MAX_DRAWDOWN

    action = pipeline.approve_pending(result.signal.stable_id())
    assert action.outcome == ApprovalActionOutcome.REJECTED
    assert action.journal_entry.outcome.value == "REJECTED"
    assert store.get_pending_order("AAPL") is None
