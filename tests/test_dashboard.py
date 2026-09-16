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
    # Phase 26: the new /intelligence page must be linked from here.
    assert 'href="/intelligence"' in response.text

    signals_response = client.get("/signals")
    assert "No signals pending human approval." in signals_response.text

    portfolio_response = client.get("/portfolio")
    assert "No open positions." in portfolio_response.text


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
    started as, not infer it from equity minus P&L by hand.

    UI integration (Claude Design "Trading Workstation" approved
    canvas): this content now lives on the dedicated Portfolio tab."""
    response = client.get("/portfolio")
    assert "Initial Capital" in response.text
    assert "100,000.00" in response.text  # this fixture's engine uses PaperTradingEngine's own default
    assert "Realized P&amp;L" in response.text or "Realized P&L" in response.text


def test_index_shows_no_feed_data_when_nothing_processed_yet(client):
    """Phase 15 §7/§22: absence of a feed_status row must never be
    silently filled in with a fabricated MOCK/SIMULATED default.

    UI integration: the MARKET FEED table now lives on the System tab."""
    response = client.get("/system")
    assert "No market data processed yet in this session" in response.text


def test_index_shows_real_feed_status_once_written(client):
    """Directly exercises live.workstation.get_feed_status() through the
    dashboard -- proving MOCK vs. DHAN and SIMULATED vs. LIVE are both
    genuinely distinguished in the rendered page, never hardcoded.

    UI integration: the full MARKET FEED table (with a Source column)
    now lives on the System tab; the Overview tab's own watchlist reads
    the same real feed_status rows, checked separately below."""
    import live.workstation as workstation_module

    state_store = workstation_module.new_live_state_store()
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    state_store.save_feed_status(symbol="RELIANCE.NS", source="DHAN", status="LIVE", bar_timestamp=now, received_at=now, connection_state="CONNECTED")
    state_store.close()

    response = client.get("/system")
    assert "RELIANCE.NS" in response.text
    assert "DHAN" in response.text
    assert "LIVE" in response.text
    assert "CONNECTED" in response.text

    overview_response = client.get("/")
    assert "RELIANCE.NS" in overview_response.text


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

    response = client.get("/system")
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

    response = client.get("/system")
    assert "n/a" in response.text


# --- AI status section (OpenAI Intelligence Integration mission, Phase 14) ---


def test_system_page_shows_ai_status_not_active_by_default(client, monkeypatch):
    # Default Settings() has llm_provider=ollama -- the dashboard must say
    # so honestly, never imply OpenAI is active just because the code
    # exists.
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    import core.config as config_module

    config_module.get_settings.cache_clear()

    response = client.get("/system")
    assert "AI INTELLIGENCE STATUS" in response.text
    assert "NOT ACTIVE" in response.text


def test_system_page_shows_ai_available_when_openai_configured_and_enabled(client, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("OPENAI_ENABLED", "true")
    import core.config as config_module

    config_module.get_settings.cache_clear()
    try:
        response = client.get("/system")
        assert "AVAILABLE" in response.text
        assert "openai" in response.text
    finally:
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_ENABLED", raising=False)
        config_module.get_settings.cache_clear()


def test_system_page_never_renders_the_openai_api_key_value(client, monkeypatch):
    fake_key = "sk-THIS-VALUE-MUST-NEVER-APPEAR-ON-THE-DASHBOARD-xyz789"
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", fake_key)
    monkeypatch.setenv("OPENAI_ENABLED", "true")
    import core.config as config_module

    config_module.get_settings.cache_clear()
    try:
        response = client.get("/system")
        assert fake_key not in response.text
    finally:
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_ENABLED", raising=False)
        config_module.get_settings.cache_clear()


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
    """UI integration: the CRITIC REJECTIONS table now lives on Signals."""
    response = client.get("/signals")
    assert "No signal has ever been rejected by the deterministic critic." in response.text


def test_index_shows_a_real_persisted_critic_rejection(client):
    """LIVE SYSTEM HARDENING mission: directly exercises
    live.workstation.get_critic_rejections() through the dashboard --
    proving a critic-rejected signal (which never creates a JournalEntry
    at all) is still genuinely visible to an operator, not silently
    lost.

    UI integration: the full table now lives on Signals; Overview shows
    only a real, honest count-level summary in its Attention panel."""
    import live.workstation as workstation_module
    from datetime import datetime, timezone

    state_store = workstation_module.new_live_state_store()
    state_store.save_critic_rejection(
        signal_id="sig-abc123", symbol="RELIANCE.NS", verdict="REJECT",
        reasons=["Kill switch is active -- execution safety blocks any new order."],
        checks=[], rejected_at=datetime.now(timezone.utc),
    )
    state_store.close()

    response = client.get("/signals")
    assert "RELIANCE.NS" in response.text
    assert "REJECT" in response.text
    assert "Kill switch is active" in response.text
    assert "sig-abc123"[:12] in response.text

    overview_response = client.get("/")
    assert "CRITIC REJECTIONS" in overview_response.text
    assert "1 recorded" in overview_response.text


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
    a decision_id was fabricated.

    UI integration: the JOURNAL table now lives on the Portfolio tab."""
    signal_id = _drive_one_pending_approval()
    client.post("/approve", data={"signal_id": signal_id})

    response = client.get("/portfolio")
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
    """UI integration: the approve/reject table now lives on Signals;
    Overview still surfaces the same real pending signal in its
    Attention panel (checked separately below)."""
    signal_id = _drive_one_pending_approval()
    response = client.get("/signals")
    assert signal_id[:12] in response.text
    assert "APPROVE" in response.text
    assert "REJECT" in response.text

    overview_response = client.get("/")
    assert "APPROVAL REQUIRED" in overview_response.text


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


# --- UI integration (Claude Design "Trading Workstation" approved canvas) -------


def test_signal_detail_page_shows_the_real_trade_plan_and_honestly_reports_ai_unavailable(client):
    """The Trade Plan/Technical Evidence/Risk Assessment sections must
    come entirely from real, persisted fields (strategy.signal.Signal,
    live.state_store.PendingApprovalRecord, a read-only RiskEngine
    recompute) -- and the AI section must NOT fabricate a narrative for
    a path that never persists one."""
    signal_id = _drive_one_pending_approval()
    response = client.get(f"/signals/{signal_id}")
    assert response.status_code == 200
    assert "AAPL" in response.text
    assert "TRADE PLAN" in response.text
    assert "PENDING_HUMAN_APPROVAL" in response.text
    assert "Trend confirmed" in response.text  # a real reason_code, not an AI narrative
    assert "POSITION SIZE" in response.text
    assert "NOT AVAILABLE for this signal" in response.text  # AI interpretation, honestly absent
    assert "SIGNAL_GENERATED" in response.text  # real state.history timeline
    assert "exit_reason TARGET" in response.text
    assert "exit_reason STOP" in response.text


def test_signal_detail_page_for_an_unknown_signal_id_is_honest_not_broken(client):
    response = client.get("/signals/does-not-exist")
    assert response.status_code == 200
    assert "may have already been approved, rejected, or expired" in response.text


def test_fleet_page_reports_not_configured_by_default(client):
    response = client.get("/fleet")
    assert "Not configured" in response.text


def test_fleet_page_shows_real_fleet_summary_data_once_configured(client, monkeypatch, tmp_path):
    """Wires the Fleet tab at a real runtime-dir with real, persisted
    per-symbol state -- exercising the SAME live/fleet_summary.py and
    live/runtime_layout.py functions `fleet-summary` itself uses, not a
    second implementation."""
    import dashboard.app as dashboard_app
    from datetime import datetime, timezone
    from live.runtime_layout import ensure_symbol_runtime_dirs, symbol_runtime_paths
    from live.state_store import LiveStateStore

    dashboard_app.configure(schedule_config_path=None, fleet_runtime_dir=str(tmp_path), fleet_symbols=["RELIANCE.NS", "TCS.NS"])

    paths = symbol_runtime_paths(tmp_path, "RELIANCE.NS")
    ensure_symbol_runtime_dirs(paths)
    (paths.logs_dir / "session.log").write_text(
        "[RELIANCE.NS] bar#   1 2026-09-15T09:15:00  close=2481.20  NO_SIGNAL  fresh=True\n", encoding="utf-8",
    )
    now = datetime.now(timezone.utc)
    state_store = LiveStateStore(paths.state_db)
    state_store.save_feed_status(symbol="RELIANCE.NS", source="DHAN", status="LIVE", bar_timestamp=now, received_at=now, connection_state="CONNECTED")
    state_store.close()
    # TCS.NS deliberately never started -- proving a never-launched symbol
    # is reported honestly, not silently dropped from the table.

    response = client.get("/fleet")
    assert response.status_code == 200
    assert "RELIANCE.NS" in response.text
    assert "TCS.NS" in response.text
    assert "1 / 2 HEALTHY" in response.text
    assert "CONNECTED" in response.text
    assert "NOT AVAILABLE" in response.text  # process-alive status, honestly absent

    dashboard_app.configure(schedule_config_path=None)  # reset for other tests in this module


def test_fleet_page_counts_a_degraded_but_arriving_feed_as_healthy(client, monkeypatch, tmp_path):
    """15-symbol live-fleet validation mission, real defect found live:
    `_data_health_label` grades any feed whose last bar is >30s old as
    DEGRADED -- deliberately conservative for a display badge, but for
    the fleet's own `--interval 1m` cadence a 30-60s age is simply the
    NORMAL gap between consecutive bars. Counting DEGRADED as unhealthy
    made a continuously-healthy 15-symbol fleet report "0 / 15 HEALTHY"
    for roughly half of every minute (observed live oscillating
    0 -> 0 -> 13 -> 15 within 36 seconds). A feed that is still
    delivering bars must count as healthy."""
    import dashboard.app as dashboard_app
    from datetime import datetime, timedelta, timezone
    from live.runtime_layout import ensure_symbol_runtime_dirs, symbol_runtime_paths
    from live.state_store import LiveStateStore

    dashboard_app.configure(schedule_config_path=None, fleet_runtime_dir=str(tmp_path), fleet_symbols=["RELIANCE.NS"])

    paths = symbol_runtime_paths(tmp_path, "RELIANCE.NS")
    ensure_symbol_runtime_dirs(paths)
    (paths.logs_dir / "session.log").write_text(
        "[RELIANCE.NS] bar#   1 2026-09-16T09:15:00  close=1248.70  BAR_PROCESSED  fresh=True\n", encoding="utf-8",
    )
    # 45s old: past the 30s DEGRADED threshold, well inside a normal 1m bar gap.
    aging = datetime.now(timezone.utc) - timedelta(seconds=45)
    state_store = LiveStateStore(paths.state_db)
    state_store.save_feed_status(symbol="RELIANCE.NS", source="DHAN", status="LIVE", bar_timestamp=aging, received_at=aging, connection_state="CONNECTED")
    state_store.close()

    response = client.get("/fleet")
    assert "DEGRADED" in response.text  # still labelled honestly...
    assert "1 / 1 HEALTHY" in response.text  # ...but counted as a working feed

    dashboard_app.configure(schedule_config_path=None)


def test_fleet_page_counts_a_genuinely_stale_feed_as_unhealthy(client, monkeypatch, tmp_path):
    """The other side of the same boundary: a feed whose last bar is
    older than the STALE threshold is NOT healthy, and must not be
    counted as one."""
    import dashboard.app as dashboard_app
    from datetime import datetime, timedelta, timezone
    from live.runtime_layout import ensure_symbol_runtime_dirs, symbol_runtime_paths
    from live.state_store import LiveStateStore

    dashboard_app.configure(schedule_config_path=None, fleet_runtime_dir=str(tmp_path), fleet_symbols=["RELIANCE.NS"])

    paths = symbol_runtime_paths(tmp_path, "RELIANCE.NS")
    ensure_symbol_runtime_dirs(paths)
    (paths.logs_dir / "session.log").write_text(
        "[RELIANCE.NS] bar#   1 2026-09-16T09:15:00  close=1248.70  BAR_PROCESSED  fresh=True\n", encoding="utf-8",
    )
    stale = datetime.now(timezone.utc) - timedelta(seconds=600)
    state_store = LiveStateStore(paths.state_db)
    state_store.save_feed_status(symbol="RELIANCE.NS", source="DHAN", status="LIVE", bar_timestamp=stale, received_at=stale, connection_state="CONNECTED")
    state_store.close()

    response = client.get("/fleet")
    assert "STALE" in response.text
    assert "0 / 1 HEALTHY" in response.text

    dashboard_app.configure(schedule_config_path=None)


def test_portfolio_page_computes_position_pnl_from_the_real_last_observed_price(client):
    """UI integration: per-position current price/P&L is a pure
    arithmetic readout of two already-real numbers (Position.entry_price
    and feed_status.last_price for the SAME symbol) -- not a new
    trading computation."""
    import live.workstation as workstation_module
    from datetime import datetime, timezone
    from paper.models import Position, PositionStatus

    engine = workstation_module.get_live_engine()
    engine.store.save_position(Position(
        position_id="pos-1", symbol="AAPL", status=PositionStatus.OPEN, signal_id="sig-1",
        entry_order_id="ord-1", entry_fill_id="fill-1", entry_time=datetime.now(timezone.utc),
        entry_price=100.0, quantity=10, stop_price=95.0, target_price=110.0,
    ))
    state_store = workstation_module.new_live_state_store()
    now = datetime.now(timezone.utc)
    state_store.save_feed_status(symbol="AAPL", source="DHAN", status="LIVE", bar_timestamp=now, received_at=now, connection_state="CONNECTED", last_price=105.0)
    state_store.close()

    response = client.get("/portfolio")
    assert "AAPL" in response.text
    assert "105.00" in response.text  # current price, read from feed_status
    assert "+50.00" in response.text  # (105 - 100) * 10, a pure readout of two real numbers


def test_portfolio_page_shows_n_a_when_no_live_price_observed_for_a_position(client):
    import live.workstation as workstation_module
    from datetime import datetime, timezone
    from paper.models import Position, PositionStatus

    engine = workstation_module.get_live_engine()
    engine.store.save_position(Position(
        position_id="pos-1", symbol="AAPL", status=PositionStatus.OPEN, signal_id="sig-1",
        entry_order_id="ord-1", entry_fill_id="fill-1", entry_time=datetime.now(timezone.utc),
        entry_price=100.0, quantity=10, stop_price=95.0, target_price=110.0,
    ))

    response = client.get("/portfolio")
    assert "n/a" in response.text


def test_overview_watchlist_shows_observed_symbols_and_a_pending_signal_badge(client):
    signal_id = _drive_one_pending_approval()
    response = client.get("/")
    assert "AAPL" in response.text
    assert "WATCHLIST" in response.text
    assert "LONG" in response.text  # the real signal's own side, badged on its watchlist row


def test_api_state_returns_a_real_json_snapshot(client):
    response = client.get("/api/state")
    assert response.status_code == 200
    body = response.json()
    assert body["kill_switch_active"] is False
    assert body["pending_approvals_count"] == 0
    assert "as_of" in body
    assert body["prices"] == []
