"""Phase 7A §10/§11: the submit_paper_market_bar_tool MCP tool -- direct-call
security/idempotency checks plus a real stdio subprocess round trip, mirroring
tests/test_mcp_paper.py's structure for paper_trade_signal_tool.
"""

import asyncio
import os
import sys

import pytest

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from mcp_server.server import submit_paper_market_bar_tool
from market.data_provider import OHLCVBar


def _bar(**overrides) -> OHLCVBar:
    base = dict(timestamp="2026-01-02T00:00:00", open=101.0, high=101.5, low=100.5, close=101.0, volume=1_000_000.0)
    base.update(overrides)
    return OHLCVBar(**base)


@pytest.fixture(autouse=True)
def _isolated_paper_engine(monkeypatch, tmp_path):
    import mcp_server.server as server_module

    monkeypatch.setattr(server_module, "_paper_engine", None)
    monkeypatch.setattr(server_module, "PAPER_DB_PATH", tmp_path / "isolated_bar.db")
    yield


# --- direct-call tests --------------------------------------------------------


def test_submit_bar_tool_is_idempotent_over_the_same_timestamp():
    bar = _bar()
    first = submit_paper_market_bar_tool(symbol="TEST", bar=bar)
    second = submit_paper_market_bar_tool(symbol="TEST", bar=bar)
    assert first == "PROCESSED"
    assert second == "DUPLICATE_SKIPPED"


def test_submit_bar_tool_rejects_an_out_of_order_bar_with_a_tool_error():
    from mcp.server.fastmcp.exceptions import ToolError

    submit_paper_market_bar_tool(symbol="TEST", bar=_bar(timestamp="2026-01-05T00:00:00"))
    with pytest.raises(ToolError):
        submit_paper_market_bar_tool(symbol="TEST", bar=_bar(timestamp="2026-01-03T00:00:00"))


def test_submit_bar_tool_reuses_the_real_ohlcv_model_not_a_second_schema():
    """Spec §2's reuse preference, verified structurally: the tool's `bar`
    parameter type is market.data_provider.OHLCVBar, not a new model."""
    import inspect

    sig = inspect.signature(submit_paper_market_bar_tool)
    assert sig.parameters["bar"].annotation is OHLCVBar


# --- real stdio subprocess test -----------------------------------------------


def test_real_mcp_client_bar_submission_is_idempotent(tmp_path):
    db_path = tmp_path / "mcp_bar_idempotency.db"

    async def _run():
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "mcp_server.server"],
            env={**os.environ, "TRADING_PAPER_DB_PATH": str(db_path)},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                bar_payload = {
                    "timestamp": "2026-01-02T00:00:00", "open": 101.0, "high": 101.5,
                    "low": 100.5, "close": 101.0, "volume": 1_000_000.0,
                }
                first = await session.call_tool("submit_paper_market_bar_tool", {"symbol": "TEST", "bar": bar_payload})
                second = await session.call_tool("submit_paper_market_bar_tool", {"symbol": "TEST", "bar": bar_payload})
                status = await session.call_tool("get_paper_status_tool", {})
                return first.structuredContent, second.structuredContent, status.structuredContent

    first, second, status = asyncio.run(_run())
    assert first.get("result") == "PROCESSED"
    assert second.get("result") == "DUPLICATE_SKIPPED"
    # No signal was ever submitted -- this tool only advances bar state.
    assert status["total_journal_entries"] == 0


def test_real_mcp_client_out_of_order_bar_is_a_structured_error(tmp_path):
    db_path = tmp_path / "mcp_bar_ordering.db"

    async def _run():
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "mcp_server.server"],
            env={**os.environ, "TRADING_PAPER_DB_PATH": str(db_path)},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool("submit_paper_market_bar_tool", {
                    "symbol": "TEST",
                    "bar": {"timestamp": "2026-01-05T00:00:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0},
                })
                result = await session.call_tool("submit_paper_market_bar_tool", {
                    "symbol": "TEST",
                    "bar": {"timestamp": "2026-01-03T00:00:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0},
                })
                return result

    result = asyncio.run(_run())
    assert result.isError
