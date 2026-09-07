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
