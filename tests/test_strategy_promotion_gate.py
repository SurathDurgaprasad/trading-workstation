"""Phase 6 (experiment registry & promotion gate). Synthetic return
lists below are chosen so learning.profitability.
compute_profitability_report_from_returns deterministically produces a
SPECIFIC ProfitabilityVerdict (verified empirically, not guessed):
  _POSITIVE  = [0.05]*30            -> POSITIVE_PERFORMANCE (zero variance, mean=+5%)
  _NEGATIVE  = [-0.05]*30           -> NEGATIVE_PERFORMANCE (zero variance, mean=-5%)
  _MEANINGLESS_POSITIVE_MEAN = [0.03]*27+[-0.20]*3  -> STATISTICALLY_MEANINGLESS, expectancy=+0.7%
  _MEANINGLESS_NEGATIVE_MEAN = [0.02]*20+[-0.10]*10 -> STATISTICALLY_MEANINGLESS, expectancy=-2.0%
  _TOO_FEW   = [0.05]*10            -> INSUFFICIENT_DATA (below the 30-trade floor)
"""

import pytest

from learning.profitability import ProfitabilityVerdict
from strategy.promotion_gate import PromotionVerdict, evaluate_promotion, evaluate_promotion_comprehensive

_POSITIVE = [0.05] * 30
_NEGATIVE = [-0.05] * 30
_MEANINGLESS_POSITIVE_MEAN = [0.03] * 27 + [-0.20] * 3
_MEANINGLESS_NEGATIVE_MEAN = [0.02] * 20 + [-0.10] * 10
_TOO_FEW = [0.05] * 10


def test_promoted_when_all_three_splits_are_confidently_positive():
    result = evaluate_promotion(
        "candidate", development_returns=_POSITIVE, validation_returns=_POSITIVE, out_of_sample_returns=_POSITIVE,
    )
    assert result.verdict == PromotionVerdict.PROMOTED
    assert "PROMOTED" in result.rationale


def test_negative_when_any_single_split_is_confidently_negative():
    result = evaluate_promotion(
        "candidate", development_returns=_NEGATIVE, validation_returns=_POSITIVE, out_of_sample_returns=_POSITIVE,
    )
    assert result.verdict == PromotionVerdict.NEGATIVE
    assert "development" in result.rationale


def test_insufficient_data_when_any_single_split_lacks_the_sample_floor():
    result = evaluate_promotion(
        "candidate", development_returns=_POSITIVE, validation_returns=_TOO_FEW, out_of_sample_returns=_POSITIVE,
    )
    assert result.verdict == PromotionVerdict.INSUFFICIENT_DATA
    assert "validation" in result.rationale


def test_inconclusive_when_every_split_is_positive_point_estimate_but_not_statistically_decisive():
    result = evaluate_promotion(
        "candidate",
        development_returns=_MEANINGLESS_POSITIVE_MEAN,
        validation_returns=_MEANINGLESS_POSITIVE_MEAN,
        out_of_sample_returns=_MEANINGLESS_POSITIVE_MEAN,
    )
    assert result.verdict == PromotionVerdict.INCONCLUSIVE


def test_rejected_when_mixed_and_no_split_is_confidently_negative_or_positive():
    result = evaluate_promotion(
        "candidate",
        development_returns=_MEANINGLESS_NEGATIVE_MEAN,
        validation_returns=_MEANINGLESS_POSITIVE_MEAN,
        out_of_sample_returns=_MEANINGLESS_NEGATIVE_MEAN,
    )
    assert result.verdict == PromotionVerdict.REJECTED


def test_insufficient_data_takes_priority_over_a_negative_split_elsewhere():
    # Priority ordering check: INSUFFICIENT_DATA must win even when
    # ANOTHER split would independently justify NEGATIVE -- you cannot
    # draw ANY conclusion (positive or negative) while one split has too
    # little data, regardless of what the other splits show.
    result = evaluate_promotion(
        "candidate", development_returns=_TOO_FEW, validation_returns=_NEGATIVE, out_of_sample_returns=_POSITIVE,
    )
    assert result.verdict == PromotionVerdict.INSUFFICIENT_DATA


def test_negative_takes_priority_over_what_would_otherwise_be_inconclusive():
    # Priority ordering check: a single confidently NEGATIVE split must
    # override what would otherwise look like a promising, consistent
    # INCONCLUSIVE signal from the other two splits.
    result = evaluate_promotion(
        "candidate",
        development_returns=_NEGATIVE,
        validation_returns=_MEANINGLESS_POSITIVE_MEAN,
        out_of_sample_returns=_MEANINGLESS_POSITIVE_MEAN,
    )
    assert result.verdict == PromotionVerdict.NEGATIVE


def test_evaluation_reproduces_this_sessions_own_h_exit_002_shape():
    # H_EXIT_002's real result (all three splits STATISTICALLY_MEANINGLESS
    # with a positive point-estimate expectancy) is the textbook
    # INCONCLUSIVE case this gate exists to formalize -- a direct sanity
    # check that the gate agrees with the hand-applied judgment already
    # recorded in strategy/hypothesis_registry.py for H_EXIT_002.
    result = evaluate_promotion(
        "H_EXIT_002_shape",
        development_returns=_MEANINGLESS_POSITIVE_MEAN,
        validation_returns=_MEANINGLESS_POSITIVE_MEAN,
        out_of_sample_returns=_MEANINGLESS_POSITIVE_MEAN,
    )
    assert result.verdict == PromotionVerdict.INCONCLUSIVE
    assert result.development.sample_size == 30
    assert result.candidate_name == "H_EXIT_002_shape"


# --- evaluate_promotion_comprehensive ----------------------------------


def test_comprehensive_promoted_when_base_is_promoted_and_no_comparisons_given():
    result = evaluate_promotion_comprehensive(
        "candidate", development_returns=_POSITIVE, validation_returns=_POSITIVE, out_of_sample_returns=_POSITIVE,
    )
    assert result.base_evaluation.verdict == PromotionVerdict.PROMOTED
    assert result.comprehensive_verdict == PromotionVerdict.PROMOTED
    assert result.beats_buy_and_hold is None
    assert result.beats_random_baseline is None
    assert result.beats_previous_baseline is None
    assert result.walk_forward_consistent is None
    assert result.regime_consistent is None
    assert "not checked" in result.comprehensive_rationale


def test_comprehensive_promoted_when_base_is_promoted_and_all_comparisons_pass():
    result = evaluate_promotion_comprehensive(
        "candidate", development_returns=_POSITIVE, validation_returns=_POSITIVE, out_of_sample_returns=_POSITIVE,
        buy_and_hold_mean_return_pct=1.0, random_baseline_mean_return_pct=0.5, previous_baseline_mean_return_pct=-0.64,
        walk_forward_fold_verdicts=[ProfitabilityVerdict.POSITIVE_PERFORMANCE, ProfitabilityVerdict.STATISTICALLY_MEANINGLESS],
        regime_verdicts={"TRENDING_UP": ProfitabilityVerdict.POSITIVE_PERFORMANCE},
    )
    assert result.candidate_mean_return_pct == pytest.approx(5.0)  # _POSITIVE is 0.05 -> 5%
    assert result.beats_buy_and_hold is True
    assert result.beats_random_baseline is True
    assert result.beats_previous_baseline is True
    assert result.walk_forward_consistent is True
    assert result.regime_consistent is True
    assert result.comprehensive_verdict == PromotionVerdict.PROMOTED


def test_comprehensive_rejected_when_base_promoted_but_loses_to_buy_and_hold():
    result = evaluate_promotion_comprehensive(
        "candidate", development_returns=_POSITIVE, validation_returns=_POSITIVE, out_of_sample_returns=_POSITIVE,
        buy_and_hold_mean_return_pct=50.0,  # far above the candidate's own 5%
    )
    assert result.base_evaluation.verdict == PromotionVerdict.PROMOTED
    assert result.beats_buy_and_hold is False
    assert result.comprehensive_verdict == PromotionVerdict.REJECTED
    assert "beats_buy_and_hold" in result.comprehensive_rationale


def test_comprehensive_rejected_when_a_walk_forward_fold_is_negative():
    result = evaluate_promotion_comprehensive(
        "candidate", development_returns=_POSITIVE, validation_returns=_POSITIVE, out_of_sample_returns=_POSITIVE,
        walk_forward_fold_verdicts=[ProfitabilityVerdict.POSITIVE_PERFORMANCE, ProfitabilityVerdict.NEGATIVE_PERFORMANCE],
    )
    assert result.walk_forward_consistent is False
    assert result.comprehensive_verdict == PromotionVerdict.REJECTED


def test_comprehensive_rejected_when_a_regime_bucket_is_negative():
    result = evaluate_promotion_comprehensive(
        "candidate", development_returns=_POSITIVE, validation_returns=_POSITIVE, out_of_sample_returns=_POSITIVE,
        regime_verdicts={"TRENDING_UP": ProfitabilityVerdict.POSITIVE_PERFORMANCE, "SIDEWAYS": ProfitabilityVerdict.NEGATIVE_PERFORMANCE},
    )
    assert result.regime_consistent is False
    assert result.comprehensive_verdict == PromotionVerdict.REJECTED


def test_comprehensive_verdict_inherits_negative_base_regardless_of_comparisons():
    # Even beating every benchmark cannot rescue a candidate that fails
    # its own underlying statistical bar -- comparisons are moot.
    result = evaluate_promotion_comprehensive(
        "candidate", development_returns=_NEGATIVE, validation_returns=_NEGATIVE, out_of_sample_returns=_NEGATIVE,
        buy_and_hold_mean_return_pct=-99.0, random_baseline_mean_return_pct=-99.0,
    )
    assert result.base_evaluation.verdict == PromotionVerdict.NEGATIVE
    assert result.comprehensive_verdict == PromotionVerdict.NEGATIVE
    assert "moot" in result.comprehensive_rationale


def test_comprehensive_verdict_inherits_inconclusive_base():
    result = evaluate_promotion_comprehensive(
        "candidate",
        development_returns=_MEANINGLESS_POSITIVE_MEAN,
        validation_returns=_MEANINGLESS_POSITIVE_MEAN,
        out_of_sample_returns=_MEANINGLESS_POSITIVE_MEAN,
    )
    assert result.base_evaluation.verdict == PromotionVerdict.INCONCLUSIVE
    assert result.comprehensive_verdict == PromotionVerdict.INCONCLUSIVE


def test_comprehensive_evaluation_reproduces_this_missions_own_real_baseline_result():
    # Real figures from this project's own scientific final report: the
    # frozen TrendMomentumBaseline's pooled mean return is -0.64%, and it
    # underperformed 96% of random-entry Monte Carlo iterations (whose
    # own average was -0.06%). A comprehensive evaluation using these
    # real numbers must land on the same NEGATIVE verdict already
    # reported -- a direct sanity check that this new gate agrees with
    # the mission's own already-published conclusion.
    baseline_returns = [-0.0064] * 30  # stand-in for the real pooled -0.64% mean (base verdict only needs the mean/CI shape)
    result = evaluate_promotion_comprehensive(
        "trend_momentum_baseline", development_returns=baseline_returns, validation_returns=baseline_returns,
        out_of_sample_returns=baseline_returns, random_baseline_mean_return_pct=-0.06,
    )
    assert result.base_evaluation.verdict == PromotionVerdict.NEGATIVE
    assert result.comprehensive_verdict == PromotionVerdict.NEGATIVE
