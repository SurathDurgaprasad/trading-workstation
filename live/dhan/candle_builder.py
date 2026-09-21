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

    def __init__(
        self, *, symbol: str, interval: str, max_tick_deviation_pct: float = 20.0,
        max_timestamp_skew_seconds: float | None = 3600.0,
        max_cold_start_wall_clock_skew_seconds: float | None = 3600.0,
    ):
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
        self._max_timestamp_skew_seconds = max_timestamp_skew_seconds
        self._last_known_timestamp: datetime | None = None
        """Live-market-readiness audit finding: unlike price, a tick's own
        `timestamp` was trusted UNCONDITIONALLY to compute its bucket, with
        no plausibility check at all -- a single tick with an otherwise-
        valid price but a corrupted/wildly-future timestamp (e.g. a decode
        glitch in Dhan's LTT field) would seed `_state.bucket_start` far in
        the future; every subsequent, genuinely-real tick would then have
        an EARLIER bucket_start than that seeded state and be rejected
        FOREVER via the late/out-of-order path below, with no
        self-recovery -- candle production for that symbol permanently
        stops. Worse, if the corrupted tick arrives while a real bucket is
        already open, its garbage-future timestamp can look like "the next
        bucket has started" and prematurely finalize/close the real,
        still-accumulating bucket early.

        Checked against `_last_known_timestamp` (this builder's own last
        genuinely accepted tick, mirroring `_last_known_price`'s identical
        pattern) rather than `received_at` (local wall-clock receipt time):
        a wall-clock comparison would be self-consistent in real production
        use, but is NOT what this check needs to be robust against a purely
        synthetic/replayed/backtested tick stream whose own timestamps are
        deliberately far from "now" (this project's own test suite,
        `paper/advance.py`'s Yahoo-driven fills, etc.) -- comparing
        consecutive REAL exchange timestamps against each other is
        self-consistent regardless of what wall-clock epoch is in use.
        1 hour default: generous enough to tolerate any real illiquid-
        symbol lull between successive trades, tight enough to catch
        genuine corruption (which in practice is either wildly wrong or
        off by a fixed encoding-bug offset, never merely "a bit late" --
        see the late-tick path below for that ordinary case). None
        disables the check entirely.

        COLD-START SELF-RECOVERY (2026-09-17 live incident): the very
        first tick a fresh CandleBuilder instance ever receives has no
        `_last_known_timestamp` to compare against, so it was previously
        trusted UNCONDITIONALLY and permanently poisoned every check after
        it -- observed live in production on this exact date: HINDUNILVR.NS
        and SUNPHARMA.NS each received a stale first tick carrying the
        PREVIOUS trading day's timestamp (2026-09-16 10:26:09/10:22:06
        UTC, almost certainly a Dhan overnight LTP-snapshot artifact sent
        on subscribe), silently accepted it as the baseline, and then
        rejected every genuinely-current tick for the rest of the session
        (203/235 rejections observed by the time this was diagnosed,
        growing unbounded) -- reproduced exactly in isolation with these
        same real values.

        `_baseline_confirmed`/`_pending_candidate_timestamp` close this,
        WITHOUT weakening the existing mid-session protection above (a
        first, simpler "re-seed on any disagreement" design was tried and
        rejected -- it broke `test_a_wildly_future_timestamp_does_not_
        permanently_kill_candle_production` by letting a single stray bad
        tick permanently displace an already-good baseline; a genuine
        single-bad-tick-in-a-good-stream and a genuine bad-FIRST-tick are
        locally indistinguishable from one disagreement alone, so this
        needs a SECOND, independent data point before ever abandoning the
        current baseline):

        While unconfirmed, a tick disagreeing with `_last_known_timestamp`
        is rejected (exactly like today, `_last_known_timestamp` and
        `_state` untouched) UNLESS it agrees with `_pending_candidate_
        timestamp` (the immediately-preceding disagreement) -- two
        DIFFERENT ticks agreeing with EACH OTHER, both independently
        disagreeing with the current baseline, is what actually
        distinguishes "the original baseline was the bad one" from "one
        stray bad tick occurred mid-stream". Only then does the baseline
        switch to this pair, `_state`/`_last_known_price` are discarded
        (they were built from the now-abandoned, untrustworthy baseline),
        and `_baseline_confirmed` becomes permanently True -- from that
        point on, behavior is byte-identical to the pre-existing,
        already-tested mid-session logic above. If a tick agrees with the
        ORIGINAL baseline instead (the ordinary case: the first tick was
        fine all along), confirmation happens the simple way -- two
        agreeing ticks against the SAME baseline -- with no reset."""
        self._baseline_confirmed: bool = False
        self._pending_candidate_timestamp: datetime | None = None
        self._max_cold_start_wall_clock_skew_seconds = max_cold_start_wall_clock_skew_seconds
        """2026-09-21 live incident (fleet-wide, all 15 symbols, real):
        the two-tick-agreement heuristic above closes the SINGLE-bad-
        first-tick case, but cannot by itself tell "two REAL current
        ticks agreeing" apart from "two STALE ticks that happen to agree
        with each other (or with the original stale baseline)" -- which
        is exactly what happened live on a Monday cold start after a
        weekend gap: EVERY one of the 15 real fleet workers received a
        stale Friday-afternoon LTP-snapshot first tick, and for every one
        of them the SECOND tick received was ALSO within
        max_timestamp_skew_seconds of that same stale Friday value
        (fell into the "agrees with the current baseline" branch below,
        not even needing the pending-candidate path) -- confirming the
        wrong baseline PERMANENTLY on the very first real chance, with
        zero self-heal available afterward (see
        test_an_overnight_gap_after_baseline_confirmed_is_a_documented_
        residual_gap_not_a_bug_in_practice's own docstring, which had
        judged this "not exercised by this project's actual deployment"
        based on the evidence available BEFORE this incident -- that
        judgment is now known to be wrong).

        Closes it directly: a baseline is only ever allowed to become
        CONFIRMED (in either the "switch to a new pending candidate" or
        the "agrees with the original baseline" branch below) if the
        CONFIRMING tick's own `timestamp` is itself plausible relative to
        its own `received_at` (the local wall-clock moment this specific
        tick actually arrived) -- deliberately NOT an injected/global
        clock dependency: `received_at` is already a real parameter on
        every call, already self-consistent for any synthetic/test tick
        stream (which sets both to the same or nearby synthetic value, by
        construction, exactly like every existing test in this file
        already does), and does not reintroduce the wall-clock-vs-
        synthetic-stream tension `_max_timestamp_skew_seconds`'s own
        docstring above explicitly reasoned about for the CORE mid-
        session check (which compares two ticks' OWN timestamps against
        each other, not against receipt time, and is completely
        unaffected by this addition). If a tick fails this check at a
        confirmation point, it is treated exactly like an ordinary
        disagreement -- remembered as the new pending candidate, rejected,
        never confirmed -- so the self-heal loop keeps running until a
        tick that is ACTUALLY current arrives. `None` disables the check
        entirely, restoring the exact pre-fix behavior for a caller that
        wants it."""
        self.rejected_tick_counts: dict[str, int] = {
            "non_positive_price": 0, "negative_volume": 0, "implausible_deviation": 0, "late_out_of_order": 0,
            "implausible_timestamp": 0,
        }
        """Strategy science Phase 16 (observability) -- each rejection is
        already logged (see on_tick), but a log line alone isn't
        queryable without grepping. Running counts by reason, visible for
        the lifetime of this instance, so an operator (or
        docs/MONDAY_LIVE_VALIDATION_PLAN.md's own Step 1 checklist item)
        can check "how many ticks were rejected today" programmatically
        instead of scanning logs by hand. Never reset automatically --
        one CandleBuilder instance lives for one (symbol, interval) pair
        for the life of the process."""

    def _bucket_start_for(self, timestamp: datetime) -> datetime:
        epoch = timestamp.timestamp()
        floored = (epoch // self._bucket_seconds) * self._bucket_seconds
        return datetime.fromtimestamp(floored, tz=timezone.utc)

    def _plausible_relative_to_receipt(self, *, timestamp: datetime, received_at: datetime) -> bool:
        """See `_max_cold_start_wall_clock_skew_seconds`'s own docstring
        for the 2026-09-21 incident this closes. Only ever consulted at a
        baseline-CONFIRMATION point, never for the core mid-session
        tick-vs-tick check."""
        if self._max_cold_start_wall_clock_skew_seconds is None:
            return True
        return abs((timestamp - received_at).total_seconds()) <= self._max_cold_start_wall_clock_skew_seconds

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
        if self._last_known_timestamp is not None and self._max_timestamp_skew_seconds is not None:
            skew_seconds = abs((timestamp - self._last_known_timestamp).total_seconds())
            if skew_seconds > self._max_timestamp_skew_seconds:
                if not self._baseline_confirmed:
                    pending = self._pending_candidate_timestamp
                    agrees_with_pending = pending is not None and abs((timestamp - pending).total_seconds()) <= self._max_timestamp_skew_seconds
                    if agrees_with_pending and self._plausible_relative_to_receipt(timestamp=timestamp, received_at=received_at):
                        # This tick agrees with the PREVIOUS disagreeing
                        # tick, not with the current baseline -- two
                        # independent ticks agreeing with each other is
                        # strong evidence the ORIGINAL baseline (not this
                        # pair) was the anomalous one. Switch to it and
                        # discard any bucket state built from the
                        # now-abandoned baseline; falls through below to
                        # process this tick normally against the new
                        # baseline. Also wall-clock-plausible (2026-09-21
                        # fix) -- not just internally consistent with the
                        # pending candidate, but actually current.
                        logger.warning(
                            "CandleBuilder(%s, %s): two consecutive ticks agree with each other "
                            "(timestamp=%s, previous candidate=%s) while disagreeing with the current "
                            "baseline (%s) -- switching baseline and discarding bucket state built from "
                            "the abandoned baseline; now confirmed.",
                            self.symbol, self.interval, timestamp, pending, self._last_known_timestamp,
                        )
                        self._last_known_timestamp = timestamp
                        self._baseline_confirmed = True
                        self._pending_candidate_timestamp = None
                        self._state = None
                        self._last_known_price = None
                    else:
                        if agrees_with_pending:
                            # 2026-09-21 fix: two ticks agree with each
                            # other but BOTH fail the wall-clock
                            # plausibility check (e.g. two fragments of the
                            # same stale snapshot burst) -- do not confirm.
                            # Roll the pending candidate forward to this
                            # tick anyway so a genuinely current tick can
                            # still break the tie on a later call.
                            logger.warning(
                                "CandleBuilder(%s, %s): two consecutive ticks agree with each other "
                                "(timestamp=%s, previous candidate=%s) but neither is plausible relative to "
                                "its own receipt time -- refusing to confirm a baseline from stale-but-"
                                "internally-consistent data; still not confirmed.",
                                self.symbol, self.interval, timestamp, pending,
                            )
                        # Cold-start self-recovery: the baseline hasn't
                        # been confirmed yet, and this lone disagreement
                        # doesn't (yet) match a prior one -- remember it as
                        # a tentative candidate but do NOT abandon the
                        # current baseline on the strength of a single
                        # disagreeing tick alone (that would misfire on an
                        # ordinary single stray bad tick mid-session, see
                        # __init__ docstring). Rejected exactly like the
                        # confirmed-baseline path below.
                        self._pending_candidate_timestamp = timestamp
                        self.rejected_tick_counts["implausible_timestamp"] += 1
                        logger.warning(
                            "CandleBuilder(%s, %s): unconfirmed timestamp baseline disagreed with a new "
                            "tick (timestamp=%s, previous baseline=%s, skew=%.0fs > %.0fs threshold) -- "
                            "rejecting and remembering as a pending candidate baseline; not yet confirmed.",
                            self.symbol, self.interval, timestamp, self._last_known_timestamp, skew_seconds,
                            self._max_timestamp_skew_seconds,
                        )
                        return None
                else:
                    self.rejected_tick_counts["implausible_timestamp"] += 1
                    logger.warning(
                        "CandleBuilder(%s, %s): rejecting a tick with an implausible timestamp (timestamp=%s, "
                        "last known real timestamp=%s, skew=%.0fs > %.0fs threshold) -- likely a corrupted/garbage "
                        "exchange timestamp, never trusted to seed, complete, or otherwise touch any bucket.",
                        self.symbol, self.interval, timestamp, self._last_known_timestamp, skew_seconds,
                        self._max_timestamp_skew_seconds,
                    )
                    return None  # fully inert -- unlike an invalid PRICE, an invalid TIMESTAMP can never be
                    # trusted to complete an elapsed bucket either, since bucket membership is computed FROM it.
            else:
                if not self._baseline_confirmed:
                    if self._plausible_relative_to_receipt(timestamp=timestamp, received_at=received_at):
                        # This tick agrees with the current (original)
                        # baseline within the threshold -- two consecutive
                        # agreeing ticks against the SAME baseline is enough
                        # evidence to trust it permanently, no reset needed.
                        # Also wall-clock-plausible (2026-09-21 fix): the
                        # ordinary, correct case -- the first tick really
                        # was fine all along. From here on, behavior is
                        # byte-identical to the pre-existing, already-
                        # tested mid-session logic.
                        self._baseline_confirmed = True
                        self._pending_candidate_timestamp = None
                    else:
                        # 2026-09-21 fix: this tick numerically agrees with
                        # the CURRENT (still-unconfirmed) baseline, but
                        # fails the wall-clock plausibility check -- the
                        # real 2026-09-21 incident's exact shape (a second
                        # stale-but-consistent tick confirming a stale
                        # first tick, without ever needing the pending-
                        # candidate path at all). Refuse to confirm; treat
                        # as a fresh, independent candidate instead of
                        # trusting agreement with an unproven baseline.
                        self._pending_candidate_timestamp = timestamp
                        self.rejected_tick_counts["implausible_timestamp"] += 1
                        logger.warning(
                            "CandleBuilder(%s, %s): tick agrees with the still-unconfirmed baseline "
                            "(timestamp=%s, baseline=%s) but neither is plausible relative to its own "
                            "receipt time -- refusing to confirm; remembering as a fresh pending candidate "
                            "instead of trusting agreement with an unproven baseline.",
                            self.symbol, self.interval, timestamp, self._last_known_timestamp,
                        )
                        return None

        price_is_valid = True
        if price <= 0:
            price_is_valid = False
            self.rejected_tick_counts["non_positive_price"] += 1
            logger.warning(
                "CandleBuilder(%s, %s): rejecting a non-positive-price tick (price=%s, timestamp=%s) -- "
                "never a real traded price.", self.symbol, self.interval, price, timestamp,
            )
        elif volume < 0:
            price_is_valid = False
            self.rejected_tick_counts["negative_volume"] += 1
            logger.warning(
                "CandleBuilder(%s, %s): rejecting a negative-volume tick (volume=%s, timestamp=%s).",
                self.symbol, self.interval, volume, timestamp,
            )
        elif self._last_known_price is not None and self._max_tick_deviation_pct is not None:
            deviation_pct = abs(price - self._last_known_price) / self._last_known_price * 100.0
            if deviation_pct > self._max_tick_deviation_pct:
                price_is_valid = False
                self.rejected_tick_counts["implausible_deviation"] += 1
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
            self.rejected_tick_counts["late_out_of_order"] += 1
            logger.warning(
                "CandleBuilder(%s, %s): dropping a late/out-of-order tick (timestamp=%s, bucket=%s) -- "
                "bucket %s is already in progress and must not be corrupted by it.",
                self.symbol, self.interval, timestamp, bucket_start, self._state.bucket_start,
            )
            return None

        if self._state is not None and bucket_start > self._state.bucket_start:
            completed = self._finalize(self._state, is_partial=False)
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
        self._last_known_timestamp = timestamp
        self._state.last_received_at = received_at
        self._state.last_source_timestamp = timestamp

        return completed

    def _finalize(self, state: _BucketState, *, is_partial: bool) -> OHLCVBar:
        return OHLCVBar(
            timestamp=state.bucket_start, open=state.open, high=state.high, low=state.low, close=state.close, volume=state.volume,
            source=DataSource.DHAN, status=DataStatus.LIVE, received_at=state.last_received_at,
            source_timestamp=state.last_source_timestamp, is_partial=is_partial,
        )

    def flush(self) -> OHLCVBar | None:
        """Returns the CURRENT in-progress bucket as a bar (is_partial=True
        -- see OHLCVBar's own field docstring) without waiting for a tick
        from the next bucket -- for an explicit, deliberate "give me
        what we have so far" call (e.g. a live-price display, or a clean
        shutdown). Does NOT get called automatically by on_tick; an
        in-progress bucket is never silently finalized by a timer,
        matching the "do not manufacture a price" posture for every other
        partial-data case in this project. Pure peek: does not clear or
        otherwise mutate the accumulating bucket, so calling this
        repeatedly (e.g. once per dashboard poll) never disturbs the real
        candle this same bucket will eventually finalize into via
        on_tick's own natural rollover."""
        if self._state is None:
            return None
        return self._finalize(self._state, is_partial=True)

    @property
    def last_known_price(self) -> float | None:
        """The most recent VALID tick price accepted by on_tick, updated
        on every accepted tick regardless of bucket boundaries -- the
        finest-grained live price this class can offer, sub-candle. None
        until the first valid tick this instance has ever seen. LIVE
        SYSTEM HARDENING mission, Part 2: this data already existed
        internally (used for the tick-deviation plausibility check, see
        __init__'s own docstring) but was never exposed publicly until
        now -- the exact gap identified in the live-data-architecture
        investigation."""
        return self._last_known_price

    @property
    def last_known_timestamp(self) -> "datetime | None":
        """The exchange timestamp of the tick `last_known_price` came
        from -- None until the first valid tick. Paired with
        last_known_price so a caller can judge its own freshness (via
        market_data.quality.SourceHealth.from_bar_timestamp, the same
        freshness math every other bar in this project is judged by)
        rather than assuming it is always "now"."""
        return self._last_known_timestamp
