"""Phase 15 §6/§12 — Dhan's WebSocket delivers ticks (Ticker/Quote/Full
packets, each carrying a single last-traded-price at a point in time), not
pre-built candles (VERIFIED: no candle-shaped streaming mode exists in the
documented Feed Request Codes -- only Ticker/Quote/Full/Depth). Building
1m/5m/15m bars from that stream requires local aggregation, done here and
ONLY here -- nothing above CandleBuilder in the pipeline ever sees a tick.

Documented candle semantics (this project's own choice, stated explicitly
per spec §6 rather than left implicit):
  - Bucket boundaries are floored to the interval from the Unix epoch (e.g.
    a "5m" bucket starting at an epoch second divisible by 300) -- the same
    boundary convention exchanges and every broker's own pre-built candles
    use, so bars line up with what a human would see on a broker terminal.
  - open = price of the first tick in the bucket.
  - high/low = running max/min of every tick's price in the bucket.
  - close = price of the most recent tick in the bucket (updated on every
    tick, finalized when the bucket closes).
  - volume = sum of each tick's own volume field. Dhan's Ticker/PrevClose
    packets carry no per-tick volume; only Quote/Full packets carry a
    cumulative day Volume, not a per-trade quantity -- see the docstring
    on `on_tick`'s `volume` parameter for how this is handled.
  - Bucketing uses the tick's OWN exchange timestamp (Last Trade Time from
    the packet), never local receipt time -- avoiding skew from network
    jitter, per spec §7's received_at/source_timestamp distinction.
  - A bar is only returned (as "completed") the instant a tick belonging to
    the NEXT bucket arrives -- there is no wall-clock timer forcing a bar
    closed early. A bucket with no ticks in it produces no bar at all
    (this project does not manufacture a synthetic flat bar for a silent
    period -- see the Phase 15 report's disconnect-behavior section for
    why: "do not manufacture a price").
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from live.freshness import interval_to_timedelta
from market.data_provider import DataSource, DataStatus, OHLCVBar

logger = logging.getLogger(__name__)


@dataclass
class _BucketState:
    bucket_start: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    last_received_at: datetime
    last_source_timestamp: datetime


class CandleBuilder:
    """One instance per (symbol, interval). Feed ticks via on_tick(); a
    completed OHLCVBar is returned the moment a tick from the NEXT bucket
    arrives, else None. Pure -- no I/O, no network, fully deterministic
    given a sequence of ticks, and therefore trivially unit-testable
    without any real Dhan connection."""

    def __init__(self, *, symbol: str, interval: str):
        self.symbol = symbol
        self.interval = interval
        self._bucket_seconds = interval_to_timedelta(interval).total_seconds()
        self._state: _BucketState | None = None

    def _bucket_start_for(self, timestamp: datetime) -> datetime:
        epoch = timestamp.timestamp()
        floored = (epoch // self._bucket_seconds) * self._bucket_seconds
        return datetime.fromtimestamp(floored, tz=timezone.utc)

    def on_tick(self, *, price: float, volume: float, timestamp: datetime, received_at: datetime) -> OHLCVBar | None:
        """`volume` is whatever incremental quantity this specific tick
        represents. Dhan's Ticker packet carries no volume at all (LTP/LTT
        only) -- callers driving CandleBuilder from Ticker packets alone
        should pass volume=0.0, producing bars with volume=0 (honest: no
        volume data was actually available), never a fabricated number.
        Quote/Full packets carry a cumulative day Volume rather than a
        per-tick delta; DhanMarketDataSource is responsible for that
        cumulative-to-incremental conversion before calling here (see its
        own docstring) -- this class only ever sums whatever it's given."""
        bucket_start = self._bucket_start_for(timestamp)
        completed: OHLCVBar | None = None

        if self._state is not None and bucket_start < self._state.bucket_start:
            # Adversarial-audit finding: a late/out-of-order tick (its OWN
            # exchange timestamp belongs to a bucket that already closed)
            # must never be merged into the CURRENT bucket -- doing so
            # silently corrupts an already-in-progress bar's high/low/close/
            # volume with a price that was never actually observed during
            # that bucket, and can even push last_source_timestamp BEFORE
            # the bar's own declared timestamp (an internally inconsistent
            # record). Real, plausible cause: server-side reordering,
            # reconnect-driven redelivery, or interleaved packet types for
            # the same instrument -- TCP's in-order delivery guarantees
            # only the transport layer, not the exchange-timestamp order of
            # what arrives on it. Dropped, never fabricated into either
            # bucket -- matches this module's own "do not manufacture a
            # price" posture applied to corruption, not just fabrication.
            logger.warning(
                "CandleBuilder(%s, %s): dropping a late/out-of-order tick (timestamp=%s, bucket=%s) -- "
                "bucket %s is already in progress and must not be corrupted by it.",
                self.symbol, self.interval, timestamp, bucket_start, self._state.bucket_start,
            )
            return None

        if self._state is not None and bucket_start > self._state.bucket_start:
            completed = self._finalize(self._state)
            self._state = None

        if self._state is None:
            self._state = _BucketState(
                bucket_start=bucket_start, open=price, high=price, low=price, close=price,
                volume=0.0, last_received_at=received_at, last_source_timestamp=timestamp,
            )

        self._state.high = max(self._state.high, price)
        self._state.low = min(self._state.low, price)
        self._state.close = price
        self._state.volume += volume
        self._state.last_received_at = received_at
        self._state.last_source_timestamp = timestamp

        return completed

    def _finalize(self, state: _BucketState) -> OHLCVBar:
        return OHLCVBar(
            timestamp=state.bucket_start, open=state.open, high=state.high, low=state.low, close=state.close, volume=state.volume,
            source=DataSource.DHAN, status=DataStatus.LIVE, received_at=state.last_received_at, source_timestamp=state.last_source_timestamp,
        )

    def flush(self) -> OHLCVBar | None:
        """Returns the CURRENT in-progress bucket as a bar without waiting
        for a tick from the next bucket -- for an explicit, deliberate
        "close out whatever we have" call (e.g. on a clean shutdown). Does
        NOT get called automatically by on_tick; an in-progress bucket is
        never silently finalized by a timer, matching the "do not
        manufacture a price" posture for every other partial-data case in
        this project."""
        if self._state is None:
            return None
        return self._finalize(self._state)
