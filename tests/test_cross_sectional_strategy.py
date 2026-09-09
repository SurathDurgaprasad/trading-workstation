"""H_XSECT_001: tests for quant_research/cross_sectional_strategy.py --
the real, cost-aware, risk-sized backtest wrapper around the
cross-sectional laggard finding."""

import pandas as pd
import pytest

from quant_research.cross_sectional_strategy import (
    BOTTOM_BUCKET_LABEL,
    BUCKET_COLUMN,
    CrossSectionalLaggardStrategy,
)
from strategy.signal import ReasonCode, Side


def _frame(buckets: list, closes: list[float], atrs: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=len(buckets), freq="D")
    return pd.DataFrame({BUCKET_COLUMN: buckets, "close": closes, "atr_14": atrs}, index=dates)


def test_fires_only_on_new_entry_into_bottom_bucket():
    """Bar 0: not Q5 (no signal, also index==0 guard). Bar 1: newly Q5 --
    fires. Bar 2: still Q5 (was Q5 yesterday too) -- must NOT fire again,
    the report's own frozen "newly in the bottom quintile" rule."""
    frame = _frame(
        buckets=["Q3", "Q5", "Q5", "Q2"],
        closes=[100.0, 98.0, 97.0, 99.0],
        atrs=[2.0, 2.0, 2.0, 2.0],
    )
    strategy = CrossSectionalLaggardStrategy()

    assert strategy.generate_signal(frame, 0, "TEST.NS") is None
    signal = strategy.generate_signal(frame, 1, "TEST.NS")
    assert signal is not None
    assert signal.side == Side.LONG
    assert signal.reason_codes == [ReasonCode.CROSS_SECTIONAL_LAGGARD]
    assert strategy.generate_signal(frame, 2, "TEST.NS") is None  # already Q5 yesterday
    assert strategy.generate_signal(frame, 3, "TEST.NS") is None  # not Q5 at all


def test_never_fires_when_bucket_is_nan():
    frame = _frame(buckets=[None, None], closes=[100.0, 99.0], atrs=[2.0, 2.0])
    strategy = CrossSectionalLaggardStrategy()
    assert strategy.generate_signal(frame, 1, "TEST.NS") is None


def test_never_fires_on_a_non_bottom_bucket():
    frame = _frame(buckets=["Q3", "Q1"], closes=[100.0, 101.0], atrs=[2.0, 2.0])
    strategy = CrossSectionalLaggardStrategy()
    assert strategy.generate_signal(frame, 1, "TEST.NS") is None


def test_stop_and_target_derived_from_atr_and_frozen_constants():
    from strategy.baseline import STOP_ATR_MULTIPLIER, TARGET_RISK_REWARD

    frame = _frame(buckets=["Q3", "Q5"], closes=[100.0, 100.0], atrs=[4.0, 4.0])
    strategy = CrossSectionalLaggardStrategy()
    signal = strategy.generate_signal(frame, 1, "TEST.NS")
    assert signal is not None
    expected_stop_distance = 4.0 * STOP_ATR_MULTIPLIER
    assert signal.stop_price == pytest.approx(100.0 - expected_stop_distance)
    assert signal.target_price == pytest.approx(100.0 + expected_stop_distance * TARGET_RISK_REWARD)


def test_never_fires_when_atr_is_zero_or_missing():
    frame = _frame(buckets=["Q3", "Q5"], closes=[100.0, 100.0], atrs=[0.0, 0.0])
    strategy = CrossSectionalLaggardStrategy()
    assert strategy.generate_signal(frame, 1, "TEST.NS") is None


def test_bottom_bucket_label_is_configurable_not_hardcoded_q5():
    """Guards against silently assuming n_buckets=5 always -- a caller
    using terciles (n_buckets=3) must be able to point at 'Q3' as the
    bottom bucket instead."""
    frame = _frame(buckets=["Q1", "Q3"], closes=[100.0, 100.0], atrs=[2.0, 2.0])
    strategy = CrossSectionalLaggardStrategy(bottom_bucket_label="Q3")
    signal = strategy.generate_signal(frame, 1, "TEST.NS")
    assert signal is not None
    assert BOTTOM_BUCKET_LABEL == "Q5"  # the actual default used in the real H_XSECT_001 backtest
