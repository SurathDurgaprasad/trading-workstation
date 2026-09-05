import random
from datetime import datetime, timedelta

import pandas as pd
import pytest

from backtesting.random_baseline import (
    MonteCarloIteration,
    RandomBaselineMonteCarloResult,
    RandomEntryStrategy,
    run_random_baseline_monte_carlo,
)
from strategy.signal import ReasonCode, Side


def _series(n: int = 60, *, start: float = 100.0, atr: float = 2.0) -> pd.DataFrame:
    index = [datetime(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    closes = [start + 0.1 * i for i in range(n)]
    return pd.DataFrame({
        "open": closes, "high": [c + 1.0 for c in closes], "low": [c - 1.0 for c in closes],
        "close": closes, "atr_14": [atr] * n,
    }, index=index)


# --- RandomEntryStrategy --------------------------------------------------------


def test_random_entry_strategy_fires_exactly_target_count_when_enough_bars():
    series = _series(60)
    strategy = RandomEntryStrategy(target_trade_count=5, rng=random.Random(42))

    fired = [i for i in range(len(series)) if strategy.generate_signal(series, i, "TEST") is not None]

    assert len(fired) == 5


def test_random_entry_strategy_caps_at_available_eligible_bars():
    series = _series(3)
    strategy = RandomEntryStrategy(target_trade_count=1_000, rng=random.Random(1))

    fired = [i for i in range(len(series)) if strategy.generate_signal(series, i, "TEST") is not None]

    assert len(fired) == 3  # capped, not fabricated beyond what exists


def test_random_entry_strategy_is_deterministic_for_a_fixed_seed():
    series = _series(60)
    fired_a = [i for i in range(len(series)) if RandomEntryStrategy(target_trade_count=5, rng=random.Random(7)).generate_signal(series, i, "TEST") is not None]
    fired_b = [i for i in range(len(series)) if RandomEntryStrategy(target_trade_count=5, rng=random.Random(7)).generate_signal(series, i, "TEST") is not None]

    assert fired_a == fired_b


def test_random_entry_strategy_different_seeds_produce_different_entries():
    series = _series(60)
    fired_a = {i for i in range(len(series)) if RandomEntryStrategy(target_trade_count=5, rng=random.Random(1)).generate_signal(series, i, "TEST") is not None}
    fired_b = {i for i in range(len(series)) if RandomEntryStrategy(target_trade_count=5, rng=random.Random(2)).generate_signal(series, i, "TEST") is not None}

    assert fired_a != fired_b


def test_random_entry_strategy_signal_uses_the_same_atr_stop_target_math_as_baseline():
    series = _series(10, start=100.0, atr=2.0)
    strategy = RandomEntryStrategy(target_trade_count=10, rng=random.Random(1))

    signal = strategy.generate_signal(series, 0, "TEST")

    assert signal is not None
    assert signal.side == Side.LONG
    assert signal.reason_codes == [ReasonCode.RANDOM_BASELINE]
    # STOP_ATR_MULTIPLIER=1.5, TARGET_RISK_REWARD=2.0 (strategy/baseline.py)
    assert signal.stop_price == pytest.approx(100.0 - 2.0 * 1.5)
    assert signal.target_price == pytest.approx(100.0 + 2.0 * 1.5 * 2.0)


def test_random_entry_strategy_zero_target_count_fires_nothing():
    series = _series(10)
    strategy = RandomEntryStrategy(target_trade_count=0, rng=random.Random(1))

    fired = [i for i in range(len(series)) if strategy.generate_signal(series, i, "TEST") is not None]

    assert fired == []


# --- run_random_baseline_monte_carlo --------------------------------------------


def test_monte_carlo_produces_one_result_per_iteration():
    series_by_symbol = {"AAA": _series(60), "BBB": _series(60, start=50.0)}
    real_counts = {"AAA": 3, "BBB": 2}

    result = run_random_baseline_monte_carlo(
        indicator_series_by_symbol=series_by_symbol, real_trade_counts_by_symbol=real_counts,
        iterations=5, initial_capital=100_000.0,
    )

    assert len(result.iterations) == 5
    assert all(isinstance(it, MonteCarloIteration) for it in result.iterations)


def test_monte_carlo_is_reproducible_for_the_same_base_seed():
    series_by_symbol = {"AAA": _series(60)}
    real_counts = {"AAA": 3}

    result_a = run_random_baseline_monte_carlo(indicator_series_by_symbol=series_by_symbol, real_trade_counts_by_symbol=real_counts, iterations=3, base_seed=10)
    result_b = run_random_baseline_monte_carlo(indicator_series_by_symbol=series_by_symbol, real_trade_counts_by_symbol=real_counts, iterations=3, base_seed=10)

    assert [it.mean_return_pct for it in result_a.iterations] == [it.mean_return_pct for it in result_b.iterations]
    assert [it.pooled_trades for it in result_a.iterations] == [it.pooled_trades for it in result_b.iterations]


def test_monte_carlo_skips_a_symbol_with_zero_real_trades():
    series_by_symbol = {"AAA": _series(60), "NEVER_TRADED": _series(60)}
    real_counts = {"AAA": 3}  # NEVER_TRADED intentionally absent

    result = run_random_baseline_monte_carlo(indicator_series_by_symbol=series_by_symbol, real_trade_counts_by_symbol=real_counts, iterations=2)

    # Can't directly see per-symbol trades from the public result, but a
    # symbol given zero target count must not silently trade anyway --
    # sanity bound: pooled_trades never exceeds the real AAA count (3).
    assert all(it.pooled_trades <= 3 for it in result.iterations)


def test_fraction_random_at_least_as_good_is_none_without_a_real_comparison_value():
    result = RandomBaselineMonteCarloResult(iterations=[MonteCarloIteration(seed=0, pooled_trades=1, mean_return_pct=1.0)])

    assert result.fraction_random_at_least_as_good is None


def test_fraction_random_at_least_as_good_computes_correctly():
    result = RandomBaselineMonteCarloResult(
        iterations=[
            MonteCarloIteration(seed=0, pooled_trades=1, mean_return_pct=-1.0),
            MonteCarloIteration(seed=1, pooled_trades=1, mean_return_pct=0.0),
            MonteCarloIteration(seed=2, pooled_trades=1, mean_return_pct=1.0),
            MonteCarloIteration(seed=3, pooled_trades=1, mean_return_pct=2.0),
        ],
        real_strategy_mean_return_pct=0.5,
    )

    # 2 of 4 iterations (1.0 and 2.0) are >= 0.5
    assert result.fraction_random_at_least_as_good == pytest.approx(0.5)


def test_fraction_random_at_least_as_good_is_none_for_no_iterations():
    result = RandomBaselineMonteCarloResult(iterations=[], real_strategy_mean_return_pct=0.5)

    assert result.fraction_random_at_least_as_good is None
