import math
from datetime import datetime

from backtesting.costs import CostModel
from backtesting.execution import OpenPosition, close_trade
from backtesting.trade import ExitReason
from strategy.signal import ReasonCode, Side, Signal


def _signal(**overrides) -> Signal:
    base = dict(
        symbol="TEST",
        generated_at=datetime(2026, 1, 1),
        side=Side.LONG,
        reference_price=100.0,
        stop_price=95.0,
        target_price=110.0,
        risk_reward=2.0,
        strategy_name="unit-test",
        reason_codes=[ReasonCode.TREND_CONFIRMED],
    )
    base.update(overrides)
    return Signal(**base)


def test_position_carries_entry_fields_through_to_the_closed_trade():
    position = OpenPosition(
        signal=_signal(),
        entry_time=datetime(2026, 1, 2),
        entry_price=101.0,
        quantity=25,
        stop_price=96.0,
        target_price=111.0,
    )

    trade = close_trade(
        position,
        exit_price=111.0,
        exit_time=datetime(2026, 1, 5),
        exit_reason=ExitReason.TARGET,
        symbol="TEST",
        cost_model=CostModel(brokerage_per_fill=0, fees_pct=0, taxes_pct=0),
    )

    assert trade.symbol == "TEST"
    assert trade.side == Side.LONG
    assert trade.entry_time == datetime(2026, 1, 2)
    assert trade.entry_price == 101.0
    assert trade.quantity == 25
    assert trade.stop_price == 96.0
    assert trade.target_price == 111.0
    assert trade.exit_time == datetime(2026, 1, 5)
    assert trade.exit_price == 111.0
    assert trade.exit_reason == ExitReason.TARGET


def test_r_multiple_is_net_pnl_over_initial_dollar_risk():
    # entry 100, stop 90 -> risk per unit = 10; quantity 5 -> initial risk = 50
    position = OpenPosition(
        signal=_signal(stop_price=90.0),
        entry_time=datetime(2026, 1, 2),
        entry_price=100.0,
        quantity=5,
        stop_price=90.0,
        target_price=130.0,
    )
    zero_cost = CostModel(brokerage_per_fill=0, fees_pct=0, taxes_pct=0)

    # Exit at target (130): gross = (130-100)*5 = 150, net = 150 (zero cost).
    # initial_risk = (100-90)*5 = 50 -> R = 150/50 = 3.0 (matches the 3R target distance).
    trade = close_trade(
        position, exit_price=130.0, exit_time=datetime(2026, 1, 5),
        exit_reason=ExitReason.TARGET, symbol="TEST", cost_model=zero_cost,
    )
    assert math.isclose(trade.r_multiple, 3.0)


def test_r_multiple_is_negative_one_on_a_clean_stop_out():
    position = OpenPosition(
        signal=_signal(stop_price=90.0),
        entry_time=datetime(2026, 1, 2),
        entry_price=100.0,
        quantity=5,
        stop_price=90.0,
        target_price=130.0,
    )
    zero_cost = CostModel(brokerage_per_fill=0, fees_pct=0, taxes_pct=0)

    trade = close_trade(
        position, exit_price=90.0, exit_time=datetime(2026, 1, 3),
        exit_reason=ExitReason.STOP, symbol="TEST", cost_model=zero_cost,
    )
    assert math.isclose(trade.r_multiple, -1.0)


def test_quantity_is_always_a_whole_number_of_units():
    position = OpenPosition(
        signal=_signal(), entry_time=datetime(2026, 1, 2), entry_price=100.0,
        quantity=7, stop_price=95.0, target_price=110.0,
    )
    assert isinstance(position.quantity, int)
