"""Phase 12 §3 — a deterministic mock live feed. Implements
live.contracts.MarketDataSource by replaying an explicit, pre-built SCRIPT
of events (bars, disconnects, reconnects) — nothing here is random or
wall-clock-dependent unless a test deliberately injects a clock. This is
what makes every failure mode (duplicate/out-of-order/gap/delayed/stale/
disconnect/reconnect) exactly reproducible in a test, with no real
credentials or network access.

Two ways to build a script:
  - `MockMarketDataSource.from_cached_history(...)` — a normal, in-order
    replay of REAL cached OHLCV data (reuses backtesting.cache /
    market.indicators unchanged), tagged source=MOCK, status=SIMULATED.
  - Construct `MockScriptEvent` lists directly for the failure-mode tests
    (inject a duplicate, reorder two bars, drop one, mark one delayed, drop
    in a DISCONNECT/RECONNECT pair) — full control, spec's explicit ask.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from live.contracts import FeedDisconnectedError, MarketBarEvent, MarketDataSource
from market.data_provider import DataSource, DataStatus, OHLCVBar


class MockEventKind(str, Enum):
    BAR = "BAR"
    DISCONNECT = "DISCONNECT"
    RECONNECT = "RECONNECT"


@dataclass(frozen=True)
class MockScriptEvent:
    kind: MockEventKind
    symbol: str | None = None
    bar: OHLCVBar | None = None

    @classmethod
    def bar_event(cls, symbol: str, bar: OHLCVBar) -> "MockScriptEvent":
        return cls(kind=MockEventKind.BAR, symbol=symbol, bar=bar)

    @classmethod
    def disconnect(cls) -> "MockScriptEvent":
        return cls(kind=MockEventKind.DISCONNECT)

    @classmethod
    def reconnect(cls) -> "MockScriptEvent":
        return cls(kind=MockEventKind.RECONNECT)


def make_mock_bar(
    *, timestamp: datetime, open: float, high: float, low: float, close: float, volume: float = 0.0,
    source_timestamp: datetime | None = None,
) -> OHLCVBar:
    """Convenience constructor for a script bar — source/status are always
    MOCK/SIMULATED here; `received_at` is intentionally left unset because
    MockMarketDataSource stamps it at actual delivery time (next_bar()),
    not at script-construction time, matching how a real feed would work."""
    return OHLCVBar(
        timestamp=timestamp, open=open, high=high, low=low, close=close, volume=volume,
        source=DataSource.MOCK, status=DataStatus.SIMULATED,
        source_timestamp=source_timestamp or timestamp,
    )


class MockMarketDataSource:
    """A scripted, deterministic MarketDataSource. See module docstring."""

    def __init__(self, script: Iterable[MockScriptEvent], *, clock: Callable[[], datetime] | None = None):
        self._script: list[MockScriptEvent] = list(script)
        self._position = 0
        self._connected = True
        self._subscribed_symbols: set[str] = set()
        self._interval: str | None = None
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._closed = False

    # -- MarketDataSource protocol -------------------------------------------

    def subscribe(self, symbols: list[str], interval: str) -> None:
        if self._closed:
            raise RuntimeError("Cannot subscribe on a closed MockMarketDataSource.")
        self._subscribed_symbols = set(symbols)
        self._interval = interval

    def next_bar(self) -> MarketBarEvent | None:
        if self._closed:
            raise RuntimeError("Cannot read from a closed MockMarketDataSource.")

        while self._position < len(self._script):
            event = self._script[self._position]
            self._position += 1  # script always advances -- nothing blocks it indefinitely

            if event.kind == MockEventKind.DISCONNECT:
                self._connected = False
                continue
            if event.kind == MockEventKind.RECONNECT:
                self._connected = True
                continue

            # event.kind == BAR. A bar scripted while disconnected is LOST,
            # not queued for post-reconnect delivery -- matching how a real
            # streaming feed behaves (an outage does not replay missed
            # ticks). The script has already moved past it; the NEXT call
            # continues from whatever comes after in the script.
            if not self._connected:
                raise FeedDisconnectedError(f"Feed disconnected; the bar for {event.symbol} at {event.bar.timestamp} was lost.")

            if event.symbol not in self._subscribed_symbols:
                continue  # bar for a symbol we're not subscribed to -- skip, don't fail

            delivered = event.bar.model_copy(update={"received_at": self._clock()})
            return MarketBarEvent(symbol=event.symbol, bar=delivered)

        return None  # script exhausted -- a clean end, not a failure

    def is_connected(self) -> bool:
        return self._connected

    def unsubscribe(self, symbols: list[str] | None = None) -> None:
        if symbols is None:
            self._subscribed_symbols = set()
        else:
            self._subscribed_symbols -= set(symbols)

    def close(self) -> None:
        self._closed = True

    # -- construction helpers -------------------------------------------------

    @classmethod
    def from_cached_history(cls, symbol: str, *, interval: str = "1d", period: str = "1y", clock: Callable[[], datetime] | None = None) -> "MockMarketDataSource":
        """Builds a normal, in-order BAR-only script from REAL cached OHLCV
        data (Yahoo, via the existing CachedMarketDataProvider — unchanged),
        re-tagged source=MOCK/status=SIMULATED. This is "replay existing
        cached OHLCV data as if it were arriving live" (spec §3)."""
        from backtesting.cache import CachedMarketDataProvider
        from market.data_provider import get_market_data_provider

        provider = CachedMarketDataProvider(get_market_data_provider())
        ohlcv = provider.fetch_ohlcv(symbol, period=period, interval=interval)

        script = [
            MockScriptEvent.bar_event(
                symbol,
                make_mock_bar(timestamp=bar.timestamp, open=bar.open, high=bar.high, low=bar.low, close=bar.close, volume=bar.volume),
            )
            for bar in ohlcv.bars
        ]
        source = cls(script, clock=clock)
        source.subscribe([symbol], interval)
        return source
