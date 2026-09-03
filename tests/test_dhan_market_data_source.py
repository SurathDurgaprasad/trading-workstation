"""Phase 15 §23: DhanMarketDataSource, tested against a FAKE transport
(dependency-injected via `transport_factory`) -- no real network, no real
Dhan account, no credentials. The fake transport lets tests simulate
exactly the scenarios spec §23/§9/§10 asks for: malformed messages,
disconnects, reconnects, and the bounded-retry ceiling.
"""
import struct
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from live.contracts import NO_NEW_BAR, FeedDisconnectedError
from live.dhan.config import DhanCredentials
from live.dhan.instruments import DhanInstrumentMap
from live.dhan.market_data_source import DhanConnectionState, DhanMarketDataSource
from market.data_provider import DataSource, DataStatus

_FIXTURE_CSV = """SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_INSTRUMENT_NAME,SEM_EXPIRY_CODE,SEM_TRADING_SYMBOL,SEM_LOT_UNITS,SEM_CUSTOM_SYMBOL,SEM_EXPIRY_DATE,SEM_STRIKE_PRICE,SEM_OPTION_TYPE,SEM_TICK_SIZE,SEM_EXPIRY_FLAG,SEM_EXCH_INSTRUMENT_TYPE,SEM_SERIES,SM_SYMBOL_NAME
NSE,E,2885,EQUITY,0,RELIANCE,1.0,Reliance Industries,,,,10.0000,NA,ES,EQ,RELIANCE INDUSTRIES LTD
"""


class _FakeTransport:
    """`auto_open` defaults to True (a successful handshake) so existing
    tests -- which exercise post-connect behavior, not the handshake itself
    -- don't need to know about on_open at all. `auto_open=False` (Phase 16
    addition) reproduces the real scenario found against a real Dhan
    account: the connection errors/closes BEFORE on_open ever fires."""

    def __init__(self, auto_open: bool = True):
        self.auto_open = auto_open
        self.sent_messages = []
        self.closed = False
        self.url = None
        self._on_open = None
        self._on_message = None
        self._on_close = None
        self._on_error = None

    def connect(self, url, *, on_open, on_message, on_close, on_error):
        self.url = url
        self._on_open = on_open
        self._on_message = on_message
        self._on_close = on_close
        self._on_error = on_error
        if self.auto_open:
            self._on_open()

    def send_json(self, message):
        self.sent_messages.append(message)

    def close(self):
        self.closed = True

    def simulate_open(self):
        self._on_open()

    def simulate_message(self, data: bytes):
        self._on_message(data)

    def simulate_close(self, code=1000, reason="simulated"):
        self._on_close(code, reason)

    def simulate_error(self, error):
        self._on_error(error)


class _FakeTransportFactory:
    def __init__(self, auto_open: bool = True):
        self.auto_open = auto_open
        self.instances: list[_FakeTransport] = []

    def __call__(self):
        transport = _FakeTransport(auto_open=self.auto_open)
        self.instances.append(transport)
        return transport

    @property
    def current(self) -> _FakeTransport:
        return self.instances[-1]


@pytest.fixture
def instrument_map() -> DhanInstrumentMap:
    import io

    return DhanInstrumentMap(pd.read_csv(io.StringIO(_FIXTURE_CSV), dtype=str, keep_default_na=False))


@pytest.fixture
def credentials() -> DhanCredentials:
    return DhanCredentials(client_id="1000000001", access_token="fake-token-for-tests")


def _ticker_packet(security_id: int, price: float, epoch: int) -> bytes:
    header = struct.pack("<BhBi", 2, 16, 1, security_id)  # response_code=2 (Ticker), segment=1 (NSE_EQ)
    body = struct.pack("<fi", price, epoch)
    return header + body


def _disconnect_packet(reason_code: int) -> bytes:
    header = struct.pack("<BhBi", 50, 10, 0, 0)
    body = struct.pack("<h", reason_code)
    return header + body


def _source(instrument_map, credentials, **overrides) -> tuple[DhanMarketDataSource, _FakeTransportFactory]:
    factory = _FakeTransportFactory()
    source = DhanMarketDataSource(
        credentials=credentials, instrument_map=instrument_map, interval="1m",
        transport_factory=factory, next_bar_timeout_seconds=0.2, **overrides,
    )
    return source, factory


def test_subscribe_connects_and_sends_a_subscribe_message(instrument_map, credentials):
    source, factory = _source(instrument_map, credentials)
    source.subscribe(["RELIANCE.NS"], "1m")
    assert source.is_connected() is True
    assert len(factory.current.sent_messages) == 1
    message = factory.current.sent_messages[0]
    assert message["InstrumentList"] == [{"ExchangeSegment": "NSE_EQ", "SecurityId": "2885"}]


def test_subscribe_url_carries_credentials_as_query_params(instrument_map, credentials):
    source, factory = _source(instrument_map, credentials)
    source.subscribe(["RELIANCE.NS"], "1m")
    assert "token=fake-token-for-tests" in factory.current.url
    assert "clientId=1000000001" in factory.current.url


def test_subscribe_with_wrong_interval_raises(instrument_map, credentials):
    source, factory = _source(instrument_map, credentials)
    with pytest.raises(ValueError):
        source.subscribe(["RELIANCE.NS"], "5m")


def test_decode_last_trade_time_corrects_the_ist_labeled_as_utc_epoch():
    """Phase 16 fix (VERIFIED against a real account, 2026-09-03): a real
    tick's LTT, decoded the naive way (fromtimestamp(epoch, tz=UTC)),
    produced wall-clock digits matching the CURRENT IST time, not the
    current UTC time -- confirmed via an independent cross-check against
    Dhan's own real HTTP Date header (ruling out a local-clock artifact).
    _decode_last_trade_time must reinterpret those digits as IST and
    return the genuinely correct UTC instant, exactly 5:30 earlier."""
    # Dhan's raw wire value: the integer that, decoded naively as UTC, reads "10:07:00".
    raw_dhan_epoch = int(datetime(2026, 9, 3, 10, 7, 0, tzinfo=timezone.utc).timestamp())
    decoded = DhanMarketDataSource._decode_last_trade_time(raw_dhan_epoch)
    assert decoded == datetime(2026, 9, 3, 4, 37, 0, tzinfo=timezone.utc)  # true UTC equivalent of IST 10:07:00


def test_a_tick_with_a_real_time_equivalent_epoch_produces_a_bar_close_to_true_now(instrument_map, credentials):
    """End-to-end regression for the same fix: before it, a tick whose LTT
    reflected the genuine current moment would produce a bar timestamped
    ~5.5 hours in the FUTURE relative to true UTC now -- which silently
    broke FreshnessPolicy (a negative age is always <= any positive
    threshold, so every real Dhan bar was always judged "fresh" regardless
    of actual staleness). After the fix, a bar built from an epoch
    representing the real current moment must land close to true now."""
    source, factory = _source(instrument_map, credentials)
    source.subscribe(["RELIANCE.NS"], "1m")

    true_now_utc = datetime.now(timezone.utc)
    # Simulate Dhan's actual wire behavior: the raw epoch that decodes (naively, as UTC) to IST "now".
    ist_now = true_now_utc.astimezone(ZoneInfo("Asia/Kolkata")).replace(tzinfo=timezone.utc)
    raw_dhan_epoch_for_now = int(ist_now.timestamp())

    factory.current.simulate_message(_ticker_packet(2885, 1400.0, epoch=raw_dhan_epoch_for_now))
    # cross into the next bucket to force the bar closed and observable
    factory.current.simulate_message(_ticker_packet(2885, 1401.0, epoch=raw_dhan_epoch_for_now + 61))

    event = source.next_bar()
    assert event is not None
    age = abs((true_now_utc - event.bar.timestamp).total_seconds())
    assert age < 120, f"bar.timestamp should be close to true now, was off by {age}s (the pre-fix bug put it ~19800s / 5.5h away)"


def test_a_tick_that_completes_a_bar_is_delivered_via_next_bar(instrument_map, credentials):
    source, factory = _source(instrument_map, credentials)
    source.subscribe(["RELIANCE.NS"], "1m")
    factory.current.simulate_message(_ticker_packet(2885, 1428.5, epoch=60))
    factory.current.simulate_message(_ticker_packet(2885, 1430.0, epoch=121))  # crosses into the next 1m bucket

    event = source.next_bar()
    assert event is not None
    assert event.symbol == "RELIANCE.NS"
    assert event.bar.open == pytest.approx(1428.5)
    assert event.bar.source == DataSource.DHAN
    assert event.bar.status == DataStatus.LIVE


def test_next_bar_returns_no_new_bar_sentinel_on_timeout(instrument_map, credentials):
    """The Phase 14-identified gap, now fixed: "no new bar yet" must be
    distinct from both a permanent feed-ended signal (bare None) and a
    real bar -- NO_NEW_BAR, not an exception, not None."""
    source, factory = _source(instrument_map, credentials)
    source.subscribe(["RELIANCE.NS"], "1m")
    result = source.next_bar()
    assert result is NO_NEW_BAR
    assert result is not None
    assert source.is_connected() is True  # still connected -- just nothing completed yet


def test_malformed_message_is_dropped_without_crashing(instrument_map, credentials):
    source, factory = _source(instrument_map, credentials)
    source.subscribe(["RELIANCE.NS"], "1m")
    factory.current.simulate_message(b"\x02\x00")  # far too short to be any valid packet
    assert source.is_connected() is True  # the connection itself is unaffected
    assert source.next_bar() is NO_NEW_BAR  # and nothing bogus was queued


def test_message_for_an_unsubscribed_security_id_is_ignored(instrument_map, credentials):
    source, factory = _source(instrument_map, credentials)
    source.subscribe(["RELIANCE.NS"], "1m")
    factory.current.simulate_message(_ticker_packet(999999, 100.0, epoch=60))  # never subscribed
    assert source.next_bar() is NO_NEW_BAR


def test_duplicate_ticks_at_the_same_timestamp_do_not_each_complete_a_bar(instrument_map, credentials):
    source, factory = _source(instrument_map, credentials)
    source.subscribe(["RELIANCE.NS"], "1m")
    factory.current.simulate_message(_ticker_packet(2885, 100.0, epoch=10))
    factory.current.simulate_message(_ticker_packet(2885, 100.0, epoch=10))  # exact duplicate
    assert source.next_bar() is NO_NEW_BAR  # still the same bucket -- nothing completed


def test_out_of_order_tick_within_the_same_bucket_is_absorbed_not_rejected(instrument_map, credentials):
    """A tick that arrives slightly out of order but still within the
    current bucket is just another data point for that bucket -- Dhan
    ticks are trusted at this layer; true out-of-order/duplicate BAR
    protection happens downstream in the existing PaperTradingEngine,
    unchanged."""
    source, factory = _source(instrument_map, credentials)
    source.subscribe(["RELIANCE.NS"], "1m")
    factory.current.simulate_message(_ticker_packet(2885, 100.0, epoch=30))
    factory.current.simulate_message(_ticker_packet(2885, 99.0, epoch=10))  # earlier timestamp, same bucket
    factory.current.simulate_message(_ticker_packet(2885, 101.0, epoch=61))
    bar_event = source.next_bar()
    assert bar_event.bar.low == pytest.approx(99.0)


def test_disconnect_marks_reconnecting_then_reconnects_within_bound(instrument_map, credentials):
    source, factory = _source(instrument_map, credentials, max_reconnect_attempts=3, backoff_base_seconds=0.01, backoff_max_seconds=0.02)
    source.subscribe(["RELIANCE.NS"], "1m")
    factory.current.simulate_close(code=1006, reason="abnormal closure")
    # a fresh transport should have been created and re-subscribed
    assert len(factory.instances) == 2
    assert source.state in (DhanConnectionState.CONNECTED, DhanConnectionState.RECONNECTING)


def test_reconnect_attempts_are_bounded_then_the_feed_reports_disconnected(instrument_map, credentials):
    """Section 9: no infinite uncontrolled reconnect loop. Force every
    reconnect attempt to fail, and confirm the source gives up after
    max_reconnect_attempts rather than retrying forever."""
    source, factory = _source(instrument_map, credentials, max_reconnect_attempts=2, backoff_base_seconds=0.01, backoff_max_seconds=0.01)

    call_count = {"n": 0}
    original_connect = source._connect

    def _failing_connect():
        call_count["n"] += 1
        raise ConnectionError("simulated: Dhan server unreachable")

    source._connect = _failing_connect
    source.state = DhanConnectionState.CONNECTED  # pretend we were connected, then it dropped
    source._subscribed_symbols = {"RELIANCE.NS"}
    source._attempt_reconnect()

    assert source.state == DhanConnectionState.FAILED
    assert call_count["n"] == 2  # exactly max_reconnect_attempts, not unbounded

    with pytest.raises(FeedDisconnectedError):
        source.next_bar()


def test_subscribe_after_failed_resets_the_retry_budget(instrument_map, credentials):
    """Hardening finding (found via offline code review, no live network
    involved -- confirmed deterministically here): subscribe() calls
    _connect() directly when recovering from FAILED, bypassing the normal
    claim path that resets _reconnect_attempts on stability. Without a
    fix, a manual resubscribe after a permanent failure inherited the
    exhausted counter from the PREVIOUS episode and could fail permanently
    again after zero real retries on the very next drop."""
    source, factory = _source(instrument_map, credentials, max_reconnect_attempts=1, backoff_base_seconds=0.01, backoff_max_seconds=0.01)
    with source._lock:
        source.state = DhanConnectionState.FAILED
        source._reconnect_attempts = source.max_reconnect_attempts  # simulate an exhausted PREVIOUS episode

    source.subscribe(["RELIANCE.NS"], "1m")  # a fresh manual resubscribe after permanent failure
    assert source.state == DhanConnectionState.CONNECTED
    assert source._reconnect_attempts == 0  # budget reset -- not inherited from the old failed episode

    # prove it can actually survive a subsequent drop now, unlike before the fix
    factory.current.simulate_error("a drop after the fresh resubscribe")
    assert source.state == DhanConnectionState.CONNECTED  # reconnected -- had budget to do so


def test_connect_refuses_to_create_a_transport_if_already_closed(instrument_map, credentials):
    """Hardening fix, precise/white-box version (found via offline code
    review, no live network involved): _connect() now re-checks CLOSED
    under the lock before creating a transport -- this is the exact
    mechanism that closes the orphan-connection race between close() and
    an in-flight reconnect (see the coarser threaded test below for the
    end-to-end version of the same fix)."""
    source, factory = _source(instrument_map, credentials)
    source.state = DhanConnectionState.CLOSED
    source._connect()
    assert len(factory.instances) == 0  # no transport created -- close() wins even if _connect() is invoked anyway
    assert source.state == DhanConnectionState.CLOSED


def test_close_during_an_in_flight_reconnect_prevents_it_from_completing(instrument_map, credentials):
    """Hardening fix, end-to-end/threaded version (found via offline code
    review + a real-threading test, no live network involved): close()
    previously mutated state and read self._transport WITHOUT the lock, so
    a reconnect already past its own pre-check could race past a
    concurrent close() and open a fresh, un-tracked WebSocket anyway -- an
    orphan connection the caller believes is closed. close() now captures
    self._transport under the same lock it uses to set CLOSED, and
    _connect() re-checks CLOSED under that same lock immediately before
    creating a transport, so close() winning the race means no new
    transport is ever created."""
    source, factory = _source(
        instrument_map, credentials, max_reconnect_attempts=5,
        backoff_base_seconds=0.3, backoff_max_seconds=0.3,  # long enough to reliably close() during the sleep
    )
    source.subscribe(["RELIANCE.NS"], "1m")
    assert len(factory.instances) == 1

    thread = threading.Thread(target=factory.current.simulate_error, args=("drop",))
    thread.start()
    time.sleep(0.05)  # let the reconnect claim its attempt and enter the backoff sleep
    assert source.state == DhanConnectionState.RECONNECTING

    source.close()  # races in WHILE the reconnect is still sleeping
    thread.join(timeout=2.0)
    assert not thread.is_alive()

    assert source.state == DhanConnectionState.CLOSED
    assert len(factory.instances) == 1  # the in-flight reconnect must NOT have created a second (orphan) transport


def test_disconnect_reason_never_contains_the_raw_access_token(instrument_map, credentials):
    """Defense-in-depth (no evidence of an actual leak -- see
    _redact_secret's docstring): if a failure's reason text ever happened
    to embed the raw access token, it must never survive into
    _last_disconnect_reason (which flows into FeedDisconnectedError's
    message and onward into CLI/dashboard output)."""
    source, factory = _source(instrument_map, credentials)
    source.subscribe(["RELIANCE.NS"], "1m")
    factory.current.simulate_error(f"pretend leak: token={credentials.access_token} in this error message")
    assert credentials.access_token not in source._last_disconnect_reason
    assert "***" in source._last_disconnect_reason


def test_close_is_terminal_and_never_triggers_a_reconnect(instrument_map, credentials):
    source, factory = _source(instrument_map, credentials)
    source.subscribe(["RELIANCE.NS"], "1m")
    source.close()
    assert source.state == DhanConnectionState.CLOSED
    assert factory.current.closed is True

    factory.current.simulate_close(code=1000, reason="post-close noise")
    assert source.state == DhanConnectionState.CLOSED  # a stray close callback after close() must not resurrect it
    assert len(factory.instances) == 1  # no new transport was created


def test_handshake_failure_before_open_does_not_crash_and_triggers_reconnect(instrument_map, credentials):
    """Phase 16 (VERIFIED against a real account): connecting to the real
    Dhan feed produced 'Connection to remote host was lost' (no close code)
    roughly 0.5s after connect -- before on_open ever fired. Under the
    original design (CONNECTED declared the instant the background thread
    started), this crashed subscribe() with a raw
    WebSocketConnectionClosedException from inside send_json(). subscribe()
    must never raise here, must never report CONNECTED before a real
    on_open, and must route a pre-open failure through the same bounded
    reconnect path as any other disconnect."""
    factory = _FakeTransportFactory(auto_open=False)
    source = DhanMarketDataSource(
        credentials=credentials, instrument_map=instrument_map, interval="1m",
        transport_factory=factory, next_bar_timeout_seconds=0.2,
        max_reconnect_attempts=3, backoff_base_seconds=0.01, backoff_max_seconds=0.01,
    )
    source.subscribe(["RELIANCE.NS"], "1m")  # must not raise, even though on_open never fires
    assert source.state != DhanConnectionState.CONNECTED
    assert factory.current.sent_messages == []  # nothing sent to a socket that was never open

    factory.current.simulate_error("Connection to remote host was lost.")
    assert len(factory.instances) == 2  # a reconnect attempt was made
    # the reconnect's own transport also never opens (auto_open=False for the whole factory,
    # matching what was actually observed live) -- it should be attempting again, not CONNECTED
    # or dead, and it must not have raised.
    assert source.state == DhanConnectionState.CONNECTING


def test_a_send_failure_after_open_is_treated_as_a_disconnect_not_a_crash(instrument_map, credentials):
    """A narrower variant of the same real-world risk: the socket closes in
    the gap between on_open firing and send_json() actually writing to it.
    send_json() raising must not propagate out of subscribe()/_send_subscribe -- it must be treated as a disconnect."""
    source, factory = _source(instrument_map, credentials, max_reconnect_attempts=3, backoff_base_seconds=0.01, backoff_max_seconds=0.01)

    def _raising_send_json(message):
        raise ConnectionError("simulated: socket closed between open and send")

    source.subscribe(["RELIANCE.NS"], "1m")  # first subscribe succeeds via auto_open
    factory.current.send_json = _raising_send_json
    source._send_subscribe([("NSE_EQ", "2885")])  # must not raise
    assert len(factory.instances) == 2  # treated as a disconnect -> reconnect attempted


def test_error_then_close_for_the_same_failure_triggers_exactly_one_reconnect(instrument_map, credentials):
    """Phase 16 (VERIFIED against a real account -- a serious finding): a
    real WebSocketApp fires BOTH on_error and on_close for the same
    underlying failure. Before generation-tagged deduplication, each of
    those (plus send failures, plus server-sent Disconnect packets) called
    _attempt_reconnect() independently, causing an actual reconnect storm
    against the real Dhan feed -- dozens of connection attempts within
    ~15 seconds instead of the configured bound -- which got this
    project's Dhan client ID rate-limited ("429 Too Many Requests ...
    client id is blocked") by Dhan's own server. Exactly ONE reconnect
    must happen per real failure, however many redundant signals arrive
    for it."""
    source, factory = _source(instrument_map, credentials, max_reconnect_attempts=5, backoff_base_seconds=0.01, backoff_max_seconds=0.01)
    source.subscribe(["RELIANCE.NS"], "1m")
    assert len(factory.instances) == 1
    first_transport = factory.current  # captured before any reconnect -- the fake auto-opens synchronously,
    # so factory.current would otherwise already point at the NEW transport by the time simulate_close() runs.

    # Both signals fire for the SAME connection attempt, error first then close --
    # matching real websocket-client behavior observed live (both tied to the same underlying WebSocketApp).
    first_transport.simulate_error("Connection to remote host was lost.")
    first_transport.simulate_close(code=None, reason=None)  # the same transport's belated, now-stale close callback

    assert len(factory.instances) == 2  # exactly one reconnect, not two
    assert source.state == DhanConnectionState.CONNECTED  # the single reconnect succeeded cleanly (fake auto-opens)


def test_a_stale_generations_close_after_a_newer_attempt_is_already_open_is_ignored(instrument_map, credentials):
    """A second real-world race this same fix must close: a callback for
    an OLD (already-superseded) connection attempt arriving late must not
    be mistaken for a failure of the CURRENT, successfully-open connection."""
    source, factory = _source(instrument_map, credentials, max_reconnect_attempts=5, backoff_base_seconds=0.01, backoff_max_seconds=0.01)
    source.subscribe(["RELIANCE.NS"], "1m")
    stale_transport = factory.instances[0]

    factory.current.simulate_error("stale failure")  # triggers a reconnect -> a new (2nd) transport opens
    assert len(factory.instances) == 2
    assert source.state == DhanConnectionState.CONNECTED

    stale_transport.simulate_close(code=1000, reason="late callback from the superseded connection")
    assert len(factory.instances) == 2  # ignored -- must NOT spawn a 3rd, unnecessary reconnect
    assert source.state == DhanConnectionState.CONNECTED


def test_a_flapping_connection_never_resets_the_bound_and_eventually_fails(instrument_map, credentials):
    """Phase 16 (VERIFIED against a real account -- the deeper root cause
    behind the reconnect-storm finding): resetting the attempt counter on
    every successful open let a rapidly flapping connection (open, then
    fail again within milliseconds) dodge the bound forever against the
    real Dhan feed -- only Dhan's own server-side rate limiter eventually
    stopped the storm ("429 Too Many Requests ... client id is blocked").
    A connection that never stays up for min_stable_connection_seconds
    must still hit the bound and reach FAILED, not retry indefinitely."""
    source, factory = _source(
        instrument_map, credentials, max_reconnect_attempts=3, backoff_base_seconds=0.01, backoff_max_seconds=0.01,
        min_stable_connection_seconds=10.0,  # far longer than this whole fast test takes to run
    )
    source.subscribe(["RELIANCE.NS"], "1m")
    assert source.state == DhanConnectionState.CONNECTED

    for _ in range(10):  # far more "flaps" than max_reconnect_attempts, to prove it doesn't just get lucky
        if source.state == DhanConnectionState.FAILED:
            break
        factory.current.simulate_error("flapping connection: fails immediately after every open")

    assert source.state == DhanConnectionState.FAILED
    assert source._reconnect_attempts == 3
    assert len(factory.instances) == 4  # 1 initial + exactly 3 reconnects, never more


def test_a_genuinely_stable_connection_resets_the_bound_before_a_later_failure(instrument_map, credentials):
    """The complement of the flapping test: a connection that WAS stable
    for long enough must still get its retry counter reset before the next
    failure, so a single drop after a long healthy run doesn't inherit an
    exhausted-looking counter from a much earlier, unrelated episode."""
    source, factory = _source(
        instrument_map, credentials, max_reconnect_attempts=2, backoff_base_seconds=0.01, backoff_max_seconds=0.01,
        min_stable_connection_seconds=0.0,  # "stable" the instant it opens, for a fast test
    )
    source.subscribe(["RELIANCE.NS"], "1m")
    factory.current.simulate_error("first drop")
    assert source._reconnect_attempts == 1
    assert source.state == DhanConnectionState.CONNECTED  # reconnected cleanly (fake auto-opens)

    factory.current.simulate_error("second drop, after being stable again")
    assert source._reconnect_attempts == 1  # reset before counting this one -- not accumulated to 2
    assert source.state == DhanConnectionState.CONNECTED


def test_server_sent_disconnect_packet_triggers_reconnect_path(instrument_map, credentials):
    source, factory = _source(instrument_map, credentials, max_reconnect_attempts=3, backoff_base_seconds=0.01, backoff_max_seconds=0.01)
    source.subscribe(["RELIANCE.NS"], "1m")
    factory.current.simulate_message(_disconnect_packet(805))  # "too many connections" per Dhan's documented codes
    assert len(factory.instances) == 2  # reconnect was attempted
