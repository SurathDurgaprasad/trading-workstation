"""LIVE SYSTEM HARDENING mission, Part 11 — real local-vs-Dhan-server clock
skew measurement, factored out of `main.py`'s `readiness-check --deep` (where
this logic originally lived, inline, CLI-print-only) so it can also be
called once at `paper-live --source dhan` session startup and persisted to
live/state_store.py's `clock_skew` table — the ONLY way the dashboard (a
separate, zero-I/O-on-page-load process, see dashboard/app.py's own
documented rule) can honestly show clock-skew status without either making
its own live network call on every 15s auto-refresh or fabricating a value.

Real, live-confirmed finding (2026-09-01 through 2026-09-07, 4+ independent
measurements across two methods that agree to ~1s): this machine's clock
runs approximately 130 seconds BEHIND Dhan's server clock. Root cause
confirmed via `w32tm /query /status`: Windows Time service has never
synced to NTP on this machine ("Leap Indicator: 3 (not synchronized)",
"Source: Local CMOS Clock"). This module does NOT and must NOT fix that —
system clock sync is an OS-level change outside this codebase's authority.
It only measures, classifies, and reports so the platform (and the human
operator) can trust its own freshness math instead of being silently wrong.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable

from live.dhan.config import DHAN_REST_BASE_URL, DhanCredentials

# (url, headers) -> (status_code, Date response header, or None if absent).
# Deliberately narrower than a full requests.Response (mirrors
# live/dhan/rest_client.py's own HttpGet DI pattern) so tests can inject a
# trivial fake with no `requests` dependency. before/after timing is taken
# OUTSIDE this callable (in measure_clock_skew itself) so a fake needs no
# awareness of real wall-clock time at all.
HttpGetWithDate = Callable[[str, dict], tuple[int, "str | None"]]


class ClockSkewUnavailable(RuntimeError):
    """Raised when skew could not be measured: network/HTTP failure, or a
    response with no Date header at all. Callers must treat this as
    "unknown", never silently assume zero skew."""


@dataclass(frozen=True)
class ClockSkewResult:
    skew_seconds: float
    """Positive = this machine's clock is AHEAD of Dhan's server clock.
    Negative = this machine's clock is BEHIND (the live-observed case)."""
    measured_at: datetime  # UTC, when this specific measurement was taken
    classification: str  # "PASS" | "WARNING" | "FAIL"
    detail: str
    http_status: int
    """The /fundlimit call's own HTTP status -- a real server's `Date`
    header is present on error responses too (401/500/etc.), so skew can
    be measured even when the call itself failed for an unrelated reason
    (e.g. an expired token). Connectivity and clock-skew are reported as
    two separate findings by the caller; this field is what lets it do
    that from the one real network call this function makes."""


def _default_http_get(url: str, headers: dict) -> tuple[int, "str | None"]:
    import requests

    response = requests.get(url, headers=headers, timeout=10)
    return response.status_code, response.headers.get("Date")


def measure_clock_skew(
    credentials: DhanCredentials,
    *,
    http_get: HttpGetWithDate = _default_http_get,
    base_url: str = DHAN_REST_BASE_URL,
) -> ClockSkewResult:
    """Makes ONE real Dhan REST GET (/fundlimit — the same read-only,
    already-used-elsewhere endpoint live/dhan/rest_client.py's
    get_fund_limit() calls) and derives skew from its HTTP `Date` response
    header, bracketed by local before/after timestamps so network latency
    itself doesn't get misread as skew (the midpoint of [before, after] is
    used as "local time" for the comparison — the same technique NTP
    clients use). Skew is derived from the Date header regardless of the
    call's own HTTP status -- a real server stamps Date on error
    responses too, so an auth failure doesn't have to also mean "skew
    unknown." Raises ClockSkewUnavailable only when no measurement is
    possible at all (transport failure, or a response with no Date
    header); never returns a fabricated result."""
    headers = {"Content-Type": "application/json", "access-token": credentials.access_token}
    before = datetime.now(timezone.utc)
    try:
        status_code, date_header = http_get(f"{base_url}/fundlimit", headers)
    except Exception as exc:  # noqa: BLE001 -- any transport failure means "unavailable", not a crash
        raise ClockSkewUnavailable(f"Dhan REST GET /fundlimit raised {type(exc).__name__}: {exc}") from exc
    after = datetime.now(timezone.utc)
    if not date_header:
        raise ClockSkewUnavailable(f"No Date header in the Dhan REST response (HTTP {status_code}).")
    server_time = parsedate_to_datetime(date_header)
    if server_time.tzinfo is None:
        server_time = server_time.replace(tzinfo=timezone.utc)
    midpoint_local = before + (after - before) / 2
    skew_seconds = (midpoint_local - server_time).total_seconds()
    measured_at = after
    if abs(skew_seconds) < 5:
        return ClockSkewResult(skew_seconds, measured_at, "PASS", f"{skew_seconds:+.1f}s -- within 5s tolerance.", status_code)
    if abs(skew_seconds) < 60:
        return ClockSkewResult(
            skew_seconds, measured_at, "WARNING",
            f"{skew_seconds:+.1f}s -- exceeds 5s. Freshness/staleness checks on THIS machine are biased by this "
            f"amount. Recommended: sync this machine's clock (Windows: run 'w32tm /resync' as Administrator, or "
            f"enable 'Set time automatically' in Settings). This is an environment issue, not application code.",
            status_code,
        )
    return ClockSkewResult(
        skew_seconds, measured_at, "FAIL",
        f"{skew_seconds:+.1f}s -- exceeds 60s, a full candle interval. Freshness/staleness logic cannot be "
        f"trusted on this machine until the clock is corrected (Windows: run 'w32tm /resync' as Administrator, "
        f"or enable 'Set time automatically' in Settings).",
        status_code,
    )
