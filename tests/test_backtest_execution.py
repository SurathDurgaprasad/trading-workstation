from datetime import datetime

import pandas as pd

from backtesting.costs import CostModel
from backtesting.engine import run_backtest
from backtesting.trade import ExitReason
from strategy.signal import ReasonCode, Side, Signal
from tests.conftest import make_bar, make_indicator_series


class _OneShotStrategy:
    """Emits exactly one fixed signal at a chosen bar index, nothing else —
    lets execution behavior be tested independently of entry-condition logic."""

    name = "one_shot_test_strategy"

    def __init__(self, *, at_index: int, stop_price: float, target_price: float):
        self._at_index = at_index
        self._stop_price = stop_price
        self._target_price = target_price
        self._fired = False

    def generate_signal(self, indicator_series, index, symbol):
        if index != self._at_index or self._fired:
            return None
        self._fired = True
        row = indicator_series.iloc[index]
        return Signal(
            symbol=symbol,
            generated_at=indicator_series.index[index],
            side=Side.LONG,
            reference_price=float(row["close"]),
            stop_price=self._stop_price,
            target_price=self._target_price,
            risk_reward=2.0,
            strategy_name=self.name,
            reason_codes=[ReasonCode.TREND_CONFIRMED],
        )


_ZERO_COST = CostModel(brokerage_per_fill=0.0, fees_pct=0.0, taxes_pct=0.0, entry_slippage_bps=0.0, exit_slippage_bps=0.0)


def test_entry_fills_at_next_bar_open_not_signal_bar_close():
    bars = [
        make_bar(close=100.0),  # index 0: signal generated here
        make_bar(open=105.0, high=106.0, low=104.0, close=105.5),  # index 1: entry bar
        make_bar(open=105.5, high=110.0, low=105.0, close=109.0),  # index 2: still open
    ]
    series = make_indicator_series(bars)
    strategy = _OneShotStrategy(at_index=0, stop_price=90.0, target_price=200.0)  # far away, won't trigger exit

    result = run_backtest(
        symbol="TEST", indicator_series=series, strategy=strategy, cost_model=_ZERO_COST, initial_capital=100_000
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_price == 105.0  # bar 1's OPEN, not bar 0's close (100.0) or bar 1's close (105.5)
    assert trade.entry_time == series.index[1]
    assert trade.signal_generated_at == series.index[0]


def test_target_hit_exits_at_target_price():
    bars = [
        make_bar(close=100.0),
        make_bar(open=101.0, high=101.5, low=100.5, close=101.0),  # entry bar
        make_bar(open=101.0, high=120.0, low=100.0, close=115.0),  # target (110) clearly hit, stop (90) not
    ]
    series = make_indicator_series(bars)
    strategy = _OneShotStrategy(at_index=0, stop_price=90.0, target_price=110.0)

    result = run_backtest(symbol="TEST", indicator_series=series, strategy=strategy, cost_model=_ZERO_COST)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == ExitReason.TARGET
    assert trade.exit_price == 110.0
    assert trade.exit_time == series.index[2]


def test_stop_hit_exits_at_stop_price():
    bars = [
        make_bar(close=100.0),
        make_bar(open=101.0, high=101.5, low=100.5, close=101.0),
        make_bar(open=101.0, high=102.0, low=85.0, close=90.0),  # stop (90) hit, target (110) not
    ]
    series = make_indicator_series(bars)
    strategy = _OneShotStrategy(at_index=0, stop_price=90.0, target_price=110.0)

    result = run_backtest(symbol="TEST", indicator_series=series, strategy=strategy, cost_model=_ZERO_COST)

    trade = result.trades[0]
    assert trade.exit_reason == ExitReason.STOP
    assert trade.exit_price == 90.0


def test_same_bar_stop_and_target_ambiguity_resolves_to_stop():
    bars = [
        make_bar(close=100.0),
        make_bar(open=101.0, high=101.5, low=100.5, close=101.0),
        # this single bar's range spans BOTH the stop (90) and the target (110) —
        # the conservative rule must pick STOP, never TARGET.
        make_bar(open=101.0, high=115.0, low=85.0, close=95.0),
    ]
    series = make_indicator_series(bars)
    strategy = _OneShotStrategy(at_index=0, stop_price=90.0, target_price=110.0)

    result = run_backtest(symbol="TEST", indicator_series=series, strategy=strategy, cost_model=_ZERO_COST)

    trade = result.trades[0]
    assert trade.exit_reason == ExitReason.STOP
    assert trade.exit_price == 90.0


def test_end_of_data_forces_a_close_on_the_last_bar():
    bars = [
        make_bar(close=100.0),
        make_bar(open=101.0, high=102.0, low=100.5, close=101.5),  # entry bar, nothing hit
        make_bar(open=101.5, high=103.0, low=101.0, close=102.0),  # last bar, still nothing hit
    ]
    series = make_indicator_series(bars)
    strategy = _OneShotStrategy(at_index=0, stop_price=50.0, target_price=500.0)  # unreachable

    result = run_backtest(symbol="TEST", indicator_series=series, strategy=strategy, cost_model=_ZERO_COST)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == ExitReason.END_OF_DATA
    assert trade.exit_price == 102.0  # last bar's close
    assert trade.exit_time == series.index[-1]


def test_no_signal_generated_on_the_final_bar_no_next_bar_to_enter_on():
    # A signal at the very last index has no i+1 to fill on — must be ignored.
    bars = [make_bar(close=100.0)]
    series = make_indicator_series(bars)
    strategy = _OneShotStrategy(at_index=0, stop_price=90.0, target_price=110.0)

    result = run_backtest(symbol="TEST", indicator_series=series, strategy=strategy, cost_model=_ZERO_COST)

    assert result.trades == []
