"""Phase 18 -- shared adapter logic for wrapping any EXISTING, unmodified
live.contracts.MarketDataSource (MockMarketDataSource or
DhanMarketDataSource -- both implement the same Protocol) as a
market_data.contracts.SnapshotAdapter.

Private module (leading underscore): market_data/adapters/mock.py and
market_data/adapters/dhan.py both build on this one class rather than
each reimplementing the same drain/cache/subscribe logic twice.
"""

import time
from datetime import datetime, timezone

from live.contracts import NO_NEW_BAR, FeedDisconnectedError, MarketDataSource
from market.data_provider import OHLCVBar
from market_data.models import InstrumentSnapshot
from market_data.quality import SourceHealth


class StreamingSnapshotAdapter:
    """Wraps any live.contracts.MarketDataSource. Subscribes lazily, on
    the first get_snapshot() call for a given symbol, so callers never
    need to manage subscription lifecycle themselves.

    get_snapshot() DRAINS whatever the underlying source has already
    produced via next_bar() -- it never fabricates a bar, and it can
    block up to the source's own `next_bar_timeout_seconds` on its last
    drain iteration when nothing new has arrived (a real, documented
    characteristic of the underlying poll-with-timeout contract, not
    something this adapter can avoid without changing that contract,
    which Phase 18 explicitly does not do).

    `warmup_seconds` (LIVE SYSTEM HARDENING mission, real-live-market
    finding): a real `shadow-run --live-source dhan` this session
    reported "0/3 live quote overlays succeeded" -- reproduced live and
    root-caused to a pure TIMING gap, not a broken component. A real
    WebSocket handshake+auth is asynchronous (confirmed live: ~0.5s to
    reach CONNECTED from a cold start), and a symbol's own first tick
    only starts flowing after ITS OWN subscribe message is sent -- a
    single, unbudgeted get_snapshot() call for a symbol subscribed
    moments earlier can easily observe DISCONNECTED (checked before the
    handshake completes) or NO_DATA (connected, but no tick has arrived
    for THIS symbol yet). Reproduced live with instrumentation: given a
    real, bounded warm-up window, all 3 real symbols consistently
    reached HEALTHY with real live prices. Defaults to 0.0 (== the
    exact original behavior, no wait at all -- every existing caller
    and test is unaffected); a caller building a REAL live overlay
    (`market_data.adapters.dhan.build_dhan_adapter`) opts in with a
    real, bounded value instead."""

    def __init__(self, source: MarketDataSource, *, interval: str, warmup_seconds: float = 0.0, warmup_poll_seconds: float = 0.25):
        self._source = source
        self._interval = interval
        self._latest: dict[str, OHLCVBar] = {}
        self._subscribed: set[str] = set()
        self._warmup_seconds = warmup_seconds
        self._warmup_poll_seconds = warmup_poll_seconds

    def _ensure_subscribed(self, symbol: str) -> bool:
        """Returns True iff THIS call is the one that actually subscribed
        (i.e. `symbol` was not already subscribed) -- the warm-up wait
        below only ever applies to a symbol's OWN first call, never to a
        subsequent, already-warm one."""
        if symbol not in self._subscribed:
            self._source.subscribe([symbol], self._interval)
            self._subscribed.add(symbol)
            return True
        return False

    def _drain(self) -> None:
        """Pulls every bar currently available without waiting for a NEW
        one beyond the source's own single poll timeout -- stops the
        instant next_bar() reports NO_NEW_BAR, the feed has permanently
        ended (None), or the feed is disconnected."""
        while True:
            try:
                event = self._source.next_bar()
            except FeedDisconnectedError:
                return
            if event is NO_NEW_BAR or event is None:
                return
            self._latest[event.symbol] = event.bar

    def _wait_for_warmup(self, symbol: str) -> None:
        """Bounded, opt-in wait (see `warmup_seconds`'s own docstring) for
        the connection to actually complete and for THIS symbol's own
        first tick to arrive -- polls rather than sleeping the full
        budget unconditionally, so a fast-connecting/fast-ticking real
        feed returns as soon as it genuinely has data, never slower than
        necessary. A no-op whenever warmup_seconds <= 0 (the default)."""
        if self._warmup_seconds <= 0:
            return
        deadline = time.monotonic() + self._warmup_seconds
        while time.monotonic() < deadline:
            if self._source.is_connected():
                self._drain()
                if symbol in self._latest:
                    return
            else:
                time.sleep(self._warmup_poll_seconds)

    def get_snapshot(self, symbol: str) -> InstrumentSnapshot:
        now = datetime.now(timezone.utc)
        newly_subscribed = self._ensure_subscribed(symbol)

        if newly_subscribed:
            self._wait_for_warmup(symbol)

        if not self._source.is_connected():
            cached = self._latest.get(symbol)
            return InstrumentSnapshot(symbol=symbol, latest_bar=cached, health=SourceHealth.disconnected(), as_of=now)

        self._drain()
        bar = self._latest.get(symbol)
        if bar is None:
            return InstrumentSnapshot(symbol=symbol, latest_bar=None, health=SourceHealth.no_data(), as_of=now)
        health = SourceHealth.from_bar_timestamp(bar_timestamp=bar.timestamp, interval=self._interval, now=now)
        return InstrumentSnapshot(symbol=symbol, latest_bar=bar, health=health, as_of=now)

    def close(self) -> None:
        self._source.close()
