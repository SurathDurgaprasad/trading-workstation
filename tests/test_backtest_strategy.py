import math

from strategy.baseline import STOP_ATR_MULTIPLIER, TARGET_RISK_REWARD, TrendMomentumBaseline
from strategy.signal import ReasonCode, Side
from tests.conftest import make_bar, make_indicator_series


def _series_with_last(**overrides):
    bars = [make_bar() for _ in range(3)] + [make_bar(**overrides)]
    return make_indicator_series(bars)


def test_valid_long_setup_emits_signal_with_correct_math():
    series = _series_with_last(close=100.0, atr_14=2.0)
    strategy = TrendMomentumBaseline()

    signal = strategy.generate_signal(series, len(series) - 1, "TEST")

    assert signal is not None
    assert signal.side == Side.LONG
    assert signal.strategy_name == "trend_momentum_baseline"
    assert set(signal.reason_codes) == {
        ReasonCode.TREND_CONFIRMED,
        ReasonCode.MOMENTUM_CONFIRMED,
        ReasonCode.VOLUME_CONFIRMED,
    }

    expected_stop_distance = 2.0 * STOP_ATR_MULTIPLIER
    assert math.isclose(signal.stop_price, 100.0 - expected_stop_distance)
    assert math.isclose(signal.target_price, 100.0 + expected_stop_distance * TARGET_RISK_REWARD)
    assert signal.risk_reward == TARGET_RISK_REWARD


def test_no_setup_when_no_condition_holds():
    series = _series_with_last(sma_20=80.0, sma_50=90.0, rsi_14=40.0, macd=-1.0, volume_trend="decreasing")
    strategy = TrendMomentumBaseline()

    assert strategy.generate_signal(series, len(series) - 1, "TEST") is None


def test_conflicting_indicators_trend_up_momentum_down():
    # Trend confirmed (sma20 > sma50), but momentum explicitly contradicts it.
    series = _series_with_last(sma_20=95.0, sma_50=90.0, rsi_14=30.0, macd=-1.0, macd_signal=0.5)
    strategy = TrendMomentumBaseline()

    assert strategy.generate_signal(series, len(series) - 1, "TEST") is None


def test_volume_not_supportive_blocks_signal_even_if_trend_and_momentum_agree():
    series = _series_with_last(volume_trend="neutral")
    strategy = TrendMomentumBaseline()

    assert strategy.generate_signal(series, len(series) - 1, "TEST") is None

    series_decreasing = _series_with_last(volume_trend="decreasing")
    assert strategy.generate_signal(series_decreasing, len(series_decreasing) - 1, "TEST") is None


def test_insufficient_history_returns_none():
    import pandas as pd

    series = _series_with_last(sma_50=float("nan"))
    strategy = TrendMomentumBaseline()

    assert strategy.generate_signal(series, len(series) - 1, "TEST") is None


def test_missing_atr_returns_none():
    series = _series_with_last(atr_14=float("nan"))
    strategy = TrendMomentumBaseline()

    assert strategy.generate_signal(series, len(series) - 1, "TEST") is None


def test_missing_volume_information_returns_none():
    series = _series_with_last(volume_trend=None)
    strategy = TrendMomentumBaseline()

    assert strategy.generate_signal(series, len(series) - 1, "TEST") is None


def test_zero_atr_returns_none_rather_than_a_zero_width_stop():
    series = _series_with_last(atr_14=0.0)
    strategy = TrendMomentumBaseline()

    assert strategy.generate_signal(series, len(series) - 1, "TEST") is None
