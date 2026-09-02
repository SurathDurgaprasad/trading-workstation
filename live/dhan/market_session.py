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

Documented limitation, stated rather than hidden: this does NOT account
for exchange holidays (Diwali, Republic Day, etc.) -- a holiday Tuesday at
10 AM IST is reported OPEN by this module, since holiday calendars change
yearly and are not something this module fetches or hardcodes. Any caller
that needs holiday-accurate session state must cross-check against the
exchange's own published holiday calendar separately; this module's
CLOSED/OPEN/PRE_OPEN answer is a necessary but not sufficient signal, and
callers must not treat the reverse.
"""

from dataclasses import dataclass
from datetime import datetime, time
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


def current_market_session(now: datetime | None = None) -> MarketSession:
    """`now` may be naive (assumed already IST) or tz-aware in any zone
    (converted to IST). Defaults to the real current time. Pure function
    of its input otherwise -- fully deterministic and testable without a
    real clock."""
    if now is None:
        now = datetime.now(IST)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=IST)
    else:
        now = now.astimezone(IST)

    is_weekday = now.weekday() < 5  # Monday=0 .. Sunday=6; NSE/BSE cash market does not trade Sat/Sun
    local_time = now.time()

    if not is_weekday:
        state = MarketSessionState.CLOSED
    elif _PRE_OPEN_START <= local_time < _OPEN_START:
        state = MarketSessionState.PRE_OPEN
    elif _OPEN_START <= local_time < _OPEN_END:
        state = MarketSessionState.OPEN
    else:
        state = MarketSessionState.CLOSED

    return MarketSession(state=state, as_of_ist=now, is_weekday=is_weekday)


def is_bar_within_expected_session(bar_timestamp: datetime) -> bool:
    """A bar timestamped outside PRE_OPEN/OPEN is unexpected -- not
    necessarily wrong (a broker might legitimately send a settlement/AMO
    update outside session hours), but callers (e.g. the live pipeline)
    should treat it as a signal to log/flag rather than silently
    processing it as an ordinary intraday bar."""
    return current_market_session(bar_timestamp).state != MarketSessionState.CLOSED
