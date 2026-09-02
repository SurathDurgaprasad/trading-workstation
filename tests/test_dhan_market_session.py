"""Phase 15 §23 unit tests: IST market-session semantics. Pure function of
a supplied clock -- no real-time dependency.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from live.dhan.market_session import IST, MarketSessionState, current_market_session, is_bar_within_expected_session


def _ist(y, m, d, hh, mm) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=IST)


def test_before_pre_open_is_closed():
    # Monday 2026-09-07, 08:59 IST
    session = current_market_session(_ist(2026, 9, 7, 8, 59))
    assert session.state == MarketSessionState.CLOSED


def test_pre_open_window():
    session = current_market_session(_ist(2026, 9, 7, 9, 5))
    assert session.state == MarketSessionState.PRE_OPEN


def test_open_window_start_boundary_is_inclusive():
    session = current_market_session(_ist(2026, 9, 7, 9, 15))
    assert session.state == MarketSessionState.OPEN


def test_mid_session_is_open():
    session = current_market_session(_ist(2026, 9, 7, 12, 0))
    assert session.state == MarketSessionState.OPEN


def test_open_window_end_boundary_is_exclusive():
    session = current_market_session(_ist(2026, 9, 7, 15, 30))
    assert session.state == MarketSessionState.CLOSED


def test_just_before_close_is_open():
    session = current_market_session(_ist(2026, 9, 7, 15, 29))
    assert session.state == MarketSessionState.OPEN


def test_after_close_is_closed():
    session = current_market_session(_ist(2026, 9, 7, 20, 0))
    assert session.state == MarketSessionState.CLOSED


def test_saturday_is_closed_even_during_normal_session_hours():
    # 2026-09-05 is a Saturday
    session = current_market_session(_ist(2026, 9, 5, 12, 0))
    assert session.state == MarketSessionState.CLOSED
    assert session.is_weekday is False


def test_sunday_is_closed():
    # 2026-09-06 is a Sunday
    session = current_market_session(_ist(2026, 9, 6, 12, 0))
    assert session.state == MarketSessionState.CLOSED


def test_naive_datetime_is_treated_as_already_ist():
    naive = datetime(2026, 9, 7, 12, 0)
    session = current_market_session(naive)
    assert session.state == MarketSessionState.OPEN


def test_utc_timestamp_is_converted_to_ist_correctly():
    # 07:00 UTC == 12:30 IST (UTC+5:30) on a weekday -- must read as OPEN, not CLOSED
    utc_time = datetime(2026, 9, 7, 7, 0, tzinfo=ZoneInfo("UTC"))
    session = current_market_session(utc_time)
    assert session.state == MarketSessionState.OPEN
    assert session.as_of_ist.hour == 12
    assert session.as_of_ist.minute == 30


def test_is_bar_within_expected_session_true_during_open():
    assert is_bar_within_expected_session(_ist(2026, 9, 7, 10, 0)) is True


def test_is_bar_within_expected_session_false_after_close():
    assert is_bar_within_expected_session(_ist(2026, 9, 7, 22, 0)) is False
