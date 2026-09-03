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

    def __init__(self):
        self.subscribed: list[tuple[list[str], str]] = []
        self.closed = False
        self._connected = True
        self._queue: list[MarketBarEvent | object | None] = []
        self._raise_disconnected = False

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
