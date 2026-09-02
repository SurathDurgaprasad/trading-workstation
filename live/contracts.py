"""Phase 12 §1 — the live-capable market data contract. Modeled on the
existing `market.data_provider.MarketDataProvider` Protocol (same
`@runtime_checkable` pattern, same "one method, one job" shape) but for a
STREAMING source rather than a one-shot historical fetch — subscribe once,
then pull bars as they arrive.

Deliberately generic: nothing here assumes Dhan, or any specific broker.
`live/mock_source.py` (a finite scripted replay) and, as of Phase 15,
`live/dhan/market_data_source.py` (a real, open-ended WebSocket feed) both
implement this same Protocol unchanged.

Phase 15 addition: `NO_NEW_BAR`. The original next_bar() contract (`None`
means "the feed has cleanly ended, permanently") is exactly right for a
finite scripted replay, but meaningless for a real feed that is simply
between candles -- MockMarketDataSource's script eventually runs out for
good, but a live WebSocket connection never "ends" the way a file does; it
just sometimes has nothing new to report *yet*. Reusing bare `None` for
both would make LiveSimPipeline.process_next() treat an ordinary quiet
moment as FEED_EXHAUSTED and stop polling — a real bug, not a hypothetical
one, found while wiring DhanMarketDataSource into the existing pipeline.
`NO_NEW_BAR` is a distinct singleton (never `None`, never a MarketBarEvent)
so process_next() can tell the two cases apart without any change to
MockMarketDataSource's existing, still-correct behavior.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from market.data_provider import OHLCVBar


@dataclass(frozen=True)
class MarketBarEvent:
    """Pairs a bar with the symbol it belongs to — OHLCVBar itself carries
    no symbol (matching market.data_provider.OHLCV's existing shape, where
    symbol lives on the wrapper, not the bar)."""

    symbol: str
    bar: OHLCVBar


class FeedDisconnectedError(Exception):
    """Raised by next_bar() while the source is in a simulated/real
    disconnected state. Callers must treat this as fail-closed (stop
    generating new signals) rather than retrying in a tight loop — see
    live/pipeline.py."""


class _NoNewBarSentinel:
    def __repr__(self) -> str:
        return "NO_NEW_BAR"

    def __bool__(self) -> bool:
        return False  # so `if not event:` reads naturally, same as None would


NO_NEW_BAR = _NoNewBarSentinel()
"""Returned by next_bar() to mean "still connected, nothing new arrived
within this poll" — as opposed to `None` ("the feed is permanently
finished") or a real MarketBarEvent. A source that never has this
in-between state (like the finite mock replay) simply never returns it."""


@runtime_checkable
class MarketDataSource(Protocol):
    def subscribe(self, symbols: list[str], interval: str) -> None:
        """Begin producing bars for `symbols` at `interval`. Calling this
        again with new symbols/interval is implementation-defined (the mock
        source treats it as replacing the subscription)."""

    def next_bar(self) -> "MarketBarEvent | _NoNewBarSentinel | None":
        """Returns the next bar in arrival order; `NO_NEW_BAR` if the feed
        is alive but has nothing new yet (see this module's docstring); or
        `None` if the feed has cleanly ended, permanently (no more data
        ever, not a failure). Raises FeedDisconnectedError if the
        connection is currently down."""

    def is_connected(self) -> bool:
        """True if the source is currently able to produce bars. False
        during a simulated/real disconnect — checked by the pipeline before
        deciding whether stale/missing data is expected or a genuine fault."""

    def unsubscribe(self, symbols: list[str] | None = None) -> None:
        """Stop producing bars for `symbols` (or all, if None)."""

    def close(self) -> None:
        """Release any held resources. Idempotent."""
