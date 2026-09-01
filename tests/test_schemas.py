import pytest
from pydantic import ValidationError

from schemas.critic import CriticAssessment
from schemas.debate import DebateSummary
from schemas.decision import TradingDecision
from schemas.enums import TradingAction
from schemas.risk import RiskAssessment
from schemas.technical import TechnicalAnalysis


def test_valid_technical_analysis():
    model = TechnicalAnalysis(
        trend="up",
        support_resistance="support 100 / resistance 120",
        vwap="above vwap",
        entry_quality="good",
        exit_quality="n/a",
    )
    assert model.trend == "up"


def test_technical_analysis_requires_all_fields():
    with pytest.raises(ValidationError):
        TechnicalAnalysis(trend="up")  # missing required fields


def test_valid_risk_assessment():
    model = RiskAssessment(
        position_sizing="unquantified",
        risk_reward="1:2",
        stop_loss="below swing low",
        capital_protection="reduce size in high ATR",
    )
    assert model.risk_reward == "1:2"


def test_valid_critic_assessment_with_list_fields():
    model = CriticAssessment(
        weak_assumptions=["a"],
        hidden_risks=["b"],
        failure_scenarios=["c"],
        missing_rules=["d"],
    )
    assert model.weak_assumptions == ["a"]


def test_critic_assessment_rejects_non_list_for_list_field():
    with pytest.raises(ValidationError):
        CriticAssessment(
            weak_assumptions="not a list",
            hidden_risks=["b"],
            failure_scenarios=["c"],
            missing_rules=["d"],
        )


def test_valid_debate_summary():
    model = DebateSummary(agreements="a", disagreements="b", consensus="c")
    assert model.consensus == "c"


def test_trading_action_enum_values():
    assert TradingAction.BUY == "BUY"
    assert TradingAction.WAIT.value == "WAIT"
    assert {a.value for a in TradingAction} == {
        "STRONG_BUY",
        "BUY",
        "WAIT",
        "SELL",
        "STRONG_SELL",
    }


def test_valid_trading_decision():
    model = TradingDecision(
        decision=TradingAction.BUY,
        confidence=80,
        entry_strategy="on breakout",
        stop_loss="below entry",
        reasoning="strong trend",
        risks="reversal",
    )
    assert model.decision is TradingAction.BUY


def test_trading_decision_rejects_invalid_action_string():
    with pytest.raises(ValidationError):
        TradingDecision(
            decision="MAYBE",  # not a member of TradingAction
            confidence=80,
            entry_strategy="on breakout",
            stop_loss="below entry",
            reasoning="strong trend",
            risks="reversal",
        )


@pytest.mark.parametrize("confidence", [-1, 101])
def test_trading_decision_rejects_out_of_range_confidence(confidence):
    with pytest.raises(ValidationError):
        TradingDecision(
            decision=TradingAction.WAIT,
            confidence=confidence,
            entry_strategy="x",
            stop_loss="x",
            reasoning="x",
            risks="x",
        )
