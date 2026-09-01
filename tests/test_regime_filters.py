"""Phase 9: the regime-filter candidates must be causal, and must only be
able to SUPPRESS an otherwise-valid signal -- never invent one, never alter
its price/stop/target. Mirrors the causality-testing style of
test_backtest_lookahead.py.
"""
import pandas as pd
import pytest

from strategy.baseline import TrendMomentumBaseline
from strategy.contracts import Strategy
from strategy.regime_filters import CANDIDATES, FilteredStrategy, add_regime_columns
from tests.conftest import make_bar, make_indicator_series


def _series_with_regime_columns(n=260, **overrides):
    bars = [make_bar(**overrides) for _ in range(n)]
    return add_regime_columns(make_indicator_series(bars))


@pytest.mark.parametrize("filter_name", list(CANDIDATES))
def test_filtered_strategy_satisfies_the_strategy_protocol(filter_name):
    filtered = FilteredStrategy(inner=TrendMomentumBaseline(), filter_name=filter_name, predicate=CANDIDATES[filter_name])
    assert isinstance(filtered, Strategy)
    assert filtered.version
    assert filtered.name == f"trend_momentum_baseline+{filter_name}"


@pytest.mark.parametrize("filter_name", list(CANDIDATES))
def test_filtered_strategy_never_returns_a_signal_the_inner_strategy_did_not(filter_name):
    """The filter can only suppress -- it must be impossible for the
    filtered strategy to produce a signal at a bar where the unchanged
    inner strategy would not have."""
    series = _series_with_regime_columns()
    inner = TrendMomentumBaseline()
    filtered = FilteredStrategy(inner=inner, filter_name=filter_name, predicate=CANDIDATES[filter_name])

    for i in range(len(series)):
        inner_signal = inner.generate_signal(series, i, "TEST")
        filtered_signal = filtered.generate_signal(series, i, "TEST")
        if inner_signal is None:
            assert filtered_signal is None
        if filtered_signal is not None:
            # When the filter DOES allow a signal through, it must be
            # byte-identical to the inner strategy's own signal -- never a
            # different price/stop/target/side.
            assert filtered_signal.model_dump() == inner_signal.model_dump()


@pytest.mark.parametrize("filter_name", list(CANDIDATES))
def test_filter_decision_at_bar_t_is_causal(filter_name):
    """Mutating bars strictly AFTER bar T must not change the filter's
    allow/suppress decision at bar T -- same control-case structure as
    test_backtest_lookahead.py."""
    series = _series_with_regime_columns(n=260)
    inner = TrendMomentumBaseline()
    filtered = FilteredStrategy(inner=inner, filter_name=filter_name, predicate=CANDIDATES[filter_name])
    target_index = 220  # deep enough for sma_200/atr_median_100 to be non-NaN

    signal_before = filtered.generate_signal(series, target_index, "TEST")

    mutated = series.copy()
    future_rows = mutated.index[target_index + 1 :]
    mutated.loc[future_rows, "close"] = 1.0
    mutated.loc[future_rows, "sma_200"] = 99999.0
    mutated.loc[future_rows, "atr_14"] = 99999.0
    mutated.loc[future_rows, "atr_median_100"] = 0.0001
    mutated.loc[future_rows, "sma_20"] = 1.0
    mutated.loc[future_rows, "sma_50"] = 99999.0

    signal_after = filtered.generate_signal(mutated, target_index, "TEST")

    if signal_before is None:
        assert signal_after is None
    else:
        assert signal_after is not None
        assert signal_before.model_dump() == signal_after.model_dump()


def test_add_regime_columns_does_not_mutate_the_input_frame():
    series = make_indicator_series([make_bar() for _ in range(210)])
    original_columns = set(series.columns)
    add_regime_columns(series)
    assert set(series.columns) == original_columns  # caller's frame untouched


def test_add_regime_columns_is_causal_by_construction():
    """Same structural check as test_backtest_lookahead.py's indicator-
    series test, applied to the two Phase 9 columns."""
    series = make_indicator_series([make_bar(close=100 + i * 0.4) for i in range(260)])
    augmented = add_regime_columns(series)

    check_index = 210
    truncated = add_regime_columns(series.iloc[: check_index + 1])

    full_row = augmented.iloc[check_index]
    truncated_row = truncated.iloc[-1]
    for column in ("sma_200", "atr_median_100"):
        full_value, truncated_value = full_row[column], truncated_row[column]
        if pd.isna(full_value) and pd.isna(truncated_value):
            continue
        assert full_value == truncated_value, f"{column} at row {check_index} depends on future data"
