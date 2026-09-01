"""Level 4 — the primary Phase 6 integration test (spec §25): real cached
historical OHLCV -> real indicators -> real strategy -> real RiskEngine ->
real PaperTradingEngine -> real Account -> real SQLite -> real Journal.
Nothing here is mocked. Strategy parameters are untouched (spec §30 — no
optimization). Skipped, not failed, if the cache from earlier phases isn't
present in this checkout.
"""

import pytest

from backtesting.cache import CACHE_ROOT, CachedMarketDataProvider
from market.data_provider import MarketDataError, get_market_data_provider
from market.indicators import compute_indicator_series
from paper.engine import PaperTradingEngine
from paper.reconciliation import reconcile
from paper.replay import replay_historical
from paper.store import PaperStore
from strategy.baseline import TrendMomentumBaseline

_AAPL_CACHE = CACHE_ROOT / "AAPL" / "1d.csv"
_RELIANCE_CACHE = CACHE_ROOT / "RELIANCE.NS" / "1d.csv"


class _NoNetworkProvider:
    def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
        raise AssertionError(f"Historical paper replay attempted a live fetch for {symbol} — cache should have served this.")


def _cached_indicator_series(symbol: str):
    provider = CachedMarketDataProvider(_NoNetworkProvider())
    ohlcv = provider.fetch_ohlcv(symbol, interval="1d")
    return compute_indicator_series(ohlcv)


@pytest.mark.skipif(not _AAPL_CACHE.exists(), reason=f"No cached AAPL data at {_AAPL_CACHE}")
def test_real_aapl_paper_replay_end_to_end():
    series = _cached_indicator_series("AAPL")
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)

    summary = replay_historical(engine, symbol="AAPL", indicator_series=series, strategy=TrendMomentumBaseline())

    assert summary.bars_processed == len(series)
    journal = store.list_journal_entries()
    assert len(journal) == summary.signals_submitted

    report = reconcile(store)
    assert report.ok, report.issues

    # Honest reporting, not cherry-picking: whatever happened, happened.
    trades = store.list_trades()
    print(f"\nAAPL paper replay: {len(journal)} signals, {len(trades)} trades, "
          f"final equity {store.get_account().equity:.2f}")


@pytest.mark.skipif(not _RELIANCE_CACHE.exists(), reason=f"No cached RELIANCE.NS data at {_RELIANCE_CACHE}")
def test_real_reliance_paper_replay_end_to_end():
    series = _cached_indicator_series("RELIANCE.NS")
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)

    summary = replay_historical(engine, symbol="RELIANCE.NS", indicator_series=series, strategy=TrendMomentumBaseline())

    assert summary.bars_processed == len(series)
    report = reconcile(store)
    assert report.ok, report.issues

    trades = store.list_trades()
    print(f"\nRELIANCE.NS paper replay: {summary.signals_submitted} signals, {len(trades)} trades, "
          f"final equity {store.get_account().equity:.2f}")


@pytest.mark.skipif(not _AAPL_CACHE.exists(), reason=f"No cached AAPL data at {_AAPL_CACHE}")
def test_real_aapl_paper_replay_is_reproducible():
    """Spec §17: same signals/approvals/rejections/trades/entries/exits/
    quantities/PnL/risk-decisions on repeat — random UUIDs may differ."""
    series = _cached_indicator_series("AAPL")

    def run_once():
        store = PaperStore(":memory:")
        engine = PaperTradingEngine(store, initial_capital=100_000.0)
        replay_historical(engine, symbol="AAPL", indicator_series=series, strategy=TrendMomentumBaseline())
        trades = store.list_trades()
        journal = store.list_journal_entries()
        return {
            "trade_count": len(trades),
            "trade_business_values": sorted(
                (t.entry_price, t.exit_price, t.quantity, t.net_pnl, t.exit_reason.value) for t in trades
            ),
            "journal_outcomes": sorted(j.outcome.value for j in journal),
            "final_equity": store.get_account().equity,
        }

    run_a = run_once()
    run_b = run_once()
    assert run_a == run_b


@pytest.mark.skipif(not _AAPL_CACHE.exists(), reason=f"No cached AAPL data at {_AAPL_CACHE}")
def test_real_aapl_paper_replay_is_llm_free():
    """The paper engine must work with Ollama completely unavailable (spec
    §18) — proven structurally, the same way Phase 3's backtester was: no
    LLM module gets imported anywhere in this call path."""
    import sys

    forbidden_already_imported = {
        name for name in sys.modules if name.split(".")[0] in {"langgraph", "langchain_ollama", "ollama"}
    }

    series = _cached_indicator_series("AAPL")
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    replay_historical(engine, symbol="AAPL", indicator_series=series, strategy=TrendMomentumBaseline())

    newly_imported = {
        name for name in sys.modules if name.split(".")[0] in {"langgraph", "langchain_ollama", "ollama"}
    } - forbidden_already_imported
    assert not newly_imported, f"Paper replay pulled in LLM modules: {newly_imported}"
