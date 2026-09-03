"""Phase 18 -- the unifying market-data contract.

Deliberately thin, and deliberately NOT a replacement for either existing
protocol:

  * market.data_provider.MarketDataProvider -- one-shot historical fetch
    (fetch_ohlcv), used by backtesting/, `paper run`, `analyze`. Unchanged.
  * live.contracts.MarketDataSource -- streaming subscribe/next_bar, used
    by `paper-live`/`live-sim`. Unchanged.

Both remain exactly as they are, used exactly where they already are.
SnapshotAdapter answers a NEW question neither of those answers alone:
"what is the CURRENT state of this instrument, right now, regardless of
whether the underlying source is streaming or historical?" See
market_data/adapters/ for the concrete adapters that answer it by wrapping
the two existing protocols above, and market_data/provider.py for the
facade that ties one adapter to a MarketUniverse.
"""

from typing import Protocol, runtime_checkable

from market_data.models import InstrumentSnapshot


@runtime_checkable
class SnapshotAdapter(Protocol):
    def get_snapshot(self, symbol: str) -> InstrumentSnapshot:
        """Returns the current best-known snapshot for `symbol`. Never
        raises for "no data yet" or "not currently connected" -- returns
        an InstrumentSnapshot with latest_bar=None and the appropriate
        SourceHealth instead, so callers inspect state rather than needing
        to catch an exception for an entirely ordinary condition."""

    def close(self) -> None:
        """Release any held resources. Idempotent."""
