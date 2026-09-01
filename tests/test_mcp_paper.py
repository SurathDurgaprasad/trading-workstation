"""Level 5: real MCP stdio subprocess/client tests for the Phase 6 paper-
trading tools. Each test gets its own isolated SQLite file via the
TRADING_PAPER_DB_PATH env var (mcp_server/server.py honors it) — never the
real persistent data/paper_trading.db.
"""

import asyncio
import sys

import pytest

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.server.fastmcp.exceptions import ToolError

from paper.models import JournalOutcome
from mcp_server.server import get_account_tool, get_paper_status_tool, paper_trade_signal_tool
from strategy.signal import ReasonCode, Side, Signal


def _signal(**overrides) -> Signal:
    base = dict(
        symbol="TEST", generated_at="2026-01-01T00:00:00", side=Side.LONG,
        reference_price=100.0, stop_price=95.0, target_price=110.0, risk_reward=2.0,
        strategy_name="unit-test", reason_codes=[ReasonCode.TREND_CONFIRMED],
    )
    base.update(overrides)
    return Signal(**base)


@pytest.fixture(autouse=True)
def _isolated_paper_engine(monkeypatch, tmp_path):
    """Every direct-call test in this file gets a fresh in-process engine —
    the stdio subprocess tests get their own isolation via the env var."""
    import mcp_server.server as server_module

    monkeypatch.setattr(server_module, "_paper_engine", None)
    monkeypatch.setattr(server_module, "PAPER_DB_PATH", tmp_path / "isolated.db")
    yield


# --- direct-call tests (fast) ------------------------------------------------


def test_paper_trade_signal_tool_is_idempotent():
    signal = _signal()
    j1 = paper_trade_signal_tool(signal=signal)
    j2 = paper_trade_signal_tool(signal=signal)
    assert j1.journal_entry_id == j2.journal_entry_id
    assert j1.outcome == JournalOutcome.APPROVED_PENDING


def test_paper_trade_signal_tool_recomputes_risk_never_trusts_the_caller():
    """Spec §20: the tool signature doesn't even ACCEPT a client-supplied
    quantity/approved/risk value — Signal has no such fields, so there is
    nothing to "trust" in the first place. This test proves the RiskDecision
    used is the real RiskEngine's own, by checking it against a direct call."""
    from risk.account import new_account
    from risk.engine import RiskEngine

    signal = _signal()
    journal = paper_trade_signal_tool(signal=signal)

    import mcp_server.server as server_module
    engine = server_module._get_paper_engine()
    stored_decision = engine.store.get_risk_decision(journal.risk_decision_id)

    direct_decision = RiskEngine().evaluate(signal, new_account(100_000.0))
    assert stored_decision.model_dump() == direct_decision.model_dump()


def test_get_account_tool_reflects_a_paper_trade():
    paper_trade_signal_tool(signal=_signal())
    account = get_account_tool()
    assert account.equity == 100_000.0  # nothing filled yet, still pending

    status = get_paper_status_tool()
    assert status.total_journal_entries == 1
    assert status.total_trades == 0


def test_paper_trade_signal_tool_rejects_a_structurally_invalid_signal_cleanly():
    # side/target/stop validity is enforced by RiskEngine, surfaced as a
    # REJECTED journal entry, not a crash.
    journal = paper_trade_signal_tool(signal=_signal(stop_price=105.0))  # stop above entry -- invalid for LONG
    assert journal.outcome == JournalOutcome.REJECTED


# --- real stdio subprocess tests ---------------------------------------------


def test_real_mcp_client_duplicate_paper_trade_request_is_idempotent(tmp_path):
    """Spec §21: two real MCP calls, same signal -> one paper trade."""
    db_path = tmp_path / "mcp_idempotency.db"

    async def _run():
        import os

        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_server.server"],
            env={**os.environ, "TRADING_PAPER_DB_PATH": str(db_path)},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                signal_payload = {
                    "symbol": "AAPL", "generated_at": "2026-01-01T00:00:00", "side": "LONG",
                    "reference_price": 200.0, "stop_price": 195.0, "target_price": 210.0,
                    "risk_reward": 2.0, "strategy_name": "unit-test", "reason_codes": ["TREND_CONFIRMED"],
                }

                first = await session.call_tool("paper_trade_signal_tool", {"signal": signal_payload})
                second = await session.call_tool("paper_trade_signal_tool", {"signal": signal_payload})

                status = await session.call_tool("get_paper_status_tool", {})
                return first.structuredContent, second.structuredContent, status.structuredContent

    first, second, status = asyncio.run(_run())
    assert first["journal_entry_id"] == second["journal_entry_id"]
    assert status["total_journal_entries"] == 1  # NOT 2


def test_real_mcp_client_can_read_account_and_status(tmp_path):
    db_path = tmp_path / "mcp_status.db"

    async def _run():
        import os

        params = StdioServerParameters(
            command=sys.executable, args=["-m", "mcp_server.server"],
            env={**os.environ, "TRADING_PAPER_DB_PATH": str(db_path)},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = {t.name for t in (await session.list_tools()).tools}
                account = await session.call_tool("get_account_tool", {})
                positions = await session.call_tool("get_open_positions_tool", {})
                trades = await session.call_tool("get_trade_history_tool", {})
                return tools, account.structuredContent, positions, trades

    tools, account, positions, trades = asyncio.run(_run())
    assert {"paper_trade_signal_tool", "get_account_tool", "get_open_positions_tool", "get_trade_history_tool", "get_journal_entry_tool", "get_paper_status_tool"} <= tools
    assert account["cash"] == 100_000.0


def test_no_mcp_tool_can_execute_a_real_order():
    """Static security check, re-verified for Phase 6's additions
    specifically (Phase 5's version already covers the original 4)."""
    tool_names = [t.name for t in asyncio.run(_list_tools())]
    forbidden = ("execute", "place", "cancel", "buy", "sell", "broker", "withdraw", "deposit")
    for name in tool_names:
        lowered = name.lower()
        for verb in forbidden:
            assert verb not in lowered, f"{name} looks like a live-execution tool ({verb})"
    assert len(tool_names) == 20  # 4 (Phase 5) + 6 (Phase 6) + 1 (Phase 7A) + 1 (Phase 12) + 8 (Phase 13)


async def _list_tools():
    from mcp_server.server import mcp

    return await mcp.list_tools()
