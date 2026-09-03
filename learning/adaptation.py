"""Phase 38 -- controlled adaptive learning: a PROMOTION RECOMMENDATION,
never an automatic config change.

The roadmap's own instruction for this phase is explicit: "DO NOT allow
uncontrolled autonomous strategy mutation... No automatic production
promotion without evidence thresholds. All changes must be auditable."

This module is deliberately narrow. It does not generate parameter
candidates, run backtests, or touch any config file -- Phase 37's
`experiments/` registry and `experiments.comparison.compare_experiments`
already provide the full pipeline this phase's roadmap text describes as
"Prediction Outcomes -> Performance Analysis -> ... -> Comparison": a
human registers a baseline experiment (the current config) and a
candidate experiment (a config they deliberately changed and started
tracking), runs both for a while, then asks this module for a verdict.

`compare_and_recommend` is a pure, deterministic function of two already
-computed `ExperimentComparison` objects. It NEVER reads or writes any
config file, and it never chooses what to compare -- the human supplies
both experiment ids. The only output is an explainable
`PromotionRecommendation` record with one of three verdicts; promoting a
config remains an entirely manual step (edit the config's own source,
then register a NEW experiment to track it) that this module cannot
perform and does not attempt to.
"""

from dataclasses import dataclass
from enum import Enum

from experiments.comparison import ExperimentComparison

MIN_SAMPLE_SIZE_FOR_PROMOTION = 30
"""A conservative, stated rule-of-thumb threshold (roughly where a normal
approximation to a binomial proportion starts to be reasonable) -- not a
guarantee of significance. Even at this size a personal trading system's
sample is small; the recommendation's own reasoning says so explicitly
rather than letting a passed threshold read as "proven"."""

MIN_IMPROVEMENT_MARGIN = 0.10
"""The candidate's win rate must exceed the baseline's by at least this
many percentage points before promotion is recommended -- deliberately
wide to absorb small-sample noise, not tuned against any historical
result."""


class PromotionVerdict(str, Enum):
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    """Sample size threshold not met, or a comparison isn't meaningful
    (e.g. same config_version on both sides)."""
    NO_IMPROVEMENT = "NO_IMPROVEMENT"
    """Both experiments have enough data, but the candidate's win rate
    does not exceed the baseline's by the minimum margin."""
    RECOMMEND_PROMOTION = "RECOMMEND_PROMOTION"
    """Both thresholds are met. Still advisory only -- see
    PromotionRecommendation's own docstring."""


@dataclass(frozen=True)
class PromotionRecommendation:
    baseline: ExperimentComparison
    candidate: ExperimentComparison
    verdict: PromotionVerdict
    reasoning: list[str]
    """Every number and threshold that produced `verdict`, in order --
    fully auditable without re-running the computation."""


def compare_and_recommend(baseline: ExperimentComparison, candidate: ExperimentComparison) -> PromotionRecommendation:
    reasoning: list[str] = []

    if baseline.experiment.config_version == candidate.experiment.config_version:
        reasoning.append(
            f"Baseline and candidate share the same config_version ({baseline.experiment.config_version}) -- "
            "not a meaningful comparison. Register a genuinely different, deliberately-changed config as the candidate."
        )
        return PromotionRecommendation(baseline=baseline, candidate=candidate, verdict=PromotionVerdict.INSUFFICIENT_EVIDENCE, reasoning=reasoning)

    if baseline.resolved < MIN_SAMPLE_SIZE_FOR_PROMOTION or candidate.resolved < MIN_SAMPLE_SIZE_FOR_PROMOTION:
        reasoning.append(
            f"Baseline has {baseline.resolved} resolved prediction(s); candidate has {candidate.resolved}. "
            f"Both must reach at least {MIN_SAMPLE_SIZE_FOR_PROMOTION} before any promotion is considered."
        )
        reasoning.append(
            f"Note: {MIN_SAMPLE_SIZE_FOR_PROMOTION} samples is still a SMALL sample for a trading strategy -- "
            "treat any verdict from a dataset this size as preliminary, not conclusive."
        )
        return PromotionRecommendation(baseline=baseline, candidate=candidate, verdict=PromotionVerdict.INSUFFICIENT_EVIDENCE, reasoning=reasoning)

    if baseline.win_rate is None or candidate.win_rate is None:
        reasoning.append("Win rate could not be computed for one of the two experiments (no resolved prediction had a recorded return).")
        return PromotionRecommendation(baseline=baseline, candidate=candidate, verdict=PromotionVerdict.INSUFFICIENT_EVIDENCE, reasoning=reasoning)

    margin = candidate.win_rate - baseline.win_rate
    reasoning.append(
        f"Baseline win rate: {baseline.win_rate:+.2%} over {baseline.resolved} resolved prediction(s) "
        f"(config_version={baseline.experiment.config_version})."
    )
    reasoning.append(
        f"Candidate win rate: {candidate.win_rate:+.2%} over {candidate.resolved} resolved prediction(s) "
        f"(config_version={candidate.experiment.config_version})."
    )
    reasoning.append(f"Win rate margin: {margin:+.2%} (minimum required for promotion: +{MIN_IMPROVEMENT_MARGIN:.0%}).")
    if baseline.average_return is not None and candidate.average_return is not None:
        reasoning.append(
            f"Average return -- baseline: {baseline.average_return:+.2%}, candidate: {candidate.average_return:+.2%} "
            "(informational only, not part of the promotion threshold)."
        )

    if margin < MIN_IMPROVEMENT_MARGIN - 1e-9:  # float-epsilon tolerance: a margin computed as exactly the threshold must not miss it by rounding
        reasoning.append("Margin does not meet the minimum improvement threshold -- promotion is NOT recommended.")
        return PromotionRecommendation(baseline=baseline, candidate=candidate, verdict=PromotionVerdict.NO_IMPROVEMENT, reasoning=reasoning)

    reasoning.append(
        "Candidate meets both the minimum sample size and minimum improvement margin. "
        "This is a RECOMMENDATION ONLY -- no configuration has been changed. Promotion, if desired, remains a "
        "manual step: edit the relevant config's own source, then register a NEW experiment to track it going forward."
    )
    return PromotionRecommendation(baseline=baseline, candidate=candidate, verdict=PromotionVerdict.RECOMMEND_PROMOTION, reasoning=reasoning)
