from datetime import datetime, timezone

from market.data_provider import OHLCVBar
from market_data.models import InstrumentSnapshot
from market_data.provider import UnifiedMarketDataFacade
from market_data.quality import SourceHealth, SourceStatus
from market_data.universe import MarketUniverse


class _FakeAdapter:
    def __init__(self):
        self.calls: list[str] = []
        self.closed = False
        self._data: dict[str, OHLCVBar] = {}

    def set_bar(self, symbol: str, bar: OHLCVBar) -> None:
        self._data[symbol] = bar

    def get_snapshot(self, symbol: str) -> InstrumentSnapshot:
        self.calls.append(symbol)
        now = datetime.now(timezone.utc)
        bar = self._data.get(symbol)
        health = SourceHealth.no_data() if bar is None else SourceHealth.from_bar_timestamp(bar_timestamp=now, interval="1d", now=now)
        return InstrumentSnapshot(symbol=symbol, latest_bar=bar, health=health, as_of=now)

    def close(self) -> None:
        self.closed = True


def _bar() -> OHLCVBar:
    return OHLCVBar(timestamp=datetime(2026, 9, 3, 10, 0), open=100.0, high=101.0, low=99.0, close=100.5, volume=10.0)


def test_get_snapshot_delegates_to_the_adapter():
    adapter = _FakeAdapter()
    adapter.set_bar("RELIANCE", _bar())
    facade = UnifiedMarketDataFacade(adapter=adapter, universe=MarketUniverse.from_watchlist(["RELIANCE"]))

    snapshot = facade.get_snapshot("RELIANCE")
    assert snapshot.latest_bar is not None
    assert adapter.calls == ["RELIANCE"]


def test_get_market_snapshot_covers_every_universe_symbol_in_order():
    adapter = _FakeAdapter()
    adapter.set_bar("RELIANCE", _bar())  # TCS deliberately has no data
    universe = MarketUniverse.from_watchlist(["RELIANCE", "TCS"])
    facade = UnifiedMarketDataFacade(adapter=adapter, universe=universe)

    market_snapshot = facade.get_market_snapshot()

    assert len(market_snapshot) == 2
    assert adapter.calls == ["RELIANCE", "TCS"]
    assert market_snapshot.get("RELIANCE").latest_bar is not None
    assert market_snapshot.get("TCS").latest_bar is None
    assert market_snapshot.get("TCS").health.status == SourceStatus.NO_DATA


def test_close_delegates_to_the_adapter():
    adapter = _FakeAdapter()
    facade = UnifiedMarketDataFacade(adapter=adapter, universe=MarketUniverse.from_watchlist(["RELIANCE"]))
    facade.close()
    assert adapter.closed is True
