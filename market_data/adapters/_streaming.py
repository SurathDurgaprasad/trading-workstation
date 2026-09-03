"""Phase 18 -- shared adapter logic for wrapping any EXISTING, unmodified
live.contracts.MarketDataSource (MockMarketDataSource or
DhanMarketDataSource -- both implement the same Protocol) as a
market_data.contracts.SnapshotAdapter.

Private module (leading underscore): market_data/adapters/mock.py and
market_data/adapters/dhan.py both build on this one class rather than
each reimplementing the same drain/cache/subscribe logic twice.
"""

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
    which Phase 18 explicitly does not do)."""

    def __init__(self, source: MarketDataSource, *, interval: str):
        self._source = source
        self._interval = interval
        self._latest: dict[str, OHLCVBar] = {}
        self._subscribed: set[str] = set()

    def _ensure_subscribed(self, symbol: str) -> None:
        if symbol not in self._subscribed:
            self._source.subscribe([symbol], self._interval)
            self._subscribed.add(symbol)

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

    def get_snapshot(self, symbol: str) -> InstrumentSnapshot:
        now = datetime.now(timezone.utc)
        self._ensure_subscribed(symbol)

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
