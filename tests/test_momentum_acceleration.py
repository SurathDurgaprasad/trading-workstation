"""H_ENTRY_004: permanent causality/leakage tests for the momentum-
acceleration filter study, mirroring the style of test_regime_filters.py
and test_volume_signal.py.
"""
import pandas as pd
import pytest

from market.data_provider import OHLCV
from market.indicators import compute_indicator_series
from strategy.baseline import TrendMomentumBaseline
from strategy.momentum_acceleration import (
    CANDIDATES,
    add_momentum_acceleration_columns,
)
from strategy.regime_filters import FilteredStrategy


def _ohlcv(n, seed_close=100.0):
    bars = []
    for i in range(n):
        close = seed_close + i * 0.3 + (0.6 if i % 4 == 0 else -0.3)
        bars.append({
            "Open": close - 0.2, "High": close + 1.2, "Low": close - 1.2, "Close": close,
            "Volume": 1_000_000 + (i % 11) * 15_000,
        })
    frame = pd.DataFrame(bars, index=pd.date_range("2024-01-01", periods=n, freq="D"))
    return OHLCV.from_dataframe(symbol="TEST", interval="1d", frame=frame)


def _series(n=260):
    return add_momentum_acceleration_columns(compute_indicator_series(_ohlcv(n)))


# --- column computation -------------------------------------------------------


def test_add_momentum_acceleration_columns_is_purely_additive():
    base = compute_indicator_series(_ohlcv(100))
    augmented = add_momentum_acceleration_columns(base)

    for column in base.columns:
        pd.testing.assert_series_equal(base[column], augmented[column])
    assert "rsi_delta_3" in augmented.columns
    assert "macd_histogram_delta_3" in augmented.columns


def test_rsi_delta_matches_a_direct_three_bar_diff():
    series = _series(100)
    # Pick a row comfortably past every indicator's own warm-up window.
    i = 80
    expected = series["rsi_14"].iloc[i] - series["rsi_14"].iloc[i - 3]
    assert series["rsi_delta_3"].iloc[i] == pytest.approx(expected)


# --- candidate directional logic -----------------------------------------------


@pytest.mark.parametrize(
    "name,rsi_delta,macd_delta,expected",
    [
        ("A_rsi_accelerating", 0.5, -0.1, True),
        ("A_rsi_accelerating", -0.5, 0.1, False),
        ("A_rsi_accelerating", 0.0, 0.1, False),  # boundary is strict >
        ("B_macd_histogram_widening", -0.1, 0.5, True),
        ("B_macd_histogram_widening", 0.1, -0.5, False),
        ("B_macd_histogram_widening", 0.1, 0.0, False),  # boundary is strict >
        ("C_both_accelerating", 0.5, 0.5, True),
        ("C_both_accelerating", 0.5, -0.5, False),
        ("C_both_accelerating", -0.5, 0.5, False),
    ],
)
def test_candidate_direction_matches_frozen_definition(name, rsi_delta, macd_delta, expected):
    row = pd.Series({"rsi_delta_3": rsi_delta, "macd_histogram_delta_3": macd_delta})
    assert CANDIDATES[name](row) is expected


@pytest.mark.parametrize("candidate_name", list(CANDIDATES))
def test_candidate_fails_closed_on_missing_history(candidate_name):
    row = pd.Series({"rsi_delta_3": float("nan"), "macd_histogram_delta_3": float("nan")})
    assert CANDIDATES[candidate_name](row) is False


# --- causality ----------------------------------------------------------------


@pytest.mark.parametrize("candidate_name", list(CANDIDATES))
def test_filtered_strategy_via_acceleration_predicate_only_suppresses(candidate_name):
    """Incremental-value path: TrendMomentumBaseline gated by an
    acceleration predicate must obey the same suppress-only guarantee
    Phase 9 already proved for FilteredStrategy in general -- re-verified
    here specifically for an acceleration-based predicate."""
    series = _series(n=260)
    predicate = CANDIDATES[candidate_name]

    inner = TrendMomentumBaseline()
    filtered = FilteredStrategy(inner=inner, filter_name=candidate_name, predicate=predicate)

    for i in range(len(series)):
        inner_signal = inner.generate_signal(series, i, "TEST")
        filtered_signal = filtered.generate_signal(series, i, "TEST")
        if inner_signal is None:
            assert filtered_signal is None
        if filtered_signal is not None:
            assert filtered_signal.model_dump() == inner_signal.model_dump()


def test_acceleration_columns_ignore_future_bars():
    series = _series(n=260)
    target_index = 200

    mutated = series.copy()
    future_rows = mutated.index[target_index + 1 :]
    mutated.loc[future_rows, "rsi_14"] = 999.0
    mutated.loc[future_rows, "macd_histogram"] = 999.0
    remutated = add_momentum_acceleration_columns(mutated.drop(columns=["rsi_delta_3", "macd_histogram_delta_3"]))

    assert remutated["rsi_delta_3"].iloc[target_index] == pytest.approx(series["rsi_delta_3"].iloc[target_index])
    assert remutated["macd_histogram_delta_3"].iloc[target_index] == pytest.approx(series["macd_histogram_delta_3"].iloc[target_index])


# --- run_universe_momentum_acceleration_experiment -----------------------------


@pytest.fixture
def _fake_acceleration_universe_provider(monkeypatch):
    from market.data_provider import MarketDataError

    class _Provider:
        def __init__(self, good_symbols):
            self._good = good_symbols

        def fetch_ohlcv(self, symbol, *, period="5y", interval="1d"):
            if symbol not in self._good:
                raise MarketDataError(f"no data for {symbol}")
            return _ohlcv(260, seed_close=100.0)

    def _apply(good_symbols):
        import market.data_provider as market_data_provider_module

        monkeypatch.setattr(market_data_provider_module, "get_market_data_provider", lambda: _Provider(good_symbols))

        # Bypass the real on-disk cache entirely -- "AAA"/"BBB"/"BADSYMBOL"
        # are not real cached symbols, so a cache MISS would otherwise
        # WRITE a real file under data/market/ as a side effect (same
        # concern/fix already established for every other universe-level
        # experiment test in this project).
        import backtesting.cache as cache_module

        monkeypatch.setattr(cache_module, "CachedMarketDataProvider", lambda inner: inner)

    return _apply


def test_run_universe_momentum_acceleration_experiment_pools_across_symbols_and_candidates(_fake_acceleration_universe_provider):
    _fake_acceleration_universe_provider({"AAA", "BBB"})

    from strategy.momentum_acceleration import (
        UniverseMomentumAccelerationExperimentResult,
        run_universe_momentum_acceleration_experiment,
    )

    result = run_universe_momentum_acceleration_experiment(["AAA", "BBB"], initial_capital=100_000.0)

    assert isinstance(result, UniverseMomentumAccelerationExperimentResult)
    assert result.failed_symbols == {}
    assert set(result.development_trades) == set(CANDIDATES)
    assert set(result.validation_trades) == set(CANDIDATES)
    assert set(result.out_of_sample_trades) == set(CANDIDATES)
    for candidate_name in CANDIDATES:
        assert isinstance(result.development_trades[candidate_name], list)
        assert isinstance(result.validation_trades[candidate_name], list)
        assert isinstance(result.out_of_sample_trades[candidate_name], list)


def test_run_universe_momentum_acceleration_experiment_isolates_a_failing_symbol(_fake_acceleration_universe_provider):
    _fake_acceleration_universe_provider({"AAA"})

    from strategy.momentum_acceleration import run_universe_momentum_acceleration_experiment

    result = run_universe_momentum_acceleration_experiment(["AAA", "BADSYMBOL"], initial_capital=100_000.0)

    assert "BADSYMBOL" in result.failed_symbols
    assert "AAA" not in result.failed_symbols
