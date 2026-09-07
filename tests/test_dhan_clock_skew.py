"""LIVE SYSTEM HARDENING mission, Part 11 -- unit coverage for
live/dhan/clock_skew.py's real skew-measurement logic, using an injected
fake http_get (no `requests` dependency, no network) so PASS/WARNING/FAIL
classification boundaries and the "any real response has a Date header"
property are exercised deterministically."""

from email.utils import format_datetime

import pytest

from live.dhan.clock_skew import ClockSkewUnavailable, measure_clock_skew
from live.dhan.config import DhanCredentials

CREDENTIALS = DhanCredentials(client_id="fake-id", access_token="fake-token")


def _date_header(dt) -> str:
    return format_datetime(dt, usegmt=True)


def test_skew_within_5s_classified_pass():
    import datetime as dt_module

    now = dt_module.datetime.now(dt_module.timezone.utc)

    def fake_get(url, headers):
        return 200, _date_header(now)

    result = measure_clock_skew(CREDENTIALS, http_get=fake_get)
    assert result.classification == "PASS"
    assert abs(result.skew_seconds) < 5
    assert result.http_status == 200


def test_skew_between_5_and_60s_classified_warning():
    import datetime as dt_module

    server_time = dt_module.datetime.now(dt_module.timezone.utc) - dt_module.timedelta(seconds=30)

    def fake_get(url, headers):
        return 200, _date_header(server_time)

    result = measure_clock_skew(CREDENTIALS, http_get=fake_get)
    assert result.classification == "WARNING"
    assert 5 <= abs(result.skew_seconds) < 60
    assert "w32tm /resync" in result.detail


def test_skew_beyond_60s_classified_fail_matches_real_live_observation():
    # Real, live-confirmed value on this machine (2026-09-01 through
    # 2026-09-07, multiple independent measurements): local clock runs
    # ~130s behind Dhan's server clock.
    import datetime as dt_module

    server_time = dt_module.datetime.now(dt_module.timezone.utc) + dt_module.timedelta(seconds=130)

    def fake_get(url, headers):
        return 200, _date_header(server_time)

    result = measure_clock_skew(CREDENTIALS, http_get=fake_get)
    assert result.classification == "FAIL"
    assert abs(result.skew_seconds) >= 60
    assert "cannot be trusted" in result.detail


def test_skew_still_measured_from_a_non_2xx_response_with_a_date_header():
    # A real server stamps Date on error responses too (e.g. an expired
    # token returning 401) -- skew must still be derivable; only
    # connectivity is a separate, orthogonal finding the caller reports.
    import datetime as dt_module

    now = dt_module.datetime.now(dt_module.timezone.utc)

    def fake_get(url, headers):
        return 401, _date_header(now)

    result = measure_clock_skew(CREDENTIALS, http_get=fake_get)
    assert result.classification == "PASS"
    assert result.http_status == 401


def test_missing_date_header_raises_clock_skew_unavailable():
    def fake_get(url, headers):
        return 200, None

    with pytest.raises(ClockSkewUnavailable):
        measure_clock_skew(CREDENTIALS, http_get=fake_get)


def test_transport_failure_raises_clock_skew_unavailable_not_the_original_exception():
    def fake_get(url, headers):
        raise ConnectionError("no route to host")

    with pytest.raises(ClockSkewUnavailable):
        measure_clock_skew(CREDENTIALS, http_get=fake_get)


def test_access_token_is_sent_in_headers_never_in_the_url():
    captured = {}

    def fake_get(url, headers):
        captured["url"] = url
        captured["headers"] = headers
        import datetime as dt_module

        return 200, _date_header(dt_module.datetime.now(dt_module.timezone.utc))

    measure_clock_skew(CREDENTIALS, http_get=fake_get)
    assert "fake-token" not in captured["url"]
    assert captured["headers"]["access-token"] == "fake-token"
