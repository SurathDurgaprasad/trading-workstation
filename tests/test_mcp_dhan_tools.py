"""Phase 15 §21/§23: MCP read-only Dhan tools. No place_order/modify_order/
cancel_order tool exists here or anywhere in the server -- proven both
structurally (test_no_new_dhan_mcp_tool_can_execute_a_real_order) and by
the fact that get_dhan_account_funds_tool/get_dhan_account_positions_tool
only ever call DhanAccountReader, whose only methods are GETs.
"""
import io

import pandas as pd
import pytest

from live.dhan.instruments import DhanInstrumentMap

_FIXTURE_CSV = """SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_INSTRUMENT_NAME,SEM_EXPIRY_CODE,SEM_TRADING_SYMBOL,SEM_LOT_UNITS,SEM_CUSTOM_SYMBOL,SEM_EXPIRY_DATE,SEM_STRIKE_PRICE,SEM_OPTION_TYPE,SEM_TICK_SIZE,SEM_EXPIRY_FLAG,SEM_EXCH_INSTRUMENT_TYPE,SEM_SERIES,SM_SYMBOL_NAME
NSE,E,2885,EQUITY,0,RELIANCE,1.0,Reliance Industries,,,,10.0000,NA,ES,EQ,RELIANCE INDUSTRIES LTD
"""


@pytest.fixture(autouse=True)
def _isolated_live_engine(monkeypatch, tmp_path):
    import live.workstation as workstation_module

    monkeypatch.setattr(workstation_module, "_live_engine", None)
    monkeypatch.setattr(workstation_module, "LIVE_SIM_DB_PATH", tmp_path / "live_sim.db")
    monkeypatch.setattr(workstation_module, "LIVE_STATE_DB_PATH", tmp_path / "live_state.db")
    yield


def test_get_live_market_status_tool_is_empty_when_nothing_processed():
    import mcp_server.server as server_module

    assert server_module.get_live_market_status_tool() == []


def test_get_live_market_status_tool_reflects_a_written_feed_status():
    import mcp_server.server as server_module
    import live.workstation as workstation_module
    from datetime import datetime, timezone

    state_store = workstation_module.new_live_state_store()
    now = datetime.now(timezone.utc)
    state_store.save_feed_status(symbol="RELIANCE.NS", source="DHAN", status="LIVE", bar_timestamp=now, received_at=now, connection_state="CONNECTED")
    state_store.close()

    rows = server_module.get_live_market_status_tool()
    assert len(rows) == 1
    assert rows[0]["symbol"] == "RELIANCE.NS"
    assert rows[0]["source"] == "DHAN"
    assert rows[0]["status"] == "LIVE"
    assert rows[0]["connection_state"] == "CONNECTED"


def test_get_dhan_account_funds_tool_raises_a_clean_tool_error_without_credentials(monkeypatch):
    from mcp.server.fastmcp.exceptions import ToolError

    monkeypatch.delenv("DHAN_CLIENT_ID", raising=False)
    monkeypatch.delenv("DHAN_ACCESS_TOKEN", raising=False)
    import mcp_server.server as server_module

    with pytest.raises(ToolError):
        server_module.get_dhan_account_funds_tool()


def test_get_dhan_account_positions_tool_raises_a_clean_tool_error_without_credentials(monkeypatch):
    from mcp.server.fastmcp.exceptions import ToolError

    monkeypatch.delenv("DHAN_CLIENT_ID", raising=False)
    monkeypatch.delenv("DHAN_ACCESS_TOKEN", raising=False)
    import mcp_server.server as server_module

    with pytest.raises(ToolError):
        server_module.get_dhan_account_positions_tool()


def test_get_dhan_account_funds_tool_maps_a_real_shaped_response(monkeypatch):
    """Injects a fake HTTP GET via DhanRestClient's own injectable
    http_get, proving the MCP tool's plumbing end to end without a real
    network call."""
    monkeypatch.setenv("DHAN_CLIENT_ID", "1000000009")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "fake-token")

    from live.dhan.rest_client import DhanRestClient

    fake_body = {
        "dhanClientId": "1000000009", "availabelBalance": 98440.0, "sodLimit": 113642, "collateralAmount": 0.0,
        "receiveableAmount": 0.0, "utilizedAmount": 15202.0, "blockedPayoutAmount": 0.0, "withdrawableBalance": 98310.0,
    }
    original_init = DhanRestClient.__init__

    def _patched_init(self, credentials, **kwargs):
        original_init(self, credentials=credentials, http_get=lambda url, headers: (200, fake_body))

    monkeypatch.setattr(DhanRestClient, "__init__", _patched_init)

    import mcp_server.server as server_module

    result = server_module.get_dhan_account_funds_tool()
    assert result["available_balance"] == 98440.0
    assert result["dhan_client_id"] == "1000000009"


def test_no_new_dhan_mcp_tool_can_execute_a_real_order():
    forbidden = ("execute", "place", "cancel", "buy", "sell", "broker", "withdraw", "deposit", "modify")
    new_tool_names = ["get_live_market_status_tool", "get_dhan_account_funds_tool", "get_dhan_account_positions_tool"]
    for name in new_tool_names:
        lowered = name.lower()
        for verb in forbidden:
            assert verb not in lowered, f"{name} looks like a live-execution tool ({verb})"
