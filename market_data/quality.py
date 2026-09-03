"""Phase 18 -- a source-agnostic data-quality/health model.

SourceHealth generalizes the freshness concept already proven in
live/freshness.py (bar-level staleness, used by the live pipeline's own
signal-suppression gate) to ANY market_data adapter -- Yahoo, mock, or
Dhan -- not just the live Dhan feed. This does NOT reimplement staleness
math: `from_bar_timestamp` delegates directly to the existing
FreshnessPolicy, so a 1-minute bar and a 1-day bar are judged by the same
interval-derived threshold formula everywhere in this project, not two
different ones. live/freshness.FreshnessPolicy remains the sole authority
the live pipeline itself uses for its own signal-suppression gate; this
module is a thinner, adapter-facing summary of "can I trust this data
right now?" for the new unified facade (market_data/provider.py).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from live.freshness import DEFAULT_FRESHNESS_POLICY, FreshnessPolicy


class SourceStatus(str, Enum):
    """Coarse, source-agnostic health classification -- deliberately NOT
    reusing market.data_provider.DataStatus (LIVE/DELAYED/HISTORICAL/
    SIMULATED), which answers "what KIND of data is this" (a property of
    the bar itself, fixed at creation), not "is the adapter healthy right
    now" (a property of the current attempt to read it, which can degrade
    independently of what kind of feed it nominally is)."""

    HEALTHY = "HEALTHY"
    STALE = "STALE"
    DISCONNECTED = "DISCONNECTED"
    NO_DATA = "NO_DATA"
    ERROR = "ERROR"


@dataclass(frozen=True)
class SourceHealth:
    status: SourceStatus
    last_updated: datetime | None
    age_seconds: float | None
    detail: str | None = None

    @classmethod
    def no_data(cls) -> "SourceHealth":
        return cls(SourceStatus.NO_DATA, None, None, "No data has been fetched yet.")

    @classmethod
    def disconnected(cls, detail: str | None = None) -> "SourceHealth":
        return cls(SourceStatus.DISCONNECTED, None, None, detail)

    @classmethod
    def error(cls, detail: str) -> "SourceHealth":
        return cls(SourceStatus.ERROR, None, None, detail)

    @classmethod
    def from_bar_timestamp(
        cls,
        *,
        bar_timestamp: datetime,
        interval: str,
        now: datetime | None = None,
        policy: FreshnessPolicy = DEFAULT_FRESHNESS_POLICY,
        max_future_tolerance_seconds: float = 300.0,
    ) -> "SourceHealth":
        """Classifies freshness using the SAME FreshnessPolicy the live
        pipeline itself uses. `policy.check()` already normalizes
        naive/aware datetimes internally (see live/freshness.py's own
        `_naive` docstring) -- this project's bars are a genuine mix
        (Yahoo/mock are naive by convention, real Dhan bars are UTC-aware
        since the Phase 16 timezone fix), so that existing robustness
        carries through here without extra handling.

        Phase 18 audit fix -- VERIFIED against real Phase 16 observations:
        FreshnessPolicy.check() alone treats a bar timestamped in the
        FUTURE relative to `now` as trivially "fresh" (a negative age is
        always <= any positive threshold) -- exactly the failure mode
        that let the original Dhan IST/UTC timestamp bug (~5.5 hours in
        the future) go undetected before it was found and fixed in Phase
        16. `max_future_tolerance_seconds` (default 300s / 5 minutes)
        distinguishes that genuine anomaly from ordinary, small,
        already-observed clock skew between a real broker's server and
        this machine (Dhan's own clock ran ~2 minutes ahead of local in
        Phase 16 testing -- well within this tolerance, still HEALTHY).
        A future timestamp beyond the tolerance is reported ERROR, never
        silently passed through as HEALTHY -- this module is meant to
        ground broader future market-intelligence reasoning (roadmap §3.1,
        §8), not just one pipeline's own internal gate, so it does not
        inherit FreshnessPolicy's narrower "never flags the future"
        blind spot."""
        now = now or datetime.now(timezone.utc)
        result = policy.check(bar_timestamp, interval=interval, now=now)
        age_seconds = result.age.total_seconds()
        if age_seconds < -max_future_tolerance_seconds:
            return cls(
                SourceStatus.ERROR,
                bar_timestamp,
                age_seconds,
                f"bar timestamp is {abs(age_seconds):.0f}s in the future relative to now, beyond the "
                f"{max_future_tolerance_seconds:.0f}s tolerance -- treated as a data anomaly, not fresh data",
            )
        if result.is_fresh:
            return cls(SourceStatus.HEALTHY, bar_timestamp, age_seconds)
        return cls(
            SourceStatus.STALE,
            bar_timestamp,
            age_seconds,
            f"age {age_seconds:.0f}s exceeds threshold {result.threshold.total_seconds():.0f}s",
        )
