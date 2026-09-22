"""Property-based tests for market/indicators.py -- autonomous hardening
cycle 10 (escalation ladder level 4, mission section 11.A). Unlike
risk/engine.py (cycle 7) and the ml_research pipeline (cycle 9, audited
with no defect found), this module had thin coverage (9 example-based
tests in tests/test_market_data.py, no dedicated indicator test file,
no property tests) before this cycle -- a genuine, previously
unexercised attack surface for the exact categories this campaign's
own mission calls out: empty/one-bar/short series, constant series,
monotonic series, extreme values, zero-volume series, and NaN/Inf
propagation.

Every property here is derived from the function's own actual,
observable contract (read from market/indicators.py directly), never
an invented/undocumented invariant:
  - compute_sma: a simple moving average must lie within [min, max] of
    its own window -- an arithmetic identity, not an assumption.
  - compute_rsi: bounded in [0, 100] by definition wherever defined
    (market/indicators.py's own docstring/implementation already
    special-cases the all-gains/flat-window edges and explicitly
    replaces +/-Inf with NaN).
  - compute_atr: True Range and its rolling mean are never negative.
  - compute_macd: histogram = macd - signal is an exact algebraic
    identity by construction, not merely typically true.
  - compute_volume_analysis: volume_ratio is a ratio of two
    non-negative quantities (guarded against a zero denominator) --
    never negative when defined.

Deliberately bounded and deterministic (max_examples capped,
derandomize=True), per this project's "no fake coverage / no
meaningless test explosion" discipline.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from hypothesis import HealthCheck, given, settings, strategies as st

from market.data_provider import OHLCV, OHLCVBar
from market.indicators import (
    RSI_PERIOD,
    compute_atr,
    compute_indicators,
    compute_macd,
    compute_rsi,
    compute_sma,
    compute_volume_analysis,
)

_PROPERTY_SETTINGS = settings(max_examples=100, derandomize=True, suppress_health_check=[HealthCheck.too_slow])
"""Red-team investigation (2026-09-22): test_compute_sma_never_raises_
regardless_of_length_vs_period failed intermittently during FULL-SUITE runs
(never in isolation) -- once as a bare failure, once explicitly as
Hypothesis's own `FailedHealthCheck: too_slow`. `derandomize=True` (above,
unchanged) makes the actual generated EXAMPLES fully deterministic across
runs -- the same inputs are tried every time, in the same order -- which
already rules out "a different random input occasionally exposes a real
bug" as the explanation; only Hypothesis's own WALL-CLOCK timing budget for
data GENERATION (not the indicator computation itself) is sensitive to
whatever else is running concurrently in a 2700+-test suite. Confirmed by
running the isolated test 5 consecutive times (all passed, sub-second each)
and by the fact that `too_slow` is a data-generation-speed heuristic, not a
correctness check -- suppressing it here changes nothing about what values
get tested or what compute_sma is expected to return; it only stops
Hypothesis from failing a test because the surrounding test suite made the
MACHINE, not the CODE, slow. market/indicators.py itself was read
line-by-line and found to contain no source of nondeterminism (no dict
ordering dependency, no uninitialized state) that could otherwise explain
this."""

_PRICE = st.floats(min_value=0.01, max_value=1_000_000.0, allow_nan=False, allow_infinity=False)
_VOLUME = st.floats(min_value=0.0, max_value=1_000_000_000.0, allow_nan=False, allow_infinity=False)


def _close_series(values: list[float]) -> pd.Series:
    return pd.Series(values, dtype=float)


# --- compute_sma -------------------------------------------------------------


@_PROPERTY_SETTINGS
@given(closes=st.lists(_PRICE, min_size=0, max_size=60), period=st.integers(min_value=1, max_value=20))
def test_compute_sma_never_raises_regardless_of_length_vs_period(closes, period):
    """No unexpected exception -- including the degenerate cases (empty
    series, a period longer than the series) that a naive rolling-window
    implementation might mishandle."""
    compute_sma(_close_series(closes), period)  # must not raise


@_PROPERTY_SETTINGS
@given(closes=st.lists(_PRICE, min_size=1, max_size=60), period=st.integers(min_value=1, max_value=10))
def test_compute_sma_stays_within_its_own_window_bounds(closes, period):
    """A moving AVERAGE can never fall outside the min/max of the values
    it averages -- an arithmetic identity, checked at every valid
    (non-NaN) point in the output."""
    series = _close_series(closes)
    sma = compute_sma(series, period)
    for i in range(len(series)):
        value = sma.iloc[i]
        if pd.isna(value):
            continue
        window = series.iloc[max(0, i - period + 1) : i + 1]
        assert window.min() - 1e-6 <= value <= window.max() + 1e-6


# --- compute_rsi ---------------------------------------------------------------


@_PROPERTY_SETTINGS
@given(closes=st.lists(_PRICE, min_size=0, max_size=60))
def test_compute_rsi_never_raises(closes):
    compute_rsi(_close_series(closes), period=RSI_PERIOD)  # must not raise


@_PROPERTY_SETTINGS
@given(closes=st.lists(_PRICE, min_size=1, max_size=80))
def test_compute_rsi_is_always_bounded_zero_to_hundred_or_nan(closes):
    """Documented bound (market/indicators.py's own RSI convention):
    RSI in [0, 100] wherever defined -- never a raw ratio that escaped
    the formula's own [0,100] normalization, and never +/-Inf (the
    function's own final `.replace([inf, -inf], nan)` is what this
    property actually proves holds, not merely assumes)."""
    rsi = compute_rsi(_close_series(closes), period=RSI_PERIOD)
    for value in rsi:
        if pd.isna(value):
            continue
        assert math.isfinite(value)
        assert 0.0 <= value <= 100.0


@_PROPERTY_SETTINGS
@given(base=_PRICE, n=st.integers(min_value=RSI_PERIOD + 1, max_value=60))
def test_compute_rsi_is_exactly_100_for_a_strictly_increasing_series(base, n):
    """Named edge case (all gains, zero losses): the function's own
    comment documents 100 as the conventional value here -- not merely
    'close to 100'."""
    closes = _close_series([base + i for i in range(n)])
    rsi = compute_rsi(closes, period=RSI_PERIOD)
    assert rsi.iloc[-1] == 100.0


@_PROPERTY_SETTINGS
@given(base=_PRICE, n=st.integers(min_value=RSI_PERIOD + 1, max_value=60))
def test_compute_rsi_is_exactly_50_for_a_perfectly_constant_series(base, n):
    """Named edge case (a completely flat window -- zero gains AND zero
    losses): the function's own comment documents 50 as the conventional
    value, distinct from the all-gains 100 case above."""
    closes = _close_series([base] * n)
    rsi = compute_rsi(closes, period=RSI_PERIOD)
    assert rsi.iloc[-1] == 50.0


# --- compute_atr ---------------------------------------------------------------


@_PROPERTY_SETTINGS
@given(
    closes=st.lists(_PRICE, min_size=0, max_size=60),
    period=st.integers(min_value=1, max_value=20),
)
def test_compute_atr_never_raises_and_is_never_negative(closes, period):
    """True Range (max of three non-negative differences) and its
    rolling mean can never be negative -- checked directly against
    high/low derived from each close with a small, always-valid spread,
    plus the degenerate empty/short-series cases."""
    close = _close_series(closes)
    high = close * 1.01 + 0.01
    low = close * 0.99
    atr = compute_atr(high, low, close, period=period)
    for value in atr:
        if pd.isna(value):
            continue
        assert math.isfinite(value)
        assert value >= -1e-9  # tiny float slack only


# --- compute_macd ----------------------------------------------------------------


@_PROPERTY_SETTINGS
@given(closes=st.lists(_PRICE, min_size=0, max_size=60))
def test_compute_macd_never_raises(closes):
    compute_macd(_close_series(closes))  # must not raise


@_PROPERTY_SETTINGS
@given(closes=st.lists(_PRICE, min_size=1, max_size=60))
def test_compute_macd_histogram_is_exactly_macd_minus_signal(closes):
    """Algebraic identity by construction (histogram = macd_line -
    signal_line), not merely typically true -- verified at every row,
    not just the latest one the pre-existing example-based test checks."""
    frame = compute_macd(_close_series(closes))
    diff = (frame["macd"] - frame["signal"] - frame["histogram"]).abs()
    assert (diff.fillna(0.0) < 1e-9).all()


@_PROPERTY_SETTINGS
@given(closes=st.lists(_PRICE, min_size=1, max_size=60))
def test_compute_macd_never_produces_inf_for_finite_bounded_input(closes):
    frame = compute_macd(_close_series(closes))
    for col in ("macd", "signal", "histogram"):
        for value in frame[col]:
            if pd.isna(value):
                continue
            assert math.isfinite(value)


# --- compute_volume_analysis -------------------------------------------------


@_PROPERTY_SETTINGS
@given(volumes=st.lists(_VOLUME, min_size=0, max_size=60))
def test_compute_volume_analysis_never_raises(volumes):
    compute_volume_analysis(pd.Series(volumes, dtype=float))  # must not raise


@_PROPERTY_SETTINGS
@given(volumes=st.lists(_VOLUME, min_size=25, max_size=60))
def test_volume_ratio_is_never_negative_when_defined(volumes):
    """Documented bound (mission section 4): volume_ratio >= 0 when
    defined -- a ratio of two non-negative quantities, with the
    zero-denominator case already explicitly handled (0.0, not NaN/Inf)
    in market/indicators.py's own compute_volume_analysis."""
    analysis = compute_volume_analysis(pd.Series(volumes, dtype=float))
    if analysis is not None:
        assert math.isfinite(analysis.volume_ratio)
        assert analysis.volume_ratio >= 0.0


@_PROPERTY_SETTINGS
@given(n=st.integers(min_value=25, max_value=60))
def test_compute_volume_analysis_handles_an_all_zero_volume_series(n):
    """Named edge case (mission: 'zero-volume series') -- must not
    divide by zero into Inf/NaN; the function's own explicit `if
    volume_sma_20 == 0: volume_ratio = 0.0` branch is what this proves."""
    analysis = compute_volume_analysis(pd.Series([0.0] * n))
    assert analysis is not None
    assert analysis.volume_ratio == 0.0
    assert analysis.current_volume == 0.0
    assert analysis.volume_sma_20 == 0.0


# --- compute_indicators (top-level, real OHLCV construction) -----------------


@_PROPERTY_SETTINGS
@given(closes=st.lists(_PRICE, min_size=1, max_size=60))
def test_compute_indicators_never_raises_on_any_nonempty_series_and_stays_bounded(closes):
    """The top-level entry point every live/scanner/backtest path calls.
    Empty OHLCV already raises explicitly (tested elsewhere,
    test_compute_indicators_raises_on_empty_ohlcv) -- this sweeps every
    OTHER length, including ones shorter than any single indicator's own
    warm-up period, and checks the two bounded indicators (rsi_14,
    volume via compute_volume_analysis's own volume_ratio, indirectly
    through TechnicalIndicators.volume) never escape their documented
    ranges when the series is long enough to produce a non-None value."""
    start = datetime(2026, 1, 1)
    bars = [
        OHLCVBar(
            timestamp=start + timedelta(days=i), open=c, high=c * 1.01 + 0.01, low=c * 0.99,
            close=c, volume=1_000_000.0,
        )
        for i, c in enumerate(closes)
    ]
    ohlcv = OHLCV(symbol="PROPTEST", interval="1d", bars=bars)

    indicators = compute_indicators(ohlcv)  # must not raise

    if indicators.rsi_14 is not None:
        assert math.isfinite(indicators.rsi_14)
        assert 0.0 <= indicators.rsi_14 <= 100.0
    if indicators.atr_14 is not None:
        assert math.isfinite(indicators.atr_14)
        assert indicators.atr_14 >= -1e-9
    if indicators.volume is not None:
        assert math.isfinite(indicators.volume.volume_ratio)
        assert indicators.volume.volume_ratio >= 0.0
