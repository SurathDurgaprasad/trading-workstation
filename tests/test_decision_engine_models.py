from datetime import datetime, timezone

import pytest

from decision_engine.config import DecisionConfig
from decision_engine.models import Decision, DecisionLabel, RiskContext
from market_intelligence.models import CandidateScore


def _candidate() -> CandidateScore:
    return CandidateScore(
        symbol="AAPL", as_of=datetime(2024, 6, 1), last_close=190.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.1, trend_score=1.0, momentum_score=0.5, breakout_score=0.01,
        relative_strength_score=0.02, sector_strength_score=None, composite_score=1.5,
        explanation=["fake"],
    )


def _decision_kwargs(**overrides):
    base = dict(
        decision_id="dec-1", symbol="AAPL", as_of=datetime.now(timezone.utc), label=DecisionLabel.NO_ACTION,
        rationale=["no evidence"], config_version="abc", scanner_evidence=None, research_evidence=None,
        market_context=None, risk_context=RiskContext.unknown(), narrative=None, narrative_unavailable_reason=None,
    )
    base.update(overrides)
    return base


def test_no_action_is_allowed_without_scanner_evidence():
    decision = Decision(**_decision_kwargs())
    assert decision.label == DecisionLabel.NO_ACTION
    assert decision.scanner_evidence is None


@pytest.mark.parametrize("label", [DecisionLabel.BUY, DecisionLabel.WATCH, DecisionLabel.AVOID, DecisionLabel.EXIT])
def test_a_real_recommendation_requires_scanner_evidence(label):
    with pytest.raises(ValueError):
        Decision(**_decision_kwargs(label=label, scanner_evidence=None))


@pytest.mark.parametrize("label", [DecisionLabel.BUY, DecisionLabel.WATCH, DecisionLabel.AVOID, DecisionLabel.EXIT])
def test_a_real_recommendation_is_allowed_with_scanner_evidence(label):
    decision = Decision(**_decision_kwargs(label=label, scanner_evidence=_candidate()))
    assert decision.label == label
    assert decision.scanner_evidence is not None


def test_risk_context_unknown_states_its_own_limitation():
    context = RiskContext.unknown()
    assert context.has_open_position is False
    assert context.consecutive_losses == 0
    assert context.note is not None


def test_decision_config_version_id_is_deterministic_and_change_sensitive():
    a = DecisionConfig()
    b = DecisionConfig()
    c = DecisionConfig(require_corroboration_for_buy=False)

    assert a.version_id() == b.version_id()
    assert a.version_id() != c.version_id()
