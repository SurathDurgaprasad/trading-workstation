"""Phase 15 §11 — explicit Indian market-session semantics.

Dhan's WebSocket feed documents a "Market Status Packet" (response code 7)
but its byte layout is NOT published on the current live docs (see
wire.py's module docstring) -- REQUIRES CONFIRMATION, unusable today. This
module instead derives session state from IST wall-clock time against
NSE/BSE's own published equity cash-market session times, stated
explicitly here rather than left as an implicit assumption buried in a
freshness threshold:

  PRE_OPEN : 09:00:00 - 09:15:00 IST (order collection/matching window)
  OPEN     : 09:15:00 - 15:30:00 IST (continuous trading)
  CLOSED   : everything else, INCLUDING weekends

Documented limitation, stated rather than hidden: by default this does
NOT account for exchange holidays (Diwali, Republic Day, etc.) -- a
holiday Tuesday at 10 AM IST is reported OPEN unless the caller supplies
a `holidays` set. This module fetches or hardcodes no calendar of its
own (holiday dates change yearly and this project's own "never silently
fake data" posture forbids guessing them) -- but it CAN consult one a
caller already has, most notably scheduler/config.py's own
`ScheduleConfig.holidays` (a plain, user-supplied, YAML-configurable
date tuple, empty by default, already used to gate `schedule tick` --
see that module's own docstring for why no holiday-calendar API is
integrated). Live-market-readiness audit finding: `scheduler/runner.py`
already checks `ScheduleConfig.is_holiday()` before ever calling this
function, so the SCHEDULER was already holiday-safe -- but every OTHER
caller (the dashboard's market-status banner, `readiness-check`,
`paper-live`/`shadow-run` startup banners) only ever called this
function with no holiday awareness at all, even when the operator had
already configured a holiday list for scheduling. Passing that SAME
list in here closes that gap without inventing a second, inconsistent
holiday format.

A caller that has no holiday list at all gets EXACTLY today's existing
behavior (holidays defaults to an empty frozenset, so `is_confirmed_holiday`
is always False and `holiday_calendar_size` is 0) -- this is purely
additive, never a silent behavior change for an existing caller that
does not opt in.
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

_PRE_OPEN_START = time(9, 0)
_OPEN_START = time(9, 15)
_OPEN_END = time(15, 30)


class MarketSessionState(str, Enum):
    PRE_OPEN = "PRE_OPEN"
    OPEN = "OPEN"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class MarketSession:
    state: MarketSessionState
    as_of_ist: datetime
    is_weekday: bool
    is_confirmed_holiday: bool = False
    """True only when the caller supplied a `holidays` set (possibly
    empty) AND today's date is in it -- in that case `state` is forced
    CLOSED regardless of weekday/time. False does NOT mean "confirmed
    not a holiday" -- check `holiday_calendar_consulted` to tell "a real
    (possibly empty) calendar was checked and today wasn't in it" apart
    from "no calendar was ever supplied, this is unverified.\""""
    holiday_calendar_consulted: bool = False
    """True iff the caller passed a `holidays` argument at all (even an
    explicitly empty one) -- deliberately distinct from
    `holiday_calendar_size == 0`, which is ambiguous between "an empty
    calendar was genuinely checked" and "no calendar was supplied."""
    holiday_calendar_size: int = 0
    """Size of the `holidays` set the caller supplied (0 whether none was
    supplied OR an empty one was -- see `holiday_calendar_consulted` to
    disambiguate). This session's OPEN/PRE_OPEN state must not be read as
    a confirmed trading day unless `holiday_calendar_consulted` is True."""


def current_market_session(now: datetime | None = None, holidays: frozenset[date] | None = None) -> MarketSession:
    """`now` may be naive (assumed already IST) or tz-aware in any zone
    (converted to IST). Defaults to the real current time. `holidays` is
    an optional set of exchange holiday dates (e.g. from
    `scheduler.config.ScheduleConfig.from_yaml_file(path).holidays`) --
    omitting it entirely (the default, `None`) reproduces this function's
    original behavior exactly. Passing an explicit set -- even an empty
    one -- marks `holiday_calendar_consulted=True`, distinct from "never
    checked" (see `MarketSession.holiday_calendar_consulted`'s own
    docstring for why this distinction is deliberate, not incidental).
    Pure function of its inputs otherwise -- fully deterministic and
    testable without a real clock."""
    if now is None:
        now = datetime.now(IST)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=IST)
    else:
        now = now.astimezone(IST)

    holiday_calendar_consulted = holidays is not None
    holidays = holidays or frozenset()
    is_weekday = now.weekday() < 5  # Monday=0 .. Sunday=6; NSE/BSE cash market does not trade Sat/Sun
    local_time = now.time()
    is_confirmed_holiday = now.date() in holidays

    if is_confirmed_holiday or not is_weekday:
        state = MarketSessionState.CLOSED
    elif _PRE_OPEN_START <= local_time < _OPEN_START:
        state = MarketSessionState.PRE_OPEN
    elif _OPEN_START <= local_time < _OPEN_END:
        state = MarketSessionState.OPEN
    else:
        state = MarketSessionState.CLOSED

    return MarketSession(
        state=state, as_of_ist=now, is_weekday=is_weekday, is_confirmed_holiday=is_confirmed_holiday,
        holiday_calendar_consulted=holiday_calendar_consulted, holiday_calendar_size=len(holidays),
    )


def is_bar_within_expected_session(bar_timestamp: datetime) -> bool:
    """A bar timestamped outside PRE_OPEN/OPEN is unexpected -- not
    necessarily wrong (a broker might legitimately send a settlement/AMO
    update outside session hours), but callers (e.g. the live pipeline)
    should treat it as a signal to log/flag rather than silently
    processing it as an ordinary intraday bar."""
    return current_market_session(bar_timestamp).state != MarketSessionState.CLOSED
