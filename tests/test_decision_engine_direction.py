"""NSE PREDICTION ENGINE mission: tests for decision_engine/direction.py
-- the UP/DOWN/NO_EDGE directional assessment, kept structurally separate
from decision_engine.rules.classify's BUY/WATCH/AVOID/EXIT/NO_ACTION.
"""
from datetime import datetime

from decision_engine.direction import DirectionLabel, classify_direction
from market_intelligence.models import CandidateScore


def _candidate(
    *, trend=1.0, momentum=0.3, breakout=0.0, relative_strength=None, sector_strength=None, composite=None,
) -> CandidateScore:
    resolved_composite = composite if composite is not None else trend + momentum + breakout + (relative_strength or 0.0) + (sector_strength or 0.0)
    return CandidateScore(
        symbol="RELIANCE.NS", as_of=datetime(2024, 1, 1), last_close=2500.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.1, trend_score=trend, momentum_score=momentum, breakout_score=breakout,
        relative_strength_score=relative_strength, sector_strength_score=sector_strength,
        composite_score=resolved_composite, explanation=["irrelevant for this test"],
    )


def test_classify_direction_none_candidate_is_no_edge_with_no_fabricated_evidence():
    result = classify_direction(None)
    assert result.label == DirectionLabel.NO_EDGE
    assert result.confidence == 0.0
    assert result.bullish_evidence == ()
    assert result.bearish_evidence == ()
    assert result.unavailable_factors == ()


def test_classify_direction_up_when_composite_positive():
    candidate = _candidate(trend=1.0, momentum=0.3, breakout=0.02, relative_strength=0.05, sector_strength=None)
    result = classify_direction(candidate)
    assert result.label == DirectionLabel.UP
    assert result.confidence > 0.0
    assert any("Trend" in line for line in result.bullish_evidence)
    assert result.contradicting_evidence == result.bearish_evidence


def test_classify_direction_down_when_composite_negative():
    candidate = _candidate(trend=-1.0, momentum=-0.4, breakout=-0.01, relative_strength=-0.02, sector_strength=None)
    result = classify_direction(candidate)
    assert result.label == DirectionLabel.DOWN
    assert any("Trend" in line for line in result.bearish_evidence)
    assert result.contradicting_evidence == result.bullish_evidence


def test_classify_direction_no_edge_when_composite_exactly_flat():
    candidate = _candidate(trend=1.0, momentum=-1.0, breakout=0.0, relative_strength=None, sector_strength=None, composite=0.0)
    result = classify_direction(candidate)
    assert result.label == DirectionLabel.NO_EDGE
    assert result.confidence == 0.0
    assert result.contradicting_evidence == ()


def test_classify_direction_contradictions_are_visible_even_when_labeled_up():
    """A DOWN-pointing factor on an otherwise-UP symbol must show up as a
    genuine contradiction, not be hidden -- this is the whole point of
    tracking contradicting_evidence separately."""
    candidate = _candidate(trend=1.0, momentum=1.0, breakout=1.0, relative_strength=-0.5, sector_strength=None)
    result = classify_direction(candidate)
    assert result.label == DirectionLabel.UP
    assert any("Relative strength" in line for line in result.bearish_evidence)
    assert any("Relative strength" in line for line in result.contradicting_evidence)


def test_classify_direction_unavailable_factors_never_treated_as_evidence():
    candidate = _candidate(trend=1.0, momentum=0.3, breakout=0.0, relative_strength=None, sector_strength=None)
    result = classify_direction(candidate)
    assert "relative_strength_score" in result.unavailable_factors
    assert "sector_strength_score" in result.unavailable_factors
    assert not any("Relative strength" in line for line in result.bullish_evidence + result.bearish_evidence)


def test_to_lines_never_crashes_and_mentions_label_and_confidence():
    candidate = _candidate()
    result = classify_direction(candidate)
    lines = result.to_lines()
    assert any("UP" in line for line in lines)
    assert any("Confidence" in line for line in lines)
