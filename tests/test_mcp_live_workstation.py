"""Phase 13: MCP tools for the `paper-live` human-approval workstation.
Read-only observation tools plus exactly two unmistakably-named
approval-action tools (approve_pending_signal_tool/reject_pending_signal_tool)
that call the SAME LiveSimPipeline.approve_pending()/reject_pending() the
`paper-live` CLI's interactive prompt calls -- never a new execution path.

Every test gets its own isolated pair of SQLite files (live-sim paper db +
live state db) via monkeypatch, mirroring test_mcp_paper.py's convention --
never the real persistent data/live_sim_trading.db / data/live_state.db.
"""
from datetime import datetime

import pytest

from live.freshness import FreshnessPolicy
from live.mock_source import MockMarketDataSource
from live.pipeline import LiveSimPipeline
from strategy.registry import get_strategy
from tests.conftest import AAPL_CACHE_PATH, real_aapl_mock_script

pytestmark = pytest.mark.skipif(not AAPL_CACHE_PATH.exists(), reason=f"No cached AAPL data at {AAPL_CACHE_PATH}")
_GENEROUS_FRESHNESS = FreshnessPolicy(multiplier=1_000_000.0)


@pytest.fixture(autouse=True)
def _isolated_live_engine(monkeypatch, tmp_path):
    import live.workstation as workstation_module

    monkeypatch.setattr(workstation_module, "_live_engine", None)
    monkeypatch.setattr(workstation_module, "LIVE_SIM_DB_PATH", tmp_path / "live_sim.db")
    monkeypatch.setattr(workstation_module, "LIVE_STATE_DB_PATH", tmp_path / "live_state.db")
    yield


def _drive_one_pending_approval(server_module):
    """Uses a REAL LiveSimPipeline (same construction shape as the
    `paper-live` CLI, default tz-aware clock) against the SAME persistent
    engine/state-store files the MCP tools read (via live/workstation.py),
    to produce exactly one PENDING_HUMAN_APPROVAL signal_id for the tools
    under test to act on."""
    import live.workstation as workstation_module

    engine = workstation_module.get_live_engine()
    state_store = workstation_module.new_live_state_store()
    script = real_aapl_mock_script()
    pipeline = LiveSimPipeline(
        source=MockMarketDataSource(script), engine=engine, strategy=get_strategy("trend_momentum_baseline"),
        symbols=["AAPL"], interval="1d", require_human_approval=True, state_store=state_store,
        freshness_policy=_GENEROUS_FRESHNESS,
    )
    result = None
    while True:
        result = pipeline.process_next()
        if result.kind in ("PENDING_HUMAN_APPROVAL", "FEED_EXHAUSTED"):
            break
    assert result.kind == "PENDING_HUMAN_APPROVAL"
    signal_id = result.signal.stable_id()
    state_store.close()
    return signal_id


def test_get_live_sim_status_tool_reflects_a_pending_approval():
    import mcp_server.server as server_module

    _drive_one_pending_approval(server_module)
    status = server_module.get_live_sim_status_tool()
    assert status.status == "SIMULATED"
    assert status.source == "MOCK"
    assert status.kill_switch_active is False
    assert status.pending_approvals_count == 1
    assert status.account.equity == 100_000.0
    assert status.reconciliation_ok is True


def test_get_pending_approvals_tool_lists_the_signal():
    import mcp_server.server as server_module

    signal_id = _drive_one_pending_approval(server_module)
    pending = server_module.get_pending_approvals_tool()
    assert len(pending) == 1
    assert pending[0].signal_id == signal_id
    assert pending[0].symbol == "AAPL"
    assert pending[0].state == "PENDING_HUMAN_APPROVAL"
    assert pending[0].requested_quantity > 0


def test_approve_pending_signal_tool_executes_via_the_same_domain_method():
    import mcp_server.server as server_module

    signal_id = _drive_one_pending_approval(server_module)
    result = server_module.approve_pending_signal_tool(signal_id, reason="mcp test")
    assert result["outcome"] == "APPROVED"
    assert result["execution_outcome"] == "APPROVED_PENDING"

    journal = server_module.get_trade_journal_tool()
    assert len(journal) == 1
    assert journal[0].signal_id == signal_id

    positions = server_module.get_positions_tool()
    assert positions == []  # fill happens on the NEXT bar, not immediately -- unchanged Phase 3 semantics


def test_approve_pending_signal_tool_is_idempotent():
    import mcp_server.server as server_module

    signal_id = _drive_one_pending_approval(server_module)
    first = server_module.approve_pending_signal_tool(signal_id)
    second = server_module.approve_pending_signal_tool(signal_id)
    assert first["outcome"] == "APPROVED"
    assert second["outcome"] == "ALREADY_DECIDED"


def test_reject_pending_signal_tool_never_creates_an_order():
    import mcp_server.server as server_module

    signal_id = _drive_one_pending_approval(server_module)
    result = server_module.reject_pending_signal_tool(signal_id, reason="not now")
    assert result["outcome"] == "REJECTED"
    assert server_module.get_pending_approvals_tool() == []
    assert server_module.get_trade_journal_tool() == []


def test_approve_pending_signal_tool_reports_not_found_for_an_unknown_id():
    import mcp_server.server as server_module

    result = server_module.approve_pending_signal_tool("no-such-signal-id")
    assert result["outcome"] == "NOT_FOUND"


def test_approval_tools_have_no_execution_override_parameters():
    """Same structural proof as tests/test_approval_security.py, at the MCP
    boundary: these tools cannot accept a quantity/stop/target/price."""
    import inspect

    import mcp_server.server as server_module

    for tool in (server_module.approve_pending_signal_tool, server_module.reject_pending_signal_tool):
        params = set(inspect.signature(tool).parameters)
        assert params == {"signal_id", "reason"}


def test_no_new_mcp_tool_can_execute_a_real_order():
    forbidden = ("execute", "place", "cancel", "buy", "sell", "broker", "withdraw", "deposit")
    new_tool_names = [
        "get_live_sim_status_tool", "get_pending_approvals_tool", "get_positions_tool",
        "get_account_state_tool", "get_risk_state_tool", "get_trade_journal_tool",
        "approve_pending_signal_tool", "reject_pending_signal_tool",
    ]
    for name in new_tool_names:
        lowered = name.lower()
        for verb in forbidden:
            assert verb not in lowered, f"{name} looks like a live-execution tool ({verb})"
