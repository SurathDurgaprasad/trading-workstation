import copy
from datetime import datetime, timedelta

import pandas as pd

from backtesting.regime import (
    RegimeClassification,
    TrendRegime,
    VolatilityRegime,
    classify_regime_at_index,
    classify_trend_at,
    classify_volatility_at,
    group_trade_returns_by_regime,
)
from backtesting.trade import ExitReason, Trade
from strategy.signal import Side


def _series(rows: list[dict]) -> pd.DataFrame:
    index = [datetime(2026, 1, 1) + timedelta(days=i) for i in range(len(rows))]
    return pd.DataFrame(rows, index=index)


def _flat_row(sma_20=100.0, sma_50=100.0, atr_14=2.0, close=100.0) -> dict:
    return {"sma_20": sma_20, "sma_50": sma_50, "atr_14": atr_14, "close": close}


def _repeat(n: int, **kwargs) -> list[dict]:
    """Genuinely independent dict instances -- `[_flat_row()] * n` would
    alias the SAME dict object n times (a real bug found while writing
    these tests: mutating rows[i] silently mutated every row)."""
    return [_flat_row(**kwargs) for _ in range(n)]


# --- classify_trend_at: boundary conditions -------------------------------------


def test_classify_trend_unknown_before_slope_lookback_window_exists():
    series = _series(_repeat(5))  # fewer rows than DEFAULT_TREND_SLOPE_LOOKBACK=10

    assert classify_trend_at(series, 4) == TrendRegime.UNKNOWN


def test_classify_trend_unknown_for_nan_sma():
    rows = _repeat(11)
    rows[10]["sma_20"] = float("nan")
    series = _series(rows)

    assert classify_trend_at(series, 10) == TrendRegime.UNKNOWN


def test_classify_trend_up_when_sma20_above_sma50_and_rising():
    rows = _repeat(11, sma_20=100.0, sma_50=95.0)
    rows[10]["sma_20"] = 103.0  # +3% over 10 bars vs the prior row's 100.0

    series = _series(rows)

    assert classify_trend_at(series, 10) == TrendRegime.UP


def test_classify_trend_down_when_sma20_below_sma50_and_falling():
    rows = _repeat(11, sma_20=100.0, sma_50=105.0)
    rows[10]["sma_20"] = 97.0  # -3% vs prior

    series = _series(rows)

    assert classify_trend_at(series, 10) == TrendRegime.DOWN


def test_classify_trend_sideways_when_sma20_above_sma50_but_flat():
    # sma_20 > sma_50 (would look "bullish" by the raw comparison alone)
    # but the slope over the lookback is essentially zero -- must be
    # SIDEWAYS, not UP, proving the slope check actually matters.
    rows = _repeat(11, sma_20=100.0, sma_50=95.0)

    series = _series(rows)

    assert classify_trend_at(series, 10) == TrendRegime.SIDEWAYS


def test_classify_trend_exact_threshold_boundary_counts_as_trending():
    # slope_pct exactly == slope_threshold_pct (0.5%) must classify as UP
    # (>=, inclusive), not SIDEWAYS.
    rows = _repeat(11, sma_20=100.0, sma_50=95.0)
    rows[10]["sma_20"] = 100.5  # exactly +0.5%

    series = _series(rows)

    assert classify_trend_at(series, 10) == TrendRegime.UP


def test_classify_trend_unknown_for_zero_prior_sma_avoids_division_by_zero():
    rows = _repeat(11, sma_20=0.0, sma_50=95.0)
    rows[10]["sma_20"] = 5.0

    series = _series(rows)

    assert classify_trend_at(series, 10) == TrendRegime.UNKNOWN


def test_classify_trend_never_reads_rows_after_index_look_ahead_safety():
    # Mirrors the project's own established look-ahead test pattern
    # (tests/test_backtest_lookahead.py): mutating bars strictly AFTER
    # `index` must never change the classification AT `index`.
    rows = _repeat(15, sma_20=100.0, sma_50=95.0)
    rows[10]["sma_20"] = 103.0
    series_a = _series(rows)

    mutated = copy.deepcopy(rows)
    for i in range(11, 15):
        mutated[i]["sma_20"] = -999.0  # wildly different future values
    series_b = _series(mutated)

    assert classify_trend_at(series_a, 10) == classify_trend_at(series_b, 10) == TrendRegime.UP


# --- classify_volatility_at: boundary conditions --------------------------------


def test_classify_volatility_unknown_before_lookback_window_exists():
    series = _series(_repeat(30))  # fewer than DEFAULT_VOLATILITY_LOOKBACK=60

    assert classify_volatility_at(series, 29) == VolatilityRegime.UNKNOWN


def test_classify_volatility_normal_when_atr_matches_trailing_average():
    rows = _repeat(61, atr_14=2.0, close=100.0)

    series = _series(rows)

    assert classify_volatility_at(series, 60) == VolatilityRegime.NORMAL


def test_classify_volatility_high_when_atr_spikes_above_trailing_average():
    rows = _repeat(61, atr_14=2.0, close=100.0)
    rows[60]["atr_14"] = 3.5  # 3.5% vs trailing 2% average -> ratio 1.75 >= 1.5

    series = _series(rows)

    assert classify_volatility_at(series, 60) == VolatilityRegime.HIGH


def test_classify_volatility_low_when_atr_contracts_below_trailing_average():
    rows = _repeat(61, atr_14=2.0, close=100.0)
    rows[60]["atr_14"] = 1.0  # ratio 0.5 <= 0.67

    series = _series(rows)

    assert classify_volatility_at(series, 60) == VolatilityRegime.LOW


def test_classify_volatility_exact_high_threshold_boundary_counts_as_high():
    rows = _repeat(61, atr_14=2.0, close=100.0)
    rows[60]["atr_14"] = 3.0  # ratio exactly 1.5

    series = _series(rows)

    assert classify_volatility_at(series, 60) == VolatilityRegime.HIGH


def test_classify_volatility_current_bar_excluded_from_its_own_trailing_baseline():
    # If the current (spiking) bar were included in its own trailing
    # average, it would partially average itself away and understate the
    # true ratio. All 60 PRIOR bars are calm (atr_pct=2%); only the
    # CURRENT bar spikes.
    rows = _repeat(60, atr_14=2.0, close=100.0) + _repeat(1, atr_14=10.0, close=100.0)

    series = _series(rows)

    # Trailing average of the 60 prior bars is exactly 2% (unaffected by
    # the spike), so ratio = 10/2 = 5.0 -- unambiguously HIGH.
    assert classify_volatility_at(series, 60) == VolatilityRegime.HIGH


def test_classify_volatility_never_reads_rows_after_index_look_ahead_safety():
    rows = _repeat(65, atr_14=2.0, close=100.0)
    series_a = _series(rows)

    mutated = copy.deepcopy(rows)
    for i in range(61, 65):
        mutated[i]["atr_14"] = 999.0
    series_b = _series(mutated)

    assert classify_volatility_at(series_a, 60) == classify_volatility_at(series_b, 60) == VolatilityRegime.NORMAL


# --- classify_regime_at_index composition ---------------------------------------


def test_classify_regime_at_index_combines_both_dimensions():
    rows = _repeat(61, sma_20=100.0, sma_50=95.0, atr_14=2.0, close=100.0)
    rows[60]["sma_20"] = 103.0
    rows[60]["atr_14"] = 3.5

    series = _series(rows)
    result = classify_regime_at_index(series, 60)

    assert result.trend == TrendRegime.UP
    assert result.volatility == VolatilityRegime.HIGH


# --- group_trade_returns_by_regime ----------------------------------------------


def _trade(*, symbol="TEST", entry_time, entry_price=100.0, quantity=10, net_pnl=50.0) -> Trade:
    return Trade(
        symbol=symbol, side=Side.LONG, strategy_name="unit-test", signal_generated_at=entry_time,
        entry_time=entry_time, entry_price=entry_price, quantity=quantity, stop_price=90.0, target_price=110.0,
        exit_time=entry_time, exit_price=entry_price + net_pnl / quantity, exit_reason=ExitReason.TARGET,
        gross_pnl=net_pnl, costs=0.0, net_pnl=net_pnl, r_multiple=1.0,
    )


def test_group_trade_returns_by_regime_buckets_correctly():
    rows = _repeat(61, sma_20=100.0, sma_50=95.0, atr_14=2.0, close=100.0)
    rows[60]["sma_20"] = 103.0  # bar 60 -> TRENDING_UP, NORMAL_VOLATILITY
    series = _series(rows)
    entry_time = series.index[60]

    trade = _trade(entry_time=entry_time, net_pnl=100.0)

    buckets = group_trade_returns_by_regime([(trade, series)])

    expected_key = RegimeClassification(trend=TrendRegime.UP, volatility=VolatilityRegime.NORMAL)
    assert expected_key in buckets
    assert buckets[expected_key] == [100.0 / (100.0 * 10)]


def test_group_trade_returns_by_regime_skips_a_trade_whose_entry_time_is_not_in_its_series():
    rows = _repeat(61, sma_20=100.0, sma_50=95.0, atr_14=2.0, close=100.0)
    series = _series(rows)
    trade = _trade(entry_time=datetime(2099, 1, 1), net_pnl=100.0)

    buckets = group_trade_returns_by_regime([(trade, series)])

    assert buckets == {}


def test_group_trade_returns_by_regime_pools_multiple_trades_in_the_same_bucket():
    rows = _repeat(61, sma_20=100.0, sma_50=95.0, atr_14=2.0, close=100.0)
    series = _series(rows)
    entry_time = series.index[60]  # SIDEWAYS/NORMAL: flat series, and index 60 has enough history for both lookbacks (>=60)

    trade_a = _trade(symbol="AAA", entry_time=entry_time, net_pnl=100.0)
    trade_b = _trade(symbol="BBB", entry_time=entry_time, net_pnl=-50.0)

    buckets = group_trade_returns_by_regime([(trade_a, series), (trade_b, series)])

    key = RegimeClassification(trend=TrendRegime.SIDEWAYS, volatility=VolatilityRegime.NORMAL)
    assert len(buckets[key]) == 2
