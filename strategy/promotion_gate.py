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


class ComprehensivePromotionEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True)

    base_evaluation: PromotionEvaluation
    """The unchanged, existing dev/val/oos verdict -- a comprehensive
    PROMOTED verdict can never be more permissive than this; it can only
    add MORE required conditions on top."""
    candidate_mean_return_pct: float
    """Simple mean of every development+validation+out_of_sample return
    combined, expressed as a percentage -- the ONE number every optional
    comparison below is measured against. Not itself a substitute for
    base_evaluation's own split-by-split statistical rigor; a single
    summary figure for comparison purposes only."""
    beats_buy_and_hold: bool | None
    """None means "not checked" (no buy_and_hold_mean_return_pct was
    given) -- NEVER treated as "passed". See comprehensive_rationale for
    which comparisons were actually evaluated."""
    beats_random_baseline: bool | None
    beats_previous_baseline: bool | None
    walk_forward_consistent: bool | None
    """None means "not checked". True means NO walk-forward fold in the
    list provided reached a confident NEGATIVE_PERFORMANCE verdict."""
    regime_consistent: bool | None
    """None means "not checked". True means NO regime bucket in the
    mapping provided (already filtered by the caller to buckets with
    sufficient sample size) reached a confident NEGATIVE_PERFORMANCE
    verdict."""
    comprehensive_verdict: PromotionVerdict
    comprehensive_rationale: str


def evaluate_promotion_comprehensive(
    candidate_name: str,
    *,
    development_returns: list[float],
    validation_returns: list[float],
    out_of_sample_returns: list[float],
    buy_and_hold_mean_return_pct: float | None = None,
    random_baseline_mean_return_pct: float | None = None,
    previous_baseline_mean_return_pct: float | None = None,
    walk_forward_fold_verdicts: list[ProfitabilityVerdict] | None = None,
    regime_verdicts: dict[str, ProfitabilityVerdict] | None = None,
) -> ComprehensivePromotionEvaluation:
    """Extends evaluate_promotion() (reused unchanged, never re-
    implemented) with the mission's own required comparisons: buy-and-
    hold, random-entry Monte Carlo, the previous (frozen) baseline,
    walk-forward consistency across independent rolling windows, and
    regime consistency across market conditions. Every comparison is
    OPTIONAL to call with -- a caller doing a partial check need not
    have all five ready -- but a comparison that IS provided becomes a
    REQUIRED condition for a PROMOTED verdict; nothing is ever silently
    treated as "passed" just because it wasn't checked.

    A candidate can only reach comprehensive PROMOTED if:
      1. evaluate_promotion()'s own base verdict is PROMOTED (all three
         splits confidently POSITIVE_PERFORMANCE), AND
      2. every comparison the caller DID provide evaluates to True.

    If the base verdict is not PROMOTED, the comprehensive verdict
    inherits it directly (NEGATIVE/INCONCLUSIVE/REJECTED/
    INSUFFICIENT_DATA) -- no amount of beating a benchmark rescues a
    candidate that fails the underlying statistical bar. If the base
    verdict IS PROMOTED but a required comparison fails, the
    comprehensive verdict downgrades to REJECTED (clears the statistical
    bar on its own trades, but loses to a real benchmark it must beat)."""
    base_evaluation = evaluate_promotion(
        candidate_name, development_returns=development_returns, validation_returns=validation_returns,
        out_of_sample_returns=out_of_sample_returns,
    )

    all_returns = development_returns + validation_returns + out_of_sample_returns
    candidate_mean_return_pct = (sum(all_returns) / len(all_returns) * 100.0) if all_returns else 0.0

    beats_buy_and_hold = candidate_mean_return_pct > buy_and_hold_mean_return_pct if buy_and_hold_mean_return_pct is not None else None
    beats_random_baseline = candidate_mean_return_pct > random_baseline_mean_return_pct if random_baseline_mean_return_pct is not None else None
    beats_previous_baseline = candidate_mean_return_pct > previous_baseline_mean_return_pct if previous_baseline_mean_return_pct is not None else None
    walk_forward_consistent = (
        not any(v == ProfitabilityVerdict.NEGATIVE_PERFORMANCE for v in walk_forward_fold_verdicts)
        if walk_forward_fold_verdicts is not None else None
    )
    regime_consistent = (
        not any(v == ProfitabilityVerdict.NEGATIVE_PERFORMANCE for v in regime_verdicts.values())
        if regime_verdicts is not None else None
    )

    checks = {
        "beats_buy_and_hold": beats_buy_and_hold, "beats_random_baseline": beats_random_baseline,
        "beats_previous_baseline": beats_previous_baseline, "walk_forward_consistent": walk_forward_consistent,
        "regime_consistent": regime_consistent,
    }
    checked = {name: value for name, value in checks.items() if value is not None}
    skipped = [name for name, value in checks.items() if value is None]
    failed = [name for name, value in checked.items() if value is False]

    if base_evaluation.verdict != PromotionVerdict.PROMOTED:
        comprehensive_verdict = base_evaluation.verdict
        comprehensive_rationale = (
            f"{comprehensive_verdict.value}: inherited directly from the base dev/val/oos evaluation "
            f"({base_evaluation.rationale}) -- comparisons against benchmarks are moot until the underlying "
            "statistical bar is cleared."
        )
    elif failed:
        comprehensive_verdict = PromotionVerdict.REJECTED
        comprehensive_rationale = (
            f"REJECTED: the base dev/val/oos evaluation is PROMOTED, but the candidate fails required "
            f"comparison(s): {', '.join(failed)}. Clearing its own statistical bar is not sufficient -- it "
            "must also beat every real benchmark it was compared against."
        )
    else:
        comprehensive_verdict = PromotionVerdict.PROMOTED
        skipped_note = f" (not checked: {', '.join(skipped)})" if skipped else ""
        comprehensive_rationale = (
            f"PROMOTED: the base dev/val/oos evaluation is PROMOTED and every provided comparison "
            f"({', '.join(checked) or 'none'}) passed{skipped_note}."
        )

    return ComprehensivePromotionEvaluation(
        base_evaluation=base_evaluation, candidate_mean_return_pct=candidate_mean_return_pct,
        beats_buy_and_hold=beats_buy_and_hold, beats_random_baseline=beats_random_baseline,
        beats_previous_baseline=beats_previous_baseline, walk_forward_consistent=walk_forward_consistent,
        regime_consistent=regime_consistent, comprehensive_verdict=comprehensive_verdict,
        comprehensive_rationale=comprehensive_rationale,
    )
