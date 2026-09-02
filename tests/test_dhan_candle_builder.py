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
