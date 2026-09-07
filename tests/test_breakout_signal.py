"""H_BREAKOUT_001: permanent causality/leakage tests for the breakout
signal study, mirroring the style of test_mean_reversion_signal.py and
test_relative_strength_signal.py.
"""
import pandas as pd
import pytest

from market.data_provider import OHLCV
from market.indicators import compute_indicator_series
from quant_research.breakout_signal import (
    CANDIDATES,
    DONCHIAN_LOOKBACK_BARS,
    BreakoutSignalStrategy,
    add_breakout_columns,
)
from strategy.signal import ReasonCode


def _ohlcv(n, seed_close=100.0, breakout_at=None, volume_pattern=None, low_vol_before_breakout=False):
    """A mostly-flat/quiet series (tight daily range) with an optional
    genuine, sustained breakout starting at `breakout_at` (a real,
    multi-bar range expansion well above the prior 20-bar high)."""
    bars = []
    close = seed_close
    for i in range(n):
        if breakout_at is not None and i >= breakout_at:
            close += 2.0  # real, sustained range expansion
            high, low = close + 1.5, close - 0.3
        else:
            close += 0.02  # near-flat drift, tight range -- low volatility
            high, low = close + 0.3, close - 0.3
        volume = volume_pattern(i) if volume_pattern else 1_000_000.0
        bars.append({"Open": close - 0.1, "High": high, "Low": low, "Close": close, "Volume": volume})
    frame = pd.DataFrame(bars, index=pd.date_range("2024-01-01", periods=n, freq="D"))
    return OHLCV.from_dataframe(symbol="TEST", interval="1d", frame=frame)


def _series(n=260, breakout_at=None, volume_pattern=None):
    return add_breakout_columns(compute_indicator_series(_ohlcv(n, breakout_at=breakout_at, volume_pattern=volume_pattern)))


# --- column computation -------------------------------------------------------


def test_add_breakout_columns_is_purely_additive():
    base = compute_indicator_series(_ohlcv(150))
    augmented = add_breakout_columns(base)

    for column in base.columns:
        pd.testing.assert_series_equal(base[column], augmented[column])
    assert "donchian_high_20" in augmented.columns
    assert "atr_pct_median_60" in augmented.columns


def test_donchian_high_excludes_the_current_bars_own_high():
    """The classic off-by-one trap: without shift(1), "today's high is a
    new 20-day high" is trivially true on almost every up-trending bar.
    donchian_high_20 at row i must equal the max HIGH of rows
    [i-20, i-1] -- never including row i's own high."""
    series = _series(n=150)
    i = 100
    expected = compute_indicator_series(_ohlcv(150))["high"].iloc[i - DONCHIAN_LOOKBACK_BARS : i].max()
    assert series["donchian_high_20"].iloc[i] == pytest.approx(expected)


def test_a_real_breakout_is_detected():
    series = _series(n=150, breakout_at=100)
    # A few bars into the breakout, close should clear the pre-breakout 20-bar high.
    row = series.iloc[105]
    assert row["close"] > row["donchian_high_20"]


def test_a_flat_series_never_breaks_out():
    series = _series(n=150)  # no breakout_at -- pure near-flat drift throughout
    breakouts = series["close"] > series["donchian_high_20"]
    assert not breakouts.fillna(False).any()


# --- candidate directional logic -----------------------------------------------


@pytest.mark.parametrize(
    "name,close,donchian_high,atr_pct,atr_median,volume_ratio,expected",
    [
        ("A_raw_breakout", 105.0, 100.0, 0.02, 0.03, 1.0, True),
        ("A_raw_breakout", 95.0, 100.0, 0.02, 0.03, 1.0, False),
        ("B_breakout_after_volatility_contraction", 105.0, 100.0, 0.02, 0.03, 1.0, True),  # atr_pct < median: contraction
        ("B_breakout_after_volatility_contraction", 105.0, 100.0, 0.05, 0.03, 1.0, False),  # atr_pct > median: no contraction
        ("B_breakout_after_volatility_contraction", 95.0, 100.0, 0.02, 0.03, 1.0, False),  # not even a breakout
        ("C_breakout_with_volume_expansion", 105.0, 100.0, 0.02, 0.03, 2.0, True),  # volume_ratio > 1.5
        ("C_breakout_with_volume_expansion", 105.0, 100.0, 0.02, 0.03, 1.2, False),  # volume_ratio <= 1.5
        ("C_breakout_with_volume_expansion", 95.0, 100.0, 0.02, 0.03, 2.0, False),  # not even a breakout
    ],
)
def test_candidate_direction_matches_frozen_definition(name, close, donchian_high, atr_pct, atr_median, volume_ratio, expected):
    row = pd.Series({
        "close": close, "donchian_high_20": donchian_high, "atr_pct_of_price": atr_pct,
        "atr_pct_median_60": atr_median, "volume_ratio": volume_ratio,
    })
    assert CANDIDATES[name](row) is expected


@pytest.mark.parametrize("candidate_name", list(CANDIDATES))
def test_candidate_fails_closed_on_missing_history(candidate_name):
    row = pd.Series({
        "close": 105.0, "donchian_high_20": float("nan"), "atr_pct_of_price": float("nan"),
        "atr_pct_median_60": float("nan"), "volume_ratio": float("nan"),
    })
    assert CANDIDATES[candidate_name](row) is False


# --- BreakoutSignalStrategy ------------------------------------------------------


def test_strategy_uses_the_dedicated_reason_code():
    series = _series(n=150, breakout_at=100)
    strategy = BreakoutSignalStrategy("A_raw_breakout")

    fired = [strategy.generate_signal(series, i, "TEST") for i in range(len(series))]
    real_signals = [s for s in fired if s is not None]

    assert real_signals, "expected at least one signal from a real, sustained breakout"
    assert all(s.reason_codes == [ReasonCode.BREAKOUT_CONFIRMED] for s in real_signals)


def test_strategy_never_fires_without_valid_atr():
    series = _series(n=150, breakout_at=100)
    mutated = series.copy()
    mutated["atr_14"] = 0.0  # degenerate ATR everywhere
    strategy = BreakoutSignalStrategy("A_raw_breakout")

    for i in range(len(mutated)):
        assert strategy.generate_signal(mutated, i, "TEST") is None


def test_strategy_ignores_future_bars():
    series = _series(n=260, breakout_at=150)
    target_index = 200
    strategy = BreakoutSignalStrategy("A_raw_breakout")

    signal_before = strategy.generate_signal(series, target_index, "TEST")

    mutated = series.copy()
    future_rows = mutated.index[target_index + 1 :]
    mutated.loc[future_rows, "donchian_high_20"] = 999999.0
    mutated.loc[future_rows, "close"] = 1.0

    signal_after = strategy.generate_signal(mutated, target_index, "TEST")

    if signal_before is None:
        assert signal_after is None
    else:
        assert signal_after is not None
        assert signal_before.model_dump() == signal_after.model_dump()


# --- run_universe_breakout_experiment --------------------------------------------


@pytest.fixture
def _fake_breakout_universe_provider(monkeypatch):
    from market.data_provider import MarketDataError

    class _Provider:
        def __init__(self, good_symbols):
            self._good = good_symbols

        def fetch_ohlcv(self, symbol, *, period="5y", interval="1d"):
            if symbol not in self._good:
                raise MarketDataError(f"no data for {symbol}")
            return _ohlcv(260, breakout_at=150, volume_pattern=lambda i: 1_000_000 * (1 + (i % 13) * 0.3))

    def _apply(good_symbols):
        import market.data_provider as market_data_provider_module

        monkeypatch.setattr(market_data_provider_module, "get_market_data_provider", lambda: _Provider(good_symbols))

        # Bypass the real on-disk cache entirely -- "AAA"/"BBB"/"BADSYMBOL"
        # are not real cached symbols, so a cache MISS would otherwise
        # WRITE a real file under data/market/ as a side effect (same
        # concern/fix established for every other universe-level
        # experiment test in this project).
        import backtesting.cache as cache_module

        monkeypatch.setattr(cache_module, "CachedMarketDataProvider", lambda inner: inner)

    return _apply


def test_run_universe_breakout_experiment_pools_across_symbols_and_candidates(_fake_breakout_universe_provider):
    _fake_breakout_universe_provider({"AAA", "BBB"})

    from quant_research.breakout_signal import UniverseBreakoutExperimentResult, run_universe_breakout_experiment

    result = run_universe_breakout_experiment(["AAA", "BBB"], initial_capital=100_000.0)

    assert isinstance(result, UniverseBreakoutExperimentResult)
    assert result.failed_symbols == {}
    assert set(result.development_trades) == set(CANDIDATES)
    assert set(result.validation_trades) == set(CANDIDATES)
    assert set(result.out_of_sample_trades) == set(CANDIDATES)
    for candidate_name in CANDIDATES:
        assert isinstance(result.development_trades[candidate_name], list)
        assert isinstance(result.validation_trades[candidate_name], list)
        assert isinstance(result.out_of_sample_trades[candidate_name], list)


def test_run_universe_breakout_experiment_isolates_a_failing_symbol(_fake_breakout_universe_provider):
    _fake_breakout_universe_provider({"AAA"})

    from quant_research.breakout_signal import run_universe_breakout_experiment

    result = run_universe_breakout_experiment(["AAA", "BADSYMBOL"], initial_capital=100_000.0)

    assert "BADSYMBOL" in result.failed_symbols
    assert "AAA" not in result.failed_symbols
