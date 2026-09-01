"""Phase 12 §1 — the live-capable market data contract. Modeled on the
existing `market.data_provider.MarketDataProvider` Protocol (same
`@runtime_checkable` pattern, same "one method, one job" shape) but for a
STREAMING source rather than a one-shot historical fetch — subscribe once,
then pull bars as they arrive.

Deliberately generic: nothing here assumes Dhan, or any specific broker.
`live/mock_source.py` is the only implementation in this phase.
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


@runtime_checkable
class MarketDataSource(Protocol):
    def subscribe(self, symbols: list[str], interval: str) -> None:
        """Begin producing bars for `symbols` at `interval`. Calling this
        again with new symbols/interval is implementation-defined (the mock
        source treats it as replacing the subscription)."""

    def next_bar(self) -> MarketBarEvent | None:
        """Returns the next bar in arrival order, or None if the feed has
        cleanly ended (no more data, not a failure). Raises
        FeedDisconnectedError if the connection is currently down."""

    def is_connected(self) -> bool:
        """True if the source is currently able to produce bars. False
        during a simulated/real disconnect — checked by the pipeline before
        deciding whether stale/missing data is expected or a genuine fault."""

    def unsubscribe(self, symbols: list[str] | None = None) -> None:
        """Stop producing bars for `symbols` (or all, if None)."""

    def close(self) -> None:
        """Release any held resources. Idempotent."""
