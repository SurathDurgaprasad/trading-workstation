"""Phase 34 -- decision confidence: a deterministic, explainable measure
of how many independent scanner factors agree with a decision's own
direction, as a fraction of the factors that were actually available.

This is NOT probability-calibrated on its own (that requires real
historical outcome data comparing predicted confidence to actual
win rate -- see learning/analysis.py's compute_real_confidence_calibration,
which consumes this score against Phase 23's prediction outcomes). This
module only answers "how much of the AVAILABLE evidence points the same
way", a measurable input, never an LLM guess -- the roadmap's own rule
for this phase: "Confidence must NOT be fabricated by an LLM. It must
derive from measurable system evidence."

Reuses market_intelligence.models.CandidateScore's existing factor
scores unchanged -- no new data collection, no new scanner logic.
"""

from dataclasses import dataclass

from market_intelligence.models import CandidateScore

_FACTOR_NAMES = ("trend_score", "momentum_score", "breakout_score", "relative_strength_score", "sector_strength_score")


@dataclass(frozen=True)
class ConfidenceBreakdown:
    score: float
    """0.0-1.0: agreeing_factors / (agreeing_factors + disagreeing_factors).
    0.0 when no candidate, a flat (zero) composite score, or zero factors
    were available to compare -- never a fabricated middle value."""
    direction: int
    """+1 (composite_score > 0), -1 (< 0), or 0 (flat -- no directional
    confidence is meaningful)."""
    agreeing_factors: tuple[str, ...]
    disagreeing_factors: tuple[str, ...]
    neutral_factors: tuple[str, ...]
    """Factors that were available but exactly zero -- neither agreeing
    nor disagreeing, counted in neither the numerator nor denominator."""
    unavailable_factors: tuple[str, ...]
    """Factors that were None (e.g. no benchmark configured for
    relative_strength, no sector_map for sector_strength) -- never
    treated as agreement or disagreement."""

    def explanation(self) -> str:
        if self.direction == 0:
            return "Composite score is exactly flat (0.0) -- no directional confidence is meaningful."
        agree = ", ".join(self.agreeing_factors) or "none"
        disagree = ", ".join(self.disagreeing_factors) or "none"
        return f"{len(self.agreeing_factors)} of {len(self.agreeing_factors) + len(self.disagreeing_factors)} available factor(s) agree ({agree}); disagreeing: {disagree}."


def compute_confidence(candidate: CandidateScore | None) -> ConfidenceBreakdown:
    if candidate is None:
        return ConfidenceBreakdown(score=0.0, direction=0, agreeing_factors=(), disagreeing_factors=(), neutral_factors=(), unavailable_factors=tuple(_FACTOR_NAMES))

    if candidate.composite_score > 0:
        direction = 1
    elif candidate.composite_score < 0:
        direction = -1
    else:
        direction = 0

    if direction == 0:
        return ConfidenceBreakdown(score=0.0, direction=0, agreeing_factors=(), disagreeing_factors=(), neutral_factors=(), unavailable_factors=())

    agreeing: list[str] = []
    disagreeing: list[str] = []
    neutral: list[str] = []
    unavailable: list[str] = []

    for name in _FACTOR_NAMES:
        value = getattr(candidate, name)
        if value is None:
            unavailable.append(name)
        elif value == 0:
            neutral.append(name)
        elif (value > 0) == (direction > 0):
            agreeing.append(name)
        else:
            disagreeing.append(name)

    total_considered = len(agreeing) + len(disagreeing)
    score = (len(agreeing) / total_considered) if total_considered > 0 else 0.0

    return ConfidenceBreakdown(
        score=score, direction=direction, agreeing_factors=tuple(agreeing), disagreeing_factors=tuple(disagreeing),
        neutral_factors=tuple(neutral), unavailable_factors=tuple(unavailable),
    )
