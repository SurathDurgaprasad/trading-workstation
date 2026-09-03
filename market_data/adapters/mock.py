"""Phase 18 -- constructs a market_data snapshot adapter around the
EXISTING, unmodified MockMarketDataSource (live/mock_source.py). No
changes to that module -- this only wraps it.
"""

from live.mock_source import MockMarketDataSource
from market_data.adapters._streaming import StreamingSnapshotAdapter


def build_mock_adapter(symbol: str, *, interval: str = "1d", period: str = "1y") -> StreamingSnapshotAdapter:
    """`symbol` here is which cached history to replay -- MockMarketDataSource
    is inherently single-symbol (see live/mock_source.py). Asking the
    resulting adapter for a DIFFERENT symbol's snapshot is not an error;
    it will simply never receive data for a symbol this replay script
    doesn't cover, correctly surfacing as SourceHealth.no_data()."""
    source = MockMarketDataSource.from_cached_history(symbol, interval=interval, period=period)
    return StreamingSnapshotAdapter(source, interval=interval)
