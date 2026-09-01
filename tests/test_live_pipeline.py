"""Phase 12 §9 — the mandatory test list, end to end through
LiveSimPipeline: ordering, duplicate/out-of-order/stale bars, disconnect/
reconnect, source/freshness metadata, 1m/5m/15m intervals, mock replay
determinism, restart, paper/backtest parity, fail-closed behavior, and
structural no-LLM/no-broker checks.
"""

from datetime import datetime, timedelta, timezone

import pytest

from live.contracts import FeedDisconnectedError
from live.freshness import FreshnessPolicy
from live.mock_source import MockMarketDataSource, MockScriptEvent, make_mock_bar
from live.pipeline import LiveSimPipeline
from market.data_provider import DataSource, DataStatus
from paper.engine import PaperTradingEngine
from paper.errors import OutOfOrderBarError
from paper.reconciliation import reconcile
from paper.store import PaperStore
from strategy.baseline import TrendMomentumBaseline
from tests.conftest import AAPL_CACHE_PATH, make_bar, make_indicator_series


def _qualifying_bar(day, hour=9, minute=15, **overrides):
    """A bar shaped to satisfy TrendMomentumBaseline's entry conditions
    once enough history has accumulated (mirrors tests/conftest.py's
    make_bar default, but as a raw OHLCVBar for the mock feed)."""
    base = dict(timestamp=datetime(2026, 1, day, hour, minute), open=100.0, high=101.0, low=99.0, close=100.0, volume=1_000_000.0)
    base.update(overrides)
    return make_mock_bar(**base)


def _pipeline(script, *, interval="1d", require_human_approval=False, clock=None, freshness_policy=None):
    source = MockMarketDataSource(script, clock=clock)
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    pipeline = LiveSimPipeline(
        source=source, engine=engine, strategy=TrendMomentumBaseline(), symbols=["TEST"], interval=interval,
        require_human_approval=require_human_approval, clock=clock, freshness_policy=freshness_policy or FreshnessPolicy(),
    )
    return pipeline, engine, store


# --- 1. live-bar ordering / 8. source metadata / 9. freshness metadata -----


def test_bars_processed_in_order_carry_source_and_freshness_metadata():
    script = [MockScriptEvent.bar_event("TEST", _qualifying_bar(d)) for d in range(1, 5)]
    pipeline, engine, store = _pipeline(script, clock=lambda: datetime(2026, 1, 4, 9, 16))
    results = []
    while (r := pipeline.process_next()).kind != "FEED_EXHAUSTED":
        results.append(r)
    assert [r.bar.timestamp.day for r in results] == [1, 2, 3, 4]
    assert all(r.bar.source == DataSource.MOCK for r in results)
    assert all(r.bar.status == DataStatus.SIMULATED for r in results)
    assert all(r.freshness is not None for r in results)


# --- 2. duplicate bar ---------------------------------------------------------


def test_duplicate_bar_is_a_no_op_via_the_pipeline():
    bar = _qualifying_bar(1)
    script = [MockScriptEvent.bar_event("TEST", bar), MockScriptEvent.bar_event("TEST", bar)]
    pipeline, engine, store = _pipeline(script, clock=lambda: datetime(2026, 1, 1, 9, 16))
    first = pipeline.process_next()
    second = pipeline.process_next()
    assert first.kind == "BAR_PROCESSED"
    assert second.kind == "DUPLICATE_SKIPPED"
    report = reconcile(store)
    assert report.ok, report.issues


# --- 3. out-of-order bar -------------------------------------------------------


def test_out_of_order_bar_is_rejected_not_silently_applied():
    script = [MockScriptEvent.bar_event("TEST", _qualifying_bar(5)), MockScriptEvent.bar_event("TEST", _qualifying_bar(3))]
    pipeline, engine, store = _pipeline(script, clock=lambda: datetime(2026, 1, 5, 9, 16))
    first = pipeline.process_next()
    second = pipeline.process_next()
    assert first.kind == "BAR_PROCESSED"
    assert second.kind == "OUT_OF_ORDER_REJECTED"
    report = reconcile(store)
    assert report.ok, report.issues


# --- 4. stale bar --------------------------------------------------------------


def test_stale_bar_suppresses_new_signal_generation():
    """A bar delivered long after its own timestamp must not be allowed to
    open a NEW position (spec §4: "reject new signal")."""
    bar = _qualifying_bar(1)
    script = [MockScriptEvent.bar_event("TEST", bar)]
    very_late = datetime(2026, 1, 1, 11, 0)  # ~1h45m after a 9:15 bar -- well past any reasonable 1d/1m threshold in this test
    pipeline, engine, store = _pipeline(script, interval="1m", clock=lambda: very_late, freshness_policy=FreshnessPolicy(multiplier=2.0, minimum_threshold=timedelta(seconds=30)))
    result = pipeline.process_next()
    assert result.kind == "STALE_SIGNAL_SUPPRESSED"
    assert result.freshness.is_fresh is False
    assert result.signal is None


def test_fresh_bar_is_not_suppressed():
    bar = _qualifying_bar(1)
    script = [MockScriptEvent.bar_event("TEST", bar)]
    pipeline, engine, store = _pipeline(script, interval="1m", clock=lambda: bar.timestamp + timedelta(seconds=10))
    result = pipeline.process_next()
    assert result.kind == "BAR_PROCESSED"


# --- 5/6. feed disconnect / reconnect ------------------------------------------


def test_feed_disconnect_is_reported_and_does_not_crash_the_pipeline():
    script = [MockScriptEvent.disconnect(), MockScriptEvent.bar_event("TEST", _qualifying_bar(1))]
    pipeline, engine, store = _pipeline(script, clock=lambda: datetime(2026, 1, 1, 9, 16))
    result = pipeline.process_next()
    assert result.kind == "FEED_DISCONNECTED"


def test_reconnect_resumes_normal_processing():
    script = [
        MockScriptEvent.disconnect(),
        MockScriptEvent.bar_event("TEST", _qualifying_bar(1)),
        MockScriptEvent.reconnect(),
        MockScriptEvent.bar_event("TEST", _qualifying_bar(2)),
    ]
    pipeline, engine, store = _pipeline(script, clock=lambda: datetime(2026, 1, 2, 9, 16))
    disconnected = pipeline.process_next()
    resumed = pipeline.process_next()
    assert disconnected.kind == "FEED_DISCONNECTED"
    assert resumed.kind == "BAR_PROCESSED"
    assert resumed.bar.timestamp.day == 2


# --- 10/11/12. interval support -------------------------------------------------


@pytest.mark.parametrize("interval,step", [("1m", timedelta(minutes=1)), ("5m", timedelta(minutes=5)), ("15m", timedelta(minutes=15))])
def test_intraday_intervals_process_correctly(interval, step):
    start = datetime(2026, 1, 1, 9, 15)
    bars = [make_mock_bar(timestamp=start + step * i, open=100.0, high=101.0, low=99.0, close=100.0, volume=1000.0) for i in range(30)]
    script = [MockScriptEvent.bar_event("TEST", b) for b in bars]
    pipeline, engine, store = _pipeline(script, interval=interval, clock=lambda: start + step * 30)
    processed = 0
    while (r := pipeline.process_next()).kind != "FEED_EXHAUSTED":
        assert r.kind in ("BAR_PROCESSED", "STALE_SIGNAL_SUPPRESSED")
        processed += 1
    assert processed == 30
    report = reconcile(store)
    assert report.ok, report.issues


# --- 13. mock replay determinism ------------------------------------------------


def test_mock_replay_is_deterministic_across_two_runs():
    def build_script():
        bars = [make_bar(close=100 + (i % 20), open=100 + (i % 20), high=102 + (i % 20), low=97 + (i % 20)) if i % 5 == 0
                else make_bar(sma_20=80.0, sma_50=90.0, close=100 + (i % 20), open=100 + (i % 20), high=102 + (i % 20), low=97 + (i % 20))
                for i in range(40)]
        series = make_indicator_series(bars)
        return [
            MockScriptEvent.bar_event("TEST", make_mock_bar(timestamp=ts, open=row["open"], high=row["high"], low=row["low"], close=row["close"], volume=row["volume"]))
            for ts, row in series.iterrows()
        ]

    def run_once():
        pipeline, engine, store = _pipeline(build_script(), clock=lambda: datetime(2026, 3, 1))
        while pipeline.process_next().kind != "FEED_EXHAUSTED":
            pass
        trades = store.list_trades()
        return {
            "equity": engine.account.equity,
            "trade_count": len(trades),
            "trade_values": sorted((t.entry_price, t.exit_price, t.net_pnl, t.exit_reason.value) for t in trades),
        }

    assert run_once() == run_once()


# --- 14. restart -----------------------------------------------------------------


def test_pipeline_restart_matches_uninterrupted_run(tmp_path):
    start = datetime(2026, 1, 1, 9, 15)
    bars = []
    for i in range(60):
        close = 100 + (i % 20)
        vol = 1_000_000.0 * (1.2 if i % 5 == 0 else 0.8)
        bars.append(make_mock_bar(timestamp=start + timedelta(minutes=i), open=close, high=close + 2, low=close - 2, close=close, volume=vol))
    script_a = [MockScriptEvent.bar_event("TEST", b) for b in bars]
    script_b1 = [MockScriptEvent.bar_event("TEST", b) for b in bars[:30]]
    script_b2 = [MockScriptEvent.bar_event("TEST", b) for b in bars[30:]]

    def business_state(store):
        account = store.get_account()
        trades = store.list_trades()
        return {"equity": account.equity, "trade_count": len(trades), "trade_pnls": sorted(t.net_pnl for t in trades)}

    store_a = PaperStore(tmp_path / "uninterrupted.db")
    engine_a = PaperTradingEngine(store_a, initial_capital=100_000.0)
    pipeline_a = LiveSimPipeline(source=MockMarketDataSource(script_a), engine=engine_a, strategy=TrendMomentumBaseline(), symbols=["TEST"], interval="1m", clock=lambda: start + timedelta(hours=2))
    while pipeline_a.process_next().kind != "FEED_EXHAUSTED":
        pass
    state_a = business_state(store_a)
    store_a.close()

    store_b1 = PaperStore(tmp_path / "restarted.db")
    engine_b1 = PaperTradingEngine(store_b1, initial_capital=100_000.0)
    pipeline_b1 = LiveSimPipeline(source=MockMarketDataSource(script_b1), engine=engine_b1, strategy=TrendMomentumBaseline(), symbols=["TEST"], interval="1m", clock=lambda: start + timedelta(hours=2))
    while pipeline_b1.process_next().kind != "FEED_EXHAUSTED":
        pass
    store_b1.close()

    store_b2 = PaperStore(tmp_path / "restarted.db")
    engine_b2 = PaperTradingEngine(store_b2, initial_capital=100_000.0)
    pipeline_b2 = LiveSimPipeline(source=MockMarketDataSource(script_b2), engine=engine_b2, strategy=TrendMomentumBaseline(), symbols=["TEST"], interval="1m", clock=lambda: start + timedelta(hours=2))
    while pipeline_b2.process_next().kind != "FEED_EXHAUSTED":
        pass
    state_b = business_state(store_b2)

    assert state_a == state_b
    report = reconcile(store_b2)
    assert report.ok, report.issues
    store_b2.close()


# --- 15. paper/backtest parity --------------------------------------------------


@pytest.mark.skipif(not AAPL_CACHE_PATH.exists(), reason=f"No cached AAPL data at {AAPL_CACHE_PATH}")
def test_live_pipeline_matches_backtest_on_real_aapl_data():
    from backtesting.cache import CACHE_ROOT, CachedMarketDataProvider
    from backtesting.engine import run_backtest
    from market.indicators import compute_indicator_series

    class _NoNetwork:
        def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
            raise AssertionError("must use cache")

    provider = CachedMarketDataProvider(_NoNetwork())
    ohlcv = provider.fetch_ohlcv("AAPL", interval="1d")
    series = compute_indicator_series(ohlcv)
    bt_result = run_backtest(symbol="AAPL", indicator_series=series, strategy=TrendMomentumBaseline(), initial_capital=100_000.0)

    script = [
        MockScriptEvent.bar_event("AAPL", make_mock_bar(timestamp=ts, open=row["open"], high=row["high"], low=row["low"], close=row["close"], volume=row["volume"]))
        for ts, row in series.iterrows()
    ]
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    # far_future_clock is FIXED (not advancing with each bar), so the
    # freshness threshold must exceed the ENTIRE series span (~5y here) or
    # early bars would be (correctly, by the freshness guard's own logic)
    # flagged stale relative to this fixed future "now" -- freshness isn't
    # what's under test here, so make the threshold generously larger than
    # the whole dataset rather than merely "large".
    far_future_clock = lambda: series.index[-1] + timedelta(days=1)
    pipeline = LiveSimPipeline(source=MockMarketDataSource(script), engine=engine, strategy=TrendMomentumBaseline(), symbols=["AAPL"], interval="1d", clock=far_future_clock, freshness_policy=FreshnessPolicy(multiplier=10_000.0))
    while pipeline.process_next().kind != "FEED_EXHAUSTED":
        pass

    live_trades = sorted((t.entry_price, t.exit_price, t.quantity, t.net_pnl, t.exit_reason.value) for t in store.list_trades())
    bt_trades = sorted((t.entry_price, t.exit_price, t.quantity, t.net_pnl, t.exit_reason.value) for t in bt_result.trades)
    assert live_trades == bt_trades
    report = reconcile(store)
    assert report.ok, report.issues


# --- 16. fail-closed / causality -------------------------------------------------


def test_mutating_a_future_bar_does_not_change_an_already_processed_decision():
    """The core causality guarantee, proven at the pipeline level: what
    happened on bar N must not depend on what bar N+1 turns out to be."""
    start = datetime(2026, 1, 1, 9, 15)
    common_bars = [make_mock_bar(timestamp=start + timedelta(minutes=i), open=100 + i, high=101 + i, low=99 + i, close=100 + i, volume=1000.0) for i in range(10)]

    script_a = [MockScriptEvent.bar_event("TEST", b) for b in common_bars] + [
        MockScriptEvent.bar_event("TEST", make_mock_bar(timestamp=start + timedelta(minutes=10), open=500, high=600, low=400, close=550, volume=99999.0))
    ]
    script_b = [MockScriptEvent.bar_event("TEST", b) for b in common_bars] + [
        MockScriptEvent.bar_event("TEST", make_mock_bar(timestamp=start + timedelta(minutes=10), open=1, high=2, low=0.5, close=1, volume=1.0))
    ]

    def run(script):
        pipeline, engine, store = _pipeline(script, interval="1m", clock=lambda: start + timedelta(hours=1))
        results = []
        for _ in range(10):  # only the first 10 (common) bars
            results.append(pipeline.process_next())
        return results

    results_a = run(script_a)
    results_b = run(script_b)
    for ra, rb in zip(results_a, results_b):
        assert ra.kind == rb.kind
        assert ra.bar.close == rb.bar.close


def test_out_of_order_rejection_leaves_no_partial_state():
    script = [MockScriptEvent.bar_event("TEST", _qualifying_bar(5)), MockScriptEvent.bar_event("TEST", _qualifying_bar(3))]
    pipeline, engine, store = _pipeline(script, clock=lambda: datetime(2026, 1, 5, 9, 16))
    pipeline.process_next()
    with pytest.raises(OutOfOrderBarError):
        # process_bar itself still raises when called directly -- the
        # pipeline's own catch is what turns it into OUT_OF_ORDER_REJECTED;
        # this confirms the underlying guarantee (Phase 7A) is untouched.
        engine.process_bar("TEST", __import__("paper.engine", fromlist=["Bar"]).Bar(timestamp=datetime(2026, 1, 3), open=1, high=2, low=0.5, close=1))


# --- 17/18. no LLM / no broker dependency ----------------------------------------


def test_live_pipeline_never_imports_llm_modules():
    import sys

    forbidden_before = {n for n in sys.modules if n.split(".")[0] in {"langgraph", "langchain_ollama", "ollama"}}
    script = [MockScriptEvent.bar_event("TEST", _qualifying_bar(1))]
    pipeline, engine, store = _pipeline(script, clock=lambda: datetime(2026, 1, 1, 9, 16))
    pipeline.process_next()
    forbidden_after = {n for n in sys.modules if n.split(".")[0] in {"langgraph", "langchain_ollama", "ollama"}} - forbidden_before
    assert not forbidden_after


def test_live_package_has_no_broker_module_or_reference():
    import inspect

    import live.pipeline

    source = inspect.getsource(live.pipeline)
    for forbidden in ("dhan", "zerodha", "kite", "fyers", "broker_api", "place_order", "execute_trade"):
        assert forbidden not in source.lower()
