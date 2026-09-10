"""H_BREADTH_001: tests for quant_research/market_breadth.py --
compute_universe_breadth_series, the one new piece of production code
this hypothesis needs (a pure cross-sectional aggregation over each
SymbolDataset's own already-causal trend_regime column).
"""
import pandas as pd

from quant_research.market_breadth import compute_universe_breadth_series
from quant_research.market_behavior import SymbolDataset


def _dataset(symbol: str, regimes: list[str]) -> SymbolDataset:
    dates = pd.date_range("2024-01-01", periods=len(regimes), freq="D")
    frame = pd.DataFrame({"trend_regime": regimes}, index=dates)
    return SymbolDataset(symbol=symbol, market="NSE", raw_market="NSE", frame=frame, development_end=None, validation_end=None)


def test_breadth_is_fraction_trending_up_among_valid_symbols():
    datasets = {
        "A": _dataset("A", ["TRENDING_UP"]),
        "B": _dataset("B", ["TRENDING_UP"]),
        "C": _dataset("C", ["TRENDING_DOWN"]),
        "D": _dataset("D", ["SIDEWAYS"]),
    }
    breadth = compute_universe_breadth_series(datasets)
    assert breadth.iloc[0] == 0.5  # 2 of 4 TRENDING_UP


def test_breadth_excludes_unknown_from_denominator():
    datasets = {
        "A": _dataset("A", ["TRENDING_UP"]),
        "B": _dataset("B", ["UNKNOWN"]),
        "C": _dataset("C", ["UNKNOWN"]),
    }
    breadth = compute_universe_breadth_series(datasets)
    # 1 TRENDING_UP out of 1 VALID (UNKNOWN excluded from both numerator and denominator)
    assert breadth.iloc[0] == 1.0


def test_breadth_is_nan_when_every_symbol_unknown_that_date():
    datasets = {
        "A": _dataset("A", ["UNKNOWN"]),
        "B": _dataset("B", ["UNKNOWN"]),
    }
    breadth = compute_universe_breadth_series(datasets)
    assert pd.isna(breadth.iloc[0])


def test_breadth_zero_when_no_symbol_trending_up():
    datasets = {
        "A": _dataset("A", ["TRENDING_DOWN"]),
        "B": _dataset("B", ["SIDEWAYS"]),
    }
    breadth = compute_universe_breadth_series(datasets)
    assert breadth.iloc[0] == 0.0


def test_breadth_one_value_per_calendar_date_and_causal_per_date():
    datasets = {
        "A": _dataset("A", ["TRENDING_UP", "TRENDING_DOWN", "TRENDING_UP"]),
        "B": _dataset("B", ["TRENDING_UP", "TRENDING_UP", "TRENDING_DOWN"]),
    }
    breadth = compute_universe_breadth_series(datasets)
    assert len(breadth) == 3
    assert breadth.iloc[0] == 1.0  # both TRENDING_UP
    assert breadth.iloc[1] == 0.5  # one of two
    assert breadth.iloc[2] == 0.5  # one of two -- confirms each date computed independently, not smoothed/carried over


def test_breadth_handles_misaligned_calendars_without_fabricating_values():
    dates_a = pd.date_range("2024-01-01", periods=2, freq="D")
    dates_b = pd.date_range("2024-01-02", periods=2, freq="D")  # starts one day later
    frame_a = pd.DataFrame({"trend_regime": ["TRENDING_UP", "TRENDING_UP"]}, index=dates_a)
    frame_b = pd.DataFrame({"trend_regime": ["TRENDING_DOWN", "TRENDING_DOWN"]}, index=dates_b)
    datasets = {
        "A": SymbolDataset(symbol="A", market="NSE", raw_market="NSE", frame=frame_a, development_end=None, validation_end=None),
        "B": SymbolDataset(symbol="B", market="NSE", raw_market="NSE", frame=frame_b, development_end=None, validation_end=None),
    }
    breadth = compute_universe_breadth_series(datasets)
    # 2024-01-01: only A has data (TRENDING_UP) -> 1/1 = 1.0
    assert breadth.loc["2024-01-01"] == 1.0
    # 2024-01-02: both A (TRENDING_UP) and B (TRENDING_DOWN) -> 1/2 = 0.5
    assert breadth.loc["2024-01-02"] == 0.5
    # 2024-01-03: only B has data (TRENDING_DOWN) -> 0/1 = 0.0
    assert breadth.loc["2024-01-03"] == 0.0
