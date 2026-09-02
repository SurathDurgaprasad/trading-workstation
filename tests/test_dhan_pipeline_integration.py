"""Phase 15 §23 integration tests: DhanMarketDataSource -> the EXISTING,
UNCHANGED LiveSimPipeline (Phase 12/13). Proves the substitution-at-the-
edges promise holds: swapping MockMarketDataSource for DhanMarketDataSource
requires zero changes to LiveSimPipeline's own logic (beyond the NO_NEW_BAR
fix, which benefits both sources identically).

Uses the fake-transport injection from test_dhan_market_data_source.py's
own pattern -- no real network, no credentials.
"""
import struct
from datetime import datetime, timezone

import pandas as pd
import pytest

from live.contracts import FeedDisconnectedError
from live.dhan.config import DhanCredentials
from live.dhan.instruments import DhanInstrumentMap
from live.dhan.market_data_source import DhanConnectionState, DhanMarketDataSource
from live.freshness import FreshnessPolicy
from live.pipeline import LiveSimPipeline
from market.data_provider import DataSource, DataStatus
from paper.engine import PaperTradingEngine
from paper.store import PaperStore
from strategy.baseline import TrendMomentumBaseline

_FIXTURE_CSV = """SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_INSTRUMENT_NAME,SEM_EXPIRY_CODE,SEM_TRADING_SYMBOL,SEM_LOT_UNITS,SEM_CUSTOM_SYMBOL,SEM_EXPIRY_DATE,SEM_STRIKE_PRICE,SEM_OPTION_TYPE,SEM_TICK_SIZE,SEM_EXPIRY_FLAG,SEM_EXCH_INSTRUMENT_TYPE,SEM_SERIES,SM_SYMBOL_NAME
NSE,E,2885,EQUITY,0,RELIANCE,1.0,Reliance Industries,,,,10.0000,NA,ES,EQ,RELIANCE INDUSTRIES LTD
"""


class _FakeTransport:
    """Auto-fires on_open on connect() (a successful handshake), matching
    test_dhan_market_data_source.py's fake -- these integration tests exist
    to exercise the pipeline above the transport, not the handshake itself
    (see that file's Phase 16 on_open lifecycle fix for why this exists)."""

    def __init__(self):
        self.sent_messages = []
        self._on_open = None
        self._on_message = None
        self._on_close = None

    def connect(self, url, *, on_open, on_message, on_close, on_error):
        self._on_open = on_open
        self._on_message = on_message
        self._on_close = on_close
        self._on_open()

    def send_json(self, message):
        self.sent_messages.append(message)

    def close(self):
        pass

    def simulate_message(self, data: bytes):
        self._on_message(data)


class _FakeTransportFactory:
    def __init__(self):
        self.instances = []

    def __call__(self):
        transport = _FakeTransport()
        self.instances.append(transport)
        return transport

    @property
    def current(self):
        return self.instances[-1]


_BASE_EPOCH = int(datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc).timestamp())  # near the pipelines' clock=2026-09-01 fixture below


def _ticker_packet(security_id: int, price: float, epoch: int) -> bytes:
    header = struct.pack("<BhBi", 2, 16, 1, security_id)
    body = struct.pack("<fi", price, epoch)
    return header + body


@pytest.fixture
def instrument_map():
    import io

    return DhanInstrumentMap(pd.read_csv(io.StringIO(_FIXTURE_CSV), dtype=str, keep_default_na=False))


@pytest.fixture
def dhan_pipeline(instrument_map):
    credentials = DhanCredentials(client_id="1000000001", access_token="fake-token")
    factory = _FakeTransportFactory()
    source = DhanMarketDataSource(
        credentials=credentials, instrument_map=instrument_map, interval="1m",
        transport_factory=factory, next_bar_timeout_seconds=0.2,
    )
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    # A generous freshness multiplier + a fixed clock close to "now" (ticks
    # use small epoch offsets in these tests, not real wall-clock time).
    pipeline = LiveSimPipeline(
        source=source, engine=engine, strategy=TrendMomentumBaseline(), symbols=["RELIANCE.NS"], interval="1m",
        freshness_policy=FreshnessPolicy(multiplier=1_000_000.0), clock=lambda: datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    return pipeline, source, factory, store


def test_a_dhan_bar_is_tagged_correctly_through_the_unchanged_pipeline(dhan_pipeline):
    pipeline, source, factory, store = dhan_pipeline
    factory.current.simulate_message(_ticker_packet(2885, 1400.0, epoch=_BASE_EPOCH + 0))
    factory.current.simulate_message(_ticker_packet(2885, 1401.0, epoch=_BASE_EPOCH + 61))  # completes the first 1m bar

    result = pipeline.process_next()
    assert result.kind == "BAR_PROCESSED"
    assert result.bar.source == DataSource.DHAN
    assert result.bar.status == DataStatus.LIVE
    assert result.symbol == "RELIANCE.NS"


def test_no_new_data_does_not_stop_the_pipeline(dhan_pipeline):
    """The NO_NEW_BAR fix, proven end-to-end: polling a quiet Dhan feed
    must report NO_NEW_DATA, never FEED_EXHAUSTED (which would make the
    CLI/dashboard loop stop as if the feed had permanently ended)."""
    pipeline, source, factory, store = dhan_pipeline
    result = pipeline.process_next()
    assert result.kind == "NO_NEW_DATA"

    # and the pipeline is still fully usable afterward -- not stuck
    factory.current.simulate_message(_ticker_packet(2885, 1400.0, epoch=_BASE_EPOCH + 0))
    factory.current.simulate_message(_ticker_packet(2885, 1401.0, epoch=_BASE_EPOCH + 61))
    result2 = pipeline.process_next()
    assert result2.kind == "BAR_PROCESSED"


def test_stale_dhan_bar_suppresses_new_signals(dhan_pipeline, instrument_map):
    """Reuses the EXISTING FreshnessPolicy unchanged -- a Dhan bar
    timestamped far in the past (per the pipeline's clock) must be
    STALE_SIGNAL_SUPPRESSED, exactly like a stale mock bar."""
    credentials = DhanCredentials(client_id="1000000001", access_token="fake-token")
    factory = _FakeTransportFactory()
    source = DhanMarketDataSource(credentials=credentials, instrument_map=instrument_map, interval="1m", transport_factory=factory, next_bar_timeout_seconds=0.2)
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    # TIGHT freshness this time, and a clock far ahead of the ticks' epoch timestamps.
    pipeline = LiveSimPipeline(
        source=source, engine=engine, strategy=TrendMomentumBaseline(), symbols=["RELIANCE.NS"], interval="1m",
        freshness_policy=FreshnessPolicy(multiplier=2.0), clock=lambda: datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    factory.current.simulate_message(_ticker_packet(2885, 1400.0, epoch=60))  # epoch 60 = 1970, wildly stale vs. clock=2026
    factory.current.simulate_message(_ticker_packet(2885, 1401.0, epoch=121))

    result = pipeline.process_next()
    assert result.kind == "STALE_SIGNAL_SUPPRESSED"


def test_duplicate_dhan_bar_is_skipped_by_the_existing_engine(dhan_pipeline, instrument_map):
    """Duplicate-bar protection lives in PaperTradingEngine.process_bar(),
    unchanged since Phase 12 -- proven here to apply identically to
    Dhan-sourced bars, not re-implemented.

    A single CandleBuilder can never "resend" an already-closed bucket (it
    only moves forward) -- so the realistic way this actually happens is a
    reconnect: a fresh DhanMarketDataSource (fresh CandleBuilder state)
    resubscribes and happens to redeliver a bar for a bucket the engine
    already processed. That's exactly what this test simulates."""
    pipeline, source, factory, store = dhan_pipeline
    factory.current.simulate_message(_ticker_packet(2885, 1400.0, epoch=_BASE_EPOCH + 0))
    factory.current.simulate_message(_ticker_packet(2885, 1401.0, epoch=_BASE_EPOCH + 61))
    first = pipeline.process_next()
    assert first.kind == "BAR_PROCESSED"

    # Simulate a reconnect: a brand new source/CandleBuilder, same engine,
    # replaying the identical first bucket.
    credentials = DhanCredentials(client_id="1000000001", access_token="fake-token")
    new_factory = _FakeTransportFactory()
    new_source = DhanMarketDataSource(credentials=credentials, instrument_map=instrument_map, interval="1m", transport_factory=new_factory, next_bar_timeout_seconds=0.2)
    pipeline.source = new_source
    new_source.subscribe(["RELIANCE.NS"], "1m")
    new_factory.current.simulate_message(_ticker_packet(2885, 1400.0, epoch=_BASE_EPOCH + 0))
    new_factory.current.simulate_message(_ticker_packet(2885, 1401.0, epoch=_BASE_EPOCH + 61))
    second = pipeline.process_next()
    assert second.kind == "DUPLICATE_SKIPPED"


def test_processing_a_dhan_bar_writes_feed_status_for_the_dashboard(instrument_map):
    """Phase 15 §7/§22: a separate process (the dashboard) can only know
    the feed's real status via LiveStateStore.feed_status -- proven here
    written correctly the moment a real bar is processed."""
    from live.state_store import LiveStateStore

    credentials = DhanCredentials(client_id="1000000001", access_token="fake-token")
    factory = _FakeTransportFactory()
    source = DhanMarketDataSource(credentials=credentials, instrument_map=instrument_map, interval="1m", transport_factory=factory, next_bar_timeout_seconds=0.2)
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    state_store = LiveStateStore(":memory:")
    pipeline = LiveSimPipeline(
        source=source, engine=engine, strategy=TrendMomentumBaseline(), symbols=["RELIANCE.NS"], interval="1m",
        freshness_policy=FreshnessPolicy(multiplier=1_000_000.0), clock=lambda: datetime(2026, 9, 1, tzinfo=timezone.utc),
        state_store=state_store,
    )
    assert state_store.get_feed_status("RELIANCE.NS") is None  # nothing yet

    factory.current.simulate_message(_ticker_packet(2885, 1400.0, epoch=_BASE_EPOCH + 0))
    factory.current.simulate_message(_ticker_packet(2885, 1401.0, epoch=_BASE_EPOCH + 61))
    result = pipeline.process_next()
    assert result.kind == "BAR_PROCESSED"

    record = state_store.get_feed_status("RELIANCE.NS")
    assert record is not None
    assert record.source == "DHAN"
    assert record.status == "LIVE"
    assert record.connection_state == "CONNECTED"


def test_disconnect_with_reconnect_attempts_exhausted_reports_feed_disconnected(instrument_map):
    credentials = DhanCredentials(client_id="1000000001", access_token="fake-token")
    factory = _FakeTransportFactory()
    source = DhanMarketDataSource(
        credentials=credentials, instrument_map=instrument_map, interval="1m", transport_factory=factory,
        next_bar_timeout_seconds=0.1, max_reconnect_attempts=1, backoff_base_seconds=0.01, backoff_max_seconds=0.01,
    )
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    pipeline = LiveSimPipeline(source=source, engine=engine, strategy=TrendMomentumBaseline(), symbols=["RELIANCE.NS"], interval="1m")

    # Force every reconnect attempt to fail, then trigger the disconnect path.
    def _always_fail():
        raise ConnectionError("simulated Dhan outage")

    source._connect = _always_fail
    source._attempt_reconnect()
    assert source.state == DhanConnectionState.FAILED

    result = pipeline.process_next()
    assert result.kind == "FEED_DISCONNECTED"
