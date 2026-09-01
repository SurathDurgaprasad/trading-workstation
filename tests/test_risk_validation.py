from datetime import datetime

from risk.account import new_account
from risk.config import RiskConfig
from risk.engine import RiskEngine
from risk.veto import VetoReason
from strategy.signal import ReasonCode, Side, Signal


def _signal(**overrides) -> Signal:
    base = dict(
        symbol="TEST",
        generated_at=datetime(2026, 1, 1),
        side=Side.LONG,
        reference_price=100.0,
        stop_price=95.0,
        target_price=110.0,
        risk_reward=2.0,
        strategy_name="unit-test",
        reason_codes=[ReasonCode.TREND_CONFIRMED],
    )
    base.update(overrides)
    return Signal(**base)


def test_short_side_is_rejected_not_yet_supported():
    engine = RiskEngine(RiskConfig())
    account = new_account(100_000.0)

    decision = engine.evaluate(_signal(side=Side.SHORT), account)

    assert not decision.approved
    assert VetoReason.INVALID_SIGNAL in decision.veto_reasons


def test_target_at_or_below_entry_is_rejected():
    engine = RiskEngine(RiskConfig())
    account = new_account(100_000.0)

    decision = engine.evaluate(_signal(target_price=100.0), account)
    assert not decision.approved
    assert VetoReason.INVALID_SIGNAL in decision.veto_reasons

    decision2 = engine.evaluate(_signal(target_price=90.0), account)
    assert not decision2.approved
    assert VetoReason.INVALID_SIGNAL in decision2.veto_reasons


def test_a_fully_valid_signal_is_not_flagged_invalid():
    engine = RiskEngine(RiskConfig())
    account = new_account(100_000.0)

    decision = engine.evaluate(_signal(), account)
    assert VetoReason.INVALID_SIGNAL not in decision.veto_reasons
    assert VetoReason.INVALID_STOP not in decision.veto_reasons


def test_structurally_invalid_signal_never_produces_a_position_size():
    # A signal whose stop math is nonsensical must fail closed with no
    # sizing at all, not a garbage/negative quantity.
    engine = RiskEngine(RiskConfig())
    account = new_account(100_000.0)

    decision = engine.evaluate(_signal(stop_price=105.0), account)  # stop above entry
    assert decision.position_size is None
    assert decision.risk_amount is None
    assert not decision.approved
