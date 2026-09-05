"""Phase 15 §5/§9/§10 — DhanMarketDataSource implements the EXISTING
live.contracts.MarketDataSource protocol (unchanged) against a real Dhan
WebSocket connection. The rest of the pipeline (strategy, RiskEngine,
approval, freshness) sees only OHLCVBar, exactly as it does for the mock
source -- nothing above this class ever sees a Dhan packet, a security ID,
or an exchange-segment byte.

Design split for testability without a real Dhan account: the WIRE-LEVEL
logic (turning one binary packet into a candle-builder update, and
recognizing a disconnect packet) lives in plain, synchronous methods that
take already-received bytes and are fully unit-testable with synthetic
packets (tests/test_dhan_market_data_source.py). The actual socket I/O is a
thin `_Transport` Protocol so those same tests can inject a fake transport
instead of a real WebSocket -- the transport is the only part that
genuinely cannot be exercised without hitting api-feed.dhan.co.

Connection lifecycle (§9): connect -> authenticate (via the URL's own query
params, per Dhan's documented flow -- no separate auth handshake) ->
subscribe -> receive -> on disconnect, bounded exponential backoff up to
`max_reconnect_attempts`, then a TERMINAL failed state. There is no
unbounded retry loop by construction -- once attempts are exhausted, this
class stops trying and reports FEED_DISCONNECTED forever after, rather
than spinning.
"""

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from live.contracts import NO_NEW_BAR, FeedDisconnectedError, MarketBarEvent, MarketDataSource
from live.dhan.candle_builder import CandleBuilder
from live.dhan.config import DhanCredentials
from live.dhan.instruments import DhanInstrumentMap
from live.dhan.market_session import IST
from live.dhan.wire import (
    MAX_INSTRUMENTS_PER_SUBSCRIBE_MESSAGE,
    DhanDisconnectPacket,
    DhanFeedRequestCode,
    DhanFullPacket,
    DhanQuotePacket,
    DhanTickerPacket,
    DhanWireFormatError,
    build_feed_url,
    build_subscribe_message,
    parse_packet,
)


logger = logging.getLogger(__name__)


class DhanConnectionState:
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    FAILED = "FAILED"  # terminal -- reconnect attempts exhausted
    CLOSED = "CLOSED"  # terminal -- close() was called deliberately


class _Transport(Protocol):
    """The only part of this module that talks to a real socket. Tests
    inject a fake implementing this same shape instead of a real
    websocket-client connection.

    `on_open` (Phase 16 addition -- VERIFIED necessary against a real
    account: connecting to a real Dhan feed that immediately drops the
    connection ["Connection to remote host was lost", no close code, ~0.5s
    after connect] crashed `subscribe()` under the original design, which
    declared CONNECTED and sent the subscribe message the instant the
    background thread *started*, not once the handshake had actually
    succeeded. `on_open` is the only trustworthy "the handshake genuinely
    completed" signal; nothing here is CONNECTED, and no message is sent,
    before it fires."""

    def connect(self, url: str, *, on_open, on_message, on_close, on_error) -> None: ...
    def send_json(self, message: dict) -> None: ...
    def close(self) -> None: ...


@dataclass
class _WebsocketClientTransport:
    """The real transport, built on the already-installed `websocket-client`
    library (websocket-client==1.9.0, confirmed present in venv/ -- no new
    dependency). Runs WebSocketApp.run_forever() in a background thread
    since the rest of this project's pipeline is synchronous and polls
    next_bar() rather than awaiting an event loop."""

    _app: object = field(default=None, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)

    def connect(self, url: str, *, on_open, on_message, on_close, on_error) -> None:
        import websocket  # websocket-client

        def _on_open(_ws):
            on_open()

        def _on_message(_ws, message):
            on_message(message)

        def _on_close(_ws, close_status_code, close_msg):
            on_close(close_status_code, close_msg)

        def _on_error(_ws, error):
            on_error(error)

        self._app = websocket.WebSocketApp(url, on_open=_on_open, on_message=_on_message, on_close=_on_close, on_error=_on_error)
        self._thread = threading.Thread(target=self._app.run_forever, kwargs={"ping_interval": 0}, daemon=True)
        self._thread.start()

    def send_json(self, message: dict) -> None:
        import json

        if self._app is None or self._app.sock is None:
            raise FeedDisconnectedError("Cannot send: no active Dhan WebSocket connection.")
        self._app.send(json.dumps(message))

    def close(self) -> None:
        if self._app is not None:
            self._app.close()


@dataclass
class DhanMarketDataSource:
    """MarketDataSource protocol implementation for real Dhan live data.

    `instrument_map` resolves subscribed symbols to Dhan (exchange_segment,
    security_id) pairs -- see live/dhan/instruments.py. `interval` selects
    the CandleBuilder bucket size ("1m"/"5m"/"15m", matching this project's
    existing interval-string convention).
    """

    credentials: DhanCredentials
    instrument_map: DhanInstrumentMap
    interval: str
    max_reconnect_attempts: int = 5
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 30.0
    next_bar_timeout_seconds: float = 5.0
    # Phase 16 addition (VERIFIED necessary against a real account -- see
    # _claim_reconnect_locked's docstring): a connection must stay open for
    # at least this long before a later failure is treated as the start of
    # a FRESH retry streak. Without this, a rapidly flapping connection
    # (opens, then dies again within milliseconds -- exactly what the real
    # Dhan feed did) resets the attempt counter on every single open and
    # the bound never actually engages.
    min_stable_connection_seconds: float = 10.0
    transport_factory: type = _WebsocketClientTransport

    def __post_init__(self):
        self.state: str = DhanConnectionState.DISCONNECTED
        self._transport: _Transport | None = None
        self._bar_queue: "queue.Queue[MarketBarEvent]" = queue.Queue()
        self._candle_builders: dict[str, CandleBuilder] = {}
        self._security_id_to_symbol: dict[str, str] = {}
        self._subscribed_symbols: set[str] = set()
        self._reconnect_attempts = 0
        self._last_disconnect_reason: str | None = None
        self._connected_at: float | None = None
        # Phase 16 addition (VERIFIED necessary against a real account -- see
        # _report_connection_lost's docstring): guards the state machine and
        # tags every connection attempt with a generation number so that
        # redundant failure signals for the SAME attempt are deduplicated.
        self._lock = threading.Lock()
        self._connection_generation = 0

    # -- MarketDataSource protocol -------------------------------------------

    def _resolve_instrument(self, symbol: str):
        """"RELIANCE.NS"-shaped symbols resolve via the Yahoo-suffix
        convention; a bare "RELIANCE" is assumed NSE equity. Centralized
        here so subscribe() and the reconnect path never duplicate (and
        risk diverging on) this resolution logic."""
        if "." in symbol:
            return self.instrument_map.lookup_yahoo_symbol(symbol)
        return self.instrument_map.lookup(trading_symbol=symbol, exchange="NSE")

    def subscribe(self, symbols: list[str], interval: str) -> None:
        if interval != self.interval:
            raise ValueError(f"This DhanMarketDataSource was constructed for interval={self.interval!r}, not {interval!r}. Construct a separate instance per interval.")

        instruments = []
        for symbol in symbols:
            instrument = self._resolve_instrument(symbol)
            self._security_id_to_symbol[instrument.security_id] = symbol
            self._candle_builders.setdefault(symbol, CandleBuilder(symbol=symbol, interval=self.interval))
            instruments.append((instrument.exchange_segment, instrument.security_id))
            self._subscribed_symbols.add(symbol)

        if self.state in (DhanConnectionState.DISCONNECTED, DhanConnectionState.FAILED):
            # Hardening fix (found via offline code review, not a live incident): _connect() itself never
            # resets _reconnect_attempts -- only _claim_reconnect_locked does, on stability. A manual
            # resubscribe after a permanent FAILED must start a genuinely fresh retry budget, not inherit
            # the exhausted counter from the PREVIOUS episode (which would otherwise silently fail again
            # after zero real retries on the very next drop).
            with self._lock:
                self._reconnect_attempts = 0
                self._connected_at = None
            self._connect()  # _on_transport_open sends the subscribe message once the handshake genuinely completes
        elif self.state == DhanConnectionState.CONNECTED:
            self._send_subscribe(instruments)
        # else: CONNECTING/RECONNECTING already in flight -- _on_transport_open will pick up
        # the now-updated _subscribed_symbols set once it fires; nothing to send yet.

    def next_bar(self):
        """Blocks up to `next_bar_timeout_seconds` waiting for a completed
        bar. Returns `NO_NEW_BAR` on timeout with no bar available yet --
        the feed is alive, just between candles (see live/contracts.py's
        NO_NEW_BAR docstring for why this is distinct from `None`). This
        source never returns bare `None`: unlike a finite scripted replay,
        a live WebSocket feed has no "permanently ended" state short of a
        FeedDisconnectedError. Raises FeedDisconnectedError once
        reconnection attempts are exhausted (state == FAILED)."""
        if self.state == DhanConnectionState.FAILED:
            raise FeedDisconnectedError(f"Dhan feed permanently disconnected after {self._reconnect_attempts} reconnect attempts: {self._last_disconnect_reason}")
        try:
            return self._bar_queue.get(timeout=self.next_bar_timeout_seconds)
        except queue.Empty:
            return NO_NEW_BAR

    def rejected_tick_counts_by_symbol(self) -> dict[str, dict[str, int]]:
        """Strategy science Phase 16 (observability) -- aggregates each
        subscribed symbol's own CandleBuilder.rejected_tick_counts (see
        that class's own docstring) into one queryable view across the
        whole feed, so an operator can check "how many bad ticks has this
        session seen, across every symbol" without grepping logs or
        reaching into private per-symbol state directly. A snapshot at
        call time -- counts only ever grow for the life of this source
        instance, never reset here."""
        return {symbol: dict(builder.rejected_tick_counts) for symbol, builder in self._candle_builders.items()}

    def is_connected(self) -> bool:
        return self.state == DhanConnectionState.CONNECTED

    def unsubscribe(self, symbols: list[str] | None = None) -> None:
        target = set(symbols) if symbols is not None else set(self._subscribed_symbols)
        self._subscribed_symbols -= target

    def close(self) -> None:
        """Hardening fix (found via offline code review + a real-threading
        stress test, no live network involved): this previously mutated
        `self.state`/read `self._transport` WITHOUT the lock. A reconnect
        already past its own CLOSED pre-check (inside _run_reconnect_attempt)
        could race past this unlocked write and call _connect() anyway,
        which used to unconditionally overwrite state back to CONNECTING and
        open a brand-new, un-tracked WebSocket -- an orphan connection the
        caller believes is closed. _connect() now re-checks CLOSED under the
        SAME lock immediately before creating a transport, so whichever of
        close()/_connect() acquires the lock first deterministically wins,
        and the loser either never creates a new transport (if close() won)
        or close() correctly captures and closes the one _connect() just
        created (if _connect() won)."""
        with self._lock:
            self.state = DhanConnectionState.CLOSED
            transport = self._transport
        logger.info("Dhan feed closed by caller.")
        if transport is not None:
            transport.close()

    # -- connection management (§9) ----------------------------------------

    def _connect(self) -> None:
        with self._lock:
            if self.state == DhanConnectionState.CLOSED:
                return  # a close() raced ahead of this (re)connect attempt -- honor it, never revive after close()
            self.state = DhanConnectionState.CONNECTING
            self._connection_generation += 1
            generation = self._connection_generation
            transport = self.transport_factory()
            self._transport = transport
        url = build_feed_url(client_id=self.credentials.client_id, access_token=self.credentials.access_token)
        transport.connect(
            url,
            on_open=lambda: self._on_transport_open(generation),
            on_message=self._on_raw_message,
            on_close=lambda status_code, reason: self._report_connection_lost(generation, f"transport closed (code={status_code}, reason={reason})"),
            on_error=lambda error: self._report_connection_lost(generation, f"transport error: {error}"),
        )
        # state stays CONNECTING here -- do NOT declare CONNECTED until
        # _on_transport_open actually fires (see _Transport's docstring).

    def _redact_secret(self, text: str) -> str:
        """Defense-in-depth (Phase 16 hardening -- no evidence of an actual
        leak; the exception-construction code paths in the pinned
        websocket-client version were checked and never embed the request
        URL, only response-derived text or bare hostnames). Still: this
        project treats "never expose credentials in logs" as a hard
        invariant enforced at the code level, not a property assumed of a
        third-party library's current behavior -- see DhanCredentials'
        masked __repr__ for the same posture elsewhere in this package."""
        token = self.credentials.access_token
        if token and token in text:
            return text.replace(token, "***")
        return text

    def _on_transport_open(self, generation: int) -> None:
        with self._lock:
            if generation != self._connection_generation:
                return  # a stale/superseded connection attempt -- ignore
            self.state = DhanConnectionState.CONNECTED
            # _reconnect_attempts is NOT reset here -- see _claim_reconnect_locked's docstring for why
            # resetting on every open (rather than on sustained stability) enabled a real reconnect storm.
            self._connected_at = time.monotonic()
            subscribed = list(self._subscribed_symbols)
        logger.info("Dhan feed CONNECTED (generation=%d, subscribed symbols=%d).", generation, len(subscribed))
        if subscribed:
            instruments = [
                (instrument.exchange_segment, instrument.security_id)
                for instrument in (self._resolve_instrument(symbol) for symbol in subscribed)
            ]
            self._send_subscribe(instruments, generation=generation)

    def _send_subscribe(self, instruments: list[tuple[str, str]], *, generation: int | None = None) -> None:
        # Ticker mode only -- LTP+LTT is all this project's candle building
        # needs (see CandleBuilder/_extract_tick's own docstrings on why
        # Quote/Full's cumulative volume isn't used).
        request_code = DhanFeedRequestCode.SUBSCRIBE_TICKER
        for start in range(0, len(instruments), MAX_INSTRUMENTS_PER_SUBSCRIBE_MESSAGE):
            chunk = instruments[start : start + MAX_INSTRUMENTS_PER_SUBSCRIBE_MESSAGE]
            try:
                self._transport.send_json(build_subscribe_message(request_code=request_code, instruments=chunk))
            except Exception as exc:  # noqa: BLE001 -- a send failure means the connection is already gone (e.g. closed
                # between on_open and this call); route it through the same deduplicated reconnect path as
                # on_close/on_error, never let a raw transport exception escape to the caller.
                self._report_connection_lost(generation if generation is not None else self._connection_generation, f"send failed: {exc}")
                return

    def _report_connection_lost(self, generation: int, reason: str) -> None:
        """The single funnel for every way a connection attempt can be
        discovered to have failed (on_error, on_close, a send failure, or a
        server-sent Disconnect packet in _handle_packet).

        Phase 16 fix -- VERIFIED necessary against a real account: a real
        WebSocketApp fires BOTH on_error and on_close for the same
        underlying failure (each from its own thread, genuinely concurrent
        -- confirmed with a real-threading stress test, not just sequential
        fake-transport calls), and a send can fail independently for that
        same loss. The generation check alone is NOT sufficient: two
        concurrent reports for the SAME still-current generation (i.e.
        arriving before _connect() has had a chance to bump the generation,
        which only happens after the backoff sleep) both pass it. The
        actual mutual exclusion has to be the STATE transition itself,
        claimed atomically under the lock in _claim_reconnect -- see its
        docstring. Without this, one real failure triggered 2-3+ separate
        reconnect episodes, and under genuine thread concurrency this
        compounded into an actual reconnect storm (hundreds of connection
        attempts) that got this project's Dhan client ID rate-limited by
        Dhan's own server ("429 Too Many Requests ... client id is
        blocked") during Phase 16 testing."""
        reason = self._redact_secret(reason)
        with self._lock:
            if generation != self._connection_generation:
                return  # a stale, already-superseded generation -- ignore
            self._last_disconnect_reason = reason
            attempt_number = self._claim_reconnect_locked()
            failed = self.state == DhanConnectionState.FAILED
            total_attempts = self._reconnect_attempts
        if attempt_number is not None:
            logger.info("Dhan feed connection lost (%s) -- reconnecting, attempt %d/%d.", reason, attempt_number, self.max_reconnect_attempts)
            self._run_reconnect_attempt(attempt_number)
        elif failed:
            logger.warning("Dhan feed permanently FAILED after %d reconnect attempts -- last reason: %s", total_attempts, reason)

    def _claim_reconnect_locked(self) -> "int | None":
        """Must be called while holding self._lock. Atomically decides
        whether THIS caller is the one that gets to initiate a new
        reconnect episode -- returns the attempt number if so, or None if
        there's nothing to do (already CLOSED, a reconnect is already in
        flight, or the bound is already exhausted). This is the actual
        mutual-exclusion point: state, not just the generation number, is
        what a concurrent duplicate report checks against.

        Phase 16 fix -- VERIFIED necessary against a real account: the
        original design reset _reconnect_attempts to 0 the instant a
        connection opened. Against the real Dhan feed, connections kept
        opening successfully and then closing again within milliseconds
        (a "flapping" connection) -- every open reset the counter to 0
        before the very next failure could ever push it toward the bound,
        so the bound never actually engaged; only Dhan's own server-side
        rate limiter eventually stopped the storm ("429 Too Many Requests
        ... client id is blocked"). The counter must only reset if the
        connection was genuinely stable for min_stable_connection_seconds
        first -- a flapping connection accumulates attempts across the
        whole flapping episode and correctly reaches FAILED."""
        if self.state in (DhanConnectionState.CLOSED, DhanConnectionState.RECONNECTING):
            return None
        was_stable = self._connected_at is not None and (time.monotonic() - self._connected_at) >= self.min_stable_connection_seconds
        if was_stable:
            self._reconnect_attempts = 0
        self._connected_at = None
        if self._reconnect_attempts >= self.max_reconnect_attempts:
            self.state = DhanConnectionState.FAILED
            return None
        self.state = DhanConnectionState.RECONNECTING
        self._reconnect_attempts += 1
        return self._reconnect_attempts

    def _run_reconnect_attempt(self, attempt_number: int) -> None:
        """Executes ONE already-claimed reconnect attempt (backoff, then
        connect). On a SYNCHRONOUS connect() failure, retries by claiming
        the next attempt directly -- this is a legitimate continuation of
        the episode already claimed by _claim_reconnect_locked, not a new
        duplicate claim, so it does not re-check "already RECONNECTING"."""
        backoff = min(self.backoff_base_seconds * (2 ** (attempt_number - 1)), self.backoff_max_seconds)
        time.sleep(backoff)
        with self._lock:
            if self.state == DhanConnectionState.CLOSED:
                return  # close() happened while backing off -- honor it, never reconnect after a deliberate close
        try:
            self._connect()  # _on_transport_open resends the subscribed instruments once this attempt actually opens
        except Exception as exc:  # noqa: BLE001 -- a failed reconnect attempt must not crash the background thread; it just counts against the bound
            reason = self._redact_secret(f"reconnect attempt {attempt_number} failed: {exc}")
            with self._lock:
                self._last_disconnect_reason = reason
                if self._reconnect_attempts >= self.max_reconnect_attempts:
                    self.state = DhanConnectionState.FAILED
                    total_attempts = self._reconnect_attempts
                    logger.warning("Dhan feed permanently FAILED after %d reconnect attempts -- last reason: %s", total_attempts, reason)
                    return
                self._reconnect_attempts += 1
                next_attempt = self._reconnect_attempts
            logger.info("Dhan feed reconnect attempt %d failed synchronously (%s) -- retrying, attempt %d/%d.", attempt_number, reason, next_attempt, self.max_reconnect_attempts)
            self._run_reconnect_attempt(next_attempt)

    def _attempt_reconnect(self) -> None:
        """White-box entry point used directly by tests (and internally,
        indistinguishable from a fresh _report_connection_lost call with no
        generation to check): claim a reconnect episode and run it."""
        with self._lock:
            attempt_number = self._claim_reconnect_locked()
        if attempt_number is not None:
            self._run_reconnect_attempt(attempt_number)

    # -- wire-level handling, pure and unit-testable with synthetic bytes ---

    def _on_raw_message(self, data: bytes) -> None:
        try:
            self._handle_packet(data)
        except DhanWireFormatError:
            # A corrupted/unrecognized packet is dropped, never treated as
            # a valid price -- logging is the caller's/operator's concern;
            # this method's contract is simply "never crash the socket
            # thread on bad input."
            return

    def _handle_packet(self, data: bytes):
        """Returns the MarketBarEvent it queued (if any) -- primarily so
        tests can call this directly with synthetic bytes and assert on
        the return value without needing a real queue/thread."""
        packet = parse_packet(data)

        if isinstance(packet, DhanDisconnectPacket):
            # Routed through the same dedup funnel as on_error/on_close/send-failure (see
            # _report_connection_lost's docstring) -- a server-sent Disconnect packet typically
            # precedes the socket's own on_close/on_error for the same teardown.
            self._report_connection_lost(self._connection_generation, f"server-sent disconnect (code={packet.reason_code})")
            return None

        symbol = self._security_id_to_symbol.get(str(packet.header.security_id))
        if symbol is None:
            return None  # a packet for a security we never subscribed to (or already unsubscribed) -- ignore, don't guess

        price, volume, epoch_seconds = self._extract_tick(packet)
        if price is None:
            return None

        timestamp = self._decode_last_trade_time(epoch_seconds)
        received_at = datetime.now(timezone.utc)
        builder = self._candle_builders[symbol]
        bar = builder.on_tick(price=price, volume=volume, timestamp=timestamp, received_at=received_at)
        if bar is None:
            return None
        event = MarketBarEvent(symbol=symbol, bar=bar)
        self._bar_queue.put(event)
        return event

    @staticmethod
    def _extract_tick(packet) -> tuple[float | None, float, int]:
        """Ticker packets carry no volume at all (VERIFIED -- LTP/LTT
        only); this project passes volume=0.0 for those rather than
        inventing a number (see CandleBuilder.on_tick's own docstring).
        Quote/Full packets carry a cumulative day Volume; this method does
        NOT attempt a cumulative-to-incremental conversion (a real
        implementation would need to track the previous cumulative value
        per symbol) -- Ticker-mode subscription is what this project
        actually uses (see _send_subscribe), so this path is exercised
        for completeness but not relied upon."""
        if isinstance(packet, DhanTickerPacket):
            return packet.last_traded_price, 0.0, packet.last_trade_time_epoch
        if isinstance(packet, (DhanQuotePacket, DhanFullPacket)):
            return packet.last_traded_price, 0.0, packet.last_trade_time_epoch
        return None, 0.0, 0

    @staticmethod
    def _decode_last_trade_time(epoch_seconds: int) -> datetime:
        """Phase 16 fix -- VERIFIED against a real account, 2026-09-03:
        Dhan's "Last Trade Time" field is documented as an epoch but is NOT
        a true Unix UTC epoch. A real tick's LTT, decoded the naive way
        (`datetime.fromtimestamp(epoch, tz=UTC)`), produced wall-clock
        digits matching the CURRENT IST time, not the current UTC time --
        confirmed with an independent cross-check (this project's own local
        clock was itself verified accurate to within ~2 minutes of Dhan's
        own real HTTP `Date` response header from an earlier session, so
        the anomaly is not a local-clock artifact). The evidence points to
        Dhan computing this field from IST wall-clock digits encoded as if
        they were already UTC (a naive-local-epoch pattern), not documented
        anywhere in the current live docs.

        Uncorrected, this silently broke FreshnessPolicy for every real
        Dhan bar: bar.timestamp ends up ~5.5 hours in the FUTURE relative
        to true UTC "now", making `age = now - bar_timestamp` negative --
        which is always <= any positive threshold, so is_fresh was always
        True regardless of actual staleness. This is the fix: reinterpret
        the decoded wall-clock digits as IST (not UTC), then convert to the
        genuinely correct UTC instant."""
        naive_ist_digits = datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).replace(tzinfo=IST)
        return naive_ist_digits.astimezone(timezone.utc)
