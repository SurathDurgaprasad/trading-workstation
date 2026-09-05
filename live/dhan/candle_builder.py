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

    def __init__(self, *, symbol: str, interval: str, max_tick_deviation_pct: float = 20.0):
        self.symbol = symbol
        self.interval = interval
        self._bucket_seconds = interval_to_timedelta(interval).total_seconds()
        self._state: _BucketState | None = None
        self._max_tick_deviation_pct = max_tick_deviation_pct
        """Strategy science Phase 13 (live data stress testing) -- an
        adversarial-audit finding: a single corrupted-but-well-formed
        tick (still a positive float, so OHLCVBar's own gt=0 validation
        never catches it) previously flowed straight into a bar's high/
        low/close with zero resistance. A tick deviating more than this
        percentage from the last REAL price accepted (tracked in
        _last_known_price, persisting across bucket rollovers -- not
        just within-bucket) is dropped as implausible, logged, never
        silently corrupting a bar. A heuristic, not a guarantee: 20% is
        conservative for equities (a genuine circuit-breaker-magnitude
        move could rarely be flagged too) -- deliberately erring toward
        dropping a rare genuine extreme tick over accepting garbage
        data, consistent with this project's "never trade on bad data"
        posture. Configurable per instance; None disables the check
        entirely (e.g. for instruments with legitimately huge normal
        swings). An invalid tick's PRICE never seeds or merges into any
        bucket, but its TIMESTAMP can still legitimately complete an
        already-elapsed prior bucket (elapsed exchange time is trustworthy
        independent of whether this specific tick's price is) -- see the
        price_is_valid handling inside on_tick."""
        self._last_known_price: float | None = None

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
        own docstring) -- this class only ever sums whatever it's given.

        KNOWN, DOCUMENTED LIMITATION (not fixed -- explicitly acknowledged,
        per this project's own "do not fake dedup without a reliable
        message identifier" rule): Dhan's Ticker/Quote/Full packets carry
        no per-message sequence number or unique tick ID (verified against
        the documented packet formats -- only security_id/LTP/LTT), so an
        exact-duplicate tick redelivered after a reconnect (same price,
        volume, and timestamp as one already processed) cannot be reliably
        told apart from a second, genuinely distinct trade that happens to
        share those same values -- it is NOT deduplicated, and would be
        merged into the current bucket again. In this project's actual,
        currently-used configuration this is harmless: Ticker-mode
        subscription is what `DhanMarketDataSource` sends (see
        `_send_subscribe`), and Ticker packets always pass `volume=0.0`
        here, so a redelivered duplicate changes nothing (max/min/close are
        idempotent for a repeated identical price, and 0.0 volume adds
        0.0). It would only matter for a real per-tick-volume feed, which
        this project does not have (the Quote/Full cumulative-to-incremental
        conversion above is explicitly not implemented either)."""
        price_is_valid = True
        if price <= 0:
            price_is_valid = False
            logger.warning(
                "CandleBuilder(%s, %s): rejecting a non-positive-price tick (price=%s, timestamp=%s) -- "
                "never a real traded price.", self.symbol, self.interval, price, timestamp,
            )
        elif volume < 0:
            price_is_valid = False
            logger.warning(
                "CandleBuilder(%s, %s): rejecting a negative-volume tick (volume=%s, timestamp=%s).",
                self.symbol, self.interval, volume, timestamp,
            )
        elif self._last_known_price is not None and self._max_tick_deviation_pct is not None:
            deviation_pct = abs(price - self._last_known_price) / self._last_known_price * 100.0
            if deviation_pct > self._max_tick_deviation_pct:
                price_is_valid = False
                logger.warning(
                    "CandleBuilder(%s, %s): rejecting an implausible tick (price=%s, last known real price=%s, "
                    "deviation=%.1f%% > %.1f%% threshold, timestamp=%s) -- likely corrupted/fat-finger data.",
                    self.symbol, self.interval, price, self._last_known_price, deviation_pct,
                    self._max_tick_deviation_pct, timestamp,
                )

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

        if not price_is_valid:
            # The bad tick's OWN price/volume must never seed or merge into
            # ANY bucket -- but its timestamp may have legitimately
            # completed the PREVIOUS bucket just above (bucket completion
            # is a question of elapsed exchange time, which this tick's
            # timestamp can still be trusted for, independent of whether
            # its price can be). _last_known_price is deliberately NOT
            # updated here, so the next tick is still checked against the
            # last genuinely real price, and _state is deliberately left
            # None (rather than seeded from garbage) -- the next bucket
            # only starts once a genuinely valid tick actually arrives.
            return completed

        if self._state is None:
            self._state = _BucketState(
                bucket_start=bucket_start, open=price, high=price, low=price, close=price,
                volume=0.0, last_received_at=received_at, last_source_timestamp=timestamp,
            )

        self._state.high = max(self._state.high, price)
        self._state.low = min(self._state.low, price)
        self._state.close = price
        self._state.volume += volume
        self._last_known_price = price
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
