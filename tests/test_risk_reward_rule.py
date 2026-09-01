from datetime import datetime

from risk.account import new_account
from risk.config import RiskConfig
from risk.engine import RiskEngine
from risk.veto import VetoReason
from strategy.signal import ReasonCode, Side, Signal


def _signal(risk_reward: float, **overrides) -> Signal:
    base = dict(
        symbol="TEST",
        generated_at=datetime(2026, 1, 1),
        side=Side.LONG,
        reference_price=100.0,
        stop_price=95.0,
        target_price=110.0,
        risk_reward=risk_reward,
        strategy_name="unit-test",
        reason_codes=[ReasonCode.TREND_CONFIRMED],
    )
    base.update(overrides)
    return Signal(**base)


def test_risk_reward_at_or_above_minimum_is_approved():
    engine = RiskEngine(RiskConfig(min_risk_reward=1.5))
    account = new_account(100_000.0)

    decision_at = engine.evaluate(_signal(1.5), account)
    assert VetoReason.INVALID_RISK_REWARD not in decision_at.veto_reasons

    decision_above = engine.evaluate(_signal(2.0), account)
    assert VetoReason.INVALID_RISK_REWARD not in decision_above.veto_reasons
    assert decision_above.approved


def test_risk_reward_below_minimum_is_rejected():
    engine = RiskEngine(RiskConfig(min_risk_reward=1.5))
    account = new_account(100_000.0)

    decision = engine.evaluate(_signal(1.49), account)
    assert not decision.approved
    assert VetoReason.INVALID_RISK_REWARD in decision.veto_reasons


def test_zero_risk_reward_is_rejected():
    # Signal itself validates risk_reward > 0 at construction (see
    # strategy/signal.py's Field(gt=0)) -- 0.0 cannot reach the engine as a
    # Signal at all, which is itself a fail-closed guarantee one layer up.
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _signal(0.0)


def test_negative_risk_reward_is_rejected():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _signal(-1.0)
