"""Phase 12 §4 — a deterministic, configurable-per-interval freshness guard.
Pure function of (bar timestamp, interval, now) — no I/O, no global state, no
hardcoded universal threshold (spec's explicit instruction: "do not invent a
universal threshold... make it configurable per interval").

The threshold is derived from the interval's own duration (a bar can only be
"fresh" relative to how often bars are expected to arrive) rather than three
separately-guessed magic numbers for 1m/5m/15m — this is a formula, not a
lookup table, so it generalizes to any interval string
strategy/backtesting already accepts without needing a new entry per
interval.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

_INTERVAL_PATTERN = re.compile(r"^(\d+)(m|h|d|wk|mo)$")

_UNIT_TO_TIMEDELTA_KWARGS = {
    "m": "minutes",
    "h": "hours",
    "d": "days",
    "wk": "weeks",
}


def interval_to_timedelta(interval: str) -> timedelta:
    """"1m" -> 1 minute, "5m" -> 5 minutes, "15m" -> 15 minutes, "1h" -> 1
    hour, "1d" -> 1 day, matching the interval strings already used
    throughout this project (main.py's --interval, yfinance's own interval
    vocabulary). "mo" (months) has no fixed timedelta and is rejected
    explicitly rather than approximated."""
    match = _INTERVAL_PATTERN.match(interval.strip().lower())
    if not match:
        raise ValueError(f"Unrecognized interval format: {interval!r}")
    quantity, unit = match.groups()
    if unit == "mo":
        raise ValueError(f"Interval {interval!r} has no fixed duration (calendar months) — not supported for freshness thresholds.")
    return timedelta(**{_UNIT_TO_TIMEDELTA_KWARGS[unit]: int(quantity)})


@dataclass(frozen=True)
class FreshnessResult:
    is_fresh: bool
    age: timedelta
    threshold: timedelta
    bar_timestamp: datetime
    now: datetime


@dataclass(frozen=True)
class FreshnessPolicy:
    """threshold = interval_duration * multiplier, floored at
    minimum_threshold. Defaults (2x the interval, floor 30s) are a
    documented, overridable starting point — not a claim of correctness for
    every symbol/venue; callers building a real live feed should tune
    `multiplier` against that feed's own observed latency."""

    multiplier: float = 2.0
    minimum_threshold: timedelta = timedelta(seconds=30)

    def threshold_for(self, interval: str) -> timedelta:
        base = interval_to_timedelta(interval) * self.multiplier
        return max(base, self.minimum_threshold)

    def check(self, bar_timestamp: datetime, *, interval: str, now: datetime) -> FreshnessResult:
        """Normalizes both timestamps to naive before comparing — every bar
        timestamp elsewhere in this project is naive by convention
        (market.data_provider._to_timestamp, paper.engine._naive), but a
        caller's `now` (e.g. datetime.now(timezone.utc)) commonly is not.
        Making `check()` itself robust here removes that footgun from every
        caller rather than documenting it as their responsibility (the bug
        this fixed: LiveSimPipeline's own default clock was tz-aware,
        raising TypeError against naive historical bar timestamps — found
        via the run_mock_live_simulation_tool MCP tool's own test)."""
        age = _naive(now) - _naive(bar_timestamp)
        threshold = self.threshold_for(interval)
        return FreshnessResult(is_fresh=age <= threshold, age=age, threshold=threshold, bar_timestamp=bar_timestamp, now=now)


def _naive(ts: datetime) -> datetime:
    return ts.replace(tzinfo=None) if ts.tzinfo is not None else ts


DEFAULT_FRESHNESS_POLICY = FreshnessPolicy()
