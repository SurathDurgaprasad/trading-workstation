from datetime import datetime

import pytest

from decision_engine.confidence import compute_confidence
from market_intelligence.models import CandidateScore


def _candidate(**overrides) -> CandidateScore:
    defaults = dict(
        symbol="AAPL", as_of=datetime(2024, 6, 1), last_close=100.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.0, trend_score=1.0, momentum_score=0.5, breakout_score=0.1,
        relative_strength_score=0.05, sector_strength_score=0.02, composite_score=1.67, explanation=["fake"],
    )
    defaults.update(overrides)
    return CandidateScore(**defaults)


def test_no_candidate_gives_zero_confidence_and_all_unavailable():
    breakdown = compute_confidence(None)
    assert breakdown.score == 0.0
    assert breakdown.direction == 0
    assert len(breakdown.unavailable_factors) == 5


def test_flat_composite_gives_zero_confidence():
    candidate = _candidate(composite_score=0.0)
    breakdown = compute_confidence(candidate)
    assert breakdown.score == 0.0
    assert breakdown.direction == 0


def test_all_factors_agreeing_gives_full_confidence():
    candidate = _candidate(trend_score=1.0, momentum_score=0.5, breakout_score=0.1, relative_strength_score=0.05, sector_strength_score=0.02, composite_score=1.67)
    breakdown = compute_confidence(candidate)
    assert breakdown.score == pytest.approx(1.0)
    assert breakdown.direction == 1
    assert set(breakdown.agreeing_factors) == {"trend_score", "momentum_score", "breakout_score", "relative_strength_score", "sector_strength_score"}
    assert breakdown.disagreeing_factors == ()


def test_partial_agreement_computes_a_fraction():
    # composite positive, but momentum and breakout disagree -> 3 of 5 agree
    candidate = _candidate(trend_score=1.0, momentum_score=-0.2, breakout_score=-0.1, relative_strength_score=0.05, sector_strength_score=0.02, composite_score=0.75)
    breakdown = compute_confidence(candidate)
    assert breakdown.score == pytest.approx(3 / 5)
    assert set(breakdown.agreeing_factors) == {"trend_score", "relative_strength_score", "sector_strength_score"}
    assert set(breakdown.disagreeing_factors) == {"momentum_score", "breakout_score"}


def test_negative_direction_agreement():
    candidate = _candidate(trend_score=-1.0, momentum_score=-0.5, breakout_score=-0.1, relative_strength_score=-0.05, sector_strength_score=-0.02, composite_score=-1.67)
    breakdown = compute_confidence(candidate)
    assert breakdown.direction == -1
    assert breakdown.score == pytest.approx(1.0)


def test_unavailable_factors_are_excluded_from_the_denominator():
    candidate = _candidate(relative_strength_score=None, sector_strength_score=None, trend_score=1.0, momentum_score=1.0, breakout_score=1.0, composite_score=3.0)
    breakdown = compute_confidence(candidate)
    assert breakdown.score == pytest.approx(1.0)  # 3 of 3 AVAILABLE agree
    assert set(breakdown.unavailable_factors) == {"relative_strength_score", "sector_strength_score"}


def test_neutral_zero_factors_are_excluded_from_both_sides():
    candidate = _candidate(trend_score=0.0, momentum_score=1.0, breakout_score=1.0, relative_strength_score=1.0, sector_strength_score=1.0, composite_score=4.0)
    breakdown = compute_confidence(candidate)
    assert "trend_score" in breakdown.neutral_factors
    assert breakdown.score == pytest.approx(1.0)  # 4 of 4 non-neutral, non-unavailable agree




def test_explanation_is_a_readable_string():
    candidate = _candidate()
    breakdown = compute_confidence(candidate)
    text = breakdown.explanation()
    assert "of" in text and "agree" in text


def test_explanation_for_flat_composite():
    breakdown = compute_confidence(_candidate(composite_score=0.0))
    assert "flat" in breakdown.explanation().lower()
