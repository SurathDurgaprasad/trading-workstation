"""core/timeutil.py -- the consolidated repository-wide datetime
normalization policy. See that module's own docstring for the historical
bug class (Phase 33/37/42) this replaces.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from core.timeutil import as_utc_aware, match_index_awareness, to_naive


# --- to_naive -----------------------------------------------------------


def test_to_naive_passes_through_an_already_naive_datetime():
    value = datetime(2026, 9, 13, 9, 15)
    assert to_naive(value) == value
    assert to_naive(value).tzinfo is None


def test_to_naive_strips_tzinfo_from_an_aware_datetime():
    value = datetime(2026, 9, 13, 9, 15, tzinfo=timezone.utc)
    result = to_naive(value)
    assert result.tzinfo is None
    assert result == datetime(2026, 9, 13, 9, 15)


def test_to_naive_accepts_a_pandas_timestamp():
    ts = pd.Timestamp("2026-09-13 09:15:00")
    result = to_naive(ts)
    assert isinstance(result, datetime)
    assert result.tzinfo is None


def test_to_naive_accepts_a_tz_aware_pandas_timestamp():
    ts = pd.Timestamp("2026-09-13 09:15:00", tz="UTC")
    result = to_naive(ts)
    assert result.tzinfo is None


def test_to_naive_accepts_a_parseable_string():
    result = to_naive("2026-09-13 09:15:00")
    assert isinstance(result, datetime)
    assert result.tzinfo is None
    assert result.year == 2026


# --- as_utc_aware ---------------------------------------------------------


def test_as_utc_aware_passes_through_an_already_aware_datetime_unchanged():
    value = datetime(2026, 9, 13, 9, 15, tzinfo=timezone.utc)
    assert as_utc_aware(value) is value


def test_as_utc_aware_attaches_utc_to_a_naive_datetime():
    value = datetime(2026, 9, 13, 9, 15)
    result = as_utc_aware(value)
    assert result.tzinfo is timezone.utc
    assert result.replace(tzinfo=None) == value


def test_as_utc_aware_never_reconverts_a_non_utc_aware_value():
    from datetime import timedelta, tzinfo as tzinfo_type

    class _IST(tzinfo_type):
        def utcoffset(self, dt): return timedelta(hours=5, minutes=30)
        def dst(self, dt): return timedelta(0)
        def tzname(self, dt): return "IST"

    value = datetime(2026, 9, 13, 9, 15, tzinfo=_IST())
    result = as_utc_aware(value)
    assert result.tzinfo is value.tzinfo  # unchanged, not coerced to UTC


def test_as_utc_aware_makes_mixed_sorting_possible():
    """The exact failure mode this function exists to fix: sorting naive
    and aware datetimes together raises TypeError without normalization."""
    naive = datetime(2026, 9, 13, 9, 0)
    aware = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    with pytest.raises(TypeError):
        sorted([naive, aware])
    assert sorted([naive, aware], key=as_utc_aware) == [naive, aware]


# --- match_index_awareness -------------------------------------------------


def test_match_index_awareness_adds_utc_when_index_is_aware_and_value_is_naive():
    index = pd.DatetimeIndex(["2026-09-13 09:15"]).tz_localize("UTC")
    value = datetime(2026, 9, 13, 9, 15)
    result = match_index_awareness(value, index)
    assert result.tzinfo is not None


def test_match_index_awareness_strips_when_index_is_naive_and_value_is_aware():
    index = pd.DatetimeIndex(["2026-09-13 09:15"])
    value = datetime(2026, 9, 13, 9, 15, tzinfo=timezone.utc)
    result = match_index_awareness(value, index)
    assert result.tzinfo is None


def test_match_index_awareness_leaves_a_matching_pair_unchanged():
    naive_index = pd.DatetimeIndex(["2026-09-13 09:15"])
    naive_value = datetime(2026, 9, 13, 9, 15)
    assert match_index_awareness(naive_value, naive_index) == naive_value

    aware_index = pd.DatetimeIndex(["2026-09-13 09:15"]).tz_localize("UTC")
    aware_value = datetime(2026, 9, 13, 9, 15, tzinfo=timezone.utc)
    result = match_index_awareness(aware_value, aware_index)
    assert result.tzinfo is not None


def test_match_index_awareness_never_mutates_the_index():
    index = pd.DatetimeIndex(["2026-09-13 09:15"]).tz_localize("UTC")
    original_tz = index.tz
    match_index_awareness(datetime(2026, 9, 13, 9, 15), index)
    assert index.tz == original_tz
