"""EDGE DISCOVERY mission: tests for quant_research/cross_sectional.py
-- the minimal cross-sectional ranking engine H_RELSTRENGTH_001's own
module docstring flagged as a genuinely missing capability.
"""
from datetime import datetime, timedelta

import pandas as pd
import pytest

from quant_research.cross_sectional import (
    add_lookback_return_columns,
    attach_relative_score_column,
    rank_cross_sectionally,
    shared_period_boundaries,
)
from quant_research.market_behavior import SymbolDataset


def _dataset(symbol: str, closes: list[float], development_end=None, validation_end=None) -> SymbolDataset:
    dates = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    frame = pd.DataFrame({"close": closes}, index=dates)
    return SymbolDataset(
        symbol=symbol, market="NSE", raw_market="NSE", frame=frame,
        development_end=development_end or dates[len(dates) // 2],
        validation_end=validation_end or dates[-1],
    )


# --- add_lookback_return_columns --------------------------------------------------


def test_add_lookback_return_columns_is_causal_and_correct():
    dataset = _dataset("A", [100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    add_lookback_return_columns(dataset, lookbacks=(2,))
    assert "trailing_return_2" in dataset.frame.columns
    # bar index 2 (close=102) vs bar index 0 (close=100): (102/100 - 1)
    assert dataset.frame["trailing_return_2"].iloc[2] == pytest.approx(102.0 / 100.0 - 1.0)
    # first 2 bars have no 2-bar-ago reference -- must be NaN, never fabricated as 0
    assert pd.isna(dataset.frame["trailing_return_2"].iloc[0])
    assert pd.isna(dataset.frame["trailing_return_2"].iloc[1])


def test_add_lookback_return_columns_adds_every_requested_lookback():
    dataset = _dataset("A", [100.0] * 70)
    add_lookback_return_columns(dataset, lookbacks=(5, 20, 60))
    for lb in (5, 20, 60):
        assert f"trailing_return_{lb}" in dataset.frame.columns


# --- shared_period_boundaries --------------------------------------------------


def test_shared_period_boundaries_uses_first_dataset():
    dev_end = pd.Timestamp("2024-01-03")
    val_end = pd.Timestamp("2024-01-05")
    datasets = {"A": _dataset("A", [1, 2, 3, 4, 5, 6], development_end=dev_end, validation_end=val_end)}
    result_dev, result_val = shared_period_boundaries(datasets)
    assert result_dev == dev_end
    assert result_val == val_end


def test_shared_period_boundaries_raises_when_reference_has_no_split():
    dataset = _dataset("A", [1, 2, 3])
    dataset.development_end = None
    with pytest.raises(ValueError, match="no development/validation split"):
        shared_period_boundaries({"A": dataset})


# --- attach_relative_score_column --------------------------------------------------


def test_attach_relative_score_column_subtracts_aligned_external_series():
    dataset = _dataset("A", [100.0, 110.0, 121.0])
    dataset.frame["raw_score"] = [0.10, 0.20, 0.30]
    external = pd.Series([0.02, 0.03, 0.04], index=dataset.frame.index)
    attach_relative_score_column(
        {"A": dataset}, raw_score_column="raw_score", external_series_by_key={"BENCHMARK": external},
        key_for_symbol=lambda symbol: "BENCHMARK", output_column="relative_score",
    )
    assert dataset.frame["relative_score"].tolist() == pytest.approx([0.08, 0.17, 0.26])


def test_attach_relative_score_column_forward_fills_causally():
    """The external series has fewer dates than the symbol's own frame
    (e.g. it starts later, or is sparser) -- values must be forward-
    filled from the LAST available external value, never interpolated
    from a future one."""
    dataset = _dataset("A", [100.0, 100.0, 100.0, 100.0])
    dataset.frame["raw_score"] = [0.10, 0.10, 0.10, 0.10]
    sparse_dates = [dataset.frame.index[0], dataset.frame.index[2]]
    external = pd.Series([0.01, 0.05], index=sparse_dates)
    attach_relative_score_column(
        {"A": dataset}, raw_score_column="raw_score", external_series_by_key={"BENCHMARK": external},
        key_for_symbol=lambda symbol: "BENCHMARK", output_column="relative_score",
    )
    # bar 1 has no external value yet at that exact date under reindex -- forward-filled from bar 0's 0.01
    assert dataset.frame["relative_score"].tolist() == pytest.approx([0.09, 0.09, 0.05, 0.05])


def test_attach_relative_score_column_uses_per_symbol_key():
    """key_for_symbol lets different symbols draw from DIFFERENT
    external series (e.g. each stock's own sector index) rather than
    one shared benchmark -- the sector-relative use case."""
    dataset_a = _dataset("A", [100.0, 100.0])
    dataset_a.frame["raw_score"] = [0.10, 0.10]
    dataset_b = _dataset("B", [100.0, 100.0])
    dataset_b.frame["raw_score"] = [0.10, 0.10]
    dates = dataset_a.frame.index
    series_x = pd.Series([0.01, 0.01], index=dates)
    series_y = pd.Series([0.05, 0.05], index=dates)
    attach_relative_score_column(
        {"A": dataset_a, "B": dataset_b}, raw_score_column="raw_score",
        external_series_by_key={"SECTOR_X": series_x, "SECTOR_Y": series_y},
        key_for_symbol=lambda symbol: {"A": "SECTOR_X", "B": "SECTOR_Y"}[symbol],
        output_column="relative_score",
    )
    assert dataset_a.frame["relative_score"].iloc[0] == pytest.approx(0.09)
    assert dataset_b.frame["relative_score"].iloc[0] == pytest.approx(0.05)


def test_attach_relative_score_column_never_falls_back_to_raw_score_for_an_unmapped_symbol():
    """A symbol whose key_for_symbol has no matching external series
    must get NaN throughout -- never silently reuse the raw score,
    which would misrepresent an unmeasured relative score as computed."""
    dataset = _dataset("A", [100.0, 100.0])
    dataset.frame["raw_score"] = [0.10, 0.10]
    attach_relative_score_column(
        {"A": dataset}, raw_score_column="raw_score", external_series_by_key={},
        key_for_symbol=lambda symbol: None, output_column="relative_score",
    )
    assert dataset.frame["relative_score"].isna().all()


# --- rank_cross_sectionally --------------------------------------------------


def _dataset_with_score_and_forward(symbol: str, dates, scores, forward_returns, dev_end, val_end) -> SymbolDataset:
    frame = pd.DataFrame({"close": [100.0] * len(dates), "score": scores, "fwd_return_1": forward_returns}, index=dates)
    return SymbolDataset(symbol=symbol, market="NSE", raw_market="NSE", frame=frame, development_end=dev_end, validation_end=val_end)


def test_rank_cross_sectionally_buckets_by_score_correctly():
    """4 symbols, 1 date, 2 buckets -- top-2 scorers get bucket Q1, bottom-2 get Q2.
    Forward returns are set to a fixed, distinguishing value per symbol so the test can
    verify each symbol's return landed in the RIGHT bucket, not just that buckets exist."""
    dates = pd.date_range("2024-06-01", periods=1)
    dev_end, val_end = pd.Timestamp("2024-12-31"), pd.Timestamp("2025-12-31")
    datasets = {
        "HIGH1": _dataset_with_score_and_forward("HIGH1", dates, [0.10], [0.05], dev_end, val_end),
        "HIGH2": _dataset_with_score_and_forward("HIGH2", dates, [0.08], [0.04], dev_end, val_end),
        "LOW1": _dataset_with_score_and_forward("LOW1", dates, [0.02], [-0.03], dev_end, val_end),
        "LOW2": _dataset_with_score_and_forward("LOW2", dates, [0.01], [-0.02], dev_end, val_end),
    }
    result = rank_cross_sectionally(datasets, score_column="score", horizons=(1,), n_buckets=2, min_symbols_per_date=4)

    assert set(result.keys()) == {"Q1", "Q2"}
    q1_returns = sorted([result["Q1"][1].mean_return])  # mean of {0.05, 0.04}
    assert result["Q1"][1].sample_size == 2
    assert result["Q1"][1].mean_return == pytest.approx((0.05 + 0.04) / 2)
    assert result["Q2"][1].sample_size == 2
    assert result["Q2"][1].mean_return == pytest.approx((-0.03 + -0.02) / 2)


def test_rank_cross_sectionally_skips_dates_below_min_symbols():
    dates = pd.date_range("2024-06-01", periods=1)
    dev_end, val_end = pd.Timestamp("2024-12-31"), pd.Timestamp("2025-12-31")
    datasets = {
        "A": _dataset_with_score_and_forward("A", dates, [0.1], [0.05], dev_end, val_end),
        "B": _dataset_with_score_and_forward("B", dates, [0.2], [0.05], dev_end, val_end),
    }
    result = rank_cross_sectionally(datasets, score_column="score", horizons=(1,), n_buckets=2, min_symbols_per_date=10)
    assert result["Q1"][1].sample_size == 0
    assert result["Q2"][1].sample_size == 0


def test_rank_cross_sectionally_never_fabricates_a_score_for_missing_data():
    """A symbol with a NaN score on a given date must be excluded from that
    date's ranking entirely, never treated as a neutral/zero score."""
    dates = pd.date_range("2024-06-01", periods=1)
    dev_end, val_end = pd.Timestamp("2024-12-31"), pd.Timestamp("2025-12-31")
    datasets = {
        "A": _dataset_with_score_and_forward("A", dates, [0.1], [0.05], dev_end, val_end),
        "B": _dataset_with_score_and_forward("B", dates, [float("nan")], [0.05], dev_end, val_end),
        "C": _dataset_with_score_and_forward("C", dates, [0.2], [0.03], dev_end, val_end),
    }
    result = rank_cross_sectionally(datasets, score_column="score", horizons=(1,), n_buckets=2, min_symbols_per_date=2)
    total_sample = result["Q1"][1].sample_size + result["Q2"][1].sample_size
    assert total_sample == 2  # only A and C, never B


def test_rank_cross_sectionally_respects_period_filter():
    dates = pd.date_range("2024-01-01", periods=3, freq="365D")  # spans dev, val, oos
    dev_end, val_end = dates[0], dates[1]
    datasets = {
        "A": _dataset_with_score_and_forward("A", dates, [0.1, 0.2, 0.3], [0.01, 0.02, 0.03], dev_end, val_end),
        "B": _dataset_with_score_and_forward("B", dates, [0.05, 0.15, 0.25], [0.05, 0.06, 0.07], dev_end, val_end),
    }
    dev_result = rank_cross_sectionally(datasets, score_column="score", horizons=(1,), n_buckets=2, period="development", min_symbols_per_date=2)
    oos_result = rank_cross_sectionally(datasets, score_column="score", horizons=(1,), n_buckets=2, period="out_of_sample", min_symbols_per_date=2)
    assert dev_result["Q1"][1].sample_size + dev_result["Q2"][1].sample_size == 2
    assert oos_result["Q1"][1].sample_size + oos_result["Q2"][1].sample_size == 2
    # development bucket returns must come from the FIRST date's forward returns only
    assert {dev_result["Q1"][1].mean_return, dev_result["Q2"][1].mean_return} <= {0.01, 0.05}
