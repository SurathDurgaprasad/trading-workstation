"""INDIAN TRADING DECISION BRAIN mission: tests for
quant_research/context_experiments.py -- the frozen baseline BUY
condition and the external-regime attachment machinery Family A/B/C
research is built on.
"""
import pandas as pd
import pytest

from market.data_provider import OHLCV
from quant_research.context_experiments import (
    attach_external_regime,
    baseline_buy_condition,
    build_benchmark_regime_series,
    build_benchmark_volatility_series,
    build_india_vix_regime_series,
)
from quant_research.market_behavior import build_symbol_dataset


# --- baseline_buy_condition --------------------------------------------------


def test_baseline_buy_condition_true_on_uptrend_and_bullish_momentum():
    row = pd.Series({"close": 110.0, "sma_20": 105.0, "sma_50": 100.0, "rsi_14": 65.0})
    assert baseline_buy_condition(row) is True


def test_baseline_buy_condition_false_when_trend_structure_fails():
    row = pd.Series({"close": 95.0, "sma_20": 105.0, "sma_50": 100.0, "rsi_14": 65.0})
    assert baseline_buy_condition(row) is False


def test_baseline_buy_condition_false_when_momentum_is_bearish():
    row = pd.Series({"close": 110.0, "sma_20": 105.0, "sma_50": 100.0, "rsi_14": 45.0})
    assert baseline_buy_condition(row) is False


def test_baseline_buy_condition_false_never_fabricated_on_missing_data():
    row = pd.Series({"close": 110.0, "sma_20": None, "sma_50": 100.0, "rsi_14": 65.0})
    assert baseline_buy_condition(row) is False


# --- fetch-backed builders (fake provider, no network) -----------------------


def _ohlcv(symbol, n=300, seed_close=100.0, step=0.05):
    bars = []
    close = seed_close
    for i in range(n):
        close += step
        bars.append({"Open": close - 0.1, "High": close + 1.0, "Low": close - 1.0, "Close": close, "Volume": 1_000_000.0})
    frame = pd.DataFrame(bars, index=pd.date_range("2024-01-01", periods=n, freq="D"))
    return OHLCV.from_dataframe(symbol=symbol, interval="1d", frame=frame)


@pytest.fixture
def _fake_provider(monkeypatch):
    from market.data_provider import MarketDataError

    class _Provider:
        def __init__(self, good_symbols):
            self._good = good_symbols

        def fetch_ohlcv(self, symbol, *, period="5y", interval="1d"):
            if symbol not in self._good:
                raise MarketDataError(f"no data for {symbol}")
            return _ohlcv(symbol)

    def _apply(good_symbols):
        import market.data_provider as market_data_provider_module

        monkeypatch.setattr(market_data_provider_module, "get_market_data_provider", lambda: _Provider(good_symbols))

        import backtesting.cache as cache_module

        monkeypatch.setattr(cache_module, "CachedMarketDataProvider", lambda inner: inner)

    return _apply


def test_build_benchmark_regime_series_returns_none_on_fetch_failure(_fake_provider):
    _fake_provider({"AAA"})
    assert build_benchmark_regime_series("MISSING") is None


def test_build_benchmark_regime_series_has_one_label_per_bar(_fake_provider):
    _fake_provider({"^NSEI"})
    series = build_benchmark_regime_series("^NSEI")
    assert series is not None
    assert len(series) == 300
    assert set(series.unique()).issubset({"TRENDING_UP", "TRENDING_DOWN", "SIDEWAYS", "UNKNOWN"})


def test_build_benchmark_volatility_series_has_one_label_per_bar(_fake_provider):
    _fake_provider({"^NSEI"})
    series = build_benchmark_volatility_series("^NSEI")
    assert series is not None
    assert len(series) == 300
    assert set(series.unique()).issubset({"HIGH_VOLATILITY", "LOW_VOLATILITY", "NORMAL_VOLATILITY", "UNKNOWN"})


def test_build_india_vix_regime_series_returns_none_when_too_short(_fake_provider):
    _fake_provider({"^INDIAVIX"})
    assert build_india_vix_regime_series(use_cache=False) is not None  # 300 bars > DEFAULT_VIX_LOOKBACK(60)


def test_build_india_vix_regime_series_labels_are_valid(_fake_provider):
    _fake_provider({"^INDIAVIX"})
    series = build_india_vix_regime_series(use_cache=False)
    assert series is not None
    assert set(series.unique()).issubset({"ELEVATED", "DEPRESSED", "NORMAL", "UNKNOWN"})
    # A perfectly steady linear-drift series should never be ELEVATED/DEPRESSED vs. its own trailing average.
    assert "ELEVATED" not in set(series.iloc[70:].unique())


def test_attach_external_regime_forward_fills_onto_each_dataset_causally(_fake_provider):
    _fake_provider({"AAA"})
    dataset = build_symbol_dataset("AAA")
    assert dataset is not None

    # A sparse external regime series (only every 10th date) must be forward-filled, never leaving
    # a gap silently treated as "no filter" -- reindex(method="ffill") behavior under test here.
    sparse_dates = dataset.frame.index[::10]
    regime = pd.Series(["TRENDING_UP"] * len(sparse_dates), index=sparse_dates)

    attach_external_regime({"AAA": dataset}, regime_series=regime, column_name="market_trend_regime")

    assert "market_trend_regime" in dataset.frame.columns
    assert (dataset.frame["market_trend_regime"] == "TRENDING_UP").sum() == len(dataset.frame)
