"""Final-product-hardening: series-level OHLCV data-quality validation.

`market/data_provider.py`'s `OHLCV.from_dataframe` already drops
individual structurally-impossible rows (NaN, or a violated OHLC
relationship -- see `_row_has_valid_ohlc_relationship` there) at
construction time. This module validates what that row-level filter
cannot: properties of the SERIES as a whole (duplicate timestamps,
non-chronological ordering, missing bars/gaps, staleness of the last
bar, symbol-identity mismatch) -- checks that need the full bar list,
not one row at a time.

Returns a `DataQualityReport` with an explicit HEALTHY/DEGRADED/INVALID
status rather than raising, matching this project's established
convention (`FreshnessPolicy.check()`, `SourceHealth.from_bar_timestamp`
-- pure functions returning a classified result for a condition that is
a fact about the world, not a programming error) so callers decide what
to do with a DEGRADED finding rather than the module deciding for them.

THE RULE THIS MODULE EXISTS TO ENFORCE (release-gate mission): INVALID
data must never reach a prediction, a decision, a paper trade, or a live
trade. `market_intelligence/scanner.py`'s `_screen_symbol`/
`_fetch_benchmark` treat INVALID as equivalent to "no usable bars" --
the candidate is excluded before any indicator/feature/decision
computation ever sees it. DEGRADED is deliberately less severe: a known,
disclosed imperfection (e.g. a data gap that may just be a market
holiday, or a slightly stale last bar) that a caller may still choose to
act on -- visible via `issues`, never silently hidden, but not a hard
block, consistent with how `SourceHealth.STALE` already works elsewhere
in this project.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from core.timeutil import to_naive
from live.freshness import DEFAULT_FRESHNESS_POLICY, FreshnessPolicy, interval_to_timedelta
from market.data_provider import OHLCV


class DataQualityStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    INVALID = "INVALID"


_STATUS_SEVERITY = {DataQualityStatus.HEALTHY: 0, DataQualityStatus.DEGRADED: 1, DataQualityStatus.INVALID: 2}


@dataclass(frozen=True)
class DataQualityReport:
    status: DataQualityStatus
    issues: tuple[str, ...] = ()

    @property
    def is_usable(self) -> bool:
        """False only for INVALID -- callers MUST refuse to predict/
        decide/trade on this data. True for HEALTHY and DEGRADED (a
        DEGRADED report's `issues` are still there to inspect/log/
        surface, never silently discarded just because it passed)."""
        return self.status is not DataQualityStatus.INVALID


def _combine(findings: list[tuple[DataQualityStatus, str]]) -> DataQualityReport:
    worst = DataQualityStatus.HEALTHY
    for status, _ in findings:
        if _STATUS_SEVERITY[status] > _STATUS_SEVERITY[worst]:
            worst = status
    return DataQualityReport(status=worst, issues=tuple(issue for _, issue in findings))


def validate_ohlcv(
    ohlcv: OHLCV,
    *,
    expected_symbol: str | None = None,
    now: datetime | None = None,
    freshness_policy: FreshnessPolicy = DEFAULT_FRESHNESS_POLICY,
    check_freshness: bool = True,
    gap_multiplier: float = 3.0,
) -> DataQualityReport:
    """Validates the SERIES-level properties row-level filtering cannot:
    emptiness, symbol identity, duplicate/non-monotonic timestamps,
    large gaps (a heuristic for missing bars -- not calendar-aware, so a
    genuine market holiday/weekend can also trigger it; reported as
    DEGRADED, not INVALID, for exactly that reason), and (optionally)
    staleness of the most recent bar. See module docstring for the
    HEALTHY/DEGRADED/INVALID contract."""
    findings: list[tuple[DataQualityStatus, str]] = []

    if not ohlcv.bars:
        return DataQualityReport(status=DataQualityStatus.INVALID, issues=("No bars in the series.",))

    if expected_symbol is not None:
        normalized_expected = expected_symbol.strip().upper()
        normalized_actual = ohlcv.symbol.strip().upper()
        if normalized_actual != normalized_expected:
            findings.append((
                DataQualityStatus.INVALID,
                f"Symbol identity mismatch: requested {normalized_expected!r}, series is for {normalized_actual!r}.",
            ))

    timestamps = [to_naive(bar.timestamp) for bar in ohlcv.bars]

    seen: set[datetime] = set()
    duplicates: set[datetime] = set()
    for ts in timestamps:
        if ts in seen:
            duplicates.add(ts)
        seen.add(ts)
    if duplicates:
        findings.append((
            DataQualityStatus.INVALID,
            f"{len(duplicates)} duplicate bar timestamp(s), e.g. {sorted(duplicates)[0].isoformat()}.",
        ))

    if timestamps != sorted(timestamps):
        findings.append((DataQualityStatus.INVALID, "Bar timestamps are not in chronological order."))
    elif len(timestamps) >= 2:
        try:
            interval_duration = interval_to_timedelta(ohlcv.interval)
        except ValueError:
            interval_duration = None
        if interval_duration is not None and interval_duration.total_seconds() > 0:
            gaps = [b - a for a, b in zip(timestamps, timestamps[1:])]
            median_gap = sorted(gaps)[len(gaps) // 2]
            threshold = max(interval_duration * gap_multiplier, median_gap * gap_multiplier)
            large_gaps = [(a, b) for a, b, g in zip(timestamps, timestamps[1:], gaps) if g > threshold]
            if large_gaps:
                first_a, first_b = large_gaps[0]
                findings.append((
                    DataQualityStatus.DEGRADED,
                    f"{len(large_gaps)} gap(s) larger than {gap_multiplier:g}x the expected interval, e.g. between "
                    f"{first_a.isoformat()} and {first_b.isoformat()} ({(first_b - first_a).total_seconds() / 60:.0f} min). "
                    "May be a legitimate market closure (weekend/holiday) or missing data -- not distinguished here.",
                ))

    if check_freshness:
        resolved_now = now or datetime.now(timezone.utc)
        last_bar = ohlcv.bars[-1]
        try:
            freshness = freshness_policy.check(last_bar.timestamp, interval=ohlcv.interval, now=resolved_now)
        except ValueError:
            freshness = None
        if freshness is not None and not freshness.is_fresh:
            findings.append((
                DataQualityStatus.DEGRADED,
                f"Last bar ({last_bar.timestamp.isoformat()}) is stale: age {freshness.age} exceeds threshold {freshness.threshold}.",
            ))

    return _combine(findings)
