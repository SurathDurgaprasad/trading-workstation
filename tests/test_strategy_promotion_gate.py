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

from strategy.promotion_gate import PromotionVerdict, evaluate_promotion

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
