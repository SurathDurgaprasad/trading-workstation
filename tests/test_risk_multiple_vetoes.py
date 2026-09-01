from datetime import datetime

from risk.account import new_account
from risk.config import RiskConfig
from risk.engine import RiskEngine
from risk.veto import VetoReason
from strategy.signal import ReasonCode, Side, Signal


def test_a_signal_can_carry_multiple_simultaneous_veto_reasons():
    """Spec §25: verify the result contains ALL applicable veto reasons, not
    just the first one encountered."""
    # consecutive_loss_hard_limit=2 (== the soft limit) opts into an immediate
    # reject at 2 losses, matching this test's original intent post Phase 4.5
    # (which otherwise turns 2 losses into reduced-risk sizing, not a reject).
    engine = RiskEngine(
        RiskConfig(
            max_drawdown_pct=10.0,
            max_consecutive_losses=2,
            consecutive_loss_hard_limit=2,
            min_risk_reward=1.5,
        )
    )
    account = new_account(100_000.0)

    # Drive the account into both a drawdown breach AND a consecutive-loss breach.
    # 300 * (80-100) = -6,000 per trade -> -12,000 total -> 12% drawdown, over the 10% limit.
    for _ in range(2):
        account.open_position(quantity=300, entry_price=100.0, entry_cost=0.0)
        account.close_position(exit_price=80.0, exit_cost=0.0, net_pnl=-6_000.0)

    # A signal that ALSO fails the R:R rule.
    signal = Signal(
        symbol="TEST",
        generated_at=datetime(2026, 1, 1),
        side=Side.LONG,
        reference_price=100.0,
        stop_price=95.0,
        target_price=100.01,  # tiny, R:R far below minimum
        risk_reward=0.1,
        strategy_name="unit-test",
        reason_codes=[ReasonCode.TREND_CONFIRMED],
    )

    decision = engine.evaluate(signal, account)

    assert not decision.approved
    assert VetoReason.MAX_DRAWDOWN in decision.veto_reasons
    assert VetoReason.CONSECUTIVE_LOSS_LIMIT in decision.veto_reasons
    assert VetoReason.INVALID_RISK_REWARD in decision.veto_reasons
    assert len(decision.veto_reasons) >= 3


def test_structural_and_account_state_vetoes_can_co_occur():
    engine = RiskEngine(RiskConfig(max_daily_loss_pct=3.0))
    account = new_account(100_000.0)
    account.open_position(quantity=1000, entry_price=100.0, entry_cost=0.0)
    account.close_position(exit_price=95.0, exit_cost=0.0, net_pnl=-5_000.0)  # 1000*(95-100) = -5,000, breaches daily loss

    invalid_signal = Signal(
        symbol="TEST",
        generated_at=datetime(2026, 1, 1),
        side=Side.LONG,
        reference_price=100.0,
        stop_price=105.0,  # invalid: stop above entry
        target_price=110.0,
        risk_reward=2.0,
        strategy_name="unit-test",
        reason_codes=[ReasonCode.TREND_CONFIRMED],
    )

    decision = engine.evaluate(invalid_signal, account)

    assert not decision.approved
    assert VetoReason.INVALID_STOP in decision.veto_reasons
    assert VetoReason.MAX_DAILY_LOSS in decision.veto_reasons
