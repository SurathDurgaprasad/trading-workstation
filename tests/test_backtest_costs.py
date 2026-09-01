import math

from backtesting.costs import CostModel
from strategy.signal import Side


def test_cost_for_fill_combines_flat_brokerage_and_percentage_costs():
    model = CostModel(brokerage_per_fill=20.0, fees_pct=0.1, taxes_pct=0.2)
    # notional 10,000 -> fees+taxes = 0.3% of 10,000 = 30.0, plus flat 20.0
    assert math.isclose(model.cost_for_fill(notional=10_000.0), 50.0)


def test_zero_cost_model_charges_nothing():
    model = CostModel(brokerage_per_fill=0.0, fees_pct=0.0, taxes_pct=0.0)
    assert model.cost_for_fill(notional=1_000_000.0) == 0.0


def test_entry_slippage_makes_a_long_fill_worse_not_better():
    model = CostModel(entry_slippage_bps=10.0)  # 0.10%
    filled = model.slippage_adjusted_price(price=100.0, side=Side.LONG, is_entry=True)
    assert math.isclose(filled, 100.10)  # buys at a HIGHER price than theoretical


def test_exit_slippage_makes_a_long_exit_worse_not_better():
    model = CostModel(exit_slippage_bps=10.0)
    filled = model.slippage_adjusted_price(price=100.0, side=Side.LONG, is_entry=False)
    assert math.isclose(filled, 99.90)  # sells at a LOWER price than theoretical


def test_gross_minus_costs_equals_net_on_a_known_trade():
    from backtesting.execution import OpenPosition, close_trade
    from strategy.signal import ReasonCode, Signal
    from datetime import datetime

    model = CostModel(brokerage_per_fill=10.0, fees_pct=0.0, taxes_pct=0.0)
    signal = Signal(
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
    position = OpenPosition(
        signal=signal,
        entry_time=datetime(2026, 1, 2),
        entry_price=100.0,
        quantity=10,
        stop_price=95.0,
        target_price=110.0,
    )

    trade = close_trade(
        position,
        exit_price=110.0,
        exit_time=datetime(2026, 1, 3),
        exit_reason=trade_exit_reason(),
        symbol="TEST",
        cost_model=model,
    )

    assert math.isclose(trade.gross_pnl, 100.0)  # (110-100)*10
    assert math.isclose(trade.costs, 20.0)  # 10.0 brokerage on entry + 10.0 on exit, 0 fees/taxes
    assert math.isclose(trade.net_pnl, 80.0)
    assert math.isclose(trade.net_pnl, trade.gross_pnl - trade.costs)


def trade_exit_reason():
    from backtesting.trade import ExitReason

    return ExitReason.TARGET
