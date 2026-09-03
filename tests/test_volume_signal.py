"""Phase 11: permanent causality/leakage tests for the volume-signal
confirmation study, mirroring the style of test_regime_filters.py and
test_alpha_features.py. Also locks in each candidate's directional logic
against the frozen Phase 10 thresholds/values.
"""
import pandas as pd
import pytest

from market.indicators import compute_indicator_series
from market.data_provider import OHLCV
from quant_research.volume_signal import (
    CANDIDATES,
    VolumeSignalStrategy,
    dev_fit_volume_thresholds,
    make_volume_predicate,
)
from strategy.regime_filters import FilteredStrategy
from strategy.baseline import TrendMomentumBaseline


def _ohlcv(n, seed_close=100.0, volume_pattern=None):
    bars = []
    for i in range(n):
        volume = volume_pattern(i) if volume_pattern else 1_000_000 + (i % 11) * 15_000
        bars.append({
            "Open": seed_close + i * 0.3, "High": seed_close + i * 0.3 + 1.2,
            "Low": seed_close + i * 0.3 - 1.2, "Close": seed_close + i * 0.3 + (0.6 if i % 4 == 0 else -0.3),
            "Volume": volume,
        })
    frame = pd.DataFrame(bars, index=pd.date_range("2024-01-01", periods=n, freq="D"))
    return OHLCV.from_dataframe(symbol="TEST", interval="1d", frame=frame)


def _series(n=260, volume_pattern=None):
    return compute_indicator_series(_ohlcv(n, volume_pattern=volume_pattern))


# --- directional/threshold unit tests -----------------------------------------


@pytest.mark.parametrize(
    "name,volume_ratio,p20,p80,expected",
    [
        ("A_high_volume", 2.5, 0.8, 2.0, True),
        ("A_high_volume", 1.5, 0.8, 2.0, False),
        ("A_high_volume", 2.0, 0.8, 2.0, False),  # boundary is strict >
        ("B_low_volume", 0.5, 0.8, 2.0, True),
        ("B_low_volume", 1.0, 0.8, 2.0, False),
        ("B_low_volume", 0.8, 0.8, 2.0, False),  # boundary is strict <
        ("C_extreme_volume", 2.5, 0.8, 2.0, True),
        ("C_extreme_volume", 0.5, 0.8, 2.0, True),
        ("C_extreme_volume", 1.0, 0.8, 2.0, False),
    ],
)
def test_candidate_direction_matches_frozen_definition(name, volume_ratio, p20, p80, expected):
    assert CANDIDATES[name](volume_ratio, p20, p80) is expected


def test_dev_fit_thresholds_are_fit_only_on_the_given_series():
    dev_values = pd.Series([1.0] * 40 + [2.0] * 40 + [3.0] * 20)
    thresholds = dev_fit_volume_thresholds(dev_values)
    assert thresholds is not None
    p20, p80 = thresholds
    assert p20 < p80


def test_dev_fit_thresholds_returns_none_for_too_small_a_sample():
    assert dev_fit_volume_thresholds(pd.Series([1.0, 2.0, 3.0])) is None


# --- causality --------------------------------------------------------------


def test_volume_signal_strategy_ignores_future_bars():
    series = _series()
    p20, p80 = dev_fit_volume_thresholds(series["volume_ratio"].iloc[:150])
    strategy = VolumeSignalStrategy("A_high_volume", p20, p80)
    target_index = 200

    signal_before = strategy.generate_signal(series, target_index, "TEST")

    mutated = series.copy()
    future_rows = mutated.index[target_index + 1 :]
    mutated.loc[future_rows, "volume_ratio"] = 999.0
    mutated.loc[future_rows, "atr_14"] = 999.0
    mutated.loc[future_rows, "close"] = 1.0

    signal_after = strategy.generate_signal(mutated, target_index, "TEST")

    if signal_before is None:
        assert signal_after is None
    else:
        assert signal_after is not None
        assert signal_before.model_dump() == signal_after.model_dump()


def test_volume_signal_strategy_causal_by_truncated_history_equivalence():
    n = 260
    full_series = _series(n)
    p20, p80 = dev_fit_volume_thresholds(full_series["volume_ratio"].iloc[:150])
    strategy = VolumeSignalStrategy("A_high_volume", p20, p80)

    check_index = 240
    truncated_series = compute_indicator_series(_ohlcv(n)).iloc[: check_index + 1]

    full_signal = strategy.generate_signal(full_series, check_index, "TEST")
    truncated_signal = strategy.generate_signal(truncated_series, len(truncated_series) - 1, "TEST")

    if full_signal is None:
        assert truncated_signal is None
    else:
        assert truncated_signal is not None
        assert full_signal.model_dump() == truncated_signal.model_dump()


@pytest.mark.parametrize("candidate_name", list(CANDIDATES))
def test_filtered_strategy_via_volume_predicate_only_suppresses(candidate_name):
    """Incremental-value path: TrendMomentumBaseline gated by a volume
    predicate must obey the same suppress-only guarantee Phase 9 already
    proved for FilteredStrategy in general — re-verified here specifically
    for a volume-based predicate."""
    series = _series(n=260, volume_pattern=lambda i: 1_000_000 * (1 + (i % 13) * 0.3))
    p20, p80 = dev_fit_volume_thresholds(series["volume_ratio"].iloc[:150])
    predicate = make_volume_predicate(candidate_name, p20, p80)

    inner = TrendMomentumBaseline()
    filtered = FilteredStrategy(inner=inner, filter_name=f"volume_{candidate_name}", predicate=predicate)

    for i in range(len(series)):
        inner_signal = inner.generate_signal(series, i, "TEST")
        filtered_signal = filtered.generate_signal(series, i, "TEST")
        if inner_signal is None:
            assert filtered_signal is None
        if filtered_signal is not None:
            assert filtered_signal.model_dump() == inner_signal.model_dump()


def test_volume_signal_strategy_never_fires_without_valid_atr():
    series = _series()
    mutated = series.copy()
    mutated["atr_14"] = 0.0  # degenerate ATR everywhere
    p20, p80 = dev_fit_volume_thresholds(series["volume_ratio"].iloc[:150])
    strategy = VolumeSignalStrategy("C_extreme_volume", p20, p80)

    for i in range(len(mutated)):
        assert strategy.generate_signal(mutated, i, "TEST") is None
