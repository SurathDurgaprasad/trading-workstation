"""NSE PREDICTION ENGINE mission, Phase 5: a directional (UP/DOWN/NO_EDGE)
assessment, distinct from decision_engine.rules.classify's BUY/WATCH/
AVOID/EXIT/NO_ACTION label.

Why this is a SEPARATE module rather than an extension of classify():
classify() drives real behavior in the live pipeline (its label reaches
risk.engine and paper.engine) and is structurally LONG-ONLY -- it has no
concept of "predicted DOWN" at all, only "not a BUY right now" (AVOID/
WATCH), because this project never places a short/sell-to-open order and
must not grow a code path that looks like it could. This module answers
a DIFFERENT, narrower question -- "which way does the AVAILABLE evidence
point, for TRACKING/CALIBRATION purposes only" -- and is never imported
by critic/, risk/, or paper/. A DOWN label here is a forecast to measure
later (see predictions/ for the mechanism, though today's PredictionRecord
only tracks BUY-shaped price levels -- extending it to score a DOWN
forecast's own accuracy without ever implying a short trade is a natural
next step, not yet built).

Deliberately reuses decision_engine.confidence.compute_confidence's
`direction` (+1/0/-1, from CandidateScore.composite_score's own sign)
and `score` (0.0-1.0 factor-agreement fraction) COMPLETELY UNCHANGED --
no new threshold, no new weight, nothing "tuned." Per this mission's own
explicit rule ("Do NOT assign arbitrary weights and call them
intelligence... weights must come from historical evidence, controlled
experiments, documented rationale, out-of-sample validation"), inventing
a NEW confidence cutoff for NO_EDGE here (e.g. "call it NO_EDGE below
0.6") would be exactly that kind of unearned number. NO_EDGE is
therefore ONLY the composite_score == 0 case classify() and
compute_confidence already treat as directionless -- the confidence
SCORE itself (returned alongside the label) is what tells a caller how
much evidence backs a nonzero direction, read together, never collapsed
into a single fabricated cutoff.
"""

from dataclasses import dataclass
from enum import Enum

from decision_engine.confidence import ConfidenceBreakdown, compute_confidence
from market_intelligence.models import CandidateScore

_FACTOR_LABELS = {
    "trend_score": "Trend",
    "momentum_score": "Momentum (RSI)",
    "breakout_score": "Breakout",
    "relative_strength_score": "Relative strength vs. benchmark",
    "sector_strength_score": "Sector strength",
}


class DirectionLabel(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    NO_EDGE = "NO_EDGE"


@dataclass(frozen=True)
class DirectionalAssessment:
    symbol: str
    label: DirectionLabel
    confidence: float
    """decision_engine.confidence.compute_confidence's own score,
    unchanged -- 0.0-1.0 fraction of available factors agreeing with
    `label`'s direction. 0.0 for NO_EDGE (no direction to agree with)."""
    bullish_evidence: tuple[str, ...]
    """Named factors whose sign points UP, as plain-language bullets --
    populated regardless of `label` (e.g. a DOWN-labeled symbol can still
    have one bullish factor; it is shown as a genuine contradiction, not
    hidden)."""
    bearish_evidence: tuple[str, ...]
    contradicting_evidence: tuple[str, ...]
    """Factors disagreeing with `label`'s own direction -- for UP this
    equals bearish_evidence, for DOWN this equals bullish_evidence, for
    NO_EDGE this is empty (nothing to contradict a direction that was
    never asserted). Named separately so a caller doesn't have to
    re-derive "which evidence list argues against the label" itself."""
    unavailable_factors: tuple[str, ...]
    """Named factors that were None (no benchmark configured, no sector
    map, etc.) -- never silently treated as neutral or absent evidence."""

    def to_lines(self) -> list[str]:
        lines = [f"Direction: {self.label.value}  Confidence: {self.confidence:.0%}"]
        lines.append(f"Bullish evidence: {'; '.join(self.bullish_evidence) or 'none'}")
        lines.append(f"Bearish evidence: {'; '.join(self.bearish_evidence) or 'none'}")
        if self.unavailable_factors:
            lines.append(f"Unavailable: {', '.join(self.unavailable_factors)}")
        return lines


def _factor_line(name: str, value: float) -> str:
    return f"{_FACTOR_LABELS.get(name, name)} ({value:+.2f})"


def classify_direction(candidate: CandidateScore | None) -> DirectionalAssessment:
    symbol = candidate.symbol if candidate is not None else "UNKNOWN"
    breakdown: ConfidenceBreakdown = compute_confidence(candidate)

    if breakdown.direction > 0:
        label = DirectionLabel.UP
    elif breakdown.direction < 0:
        label = DirectionLabel.DOWN
    else:
        label = DirectionLabel.NO_EDGE

    if candidate is None:
        return DirectionalAssessment(
            symbol=symbol, label=label, confidence=0.0,
            bullish_evidence=(), bearish_evidence=(), contradicting_evidence=(), unavailable_factors=(),
        )

    bullish = tuple(_factor_line(name, getattr(candidate, name)) for name in breakdown.agreeing_factors + breakdown.disagreeing_factors + breakdown.neutral_factors if getattr(candidate, name) > 0)
    bearish = tuple(_factor_line(name, getattr(candidate, name)) for name in breakdown.agreeing_factors + breakdown.disagreeing_factors + breakdown.neutral_factors if getattr(candidate, name) < 0)

    if label == DirectionLabel.UP:
        contradicting = bearish
    elif label == DirectionLabel.DOWN:
        contradicting = bullish
    else:
        contradicting = ()

    return DirectionalAssessment(
        symbol=symbol, label=label, confidence=breakdown.score,
        bullish_evidence=bullish, bearish_evidence=bearish, contradicting_evidence=contradicting,
        unavailable_factors=breakdown.unavailable_factors,
    )
