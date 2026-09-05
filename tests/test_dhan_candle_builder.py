"""Phase 15 §23 unit tests: CandleBuilder tick-to-OHLCVBar aggregation.
Pure, synthetic ticks -- no network, no Dhan connection.
"""
from datetime import datetime, timezone

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


def test_max_tick_deviation_pct_none_disables_the_plausibility_check():
    builder = CandleBuilder(symbol="RELIANCE", interval="1m", max_tick_deviation_pct=None)
    builder.on_tick(price=100.0, volume=10, timestamp=_ts(0), received_at=_ts(0))
    result = builder.on_tick(price=10_000.0, volume=1, timestamp=_ts(10), received_at=_ts(10))
    assert result is None  # still same bucket, not completed -- but NOT dropped as implausible either

    bar = builder.flush()
    assert bar.high == 10_000.0
