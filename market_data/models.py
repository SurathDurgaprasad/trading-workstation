"""Phase 18 -- market state models.

Built ON TOP of the existing, unchanged `OHLCVBar`
(market.data_provider.OHLCVBar) rather than duplicating its fields: an
InstrumentSnapshot is a point-in-time VIEW over bars this project already
produces via the existing MarketDataProvider/MarketDataSource protocols
(market/data_provider.py, live/contracts.py) -- never a new bar
representation, and never a new source of truth.

Roadmap §5/§18: "Market data sources are abstracted. Market state can be
persisted. Data quality is measurable. No trading recommendation logic
yet." These two dataclasses are the "market state" half of that
requirement; persistence is left to whatever calls this module (no
storage layer is introduced here -- see the Phase 18 report for why).
"""

from dataclasses import dataclass
from datetime import datetime

from market.data_provider import OHLCVBar
from market_data.quality import SourceHealth


@dataclass(frozen=True)
class InstrumentSnapshot:
    """A point-in-time view of one instrument: its latest known bar (or
    None if no data has ever been observed) plus the health/quality of
    the data that produced it. Deliberately thin -- this is a view over
    existing OHLCVBar data, not a new source of truth."""

    symbol: str
    latest_bar: OHLCVBar | None
    health: SourceHealth
    as_of: datetime
    """UTC-aware: the moment THIS snapshot was constructed (always
    `datetime.now(timezone.utc)` in every adapter -- see
    market_data/adapters/), not necessarily when the underlying bar was
    produced. That is a DIFFERENT timestamp: `latest_bar.timestamp` (the
    bar's own time) and `health.last_updated` (what SourceHealth judged
    freshness against) may be naive (Yahoo/mock) or UTC-aware (real Dhan,
    since Phase 16) and are generally earlier than `as_of`."""


@dataclass(frozen=True)
class MarketSnapshot:
    """A point-in-time view of every instrument in a configured universe
    (see market_data/universe.py). Symbols with no data yet (never
    fetched, or the fetch failed) still appear here with latest_bar=None
    and an explicit health status -- never silently omitted, so a caller
    scanning this snapshot always sees the full universe, not just the
    subset that happened to have data."""

    instruments: dict[str, InstrumentSnapshot]
    as_of: datetime

    def get(self, symbol: str) -> InstrumentSnapshot | None:
        return self.instruments.get(symbol)

    def __len__(self) -> int:
        return len(self.instruments)
