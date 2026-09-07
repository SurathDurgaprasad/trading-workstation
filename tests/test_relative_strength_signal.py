"""H_RELSTRENGTH_001: permanent causality/leakage tests for the relative-
strength signal study, mirroring the style of test_mean_reversion_signal.py
and test_volume_signal.py.
"""
import pandas as pd
import pytest

from market.data_provider import OHLCV
from market.indicators import compute_indicator_series
from quant_research.relative_strength_signal import (
    CANDIDATES,
    RelativeStrengthSignalStrategy,
    add_relative_strength_column,
    benchmark_symbol_for,
)
from strategy.signal import ReasonCode


def _ohlcv(symbol, n, seed_close=100.0, daily_drift=0.15):
    bars = []
    close = seed_close
    for i in range(n):
        close += daily_drift
        bars.append({"Open": close - 0.2, "High": close + 1.0, "Low": close - 1.0, "Close": close, "Volume": 1_000_000.0})
    frame = pd.DataFrame(bars, index=pd.date_range("2024-01-01", periods=n, freq="D"))
    return OHLCV.from_dataframe(symbol=symbol, interval="1d", frame=frame)


def _series(n=260, symbol_drift=0.30, benchmark_drift=0.05):
    """A symbol that drifts up much faster than its own benchmark --
    real, sustained relative-strength outperformance, not a coincidence."""
    symbol_series = compute_indicator_series(_ohlcv("TEST", n, daily_drift=symbol_drift))
    benchmark_series = compute_indicator_series(_ohlcv("^NSEI", n, daily_drift=benchmark_drift))
    return add_relative_strength_column(symbol_series, benchmark_series)


# --- benchmark_symbol_for -------------------------------------------------------


@pytest.mark.parametrize(
    "symbol,expected",
    [("RELIANCE.NS", "^NSEI"), ("reliance.ns", "^NSEI"), ("TATASTEEL.BO", "^NSEI"), ("AAPL", "^GSPC"), ("MSFT", "^GSPC")],
)
def test_benchmark_symbol_for_matches_alpha_features_convention(symbol, expected):
    assert benchmark_symbol_for(symbol) == expected


# --- column computation -------------------------------------------------------


def test_add_relative_strength_column_is_purely_additive():
    base = compute_indicator_series(_ohlcv("TEST", 100))
    benchmark = compute_indicator_series(_ohlcv("^NSEI", 100, daily_drift=0.05))
    augmented = add_relative_strength_column(base, benchmark)

    for column in base.columns:
        pd.testing.assert_series_equal(base[column], augmented[column])
    assert "relative_strength_20" in augmented.columns


def test_a_real_outperformer_produces_a_positive_relative_strength():
    series = _series(n=100, symbol_drift=0.40, benchmark_drift=0.05)
    assert series["relative_strength_20"].iloc[80] > 0.0


def test_a_real_underperformer_produces_a_negative_relative_strength():
    series = _series(n=100, symbol_drift=0.02, benchmark_drift=0.40)
    assert series["relative_strength_20"].iloc[80] < 0.0


# --- candidate directional logic -----------------------------------------------


@pytest.mark.parametrize(
    "name,relative_strength,expected",
    [
        ("A_any_outperformance", 0.01, True),
        ("A_any_outperformance", -0.01, False),
        ("A_any_outperformance", 0.0, False),  # boundary is strict >
        ("B_meaningful_outperformance", 0.06, True),
        ("B_meaningful_outperformance", 0.04, False),
        ("B_meaningful_outperformance", 0.05, False),  # boundary is strict >
        ("C_strong_outperformance", 0.11, True),
        ("C_strong_outperformance", 0.09, False),
        ("C_strong_outperformance", 0.10, False),  # boundary is strict >
    ],
)
def test_candidate_direction_matches_frozen_definition(name, relative_strength, expected):
    row = pd.Series({"relative_strength_20": relative_strength})
    assert CANDIDATES[name](row) is expected


@pytest.mark.parametrize("candidate_name", list(CANDIDATES))
def test_candidate_fails_closed_on_missing_history(candidate_name):
    row = pd.Series({"relative_strength_20": float("nan")})
    assert CANDIDATES[candidate_name](row) is False


def test_candidates_are_a_monotonic_ladder():
    """Whatever passes the strictest candidate must also pass the
    looser ones -- a real dose-response ladder, not three unrelated
    rules that happen to share a name pattern."""
    for relative_strength in (0.02, 0.06, 0.12):
        row = pd.Series({"relative_strength_20": relative_strength})
        if CANDIDATES["C_strong_outperformance"](row):
            assert CANDIDATES["B_meaningful_outperformance"](row)
        if CANDIDATES["B_meaningful_outperformance"](row):
            assert CANDIDATES["A_any_outperformance"](row)


# --- RelativeStrengthSignalStrategy ---------------------------------------------


def test_strategy_uses_the_dedicated_reason_code():
    series = _series(n=100, symbol_drift=0.40, benchmark_drift=0.05)
    strategy = RelativeStrengthSignalStrategy("A_any_outperformance")

    fired = [strategy.generate_signal(series, i, "TEST") for i in range(len(series))]
    real_signals = [s for s in fired if s is not None]

    assert real_signals, "expected at least one signal from a sustained real outperformer against candidate A"
    assert all(s.reason_codes == [ReasonCode.RELATIVE_STRENGTH_CONFIRMED] for s in real_signals)


def test_strategy_never_fires_without_valid_atr():
    series = _series(n=100, symbol_drift=0.40, benchmark_drift=0.05)
    mutated = series.copy()
    mutated["atr_14"] = 0.0  # degenerate ATR everywhere
    strategy = RelativeStrengthSignalStrategy("A_any_outperformance")

    for i in range(len(mutated)):
        assert strategy.generate_signal(mutated, i, "TEST") is None


def test_strategy_ignores_future_bars():
    series = _series(n=260, symbol_drift=0.40, benchmark_drift=0.05)
    target_index = 200
    strategy = RelativeStrengthSignalStrategy("A_any_outperformance")

    signal_before = strategy.generate_signal(series, target_index, "TEST")

    mutated = series.copy()
    future_rows = mutated.index[target_index + 1 :]
    mutated.loc[future_rows, "relative_strength_20"] = -999.0
    mutated.loc[future_rows, "close"] = 1.0

    signal_after = strategy.generate_signal(mutated, target_index, "TEST")

    if signal_before is None:
        assert signal_after is None
    else:
        assert signal_after is not None
        assert signal_before.model_dump() == signal_after.model_dump()


# --- run_universe_relative_strength_experiment ----------------------------------


@pytest.fixture
def _fake_relative_strength_universe_provider(monkeypatch):
    from market.data_provider import MarketDataError

    class _Provider:
        def __init__(self, good_symbols):
            self._good = good_symbols

        def fetch_ohlcv(self, symbol, *, period="5y", interval="1d"):
            if symbol not in self._good:
                raise MarketDataError(f"no data for {symbol}")
            if symbol in ("^NSEI", "^GSPC"):
                return _ohlcv(symbol, 260, daily_drift=0.05)
            return _ohlcv(symbol, 260, daily_drift=0.40)

    def _apply(good_symbols):
        import market.data_provider as market_data_provider_module

        # Every fixture symbol needs its own benchmark reachable too.
        good_symbols = set(good_symbols) | {"^NSEI", "^GSPC"}
        monkeypatch.setattr(market_data_provider_module, "get_market_data_provider", lambda: _Provider(good_symbols))

        # Bypass the real on-disk cache entirely -- "AAA"/"BBB"/"BADSYMBOL"
        # are not real cached symbols, so a cache MISS would otherwise
        # WRITE a real file under data/market/ as a side effect (same
        # concern/fix established for every other universe-level
        # experiment test in this project).
        import backtesting.cache as cache_module

        monkeypatch.setattr(cache_module, "CachedMarketDataProvider", lambda inner: inner)

    return _apply


def test_run_universe_relative_strength_experiment_pools_across_symbols_and_candidates(_fake_relative_strength_universe_provider):
    _fake_relative_strength_universe_provider({"AAA", "BBB"})

    from quant_research.relative_strength_signal import (
        UniverseRelativeStrengthExperimentResult,
        run_universe_relative_strength_experiment,
    )

    result = run_universe_relative_strength_experiment(["AAA", "BBB"], initial_capital=100_000.0)

    assert isinstance(result, UniverseRelativeStrengthExperimentResult)
    assert result.failed_symbols == {}
    assert set(result.development_trades) == set(CANDIDATES)
    assert set(result.validation_trades) == set(CANDIDATES)
    assert set(result.out_of_sample_trades) == set(CANDIDATES)
    for candidate_name in CANDIDATES:
        assert isinstance(result.development_trades[candidate_name], list)
        assert isinstance(result.validation_trades[candidate_name], list)
        assert isinstance(result.out_of_sample_trades[candidate_name], list)


def test_run_universe_relative_strength_experiment_isolates_a_failing_symbol(_fake_relative_strength_universe_provider):
    _fake_relative_strength_universe_provider({"AAA"})

    from quant_research.relative_strength_signal import run_universe_relative_strength_experiment

    result = run_universe_relative_strength_experiment(["AAA", "BADSYMBOL"], initial_capital=100_000.0)

    assert "BADSYMBOL" in result.failed_symbols
    assert "AAA" not in result.failed_symbols
