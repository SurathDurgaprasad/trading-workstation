"""H_MEANREV_002: permanent causality/leakage tests for the US
weakness-reversal signal, mirroring the style of every other new
hypothesis this session. Also proves this Strategy needs no custom
runner -- it plugs directly into the EXISTING, unchanged
backtesting.runner.run_full_backtest and backtesting.exit_experiments.
run_universe_time_based_exit_experiment.
"""
import pandas as pd
import pytest

from market.data_provider import OHLCV
from market.indicators import compute_indicator_series
from quant_research.us_weakness_reversal_signal import (
    FROZEN_WEAKNESS_THRESHOLD,
    USWeaknessReversalStrategy,
)
from strategy.signal import ReasonCode


def _ohlcv(n=200, seed_close=100.0, drop_at=None, drop_pct=0.08):
    """A mostly-flat series with an optional sharp, real 5-bar drop
    starting at `drop_at` so a genuine trailing_return_5 breach is
    reachable, not just theoretically."""
    bars = []
    close = seed_close
    for i in range(n):
        if drop_at is not None and drop_at <= i < drop_at + 5:
            close *= (1 - drop_pct / 5)
        else:
            close += 0.05
        bars.append({"Open": close - 0.1, "High": close + 1.0, "Low": close - 1.0, "Close": close, "Volume": 1_000_000.0})
    frame = pd.DataFrame(bars, index=pd.date_range("2024-01-01", periods=n, freq="D"))
    return OHLCV.from_dataframe(symbol="TEST", interval="1d", frame=frame)


def _series(n=200, drop_at=None, drop_pct=0.08):
    return compute_indicator_series(_ohlcv(n, drop_at=drop_at, drop_pct=drop_pct))


def test_frozen_threshold_is_the_documented_value():
    """Regression: this constant must never silently drift -- it is a
    frozen, sourced, external fact (the real dev-period 5th percentile),
    not a tunable parameter."""
    assert FROZEN_WEAKNESS_THRESHOLD == pytest.approx(-0.053477)


def test_strategy_never_fires_before_five_bars_of_history():
    series = _series(n=50)
    strategy = USWeaknessReversalStrategy()
    for i in range(5):
        assert strategy.generate_signal(series, i, "TEST") is None


def test_strategy_fires_on_a_real_breach_of_the_frozen_threshold():
    series = _series(n=100, drop_at=50, drop_pct=0.10)  # a genuine ~10% 5-bar decline, well past -5.3477%
    strategy = USWeaknessReversalStrategy()

    fired = [strategy.generate_signal(series, i, "TEST") for i in range(len(series))]
    real_signals = [s for s in fired if s is not None]

    assert real_signals, "expected at least one signal from a real 10% 5-bar decline against a -5.3477% threshold"
    assert all(s.reason_codes == [ReasonCode.MEAN_REVERSION_OVERSOLD] for s in real_signals)
    assert all(s.side.value == "LONG" for s in real_signals)


def test_strategy_does_not_fire_on_a_mild_decline_under_the_threshold():
    series = _series(n=100, drop_at=50, drop_pct=0.02)  # a mild ~2% decline, well short of -5.3477%
    strategy = USWeaknessReversalStrategy()

    fired = [strategy.generate_signal(series, i, "TEST") for i in range(len(series))]
    assert all(s is None for s in fired)


def test_strategy_never_fires_without_valid_atr():
    series = _series(n=100, drop_at=50, drop_pct=0.10)
    mutated = series.copy()
    mutated["atr_14"] = 0.0  # degenerate ATR everywhere
    strategy = USWeaknessReversalStrategy()

    for i in range(len(mutated)):
        assert strategy.generate_signal(mutated, i, "TEST") is None


def test_strategy_ignores_future_bars():
    series = _series(n=150, drop_at=100, drop_pct=0.10)
    target_index = 130
    strategy = USWeaknessReversalStrategy()

    signal_before = strategy.generate_signal(series, target_index, "TEST")

    mutated = series.copy()
    future_rows = mutated.index[target_index + 1 :]
    mutated.loc[future_rows, "close"] = 1.0

    signal_after = strategy.generate_signal(mutated, target_index, "TEST")

    if signal_before is None:
        assert signal_after is None
    else:
        assert signal_after is not None
        assert signal_before.model_dump() == signal_after.model_dump()


# --- integration: plugs directly into EXISTING, unchanged runners ---------------


def test_plugs_directly_into_run_full_backtest_unchanged(monkeypatch):
    from market.data_provider import MarketDataError

    class _Provider:
        def fetch_ohlcv(self, symbol, *, period="5y", interval="1d"):
            if symbol != "TEST":
                raise MarketDataError("no data")
            return _ohlcv(200, drop_at=100, drop_pct=0.10)

    import market.data_provider as market_data_provider_module

    monkeypatch.setattr(market_data_provider_module, "get_market_data_provider", lambda: _Provider())
    import backtesting.cache as cache_module

    monkeypatch.setattr(cache_module, "CachedMarketDataProvider", lambda inner: inner)

    from backtesting.runner import run_full_backtest

    run_result = run_full_backtest(symbol="TEST", strategy=USWeaknessReversalStrategy(), period="5y", interval="1d")
    assert run_result.full is not None  # no crash -- the Strategy protocol contract is satisfied end to end


def test_plugs_directly_into_run_universe_time_based_exit_experiment_unchanged(monkeypatch):
    from market.data_provider import MarketDataError

    class _Provider:
        def fetch_ohlcv(self, symbol, *, period="5y", interval="1d"):
            if symbol != "TEST":
                raise MarketDataError("no data")
            return _ohlcv(200, drop_at=100, drop_pct=0.10)

    import market.data_provider as market_data_provider_module

    monkeypatch.setattr(market_data_provider_module, "get_market_data_provider", lambda: _Provider())
    import backtesting.cache as cache_module

    monkeypatch.setattr(cache_module, "CachedMarketDataProvider", lambda inner: inner)

    from backtesting.exit_experiments import run_universe_time_based_exit_experiment

    result = run_universe_time_based_exit_experiment(
        ["TEST"], strategy=USWeaknessReversalStrategy(), max_holding_bars=5, initial_capital=100_000.0,
    )
    assert result.failed_symbols == {}
    assert isinstance(result.development_trades, list)
