"""Phase 15 §23 unit tests: CandleBuilder tick-to-OHLCVBar aggregation.
Pure, synthetic ticks -- no network, no Dhan connection.
"""
from datetime import datetime, timedelta, timezone

import pytest

from live.dhan.candle_builder import CandleBuilder
from market.data_provider import DataSource, DataStatus


def _ts(second_of_epoch: int) -> datetime:
    return datetime.fromtimestamp(second_of_epoch, tz=timezone.utc)


def test_first_tick_never_returns_a_completed_bar():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    result = builder.on_tick(price=100.0, volume=10, timestamp=_ts(0), received_at=_ts(0))
    assert result is None


def test_ticks_within_the_same_bucket_never_complete_a_bar():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(0), received_at=_ts(0))
    result = builder.on_tick(price=101.0, volume=5, timestamp=_ts(30), received_at=_ts(30))
    assert result is None  # still inside the same 60-second bucket


def test_a_tick_in_the_next_bucket_completes_the_previous_bar():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(5), received_at=_ts(5))
    builder.on_tick(price=102.0, volume=5, timestamp=_ts(30), received_at=_ts(30))
    bar = builder.on_tick(price=99.0, volume=3, timestamp=_ts(61), received_at=_ts(61))  # crosses into the next 60s bucket
    assert bar is not None
    assert bar.open == 100.0
    assert bar.high == 102.0
    assert bar.low == 100.0  # 99.0 belongs to the NEW bucket the completing tick started -- not part of this completed bar
    assert bar.close == 102.0  # last tick BEFORE the boundary crossing, not the crossing tick itself


def test_a_late_out_of_order_tick_is_dropped_not_merged_into_the_current_bucket():
    """Adversarial-audit finding: a tick whose OWN exchange timestamp
    belongs to a bucket EARLIER than the one already in progress (a
    real, plausible scenario -- server-side reordering, reconnect
    redelivery, interleaved packet types) must be dropped, never merged
    into the current bucket. Merging it would corrupt an already-valid
    bar's high/low/close/volume with a price that was never actually
    observed during that bucket, and could even push the bar's own
    last_source_timestamp BEFORE its declared bucket timestamp."""
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(65), received_at=_ts(65))  # bucket 60
    builder.on_tick(price=105.0, volume=5, timestamp=_ts(90), received_at=_ts(90))  # still bucket 60

    late_result = builder.on_tick(price=999.0, volume=100, timestamp=_ts(10), received_at=_ts(200))  # belongs to bucket 0 -- EARLIER
    assert late_result is None  # dropped, not a completed bar

    bar = builder.on_tick(price=110.0, volume=3, timestamp=_ts(125), received_at=_ts(125))  # crosses into bucket 120, completes bucket 60
    assert bar is not None
    assert bar.high == 105.0  # NOT 999.0 -- the late tick must never have touched this bucket's high
    assert bar.low == 100.0
    assert bar.close == 105.0  # NOT 999.0
    assert bar.volume == 15.0  # 10 + 5 -- the late tick's volume=100 must never have been summed in
    assert bar.source_timestamp >= bar.timestamp  # never pushed backward by the dropped late tick


def test_a_late_tick_does_not_start_a_new_bucket_when_no_bucket_is_in_progress():
    """The late-tick guard only applies when a bucket is ALREADY in
    progress -- the very first tick ever received always starts a fresh
    bucket, regardless of what timestamp it carries."""
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    result = builder.on_tick(price=100.0, volume=10, timestamp=_ts(5), received_at=_ts(5))
    assert result is None  # first tick, no bucket to be "late" against


def test_ohlc_correctness_within_one_bucket():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(0), received_at=_ts(0))
    builder.on_tick(price=105.0, volume=5, timestamp=_ts(10), received_at=_ts(10))
    builder.on_tick(price=98.0, volume=7, timestamp=_ts(20), received_at=_ts(20))
    builder.on_tick(price=101.0, volume=2, timestamp=_ts(30), received_at=_ts(30))
    bar = builder.on_tick(price=999.0, volume=0, timestamp=_ts(60), received_at=_ts(60))  # forces completion
    assert bar.open == 100.0
    assert bar.high == 105.0
    assert bar.low == 98.0
    assert bar.close == 101.0
    assert bar.volume == 10 + 5 + 7 + 2


def test_volume_sums_across_ticks_in_the_bucket():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=100, timestamp=_ts(0), received_at=_ts(0))
    builder.on_tick(price=100.0, volume=50, timestamp=_ts(1), received_at=_ts(1))
    bar = builder.on_tick(price=100.0, volume=0, timestamp=_ts(61), received_at=_ts(61))
    assert bar.volume == 150


def test_bar_is_tagged_source_dhan_status_live():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=1, timestamp=_ts(0), received_at=_ts(0))
    bar = builder.on_tick(price=100.0, volume=1, timestamp=_ts(61), received_at=_ts(61))
    assert bar.source == DataSource.DHAN
    assert bar.status == DataStatus.LIVE


def test_bucket_boundaries_are_floored_to_the_interval_from_epoch():
    """A "5m" bucket starting mid-interval must floor to the standard
    5-minute-from-epoch boundary, not to the first tick's own timestamp."""
    builder = CandleBuilder(symbol="RELIANCE", interval="5m")
    builder.on_tick(price=100.0, volume=1, timestamp=_ts(310), received_at=_ts(310))  # 5m bucket = [300, 600)
    bar = builder.on_tick(price=101.0, volume=1, timestamp=_ts(601), received_at=_ts(601))  # next bucket
    assert bar.timestamp == _ts(300)


def test_a_silent_bucket_with_no_ticks_produces_no_bar():
    """No wall-clock timer forces a bar out -- a gap in ticks just means
    no bar for that period, never a manufactured flat bar."""
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=1, timestamp=_ts(0), received_at=_ts(0))
    # jump straight to bucket #5 (300s later) with no ticks for buckets 1-4 in between
    bar = builder.on_tick(price=105.0, volume=1, timestamp=_ts(300), received_at=_ts(300))
    assert bar is not None
    assert bar.timestamp == _ts(0)  # only the bucket that actually had ticks is ever emitted
    # no bars were silently manufactured for buckets 1-4 -- there is no API to retrieve them


def test_flush_returns_the_in_progress_bucket_without_a_next_tick():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(0), received_at=_ts(0))
    bar = builder.flush()
    assert bar is not None
    assert bar.close == 100.0


def test_flush_with_no_ticks_yet_returns_none():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    assert builder.flush() is None


def test_flush_does_not_double_emit_after_natural_completion():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=1, timestamp=_ts(0), received_at=_ts(0))
    first_bar = builder.on_tick(price=101.0, volume=1, timestamp=_ts(61), received_at=_ts(61))
    assert first_bar is not None
    # a fresh bucket has started (from the second on_tick call) -- flush() now returns THAT bucket, not a duplicate of the first
    second = builder.flush()
    assert second.timestamp != first_bar.timestamp
    assert second.open == 101.0


# --- is_partial labeling + last_known_price/timestamp (LIVE SYSTEM HARDENING
# mission, Part 2: raw tick / last-known-price / partial-candle / completed-
# candle must be genuinely distinguishable, not just internally computed and
# never exposed) ------------------------------------------------------------


def test_flush_marks_the_returned_bar_as_partial():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(0), received_at=_ts(0))
    bar = builder.flush()
    assert bar.is_partial is True


def test_a_naturally_completed_bar_via_on_tick_is_never_marked_partial():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(0), received_at=_ts(0))
    bar = builder.on_tick(price=101.0, volume=5, timestamp=_ts(61), received_at=_ts(61))
    assert bar is not None
    assert bar.is_partial is False


def test_last_known_price_is_none_before_any_tick():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    assert builder.last_known_price is None
    assert builder.last_known_timestamp is None


def test_last_known_price_updates_on_every_accepted_tick_even_mid_bucket():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(0), received_at=_ts(0))
    assert builder.last_known_price == 100.0
    assert builder.last_known_timestamp == _ts(0)

    builder.on_tick(price=102.0, volume=5, timestamp=_ts(10), received_at=_ts(10))  # same bucket, no bar completed
    assert builder.last_known_price == 102.0
    assert builder.last_known_timestamp == _ts(10)


def test_last_known_price_is_unchanged_by_a_rejected_invalid_tick():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(0), received_at=_ts(0))
    builder.on_tick(price=-5.0, volume=1, timestamp=_ts(10), received_at=_ts(10))  # rejected: non-positive
    assert builder.last_known_price == 100.0  # the bad tick's price never touched it


def test_flush_is_a_pure_peek_and_does_not_disturb_the_bucket_or_last_known_price():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(0), received_at=_ts(0))
    builder.flush()
    builder.flush()  # repeated peek -- must not mutate anything
    assert builder.last_known_price == 100.0

    completed = builder.on_tick(price=105.0, volume=1, timestamp=_ts(61), received_at=_ts(61))
    assert completed is not None
    assert completed.close == 100.0  # the peeks above never altered the real bucket's own close
    assert completed.is_partial is False


# --- tick-level sanity validation (Phase 13, live data stress testing) ------


def test_a_non_positive_price_tick_is_dropped_and_never_corrupts_the_bucket():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(0), received_at=_ts(0))

    result = builder.on_tick(price=0.0, volume=5, timestamp=_ts(10), received_at=_ts(10))
    assert result is None
    result = builder.on_tick(price=-50.0, volume=5, timestamp=_ts(20), received_at=_ts(20))
    assert result is None

    bar = builder.flush()
    assert bar.open == 100.0
    assert bar.high == 100.0
    assert bar.low == 100.0
    assert bar.close == 100.0  # neither garbage tick ever touched the bucket


def test_a_negative_volume_tick_is_dropped_and_never_corrupts_the_bucket():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(0), received_at=_ts(0))

    result = builder.on_tick(price=101.0, volume=-5, timestamp=_ts(10), received_at=_ts(10))
    assert result is None

    bar = builder.flush()
    assert bar.volume == 10.0  # the negative-volume tick's -5 must never have been summed in


def test_an_implausible_price_spike_is_dropped_and_never_corrupts_the_bucket():
    # Real, plausible cause: a corrupted-but-well-formed tick (still a
    # positive float, so OHLCVBar's own gt=0 validation never catches
    # it) -- e.g. a decimal-point/units error upstream. Default
    # threshold is 20%; a 10x spike is unambiguously implausible for a
    # single tick.
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(0), received_at=_ts(0))

    result = builder.on_tick(price=1000.0, volume=5, timestamp=_ts(10), received_at=_ts(10))
    assert result is None

    bar = builder.flush()
    assert bar.high == 100.0
    assert bar.close == 100.0


def test_a_reasonable_price_move_within_threshold_is_still_accepted():
    # Proves the check isn't overly strict -- a genuine 5% intra-bucket
    # move must still be accepted normally.
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(0), received_at=_ts(0))
    result = builder.on_tick(price=105.0, volume=5, timestamp=_ts(10), received_at=_ts(10))
    assert result is None  # still same bucket, not a completed bar

    bar = builder.flush()
    assert bar.high == 105.0
    assert bar.close == 105.0


def test_the_very_first_tick_ever_is_always_accepted_regardless_of_magnitude():
    # No prior REAL price exists yet to compare against -- a known,
    # documented scope limit (a garbage FIRST tick could still seed a
    # bucket's open), not silently unaddressed.
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    result = builder.on_tick(price=999_999.0, volume=1, timestamp=_ts(0), received_at=_ts(0))
    assert result is None  # not a completed bar (first tick), but NOT dropped either

    bar = builder.flush()
    assert bar.open == 999_999.0


def test_implausible_tick_crossing_a_bucket_boundary_still_completes_the_prior_bucket():
    # A bucket's completion is a question of ELAPSED EXCHANGE TIME, which
    # a tick's own timestamp can still be trusted for even when its PRICE
    # cannot be -- an implausible tick must not indefinitely delay
    # finalizing an already-elapsed, otherwise-legitimate prior bar.
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(0), received_at=_ts(0))
    builder.on_tick(price=102.0, volume=5, timestamp=_ts(30), received_at=_ts(30))

    # Crosses into bucket 60 with an implausible price -- must still complete bucket 0.
    result = builder.on_tick(price=10_000.0, volume=1, timestamp=_ts(65), received_at=_ts(65))
    assert result is not None
    assert result.open == 100.0
    assert result.close == 102.0
    assert result.high == 102.0  # the garbage 10,000.0 must never have touched this bucket's high

    # The garbage tick must NOT have seeded bucket 60 either -- only a
    # genuinely valid tick starts it, using the last REAL price (102.0)
    # as its own comparison baseline, unaffected by the garbage tick.
    builder.on_tick(price=101.5, volume=2, timestamp=_ts(70), received_at=_ts(70))
    bar = builder.flush()
    assert bar.open == 101.5  # NOT 10_000.0


def test_rejected_tick_counts_starts_at_zero_for_every_known_reason():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    assert builder.rejected_tick_counts == {
        "non_positive_price": 0, "negative_volume": 0, "implausible_deviation": 0, "late_out_of_order": 0,
        "implausible_timestamp": 0, "non_finite_value": 0,
    }


def test_rejected_tick_counts_increments_by_reason():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(0), received_at=_ts(0))

    builder.on_tick(price=0.0, volume=5, timestamp=_ts(10), received_at=_ts(10))
    assert builder.rejected_tick_counts["non_positive_price"] == 1

    builder.on_tick(price=101.0, volume=-5, timestamp=_ts(11), received_at=_ts(11))
    assert builder.rejected_tick_counts["negative_volume"] == 1

    builder.on_tick(price=1000.0, volume=1, timestamp=_ts(12), received_at=_ts(12))
    assert builder.rejected_tick_counts["implausible_deviation"] == 1

    builder.on_tick(price=102.0, volume=1, timestamp=_ts(65), received_at=_ts(65))  # crosses into bucket 60, _last_known_price=102.0
    # Price-plausible (within threshold of 102.0) but belongs to an EARLIER
    # bucket than the one now in progress -- must hit the late-tick path,
    # not the plausibility check.
    builder.on_tick(price=101.0, volume=1, timestamp=_ts(5), received_at=_ts(5))
    assert builder.rejected_tick_counts["late_out_of_order"] == 1

    # A valid tick must never increment any counter.
    assert builder.rejected_tick_counts["non_positive_price"] == 1
    assert builder.rejected_tick_counts["negative_volume"] == 1
    assert builder.rejected_tick_counts["implausible_deviation"] == 1


def test_max_tick_deviation_pct_none_disables_the_plausibility_check():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m", max_tick_deviation_pct=None)
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(0), received_at=_ts(0))
    result = builder.on_tick(price=10_000.0, volume=1, timestamp=_ts(10), received_at=_ts(10))
    assert result is None  # still same bucket, not completed -- but NOT dropped as implausible either

    bar = builder.flush()
    assert bar.high == 10_000.0


# --- timestamp plausibility (live-market-readiness audit finding) -----------
#
# Real bug found via adversarial audit, reproduced here before being fixed:
# on_tick trusted a tick's own `timestamp` unconditionally to compute its
# bucket, with no plausibility check at all (unlike price, which IS
# checked). A single tick with a valid price but a corrupted/wildly-future
# timestamp (e.g. a decode glitch in Dhan's LTT field) would seed a bucket
# dated far in the future; every subsequent, genuinely-real tick would then
# have an earlier bucket_start than that seeded state and be rejected
# FOREVER as "late_out_of_order", with no self-recovery -- candle
# production for that symbol permanently stops. The fix compares each
# tick's timestamp against this builder's own LAST KNOWN GOOD timestamp
# (mirroring _last_known_price's identical pattern), not against
# `received_at` -- a wall-clock comparison would falsely reject every tick
# in this entire test file, whose synthetic timestamps are deliberately
# small epoch offsets, not real "now" values. One consequence, stated
# explicitly rather than hidden: a CORRUPTED VERY FIRST TICK (no prior
# timestamp to compare against yet) is not covered by this specific
# check -- every test below therefore seeds one real tick first, matching
# the realistic, hours-long-live-session shape of the actual risk found.


def test_a_wildly_future_timestamp_does_not_permanently_kill_candle_production():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(0), received_at=_ts(0))  # establishes a real baseline

    # A tick with an otherwise-valid price but a garbage timestamp ~30 days
    # ahead of the last real one -- e.g. a corrupted LTT field, not caught
    # by the price-deviation check since the price itself is fine.
    corrupted_result = builder.on_tick(price=101.0, volume=1, timestamp=_ts(30 * 86400), received_at=_ts(1))
    assert corrupted_result is None  # rejected -- never seeds/replaces the real bucket

    # Every subsequent tick uses REAL, current timestamps. Before the fix,
    # these would all be endlessly rejected as "late_out_of_order" against
    # the corrupted future bucket the bad tick would otherwise have seeded.
    result_2 = builder.on_tick(price=102.0, volume=5, timestamp=_ts(30), received_at=_ts(30))
    assert result_2 is None  # still bucket 0, no bar yet -- but must not be REJECTED
    assert builder.rejected_tick_counts["late_out_of_order"] == 0

    bar = builder.on_tick(price=103.0, volume=5, timestamp=_ts(61), received_at=_ts(61))
    assert bar is not None  # candle production recovered and completed a real bar
    assert bar.open == 100.0
    assert bar.close == 102.0  # the corrupted 101.0 tick never merged in


def test_a_wildly_future_timestamp_mid_bucket_does_not_prematurely_close_the_real_bucket():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(0), received_at=_ts(0))
    builder.on_tick(price=102.0, volume=5, timestamp=_ts(30), received_at=_ts(30))

    # A garbage-future-timestamped tick arrives WHILE a real bucket is
    # already open -- must not be trusted to finalize/roll over that bucket
    # early (it is not a genuine "next bucket" tick, its timestamp is
    # simply corrupted).
    corrupted_result = builder.on_tick(price=101.0, volume=1, timestamp=_ts(30 * 86400), received_at=_ts(31))
    assert corrupted_result is None

    # The real bucket is still open and accumulates the next genuine tick.
    bar = builder.on_tick(price=105.0, volume=2, timestamp=_ts(61), received_at=_ts(61))
    assert bar is not None
    assert bar.high == 102.0  # the corrupted 101.0 tick with the garbage timestamp never merged in
    assert bar.close == 102.0


def test_implausible_timestamp_increments_its_own_rejection_counter():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(0), received_at=_ts(0))
    builder.on_tick(price=101.0, volume=1, timestamp=_ts(30 * 86400), received_at=_ts(1))
    assert builder.rejected_tick_counts["implausible_timestamp"] == 1


def test_max_timestamp_skew_seconds_none_disables_the_timestamp_plausibility_check():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m", max_timestamp_skew_seconds=None)
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(0), received_at=_ts(0))
    # With the check disabled, the garbage-future timestamp is trusted again
    # (reproducing this module's original, pre-fix behavior exactly) -- it
    # rolls the bucket over and completes bucket 0.
    result = builder.on_tick(price=101.0, volume=1, timestamp=_ts(30 * 86400), received_at=_ts(1))
    assert result is not None
    assert result.close == 100.0
    assert builder.rejected_tick_counts["implausible_timestamp"] == 0


def test_a_moderately_late_tick_within_tolerance_is_not_treated_as_implausible():
    # Mirrors the existing late-tick test's own 190s receipt gap -- well
    # within any reasonable skew tolerance, must still hit the ordinary
    # late/out-of-order path, not the new implausible-timestamp path.
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(65), received_at=_ts(65))
    late_result = builder.on_tick(price=999.0, volume=100, timestamp=_ts(10), received_at=_ts(200))
    assert late_result is None
    assert builder.rejected_tick_counts["late_out_of_order"] == 1
    assert builder.rejected_tick_counts["implausible_timestamp"] == 0


def test_corrupted_very_first_tick_is_a_documented_residual_gap():
    # Stated, not hidden: with NO prior tick to compare against, the very
    # first tick a fresh builder ever receives is unconditionally trusted
    # as the initial baseline -- not covered by the timestamp-plausibility
    # check itself. NARROWED (2026-09-17 live incident + fix) by the
    # cold-start self-recovery below: a bad first tick no longer poisons
    # the builder PERMANENTLY -- it now self-heals the moment two
    # subsequent real ticks agree with each other (see the tests below).
    # This test documents only the remaining, narrower boundary: the
    # single bad first tick itself is still silently accepted as seed,
    # not flagged as implausible.
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    result = builder.on_tick(price=100.0, volume=10, timestamp=_ts(30 * 86400), received_at=_ts(0))
    assert result is None  # no bar yet either way
    assert builder.rejected_tick_counts["implausible_timestamp"] == 0  # NOT caught -- documented limitation


# --- cold-start self-recovery (2026-09-17 live incident: HINDUNILVR.NS / ---
# --- SUNPHARMA.NS each received a stale first tick carrying the PREVIOUS --
# --- trading day's timestamp, silently accepted as baseline, then --------
# --- rejected every genuinely-current tick for the rest of the session) --


def test_a_poisoned_first_tick_self_heals_once_a_second_consistent_tick_arrives():
    builder = CandleBuilder(symbol="HINDUNILVR", interval="1m")
    # Stale first tick -- exactly today's real incident shape: a leftover
    # snapshot from the previous session, trusted unconditionally as seed.
    poisoned = builder.on_tick(price=100.0, volume=0, timestamp=_ts(0), received_at=_ts(30 * 86400))
    assert poisoned is None

    # First genuinely current tick disagrees with the poisoned baseline --
    # rejected (matches pre-existing behavior exactly), remembered as a
    # pending candidate, NOT yet trusted off a single data point alone.
    real_tick_1 = builder.on_tick(price=101.0, volume=0, timestamp=_ts(30 * 86400 + 5), received_at=_ts(30 * 86400 + 5))
    assert real_tick_1 is None
    assert builder.rejected_tick_counts["implausible_timestamp"] == 1

    # A second genuinely current tick agrees with the first -- two
    # independent ticks agreeing with each other is enough to conclude the
    # ORIGINAL (poisoned) baseline was the anomalous one. Baseline
    # switches, the poisoned bucket state is discarded, and THIS tick
    # becomes the first tick of a fresh bucket built on the new baseline
    # (real_tick_1 itself was rejected and never touched any bucket, so
    # its own price is not recoverable -- one tick's worth of recovery
    # latency is the accepted cost of not blindly trusting a single
    # disagreement, see __init__ docstring).
    real_tick_2 = builder.on_tick(price=102.0, volume=0, timestamp=_ts(30 * 86400 + 40), received_at=_ts(30 * 86400 + 40))
    assert real_tick_2 is None  # starts the fresh bucket, no bar yet
    assert builder.rejected_tick_counts["implausible_timestamp"] == 1  # not incremented -- confirmed, not rejected

    # Recovery confirmed: subsequent real ticks are no longer rejected and
    # candle production resumes normally.
    bar = builder.on_tick(price=103.0, volume=0, timestamp=_ts(30 * 86400 + 65), received_at=_ts(30 * 86400 + 65))
    assert bar is not None
    assert bar.open == 102.0  # real_tick_2, the confirmed baseline's first tick
    assert bar.close == 102.0  # only one tick was in that fresh bucket
    assert builder.rejected_tick_counts["implausible_timestamp"] == 1  # never grew further


def test_multiple_disagreeing_startup_ticks_keep_reseeding_the_candidate_until_two_finally_agree():
    builder = CandleBuilder(symbol="SUNPHARMA", interval="1m")
    builder.on_tick(price=100.0, volume=0, timestamp=_ts(0), received_at=_ts(0))  # poisoned seed

    # A noisy startup: several disagreeing ticks, none of which agree with
    # EACH OTHER yet (each pairwise gap here deliberately exceeds the
    # default 3600s skew threshold) -- must keep rejecting and keep
    # updating the pending candidate to the MOST RECENT disagreement,
    # never falsely confirm off a single data point, and never leave the
    # original baseline touched.
    t1 = builder.on_tick(price=101.0, volume=0, timestamp=_ts(50_000), received_at=_ts(50_000))
    assert t1 is None
    assert builder.rejected_tick_counts["implausible_timestamp"] == 1
    t2 = builder.on_tick(price=102.0, volume=0, timestamp=_ts(200_000), received_at=_ts(200_000))  # disagrees with t1 too
    assert t2 is None
    assert builder.rejected_tick_counts["implausible_timestamp"] == 2

    # Finally, a tick that agrees with the MOST RECENT candidate (t2) --
    # confirms and switches baseline to this pair, discarding any bucket
    # state (there is none yet -- every prior tick here was rejected) and
    # becoming the fresh bucket's own first tick.
    t3 = builder.on_tick(price=103.0, volume=0, timestamp=_ts(200_030), received_at=_ts(200_030))
    assert t3 is None  # starts the fresh bucket, no bar yet
    assert builder.rejected_tick_counts["implausible_timestamp"] == 2  # not incremented -- this tick confirmed, not rejected

    bar = builder.on_tick(price=104.0, volume=0, timestamp=_ts(200_065), received_at=_ts(200_065))
    assert bar is not None
    assert bar.open == 103.0  # t3, the confirmed baseline's first tick -- not t1, t2, or the poisoned seed
    assert bar.close == 103.0  # only one tick was in that fresh bucket


def test_cold_start_self_recovery_does_not_weaken_the_existing_mid_session_single_bad_tick_protection():
    # Direct regression guard for the FIRST (rejected) fix design: a
    # single stray bad tick arriving mid-session, with an already-good
    # baseline, must NOT be allowed to displace that baseline just because
    # it happens before two OTHER ticks have confirmed it. This exercises
    # the exact same tick sequence as
    # test_a_wildly_future_timestamp_does_not_permanently_kill_candle_production
    # explicitly re-asserting it here as a named regression case for this
    # specific fix.
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(0), received_at=_ts(0))  # good baseline

    bad_tick = builder.on_tick(price=101.0, volume=1, timestamp=_ts(30 * 86400), received_at=_ts(1))
    assert bad_tick is None
    assert builder.rejected_tick_counts["implausible_timestamp"] == 1

    # The next tick agrees with the ORIGINAL good baseline, not with the
    # single bad tick -- must confirm the ORIGINAL baseline, not be
    # rejected as "disagreeing with a switched-to bad baseline".
    result_2 = builder.on_tick(price=102.0, volume=5, timestamp=_ts(30), received_at=_ts(30))
    assert result_2 is None
    assert builder.rejected_tick_counts["implausible_timestamp"] == 1  # not incremented again

    bar = builder.on_tick(price=103.0, volume=5, timestamp=_ts(61), received_at=_ts(61))
    assert bar is not None
    assert bar.open == 100.0
    assert bar.close == 102.0  # the single bad tick never merged in, original baseline preserved throughout


# --- Adversarial hardening pass (autonomous mission, same day) --------------
# Broader adversarial coverage requested against CandleBuilder as a critical
# financial-data boundary. Several scenarios are ALREADY covered above and
# are not duplicated here (previous-day first tick, wildly-future timestamp
# mid-session, out-of-order ticks, repeated disagreeing startup ticks). Two
# scenarios are explicitly OUT OF SCOPE for this file: malformed WIRE packets
# (handled upstream by live/dhan/wire.py's parse_packet + DhanWireFormatError,
# before anything ever reaches on_tick) and cross-symbol contamination at the
# DhanMarketDataSource level (structurally prevented there by one dict entry
# per symbol -- test_independent_instances_never_share_state below covers
# the CandleBuilder-level half of that guarantee).


def test_previous_day_first_two_consecutive_stale_ticks_now_self_heals_instead_of_confirming():
    """FIXED (2026-09-21 real live incident): this test previously
    documented a genuine, then-undismissed residual gap -- the two-tick-
    confirmation mechanism assumed a SECOND disagreeing tick that agrees
    with the first is independent evidence the ORIGINAL baseline was bad,
    but if BOTH of the first two ticks a fresh builder ever received were
    themselves stale (e.g. two fragments of the same corrupted overnight
    snapshot), they trivially agreed with each other and PERMANENTLY
    confirmed the wrong baseline. This was judged "not fixed" on
    2026-09-18 on the reasoning that the real 2026-09-17 incident always
    showed exactly ONE stale seed tick, never two, so there was no real-
    world evidence this specific pattern occurred -- that reasoning was
    proven wrong on 2026-09-21: a real Monday cold start (after a weekend
    gap) produced EXACTLY this pattern across all 15 live fleet symbols
    simultaneously (a stale Friday-afternoon LTP-snapshot first tick,
    immediately followed by a second fragment of the same stale snapshot
    agreeing with it), permanently confirming Friday's timestamp and
    producing ZERO real candles fleet-wide until diagnosed and fixed.

    Fix: a baseline can only be CONFIRMED (not merely internally
    consistent) if the confirming tick's own `timestamp` is plausible
    relative to its own `received_at` (see
    CandleBuilder._plausible_relative_to_receipt and
    `max_cold_start_wall_clock_skew_seconds`'s own docstring). Two stale-
    but-mutually-consistent ticks now correctly fail to confirm; a
    genuinely current tick still self-heals normally."""
    builder = CandleBuilder(symbol="HINDUNILVR", interval="1m")
    # received_at is the REAL wall-clock moment each tick actually arrived
    # -- distinct from the stale `timestamp` each one claims, exactly
    # matching the real incident's own shape (arrived today, claims to be
    # from a stale snapshot).
    now = _ts(30 * 86400)
    stale_seed = builder.on_tick(price=100.0, volume=0, timestamp=_ts(0), received_at=now)
    assert stale_seed is None
    assert builder._baseline_confirmed is False

    # A second fragment of the SAME stale snapshot, moments later --
    # agrees with the first stale tick numerically, but is EQUALLY
    # implausible relative to when it was actually received. Must NOT
    # confirm (the fixed behavior -- previously this falsely confirmed).
    stale_confirm_attempt = builder.on_tick(price=100.5, volume=0, timestamp=_ts(5), received_at=now)
    assert stale_confirm_attempt is None
    assert builder._baseline_confirmed is False  # the fix: no longer falsely confirmed
    assert builder.rejected_tick_counts["implausible_timestamp"] == 1  # now correctly counted as a rejection, not a silent confirm

    # Genuinely current ticks (received_at matches timestamp -- real,
    # current data) still self-heal normally, exactly as designed.
    real_tick_1 = builder.on_tick(price=2500.0, volume=0, timestamp=now, received_at=now)
    assert real_tick_1 is None
    assert builder.rejected_tick_counts["implausible_timestamp"] == 2
    real_tick_2 = builder.on_tick(price=2501.0, volume=0, timestamp=now + timedelta(seconds=60), received_at=now + timedelta(seconds=60))
    assert real_tick_2 is None  # confirms and switches baseline, starts a fresh bucket -- no bar yet
    assert builder._baseline_confirmed is True
    assert builder.rejected_tick_counts["implausible_timestamp"] == 2  # not incremented -- this tick confirmed, not rejected

    bar = builder.on_tick(price=2502.0, volume=0, timestamp=now + timedelta(seconds=125), received_at=now + timedelta(seconds=125))
    assert bar is not None
    assert bar.open == 2501.0  # real_tick_2, the confirmed baseline's first tick -- the stale ticks never merged into any bucket


def test_two_mutually_agreeing_pending_candidates_that_are_both_stale_do_not_confirm_either():
    """The OTHER confirmation point this fix closes (the "switch to a new
    pending candidate" branch, distinct from the "agrees with the
    original baseline" branch covered above): if a tick disagrees with
    the current baseline, gets remembered as pending, and a LATER tick
    agrees with THAT pending candidate -- but both are equally implausible
    relative to their own real receipt time -- confirmation must still be
    refused, and the loop must keep running until a genuinely current
    tick arrives."""
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    now = _ts(30 * 86400)

    # First tick: a real, current baseline (received_at matches timestamp).
    builder.on_tick(price=100.0, volume=0, timestamp=now, received_at=now)

    # Second and third ticks: two DIFFERENT stale fragments that happen to
    # agree with EACH OTHER (not with the current baseline), both received
    # "now" in real wall-clock terms despite claiming an ancient timestamp.
    stale_a = builder.on_tick(price=50.0, volume=0, timestamp=_ts(0), received_at=now)
    assert stale_a is None
    assert builder.rejected_tick_counts["implausible_timestamp"] == 1

    stale_b = builder.on_tick(price=50.5, volume=0, timestamp=_ts(3), received_at=now)  # agrees with stale_a (3s apart), but still implausible
    assert stale_b is None
    assert builder._baseline_confirmed is False  # must NOT have switched to the stale pair
    assert builder.rejected_tick_counts["implausible_timestamp"] == 2

    # The baseline is still the original, real one -- a subsequent real
    # tick close to it confirms normally, unaffected.
    real_confirm = builder.on_tick(price=100.5, volume=0, timestamp=now + timedelta(seconds=10), received_at=now + timedelta(seconds=10))
    assert real_confirm is None
    assert builder._baseline_confirmed is True

    bar = builder.on_tick(price=101.0, volume=0, timestamp=now + timedelta(seconds=65), received_at=now + timedelta(seconds=65))
    assert bar is not None
    assert bar.open == 100.0  # the ORIGINAL real baseline, never displaced by the stale-but-mutually-agreeing pair


def test_max_cold_start_wall_clock_skew_seconds_none_restores_the_exact_pre_fix_behavior():
    """Matches this project's consistent 'None disables' convention --
    a caller that explicitly wants the pre-2026-09-21 behavior (trust
    internal tick-to-tick agreement alone, no wall-clock cross-check) can
    still get it."""
    builder = CandleBuilder(symbol="HINDUNILVR", interval="1m", max_cold_start_wall_clock_skew_seconds=None)
    now = _ts(30 * 86400)
    builder.on_tick(price=100.0, volume=0, timestamp=_ts(0), received_at=now)
    # A second stale fragment, agreeing with the first -- with the check
    # disabled, this DOES falsely confirm, exactly like before this fix.
    builder.on_tick(price=100.5, volume=0, timestamp=_ts(5), received_at=now)
    assert builder._baseline_confirmed is True
    assert builder.rejected_tick_counts["implausible_timestamp"] == 0


def test_previous_day_stale_tick_then_current_day_ticks_self_heals_with_real_calendar_dates():
    """Same self-healing property as
    test_a_poisoned_first_tick_self_heals_once_a_second_consistent_tick_
    arrives, but with genuine calendar-crossing datetimes (2026-09-16 ->
    2026-09-17) rather than relative epoch offsets, to make the
    previous-day/current-day framing this scenario is named for concrete
    and undeniable -- mirrors the exact real HINDUNILVR.NS incident dates."""
    builder = CandleBuilder(symbol="HINDUNILVR", interval="1m")
    poisoned = builder.on_tick(
        price=2500.0, volume=0,
        timestamp=datetime(2026, 9, 16, 10, 26, 9, tzinfo=timezone.utc),
        received_at=datetime(2026, 9, 16, 10, 26, 9, tzinfo=timezone.utc),
    )
    assert poisoned is None

    real_tick_1 = builder.on_tick(
        price=2510.0, volume=0,
        timestamp=datetime(2026, 9, 17, 9, 15, 30, tzinfo=timezone.utc),
        received_at=datetime(2026, 9, 17, 9, 15, 30, tzinfo=timezone.utc),
    )
    assert real_tick_1 is None
    assert builder.rejected_tick_counts["implausible_timestamp"] == 1

    real_tick_2 = builder.on_tick(
        price=2511.0, volume=0,
        timestamp=datetime(2026, 9, 17, 9, 15, 45, tzinfo=timezone.utc),
        received_at=datetime(2026, 9, 17, 9, 15, 45, tzinfo=timezone.utc),
    )
    assert real_tick_2 is None  # switches baseline to 2026-09-17, starts a fresh bucket
    assert builder.rejected_tick_counts["implausible_timestamp"] == 1  # not incremented -- confirmed, not rejected

    bar = builder.on_tick(
        price=2512.0, volume=0,
        timestamp=datetime(2026, 9, 17, 9, 16, 30, tzinfo=timezone.utc),
        received_at=datetime(2026, 9, 17, 9, 16, 30, tzinfo=timezone.utc),
    )
    assert bar is not None
    assert bar.open == 2511.0  # the 2026-09-16 tick never merged into any bucket


def test_baseline_confirmed_state_survives_a_simulated_reconnect_and_rejects_a_replayed_stale_packet():
    """A CandleBuilder instance is created once per (symbol, interval) and
    persists for the life of the worker process -- DhanMarketDataSource
    keys `_candle_builders` by symbol via `setdefault`, so a WebSocket
    reconnect (handled entirely inside DhanMarketDataSource) never creates
    a fresh CandleBuilder; the SAME instance, with its already-confirmed
    baseline, keeps receiving ticks after `_on_transport_open` resubscribes.
    This test proves that property is actually safe: once confirmed, a
    reconnect that happens to redeliver a stale snapshot tick (Dhan's own
    overnight-LTP-on-subscribe behavior, the same mechanism that caused the
    real incident, could plausibly also fire again on a mid-session
    reconnect) is rejected via the ordinary CONFIRMED-baseline path --
    permanently correctly, not treated as a fresh cold start that a second
    agreeing bad tick could fool again."""
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=1250.0, volume=0, timestamp=_ts(0), received_at=_ts(0))
    builder.on_tick(price=1251.0, volume=0, timestamp=_ts(10), received_at=_ts(10))
    bar = builder.on_tick(price=1252.0, volume=0, timestamp=_ts(65), received_at=_ts(65))
    assert bar is not None  # baseline now confirmed, real candle production underway

    # Simulated reconnect: a stale snapshot tick arrives, matching the
    # real incident's own mechanism (Dhan resends an old LTP on a fresh
    # subscribe). Rejected via the confirmed path -- a single rejection,
    # not a re-opened cold-start window.
    replayed_stale = builder.on_tick(price=1200.0, volume=0, timestamp=_ts(30 * 86400), received_at=_ts(90))
    assert replayed_stale is None
    assert builder.rejected_tick_counts["implausible_timestamp"] == 1

    # A SECOND tick agreeing with that stale replay must NOT be able to
    # re-poison an already-confirmed baseline -- unlike the cold-start
    # case, there is no pending-candidate mechanism active anymore.
    replayed_stale_2 = builder.on_tick(price=1201.0, volume=0, timestamp=_ts(30 * 86400 + 5), received_at=_ts(95))
    assert replayed_stale_2 is None
    assert builder.rejected_tick_counts["implausible_timestamp"] == 2  # rejected too, baseline never moved

    # Real, current ticks continue to be accepted normally throughout.
    bar2 = builder.on_tick(price=1253.0, volume=0, timestamp=_ts(125), received_at=_ts(125))
    assert bar2 is not None
    assert bar2.close == 1252.0  # unaffected by either replayed stale tick


def test_missing_minute_buckets_are_skipped_not_fabricated():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=1, timestamp=_ts(0), received_at=_ts(0))  # bucket 0
    builder.on_tick(price=101.0, volume=1, timestamp=_ts(30), received_at=_ts(30))  # still bucket 0

    # Jumps straight to bucket 240 (minute 4) -- buckets 60/120/180 (minutes
    # 1-3) see zero ticks. Only bucket 0's bar is ever produced; the empty
    # buckets never get a synthetic/fabricated bar of their own.
    bar = builder.on_tick(price=105.0, volume=1, timestamp=_ts(245), received_at=_ts(245))
    assert bar is not None
    assert bar.timestamp == _ts(0)
    assert bar.close == 101.0  # bucket 0's own last real tick, not interpolated

    # The new bucket (240) was freshly seeded from this tick alone -- no
    # fabricated open/high/low/close for the skipped minutes leaked in.
    partial = builder.flush()
    assert partial.timestamp == _ts(240)
    assert partial.open == partial.high == partial.low == partial.close == 105.0


def test_an_exact_duplicate_timestamp_and_price_tick_does_not_double_count_volume():
    """2026-09-21 signal-funnel forensic audit fix: superseded the OLD
    "documented, not a bug" non-dedup behavior -- now that
    DhanMarketDataSource passes a real per-tick volume (Quote mode LTQ,
    not Ticker mode's always-0.0), an exact-duplicate redelivery (e.g.
    after a reconnect) merging its volume a second time would silently
    inflate volume_trend, directly risking a false "increasing"
    classification neither trend nor momentum data ever supported.
    Price fields remain exactly as idempotent as before -- only the
    duplicate's volume is skipped."""
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10.0, timestamp=_ts(5), received_at=_ts(5))
    builder.on_tick(price=100.0, volume=10.0, timestamp=_ts(5), received_at=_ts(5))  # exact duplicate
    bar = builder.on_tick(price=101.0, volume=1.0, timestamp=_ts(61), received_at=_ts(61))
    assert bar is not None  # this is the COMPLETED first bucket -- the third tick starts a new one
    assert bar.volume == 10.0  # the duplicate's 10.0 was NOT re-added (would be 20.0 without the fix)
    assert bar.open == 100.0
    assert bar.close == 100.0  # unchanged -- price was already idempotent for a repeated price


def test_two_genuinely_distinct_ticks_at_the_same_price_and_timestamp_second_still_only_count_once():
    """The documented, accepted tradeoff of the fix above: two REAL,
    distinct trades that happen to share the same epoch-second timestamp
    and price cannot be told apart from a redelivered duplicate (Dhan's
    packets carry no per-message sequence number) -- this is an explicit,
    narrow false-negative this project accepts (erring toward under- not
    over-counting), not a claim of perfect accounting. This test proves
    the ACTUAL behavior so the tradeoff stays visible, not silently
    assumed."""
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10.0, timestamp=_ts(5), received_at=_ts(5))
    builder.on_tick(price=100.0, volume=7.0, timestamp=_ts(5), received_at=_ts(5))  # a second, real trade -- same second, same price
    bar = builder.on_tick(price=101.0, volume=1.0, timestamp=_ts(61), received_at=_ts(61))
    assert bar is not None  # this is the COMPLETED first bucket -- the third tick starts a new one
    assert bar.volume == 10.0  # the second real trade's 7.0 was NOT counted -- documented tradeoff, not a bug


def test_two_distinct_ticks_at_different_prices_in_the_same_bucket_both_count_their_volume():
    """The ordinary, common case: two different prices within the same
    bucket are never mistaken for a duplicate, regardless of volume."""
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10.0, timestamp=_ts(5), received_at=_ts(5))
    builder.on_tick(price=100.5, volume=7.0, timestamp=_ts(6), received_at=_ts(6))
    bar = builder.on_tick(price=101.0, volume=1.0, timestamp=_ts(61), received_at=_ts(61))
    assert bar is not None
    assert bar.volume == 17.0  # both real, distinct ticks fully counted


def test_the_very_first_tick_of_a_new_bucket_is_never_mistaken_for_a_duplicate_of_the_prior_bucket():
    """Regression guard for the exact off-by-one this fix could have
    introduced: the duplicate check must compare against the PREVIOUS
    tick already merged into the bucket, computed BEFORE a fresh
    _BucketState is seeded -- not after, which would make every bucket's
    own first tick spuriously look like it duplicates itself (freshly
    seeded close/last_source_timestamp are, by construction, identical
    to the incoming tick that just seeded them)."""
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10.0, timestamp=_ts(5), received_at=_ts(5))
    # New bucket -- first tick's own price/timestamp trivially "equal" the
    # freshly-seeded state's own close/last_source_timestamp, but this must
    # NOT be treated as a duplicate of the OLD bucket's last tick.
    bar = builder.on_tick(price=100.0, volume=5.0, timestamp=_ts(65), received_at=_ts(65))
    assert bar is not None  # the first bucket completed
    assert bar.volume == 10.0
    partial = builder.flush()
    assert partial is not None
    assert partial.volume == 5.0  # the new bucket's first tick's volume was NOT dropped


def test_a_delayed_first_tick_with_a_valid_exchange_timestamp_still_works_normally():
    """Bucketing uses the tick's OWN exchange timestamp, never received_at
    -- a first tick that arrives very late in wall-clock terms (e.g. a
    queued/backlogged delivery after a brief network hiccup) but carries a
    perfectly valid exchange timestamp must be treated exactly like an
    ordinary first tick, never penalized for its late receipt."""
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    result = builder.on_tick(price=100.0, volume=1, timestamp=_ts(0), received_at=_ts(500))
    assert result is None
    assert builder.rejected_tick_counts == {
        "non_positive_price": 0, "negative_volume": 0, "implausible_deviation": 0,
        "late_out_of_order": 0, "implausible_timestamp": 0, "non_finite_value": 0,
    }
    assert builder.last_known_price == 100.0


def test_timestamp_regression_after_baseline_confirmed_is_rejected_via_the_correct_path():
    """Two sub-cases, both after baseline confirmation: a small regression
    (still within the skew tolerance) must hit the ordinary late/out-of-
    order path -- exactly the pre-existing, already-tested mid-session
    protection, not a new mechanism -- while a large regression (exceeding
    the skew tolerance) must hit the implausible-timestamp path instead,
    proving both existing guards remain correctly reachable once a
    baseline is confirmed, not just during the unconfirmed cold-start
    window."""
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=1, timestamp=_ts(0), received_at=_ts(0))
    builder.on_tick(price=101.0, volume=1, timestamp=_ts(10), received_at=_ts(10))  # confirms baseline

    small_regression = builder.on_tick(price=999.0, volume=1, timestamp=_ts(-5), received_at=_ts(15))
    assert small_regression is None
    assert builder.rejected_tick_counts["late_out_of_order"] == 1
    assert builder.rejected_tick_counts["implausible_timestamp"] == 0

    large_regression = builder.on_tick(price=998.0, volume=1, timestamp=_ts(10 - 4000), received_at=_ts(16))
    assert large_regression is None
    assert builder.rejected_tick_counts["implausible_timestamp"] == 1
    assert builder.rejected_tick_counts["late_out_of_order"] == 1  # unchanged by the second rejection


def test_a_rapid_packet_burst_within_one_bucket_aggregates_correctly():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    prices = [100.0 + ((i * 37) % 23) * 0.1 for i in range(200)]  # a deterministic pseudo-random-looking walk, all within one bucket
    for i, price in enumerate(prices):
        result = builder.on_tick(price=price, volume=1.0, timestamp=_ts(i % 59), received_at=_ts(i % 59))
        assert result is None  # every tick lands in bucket 0 -- never completes mid-burst

    bar = builder.on_tick(price=200.0, volume=1.0, timestamp=_ts(61), received_at=_ts(61))
    assert bar is not None
    assert bar.open == prices[0]
    assert bar.close == prices[-1]
    assert bar.high == max(prices)
    assert bar.low == min(prices)
    assert bar.volume == float(len(prices))


def test_independent_candle_builder_instances_never_share_state():
    """Cheap regression guard for the isolation guarantee the rest of the
    live pipeline depends on (DhanMarketDataSource keys one CandleBuilder
    per symbol): two separate instances must never observe each other's
    ticks, rejections, or price/timestamp baselines, even when driven
    concurrently with deliberately conflicting data."""
    a = CandleBuilder(symbol="RELIANCE", interval="1m")
    b = CandleBuilder(symbol="TCS", interval="1m")

    a.on_tick(price=100.0, volume=1, timestamp=_ts(0), received_at=_ts(0))
    b.on_tick(price=-1.0, volume=1, timestamp=_ts(0), received_at=_ts(0))  # deliberately invalid, only for b

    assert a.last_known_price == 100.0
    assert b.last_known_price is None
    assert a.rejected_tick_counts["non_positive_price"] == 0
    assert b.rejected_tick_counts["non_positive_price"] == 1
    assert a._state is not b._state  # not the same object, not aliased


def test_an_overnight_gap_after_baseline_confirmed_is_a_documented_residual_gap_not_a_bug_in_practice():
    """Documented, not fixed: once `_baseline_confirmed` is True, ANY tick
    disagreeing by more than `_max_timestamp_skew_seconds` is rejected
    PERMANENTLY via the confirmed path -- there is no self-heal mechanism
    left once confirmed (by design: see
    test_baseline_confirmed_state_survives_a_simulated_reconnect_and_
    rejects_a_replayed_stale_packet above for why re-opening that window
    would be dangerous). This means a CandleBuilder instance that
    genuinely persisted, unrestarted, across a multi-day gap (e.g. late
    Friday close to Monday open, a ~64-hour real exchange gap far
    exceeding the default 3600s threshold) would permanently reject the
    new session's data too. NOT exercised by this project's actual
    deployment: the real fleet's workers (and therefore every
    CandleBuilder instance) are launched fresh each trading morning via
    `fleet-supervise`, confirmed via this session's own real launch
    evidence -- a CandleBuilder instance never actually lives across a
    session boundary in production today. Documented here so this
    boundary is explicit rather than silently assumed, exactly like
    test_corrupted_very_first_tick_is_a_documented_residual_gap above."""
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=1, timestamp=_ts(0), received_at=_ts(0))
    builder.on_tick(price=101.0, volume=1, timestamp=_ts(10), received_at=_ts(10))  # confirms baseline

    weekend_gap_seconds = 64 * 3600  # Friday 15:29 IST -> Monday 09:15 IST, roughly
    next_session_tick_1 = builder.on_tick(price=105.0, volume=1, timestamp=_ts(10 + weekend_gap_seconds), received_at=_ts(10 + weekend_gap_seconds))
    assert next_session_tick_1 is None
    assert builder.rejected_tick_counts["implausible_timestamp"] == 1

    next_session_tick_2 = builder.on_tick(price=106.0, volume=1, timestamp=_ts(10 + weekend_gap_seconds + 60), received_at=_ts(10 + weekend_gap_seconds + 60))
    assert next_session_tick_2 is None
    assert builder.rejected_tick_counts["implausible_timestamp"] == 2  # still rejected -- no self-heal once confirmed, unlike the cold-start case


# --- Red-team findings, 2026-09-22 ------------------------------------------


def test_close_reflects_the_chronologically_latest_tick_not_the_most_recently_arrived_one():
    """Real defect found by adversarial audit: a tick that arrives OUT OF
    ORDER within the same still-open bucket (its own exchange timestamp is
    EARLIER than a tick already merged) must never overwrite `close` --
    this module's own docstring defines close as "price of the most recent
    tick," meaning most recent BY EXCHANGE TIME, not by arrival order.
    high/low/volume are unaffected and must still count every real tick
    regardless of order."""
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(30), received_at=_ts(30))
    # Arrives SECOND but belongs to an EARLIER moment within the same bucket.
    builder.on_tick(price=99.0, volume=5, timestamp=_ts(10), received_at=_ts(31))
    bar = builder.on_tick(price=101.0, volume=1, timestamp=_ts(61), received_at=_ts(61))

    assert bar is not None
    assert bar.close == 100.0  # the chronologically-latest tick (epoch 30), not the out-of-order one (epoch 10)
    assert bar.low == 99.0  # the out-of-order tick's price still counts toward low
    assert bar.volume == 15.0  # and still counts toward volume


def test_close_still_advances_normally_when_ticks_arrive_in_chronological_order():
    """Regression guard: the fix above must not disturb the ordinary,
    overwhelmingly common case of in-order delivery."""
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(5), received_at=_ts(5))
    builder.on_tick(price=100.5, volume=7, timestamp=_ts(30), received_at=_ts(30))
    bar = builder.on_tick(price=101.0, volume=1, timestamp=_ts(61), received_at=_ts(61))

    assert bar is not None
    assert bar.close == 100.5  # the later-arriving, later-timestamped tick correctly wins


@pytest.mark.parametrize("bad_price", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_price_is_rejected_never_merged_into_a_bucket(bad_price):
    """Real defect found by adversarial audit: NaN/Inf pass every existing
    comparison as False (nan <= 0, nan > threshold, inf <= 0 are all
    False), so neither the non-positive-price nor the deviation gate ever
    caught them -- a NaN could previously poison `close`/
    `_last_known_price` permanently and eventually raise an uncaught
    pydantic ValidationError (a different exception type than the
    DhanWireFormatError the real receive-thread callback actually
    catches) when the bar finalizes. A struct-decoded float32 CAN legally
    carry a NaN/Inf bit pattern from a corrupted packet -- reachable, not
    hypothetical."""
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(0), received_at=_ts(0))  # seeds a real baseline

    result = builder.on_tick(price=bad_price, volume=5, timestamp=_ts(30), received_at=_ts(30))

    assert result is None
    assert builder.rejected_tick_counts["non_finite_value"] == 1
    assert builder.rejected_tick_counts["non_positive_price"] == 0  # caught by the NEW, more specific gate
    # The bad tick must never have merged -- the next valid tick still sees the ORIGINAL real baseline.
    bar = builder.on_tick(price=101.0, volume=1, timestamp=_ts(61), received_at=_ts(61))
    assert bar is not None
    assert bar.close == 100.0
    assert bar.high == 100.0
    assert bar.low == 100.0
    assert bar.volume == 10.0  # the NaN tick's volume was never added


def test_non_finite_volume_is_also_rejected():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    result = builder.on_tick(price=100.0, volume=float("nan"), timestamp=_ts(0), received_at=_ts(0))

    assert result is None
    assert builder.rejected_tick_counts["non_finite_value"] == 1


def test_a_nan_price_never_permanently_poisons_the_deviation_gate_for_later_ticks():
    """The specific mechanism the audit flagged: before the fix, letting a
    NaN merge into `_last_known_price` made EVERY future deviation
    comparison against that NaN baseline also silently evaluate False,
    disabling implausible-price protection for the rest of the instance's
    life. Proven here by confirming an actually-implausible tick (60% away
    from the real baseline) is still correctly caught AFTER a NaN tick was
    seen and rejected."""
    builder = CandleBuilder(symbol="RELIANCE", interval="1m", max_tick_deviation_pct=20.0)
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(0), received_at=_ts(0))
    builder.on_tick(price=float("nan"), volume=1, timestamp=_ts(10), received_at=_ts(10))  # rejected, must not poison state

    implausible = builder.on_tick(price=160.0, volume=1, timestamp=_ts(20), received_at=_ts(20))  # 60% away from the real 100.0 baseline

    assert implausible is None
    assert builder.rejected_tick_counts["implausible_deviation"] == 1


def test_a_genuine_redelivery_of_an_out_of_order_tick_still_does_not_double_count_volume():
    """Second-order red-team finding (2026-09-22): the close-ordering fix
    (see test_close_reflects_the_chronologically_latest_tick_...) made
    last_source_timestamp/close track the CHRONOLOGICAL-MAX tick, not the
    most-recently-MERGED one. Without a separate arrival-order baseline,
    a genuine wire-redelivery of an out-of-order tick would stop matching
    last_source_timestamp/close (already moved on to a later-timestamped
    tick) and its volume would be double-counted -- silently reopening
    the exact defect the redelivery heuristic exists to prevent."""
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(50), received_at=_ts(50))  # seeds bucket, chronological max so far
    builder.on_tick(price=99.0, volume=5, timestamp=_ts(10), received_at=_ts(51))  # real, out-of-order, does NOT advance close
    builder.on_tick(price=99.0, volume=5, timestamp=_ts(10), received_at=_ts(52))  # genuine redelivery of the tick above

    bar = builder.on_tick(price=101.0, volume=1, timestamp=_ts(61), received_at=_ts(61))

    assert bar is not None
    # 10 (first) + 5 (real out-of-order) + 0 (redelivery correctly suppressed) -- the
    # completing tick's own volume=1 belongs to the NEXT bucket, not this bar. NOT 20.
    assert bar.volume == 15.0
    assert bar.close == 100.0  # unaffected: still the chronologically-latest tick


# --- G12: cross-thread synchronization (continuous red-team, 2026-09-23) ---


def test_on_tick_and_last_known_price_and_timestamp_survive_real_concurrent_contention():
    """G12 regression (docs/MASTER_KNOWN_ISSUES.md): a genuine, real
    multi-threaded test, not theoretical -- one thread continuously feeds
    on_tick() (simulating the WebSocket receive thread), a SECOND thread
    concurrently polls last_known_price_and_timestamp() (simulating a
    dashboard/monitoring poll), for many iterations. Two things must both
    hold under real contention: (1) no crash/exception on either thread --
    a torn read of an in-progress mutation would be a real bug even if it
    happened not to raise; (2) every (price, timestamp) pair observed by
    the reader must be an ACTUAL pair this builder produced (price and
    timestamp from the SAME tick), proving last_known_price_and_timestamp()
    is genuinely atomic as a pair, not just individually-safe per field."""
    import threading

    builder = CandleBuilder(symbol="RELIANCE", interval="1m", max_tick_deviation_pct=None, max_timestamp_skew_seconds=None)
    n_ticks = 2000
    # Every tick's price is uniquely tied to its own timestamp (price ==
    # second_of_epoch), so a torn/mismatched pair is trivially detectable.
    valid_pairs = {float(i): _ts(i) for i in range(n_ticks)}

    errors: list[BaseException] = []
    observed_mismatches: list[tuple] = []
    stop = threading.Event()

    def _writer() -> None:
        try:
            for i in range(n_ticks):
                builder.on_tick(price=float(i), volume=1.0, timestamp=_ts(i), received_at=_ts(i))
        except BaseException as exc:  # noqa: BLE001 -- capture, report from the main thread
            errors.append(exc)
        finally:
            stop.set()

    def _reader() -> None:
        try:
            while not stop.is_set():
                pair = builder.last_known_price_and_timestamp()
                if pair is not None:
                    price, ts = pair
                    if valid_pairs.get(price) != ts:
                        observed_mismatches.append(pair)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    writer = threading.Thread(target=_writer)
    reader = threading.Thread(target=_reader)
    reader.start()
    writer.start()
    writer.join(timeout=30)
    reader.join(timeout=30)

    assert not writer.is_alive() and not reader.is_alive(), "a thread hung -- possible deadlock"
    assert errors == [], f"a thread raised: {errors}"
    assert observed_mismatches == [], f"a torn/mismatched (price, timestamp) pair was observed: {observed_mismatches[:5]}"

    final_price, final_ts = builder.last_known_price_and_timestamp()
    assert final_price == float(n_ticks - 1)
    assert final_ts == _ts(n_ticks - 1)


def test_rejected_tick_counts_snapshot_is_a_real_copy_not_a_live_reference():
    """G12: the snapshot must not alias the internal dict -- a caller on
    another thread mutating its own copy (or simply holding it while
    on_tick keeps incrementing the real one) must never see or cause
    action-at-a-distance."""
    builder = CandleBuilder(symbol="RELIANCE", interval="1m")
    builder.on_tick(price=-1.0, volume=1.0, timestamp=_ts(0), received_at=_ts(0))  # rejected: non_positive_price

    snapshot = builder.rejected_tick_counts_snapshot()
    assert snapshot["non_positive_price"] == 1

    builder.on_tick(price=-1.0, volume=1.0, timestamp=_ts(1), received_at=_ts(1))  # a second rejection, real state advances
    assert snapshot["non_positive_price"] == 1  # the earlier snapshot is frozen, unaffected
    assert builder.rejected_tick_counts_snapshot()["non_positive_price"] == 2  # a fresh snapshot sees it
