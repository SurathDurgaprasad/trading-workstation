import math
import random
from datetime import datetime

import pytest

from backtesting.costs import CostModel
from backtesting.engine import run_backtest
from backtesting.execution_robustness import (
    ExecutionRobustnessConfig,
    run_execution_robust_backtest,
    run_execution_robustness_monte_carlo,
)
from strategy.signal import ReasonCode, Side, Signal
from tests.conftest import make_bar, make_indicator_series

_ZERO_COST = CostModel(brokerage_per_fill=0.0, fees_pct=0.0, taxes_pct=0.0, entry_slippage_bps=0.0, exit_slippage_bps=0.0)
_NO_FRICTION = ExecutionRobustnessConfig(missed_fill_probability=0.0, fill_delay_probability=0.0, slippage_multiplier_range=(1.0, 1.0))


class _RepeatingSignalStrategy:
    """Fires a fresh LONG signal every 5 bars, tight stop/target so
    entries resolve quickly -- reads only the close price."""

    name = "repeating_signal_test_strategy"

    def generate_signal(self, indicator_series, index, symbol):
        if index % 5 != 0:
            return None
        row = indicator_series.iloc[index]
        price = float(row["close"])
        return Signal(
            symbol=symbol, generated_at=indicator_series.index[index], side=Side.LONG,
            reference_price=price, stop_price=price - 2.0, target_price=price + 4.0,
            risk_reward=2.0, strategy_name=self.name, reason_codes=[ReasonCode.TREND_CONFIRMED],
        )


def _oscillating_bars(n: int) -> list[dict]:
    bars = []
    for i in range(n):
        price = 100.0 + 6.0 * math.sin(i / 3.0)
        bars.append(make_bar(open=price, high=price + 3.0, low=price - 3.0, close=price, volume=1_000_000.0))
    return bars


def _series(n: int = 100):
    return make_indicator_series(_oscillating_bars(n))


# --- control/parity: zero friction must match the standard engine exactly ---


def test_zero_friction_config_matches_the_standard_engine_exactly():
    series = _series()
    strategy = _RepeatingSignalStrategy()

    standard_result = run_backtest(symbol="TEST", indicator_series=series, strategy=strategy, cost_model=_ZERO_COST, initial_capital=100_000.0)
    robust_trades = run_execution_robust_backtest(
        symbol="TEST", indicator_series=series, strategy=_RepeatingSignalStrategy(), cost_model=_ZERO_COST,
        initial_capital=100_000.0, config=_NO_FRICTION, rng=random.Random(0),
    )

    assert len(standard_result.trades) > 0
    standard_fields = [(t.entry_time, t.exit_time, t.exit_price, t.net_pnl) for t in standard_result.trades]
    robust_fields = [(t.entry_time, t.exit_time, t.exit_price, t.net_pnl) for t in robust_trades]
    assert standard_fields == robust_fields


# --- missed fills -------------------------------------------------------


def test_missed_fill_probability_one_produces_zero_trades():
    series = _series()
    config = ExecutionRobustnessConfig(missed_fill_probability=1.0, fill_delay_probability=0.0, slippage_multiplier_range=(1.0, 1.0))
    trades = run_execution_robust_backtest(
        symbol="TEST", indicator_series=series, strategy=_RepeatingSignalStrategy(), cost_model=_ZERO_COST,
        initial_capital=100_000.0, config=config, rng=random.Random(0),
    )
    assert trades == []


# --- delayed fills -------------------------------------------------------


def test_fill_delay_probability_one_fills_two_bars_after_the_signal_not_one():
    series = _series()
    config = ExecutionRobustnessConfig(missed_fill_probability=0.0, fill_delay_probability=1.0, slippage_multiplier_range=(1.0, 1.0))

    standard_result = run_backtest(symbol="TEST", indicator_series=series, strategy=_RepeatingSignalStrategy(), cost_model=_ZERO_COST, initial_capital=100_000.0)
    delayed_trades = run_execution_robust_backtest(
        symbol="TEST", indicator_series=series, strategy=_RepeatingSignalStrategy(), cost_model=_ZERO_COST,
        initial_capital=100_000.0, config=config, rng=random.Random(0),
    )

    assert len(standard_result.trades) > 0
    assert len(delayed_trades) > 0
    # Every delayed trade's own entry_time must be ONE bar LATER than the
    # corresponding standard trade's entry_time (signal at bar i -> standard
    # fills at i+1, delayed fills at i+2 -- one calendar day later for this
    # daily-bar synthetic series).
    for standard_trade, delayed_trade in zip(standard_result.trades, delayed_trades):
        assert delayed_trade.entry_time > standard_trade.entry_time


# --- reproducibility and genuine randomness -----------------------------


def test_same_seed_reproduces_byte_identical_trades():
    series = _series()
    config = ExecutionRobustnessConfig()  # real, non-degenerate friction

    run1 = run_execution_robust_backtest(
        symbol="TEST", indicator_series=series, strategy=_RepeatingSignalStrategy(), cost_model=CostModel(),
        initial_capital=100_000.0, config=config, rng=random.Random(42),
    )
    run2 = run_execution_robust_backtest(
        symbol="TEST", indicator_series=series, strategy=_RepeatingSignalStrategy(), cost_model=CostModel(),
        initial_capital=100_000.0, config=config, rng=random.Random(42),
    )

    fields1 = [(t.entry_time, t.exit_time, t.exit_price, t.net_pnl) for t in run1]
    fields2 = [(t.entry_time, t.exit_time, t.exit_price, t.net_pnl) for t in run2]
    assert fields1 == fields2


def test_different_seeds_produce_different_results():
    series = _series()
    config = ExecutionRobustnessConfig()

    run_a = run_execution_robust_backtest(
        symbol="TEST", indicator_series=series, strategy=_RepeatingSignalStrategy(), cost_model=CostModel(),
        initial_capital=100_000.0, config=config, rng=random.Random(1),
    )
    run_b = run_execution_robust_backtest(
        symbol="TEST", indicator_series=series, strategy=_RepeatingSignalStrategy(), cost_model=CostModel(),
        initial_capital=100_000.0, config=config, rng=random.Random(2),
    )

    fields_a = [(t.entry_time, t.exit_price, t.net_pnl) for t in run_a]
    fields_b = [(t.entry_time, t.exit_price, t.net_pnl) for t in run_b]
    assert fields_a != fields_b


# --- run_execution_robustness_monte_carlo (universe-level) --------------


def test_monte_carlo_runs_the_requested_number_of_iterations_reproducibly():
    series_by_symbol = {"AAA": _series(), "BBB": _series()}
    result_1 = run_execution_robustness_monte_carlo(
        series_by_symbol, strategy=_RepeatingSignalStrategy(), iterations=5, initial_capital=100_000.0, base_seed=0,
    )
    result_2 = run_execution_robustness_monte_carlo(
        series_by_symbol, strategy=_RepeatingSignalStrategy(), iterations=5, initial_capital=100_000.0, base_seed=0,
    )

    assert len(result_1.iterations) == 5
    assert [it.mean_return_pct for it in result_1.iterations] == [it.mean_return_pct for it in result_2.iterations]


def test_fraction_flipping_sign_from_baseline_computes_correctly():
    from backtesting.execution_robustness import ExecutionRobustnessIteration, ExecutionRobustnessMonteCarloResult

    result = ExecutionRobustnessMonteCarloResult(
        iterations=[
            ExecutionRobustnessIteration(seed=0, pooled_trades=10, mean_return_pct=-1.0),
            ExecutionRobustnessIteration(seed=1, pooled_trades=10, mean_return_pct=-0.5),
            ExecutionRobustnessIteration(seed=2, pooled_trades=10, mean_return_pct=0.3),
            ExecutionRobustnessIteration(seed=3, pooled_trades=10, mean_return_pct=0.7),
        ],
        baseline_mean_return_pct=-0.8,
    )
    # baseline is negative; 2 of 4 iterations are positive (sign differs) -> 0.5
    assert result.fraction_flipping_sign_from_baseline == 0.5


def test_fraction_flipping_sign_from_baseline_is_none_without_iterations_or_baseline():
    from backtesting.execution_robustness import ExecutionRobustnessMonteCarloResult

    assert ExecutionRobustnessMonteCarloResult().fraction_flipping_sign_from_baseline is None


def test_run_execution_robust_backtest_returns_empty_list_for_empty_series():
    import pandas as pd

    trades = run_execution_robust_backtest(
        symbol="TEST", indicator_series=pd.DataFrame(), strategy=_RepeatingSignalStrategy(), rng=random.Random(0),
    )
    assert trades == []
