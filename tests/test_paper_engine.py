"""Level 1/2 (mostly real components, in-memory SQLite — no mocks on any
paper-trading internals; only the data itself is synthetic)."""

from datetime import datetime

import pytest

from paper.engine import Bar, PaperTradingEngine
from paper.models import JournalOutcome, OrderStatus, PositionStatus
from paper.reconciliation import reconcile
from paper.store import PaperStore
from risk.config import RiskConfig
from risk.engine import RiskEngine
from strategy.signal import ReasonCode, Side, Signal


def _signal(**overrides) -> Signal:
    base = dict(
        symbol="TEST", generated_at=datetime(2026, 1, 1), side=Side.LONG,
        reference_price=100.0, stop_price=95.0, target_price=110.0, risk_reward=2.0,
        strategy_name="unit-test", reason_codes=[ReasonCode.TREND_CONFIRMED],
    )
    base.update(overrides)
    return Signal(**base)


@pytest.fixture
def engine() -> PaperTradingEngine:
    return PaperTradingEngine(PaperStore(":memory:"), initial_capital=100_000.0)


def test_submit_signal_creates_a_pending_order(engine):
    journal = engine.submit_signal(_signal())
    assert journal.outcome == JournalOutcome.APPROVED_PENDING
    assert journal.order_id is not None

    order = engine.store.get_pending_order("TEST")
    assert order is not None
    assert order.status == OrderStatus.PENDING


def test_pending_order_fills_at_the_next_bars_open_not_the_signal_bars_price(engine):
    engine.submit_signal(_signal(reference_price=100.0))
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=103.0, high=103.5, low=102.5, close=103.2))

    position = engine.store.get_open_position("TEST")
    assert position is not None
    assert position.entry_price != 100.0  # not the signal's reference_price
    assert abs(position.entry_price - 103.0) < 1.0  # slippage-adjusted, close to the bar's open


def test_target_hit_closes_the_position_and_records_a_trade(engine):
    engine.submit_signal(_signal(stop_price=95.0, target_price=110.0))
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=101.5, low=100.5, close=101.0))
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 3), open=101.0, high=120.0, low=100.0, close=115.0))

    position = engine.store.get_open_position("TEST")
    assert position is None  # no longer open

    trades = engine.store.list_trades()
    assert len(trades) == 1
    assert trades[0].exit_price == 110.0

    journal = engine.store.find_journal_entry_by_signal_id(_signal().stable_id())
    assert journal.outcome == JournalOutcome.APPROVED_FILLED_CLOSED
    assert journal.trade_id is not None


def test_stop_hit_closes_the_position_at_the_stop_price(engine):
    engine.submit_signal(_signal(stop_price=95.0, target_price=110.0))
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=101.5, low=100.5, close=101.0))
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 3), open=101.0, high=102.0, low=90.0, close=93.0))

    trades = engine.store.list_trades()
    assert len(trades) == 1
    assert trades[0].exit_price == 95.0
    from backtesting.trade import ExitReason
    assert trades[0].exit_reason == ExitReason.STOP


def test_same_bar_stop_and_target_ambiguity_resolves_to_stop_matching_the_backtester(engine):
    engine.submit_signal(_signal(stop_price=95.0, target_price=110.0))
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=101.5, low=100.5, close=101.0))
    # This single bar's range spans BOTH stop (95) and target (110).
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 3), open=101.0, high=115.0, low=90.0, close=98.0))

    trades = engine.store.list_trades()
    assert len(trades) == 1
    assert trades[0].exit_price == 95.0
    from backtesting.trade import ExitReason
    assert trades[0].exit_reason == ExitReason.STOP


def test_end_of_data_forces_a_close_at_the_last_bars_close(engine):
    engine.submit_signal(_signal(stop_price=50.0, target_price=500.0))  # unreachable levels
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=102.0, low=100.5, close=101.5))
    last_bar = Bar(timestamp=datetime(2026, 1, 3), open=101.5, high=103.0, low=101.0, close=102.0)
    engine.process_bar("TEST", last_bar)
    engine.close_at_end_of_data("TEST", last_bar)

    trades = engine.store.list_trades()
    assert len(trades) == 1
    from backtesting.trade import ExitReason
    assert trades[0].exit_reason == ExitReason.END_OF_DATA


def test_rejected_signal_is_journaled_not_silently_dropped():
    strict = PaperTradingEngine(PaperStore(":memory:"), risk_engine=RiskEngine(RiskConfig(min_risk_reward=5.0)))
    journal = strict.submit_signal(_signal(risk_reward=2.0))
    assert journal.outcome == JournalOutcome.REJECTED
    assert strict.store.get_pending_order("TEST") is None


def test_duplicate_signal_does_not_create_a_duplicate_order_or_journal_row(engine):
    signal = _signal()
    j1 = engine.submit_signal(signal)
    j2 = engine.submit_signal(signal)
    assert j1.journal_entry_id == j2.journal_entry_id
    assert len(engine.store.list_journal_entries()) == 1


def test_a_second_signal_while_one_is_pending_does_not_stack_a_position(engine):
    first = _signal(generated_at=datetime(2026, 1, 1))
    second = _signal(generated_at=datetime(2026, 1, 1, 1))  # different bar -> different stable_id
    assert first.stable_id() != second.stable_id()

    j1 = engine.submit_signal(first)
    j2 = engine.submit_signal(second)

    assert j1.outcome == JournalOutcome.APPROVED_PENDING
    assert j2.outcome == JournalOutcome.SKIPPED_ALREADY_ACTIVE
    assert len(engine.store._fetch_all_json("paper_orders")) == 1


def test_a_second_signal_while_a_position_is_open_does_not_stack(engine):
    # Here account.open_positions is already 1 by the time the second signal
    # is evaluated, so RiskEngine's OWN POSITION_ALREADY_OPEN veto fires
    # (Phase 4 behavior) -- REJECTED, not the engine-level SKIPPED_ALREADY_ACTIVE
    # path (that one is specifically for the narrower pending-order gap,
    # tested separately above, where account state hasn't caught up yet).
    first = _signal(generated_at=datetime(2026, 1, 1))
    engine.submit_signal(first)
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=101.5, low=100.5, close=101.0))
    assert engine.store.get_open_position("TEST") is not None

    second = _signal(generated_at=datetime(2026, 1, 2, 1))
    j2 = engine.submit_signal(second)
    assert j2.outcome == JournalOutcome.REJECTED
    from risk.veto import VetoReason
    risk_decision = engine.store.get_risk_decision(j2.risk_decision_id)
    assert VetoReason.POSITION_ALREADY_OPEN in risk_decision.veto_reasons
    assert len(engine.store.list_positions()) == 1


def test_account_reconciles_cleanly_after_a_full_lifecycle(engine):
    engine.submit_signal(_signal())
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=101.5, low=100.5, close=101.0))
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 3), open=101.0, high=120.0, low=100.0, close=115.0))

    report = reconcile(engine.store)
    assert report.ok, report.issues


def test_journal_carries_explicit_versions_not_latest(engine):
    journal = engine.submit_signal(_signal())
    assert journal.strategy_version != "latest"
    assert journal.risk_config_version != "latest"
    assert journal.execution_model_version != "latest"
    assert len(journal.risk_config_version) > 0
