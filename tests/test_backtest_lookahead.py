"""Mandatory per Phase 3 spec §6/§20: an explicit, automated proof that a
signal generated at bar N cannot be influenced by bars after N."""

import copy

import pandas as pd

from market.data_provider import OHLCV
from market.indicators import compute_indicator_series
from strategy.baseline import TrendMomentumBaseline
from tests.conftest import make_bar, make_indicator_series


def test_mutating_future_bars_does_not_change_a_past_signal():
    strategy = TrendMomentumBaseline()
    target_index = 5

    original = make_indicator_series([make_bar() for _ in range(12)])
    signal_before = strategy.generate_signal(original, target_index, "TEST")

    mutated = original.copy()
    # Corrupt every bar strictly AFTER target_index in every way a strategy
    # could conceivably (mis)use: flip trend/momentum/volume conditions, and
    # blow up the raw price/volume numbers.
    future_rows = mutated.index[target_index + 1 :]
    mutated.loc[future_rows, "sma_20"] = 1.0
    mutated.loc[future_rows, "sma_50"] = 999.0
    mutated.loc[future_rows, "rsi_14"] = 1.0
    mutated.loc[future_rows, "macd"] = -999.0
    mutated.loc[future_rows, "macd_signal"] = 999.0
    mutated.loc[future_rows, "atr_14"] = 9999.0
    mutated.loc[future_rows, "volume_trend"] = "decreasing"
    mutated.loc[future_rows, "close"] = 0.01
    mutated.loc[future_rows, "open"] = 0.01
    mutated.loc[future_rows, "high"] = 0.02
    mutated.loc[future_rows, "low"] = 0.005
    mutated.loc[future_rows, "volume"] = 1

    signal_after = strategy.generate_signal(mutated, target_index, "TEST")

    assert signal_before is not None  # sanity: the unmutated fixture does qualify
    assert signal_after is not None
    assert signal_before.model_dump() == signal_after.model_dump()


def test_mutating_past_bars_does_change_the_signal_control_case():
    """Companion to the test above: proves the harness can actually detect a
    difference at all (a change to PAST data must be able to change the
    signal) — otherwise the previous test would trivially "pass" even if
    generate_signal ignored its input entirely."""
    strategy = TrendMomentumBaseline()
    target_index = 5

    original = make_indicator_series([make_bar() for _ in range(12)])
    signal_before = strategy.generate_signal(original, target_index, "TEST")

    mutated = original.copy()
    mutated.loc[mutated.index[target_index], "volume_trend"] = "decreasing"  # break the condition AT the signal bar
    signal_after = strategy.generate_signal(mutated, target_index, "TEST")

    assert signal_before is not None
    assert signal_after is None  # changing bar N itself changes the outcome


def test_indicator_series_columns_are_causal_by_construction():
    """A structural check on market.indicators.compute_indicator_series
    itself (not just the strategy): the value at row i, recomputed from a
    frame truncated to rows [0, i], must equal the value in the full frame's
    row i — i.e. no indicator column peeks forward."""
    bars = [
        {
            "Open": 100 + i * 0.3,
            "High": 100 + i * 0.3 + 1,
            "Low": 100 + i * 0.3 - 1,
            "Close": 100 + i * 0.3 + (0.5 if i % 5 == 0 else -0.2),
            "Volume": 1_000_000 + i * 1000,
        }
        for i in range(60)
    ]
    frame = pd.DataFrame(bars, index=pd.date_range("2026-01-01", periods=60, freq="D"))
    ohlcv = OHLCV.from_dataframe(symbol="CAUSAL", interval="1d", frame=frame)

    full_series = compute_indicator_series(ohlcv)

    check_index = 40
    truncated_frame = frame.iloc[: check_index + 1]
    truncated_ohlcv = OHLCV.from_dataframe(symbol="CAUSAL", interval="1d", frame=truncated_frame)
    truncated_series = compute_indicator_series(truncated_ohlcv)

    full_row = full_series.iloc[check_index]
    truncated_row = truncated_series.iloc[-1]

    for column in ("sma_20", "sma_50", "rsi_14", "macd", "macd_signal", "atr_14", "volume_ratio"):
        full_value = full_row[column]
        truncated_value = truncated_row[column]
        if pd.isna(full_value) and pd.isna(truncated_value):
            continue
        assert full_value == truncated_value, f"{column} at row {check_index} depends on future data"
