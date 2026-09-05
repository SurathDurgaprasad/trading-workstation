"""Strategy science, Phase 6 (experiment registry & promotion gate) --
this project's own core operating principle, stated at the top of every
mission this session has followed: "the system must earn the right to
promote a strategy. No strategy becomes the production paper-trading
strategy merely from a high win rate, attractive charts, one favorable
period/symbol, or in-sample parameter tuning." Every H_EXIT_*/H_ENTRY_*
experiment this session ran its own dev/val/oos split and applied this
SAME rule by hand (see strategy/hypothesis_registry.py's own evidence
fields); this module makes that rule a single, tested, reusable
function instead of five hand-repeated judgment calls, so a future
candidate is held to the identical bar mechanically, not by memory.

Reuses learning.profitability.compute_profitability_report_from_returns
UNCHANGED -- the SAME statistical standard (Wilson-CI win rate,
normal-approximation mean-return CI, MIN_SAMPLE_SIZE_FOR_A_VERDICT=30)
already used everywhere else in this project, never a second, competing
method invented here.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict

from learning.profitability import ProfitabilityReport, ProfitabilityVerdict, compute_profitability_report_from_returns


class PromotionVerdict(str, Enum):
    PROMOTED = "PROMOTED"
    """ALL THREE splits (development, validation, out-of-sample) reach a
    confident POSITIVE_PERFORMANCE verdict -- the only case that clears
    the bar to become the live paper-trading strategy."""
    NEGATIVE = "NEGATIVE"
    """At least one split shows a confident NEGATIVE_PERFORMANCE verdict
    -- decisive evidence of harm, not merely "not yet proven.\""""
    INCONCLUSIVE = "INCONCLUSIVE"
    """No split is NEGATIVE_PERFORMANCE and every split's point-estimate
    expectancy is positive, but at least one split's confidence interval
    still straddles zero (STATISTICALLY_MEANINGLESS) -- a real,
    consistent, directionally favorable signal that is not yet
    statistically decisive. Matches this session's own H_EXIT_002
    result exactly."""
    REJECTED = "REJECTED"
    """No split is NEGATIVE_PERFORMANCE or INSUFFICIENT_DATA, but results
    are mixed rather than consistently positive (at least one split's
    own point-estimate expectancy is zero or negative) -- inconsistent
    evidence, not a decisive negative finding but not promotable
    either. Matches this session's own H_EXIT_003/H_EXIT_004 results."""
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    """At least one split has fewer than
    learning.profitability.MIN_SAMPLE_SIZE_FOR_A_VERDICT trades --
    nothing can be concluded, positive or negative, about that split."""


class PromotionEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_name: str
    development: ProfitabilityReport
    validation: ProfitabilityReport
    out_of_sample: ProfitabilityReport
    verdict: PromotionVerdict
    rationale: str
    """A human-readable explanation of exactly which rule fired and
    why -- fully auditable without re-running the evaluation, same
    spirit as ProfitabilityReport.reasoning."""


def evaluate_promotion(
    candidate_name: str,
    *,
    development_returns: list[float],
    validation_returns: list[float],
    out_of_sample_returns: list[float],
) -> PromotionEvaluation:
    """Applies this project's own promotion rule (stated identically in
    every H_EXIT_*/H_ENTRY_* record's success_criteria/failure_criteria
    this session) mechanically:

      1. Any split with fewer than MIN_SAMPLE_SIZE_FOR_A_VERDICT trades
         -> INSUFFICIENT_DATA (nothing else can be concluded).
      2. Any split showing a confident NEGATIVE_PERFORMANCE verdict
         -> NEGATIVE (decisive harm).
      3. ALL three splits showing a confident POSITIVE_PERFORMANCE
         verdict -> PROMOTED (clears the bar).
      4. ALL three splits' point-estimate expectancy is positive, but at
         least one is not yet statistically decisive
         (STATISTICALLY_MEANINGLESS) -> INCONCLUSIVE (directionally
         promising, not proven).
      5. Otherwise (mixed: no split negative, not all positive)
         -> REJECTED (inconsistent, does not clear the bar).
    """
    development = compute_profitability_report_from_returns(development_returns)
    validation = compute_profitability_report_from_returns(validation_returns)
    out_of_sample = compute_profitability_report_from_returns(out_of_sample_returns)
    reports = {"development": development, "validation": validation, "out_of_sample": out_of_sample}

    insufficient = [name for name, r in reports.items() if r.verdict == ProfitabilityVerdict.INSUFFICIENT_DATA]
    if insufficient:
        verdict = PromotionVerdict.INSUFFICIENT_DATA
        rationale = (
            f"INSUFFICIENT_DATA: {', '.join(insufficient)} split(s) have fewer than 30 trades -- "
            "nothing can be concluded, positive or negative, until more data accumulates."
        )
        return PromotionEvaluation(
            candidate_name=candidate_name, development=development, validation=validation,
            out_of_sample=out_of_sample, verdict=verdict, rationale=rationale,
        )

    negative = [name for name, r in reports.items() if r.verdict == ProfitabilityVerdict.NEGATIVE_PERFORMANCE]
    if negative:
        verdict = PromotionVerdict.NEGATIVE
        rationale = (
            f"NEGATIVE: {', '.join(negative)} split(s) show a confident NEGATIVE_PERFORMANCE verdict -- "
            "decisive evidence of harm, not merely unproven. Must not be promoted."
        )
        return PromotionEvaluation(
            candidate_name=candidate_name, development=development, validation=validation,
            out_of_sample=out_of_sample, verdict=verdict, rationale=rationale,
        )

    if all(r.verdict == ProfitabilityVerdict.POSITIVE_PERFORMANCE for r in reports.values()):
        verdict = PromotionVerdict.PROMOTED
        rationale = (
            "PROMOTED: development, validation, and out-of-sample all show a confident POSITIVE_PERFORMANCE "
            "verdict with sufficient sample size -- clears this project's own promotion bar."
        )
        return PromotionEvaluation(
            candidate_name=candidate_name, development=development, validation=validation,
            out_of_sample=out_of_sample, verdict=verdict, rationale=rationale,
        )

    if all((r.expectancy or 0.0) > 0 for r in reports.values()):
        verdict = PromotionVerdict.INCONCLUSIVE
        rationale = (
            "INCONCLUSIVE: every split's point-estimate expectancy is positive (a real, consistent, "
            "directionally favorable signal), but at least one split's confidence interval still straddles "
            "zero -- not yet statistically decisive. Must not be promoted on this evidence alone."
        )
        return PromotionEvaluation(
            candidate_name=candidate_name, development=development, validation=validation,
            out_of_sample=out_of_sample, verdict=verdict, rationale=rationale,
        )

    verdict = PromotionVerdict.REJECTED
    rationale = (
        "REJECTED: results are mixed rather than consistently positive across all three splits -- at least "
        "one split's own point-estimate expectancy is zero or negative, though none reaches a confident "
        "NEGATIVE_PERFORMANCE verdict. Inconsistent evidence does not clear the promotion bar."
    )
    return PromotionEvaluation(
        candidate_name=candidate_name, development=development, validation=validation,
        out_of_sample=out_of_sample, verdict=verdict, rationale=rationale,
    )
