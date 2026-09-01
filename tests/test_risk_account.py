import math
from datetime import date

import pytest

from risk.account import new_account


def test_new_account_starts_flat_at_initial_capital():
    account = new_account(10_000.0)
    assert account.cash == 10_000.0
    assert account.equity == 10_000.0
    assert account.peak_equity == 10_000.0
    assert account.open_positions == 0
    assert account.consecutive_losses == 0
    assert account.total_trades == 0


def test_equity_invariant_holds_through_a_full_round_trip():
    account = new_account(10_000.0)

    account.open_position(quantity=10, entry_price=100.0, entry_cost=5.0)
    # cash committed: 10*100 + 5 = 1005; equity should still be ~10000 - 5 (the entry cost is a real loss so far)
    assert math.isclose(account.equity, account.cash + account.open_position_notional)
    assert math.isclose(account.equity, 10_000.0 - 5.0)

    account.mark_to_market(110.0)  # price moved up 10/unit * 10 units = +100 unrealized
    assert math.isclose(account.unrealized_pnl, 100.0)
    assert math.isclose(account.equity, account.cash + account.open_position_notional)
    assert math.isclose(account.equity, 10_000.0 - 5.0 + 100.0)

    account.close_position(exit_price=110.0, exit_cost=5.0, net_pnl=100.0 - 5.0 - 5.0)
    assert account.open_positions == 0
    assert math.isclose(account.equity, account.cash)  # flat: equity == cash exactly
    assert math.isclose(account.equity, 10_000.0 + (100.0 - 5.0 - 5.0))
    assert account.total_trades == 1


def test_peak_equity_never_decreases_and_drawdown_is_relative_to_it():
    account = new_account(10_000.0)

    account.open_position(quantity=1, entry_price=100.0, entry_cost=0.0)
    account.mark_to_market(120.0)  # equity rises to 10,020 -> new peak
    assert account.peak_equity >= 10_000.0
    peak_after_gain = account.peak_equity

    account.mark_to_market(80.0)  # equity falls to 9,980 -> peak must NOT decrease
    assert account.peak_equity == peak_after_gain
    assert account.current_drawdown_pct > 0


def test_drawdown_is_zero_at_a_new_peak():
    account = new_account(10_000.0)
    account.mark_to_market(0.0)  # no open position; equity unchanged at initial capital (a fresh peak)
    assert account.current_drawdown_pct == 0.0


def test_consecutive_losses_increments_on_loss_and_resets_on_win():
    account = new_account(10_000.0)

    for _ in range(3):
        account.open_position(quantity=1, entry_price=100.0, entry_cost=0.0)
        account.close_position(exit_price=90.0, exit_cost=0.0, net_pnl=-10.0)
    assert account.consecutive_losses == 3

    account.open_position(quantity=1, entry_price=100.0, entry_cost=0.0)
    account.close_position(exit_price=110.0, exit_cost=0.0, net_pnl=10.0)
    assert account.consecutive_losses == 0  # a win resets the streak


def test_cannot_open_a_second_position_while_one_is_already_open():
    account = new_account(10_000.0)
    account.open_position(quantity=1, entry_price=100.0, entry_cost=0.0)
    with pytest.raises(ValueError):
        account.open_position(quantity=1, entry_price=100.0, entry_cost=0.0)


def test_cannot_close_a_position_that_is_not_open():
    account = new_account(10_000.0)
    with pytest.raises(ValueError):
        account.close_position(exit_price=100.0, exit_cost=0.0, net_pnl=0.0)


def test_cannot_open_a_non_positive_quantity():
    account = new_account(10_000.0)
    with pytest.raises(ValueError):
        account.open_position(quantity=0, entry_price=100.0, entry_cost=0.0)
    with pytest.raises(Exception):
        account.open_position(quantity=-5, entry_price=100.0, entry_cost=0.0)


def test_roll_to_day_resets_daily_start_equity_only_on_a_new_day():
    account = new_account(10_000.0)
    account.roll_to_day(date(2026, 1, 1))
    assert account.daily_start_equity == 10_000.0

    account.open_position(quantity=1, entry_price=100.0, entry_cost=0.0)
    account.mark_to_market(150.0)  # equity now 10,050, same day -> daily_start_equity must NOT move
    account.roll_to_day(date(2026, 1, 1))
    assert account.daily_start_equity == 10_000.0
    assert account.daily_pnl == 50.0

    account.roll_to_day(date(2026, 1, 2))  # new day -> re-baseline
    assert account.daily_start_equity == account.equity
    assert account.daily_pnl == 0.0


def test_full_trade_lifecycle_transition_sequence():
    account = new_account(10_000.0)
    account.roll_to_day(date(2026, 1, 1))

    # winning trade -> new peak
    account.open_position(quantity=10, entry_price=100.0, entry_cost=0.0)
    account.close_position(exit_price=110.0, exit_cost=0.0, net_pnl=100.0)
    assert account.equity == 10_100.0
    assert account.peak_equity == 10_100.0
    assert account.consecutive_losses == 0

    # losing trade -> drawdown appears, streak starts
    account.open_position(quantity=10, entry_price=110.0, entry_cost=0.0)
    account.close_position(exit_price=100.0, exit_cost=0.0, net_pnl=-100.0)
    assert account.equity == 10_000.0
    assert account.peak_equity == 10_100.0
    assert account.current_drawdown_pct == pytest.approx((10_100.0 - 10_000.0) / 10_100.0 * 100)
    assert account.consecutive_losses == 1
