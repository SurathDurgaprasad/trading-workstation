from datetime import datetime

import pytest

from live.broker import MockBrokerAdapter
from paper.engine import Bar, PaperTradingEngine
from paper.store import PaperStore
from strategy.signal import ReasonCode, Side, Signal


def _signal(**overrides):
    base = dict(
        symbol="TEST", generated_at=datetime(2026, 1, 1), side=Side.LONG, reference_price=100.0,
        stop_price=95.0, target_price=110.0, risk_reward=2.0, strategy_name="unit-test",
        reason_codes=[ReasonCode.TREND_CONFIRMED],
    )
    base.update(overrides)
    return Signal(**base)


def test_submit_order_delegates_to_the_real_engine_and_returns_signal_id():
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    broker = MockBrokerAdapter(engine)

    signal = _signal()
    returned_id = broker.submit_order(signal)
    assert returned_id == signal.stable_id()
    assert store.find_journal_entry_by_signal_id(signal.stable_id()) is not None


def test_order_status_reflects_the_real_journal_outcome():
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    broker = MockBrokerAdapter(engine)

    signal = _signal()
    broker.submit_order(signal)
    assert broker.order_status(signal.stable_id()) == "APPROVED_PENDING"


def test_order_status_unknown_signal_returns_none():
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    broker = MockBrokerAdapter(engine)
    assert broker.order_status("never-submitted") is None


def test_list_positions_and_get_funds_reflect_real_state():
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    broker = MockBrokerAdapter(engine)

    broker.submit_order(_signal())
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=101.5, low=100.5, close=101.0))

    positions = broker.list_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "TEST"
    assert broker.get_funds().equity < 100_000.0 or broker.get_funds().cash < 100_000.0


def test_list_fills_reflects_real_trades():
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    broker = MockBrokerAdapter(engine)

    broker.submit_order(_signal())
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=101.5, low=100.5, close=101.0))
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 3), open=101.0, high=115.0, low=100.0, close=110.0))

    fills = broker.list_fills()
    assert len(fills) == 1
    assert fills[0].exit_reason.value == "TARGET"


def test_cancel_order_is_honestly_not_implemented_not_faked():
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    broker = MockBrokerAdapter(engine)
    with pytest.raises(NotImplementedError):
        broker.cancel_order("anything")
