"""Phase 38 -- learning.adaptation.compare_and_recommend is a pure
function of two already-computed ExperimentComparison objects. No store,
no network, no config file is touched anywhere in this file."""

from datetime import datetime, timezone

from experiments.comparison import ExperimentComparison
from experiments.models import ConfigType, Experiment
from learning.adaptation import (
    MIN_IMPROVEMENT_MARGIN,
    MIN_SAMPLE_SIZE_FOR_PROMOTION,
    PromotionVerdict,
    compare_and_recommend,
)


def _experiment(experiment_id: str, config_version: str) -> Experiment:
    return Experiment(
        experiment_id=experiment_id, name=f"experiment {experiment_id}", description="fake",
        config_type=ConfigType.DECISION_ENGINE, config_version=config_version,
        started_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def _comparison(
    experiment_id: str, config_version: str, *, resolved: int, win_rate: float | None,
    average_return: float | None = 0.02, profit_factor: float | None = 1.5,
) -> ExperimentComparison:
    return ExperimentComparison(
        experiment=_experiment(experiment_id, config_version), ended_at=None, total=resolved, resolved=resolved,
        win_rate=win_rate, average_return=average_return, profit_factor=profit_factor,
    )


def test_recommend_promotion_when_both_thresholds_are_met():
    baseline = _comparison("exp-A", "cfg-A", resolved=30, win_rate=0.50)
    candidate = _comparison("exp-B", "cfg-B", resolved=30, win_rate=0.70)

    result = compare_and_recommend(baseline, candidate)

    assert result.verdict == PromotionVerdict.RECOMMEND_PROMOTION
    assert any("RECOMMENDATION ONLY" in line for line in result.reasoning)


def test_insufficient_evidence_when_candidate_sample_too_small():
    baseline = _comparison("exp-A", "cfg-A", resolved=30, win_rate=0.50)
    candidate = _comparison("exp-B", "cfg-B", resolved=MIN_SAMPLE_SIZE_FOR_PROMOTION - 1, win_rate=0.90)

    result = compare_and_recommend(baseline, candidate)

    assert result.verdict == PromotionVerdict.INSUFFICIENT_EVIDENCE
    assert any(str(MIN_SAMPLE_SIZE_FOR_PROMOTION) in line for line in result.reasoning)


def test_insufficient_evidence_when_baseline_sample_too_small():
    baseline = _comparison("exp-A", "cfg-A", resolved=5, win_rate=0.50)
    candidate = _comparison("exp-B", "cfg-B", resolved=40, win_rate=0.90)

    result = compare_and_recommend(baseline, candidate)

    assert result.verdict == PromotionVerdict.INSUFFICIENT_EVIDENCE


def test_no_improvement_when_margin_below_threshold():
    baseline = _comparison("exp-A", "cfg-A", resolved=30, win_rate=0.50)
    candidate = _comparison("exp-B", "cfg-B", resolved=30, win_rate=0.55)  # only +5pp, below the 10pp bar

    result = compare_and_recommend(baseline, candidate)

    assert result.verdict == PromotionVerdict.NO_IMPROVEMENT


def test_margin_exactly_at_threshold_recommends_promotion():
    baseline = _comparison("exp-A", "cfg-A", resolved=30, win_rate=0.50)
    candidate = _comparison("exp-B", "cfg-B", resolved=30, win_rate=0.50 + MIN_IMPROVEMENT_MARGIN)

    result = compare_and_recommend(baseline, candidate)

    assert result.verdict == PromotionVerdict.RECOMMEND_PROMOTION


def test_insufficient_evidence_when_configs_are_identical():
    baseline = _comparison("exp-A", "cfg-SAME", resolved=100, win_rate=0.40)
    candidate = _comparison("exp-B", "cfg-SAME", resolved=100, win_rate=0.90)

    result = compare_and_recommend(baseline, candidate)

    assert result.verdict == PromotionVerdict.INSUFFICIENT_EVIDENCE
    assert any("same config_version" in line for line in result.reasoning)


def test_insufficient_evidence_when_win_rate_is_none():
    baseline = _comparison("exp-A", "cfg-A", resolved=30, win_rate=None)
    candidate = _comparison("exp-B", "cfg-B", resolved=30, win_rate=0.90)

    result = compare_and_recommend(baseline, candidate)

    assert result.verdict == PromotionVerdict.INSUFFICIENT_EVIDENCE


def test_candidate_worse_than_baseline_is_no_improvement_not_a_crash():
    baseline = _comparison("exp-A", "cfg-A", resolved=30, win_rate=0.80)
    candidate = _comparison("exp-B", "cfg-B", resolved=30, win_rate=0.30)

    result = compare_and_recommend(baseline, candidate)

    assert result.verdict == PromotionVerdict.NO_IMPROVEMENT


def test_reasoning_is_never_empty_for_any_verdict():
    baseline = _comparison("exp-A", "cfg-A", resolved=30, win_rate=0.50)
    candidate = _comparison("exp-B", "cfg-B", resolved=30, win_rate=0.70)
    result = compare_and_recommend(baseline, candidate)
    assert len(result.reasoning) > 0


def test_promotion_recommendation_is_frozen():
    import pytest

    baseline = _comparison("exp-A", "cfg-A", resolved=30, win_rate=0.50)
    candidate = _comparison("exp-B", "cfg-B", resolved=30, win_rate=0.70)
    result = compare_and_recommend(baseline, candidate)
    with pytest.raises(Exception):
        result.verdict = PromotionVerdict.NO_IMPROVEMENT
