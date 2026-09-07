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


def test_index_states_the_scientific_no_edge_verdict_prominently(client):
    # Live-market-readiness audit finding: nothing on the dashboard stated
    # the actual, already-completed strategy research conclusion -- the
    # closest existing analog (/intelligence's own smaller-sample
    # "Profitability evidence" section) is a DIFFERENT finding an operator
    # could easily mistake for "not enough data yet". This must appear on
    # every page (via _page()), not just one, so it can never be missed.
    for path in ("/", "/intelligence"):
        response = client.get(path)
        assert "SCIENTIFIC STRATEGY VERDICT: NO DEMONSTRATED EDGE" in response.text
        assert "Do not interpret any signal, decision, or prediction shown on this dashboard as evidence of profitability" in response.text


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


def test_market_feed_table_shows_a_real_last_price(client):
    # AUTONOMOUS LIVE PAPER-TRADING HARDENING mission, dashboard truth
    # audit: the MARKET FEED table had no price column at all -- real gap
    # against the mission's own "live prices" checklist item.
    import live.workstation as workstation_module
    from datetime import datetime, timezone

    state_store = workstation_module.new_live_state_store()
    now = datetime.now(timezone.utc)
    state_store.save_feed_status(symbol="RELIANCE.NS", source="DHAN", status="LIVE", bar_timestamp=now, received_at=now, connection_state="CONNECTED", last_price=1309.2)
    state_store.close()

    response = client.get("/")
    assert "Last Price" in response.text
    assert "1,309.20" in response.text


def test_market_feed_table_shows_n_a_when_last_price_was_never_recorded(client):
    # A row written before the last_price column existed (or by a caller
    # that never supplied one) must show an honest "n/a", never a
    # fabricated 0.00 or blank cell.
    import live.workstation as workstation_module
    from datetime import datetime, timezone

    state_store = workstation_module.new_live_state_store()
    now = datetime.now(timezone.utc)
    state_store.save_feed_status(symbol="RELIANCE.NS", source="DHAN", status="LIVE", bar_timestamp=now, received_at=now, connection_state="CONNECTED")
    state_store.close()

    response = client.get("/")
    assert "n/a" in response.text


# --- _data_health_label (LIVE SYSTEM HARDENING mission, Part 3) -- pure unit tests ---


def test_data_health_label_maps_every_connection_state():
    from dashboard.app import _data_health_label

    assert _data_health_label(connection_state="FAILED", age_seconds=0.0)[0] == "SOURCE_UNAVAILABLE"
    assert _data_health_label(connection_state="RECONNECTING", age_seconds=0.0)[0] == "RECONNECTING"
    assert _data_health_label(connection_state="DISCONNECTED", age_seconds=0.0)[0] == "DISCONNECTED"
    assert _data_health_label(connection_state="CONNECTING", age_seconds=0.0)[0] == "DISCONNECTED"
    assert _data_health_label(connection_state="CLOSED", age_seconds=0.0)[0] == "DISCONNECTED"
    assert _data_health_label(connection_state=None, age_seconds=0.0)[0] == "DISCONNECTED"


def test_data_health_label_grades_a_connected_source_by_age():
    from dashboard.app import _data_health_label

    assert _data_health_label(connection_state="CONNECTED", age_seconds=5.0)[0] == "CONNECTED"
    assert _data_health_label(connection_state="CONNECTED", age_seconds=45.0)[0] == "DEGRADED"
    assert _data_health_label(connection_state="CONNECTED", age_seconds=150.0)[0] == "STALE"
    assert _data_health_label(connection_state="CONNECTED", age_seconds=None)[0] == "CONNECTED"  # unknown age is not assumed stale


def test_data_health_label_boundaries_are_exclusive():
    from dashboard.app import _data_health_label

    assert _data_health_label(connection_state="CONNECTED", age_seconds=30.0)[0] == "CONNECTED"  # exactly the floor -- not yet degraded
    assert _data_health_label(connection_state="CONNECTED", age_seconds=120.0)[0] == "DEGRADED"  # exactly the default threshold -- not yet stale


def test_index_shows_reconnecting_and_source_unavailable_data_health(client):
    """LIVE SYSTEM HARDENING mission, Part 3: proves the dashboard's new
    Data Health column genuinely reflects a richer connection_state
    (not collapsed to plain CONNECTED/DISCONNECTED) for two symbols in
    the SAME response."""
    import live.workstation as workstation_module
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    state_store = workstation_module.new_live_state_store()
    state_store.save_feed_status(symbol="RECONNECT.NS", source="DHAN", status="LIVE", bar_timestamp=now, received_at=now, connection_state="RECONNECTING")
    state_store.save_feed_status(symbol="FAILED.NS", source="DHAN", status="LIVE", bar_timestamp=now, received_at=now, connection_state="FAILED")
    state_store.close()

    response = client.get("/")
    assert "RECONNECTING" in response.text
    assert "SOURCE_UNAVAILABLE" in response.text


def test_index_shows_stale_data_health_for_an_old_bar(client):
    import live.workstation as workstation_module
    from datetime import datetime, timedelta, timezone

    old = datetime.now(timezone.utc) - timedelta(seconds=300)
    state_store = workstation_module.new_live_state_store()
    state_store.save_feed_status(symbol="OLD.NS", source="DHAN", status="LIVE", bar_timestamp=old, received_at=old, connection_state="CONNECTED")
    state_store.close()

    response = client.get("/")
    assert "STALE" in response.text


def test_index_shows_no_critic_rejections_when_none_ever_recorded(client):
    response = client.get("/")
    assert "No signal has ever been rejected by the deterministic critic." in response.text


def test_index_shows_a_real_persisted_critic_rejection(client):
    """LIVE SYSTEM HARDENING mission: directly exercises
    live.workstation.get_critic_rejections() through the dashboard --
    proving a critic-rejected signal (which never creates a JournalEntry
    at all) is still genuinely visible to an operator, not silently
    lost."""
    import live.workstation as workstation_module
    from datetime import datetime, timezone

    state_store = workstation_module.new_live_state_store()
    state_store.save_critic_rejection(
        signal_id="sig-abc123", symbol="RELIANCE.NS", verdict="REJECT",
        reasons=["Kill switch is active -- execution safety blocks any new order."],
        checks=[], rejected_at=datetime.now(timezone.utc),
    )
    state_store.close()

    response = client.get("/")
    assert "RELIANCE.NS" in response.text
    assert "REJECT" in response.text
    assert "Kill switch is active" in response.text
    assert "sig-abc123"[:12] in response.text


def test_index_journal_table_has_a_decision_id_column(client):
    """LIVE SYSTEM HARDENING mission, Part 10: the main `/` page's journal
    table previously showed only signal_id, while /intelligence's own
    journal table already showed decision_id (added earlier this
    session) -- an inconsistency between the two operator-facing journal
    views. Reuses the SAME _decision_id_cell helper (now module-level,
    de-duplicated) both pages already relied on. A freshly-approved
    signal here never went through decision_engine (a plain
    live/pipeline.py Strategy, same as _drive_one_pending_approval's own
    real pipeline), so it correctly shows the documented "--" placeholder
    -- proving the column renders and is honest about absence, not that
    a decision_id was fabricated."""
    signal_id = _drive_one_pending_approval()
    client.post("/approve", data={"signal_id": signal_id})

    response = client.get("/")
    assert "Decision ID" in response.text
    assert "&mdash;" in response.text  # the documented placeholder for a signal with no decision_engine Decision


def test_clock_skew_banner_says_unknown_when_never_measured(client):
    """LIVE SYSTEM HARDENING mission, Part 11: absence of a clock_skew row
    must never be silently filled in with a fabricated 0.0s/PASS default
    -- the dashboard must say it was never measured, matching the same
    honesty rule feed_status already follows."""
    response = client.get("/")
    assert "Clock skew" in response.text
    assert "UNKNOWN" in response.text
    assert "Never measured in this environment" in response.text


def test_clock_skew_banner_shows_a_real_persisted_fail_reading(client):
    """Directly exercises live.workstation.get_clock_skew() through the
    dashboard, using the real, live-confirmed skew value observed on this
    machine (~130s behind Dhan's server clock) -- proving the FAIL
    classification and the Windows remediation hint both actually reach
    the rendered page, not just the CLI's readiness-check --deep output."""
    import live.workstation as workstation_module
    from datetime import datetime, timezone

    state_store = workstation_module.new_live_state_store()
    state_store.save_clock_skew(
        skew_seconds=-130.0, classification="FAIL",
        detail="-130.0s -- exceeds 60s, a full candle interval. Freshness/staleness logic cannot be trusted on "
               "this machine until the clock is corrected (Windows: run 'w32tm /resync' as Administrator, or "
               "enable 'Set time automatically' in Settings).",
        measured_at=datetime.now(timezone.utc),
    )
    state_store.close()

    response = client.get("/")
    assert "Clock skew" in response.text
    assert "FAIL" in response.text
    assert "-130.0s" in response.text
    assert "w32tm /resync" in response.text


def test_clock_skew_banner_notes_when_the_reading_itself_is_stale(client):
    """A skew reading is taken once per readiness-check/session start, not
    continuously -- an operator looking at a 45-minute-old reading during
    a long-running session must be told it may not reflect current
    conditions, not shown it as if it were live."""
    import live.workstation as workstation_module
    from datetime import datetime, timedelta, timezone

    state_store = workstation_module.new_live_state_store()
    state_store.save_clock_skew(
        skew_seconds=1.0, classification="PASS", detail="+1.0s -- within 5s tolerance.",
        measured_at=datetime.now(timezone.utc) - timedelta(minutes=45),
    )
    state_store.close()

    response = client.get("/")
    assert "may not reflect current conditions" in response.text


def test_no_risk_halt_banner_under_normal_account_state(client):
    response = client.get("/")
    assert "RISK HALT ACTIVE" not in response.text


def test_risk_halt_banner_appears_when_a_real_halt_reason_is_present(client, monkeypatch):
    """LIVE SYSTEM HARDENING mission, Part 10: real dashboard gap -- risk
    numbers were shown ("2/5 consecutive losses") but there was no
    explicit "trading is halted right now" signal distinct from the kill
    switch, even though risk.engine.RiskEngine.account_level_halt_reasons()
    already has that exact answer (see live.workstation.get_risk_halt_reasons,
    itself already covered by tests/test_paper_advance.py for the real
    halt logic). This test targets the NEW code -- the dashboard's own
    rendering of whatever that function returns -- rather than fighting
    _isolated_live_engine's deliberate fresh-engine-per-call design
    (needed for Starlette TestClient's cross-thread SQLite access, see
    that fixture's own docstring), which a pinned mutated Account can't
    survive."""
    import live.workstation as workstation_module

    monkeypatch.setattr(workstation_module, "get_risk_halt_reasons", lambda: ["CONSECUTIVE_LOSS_LIMIT"])

    response = client.get("/")
    assert "RISK HALT ACTIVE" in response.text
    assert "CONSECUTIVE_LOSS_LIMIT" in response.text
    assert "separate from the kill switch" in response.text


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


def test_banner_does_not_claim_connected_for_a_stale_row_still_marked_connected(client):
    # AUTONOMOUS LIVE PAPER-TRADING HARDENING mission, real bug found live:
    # a feed_status row's connection_state is whatever it was the LAST time
    # a real session wrote it -- once that process exits, nothing ever
    # updates the row again, so it can go on saying CONNECTED indefinitely.
    # Observed live: RELIANCE.NS's own row said CONNECTED while its data was
    # 3+ hours old and zero python processes were running. The banner must
    # use the same staleness-aware grading as the feed status table below
    # it, not just the row's last-written connection_state.
    import live.workstation as workstation_module
    from datetime import datetime, timedelta, timezone

    state_store = workstation_module.new_live_state_store()
    stale_time = datetime.now(timezone.utc) - timedelta(hours=3)
    state_store.save_feed_status(symbol="RELIANCE.NS", source="DHAN", status="LIVE", bar_timestamp=stale_time, received_at=stale_time, connection_state="CONNECTED")
    state_store.close()

    response = client.get("/")
    assert "A LIVE broker feed IS connected" not in response.text
    assert "was connected but its last update is now stale" in response.text
    assert "No real order can ever be placed here" in response.text


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
