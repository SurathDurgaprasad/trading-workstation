"""Strategy science Phase 14 (Monday live validation plan) --
live.workstation.get_kill_switch_status(), a small missing accessor
added alongside its sibling functions (get_pending_approvals,
get_positions, get_account_state) for the new readiness-check CLI.
"""
import pytest

import live.workstation as workstation


@pytest.fixture(autouse=True)
def _isolated_state_store(monkeypatch, tmp_path):
    monkeypatch.setattr(workstation, "LIVE_STATE_DB_PATH", tmp_path / "live_state.db")
    yield


def test_kill_switch_status_is_inactive_when_never_touched():
    status = workstation.get_kill_switch_status()
    assert status == {"active": False, "activated_at": None, "reason": None}


def test_kill_switch_status_reflects_a_real_activation():
    state_store = workstation.new_live_state_store()
    state_store.activate_kill_switch(reason="test activation")
    state_store.close()

    status = workstation.get_kill_switch_status()

    assert status["active"] is True
    assert status["reason"] == "test activation"
    assert status["activated_at"] is not None


def test_kill_switch_status_reflects_a_reset():
    state_store = workstation.new_live_state_store()
    state_store.activate_kill_switch(reason="test activation")
    state_store.close()
    assert workstation.get_kill_switch_status()["active"] is True

    state_store = workstation.new_live_state_store()
    state_store.reset_kill_switch()
    state_store.close()

    assert workstation.get_kill_switch_status()["active"] is False


def test_get_risk_halt_reasons_is_empty_for_a_fresh_account(monkeypatch, tmp_path):
    from paper.engine import PaperTradingEngine
    from paper.store import PaperStore

    monkeypatch.setattr(workstation, "get_live_engine", lambda: PaperTradingEngine(PaperStore(tmp_path / "live_sim.db")))
    assert workstation.get_risk_halt_reasons() == []


def test_get_risk_halt_reasons_reflects_a_real_consecutive_loss_hard_limit_breach(monkeypatch, tmp_path):
    """Single-threaded, direct call -- no Starlette TestClient involved --
    so pinning one real engine instance and mutating its account is safe
    here, unlike tests/test_dashboard.py's HTTP-level equivalent (see
    that test's own docstring for why it mocks this function instead)."""
    from paper.engine import PaperTradingEngine
    from paper.store import PaperStore

    engine = PaperTradingEngine(PaperStore(tmp_path / "live_sim.db"))
    engine.account.consecutive_losses = 6  # risk/config.py's own default consecutive_loss_hard_limit
    # G9-DISPLAY follow-up (2026-09-23): also persisted, not just mutated
    # in memory -- get_risk_halt_reasons() now calls engine.refresh_account()
    # before reading engine.account (see that function's own docstring),
    # matching what every REAL account mutation already does before any
    # other call could observe it. An in-memory-only mutation, never
    # persisted, is not a state this engine can legitimately be in outside
    # a test shortcut.
    engine.store.save_account(engine.account)
    monkeypatch.setattr(workstation, "get_live_engine", lambda: engine)

    assert workstation.get_risk_halt_reasons() == ["CONSECUTIVE_LOSS_LIMIT"]


# --- get_live_sim_status honest source/status (red-team finding, 2026-09-22) -
# Previously get_live_sim_status() HARDCODED status="SIMULATED"/source="MOCK"
# unconditionally -- never derived from what was actually running. Dormant on
# the dashboard (it never renders these two keys) but surfaced verbatim to
# any MCP client via get_live_sim_status_tool, where it would falsely report
# "source: MOCK" during a genuine --source dhan live session.


def test_get_live_sim_status_reports_unknown_when_no_feed_data_exists_yet():
    """A fresh session (or one that hasn't processed a single bar) must
    never be GUESSED as either MOCK or a real source."""
    status = workstation.get_live_sim_status()
    assert status["status"] == "UNKNOWN"
    assert status["source"] == "UNKNOWN"


def test_get_live_sim_status_reports_the_real_source_from_feed_status(monkeypatch, tmp_path):
    """The exact scenario the original hardcoded string could lie about:
    a real DHAN/LIVE feed_status row must be reported as DHAN/LIVE, not
    the old fixed MOCK/SIMULATED string."""
    from paper.engine import PaperTradingEngine
    from paper.store import PaperStore

    monkeypatch.setattr(workstation, "get_live_engine", lambda: PaperTradingEngine(PaperStore(tmp_path / "live_sim.db")))

    state_store = workstation.new_live_state_store()
    from datetime import datetime, timezone

    state_store.save_feed_status(
        symbol="RELIANCE.NS", source="DHAN", status="LIVE",
        bar_timestamp=datetime.now(timezone.utc), received_at=datetime.now(timezone.utc),
        connection_state="CONNECTED", last_price=1234.5,
    )
    state_store.close()

    status = workstation.get_live_sim_status()

    assert status["status"] == "LIVE"
    assert status["source"] == "DHAN"


def test_get_live_sim_status_reports_mixed_when_symbols_disagree(monkeypatch, tmp_path):
    """Not reachable via fleet-supervise today (one --source applies to
    every worker), but must never silently pick one source and hide the
    other if it ever happens."""
    from paper.engine import PaperTradingEngine
    from paper.store import PaperStore

    monkeypatch.setattr(workstation, "get_live_engine", lambda: PaperTradingEngine(PaperStore(tmp_path / "live_sim.db")))

    state_store = workstation.new_live_state_store()
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    state_store.save_feed_status(symbol="AAPL", source="MOCK", status="SIMULATED", bar_timestamp=now, received_at=now, connection_state=None)
    state_store.save_feed_status(symbol="RELIANCE.NS", source="DHAN", status="LIVE", bar_timestamp=now, received_at=now, connection_state="CONNECTED")
    state_store.close()

    status = workstation.get_live_sim_status()

    assert status["status"] == "MIXED"
    assert status["source"] == "MIXED"
