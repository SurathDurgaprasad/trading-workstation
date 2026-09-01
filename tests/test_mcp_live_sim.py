"""Phase 12: the run_mock_live_simulation_tool MCP tool -- always MOCK/
SIMULATED, always against an ephemeral in-memory engine, never the
persistent paper-trading database.
"""

import pytest

from mcp_server.server import run_mock_live_simulation_tool
from tests.conftest import AAPL_CACHE_PATH

pytestmark = pytest.mark.skipif(not AAPL_CACHE_PATH.exists(), reason=f"No cached AAPL data at {AAPL_CACHE_PATH}")


def test_run_mock_live_simulation_tool_is_always_mock_and_simulated():
    summary = run_mock_live_simulation_tool(symbol="AAPL", interval="1d", period="5y", max_bars=50)
    assert summary.source == "MOCK"
    assert summary.status == "SIMULATED"
    assert summary.symbol == "AAPL"
    assert summary.bars_processed == 50
    assert summary.reconciliation_ok is True


def test_run_mock_live_simulation_tool_does_not_touch_the_persistent_paper_db():
    """The tool must be idempotent-safe to call repeatedly with no
    accumulating side effect on the real paper_trading.db -- proven by
    checking it never even opens that file."""
    import mcp_server.server as server_module

    assert server_module._paper_engine is None  # not lazily created just by calling the mock-sim tool
    run_mock_live_simulation_tool(symbol="AAPL", interval="1d", period="1y", max_bars=5)
    assert server_module._paper_engine is None  # still untouched
