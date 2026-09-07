"""No real network calls anywhere in this file -- every adapter is tested
against a fake implementing the exact same Protocol
(live.contracts.MarketDataSource / market.data_provider.MarketDataProvider)
the real Dhan/mock/Yahoo classes implement, matching this project's
established test convention (see tests/test_dhan_market_data_source.py).
"""

from datetime import datetime, timezone

import pytest

from live.contracts import NO_NEW_BAR, FeedDisconnectedError, MarketBarEvent
from market.data_provider import DataSource, DataStatus, MarketDataError, OHLCV, OHLCVBar
from market_data.adapters._streaming import StreamingSnapshotAdapter
from market_data.adapters.yahoo import YahooSnapshotAdapter
from market_data.quality import SourceStatus


# --- fakes -------------------------------------------------------------


class _FakeStreamingSource:
    """Matches live.contracts.MarketDataSource exactly."""

    def __init__(self, connect_after_calls: int | None = None):
        self.subscribed: list[tuple[list[str], str]] = []
        self.closed = False
        self._connected = True
        self._queue: list[MarketBarEvent | object | None] = []
        self._raise_disconnected = False
        self._connect_after_calls = connect_after_calls
        """LIVE SYSTEM HARDENING mission: simulates a real, ASYNCHRONOUS
        connection -- is_connected() returns False for this many calls,
        then True forever after, mirroring a real WebSocket handshake
        that completes a moment after subscribe() returns rather than
        instantly. None (default) preserves the original fake's
        always-whatever-was-set behavior."""
        self._is_connected_calls = 0
        if connect_after_calls is not None:
            self._connected = False

    def subscribe(self, symbols, interval):
        self.subscribed.append((list(symbols), interval))

    def queue_bar(self, symbol: str, bar: OHLCVBar):
        self._queue.append(MarketBarEvent(symbol=symbol, bar=bar))

    def next_bar(self):
        if self._raise_disconnected:
            raise FeedDisconnectedError("simulated disconnect")
        if self._queue:
            return self._queue.pop(0)
        return NO_NEW_BAR

    def is_connected(self):
        self._is_connected_calls += 1
        if self._connect_after_calls is not None and self._is_connected_calls > self._connect_after_calls:
            self._connected = True
        return self._connected

    def set_connected(self, value: bool):
        self._connected = value

    def unsubscribe(self, symbols=None):
        pass

    def close(self):
        self.closed = True


class _FakeProvider:
    def __init__(self, ohlcv: OHLCV | None = None, error: Exception | None = None):
        self._ohlcv = ohlcv
        self._error = error
        self.calls: list[tuple[str, str, str]] = []

    def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
        self.calls.append((symbol, period, interval))
        if self._error is not None:
            raise self._error
        return self._ohlcv


def _bar(ts: datetime, close: float = 100.0) -> OHLCVBar:
    return OHLCVBar(timestamp=ts, open=close, high=close, low=close, close=close, volume=10.0)


# --- StreamingSnapshotAdapter -------------------------------------------


def test_streaming_adapter_subscribes_lazily_on_first_snapshot_call():
    source = _FakeStreamingSource()
    adapter = StreamingSnapshotAdapter(source, interval="1m")
    assert source.subscribed == []

    adapter.get_snapshot("RELIANCE.NS")
    assert source.subscribed == [(["RELIANCE.NS"], "1m")]

    adapter.get_snapshot("RELIANCE.NS")  # second call must not re-subscribe
    assert source.subscribed == [(["RELIANCE.NS"], "1m")]


def test_streaming_adapter_returns_no_data_before_any_bar_arrives():
    source = _FakeStreamingSource()
    adapter = StreamingSnapshotAdapter(source, interval="1m")
    snapshot = adapter.get_snapshot("RELIANCE.NS")
    assert snapshot.latest_bar is None
    assert snapshot.health.status == SourceStatus.NO_DATA


def test_streaming_adapter_drains_and_caches_the_latest_bar():
    source = _FakeStreamingSource()
    now = datetime.now(timezone.utc)
    source.queue_bar("RELIANCE.NS", _bar(now, close=100.0))
    source.queue_bar("RELIANCE.NS", _bar(now, close=101.0))

    adapter = StreamingSnapshotAdapter(source, interval="1m")
    snapshot = adapter.get_snapshot("RELIANCE.NS")

    assert snapshot.latest_bar.close == 101.0  # the LATEST of the two queued bars
    assert snapshot.health.status == SourceStatus.HEALTHY


def test_streaming_adapter_reports_disconnected_but_keeps_the_last_cached_bar():
    source = _FakeStreamingSource()
    now = datetime.now(timezone.utc)
    source.queue_bar("RELIANCE.NS", _bar(now, close=100.0))
    adapter = StreamingSnapshotAdapter(source, interval="1m")
    adapter.get_snapshot("RELIANCE.NS")  # populate the cache while connected

    source.set_connected(False)
    snapshot = adapter.get_snapshot("RELIANCE.NS")
    assert snapshot.health.status == SourceStatus.DISCONNECTED
    assert snapshot.latest_bar.close == 100.0  # last known bar preserved, not discarded


def test_streaming_adapter_a_different_symbol_never_pollutes_another_symbols_cache():
    source = _FakeStreamingSource()
    now = datetime.now(timezone.utc)
    source.queue_bar("TCS.NS", _bar(now, close=3500.0))
    adapter = StreamingSnapshotAdapter(source, interval="1m")

    reliance_snapshot = adapter.get_snapshot("RELIANCE.NS")
    assert reliance_snapshot.latest_bar is None  # TCS's bar must not leak into RELIANCE's snapshot


def test_streaming_adapter_close_delegates_to_the_underlying_source():
    source = _FakeStreamingSource()
    adapter = StreamingSnapshotAdapter(source, interval="1m")
    adapter.close()
    assert source.closed is True


# --- StreamingSnapshotAdapter: warmup_seconds (LIVE SYSTEM HARDENING mission) --
#
# Real live-market finding: a real shadow-run reported "0/3 live quote
# overlays succeeded". Reproduced live (instrumented get_snapshot() calls
# against the real Dhan feed) and root-caused to a pure timing gap: a
# real WebSocket connection is asynchronous, and a freshly-subscribed
# symbol's first tick is not reliably available within a single,
# unbudgeted poll. Given a real, bounded warm-up wait, live data
# consistently succeeded. These tests prove the fix without any real
# network dependency, using a fake source that simulates the same
# asynchronous-connection shape.


def test_warmup_zero_by_default_reproduces_original_instant_behavior():
    # No warmup_seconds passed at all -- must be indistinguishable from
    # the pre-fix adapter: instant NO_DATA, no waiting.
    source = _FakeStreamingSource()
    adapter = StreamingSnapshotAdapter(source, interval="1m")
    import time as _time

    t0 = _time.monotonic()
    snapshot = adapter.get_snapshot("RELIANCE.NS")
    assert _time.monotonic() - t0 < 0.05  # effectively instant
    assert snapshot.health.status == SourceStatus.NO_DATA


def test_warmup_waits_for_an_asynchronous_connection_to_complete():
    # Source is not yet connected on the first couple of polls (a real
    # WebSocket handshake in flight) but has a bar queued and waiting --
    # a bounded warm-up wait must let the connection catch up rather
    # than giving up immediately as DISCONNECTED.
    source = _FakeStreamingSource(connect_after_calls=2)
    now = datetime.now(timezone.utc)
    source.queue_bar("RELIANCE.NS", _bar(now, close=1318.5))
    adapter = StreamingSnapshotAdapter(source, interval="1m", warmup_seconds=2.0, warmup_poll_seconds=0.02)

    snapshot = adapter.get_snapshot("RELIANCE.NS")

    assert snapshot.health.status == SourceStatus.HEALTHY
    assert snapshot.latest_bar.close == 1318.5


def test_warmup_gives_up_after_its_budget_and_reports_no_data():
    # Connection never completes within the budget -- must give up
    # cleanly (DISCONNECTED, since is_connected() never becomes True)
    # rather than hanging indefinitely.
    source = _FakeStreamingSource(connect_after_calls=10_000)  # effectively never, within this test's budget
    adapter = StreamingSnapshotAdapter(source, interval="1m", warmup_seconds=0.15, warmup_poll_seconds=0.02)
    import time as _time

    t0 = _time.monotonic()
    snapshot = adapter.get_snapshot("RELIANCE.NS")
    elapsed = _time.monotonic() - t0

    assert snapshot.health.status == SourceStatus.DISCONNECTED
    assert elapsed < 0.5  # bounded -- did not hang past its own budget by an unreasonable margin


def test_warmup_only_applies_to_a_symbols_own_first_call():
    # A second get_snapshot() call for an ALREADY-subscribed symbol must
    # not re-invoke the warm-up wait -- matches the existing "subscribe
    # lazily, only once" contract exactly.
    source = _FakeStreamingSource(connect_after_calls=10_000)
    adapter = StreamingSnapshotAdapter(source, interval="1m", warmup_seconds=0.15, warmup_poll_seconds=0.02)
    adapter.get_snapshot("RELIANCE.NS")  # pays the warm-up cost once

    import time as _time

    t0 = _time.monotonic()
    adapter.get_snapshot("RELIANCE.NS")  # must NOT pay it again
    assert _time.monotonic() - t0 < 0.05


# --- YahooSnapshotAdapter -------------------------------------------------


def test_yahoo_adapter_returns_the_latest_bar_healthy():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ohlcv = OHLCV(symbol="AAPL", interval="1d", bars=[_bar(now)])
    adapter = YahooSnapshotAdapter(_FakeProvider(ohlcv=ohlcv), period="5d", interval="1d")

    snapshot = adapter.get_snapshot("AAPL")
    assert snapshot.latest_bar is not None
    assert snapshot.health.status == SourceStatus.HEALTHY


def test_yahoo_adapter_reports_no_data_for_an_empty_result():
    ohlcv = OHLCV(symbol="AAPL", interval="1d", bars=[])
    adapter = YahooSnapshotAdapter(_FakeProvider(ohlcv=ohlcv))
    snapshot = adapter.get_snapshot("AAPL")
    assert snapshot.latest_bar is None
    assert snapshot.health.status == SourceStatus.NO_DATA


def test_yahoo_adapter_reports_error_without_raising():
    """A provider failure must surface as SourceHealth.error(), never
    propagate as a raw exception -- callers scanning many symbols should
    not have one bad symbol crash the whole scan."""
    adapter = YahooSnapshotAdapter(_FakeProvider(error=MarketDataError("no data returned for XYZ")))
    snapshot = adapter.get_snapshot("XYZ")
    assert snapshot.latest_bar is None
    assert snapshot.health.status == SourceStatus.ERROR
    assert "XYZ" in snapshot.health.detail


def test_yahoo_adapter_passes_period_and_interval_through_unchanged():
    provider = _FakeProvider(ohlcv=OHLCV(symbol="AAPL", interval="1wk", bars=[]))
    adapter = YahooSnapshotAdapter(provider, period="2y", interval="1wk")
    adapter.get_snapshot("AAPL")
    assert provider.calls == [("AAPL", "2y", "1wk")]


def test_yahoo_adapter_close_is_a_safe_no_op():
    YahooSnapshotAdapter(_FakeProvider()).close()  # must not raise
