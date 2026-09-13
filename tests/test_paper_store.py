"""Transaction rollback (spec §10/§24): a failure partway through a
paper-trading step must leave NO partial state — not "order exists but fill
doesn't", not "fill exists but account was never updated"."""

from datetime import datetime

import pytest

from paper.engine import Bar, PaperTradingEngine
from paper.store import PaperStore
from strategy.signal import ReasonCode, Side, Signal


def _signal(**overrides) -> Signal:
    base = dict(
        symbol="TEST", generated_at=datetime(2026, 1, 1), side=Side.LONG,
        reference_price=100.0, stop_price=95.0, target_price=110.0, risk_reward=2.0,
        strategy_name="unit-test", reason_codes=[ReasonCode.TREND_CONFIRMED],
    )
    base.update(overrides)
    return Signal(**base)


def test_transaction_rolls_back_cleanly_on_a_mid_step_failure(monkeypatch):
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)

    # Fail on the LAST write of submit_signal's transaction (save_journal_entry)
    # -- if rollback works, the signal/risk_decision/order writes that
    # happened earlier in the SAME transaction must also be gone.
    def _boom(*args, **kwargs):
        raise RuntimeError("simulated failure writing the journal entry")

    monkeypatch.setattr(store, "save_journal_entry", _boom)

    with pytest.raises(RuntimeError):
        engine.submit_signal(_signal())

    assert store.get_signal(_signal().stable_id()) is None
    assert store.get_pending_order("TEST") is None
    assert store.list_journal_entries() == []
    assert store._fetch_all_json("risk_decisions") == []


def test_transaction_rolls_back_on_fill_failure_leaving_no_partial_position(monkeypatch):
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    engine.submit_signal(_signal())

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated failure saving the position")

    monkeypatch.setattr(store, "save_position", _boom)

    with pytest.raises(RuntimeError):
        engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=101.5, low=100.5, close=101.0))

    # The order must still show PENDING (not silently marked FILLED with no
    # position to show for it), and no fill/position must exist.
    order = store.get_pending_order("TEST")
    assert order is not None
    assert store.get_open_position("TEST") is None
    assert store._fetch_all_json("paper_fills") == []
    # Account must not have been debited for a fill that never really happened.
    assert store.get_account().cash == 100_000.0


def test_successful_transaction_actually_commits(monkeypatch):
    """Sanity check that the rollback tests above aren't passing merely
    because nothing ever gets committed."""
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    engine.submit_signal(_signal())
    assert store.get_pending_order("TEST") is not None
    assert store.get_signal(_signal().stable_id()) is not None


# --- decision_id backward compatibility (LIVE SYSTEM HARDENING mission) -----


def test_journal_entry_deserializes_an_old_pre_decision_id_json_blob():
    """A row persisted before this mission added JournalEntry.decision_id
    has no `decision_id` key in its stored data_json at all -- must
    deserialize cleanly with decision_id=None, not raise a validation
    error. Simulates that exact old shape directly (no migration script
    exists or is needed, matching this project's own established
    additive-optional-field convention)."""
    from paper.models import JournalEntry, JournalOutcome

    old_style_json = (
        '{"journal_entry_id": "j1", "signal_id": "s1", "symbol": "TEST", '
        '"risk_decision_id": "r1", "order_id": "o1", "position_id": null, "trade_id": null, '
        '"outcome": "APPROVED_PENDING", "strategy_name": "unit-test", "strategy_version": "1.0", '
        '"risk_config_version": "cfg1", "execution_model_version": "1.0", '
        '"created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"}'
    )
    entry = JournalEntry.model_validate_json(old_style_json)
    assert entry.decision_id is None
    assert entry.outcome == JournalOutcome.APPROVED_PENDING


def test_signal_deserializes_an_old_pre_decision_id_json_blob():
    old_style_json = (
        '{"symbol": "TEST", "generated_at": "2026-01-01T00:00:00", "side": "LONG", '
        '"reference_price": 100.0, "stop_price": 95.0, "target_price": 110.0, "risk_reward": 2.0, '
        '"strategy_name": "unit-test", "reason_codes": ["TREND_CONFIRMED"]}'
    )
    signal = Signal.model_validate_json(old_style_json)
    assert signal.decision_id is None


def test_integrity_check_reports_ok_for_a_healthy_database(tmp_path):
    store = PaperStore(tmp_path / "paper.db")
    assert store.integrity_check() == "ok"
    store.close()


def test_db_size_bytes_reflects_a_real_file(tmp_path):
    store = PaperStore(tmp_path / "paper.db")
    assert store.db_size_bytes() > 0
    store.close()


def test_wal_mode_is_enabled(tmp_path):
    store = PaperStore(tmp_path / "paper.db")
    mode = store._conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
    store.close()


def _position(**overrides):
    from paper.models import Position, PositionStatus

    base = dict(
        position_id="p1", symbol="TEST", status=PositionStatus.OPEN, signal_id="s1",
        entry_order_id="o1", entry_fill_id="f1", entry_time=datetime(2026, 1, 1),
        entry_price=100.0, quantity=1, stop_price=95.0, target_price=110.0,
    )
    base.update(overrides)
    return Position(**base)


def test_update_position_allows_a_normal_open_to_closed_transition():
    from paper.models import PositionStatus

    store = PaperStore(":memory:")
    store.save_position(_position())

    store.update_position(_position(status=PositionStatus.CLOSED, exit_price=105.0))

    assert store.get_position("p1").status == PositionStatus.CLOSED


def test_update_position_rejects_a_second_close_of_an_already_closed_position():
    """Final-product-hardening: CLOSED is a terminal state -- two exit
    paths racing on the same position (e.g. a stop-hit check and an
    end-of-data force-close both firing) must not silently double-close
    or silently no-op; it must be a loud, surfaced error."""
    from paper.errors import InvalidPositionTransitionError
    from paper.models import PositionStatus

    store = PaperStore(":memory:")
    store.save_position(_position())
    store.update_position(_position(status=PositionStatus.CLOSED, exit_price=105.0))

    with pytest.raises(InvalidPositionTransitionError):
        store.update_position(_position(status=PositionStatus.CLOSED, exit_price=106.0))


def test_update_position_rejects_reopening_a_closed_position():
    from paper.errors import InvalidPositionTransitionError
    from paper.models import PositionStatus

    store = PaperStore(":memory:")
    store.save_position(_position())
    store.update_position(_position(status=PositionStatus.CLOSED, exit_price=105.0))

    with pytest.raises(InvalidPositionTransitionError):
        store.update_position(_position(status=PositionStatus.OPEN))


def test_update_position_on_a_nonexistent_position_raises_value_error():
    store = PaperStore(":memory:")

    with pytest.raises(ValueError, match="no such position"):
        store.update_position(_position(position_id="does-not-exist"))


def test_schema_version_is_set_on_a_fresh_database(tmp_path):
    store = PaperStore(tmp_path / "paper.db")
    assert store.schema_version() == PaperStore.CURRENT_SCHEMA_VERSION
    store.close()
