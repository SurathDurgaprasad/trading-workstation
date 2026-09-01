"""Spec §13/§14: every RiskDecision carries a full account-state snapshot
and requested-vs-approved quantity, so a rejected signal is never a dead
end for "why didn't this trade happen?"."""

import math
from datetime import datetime

from risk.account import new_account
from risk.config import RiskConfig
from risk.engine import RiskEngine
from strategy.signal import ReasonCode, Side, Signal


def _signal(**overrides) -> Signal:
    base = dict(
        symbol="TEST", generated_at=datetime(2026, 1, 1), side=Side.LONG,
        reference_price=100.0, stop_price=95.0, target_price=110.0,
        risk_reward=2.0, strategy_name="unit-test", reason_codes=[ReasonCode.TREND_CONFIRMED],
    )
    base.update(overrides)
    return Signal(**base)


def test_audit_trail_snapshot_matches_account_state_at_decision_time():
    engine = RiskEngine(RiskConfig(risk_per_trade_pct=1.0))
    account = new_account(100_000.0)
    account.open_position(quantity=100, entry_price=100.0, entry_cost=0.0)
    account.close_position(exit_price=95.0, exit_cost=0.0, net_pnl=-500.0)

    decision = engine.evaluate(_signal(), account)

    assert math.isclose(decision.account_equity, account.equity)
    assert math.isclose(decision.current_drawdown_pct, account.current_drawdown_pct)
    assert math.isclose(decision.daily_pnl, account.daily_pnl)
    assert decision.consecutive_losses == account.consecutive_losses == 1


def test_requested_quantity_exceeds_approved_quantity_when_capital_reduces_sizing():
    engine = RiskEngine(RiskConfig(risk_per_trade_pct=50.0, max_exposure_pct=100.0))
    account = new_account(200.0)  # tiny account, forces a capital-driven reduction

    decision = engine.evaluate(_signal(reference_price=100.0, stop_price=95.0), account)

    assert decision.requested_quantity > decision.approved_quantity


def test_requested_and_approved_quantity_match_on_a_clean_approval():
    engine = RiskEngine(RiskConfig(risk_per_trade_pct=0.5))
    account = new_account(100_000.0)

    decision = engine.evaluate(_signal(reference_price=100.0, stop_price=95.0), account)

    assert decision.approved
    assert decision.requested_quantity == decision.approved_quantity == decision.position_size.quantity


def test_approved_quantity_is_zero_on_any_rejection():
    engine = RiskEngine(RiskConfig(min_risk_reward=5.0))
    account = new_account(100_000.0)

    decision = engine.evaluate(_signal(risk_reward=2.0), account)

    assert not decision.approved
    assert decision.approved_quantity == 0
