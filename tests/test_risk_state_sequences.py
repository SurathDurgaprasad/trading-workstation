"""Phase 4.5 §10/§11/§12: exact, hand-verified state sequences — not just
threshold-crossing tests, but the literal numeric paths the spec asked for."""

import math
from datetime import datetime

from risk.account import new_account
from risk.config import RiskConfig
from risk.engine import RiskEngine
from risk.veto import VetoReason
from strategy.signal import ReasonCode, Side, Signal


def _signal(**overrides) -> Signal:
    base = dict(
        symbol="TEST", generated_at=datetime(2026, 1, 1), side=Side.LONG,
        reference_price=100.0, stop_price=95.0, target_price=110.0,
        risk_reward=2.0, strategy_name="unit-test", reason_codes=[ReasonCode.TREND_CONFIRMED],
    )
    base.update(overrides)
    return Signal(**base)


def test_exact_drawdown_sequence_100k_105k_102k_98k():
    account = new_account(100_000.0)
    account.mark_to_market(0.0)
    assert account.equity == 100_000.0 and account.peak_equity == 100_000.0

    account.open_position(quantity=1000, entry_price=100.0, entry_cost=0.0)
    account.close_position(exit_price=105.0, exit_cost=0.0, net_pnl=5_000.0)  # -> 105,000
    assert math.isclose(account.equity, 105_000.0)
    assert math.isclose(account.peak_equity, 105_000.0)
    assert math.isclose(account.current_drawdown_pct, 0.0)

    account.open_position(quantity=1000, entry_price=100.0, entry_cost=0.0)
    account.close_position(exit_price=97.0, exit_cost=0.0, net_pnl=-3_000.0)  # -> 102,000
    assert math.isclose(account.equity, 102_000.0)
    assert math.isclose(account.peak_equity, 105_000.0)  # unchanged -- peak never decreases
    assert math.isclose(account.current_drawdown_pct, (105_000.0 - 102_000.0) / 105_000.0 * 100)

    account.open_position(quantity=1000, entry_price=100.0, entry_cost=0.0)
    account.close_position(exit_price=96.0, exit_cost=0.0, net_pnl=-4_000.0)  # 1000*(96-100) = -4,000 -> 98,000
    assert math.isclose(account.equity, 98_000.0)
    assert math.isclose(account.peak_equity, 105_000.0)
    assert math.isclose(account.current_drawdown_pct, (105_000.0 - 98_000.0) / 105_000.0 * 100)
    assert account.current_drawdown_pct > 0

    # Now the veto: a 6.67% drawdown must reject at a 5% configured limit...
    engine_strict = RiskEngine(RiskConfig(max_drawdown_pct=5.0))
    assert VetoReason.MAX_DRAWDOWN in engine_strict.evaluate(_signal(), account).veto_reasons
    # ...but pass at a 10% configured limit.
    engine_loose = RiskEngine(RiskConfig(max_drawdown_pct=10.0))
    assert VetoReason.MAX_DRAWDOWN not in engine_loose.evaluate(_signal(), account).veto_reasons


def test_drawdown_recovery_requires_genuine_equity_recovery_not_a_new_signal():
    # Per the blueprint (§6.3, "Critical... Human intervention required"),
    # there is deliberately NO automatic recovery from a drawdown halt —
    # only the account's own equity climbing back out of the hole clears it.
    engine = RiskEngine(RiskConfig(max_drawdown_pct=10.0))
    account = new_account(100_000.0)
    account.open_position(quantity=1000, entry_price=100.0, entry_cost=0.0)
    account.close_position(exit_price=85.0, exit_cost=0.0, net_pnl=-15_000.0)  # 15% dd -> halted
    assert VetoReason.MAX_DRAWDOWN in engine.evaluate(_signal(), account).veto_reasons

    # A winning trade that only partially recovers equity: still halted.
    account.open_position(quantity=1000, entry_price=85.0, entry_cost=0.0)
    account.close_position(exit_price=90.0, exit_cost=0.0, net_pnl=5_000.0)  # -> 90,000, dd = 10,000/105... wait peak is 100,000
    # peak is still 100,000 (never exceeded); equity now 90,000 -> dd = 10% exactly
    assert math.isclose(account.current_drawdown_pct, 10.0)
    assert VetoReason.MAX_DRAWDOWN in engine.evaluate(_signal(), account).veto_reasons  # >= 10 still vetoes

    # A further win that brings drawdown strictly under the limit: clears, on its own.
    account.open_position(quantity=1000, entry_price=90.0, entry_cost=0.0)
    account.close_position(exit_price=95.0, exit_cost=0.0, net_pnl=5_000.0)  # -> 95,000, dd = 5%
    assert math.isclose(account.current_drawdown_pct, 5.0)
    assert VetoReason.MAX_DRAWDOWN not in engine.evaluate(_signal(), account).veto_reasons


def test_exact_sequence_win_loss_loss_loss():
    account = new_account(100_000.0)

    account.open_position(quantity=100, entry_price=100.0, entry_cost=0.0)
    account.close_position(exit_price=105.0, exit_cost=0.0, net_pnl=500.0)  # WIN
    assert account.consecutive_losses == 0

    for _ in range(3):  # LOSS, LOSS, LOSS
        account.open_position(quantity=100, entry_price=100.0, entry_cost=0.0)
        account.close_position(exit_price=95.0, exit_cost=0.0, net_pnl=-500.0)
    assert account.consecutive_losses == 3

    engine = RiskEngine(RiskConfig(max_consecutive_losses=3, consecutive_loss_hard_limit=5))
    decision = engine.evaluate(_signal(), account)
    assert decision.approved  # soft limit -> reduced size, not rejected
    assert decision.risk_reduced is True


def test_reset_policy_is_explicit_any_single_win_clears_the_streak_immediately():
    """The reset rule is defined precisely (spec §11's explicit-not-assumed
    requirement): consecutive_losses resets to exactly 0 on any trade with
    net_pnl > 0, regardless of streak length beforehand, and regardless of
    how small the win is."""
    account = new_account(100_000.0)
    for _ in range(5):
        account.open_position(quantity=100, entry_price=100.0, entry_cost=0.0)
        account.close_position(exit_price=95.0, exit_cost=0.0, net_pnl=-500.0)
    assert account.consecutive_losses == 5

    account.open_position(quantity=100, entry_price=100.0, entry_cost=0.0)
    account.close_position(exit_price=100.01, exit_cost=0.0, net_pnl=1.0)  # a trivially small win
    assert account.consecutive_losses == 0


def test_three_way_simultaneous_veto_drawdown_exposure_and_consecutive_loss_hard_limit():
    engine = RiskEngine(
        RiskConfig(
            max_daily_loss_pct=100.0,  # disabled -- isolate exactly the 3 reasons under test
            max_drawdown_pct=10.0,
            max_exposure_pct=1.0,  # unattainable for any normal sizing
            max_consecutive_losses=2,
            consecutive_loss_hard_limit=2,  # immediate hard reject, matching this test's intent
            risk_per_trade_pct=5.0,  # deliberately large so exposure is easy to breach
        )
    )
    account = new_account(100_000.0)
    for _ in range(2):
        account.open_position(quantity=1000, entry_price=100.0, entry_cost=0.0)
        account.close_position(exit_price=80.0, exit_cost=0.0, net_pnl=-20_000.0)  # -> 20% drawdown, 2 losses

    decision = engine.evaluate(_signal(), account)

    assert not decision.approved
    assert VetoReason.MAX_DRAWDOWN in decision.veto_reasons
    assert VetoReason.CONSECUTIVE_LOSS_LIMIT in decision.veto_reasons
    assert VetoReason.MAX_EXPOSURE in decision.veto_reasons
    assert len(decision.veto_reasons) == 3
