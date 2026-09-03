from datetime import datetime, timedelta, timezone

from live.freshness import FreshnessPolicy
from market_data.quality import SourceHealth, SourceStatus


def test_no_data_classification():
    health = SourceHealth.no_data()
    assert health.status == SourceStatus.NO_DATA
    assert health.last_updated is None
    assert health.age_seconds is None


def test_disconnected_classification():
    health = SourceHealth.disconnected("feed dropped")
    assert health.status == SourceStatus.DISCONNECTED
    assert health.detail == "feed dropped"


def test_error_classification():
    health = SourceHealth.error("provider raised MarketDataError")
    assert health.status == SourceStatus.ERROR
    assert health.detail == "provider raised MarketDataError"


def test_from_bar_timestamp_healthy_for_a_fresh_bar():
    now = datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc)
    bar_ts = now - timedelta(seconds=30)  # well within a 1m interval's default threshold
    health = SourceHealth.from_bar_timestamp(bar_timestamp=bar_ts, interval="1m", now=now)
    assert health.status == SourceStatus.HEALTHY
    assert health.age_seconds == 30.0


def test_from_bar_timestamp_stale_for_an_old_bar():
    now = datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc)
    bar_ts = now - timedelta(hours=5)  # far beyond a 1m interval's threshold
    health = SourceHealth.from_bar_timestamp(bar_timestamp=bar_ts, interval="1m", now=now)
    assert health.status == SourceStatus.STALE
    assert health.detail is not None


def test_from_bar_timestamp_uses_the_interval_derived_threshold_not_a_fixed_one():
    """A daily bar many hours old is normal (matches the interval's own
    cadence); the SAME age for a 1-minute bar is stale. This must reuse
    live.freshness.FreshnessPolicy's own interval-scaled threshold, not a
    fixed constant -- proven here with the exact same age against two
    different intervals."""
    now = datetime(2026, 9, 3, 20, 0, tzinfo=timezone.utc)
    bar_ts = now - timedelta(hours=18)

    daily_health = SourceHealth.from_bar_timestamp(bar_timestamp=bar_ts, interval="1d", now=now)
    minute_health = SourceHealth.from_bar_timestamp(bar_timestamp=bar_ts, interval="1m", now=now)

    assert daily_health.status == SourceStatus.HEALTHY
    assert minute_health.status == SourceStatus.STALE


def test_from_bar_timestamp_handles_naive_and_aware_datetimes_identically():
    """Yahoo/mock bars are naive by project convention; real Dhan bars are
    UTC-aware since the Phase 16 timezone fix. Both must classify
    identically for the same real-world moment -- proving
    FreshnessPolicy's existing naive/aware normalization carries through
    this module unchanged."""
    now = datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc)
    aware_bar = now - timedelta(seconds=30)
    naive_bar = aware_bar.replace(tzinfo=None)

    aware_health = SourceHealth.from_bar_timestamp(bar_timestamp=aware_bar, interval="1m", now=now)
    naive_health = SourceHealth.from_bar_timestamp(bar_timestamp=naive_bar, interval="1m", now=now)

    assert aware_health.status == naive_health.status == SourceStatus.HEALTHY
    assert aware_health.age_seconds == naive_health.age_seconds == 30.0


def test_from_bar_timestamp_accepts_a_custom_policy():
    now = datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc)
    bar_ts = now - timedelta(minutes=3)
    tight_policy = FreshnessPolicy(multiplier=1.0, minimum_threshold=timedelta(seconds=1))
    health = SourceHealth.from_bar_timestamp(bar_timestamp=bar_ts, interval="1m", now=now, policy=tight_policy)
    assert health.status == SourceStatus.STALE
