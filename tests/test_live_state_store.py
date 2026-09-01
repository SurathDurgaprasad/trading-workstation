from datetime import datetime, timedelta, timezone

from live.state_store import LiveStateStore
from strategy.signal import ReasonCode, Side, Signal


def _signal(**overrides):
    base = dict(
        symbol="TEST", generated_at=datetime(2026, 1, 1), side=Side.LONG, reference_price=100.0,
        stop_price=95.0, target_price=110.0, risk_reward=2.0, strategy_name="unit-test",
        reason_codes=[ReasonCode.TREND_CONFIRMED],
    )
    base.update(overrides)
    return Signal(**base)


def test_save_and_get_pending_approval(tmp_path):
    store = LiveStateStore(tmp_path / "state.db")
    signal = _signal()
    now = datetime.now(timezone.utc)
    store.save_pending_approval(
        signal=signal, strategy_version="1.0", risk_config_version="abc123", requested_quantity=10,
        state="PENDING_HUMAN_APPROVAL", history=[("SIGNAL_GENERATED", now)], created_at=now, expires_at=now + timedelta(seconds=60),
    )
    record = store.get(signal.stable_id())
    assert record is not None
    assert record.symbol == "TEST"
    assert record.requested_quantity == 10
    assert record.state == "PENDING_HUMAN_APPROVAL"
    assert record.signal.model_dump() == signal.model_dump()


def test_list_pending_excludes_decided_signals(tmp_path):
    store = LiveStateStore(tmp_path / "state.db")
    now = datetime.now(timezone.utc)
    s1, s2 = _signal(reference_price=100.0), _signal(reference_price=200.0)
    for s in (s1, s2):
        store.save_pending_approval(
            signal=s, strategy_version="1.0", risk_config_version="v1", requested_quantity=5,
            state="PENDING_HUMAN_APPROVAL", history=[], created_at=now, expires_at=now + timedelta(seconds=60),
        )
    store.update_decision(s1.stable_id(), state="EXECUTED", history=[], decision="APPROVE", decided_at=now)

    pending = store.list_pending()
    assert len(pending) == 1
    assert pending[0].signal_id == s2.stable_id()


def test_update_decision_persists_full_audit_trail(tmp_path):
    store = LiveStateStore(tmp_path / "state.db")
    now = datetime.now(timezone.utc)
    signal = _signal()
    store.save_pending_approval(
        signal=signal, strategy_version="1.0", risk_config_version="v1", requested_quantity=10,
        state="PENDING_HUMAN_APPROVAL", history=[], created_at=now, expires_at=now + timedelta(seconds=60),
    )
    store.update_decision(
        signal.stable_id(), state="EXECUTED", history=[("EXECUTED", now)], decision="APPROVE",
        decision_reason="looks good", approved_quantity=8, final_execution_result="APPROVED_FILLED_OPEN", decided_at=now,
    )
    record = store.get(signal.stable_id())
    assert record.decision == "APPROVE"
    assert record.decision_reason == "looks good"
    assert record.approved_quantity == 8
    assert record.final_execution_result == "APPROVED_FILLED_OPEN"
    assert record.decided_at is not None


def test_history_with_enum_states_round_trips_to_their_value_not_str_repr(tmp_path):
    """Regression test: found via the restart test on real AAPL data --
    _serialize_history used str(state) on a SignalLifecycleState enum
    member, producing "SignalLifecycleState.SIGNAL_GENERATED" instead of
    "SIGNAL_GENERATED", which then failed to parse back via
    SignalLifecycleState(value) on restore."""
    from live.approval import SignalLifecycleState

    store = LiveStateStore(tmp_path / "state.db")
    now = datetime.now(timezone.utc)
    signal = _signal()
    store.save_pending_approval(
        signal=signal, strategy_version="1.0", risk_config_version="v1", requested_quantity=1,
        state="PENDING_HUMAN_APPROVAL", history=[(SignalLifecycleState.SIGNAL_GENERATED, now), (SignalLifecycleState.RISK_APPROVED, now)],
        created_at=now, expires_at=now + timedelta(seconds=60),
    )
    record = store.get(signal.stable_id())
    state_values = [s for s, _ in record.history]
    assert state_values == ["SIGNAL_GENERATED", "RISK_APPROVED"]
    # and it must parse back into real enum members without raising
    assert SignalLifecycleState(state_values[0]) == SignalLifecycleState.SIGNAL_GENERATED


def test_pending_approvals_survive_a_reopened_connection(tmp_path):
    db_path = tmp_path / "state.db"
    now = datetime.now(timezone.utc)
    signal = _signal()

    store1 = LiveStateStore(db_path)
    store1.save_pending_approval(
        signal=signal, strategy_version="1.0", risk_config_version="v1", requested_quantity=10,
        state="PENDING_HUMAN_APPROVAL", history=[("SIGNAL_GENERATED", now)], created_at=now, expires_at=now + timedelta(seconds=60),
    )
    store1.close()

    store2 = LiveStateStore(db_path)
    record = store2.get(signal.stable_id())
    assert record is not None
    assert record.state == "PENDING_HUMAN_APPROVAL"


# --- kill switch --------------------------------------------------------------


def test_kill_switch_defaults_to_inactive(tmp_path):
    store = LiveStateStore(tmp_path / "state.db")
    assert store.is_kill_switch_active() is False


def test_kill_switch_activate_and_reset(tmp_path):
    store = LiveStateStore(tmp_path / "state.db")
    store.activate_kill_switch(reason="test halt")
    assert store.is_kill_switch_active() is True
    active, activated_at, reason = store.kill_switch_state()
    assert active is True
    assert reason == "test halt"
    assert activated_at is not None

    store.reset_kill_switch()
    assert store.is_kill_switch_active() is False


def test_kill_switch_survives_a_reopened_connection(tmp_path):
    db_path = tmp_path / "state.db"
    store1 = LiveStateStore(db_path)
    store1.activate_kill_switch(reason="persisted halt")
    store1.close()

    store2 = LiveStateStore(db_path)
    assert store2.is_kill_switch_active() is True
    active, _, reason = store2.kill_switch_state()
    assert reason == "persisted halt"
