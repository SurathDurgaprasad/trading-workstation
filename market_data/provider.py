"""Phase 18 -- the concrete unified market-data facade: ties one
market_data.contracts.SnapshotAdapter (Yahoo/mock/Dhan -- see
market_data/adapters/) and a MarketUniverse together.

Deliberately does not decide WHICH adapter to use, or read any config
file itself -- callers construct the adapter and universe they want and
hand both to this class. No AI logic, no recommendation logic, no
persistence: this answers "what is the current state of the market I've
been asked to watch?" and nothing more, per the roadmap's own Phase 18
acceptance criteria.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from market_data.contracts import SnapshotAdapter
from market_data.models import InstrumentSnapshot, MarketSnapshot
from market_data.universe import MarketUniverse


@dataclass
class UnifiedMarketDataFacade:
    adapter: SnapshotAdapter
    universe: MarketUniverse

    def get_snapshot(self, symbol: str) -> InstrumentSnapshot:
        return self.adapter.get_snapshot(symbol)

    def get_market_snapshot(self) -> MarketSnapshot:
        """Builds a snapshot for every symbol in the configured universe
        -- not just symbols that happen to already have data. Iterates
        `self.universe.symbols` in order so the resulting MarketSnapshot
        is reproducible."""
        now = datetime.now(timezone.utc)
        instruments = {symbol: self.adapter.get_snapshot(symbol) for symbol in self.universe.symbols}
        return MarketSnapshot(instruments=instruments, as_of=now)

    def close(self) -> None:
        self.adapter.close()
