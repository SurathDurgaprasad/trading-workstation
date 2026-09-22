"""Adversarial red-team check (read-only audit companion): direct proof, at
the raw indicator-function level (not via compute_indicator_series or the
strategy, which tests/test_backtest_lookahead.py already covers), that
mutating a future row's INPUT data cannot change an indicator's value at an
earlier bar t.

tests/test_backtest_lookahead.py already proves this for
compute_indicator_series' output columns and for TrendMomentumBaseline's
signal. This file targets the three indicator functions the strategy most
directly depends on for its entry decision (market/indicators.py):
  - compute_sma      (trend leg: sma_20 > sma_50)
  - compute_rsi       (momentum leg: rsi_14 > 50)
  - compute_macd      (momentum leg: macd > macd_signal)

Method: build a close/high/low series, compute the indicator, record its
value at index t, then mutate every row AFTER t (large, adversarial values:
huge spikes, zeros, negative deltas) and recompute. If the indicator's
`.rolling()`/`.ewm()` construction is truly causal, the value at t must be
bit-for-bit identical before and after — the mutation is, by construction,
invisible to any computation that only reads rows <= t.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from market.indicators import ATR_PERIOD, RSI_PERIOD, compute_atr, compute_macd, compute_rsi, compute_sma


def _future_mutations(series: pd.Series, target_index: int) -> list[pd.Series]:
    """A handful of adversarial ways to corrupt every row strictly after
    target_index -- large spikes, a crash to near-zero, and NaN/inf-adjacent
    extremes -- so the test isn't just checking one lucky mutation shape."""
    mutations = []

    spiked = series.copy()
    spiked.iloc[target_index + 1 :] = 1_000_000.0
    mutations.append(spiked)

    crashed = series.copy()
    crashed.iloc[target_index + 1 :] = 0.0001
    mutations.append(crashed)

    reversed_tail = series.copy()
    tail = reversed_tail.iloc[target_index + 1 :].to_numpy()[::-1]
    reversed_tail.iloc[target_index + 1 :] = tail
    mutations.append(reversed_tail)

    return mutations


def test_compute_sma_at_t_is_unchanged_by_mutating_future_rows():
    close = pd.Series([100.0 + i * 0.7 + (3.0 if i % 7 == 0 else 0.0) for i in range(40)])
    target_index = 25
    period = 20

    original_value = compute_sma(close, period).iloc[target_index]
    assert not pd.isna(original_value)  # sanity: warmup already satisfied at t

    for mutated_close in _future_mutations(close, target_index):
        mutated_value = compute_sma(mutated_close, period).iloc[target_index]
        assert mutated_value == original_value, (
            "compute_sma(t) changed after mutating rows > t -- lookahead bug"
        )


def test_compute_rsi_at_t_is_unchanged_by_mutating_future_rows():
    close = pd.Series([100.0 + np.sin(i / 3.0) * 5.0 + i * 0.1 for i in range(40)])
    target_index = 30
    assert target_index > RSI_PERIOD  # past warmup

    original_value = compute_rsi(close, RSI_PERIOD).iloc[target_index]
    assert not pd.isna(original_value)

    for mutated_close in _future_mutations(close, target_index):
        mutated_value = compute_rsi(mutated_close, RSI_PERIOD).iloc[target_index]
        assert mutated_value == original_value, (
            "compute_rsi(t) changed after mutating rows > t -- lookahead bug"
        )


def test_compute_macd_at_t_is_unchanged_by_mutating_future_rows():
    close = pd.Series([100.0 + np.cos(i / 4.0) * 4.0 + i * 0.15 for i in range(50)])
    target_index = 35

    original_frame = compute_macd(close)
    original_macd = original_frame["macd"].iloc[target_index]
    original_signal = original_frame["signal"].iloc[target_index]
    assert not pd.isna(original_macd) and not pd.isna(original_signal)

    for mutated_close in _future_mutations(close, target_index):
        mutated_frame = compute_macd(mutated_close)
        assert mutated_frame["macd"].iloc[target_index] == original_macd, (
            "compute_macd(t)['macd'] changed after mutating rows > t -- lookahead bug"
        )
        assert mutated_frame["signal"].iloc[target_index] == original_signal, (
            "compute_macd(t)['signal'] changed after mutating rows > t -- lookahead bug"
        )


def test_compute_atr_at_t_is_unchanged_by_mutating_future_rows():
    """ATR sizes the strategy's stop/target (strategy/baseline.py), so a
    lookahead leak here would silently corrupt position sizing even if the
    entry-condition indicators (SMA/RSI/MACD) above are clean."""
    close = pd.Series([100.0 + i * 0.5 for i in range(40)])
    high = close * 1.01 + 0.05
    low = close * 0.99
    target_index = 25

    original_value = compute_atr(high, low, close, ATR_PERIOD).iloc[target_index]
    assert not pd.isna(original_value)

    mutated_high, mutated_low, mutated_close = high.copy(), low.copy(), close.copy()
    future = mutated_close.index[target_index + 1 :]
    mutated_close.loc[future] = 1_000_000.0
    mutated_high.loc[future] = 2_000_000.0
    mutated_low.loc[future] = 1.0

    mutated_value = compute_atr(mutated_high, mutated_low, mutated_close, ATR_PERIOD).iloc[target_index]
    assert mutated_value == original_value, (
        "compute_atr(t) changed after mutating rows > t -- lookahead bug"
    )
