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


# --- autonomous hardening cycle: PaperOrder terminal-state guard -----------


def _order(*, signal_id: str, **overrides):
    from paper.models import OrderStatus, PaperOrder

    base = dict(
        order_id="o1", signal_id=signal_id, symbol="TEST", side=Side.LONG, quantity=1,
        requested_price=100.0, status=OrderStatus.PENDING, created_at=datetime(2026, 1, 1),
        stop_price=95.0, target_price=110.0,
    )
    base.update(overrides)
    return PaperOrder(**base)


def _store_with_a_saved_order():
    """A PaperStore with one real signal + one PENDING order referencing
    it -- paper_orders.signal_id is a real foreign key, so a bare
    PaperOrder can't be saved without a matching signals row."""
    store = PaperStore(":memory:")
    signal = _signal()
    store.save_signal(signal, strategy_version="1.0")
    signal_id = signal.stable_id()
    store.save_order(_order(signal_id=signal_id))
    return store, signal_id


def test_update_order_allows_a_normal_pending_to_filled_transition():
    from paper.models import OrderStatus

    store, signal_id = _store_with_a_saved_order()

    store.update_order(_order(signal_id=signal_id, status=OrderStatus.FILLED))

    row = store._conn.execute("SELECT status FROM paper_orders WHERE order_id = ?", ("o1",)).fetchone()
    assert row[0] == "FILLED"


def test_update_order_rejects_reverting_a_filled_order_to_pending():
    from paper.errors import InvalidOrderTransitionError
    from paper.models import OrderStatus

    store, signal_id = _store_with_a_saved_order()
    store.update_order(_order(signal_id=signal_id, status=OrderStatus.FILLED))

    with pytest.raises(InvalidOrderTransitionError):
        store.update_order(_order(signal_id=signal_id, status=OrderStatus.PENDING))


def test_update_order_rejects_a_second_fill_of_an_already_filled_order():
    from paper.errors import InvalidOrderTransitionError
    from paper.models import OrderStatus

    store, signal_id = _store_with_a_saved_order()
    store.update_order(_order(signal_id=signal_id, status=OrderStatus.FILLED))

    with pytest.raises(InvalidOrderTransitionError):
        store.update_order(_order(signal_id=signal_id, status=OrderStatus.FILLED))


def test_update_order_on_a_nonexistent_order_raises_value_error():
    store = PaperStore(":memory:")

    with pytest.raises(ValueError, match="no such order"):
        store.update_order(_order(signal_id="does-not-exist", order_id="does-not-exist"))


# --- autonomous hardening cycle: malformed data_json on read ----------------


def test_a_malformed_position_row_raises_a_clear_error_not_a_raw_pydantic_traceback():
    """Real, previously-unguarded gap found by an SQLite-adversarial-
    resilience audit: every store's own list_*/get_* methods called the
    Pydantic model's model_validate_json() directly, unwrapped -- a row
    whose data_json fails validation (external tampering, low-level row
    corruption, a genuine bug -- NOT a schema-evolution scenario, since
    this project's own convention is additive-optional-fields, see this
    file's own test_journal_entry_deserializes_an_old_pre_decision_id_json_blob)
    would raise a raw, uncaught pydantic.ValidationError straight out of
    the store. Simulates a real corrupted row by writing one directly,
    bypassing save_position's own validated-model-in path entirely."""
    from core.sqlite_util import MalformedRowError

    store = PaperStore(":memory:")
    store._conn.execute(
        "INSERT INTO positions (position_id, symbol, status, signal_id, data_json, updated_at) VALUES (?,?,?,?,?,?)",
        ("p1", "TEST", "OPEN", "s1", '{"position_id": "p1"}', "2026-01-01T00:00:00+00:00"),  # missing every other required field
    )

    with pytest.raises(MalformedRowError) as exc_info:
        store.get_position("p1")

    assert "Position" in str(exc_info.value)
    assert "p1" in str(exc_info.value)


def test_a_malformed_row_in_a_list_query_also_raises_the_clear_error():
    from core.sqlite_util import MalformedRowError

    store = PaperStore(":memory:")
    store._conn.execute(
        "INSERT INTO positions (position_id, symbol, status, signal_id, data_json, updated_at) VALUES (?,?,?,?,?,?)",
        ("p1", "TEST", "OPEN", "s1", "not even valid json", "2026-01-01T00:00:00+00:00"),
    )

    with pytest.raises(MalformedRowError):
        store.list_positions()
