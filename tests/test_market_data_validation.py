from datetime import datetime, timedelta, timezone

import pytest

from market.data_provider import OHLCV, DataSource, DataStatus, OHLCVBar
from market_data.validation import DataQualityStatus, validate_ohlcv


def _bar(ts: datetime, price: float = 100.0) -> OHLCVBar:
    return OHLCVBar(timestamp=ts, open=price, high=price + 1, low=price - 1, close=price, volume=1_000_000)


def _series(timestamps: list[datetime], *, symbol: str = "TEST", interval: str = "1d") -> OHLCV:
    return OHLCV(symbol=symbol, interval=interval, bars=[_bar(ts) for ts in timestamps])


def _daily_timestamps(n: int, start: datetime = datetime(2026, 1, 1)) -> list[datetime]:
    return [start + timedelta(days=i) for i in range(n)]


def test_healthy_series_reports_healthy_with_no_issues():
    series = _series(_daily_timestamps(10))
    report = validate_ohlcv(series, now=datetime(2026, 1, 10, tzinfo=timezone.utc), check_freshness=False)

    assert report.status is DataQualityStatus.HEALTHY
    assert report.issues == ()
    assert report.is_usable


def test_empty_series_is_invalid():
    series = OHLCV(symbol="TEST", interval="1d", bars=[])
    report = validate_ohlcv(series, check_freshness=False)

    assert report.status is DataQualityStatus.INVALID
    assert not report.is_usable


def test_duplicate_timestamps_are_invalid():
    timestamps = _daily_timestamps(5)
    timestamps[3] = timestamps[2]  # duplicate
    series = _series(timestamps)

    report = validate_ohlcv(series, check_freshness=False)

    assert report.status is DataQualityStatus.INVALID
    assert not report.is_usable
    assert any("duplicate" in issue.lower() for issue in report.issues)


def test_non_chronological_order_is_invalid():
    timestamps = _daily_timestamps(5)
    timestamps[1], timestamps[3] = timestamps[3], timestamps[1]  # out of order
    series = _series(timestamps)

    report = validate_ohlcv(series, check_freshness=False)

    assert report.status is DataQualityStatus.INVALID
    assert not report.is_usable
    assert any("chronological" in issue.lower() for issue in report.issues)


def test_symbol_identity_mismatch_is_invalid():
    series = _series(_daily_timestamps(5), symbol="WRONG_SYMBOL")

    report = validate_ohlcv(series, expected_symbol="TEST", check_freshness=False)

    assert report.status is DataQualityStatus.INVALID
    assert any("identity mismatch" in issue.lower() for issue in report.issues)


def test_matching_symbol_identity_does_not_flag():
    series = _series(_daily_timestamps(5), symbol="test")  # case-insensitive match

    report = validate_ohlcv(series, expected_symbol="TEST", check_freshness=False)

    assert report.status is DataQualityStatus.HEALTHY


def test_large_gap_is_degraded_not_invalid():
    timestamps = _daily_timestamps(5) + [datetime(2026, 1, 1) + timedelta(days=30)]
    series = _series(timestamps)

    report = validate_ohlcv(series, check_freshness=False)

    assert report.status is DataQualityStatus.DEGRADED
    assert report.is_usable  # DEGRADED remains usable, per the module's own contract
    assert any("gap" in issue.lower() for issue in report.issues)


def test_stale_last_bar_is_degraded_when_freshness_checked():
    timestamps = _daily_timestamps(5)
    series = _series(timestamps)
    far_future_now = datetime(2026, 6, 1, tzinfo=timezone.utc)

    report = validate_ohlcv(series, now=far_future_now, check_freshness=True)

    assert report.status is DataQualityStatus.DEGRADED
    assert any("stale" in issue.lower() for issue in report.issues)


def test_freshness_check_can_be_disabled():
    timestamps = _daily_timestamps(5)
    series = _series(timestamps)
    far_future_now = datetime(2026, 6, 1, tzinfo=timezone.utc)

    report = validate_ohlcv(series, now=far_future_now, check_freshness=False)

    assert report.status is DataQualityStatus.HEALTHY


def test_invalid_outranks_degraded_when_both_present():
    timestamps = _daily_timestamps(5) + [datetime(2026, 1, 1) + timedelta(days=30)]
    timestamps[2] = timestamps[1]  # also a duplicate -> INVALID
    series = _series(timestamps)

    report = validate_ohlcv(series, check_freshness=False)

    assert report.status is DataQualityStatus.INVALID
    assert len(report.issues) >= 2  # both findings are visible, not just the worse one
