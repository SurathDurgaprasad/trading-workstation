"""Phase 13 §9: EXPECTED (local PaperTradingEngine) vs. LOCAL ACCOUNT STATE
(a BrokerAdapter -- MockBrokerAdapter for now) reconciliation. The happy
path uses a broker that delegates to the SAME engine (tautologically
clean); every mismatch test uses a SEPARATE, independently-diverged
"broker" to prove each specific failure mode is actually caught.
"""
from dataclasses import dataclass
from datetime import datetime

from live.broker import MockBrokerAdapter
from live.broker_reconciliation import reconcile_against_broker
from paper.engine import Bar, PaperTradingEngine
from paper.store import PaperStore
from risk.account import Account
from strategy.signal import ReasonCode, Side, Signal


def _signal(**overrides):
    base = dict(
        symbol="TEST", generated_at=datetime(2026, 1, 1), side=Side.LONG, reference_price=100.0,
        stop_price=95.0, target_price=110.0, risk_reward=2.0, strategy_name="unit-test",
        reason_codes=[ReasonCode.TREND_CONFIRMED],
    )
    base.update(overrides)
    return Signal(**base)


def _engine_with_open_position():
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    engine.submit_signal(_signal())
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=101.5, low=100.5, close=101.0))
    return engine


@dataclass
class _FakeBroker:
    """A test-only double that reports HAND-CONSTRUCTED, independent state
    -- standing in for what a real broker's own API would report,
    completely decoupled from our internal engine/store."""
    positions: list
    funds: Account
    fills: list

    def list_positions(self):
        return self.positions

    def get_funds(self):
        return self.funds

    def list_fills(self):
        return self.fills


def test_clean_reconciliation_against_the_same_engine():
    engine = _engine_with_open_position()
    broker = MockBrokerAdapter(engine)  # delegates to the SAME engine -- tautologically clean
    report = reconcile_against_broker(engine, broker)
    assert report.ok, report.issues


def test_missing_position_at_broker_is_detected():
    engine = _engine_with_open_position()
    fake_broker = _FakeBroker(positions=[], funds=engine.account, fills=[])
    report = reconcile_against_broker(engine, fake_broker)
    assert not report.ok
    assert any(i.check == "missing_position_at_broker" for i in report.issues)


def test_unexpected_position_at_broker_is_detected():
    engine = _engine_with_open_position()  # no local positions in a fresh no-position engine
    store2 = PaperStore(":memory:")
    other_engine = PaperTradingEngine(store2, initial_capital=100_000.0)  # never opened a position
    other_engine.submit_signal(_signal(symbol="TEST"))
    other_engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=101.5, low=100.5, close=101.0))
    phantom_position = other_engine.store.list_positions()[0]

    fresh_store = PaperStore(":memory:")
    fresh_engine = PaperTradingEngine(fresh_store, initial_capital=100_000.0)  # genuinely no local position
    fake_broker = _FakeBroker(positions=[phantom_position], funds=fresh_engine.account, fills=[])
    report = reconcile_against_broker(fresh_engine, fake_broker)
    assert not report.ok
    assert any(i.check == "unexpected_position_at_broker" for i in report.issues)


def test_quantity_mismatch_is_detected():
    engine = _engine_with_open_position()
    real_position = engine.store.list_positions()[0]
    diverged_position = real_position.model_copy(update={"quantity": real_position.quantity + 999})
    fake_broker = _FakeBroker(positions=[diverged_position], funds=engine.account, fills=[])
    report = reconcile_against_broker(engine, fake_broker)
    assert not report.ok
    assert any(i.check == "quantity_mismatch" for i in report.issues)


def test_price_mismatch_is_detected():
    engine = _engine_with_open_position()
    real_position = engine.store.list_positions()[0]
    diverged_position = real_position.model_copy(update={"entry_price": real_position.entry_price + 50.0})
    fake_broker = _FakeBroker(positions=[diverged_position], funds=engine.account, fills=[])
    report = reconcile_against_broker(engine, fake_broker)
    assert not report.ok
    assert any(i.check == "price_mismatch" for i in report.issues)


def test_cash_mismatch_is_detected():
    engine = _engine_with_open_position()
    real_position = engine.store.list_positions()[0]
    diverged_funds = engine.account.model_copy(update={"cash": engine.account.cash - 12345.0})
    fake_broker = _FakeBroker(positions=[real_position], funds=diverged_funds, fills=[])
    report = reconcile_against_broker(engine, fake_broker)
    assert not report.ok
    assert any(i.check == "cash_mismatch" for i in report.issues)


def test_trade_missing_at_broker_is_detected():
    engine = _engine_with_open_position()
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 3), open=101.0, high=115.0, low=100.0, close=110.0))  # closes via TARGET
    assert len(engine.store.list_trades()) == 1
    fake_broker = _FakeBroker(positions=[], funds=engine.account, fills=[])  # broker reports NO fills
    report = reconcile_against_broker(engine, fake_broker)
    assert not report.ok
    assert any(i.check == "trade_missing_at_broker" for i in report.issues)


def test_duplicate_trade_at_broker_is_detected():
    engine = _engine_with_open_position()
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 3), open=101.0, high=115.0, low=100.0, close=110.0))
    real_trade = engine.store.list_trades()[0]
    fake_broker = _FakeBroker(positions=[], funds=engine.account, fills=[real_trade, real_trade])  # reported TWICE
    report = reconcile_against_broker(engine, fake_broker)
    assert not report.ok
    assert any(i.check == "duplicate_trade_at_broker" for i in report.issues)


def test_reconciliation_never_repairs_state():
    """Structural guarantee, matching paper/reconciliation.py's own posture:
    calling reconcile_against_broker must never mutate the engine."""
    engine = _engine_with_open_position()
    equity_before = engine.account.equity
    fake_broker = _FakeBroker(positions=[], funds=engine.account, fills=[])
    reconcile_against_broker(engine, fake_broker)
    assert engine.account.equity == equity_before
