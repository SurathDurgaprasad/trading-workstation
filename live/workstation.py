"""Phase 13 — the ONE place that owns access to the persistent `paper-live`
workstation state (the live-sim paper account + the pending-approval/kill-
switch state store). Both mcp_server/server.py's Phase 13 tools and the new
dashboard/app.py import from here rather than each re-implementing engine
lookup, pending-approval restoration, or the approve/reject call — "no
business logic in UI handlers" (spec) applies just as much to the MCP layer
as to the dashboard.

Every function here either reads existing persisted state directly or calls
straight into live.pipeline.LiveSimPipeline.approve_pending()/
reject_pending() — the same domain methods the `paper-live` CLI's
interactive Y/N prompt calls. Nothing here recomputes a risk decision, a
signal, or an account balance, and nothing here can accept a
quantity/stop/target/price override (approve_pending_signal/
reject_pending_signal's own signatures make that impossible — see
tests/test_approval_security.py).
"""

import os
from pathlib import Path

from core.config import PROJECT_ROOT
from paper.engine import PaperTradingEngine
from paper.reconciliation import reconcile
from paper.store import PaperStore
from strategy.registry import get_strategy

LIVE_SIM_DB_PATH = Path(os.environ["TRADING_LIVE_SIM_DB_PATH"]) if "TRADING_LIVE_SIM_DB_PATH" in os.environ else PROJECT_ROOT / "data" / "live_sim_trading.db"
LIVE_STATE_DB_PATH = Path(os.environ["TRADING_LIVE_STATE_DB_PATH"]) if "TRADING_LIVE_STATE_DB_PATH" in os.environ else PROJECT_ROOT / "data" / "live_state.db"

_live_engine: PaperTradingEngine | None = None


def get_live_engine() -> PaperTradingEngine:
    global _live_engine
    if _live_engine is None:
        LIVE_SIM_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _live_engine = PaperTradingEngine(PaperStore(LIVE_SIM_DB_PATH))
    return _live_engine


def new_live_state_store():
    from live.state_store import LiveStateStore

    LIVE_STATE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return LiveStateStore(LIVE_STATE_DB_PATH)


def terminal_status_shortcut(signal_id: str, state_store) -> str | None:
    """Read-only lookup of the PERSISTED decision state for `signal_id`.
    Returns a terminal outcome string (NOT_FOUND/EXPIRED/ALREADY_DECIDED) if
    the record already shows one, else None if it is genuinely still
    PENDING_HUMAN_APPROVAL (actionable). This never decides anything itself
    — it only lets callers short-circuit a doomed pipeline call with the
    same answer LiveSimPipeline._check_actionable() would give, computed
    from the one source of truth (the persisted row) rather than from a
    freshly-built pipeline's necessarily-empty in-memory history."""
    record = state_store.get(signal_id)
    if record is None:
        return "NOT_FOUND"
    if record.state == "PENDING_HUMAN_APPROVAL":
        return None
    if record.state == "APPROVAL_EXPIRED":
        return "EXPIRED"
    return "ALREADY_DECIDED"


def build_approval_pipeline(state_store, strategy_name: str = "trend_momentum_baseline"):
    """A fresh LiveSimPipeline, rebuilt per call so its restored
    pending-approval state always reflects the CURRENT contents of the
    shared LiveStateStore (which the paper-live CLI, or another caller, may
    have changed since this process started). Uses an empty
    MockMarketDataSource — callers of this only invoke approve_pending()/
    reject_pending(), never process_next(), so no script events are needed."""
    from live.mock_source import MockMarketDataSource
    from live.pipeline import LiveSimPipeline

    source = MockMarketDataSource([])
    return LiveSimPipeline(
        source=source, engine=get_live_engine(), strategy=get_strategy(strategy_name),
        symbols=[], interval="1d", require_human_approval=True, state_store=state_store,
    )


def activate_kill_switch(reason: str = "manual activation") -> None:
    state_store = new_live_state_store()
    try:
        state_store.activate_kill_switch(reason=reason)
    finally:
        state_store.close()


def reset_kill_switch() -> None:
    state_store = new_live_state_store()
    try:
        state_store.reset_kill_switch()
    finally:
        state_store.close()


def get_live_sim_status() -> dict:
    engine = get_live_engine()
    state_store = new_live_state_store()
    try:
        active, _, reason = state_store.kill_switch_state()
        pending_count = len(state_store.list_pending())
    finally:
        state_store.close()
    report = reconcile(engine.store)
    return {
        "status": "SIMULATED",
        "source": "MOCK",
        "kill_switch_active": active,
        "kill_switch_reason": reason,
        "pending_approvals_count": pending_count,
        "account": engine.account,
        "open_positions_count": sum(1 for p in engine.store.list_positions() if p.status.value == "OPEN"),
        "reconciliation_ok": report.ok,
    }


def get_pending_approvals() -> list:
    """Returns live.state_store.PendingApprovalRecord objects, read directly
    from the persistent LiveStateStore — read-only."""
    state_store = new_live_state_store()
    try:
        return state_store.list_pending()
    finally:
        state_store.close()


def get_positions() -> list:
    return [p for p in get_live_engine().store.list_positions() if p.status.value == "OPEN"]


def get_account_state():
    return get_live_engine().account


def get_risk_state() -> dict:
    engine = get_live_engine()
    account = engine.account
    config = engine.risk_engine.config
    return {
        "consecutive_losses": account.consecutive_losses,
        "max_consecutive_losses": config.max_consecutive_losses,
        "consecutive_loss_hard_limit": config.consecutive_loss_hard_limit,
        "current_drawdown_pct": account.current_drawdown_pct,
        "max_drawdown_pct": config.max_drawdown_pct,
        "daily_pnl": account.daily_pnl,
        "max_daily_loss_pct": config.max_daily_loss_pct,
        "open_positions": account.open_positions,
    }


def get_trade_journal() -> list:
    return get_live_engine().store.list_journal_entries()


def get_feed_status() -> list:
    """Phase 15 §7/§22: returns live.state_store.FeedStatusRecord objects
    -- read-only, the ONLY honest source of "what did the market feed most
    recently deliver" for a process (dashboard/MCP) that isn't itself
    running the feed. Never fabricated: an empty list means no bar has
    ever been processed with a state_store attached, not "the feed is
    down" -- see individual records' own connection_state for that."""
    state_store = new_live_state_store()
    try:
        return state_store.list_feed_status()
    finally:
        state_store.close()


def approve_pending_signal(signal_id: str, reason: str | None = None) -> dict:
    state_store = new_live_state_store()
    try:
        shortcut = terminal_status_shortcut(signal_id, state_store)
        if shortcut is not None:
            return {"outcome": shortcut, "signal_id": signal_id, "reason": None, "execution_outcome": None}
        pipeline = build_approval_pipeline(state_store)
        result = pipeline.approve_pending(signal_id, reason=reason)
        return {
            "outcome": result.outcome.value, "signal_id": result.signal_id, "reason": result.reason,
            "execution_outcome": result.journal_entry.outcome.value if result.journal_entry else None,
        }
    finally:
        state_store.close()


def reject_pending_signal(signal_id: str, reason: str | None = None) -> dict:
    state_store = new_live_state_store()
    try:
        shortcut = terminal_status_shortcut(signal_id, state_store)
        if shortcut is not None:
            return {"outcome": shortcut, "signal_id": signal_id, "reason": None}
        pipeline = build_approval_pipeline(state_store)
        result = pipeline.reject_pending(signal_id, reason=reason)
        return {"outcome": result.outcome.value, "signal_id": result.signal_id, "reason": result.reason}
    finally:
        state_store.close()
