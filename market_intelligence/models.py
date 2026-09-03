"""Phase 19 -- market scanner output models.

A CandidateScore never carries a buy/sell/quantity/price-level -- that is
the Decision Engine's job (roadmap Phase 21), not the scanner's. A
candidate is "here is a ranked, explainable observation about this
instrument," nothing more.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CandidateScore(BaseModel):
    """One instrument's scan result. Every score that fed `composite_score`
    is also broken out individually, and `explanation` states in plain
    language what each factor observed -- so "why did the scanner rank
    this candidate here" never requires re-deriving the math."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    as_of: datetime
    """The last bar's own timestamp (naive, matching OHLCVBar.timestamp)
    -- NOT when the scan itself ran; see ScanReport.as_of for that."""

    last_close: float
    avg_daily_value: float
    volume_ratio: float | None

    trend_score: float
    momentum_score: float
    breakout_score: float
    relative_strength_score: float | None
    sector_strength_score: float | None

    composite_score: float
    explanation: list[str]


class ExcludedCandidate(BaseModel):
    """A symbol the scanner considered but did not score -- kept, not
    dropped, so "why was this stock not a candidate" is answerable from
    the report alone (roadmap §2's auditability requirement)."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    as_of: datetime | None
    reason: str


class ScanReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    scan_id: str
    as_of: datetime
    """UTC-aware: when the scan itself executed -- see the same
    real-vs-construction-time distinction documented on
    market_data.models.InstrumentSnapshot.as_of."""

    universe_mode: str
    universe_size: int
    benchmark_symbol: str | None
    benchmark_unavailable_reason: str | None
    config_version: str
    candidates: list[CandidateScore]
    """Sorted by composite_score descending, ties broken by symbol name for
    a reproducible order -- see scanner.run_scan."""
    excluded: list[ExcludedCandidate]

    def get(self, symbol: str) -> CandidateScore | None:
        normalized = symbol.strip().upper()
        for candidate in self.candidates:
            if candidate.symbol == normalized:
                return candidate
        return None
