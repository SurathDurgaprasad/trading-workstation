import pytest

from strategy.signal import Side
from strategy.simple_baselines import SimpleMomentumBaseline, SimpleTrendBaseline
from tests.conftest import make_bar, make_indicator_series


# --- SimpleMomentumBaseline ------------------------------------------------------


def test_simple_momentum_fires_when_close_above_sma20():
    series = make_indicator_series([make_bar(close=100.0, sma_20=95.0)])
    strategy = SimpleMomentumBaseline()

    signal = strategy.generate_signal(series, 0, "TEST")

    assert signal is not None
    assert signal.side == Side.LONG
    assert signal.strategy_name == "simple_momentum_baseline"


def test_simple_momentum_does_not_fire_when_close_below_sma20():
    series = make_indicator_series([make_bar(close=90.0, sma_20=95.0)])
    strategy = SimpleMomentumBaseline()

    assert strategy.generate_signal(series, 0, "TEST") is None


def test_simple_momentum_ignores_trend_and_volume_conditions():
    # sma_20 < sma_50 (would fail TrendMomentumBaseline's OWN trend leg)
    # and volume_trend is "decreasing" (would fail its volume leg) -- but
    # SimpleMomentumBaseline only checks close vs sma_20, so it must
    # still fire.
    series = make_indicator_series([make_bar(close=100.0, sma_20=95.0, sma_50=110.0, volume_trend="decreasing")])
    strategy = SimpleMomentumBaseline()

    assert strategy.generate_signal(series, 0, "TEST") is not None


def test_simple_momentum_uses_the_same_atr_stop_target_math_as_baseline():
    series = make_indicator_series([make_bar(close=100.0, sma_20=95.0, atr_14=2.0)])
    strategy = SimpleMomentumBaseline()

    signal = strategy.generate_signal(series, 0, "TEST")

    assert signal is not None
    assert signal.stop_price == pytest.approx(100.0 - 2.0 * 1.5)
    assert signal.target_price == pytest.approx(100.0 + 2.0 * 1.5 * 2.0)


def test_simple_momentum_none_for_non_positive_atr():
    series = make_indicator_series([make_bar(close=100.0, sma_20=95.0, atr_14=0.0)])
    strategy = SimpleMomentumBaseline()

    assert strategy.generate_signal(series, 0, "TEST") is None


def test_simple_momentum_none_for_nan_indicators():
    series = make_indicator_series([make_bar(close=100.0, sma_20=float("nan"))])
    strategy = SimpleMomentumBaseline()

    assert strategy.generate_signal(series, 0, "TEST") is None


# --- SimpleTrendBaseline ---------------------------------------------------------


def test_simple_trend_fires_when_sma20_above_sma50():
    series = make_indicator_series([make_bar(sma_20=95.0, sma_50=90.0)])
    strategy = SimpleTrendBaseline()

    signal = strategy.generate_signal(series, 0, "TEST")

    assert signal is not None
    assert signal.strategy_name == "simple_trend_baseline"


def test_simple_trend_does_not_fire_when_sma20_below_sma50():
    series = make_indicator_series([make_bar(sma_20=90.0, sma_50=95.0)])
    strategy = SimpleTrendBaseline()

    assert strategy.generate_signal(series, 0, "TEST") is None


def test_simple_trend_ignores_momentum_and_volume_conditions():
    # rsi_14 <= 50 and macd < macd_signal (would fail TrendMomentumBaseline's
    # OWN momentum leg) but SimpleTrendBaseline only checks sma_20 vs
    # sma_50, so it must still fire.
    series = make_indicator_series([make_bar(sma_20=95.0, sma_50=90.0, rsi_14=30.0, macd=-1.0, macd_signal=1.0)])
    strategy = SimpleTrendBaseline()

    assert strategy.generate_signal(series, 0, "TEST") is not None


def test_simple_trend_uses_the_same_atr_stop_target_math_as_baseline():
    series = make_indicator_series([make_bar(close=100.0, sma_20=95.0, sma_50=90.0, atr_14=2.0)])
    strategy = SimpleTrendBaseline()

    signal = strategy.generate_signal(series, 0, "TEST")

    assert signal is not None
    assert signal.stop_price == pytest.approx(100.0 - 2.0 * 1.5)
    assert signal.target_price == pytest.approx(100.0 + 2.0 * 1.5 * 2.0)


def test_simple_trend_none_for_non_positive_atr():
    series = make_indicator_series([make_bar(sma_20=95.0, sma_50=90.0, atr_14=0.0)])
    strategy = SimpleTrendBaseline()

    assert strategy.generate_signal(series, 0, "TEST") is None


def test_simple_trend_none_for_nan_indicators():
    series = make_indicator_series([make_bar(sma_20=float("nan"), sma_50=90.0)])
    strategy = SimpleTrendBaseline()

    assert strategy.generate_signal(series, 0, "TEST") is None
