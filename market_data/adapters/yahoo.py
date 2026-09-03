"""Phase 18 -- adapts the EXISTING, unmodified YahooFinanceProvider
(market/data_provider.py) to the unified snapshot contract. Wraps, never
reimplements: every real network call still goes through
YahooFinanceProvider.fetch_ohlcv exactly as it always has.

Unlike the streaming adapters (mock/dhan), Yahoo is a one-shot fetch --
get_snapshot() calls the underlying provider fresh each time. There is no
caching here; a caller that wants to avoid refetching on every call is
responsible for that at a higher layer (out of scope for this
foundational phase -- see the Phase 18 report).
"""

from datetime import datetime, timezone

from market.data_provider import MarketDataError, MarketDataProvider, YahooFinanceProvider
from market_data.models import InstrumentSnapshot
from market_data.quality import SourceHealth


class YahooSnapshotAdapter:
    def __init__(self, provider: MarketDataProvider | None = None, *, period: str = "5d", interval: str = "1d"):
        self._provider = provider or YahooFinanceProvider()
        self._period = period
        self._interval = interval

    def get_snapshot(self, symbol: str) -> InstrumentSnapshot:
        now = datetime.now(timezone.utc)
        try:
            ohlcv = self._provider.fetch_ohlcv(symbol, period=self._period, interval=self._interval)
        except MarketDataError as exc:
            return InstrumentSnapshot(symbol=symbol, latest_bar=None, health=SourceHealth.error(str(exc)), as_of=now)
        if not ohlcv.bars:
            return InstrumentSnapshot(symbol=symbol, latest_bar=None, health=SourceHealth.no_data(), as_of=now)
        latest = ohlcv.bars[-1]
        health = SourceHealth.from_bar_timestamp(bar_timestamp=latest.timestamp, interval=self._interval, now=now)
        return InstrumentSnapshot(symbol=symbol, latest_bar=latest, health=health, as_of=now)

    def close(self) -> None:
        pass  # YahooFinanceProvider (yfinance) holds no persistent resource to release
