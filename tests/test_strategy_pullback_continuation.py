import math

from strategy.baseline import STOP_ATR_MULTIPLIER, TARGET_RISK_REWARD
from strategy.pullback_continuation import PullbackContinuationStrategy
from strategy.signal import ReasonCode, Side
from tests.conftest import make_bar, make_indicator_series


def _pullback_series(*, filler_count: int = 1, lookback_rsi=60.0, prior_close=99.0, entry_overrides=None):
    """filler(s) -> lookback bar (index -2 from entry) -> prior bar
    (index -1, "yesterday") -> entry bar. make_bar()'s own defaults
    already qualify as a valid entry bar (sma_20=95 > sma_50=90,
    macd=1.0 > macd_signal=0.5, rsi_14=55.0, close=100.0), so entry_overrides
    only needs to override what a specific test wants to break."""
    entry_kwargs = {"rsi_14": 47.0, "close": 100.0, **(entry_overrides or {})}
    bars = (
        [make_bar() for _ in range(filler_count)]
        + [make_bar(rsi_14=lookback_rsi)]
        + [make_bar(close=prior_close)]
        + [make_bar(**entry_kwargs)]
    )
    return make_indicator_series(bars)


def test_valid_pullback_setup_emits_signal_with_correct_math():
    series = _pullback_series()
    strategy = PullbackContinuationStrategy()

    signal = strategy.generate_signal(series, len(series) - 1, "TEST")

    assert signal is not None
    assert signal.side == Side.LONG
    assert signal.strategy_name == "pullback_continuation"
    assert set(signal.reason_codes) == {ReasonCode.TREND_CONFIRMED, ReasonCode.PULLBACK_CONFIRMED}

    expected_stop_distance = 2.0 * STOP_ATR_MULTIPLIER  # make_bar()'s default atr_14=2.0
    assert math.isclose(signal.stop_price, 100.0 - expected_stop_distance)
    assert math.isclose(signal.target_price, 100.0 + expected_stop_distance * TARGET_RISK_REWARD)
    assert signal.risk_reward == TARGET_RISK_REWARD


def test_no_recent_strength_blocks_signal():
    # Lookback RSI never got high enough -- no evidence of a real push before the "pullback".
    series = _pullback_series(lookback_rsi=50.0)
    strategy = PullbackContinuationStrategy()

    assert strategy.generate_signal(series, len(series) - 1, "TEST") is None


def test_entry_rsi_still_hot_blocks_signal():
    # RSI hasn't actually cooled off -- not a pullback at all.
    series = _pullback_series(entry_overrides={"rsi_14": 60.0})
    strategy = PullbackContinuationStrategy()

    assert strategy.generate_signal(series, len(series) - 1, "TEST") is None


def test_entry_rsi_too_low_blocks_signal():
    # RSI cooled too far -- reads as a trend break, not a healthy pullback.
    series = _pullback_series(entry_overrides={"rsi_14": 35.0})
    strategy = PullbackContinuationStrategy()

    assert strategy.generate_signal(series, len(series) - 1, "TEST") is None


def test_no_resumption_bar_blocks_signal():
    # Entry bar's close does not exceed yesterday's -- price is not yet turning back up.
    series = _pullback_series(prior_close=101.0, entry_overrides={"close": 100.0})
    strategy = PullbackContinuationStrategy()

    assert strategy.generate_signal(series, len(series) - 1, "TEST") is None


def test_trend_not_confirmed_blocks_signal():
    series = _pullback_series(entry_overrides={"sma_20": 85.0, "sma_50": 90.0})
    strategy = PullbackContinuationStrategy()

    assert strategy.generate_signal(series, len(series) - 1, "TEST") is None


def test_momentum_not_confirmed_blocks_signal():
    series = _pullback_series(entry_overrides={"macd": -1.0, "macd_signal": 0.5})
    strategy = PullbackContinuationStrategy()

    assert strategy.generate_signal(series, len(series) - 1, "TEST") is None


def test_insufficient_history_returns_none():
    bars = [make_bar(rsi_14=60.0), make_bar(close=99.0), make_bar(rsi_14=47.0, close=100.0)]
    series = make_indicator_series(bars)
    strategy = PullbackContinuationStrategy()

    # index=2 < PULLBACK_LOOKBACK_BARS(2)+1 -- not enough bars for the lookback+prior window.
    assert strategy.generate_signal(series, 2, "TEST") is None


def test_zero_atr_returns_none_rather_than_a_zero_width_stop():
    series = _pullback_series(entry_overrides={"atr_14": 0.0})
    strategy = PullbackContinuationStrategy()

    assert strategy.generate_signal(series, len(series) - 1, "TEST") is None


def test_missing_indicator_returns_none():
    series = _pullback_series(entry_overrides={"sma_50": float("nan")})
    strategy = PullbackContinuationStrategy()

    assert strategy.generate_signal(series, len(series) - 1, "TEST") is None
