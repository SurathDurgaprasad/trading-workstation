from datetime import datetime, timedelta

import pytest

from live.freshness import DEFAULT_FRESHNESS_POLICY, FreshnessPolicy, interval_to_timedelta


def test_interval_to_timedelta_minutes():
    assert interval_to_timedelta("1m") == timedelta(minutes=1)
    assert interval_to_timedelta("5m") == timedelta(minutes=5)
    assert interval_to_timedelta("15m") == timedelta(minutes=15)


def test_interval_to_timedelta_hours_and_days():
    assert interval_to_timedelta("1h") == timedelta(hours=1)
    assert interval_to_timedelta("1d") == timedelta(days=1)


def test_interval_to_timedelta_rejects_months():
    with pytest.raises(ValueError):
        interval_to_timedelta("1mo")


def test_interval_to_timedelta_rejects_garbage():
    with pytest.raises(ValueError):
        interval_to_timedelta("banana")


def test_threshold_scales_with_interval():
    policy = FreshnessPolicy(multiplier=2.0, minimum_threshold=timedelta(seconds=1))
    assert policy.threshold_for("1m") == timedelta(minutes=2)
    assert policy.threshold_for("5m") == timedelta(minutes=10)
    assert policy.threshold_for("15m") == timedelta(minutes=30)


def test_threshold_is_floored_by_minimum():
    policy = FreshnessPolicy(multiplier=2.0, minimum_threshold=timedelta(minutes=5))
    assert policy.threshold_for("1m") == timedelta(minutes=5)  # 2min would be below the floor


def test_fresh_bar_within_threshold():
    policy = FreshnessPolicy(multiplier=2.0, minimum_threshold=timedelta(seconds=1))
    bar_ts = datetime(2026, 1, 1, 9, 30, 0)
    now = bar_ts + timedelta(minutes=1)
    result = policy.check(bar_ts, interval="1m", now=now)
    assert result.is_fresh
    assert result.age == timedelta(minutes=1)


def test_stale_bar_beyond_threshold():
    policy = FreshnessPolicy(multiplier=2.0, minimum_threshold=timedelta(seconds=1))
    bar_ts = datetime(2026, 1, 1, 9, 30, 0)
    now = bar_ts + timedelta(minutes=10)
    result = policy.check(bar_ts, interval="1m", now=now)
    assert not result.is_fresh


def test_bar_exactly_at_threshold_is_fresh_inclusive():
    policy = FreshnessPolicy(multiplier=1.0, minimum_threshold=timedelta(seconds=1))
    bar_ts = datetime(2026, 1, 1, 9, 30, 0)
    now = bar_ts + timedelta(minutes=5)
    result = policy.check(bar_ts, interval="5m", now=now)
    assert result.is_fresh  # <= threshold, not strictly <


def test_check_handles_a_tz_aware_now_against_a_naive_bar_timestamp():
    """Regression test: found via run_mock_live_simulation_tool's own test
    -- LiveSimPipeline's default clock (datetime.now(timezone.utc), aware)
    was compared directly against historical bar timestamps (naive, per
    market.data_provider._to_timestamp's own convention), raising
    TypeError. check() now normalizes both sides internally."""
    from datetime import timezone

    policy = FreshnessPolicy(multiplier=1000.0)
    naive_bar_ts = datetime(2021, 8, 25)
    aware_now = datetime(2026, 8, 26, tzinfo=timezone.utc)
    result = policy.check(naive_bar_ts, interval="1d", now=aware_now)
    assert result.age.days > 0  # did not raise, and computed a sane age


def test_check_handles_a_naive_now_against_a_tz_aware_bar_timestamp():
    from datetime import timezone

    policy = FreshnessPolicy(multiplier=1000.0)
    aware_bar_ts = datetime(2021, 8, 25, tzinfo=timezone.utc)
    naive_now = datetime(2026, 8, 26)
    result = policy.check(aware_bar_ts, interval="1d", now=naive_now)
    assert result.age.days > 0


def test_default_policy_exists_and_is_usable():
    result = DEFAULT_FRESHNESS_POLICY.check(datetime(2026, 1, 1), interval="1m", now=datetime(2026, 1, 1, 0, 0, 30))
    assert result.is_fresh
