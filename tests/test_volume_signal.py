"""Phase 11: permanent causality/leakage tests for the volume-signal
confirmation study, mirroring the style of test_regime_filters.py and
test_alpha_features.py. Also locks in each candidate's directional logic
against the frozen Phase 10 thresholds/values.
"""
import pandas as pd
import pytest

from market.indicators import compute_indicator_series
from market.data_provider import OHLCV
from quant_research.volume_signal import (
    CANDIDATES,
    VolumeSignalStrategy,
    dev_fit_volume_thresholds,
    make_volume_predicate,
)
from strategy.regime_filters import FilteredStrategy
from strategy.baseline import TrendMomentumBaseline


def _ohlcv(n, seed_close=100.0, volume_pattern=None):
    bars = []
    for i in range(n):
        volume = volume_pattern(i) if volume_pattern else 1_000_000 + (i % 11) * 15_000
        bars.append({
            "Open": seed_close + i * 0.3, "High": seed_close + i * 0.3 + 1.2,
            "Low": seed_close + i * 0.3 - 1.2, "Close": seed_close + i * 0.3 + (0.6 if i % 4 == 0 else -0.3),
            "Volume": volume,
        })
    frame = pd.DataFrame(bars, index=pd.date_range("2024-01-01", periods=n, freq="D"))
    return OHLCV.from_dataframe(symbol="TEST", interval="1d", frame=frame)


def _series(n=260, volume_pattern=None):
    return compute_indicator_series(_ohlcv(n, volume_pattern=volume_pattern))


# --- directional/threshold unit tests -----------------------------------------


@pytest.mark.parametrize(
    "name,volume_ratio,p20,p80,expected",
    [
        ("A_high_volume", 2.5, 0.8, 2.0, True),
        ("A_high_volume", 1.5, 0.8, 2.0, False),
        ("A_high_volume", 2.0, 0.8, 2.0, False),  # boundary is strict >
        ("B_low_volume", 0.5, 0.8, 2.0, True),
        ("B_low_volume", 1.0, 0.8, 2.0, False),
        ("B_low_volume", 0.8, 0.8, 2.0, False),  # boundary is strict <
        ("C_extreme_volume", 2.5, 0.8, 2.0, True),
        ("C_extreme_volume", 0.5, 0.8, 2.0, True),
        ("C_extreme_volume", 1.0, 0.8, 2.0, False),
    ],
)
def test_candidate_direction_matches_frozen_definition(name, volume_ratio, p20, p80, expected):
    assert CANDIDATES[name](volume_ratio, p20, p80) is expected


def test_dev_fit_thresholds_are_fit_only_on_the_given_series():
    dev_values = pd.Series([1.0] * 40 + [2.0] * 40 + [3.0] * 20)
    thresholds = dev_fit_volume_thresholds(dev_values)
    assert thresholds is not None
    p20, p80 = thresholds
    assert p20 < p80


def test_dev_fit_thresholds_returns_none_for_too_small_a_sample():
    assert dev_fit_volume_thresholds(pd.Series([1.0, 2.0, 3.0])) is None


# --- causality --------------------------------------------------------------


def test_volume_signal_strategy_ignores_future_bars():
    series = _series()
    p20, p80 = dev_fit_volume_thresholds(series["volume_ratio"].iloc[:150])
    strategy = VolumeSignalStrategy("A_high_volume", p20, p80)
    target_index = 200

    signal_before = strategy.generate_signal(series, target_index, "TEST")

    mutated = series.copy()
    future_rows = mutated.index[target_index + 1 :]
    mutated.loc[future_rows, "volume_ratio"] = 999.0
    mutated.loc[future_rows, "atr_14"] = 999.0
    mutated.loc[future_rows, "close"] = 1.0

    signal_after = strategy.generate_signal(mutated, target_index, "TEST")

    if signal_before is None:
        assert signal_after is None
    else:
        assert signal_after is not None
        assert signal_before.model_dump() == signal_after.model_dump()


def test_volume_signal_strategy_causal_by_truncated_history_equivalence():
    n = 260
    full_series = _series(n)
    p20, p80 = dev_fit_volume_thresholds(full_series["volume_ratio"].iloc[:150])
    strategy = VolumeSignalStrategy("A_high_volume", p20, p80)

    check_index = 240
    truncated_series = compute_indicator_series(_ohlcv(n)).iloc[: check_index + 1]

    full_signal = strategy.generate_signal(full_series, check_index, "TEST")
    truncated_signal = strategy.generate_signal(truncated_series, len(truncated_series) - 1, "TEST")

    if full_signal is None:
        assert truncated_signal is None
    else:
        assert truncated_signal is not None
        assert full_signal.model_dump() == truncated_signal.model_dump()


@pytest.mark.parametrize("candidate_name", list(CANDIDATES))
def test_filtered_strategy_via_volume_predicate_only_suppresses(candidate_name):
    """Incremental-value path: TrendMomentumBaseline gated by a volume
    predicate must obey the same suppress-only guarantee Phase 9 already
    proved for FilteredStrategy in general — re-verified here specifically
    for a volume-based predicate."""
    series = _series(n=260, volume_pattern=lambda i: 1_000_000 * (1 + (i % 13) * 0.3))
    p20, p80 = dev_fit_volume_thresholds(series["volume_ratio"].iloc[:150])
    predicate = make_volume_predicate(candidate_name, p20, p80)

    inner = TrendMomentumBaseline()
    filtered = FilteredStrategy(inner=inner, filter_name=f"volume_{candidate_name}", predicate=predicate)

    for i in range(len(series)):
        inner_signal = inner.generate_signal(series, i, "TEST")
        filtered_signal = filtered.generate_signal(series, i, "TEST")
        if inner_signal is None:
            assert filtered_signal is None
        if filtered_signal is not None:
            assert filtered_signal.model_dump() == inner_signal.model_dump()


def test_volume_signal_strategy_never_fires_without_valid_atr():
    series = _series()
    mutated = series.copy()
    mutated["atr_14"] = 0.0  # degenerate ATR everywhere
    p20, p80 = dev_fit_volume_thresholds(series["volume_ratio"].iloc[:150])
    strategy = VolumeSignalStrategy("C_extreme_volume", p20, p80)

    for i in range(len(mutated)):
        assert strategy.generate_signal(mutated, i, "TEST") is None


# --- run_universe_volume_filter_experiment (H_ENTRY_002 universe runner) ------


def _trending_ohlcv(symbol, n=260):
    """A real uptrend (so TrendMomentumBaseline's SMA20>SMA50/RSI/MACD
    conditions are reachable, not guaranteed to fire every bar) with
    genuinely varying volume (so dev_fit_volume_thresholds sees real
    dispersion, not a degenerate p20==p80)."""
    from market.data_provider import OHLCV

    bars = []
    for i in range(n):
        close = 100.0 + i * 0.35 + (2.0 if i % 17 == 0 else 0.0)
        volume = 1_000_000 * (1 + ((i * 7) % 23) / 10)
        bars.append({
            "Open": close - 0.2, "High": close + 1.5, "Low": close - 1.5, "Close": close, "Volume": volume,
        })
    frame = pd.DataFrame(bars, index=pd.date_range("2024-01-01", periods=n, freq="D"))
    return OHLCV.from_dataframe(symbol=symbol, interval="1d", frame=frame)


@pytest.fixture
def _fake_volume_universe_provider(monkeypatch):
    from market.data_provider import MarketDataError

    class _Provider:
        def __init__(self, good_symbols):
            self._good = good_symbols

        def fetch_ohlcv(self, symbol, *, period="5y", interval="1d"):
            if symbol not in self._good:
                raise MarketDataError(f"no data for {symbol}")
            return _trending_ohlcv(symbol)

    def _apply(good_symbols):
        import market.data_provider as market_data_provider_module

        monkeypatch.setattr(market_data_provider_module, "get_market_data_provider", lambda: _Provider(good_symbols))

        # Bypass the real on-disk cache entirely -- "AAA"/"BBB"/"BADSYMBOL"
        # are not real cached symbols, so a cache MISS would otherwise
        # WRITE a real file under data/market/ as a side effect (same
        # concern/fix already established for exit_experiments' own
        # universe tests in test_backtest_exit_experiments.py).
        import backtesting.cache as cache_module

        monkeypatch.setattr(cache_module, "CachedMarketDataProvider", lambda inner: inner)

    return _apply


def test_run_universe_volume_filter_experiment_pools_across_symbols_and_candidates(_fake_volume_universe_provider):
    _fake_volume_universe_provider({"AAA", "BBB"})

    from quant_research.volume_signal import CANDIDATES, UniverseVolumeFilterExperimentResult, run_universe_volume_filter_experiment

    result = run_universe_volume_filter_experiment(["AAA", "BBB"], initial_capital=100_000.0)

    assert isinstance(result, UniverseVolumeFilterExperimentResult)
    assert result.failed_symbols == {}
    assert result.insufficient_threshold_symbols == {}
    assert set(result.development_trades) == set(CANDIDATES)
    assert set(result.validation_trades) == set(CANDIDATES)
    assert set(result.out_of_sample_trades) == set(CANDIDATES)
    for candidate_name in CANDIDATES:
        assert isinstance(result.development_trades[candidate_name], list)
        assert isinstance(result.validation_trades[candidate_name], list)
        assert isinstance(result.out_of_sample_trades[candidate_name], list)


def test_run_universe_volume_filter_experiment_isolates_a_failing_symbol(_fake_volume_universe_provider):
    _fake_volume_universe_provider({"AAA"})

    from quant_research.volume_signal import run_universe_volume_filter_experiment

    result = run_universe_volume_filter_experiment(["AAA", "BADSYMBOL"], initial_capital=100_000.0)

    assert "BADSYMBOL" in result.failed_symbols
    assert "AAA" not in result.failed_symbols


def test_run_universe_volume_filter_experiment_flags_insufficient_threshold_data(monkeypatch):
    """A symbol with too few development-period bars for
    dev_fit_volume_thresholds's own 50-row floor must be excluded
    honestly (insufficient_threshold_symbols), never silently dropped
    into failed_symbols (a different failure mode) or crash."""
    from market.data_provider import MarketDataError

    class _Provider:
        def fetch_ohlcv(self, symbol, *, period="5y", interval="1d"):
            if symbol != "SHORT":
                raise MarketDataError(f"no data for {symbol}")
            return _trending_ohlcv(symbol, n=60)  # 60 * 0.6 = 36 dev rows, below the 50-row floor

    import market.data_provider as market_data_provider_module

    monkeypatch.setattr(market_data_provider_module, "get_market_data_provider", lambda: _Provider())
    import backtesting.cache as cache_module

    monkeypatch.setattr(cache_module, "CachedMarketDataProvider", lambda inner: inner)

    from quant_research.volume_signal import run_universe_volume_filter_experiment

    result = run_universe_volume_filter_experiment(["SHORT"], initial_capital=100_000.0)

    assert "SHORT" in result.insufficient_threshold_symbols
    assert "SHORT" not in result.failed_symbols
    assert result.insufficient_threshold_symbols["SHORT"] < 50
