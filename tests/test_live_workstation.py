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
