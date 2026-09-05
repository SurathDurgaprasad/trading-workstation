"""Phase 13 §19: the minimal local dashboard. Uses Starlette's TestClient
(httpx-backed, no real network/socket) against the SAME live/workstation.py
functions the CLI and MCP tools use -- proving the dashboard's route
handlers contain no business logic of their own (approve/reject route to
live.workstation.approve_pending_signal()/reject_pending_signal(), the exact
same functions tests/test_mcp_live_workstation.py already proves call the
real LiveSimPipeline.approve_pending()/reject_pending()).
"""
import pytest
from starlette.testclient import TestClient

from live.freshness import FreshnessPolicy
from live.mock_source import MockMarketDataSource
from live.pipeline import LiveSimPipeline
from strategy.registry import get_strategy
from tests.conftest import AAPL_CACHE_PATH, real_aapl_mock_script

pytestmark = pytest.mark.skipif(not AAPL_CACHE_PATH.exists(), reason=f"No cached AAPL data at {AAPL_CACHE_PATH}")
_GENEROUS_FRESHNESS = FreshnessPolicy(multiplier=1_000_000.0)


@pytest.fixture(autouse=True)
def _isolated_live_engine(monkeypatch, tmp_path):
    """Starlette's TestClient dispatches each request through anyio's
    thread-portal, and does not guarantee the same OS thread across
    separate .get()/.post() calls -- sqlite3 connections are not
    thread-safe across such calls by default. In real deployment this
    never matters (the `paper-live` CLI, the MCP server, and the dashboard
    are always separate single-threaded OS processes, each opening its own
    connection once); disabling the module-level engine cache here just
    makes every call open its own short-lived connection to the SAME
    on-disk file, which is safe and reproduces that same
    separate-connection shape for the test."""
    import live.workstation as workstation_module
    from paper.engine import PaperTradingEngine
    from paper.store import PaperStore

    live_sim_path = tmp_path / "live_sim.db"
    monkeypatch.setattr(workstation_module, "LIVE_SIM_DB_PATH", live_sim_path)
    monkeypatch.setattr(workstation_module, "LIVE_STATE_DB_PATH", tmp_path / "live_state.db")
    monkeypatch.setattr(workstation_module, "get_live_engine", lambda: PaperTradingEngine(PaperStore(live_sim_path)))
    yield


@pytest.fixture
def client():
    from dashboard.app import app

    return TestClient(app)


def _drive_one_pending_approval():
    """Drives a real LiveSimPipeline to produce one PENDING_HUMAN_APPROVAL
    signal, exactly like the `paper-live` CLI process would -- against the
    same on-disk SQLite file the dashboard reads (see the
    _isolated_live_engine fixture for why engine caching is disabled for
    these tests)."""
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


def test_index_renders_empty_workstation(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "SIMULATED PAPER TRADING" in response.text
    assert "No signals pending human approval." in response.text
    assert "No open positions." in response.text
    # Phase 26: the new /intelligence page must be linked from here.
    assert 'href="/intelligence"' in response.text


def test_index_shows_initial_capital_and_realized_pnl(client):
    """Mission requirement: the dashboard's ACCOUNT section must show
    starting capital and realized P&L, not just cash/equity/open P&L --
    an operator watching ₹20,000 simulated capital needs to see what it
    started as, not infer it from equity minus P&L by hand."""
    response = client.get("/")
    assert "Initial Capital" in response.text
    assert "100,000.00" in response.text  # this fixture's engine uses PaperTradingEngine's own default
    assert "Realized P&amp;L" in response.text or "Realized P&L" in response.text


def test_index_shows_no_feed_data_when_nothing_processed_yet(client):
    """Phase 15 §7/§22: absence of a feed_status row must never be
    silently filled in with a fabricated MOCK/SIMULATED default."""
    response = client.get("/")
    assert "No market data processed yet in this session" in response.text


def test_index_shows_real_feed_status_once_written(client):
    """Directly exercises live.workstation.get_feed_status() through the
    dashboard -- proving MOCK vs. DHAN and SIMULATED vs. LIVE are both
    genuinely distinguished in the rendered page, never hardcoded."""
    import live.workstation as workstation_module

    state_store = workstation_module.new_live_state_store()
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    state_store.save_feed_status(symbol="RELIANCE.NS", source="DHAN", status="LIVE", bar_timestamp=now, received_at=now, connection_state="CONNECTED")
    state_store.close()

    response = client.get("/")
    assert "RELIANCE.NS" in response.text
    assert "DHAN" in response.text
    assert "LIVE" in response.text
    assert "CONNECTED" in response.text


def test_banner_says_not_connected_when_no_feed_status_exists(client):
    response = client.get("/")
    assert "NOT connected to a live broker or feed" in response.text
    assert "No real order can ever be placed here" in response.text


def test_banner_says_not_connected_when_only_a_mock_feed_is_present(client):
    import live.workstation as workstation_module
    from datetime import datetime, timezone

    state_store = workstation_module.new_live_state_store()
    now = datetime.now(timezone.utc)
    state_store.save_feed_status(symbol="AAPL", source="MOCK", status="SIMULATED", bar_timestamp=now, received_at=now, connection_state="CONNECTED")
    state_store.close()

    response = client.get("/")
    assert "NOT connected to a live broker or feed" in response.text
    assert "No real order can ever be placed here" in response.text


def test_banner_reflects_a_genuinely_connected_live_dhan_feed(client):
    # Real gap found via news/market-intelligence architecture audit: the
    # banner used to be a hardcoded static string, contradicting the feed
    # status table whenever a real Dhan WebSocket was actually connected.
    import live.workstation as workstation_module
    from datetime import datetime, timezone

    state_store = workstation_module.new_live_state_store()
    now = datetime.now(timezone.utc)
    state_store.save_feed_status(symbol="RELIANCE.NS", source="DHAN", status="LIVE", bar_timestamp=now, received_at=now, connection_state="CONNECTED")
    state_store.close()

    response = client.get("/")
    assert "A LIVE broker feed IS connected" in response.text
    assert "NOT connected to a live broker or feed" not in response.text
    # The one part of the claim that must NEVER change, regardless of feed state.
    assert "No real order can ever be placed here" in response.text


def test_banner_stays_not_connected_when_a_live_source_is_disconnected(client):
    # A LIVE-status row whose connection has since dropped must not claim
    # current connectivity -- connection_state, not just status, gates the claim.
    import live.workstation as workstation_module
    from datetime import datetime, timezone

    state_store = workstation_module.new_live_state_store()
    now = datetime.now(timezone.utc)
    state_store.save_feed_status(symbol="RELIANCE.NS", source="DHAN", status="LIVE", bar_timestamp=now, received_at=now, connection_state="DISCONNECTED")
    state_store.close()

    response = client.get("/")
    assert "NOT connected to a live broker or feed" in response.text


def test_index_shows_a_pending_signal_with_approve_reject_buttons(client):
    signal_id = _drive_one_pending_approval()
    response = client.get("/")
    assert signal_id[:12] in response.text
    assert "APPROVE" in response.text
    assert "REJECT" in response.text


def test_approve_route_calls_the_same_domain_method_and_redirects(client):
    signal_id = _drive_one_pending_approval()
    response = client.post("/approve", data={"signal_id": signal_id}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"

    import live.workstation as workstation_module
    journal = workstation_module.get_trade_journal()
    assert len(journal) == 1
    assert journal[0].signal_id == signal_id


def test_reject_route_never_creates_an_order(client):
    signal_id = _drive_one_pending_approval()
    client.post("/reject", data={"signal_id": signal_id})

    import live.workstation as workstation_module
    assert workstation_module.get_pending_approvals() == []
    assert workstation_module.get_trade_journal() == []


def test_kill_switch_activate_and_reset_routes(client):
    response = client.get("/")
    assert "KILL SWITCH ACTIVE" not in response.text

    client.post("/kill-switch/activate", data={"reason": "dashboard test halt"})
    response = client.get("/")
    assert "KILL SWITCH ACTIVE" in response.text
    assert "dashboard test halt" in response.text

    client.post("/kill-switch/reset")
    response = client.get("/")
    assert "KILL SWITCH ACTIVE" not in response.text


def test_approving_while_kill_switch_active_is_blocked(client):
    signal_id = _drive_one_pending_approval()
    client.post("/kill-switch/activate", data={"reason": "halt"})
    client.post("/approve", data={"signal_id": signal_id})

    import live.workstation as workstation_module
    assert workstation_module.get_trade_journal() == []
    # still pending -- the kill switch blocked the approval, it didn't discard it
    assert len(workstation_module.get_pending_approvals()) == 1
