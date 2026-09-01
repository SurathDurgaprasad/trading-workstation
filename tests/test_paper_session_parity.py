"""Phase 7A §12/§18 — the mandatory critical test: the EXISTING Phase 6
replay_historical() driver vs. the NEW bar-by-bar PaperSession driver, over
identical data and configuration, must produce identical business results.
Both share the same per-bar step (paper.replay._process_series_bar), so this
test is really a regression lock proving that sharing actually holds and
will fail loudly the moment it doesn't.
"""

import pytest

from backtesting.cache import CACHE_ROOT, CachedMarketDataProvider
from market.indicators import compute_indicator_series
from paper.engine import PaperTradingEngine
from paper.reconciliation import reconcile
from paper.replay import replay_historical
from paper.session import PaperSession
from paper.store import PaperStore
from strategy.baseline import TrendMomentumBaseline
from tests.conftest import make_bar, make_indicator_series

_AAPL_CACHE = CACHE_ROOT / "AAPL" / "1d.csv"
_RELIANCE_CACHE = CACHE_ROOT / "RELIANCE.NS" / "1d.csv"


class _NoNetworkProvider:
    def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
        raise AssertionError(f"Session parity test attempted a live fetch for {symbol} — cache should have served this.")


def _cached_indicator_series(symbol: str):
    provider = CachedMarketDataProvider(_NoNetworkProvider())
    ohlcv = provider.fetch_ohlcv(symbol, interval="1d")
    return compute_indicator_series(ohlcv)


def _volatile_series(n: int = 60):
    bars = []
    for i in range(n):
        if i % 5 == 0:
            bars.append(make_bar(close=100 + (i % 20), open=100 + (i % 20), high=102 + (i % 20), low=97 + (i % 20)))
        else:
            bars.append(make_bar(sma_20=80.0, sma_50=90.0, close=100 + (i % 20), open=100 + (i % 20), high=102 + (i % 20), low=97 + (i % 20)))
    return make_indicator_series(bars)


def _business_state(store: PaperStore) -> dict:
    account = store.get_account()
    trades = store.list_trades()
    journal = store.list_journal_entries()
    return {
        "equity": account.equity,
        "trade_count": len(trades),
        "trade_business_values": sorted(
            (t.entry_price, t.exit_price, t.quantity, t.net_pnl, t.exit_reason.value) for t in trades
        ),
        "journal_outcomes": sorted(j.outcome.value for j in journal),
        "signal_count": len(journal),
    }


def _run_via_replay(series, symbol) -> dict:
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    replay_historical(engine, symbol=symbol, indicator_series=series, strategy=TrendMomentumBaseline())
    state = _business_state(store)
    report = reconcile(store)
    assert report.ok, report.issues
    return state


def _run_via_session(series, symbol) -> dict:
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    PaperSession(engine, symbol=symbol, indicator_series=series, strategy=TrendMomentumBaseline()).start().run_to_end()
    state = _business_state(store)
    report = reconcile(store)
    assert report.ok, report.issues
    return state


def test_synthetic_replay_and_session_produce_identical_results():
    series = _volatile_series(80)
    assert _run_via_replay(series, "TEST") == _run_via_session(series, "TEST")


@pytest.mark.skipif(not _AAPL_CACHE.exists(), reason=f"No cached AAPL data at {_AAPL_CACHE}")
def test_real_aapl_replay_and_session_produce_identical_results():
    series = _cached_indicator_series("AAPL")
    via_replay = _run_via_replay(series, "AAPL")
    via_session = _run_via_session(series, "AAPL")
    assert via_replay == via_session, f"replay={via_replay}\nsession={via_session}"
    print(f"\nAAPL parity: {via_replay['trade_count']} trades, {via_replay['signal_count']} signals both ways, equity {via_replay['equity']:.2f}")


@pytest.mark.skipif(not _RELIANCE_CACHE.exists(), reason=f"No cached RELIANCE.NS data at {_RELIANCE_CACHE}")
def test_real_reliance_replay_and_session_produce_identical_results():
    series = _cached_indicator_series("RELIANCE.NS")
    via_replay = _run_via_replay(series, "RELIANCE.NS")
    via_session = _run_via_session(series, "RELIANCE.NS")
    assert via_replay == via_session, f"replay={via_replay}\nsession={via_session}"
    print(f"\nRELIANCE.NS parity: {via_replay['trade_count']} trades, {via_replay['signal_count']} signals both ways, equity {via_replay['equity']:.2f}")
