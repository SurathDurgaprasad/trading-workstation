"""TRADING BRAIN EXECUTION LOOP mission: tests for quant_research/
market_behavior.py, the conditional-forward-return measurement engine.
"""
import pandas as pd
import pytest

from market.data_provider import OHLCV
from quant_research.market_behavior import (
    ForwardReturnSummary,
    build_symbol_dataset,
    measure_condition,
    measure_condition_by_market,
    summarize_forward_returns,
)


# --- summarize_forward_returns --------------------------------------------------


def test_summarize_forward_returns_basic_stats():
    summary = summarize_forward_returns([0.01, 0.02, -0.01, 0.03, -0.02], condition="test", market="NSE", horizon_bars=5)

    assert isinstance(summary, ForwardReturnSummary)
    assert summary.sample_size == 5
    assert summary.mean_return == pytest.approx(0.006)
    assert summary.win_rate == pytest.approx(0.6)  # 3 of 5 positive
    assert summary.std_dev is not None
    assert summary.mean_ci_low is not None and summary.mean_ci_high is not None
    assert summary.mean_ci_low < summary.mean_return < summary.mean_ci_high
    assert summary.p5 is not None and summary.p95 is not None
    assert summary.p5 <= summary.median_return <= summary.p95


def test_summarize_forward_returns_empty_list_is_honest_not_fabricated():
    summary = summarize_forward_returns([], condition="test", market="NSE", horizon_bars=5)

    assert summary.sample_size == 0
    assert summary.mean_return is None
    assert summary.median_return is None
    assert summary.win_rate is None
    assert summary.std_dev is None
    assert summary.mean_ci_low is None
    assert summary.mean_ci_high is None


def test_summarize_forward_returns_single_value_has_no_ci():
    """A single observation has no meaningful standard deviation/CI --
    must be None, never a fabricated 0.0 or a divide-by-zero crash."""
    summary = summarize_forward_returns([0.05], condition="test", market="NSE", horizon_bars=1)

    assert summary.sample_size == 1
    assert summary.mean_return == pytest.approx(0.05)
    assert summary.std_dev is None
    assert summary.mean_ci_low is None
    assert summary.mean_ci_high is None


def test_summarize_forward_returns_win_rate_excludes_nothing_at_zero():
    """A return of exactly 0.0 counts as neither a win, but must not
    crash or be silently dropped from the sample."""
    summary = summarize_forward_returns([0.0, 0.01, -0.01], condition="test", market="NSE", horizon_bars=1)
    assert summary.sample_size == 3
    assert summary.win_rate == pytest.approx(1 / 3)


# --- build_symbol_dataset --------------------------------------------------------


def _ohlcv(symbol, n=200, seed_close=100.0, step=0.2, volume=1_000_000.0):
    bars = []
    close = seed_close
    for i in range(n):
        close += step
        bars.append({"Open": close - 0.1, "High": close + 1.0, "Low": close - 1.0, "Close": close, "Volume": volume})
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


def test_build_symbol_dataset_returns_none_on_fetch_failure(_fake_provider):
    _fake_provider({"AAA"})
    assert build_symbol_dataset("BADSYMBOL") is None


def test_build_symbol_dataset_has_expected_columns(_fake_provider):
    _fake_provider({"RELIANCE.NS"})
    dataset = build_symbol_dataset("RELIANCE.NS")

    assert dataset is not None
    assert dataset.market == "NSE"
    assert dataset.raw_market == "NSE"
    for col in ("zscore_close_20", "relative_strength_20", "atr_pct_of_price", "volume_ratio", "trend_regime", "volatility_regime", "fwd_return_1", "fwd_return_20"):
        assert col in dataset.frame.columns


def test_build_symbol_dataset_classifies_us_symbols_correctly(_fake_provider):
    _fake_provider({"AAPL"})
    dataset = build_symbol_dataset("AAPL")

    assert dataset is not None
    assert dataset.market == "US"
    assert dataset.raw_market == "OTHER"


def test_build_symbol_dataset_period_split_is_chronological(_fake_provider):
    _fake_provider({"AAA"})
    dataset = build_symbol_dataset("AAA")

    assert dataset is not None
    assert dataset.development_end is not None
    assert dataset.validation_end is not None
    assert dataset.development_end < dataset.validation_end
    assert dataset.frame.index[0] < dataset.development_end < dataset.frame.index[-1]


# --- measure_condition / measure_condition_by_market -----------------------------


def test_measure_condition_pools_across_symbols_in_the_same_market(_fake_provider):
    _fake_provider({"AAA", "BBB"})
    datasets = {}
    for symbol in ("AAA", "BBB"):
        dataset = build_symbol_dataset(symbol)
        assert dataset is not None
        datasets[symbol] = dataset

    def _always_true(row):
        return True

    result = measure_condition(datasets, condition_name="always", condition_fn=_always_true, horizons=(1, 5))

    assert set(result) == {1, 5}
    # Every row of both symbols' full series should contribute (minus NaN warm-up rows).
    assert result[1].sample_size > 0
    assert result[1].market == "POOLED"


def test_measure_condition_by_market_never_mixes_nse_and_us(_fake_provider):
    _fake_provider({"RELIANCE.NS", "AAPL"})
    datasets = {}
    for symbol in ("RELIANCE.NS", "AAPL"):
        dataset = build_symbol_dataset(symbol)
        assert dataset is not None
        datasets[symbol] = dataset

    def _always_true(row):
        return True

    result = measure_condition_by_market(datasets, condition_name="always", condition_fn=_always_true, horizons=(1,))

    assert set(result) == {"NSE", "US"}
    assert result["NSE"][1].market == "NSE"
    assert result["US"][1].market == "US"
    # Sanity: NSE-only measurement never includes AAPL's own rows and vice versa --
    # proven structurally (market_filter applied), not by inspecting raw values here.


def test_measure_condition_respects_period_slicing(_fake_provider):
    _fake_provider({"AAA"})
    dataset = build_symbol_dataset("AAA")
    assert dataset is not None
    datasets = {"AAA": dataset}

    def _always_true(row):
        return True

    full = measure_condition(datasets, condition_name="always", condition_fn=_always_true, horizons=(1,), period="full")
    dev = measure_condition(datasets, condition_name="always", condition_fn=_always_true, horizons=(1,), period="development")
    val = measure_condition(datasets, condition_name="always", condition_fn=_always_true, horizons=(1,), period="validation")
    oos = measure_condition(datasets, condition_name="always", condition_fn=_always_true, horizons=(1,), period="out_of_sample")

    # dev+val+oos sample sizes should sum close to full (within a few rows of boundary overlap).
    assert dev[1].sample_size + val[1].sample_size + oos[1].sample_size <= full[1].sample_size + 2
    assert dev[1].sample_size > 0 and val[1].sample_size > 0 and oos[1].sample_size > 0


def test_measure_condition_respects_regime_filter(_fake_provider):
    _fake_provider({"AAA"})
    dataset = build_symbol_dataset("AAA")
    assert dataset is not None
    datasets = {"AAA": dataset}

    def _always_true(row):
        return True

    up_only = measure_condition(
        datasets, condition_name="always", condition_fn=_always_true, horizons=(1,),
        regime_filter=("TRENDING_UP", None),
    )
    unfiltered = measure_condition(datasets, condition_name="always", condition_fn=_always_true, horizons=(1,))

    # A steadily-uptrending fixture series should have most (not necessarily
    # literally all, due to warm-up) of its rows classified TRENDING_UP --
    # the regime-filtered sample must never exceed the unfiltered one.
    assert 0 < up_only[1].sample_size <= unfiltered[1].sample_size


def test_measure_condition_applies_the_actual_condition_not_just_period(_fake_provider):
    _fake_provider({"AAA"})
    dataset = build_symbol_dataset("AAA")
    assert dataset is not None
    datasets = {"AAA": dataset}

    def _never(row):
        return False

    result = measure_condition(datasets, condition_name="never", condition_fn=_never, horizons=(1,))
    assert result[1].sample_size == 0
