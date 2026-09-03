"""Phase 10: permanent causality/leakage regression tests for every alpha
feature (spec's explicit requirement — "for every promising feature add a
permanent causality test... this must become a permanent regression test").
Mirrors the truncated-history-equivalence and mutate-the-future style
already established in test_backtest_lookahead.py and test_regime_filters.py.
"""
import pandas as pd
import pytest

from market.indicators import compute_indicator_series
from market.data_provider import OHLCV
from quant_research.alpha_features import FEATURE_COLUMNS, add_alpha_features, add_forward_return_targets


def _ohlcv(n, symbol="TEST", seed_close=100.0):
    bars = [
        {
            "Open": seed_close + i * 0.3,
            "High": seed_close + i * 0.3 + 1.2,
            "Low": seed_close + i * 0.3 - 1.2,
            "Close": seed_close + i * 0.3 + (0.6 if i % 4 == 0 else -0.3),
            "Volume": 1_000_000 + (i % 11) * 15_000,
        }
        for i in range(n)
    ]
    frame = pd.DataFrame(bars, index=pd.date_range("2024-01-01", periods=n, freq="D"))
    return OHLCV.from_dataframe(symbol=symbol, interval="1d", frame=frame)


def _augmented(n=260, market_n=260):
    series = compute_indicator_series(_ohlcv(n))
    market = compute_indicator_series(_ohlcv(market_n, symbol="MARKET", seed_close=1000.0))
    return add_alpha_features(series, market)


def test_all_five_feature_columns_are_present():
    augmented = _augmented()
    for col in FEATURE_COLUMNS:
        assert col in augmented.columns


def test_relative_strength_is_nan_when_no_market_series_given():
    series = compute_indicator_series(_ohlcv(100))
    augmented = add_alpha_features(series, None)
    assert augmented["relative_strength_20"].isna().all()


@pytest.mark.parametrize("column", FEATURE_COLUMNS)
def test_feature_is_causal_by_truncated_history_equivalence(column):
    """A feature's value at row i, recomputed from data truncated to rows
    [0, i], must equal its value in the full-series row i — no feature may
    depend on a bar that hadn't happened yet."""
    n = 260
    full_symbol = compute_indicator_series(_ohlcv(n))
    full_market = compute_indicator_series(_ohlcv(n, symbol="MARKET", seed_close=1000.0))
    full_augmented = add_alpha_features(full_symbol, full_market)

    check_index = 240
    truncated_symbol = compute_indicator_series(_ohlcv(n)).iloc[: check_index + 1]
    truncated_market = compute_indicator_series(_ohlcv(n, symbol="MARKET", seed_close=1000.0)).iloc[: check_index + 1]
    truncated_augmented = add_alpha_features(truncated_symbol, truncated_market)

    full_value = full_augmented.iloc[check_index][column]
    truncated_value = truncated_augmented.iloc[-1][column]
    if pd.isna(full_value) and pd.isna(truncated_value):
        return
    assert full_value == truncated_value, f"{column} at row {check_index} depends on future data"


@pytest.mark.parametrize("column", FEATURE_COLUMNS)
def test_feature_value_at_t_is_unaffected_by_mutating_rows_after_t(column):
    """Same control-case structure as test_backtest_lookahead.py: corrupt
    every row strictly AFTER bar T (both the symbol's own future bars and
    the market index's future bars) and confirm the feature value AT T is
    untouched."""
    augmented = _augmented()
    target_index = 220

    mutated_symbol = compute_indicator_series(_ohlcv(260))
    mutated_market = compute_indicator_series(_ohlcv(260, symbol="MARKET", seed_close=1000.0))
    future_rows = mutated_symbol.index[target_index + 1 :]
    for col in ("close", "atr_14", "volume", "volume_ratio"):
        mutated_symbol.loc[future_rows, col] = mutated_symbol.loc[future_rows, col] * 0 + 999999.0
    mutated_market.loc[mutated_market.index[target_index + 1 :], "close"] = 1.0

    mutated_augmented = add_alpha_features(mutated_symbol, mutated_market)

    original_value = augmented.iloc[target_index][column]
    mutated_value = mutated_augmented.iloc[target_index][column]
    if pd.isna(original_value) and pd.isna(mutated_value):
        return
    assert original_value == mutated_value, f"{column} at bar T changed after mutating only future bars"


def test_forward_return_targets_are_labels_and_do_look_ahead_by_design():
    """Control case proving the harness can detect a real forward-looking
    dependency at all: fwd_return_1 at row i MUST change if close[i+1]
    changes — otherwise the causality tests above would be vacuous."""
    series = compute_indicator_series(_ohlcv(50))
    augmented = add_alpha_features(series, None)
    with_targets = add_forward_return_targets(augmented)

    target_index = 10
    original = with_targets.iloc[target_index]["fwd_return_1"]

    mutated = augmented.copy()
    mutated.iloc[target_index + 1, mutated.columns.get_loc("close")] = 99999.0
    mutated_with_targets = add_forward_return_targets(mutated)
    changed = mutated_with_targets.iloc[target_index]["fwd_return_1"]

    assert original != changed  # the label DOES depend on the future -- that's its job


def test_adding_forward_return_targets_never_changes_any_feature_column():
    """add_forward_return_targets only ADDS columns -- it must never alter
    an existing feature value (features and labels must stay structurally
    separated, per the module's own documented distinction)."""
    series = compute_indicator_series(_ohlcv(120))
    augmented = add_alpha_features(series, None)
    with_targets = add_forward_return_targets(augmented)

    for col in FEATURE_COLUMNS:
        pd.testing.assert_series_equal(augmented[col], with_targets[col], check_names=False)
