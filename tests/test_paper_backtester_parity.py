"""Regression lock for a real defect found via historical replay during
Phase 6's autonomous loop: PaperTradingEngine originally delayed a same-bar
entry+exit by one bar relative to the backtester (a newly-filled position
wasn't checked against the SAME bar's high/low that just filled it). Fixed
in paper/engine.py::process_bar. This test pins the fix down permanently —
paper trading and backtesting must produce IDENTICAL trades over the same
data, same strategy, same risk config (spec §3: "the paper engine and
backtester must use the same execution assumptions").
"""

import pytest

from backtesting.cache import CACHE_ROOT, CachedMarketDataProvider
from backtesting.engine import run_backtest
from market.data_provider import get_market_data_provider
from market.indicators import compute_indicator_series
from paper.engine import PaperTradingEngine
from paper.replay import replay_historical
from paper.store import PaperStore
from risk.config import RiskConfig
from strategy.baseline import TrendMomentumBaseline
from tests.conftest import make_bar, make_indicator_series

_AAPL_CACHE = CACHE_ROOT / "AAPL" / "1d.csv"


def _mixed_synthetic_series(n: int = 80):
    bars = []
    for i in range(n):
        if i % 6 == 0:
            bars.append(make_bar(close=100 + i, open=100 + i, high=101 + i, low=99 + i))
        else:
            bars.append(make_bar(sma_20=80.0, sma_50=90.0, close=100 + i, open=100 + i, high=101 + i, low=99 + i))
    return make_indicator_series(bars)


def _trade_business_key(t):
    return (t.entry_time, t.entry_price, t.exit_time, t.exit_price, t.quantity, round(t.net_pnl, 6), t.exit_reason.value)


def _run_both(indicator_series, symbol: str, risk_config: RiskConfig):
    bt_result = run_backtest(symbol=symbol, indicator_series=indicator_series, strategy=TrendMomentumBaseline(), risk_config=risk_config)

    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, risk_engine=_risk_engine(risk_config), initial_capital=100_000.0)
    replay_historical(engine, symbol=symbol, indicator_series=indicator_series, strategy=TrendMomentumBaseline())

    return bt_result, store


def _risk_engine(risk_config: RiskConfig):
    from risk.engine import RiskEngine

    return RiskEngine(risk_config)


def test_paper_engine_matches_the_backtester_exactly_on_synthetic_data():
    series = _mixed_synthetic_series()
    bt_result, store = _run_both(series, "TEST", RiskConfig())

    bt_keys = [_trade_business_key(t) for t in bt_result.trades]
    paper_keys = [_trade_business_key(t) for t in store.list_trades()]

    assert paper_keys == bt_keys
    assert abs(bt_result.final_equity - store.get_account().equity) < 1e-6


@pytest.mark.skipif(not _AAPL_CACHE.exists(), reason=f"No cached AAPL data at {_AAPL_CACHE}")
def test_paper_engine_matches_the_backtester_exactly_on_real_aapl_data():
    provider = CachedMarketDataProvider(get_market_data_provider())
    ohlcv = provider.fetch_ohlcv("AAPL", interval="1d")
    series = compute_indicator_series(ohlcv)

    bt_result, store = _run_both(series, "AAPL", RiskConfig())

    bt_keys = [_trade_business_key(t) for t in bt_result.trades]
    paper_keys = [_trade_business_key(t) for t in store.list_trades()]

    assert paper_keys == bt_keys
    assert abs(bt_result.final_equity - store.get_account().equity) < 1e-6
