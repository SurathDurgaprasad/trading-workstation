from datetime import date, datetime

import pytest

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


# --- Max daily loss --------------------------------------------------------


def test_daily_loss_below_limit_is_approved():
    engine = RiskEngine(RiskConfig(max_daily_loss_pct=3.0))
    account = new_account(100_000.0)
    account.roll_to_day(date(2026, 1, 1))
    account.open_position(quantity=1000, entry_price=100.0, entry_cost=0.0)
    account.close_position(exit_price=98.0, exit_cost=0.0, net_pnl=-2_000.0)  # 1000*(98-100) = -2,000 = 2%
    account.roll_to_day(date(2026, 1, 1))

    decision = engine.evaluate(_signal(), account)
    assert VetoReason.MAX_DAILY_LOSS not in decision.veto_reasons


def test_daily_loss_at_limit_is_rejected():
    engine = RiskEngine(RiskConfig(max_daily_loss_pct=3.0))
    account = new_account(100_000.0)
    account.roll_to_day(date(2026, 1, 1))
    account.open_position(quantity=1000, entry_price=100.0, entry_cost=0.0)
    account.close_position(exit_price=97.0, exit_cost=0.0, net_pnl=-3_000.0)  # 1000*(97-100) = -3,000 = exactly 3%
    account.roll_to_day(date(2026, 1, 1))

    decision = engine.evaluate(_signal(), account)
    assert not decision.approved
    assert VetoReason.MAX_DAILY_LOSS in decision.veto_reasons


def test_daily_loss_above_limit_is_rejected():
    engine = RiskEngine(RiskConfig(max_daily_loss_pct=3.0))
    account = new_account(100_000.0)
    account.roll_to_day(date(2026, 1, 1))
    account.open_position(quantity=1000, entry_price=100.0, entry_cost=0.0)
    account.close_position(exit_price=95.0, exit_cost=0.0, net_pnl=-5_000.0)  # 1000*(95-100) = -5,000 = 5%
    account.roll_to_day(date(2026, 1, 1))

    decision = engine.evaluate(_signal(), account)
    assert not decision.approved
    assert VetoReason.MAX_DAILY_LOSS in decision.veto_reasons


def test_daily_loss_resets_on_a_new_day():
    engine = RiskEngine(RiskConfig(max_daily_loss_pct=3.0))
    account = new_account(100_000.0)
    account.roll_to_day(date(2026, 1, 1))
    account.open_position(quantity=1000, entry_price=100.0, entry_cost=0.0)
    account.close_position(exit_price=95.0, exit_cost=0.0, net_pnl=-5_000.0)  # breach day 1
    account.roll_to_day(date(2026, 1, 1))
    assert VetoReason.MAX_DAILY_LOSS in engine.evaluate(_signal(), account).veto_reasons

    account.roll_to_day(date(2026, 1, 2))  # new trading day
    decision = engine.evaluate(_signal(), account)
    assert VetoReason.MAX_DAILY_LOSS not in decision.veto_reasons


# --- Max drawdown ------------------------------------------------------------


def test_drawdown_below_limit_is_approved():
    engine = RiskEngine(RiskConfig(max_drawdown_pct=10.0))
    account = new_account(100_000.0)
    account.mark_to_market(0.0)  # peak = 100,000
    account.open_position(quantity=1000, entry_price=100.0, entry_cost=0.0)
    account.close_position(exit_price=95.0, exit_cost=0.0, net_pnl=-5_000.0)  # 5% dd

    decision = engine.evaluate(_signal(), account)
    assert VetoReason.MAX_DRAWDOWN not in decision.veto_reasons


def test_drawdown_at_limit_is_rejected():
    engine = RiskEngine(RiskConfig(max_drawdown_pct=10.0))
    account = new_account(100_000.0)
    account.open_position(quantity=1000, entry_price=100.0, entry_cost=0.0)
    account.close_position(exit_price=90.0, exit_cost=0.0, net_pnl=-10_000.0)  # exactly 10% dd

    decision = engine.evaluate(_signal(), account)
    assert not decision.approved
    assert VetoReason.MAX_DRAWDOWN in decision.veto_reasons


def test_drawdown_above_limit_is_rejected():
    engine = RiskEngine(RiskConfig(max_drawdown_pct=10.0))
    account = new_account(100_000.0)
    account.open_position(quantity=1000, entry_price=100.0, entry_cost=0.0)
    account.close_position(exit_price=80.0, exit_cost=0.0, net_pnl=-20_000.0)  # 20% dd

    decision = engine.evaluate(_signal(), account)
    assert not decision.approved
    assert VetoReason.MAX_DRAWDOWN in decision.veto_reasons


def test_drawdown_breach_does_not_auto_recover_on_a_merely_attractive_signal():
    # Once HALTED by drawdown, the engine must not silently re-approve just
    # because a new signal looks fine -- there is no "recovery" logic here,
    # by design (spec §11): every future evaluation is rejected until the
    # account's own equity genuinely recovers.
    engine = RiskEngine(RiskConfig(max_drawdown_pct=10.0))
    account = new_account(100_000.0)
    account.open_position(quantity=1000, entry_price=100.0, entry_cost=0.0)
    account.close_position(exit_price=85.0, exit_cost=0.0, net_pnl=-15_000.0)

    for _ in range(3):
        decision = engine.evaluate(_signal(risk_reward=10.0), account)  # an "attractive" signal
        assert not decision.approved
        assert VetoReason.MAX_DRAWDOWN in decision.veto_reasons


# --- Consecutive losses -------------------------------------------------------


def test_consecutive_losses_below_threshold_is_approved():
    engine = RiskEngine(RiskConfig(max_consecutive_losses=3))
    account = new_account(100_000.0)
    for _ in range(2):
        account.open_position(quantity=1, entry_price=100.0, entry_cost=0.0)
        account.close_position(exit_price=95.0, exit_cost=0.0, net_pnl=-500.0)

    decision = engine.evaluate(_signal(), account)
    assert VetoReason.CONSECUTIVE_LOSS_LIMIT not in decision.veto_reasons


def test_consecutive_losses_at_soft_threshold_reduces_risk_instead_of_rejecting():
    # Phase 4.5: matches the blueprint's actual documented policy ("Position
    # size reduced by 50% for next 5 trades"), not an outright reject —
    # Phase 4's original hard-reject-forever behavior is what this replaces.
    engine = RiskEngine(RiskConfig(max_consecutive_losses=3, risk_per_trade_pct=1.0, consecutive_loss_risk_multiplier=0.5))

    # Same equity in both accounts -- isolate the multiplier's effect on
    # sizing from the (separately-tested) equity impact of realized losses.
    account_normal = new_account(100_000.0)
    account_streak = new_account(100_000.0)
    account_streak.consecutive_losses = 3

    normal = engine.evaluate(_signal(), account_normal)
    decision = engine.evaluate(_signal(), account_streak)

    assert decision.approved  # not rejected -- the account can still trade
    assert decision.risk_reduced is True
    assert VetoReason.CONSECUTIVE_LOSS_LIMIT not in decision.veto_reasons
    # half the risk budget -> exactly half the quantity of an equivalent non-streak decision
    assert decision.position_size.quantity == normal.position_size.quantity // 2


def test_consecutive_losses_at_hard_limit_is_rejected_outright():
    # The circuit breaker: losses continuing even through reduced-risk sizing.
    engine = RiskEngine(RiskConfig(max_consecutive_losses=3, consecutive_loss_hard_limit=5))
    account = new_account(100_000.0)
    for _ in range(5):
        account.open_position(quantity=1, entry_price=100.0, entry_cost=0.0)
        account.close_position(exit_price=95.0, exit_cost=0.0, net_pnl=-500.0)

    decision = engine.evaluate(_signal(), account)
    assert not decision.approved
    assert VetoReason.CONSECUTIVE_LOSS_LIMIT in decision.veto_reasons


def test_hard_limit_equal_to_soft_limit_reproduces_phase_4_immediate_reject():
    # An explicit opt-in to the old strict behavior, for anyone who wants it.
    engine = RiskEngine(RiskConfig(max_consecutive_losses=3, consecutive_loss_hard_limit=3))
    account = new_account(100_000.0)
    for _ in range(3):
        account.open_position(quantity=1, entry_price=100.0, entry_cost=0.0)
        account.close_position(exit_price=95.0, exit_cost=0.0, net_pnl=-500.0)

    decision = engine.evaluate(_signal(), account)
    assert not decision.approved
    assert VetoReason.CONSECUTIVE_LOSS_LIMIT in decision.veto_reasons


def test_hard_limit_below_soft_limit_is_rejected_by_config_validation():
    with pytest.raises(Exception):
        RiskConfig(max_consecutive_losses=5, consecutive_loss_hard_limit=3)


def test_a_win_during_recovery_immediately_restores_full_size():
    engine = RiskEngine(RiskConfig(max_consecutive_losses=3, risk_per_trade_pct=1.0))
    account = new_account(100_000.0)
    for _ in range(3):
        account.open_position(quantity=1, entry_price=100.0, entry_cost=0.0)
        account.close_position(exit_price=95.0, exit_cost=0.0, net_pnl=-500.0)
    assert engine.evaluate(_signal(), account).risk_reduced is True

    account.open_position(quantity=1, entry_price=100.0, entry_cost=0.0)
    account.close_position(exit_price=105.0, exit_cost=0.0, net_pnl=500.0)  # breaks the streak

    decision = engine.evaluate(_signal(), account)
    assert decision.risk_reduced is False
    assert decision.approved


def test_a_single_win_resets_the_streak_below_threshold():
    engine = RiskEngine(RiskConfig(max_consecutive_losses=3))
    account = new_account(100_000.0)
    for _ in range(2):
        account.open_position(quantity=1, entry_price=100.0, entry_cost=0.0)
        account.close_position(exit_price=95.0, exit_cost=0.0, net_pnl=-500.0)
    account.open_position(quantity=1, entry_price=100.0, entry_cost=0.0)
    account.close_position(exit_price=105.0, exit_cost=0.0, net_pnl=500.0)  # win

    decision = engine.evaluate(_signal(), account)
    assert VetoReason.CONSECUTIVE_LOSS_LIMIT not in decision.veto_reasons


def test_open_positions_are_never_counted_as_a_loss_before_closing():
    engine = RiskEngine(RiskConfig(max_consecutive_losses=1))
    account = new_account(100_000.0)
    account.open_position(quantity=1, entry_price=100.0, entry_cost=0.0)
    account.mark_to_market(50.0)  # a large unrealized loss -- still open, must not count yet
    assert account.consecutive_losses == 0


# --- Exposure -----------------------------------------------------------------


def test_exposure_within_limit_is_approved():
    engine = RiskEngine(RiskConfig(max_exposure_pct=25.0, risk_per_trade_pct=1.0))
    account = new_account(100_000.0)
    # risk_per_unit=5, budget=1000 -> qty=200 -> notional=20,000 -> 20% exposure, under 25%
    decision = engine.evaluate(_signal(reference_price=100.0, stop_price=95.0), account)
    assert decision.approved
    assert VetoReason.MAX_EXPOSURE not in decision.veto_reasons


def test_exposure_above_limit_is_rejected():
    engine = RiskEngine(RiskConfig(max_exposure_pct=10.0, risk_per_trade_pct=1.0))
    account = new_account(100_000.0)
    # same sizing as above -> 20% exposure, now over the 10% cap
    decision = engine.evaluate(_signal(reference_price=100.0, stop_price=95.0), account)
    assert not decision.approved
    assert VetoReason.MAX_EXPOSURE in decision.veto_reasons


def test_exposure_exactly_at_limit_is_approved_not_rejected():
    # The rejection condition is `exposure_pct > max`, so a position sized to
    # land exactly on the limit must be approved, not rejected.
    engine = RiskEngine(RiskConfig(max_exposure_pct=20.0, risk_per_trade_pct=1.0, max_daily_loss_pct=100.0))
    account = new_account(100_000.0)
    # risk_per_unit=5, budget=1,000 -> qty=200 -> notional=20,000 -> exactly 20% exposure
    decision = engine.evaluate(_signal(reference_price=100.0, stop_price=95.0), account)
    assert decision.approved
    assert VetoReason.MAX_EXPOSURE not in decision.veto_reasons


def test_exposure_far_above_limit_via_capital_bound_sizing_is_rejected():
    engine = RiskEngine(RiskConfig(max_exposure_pct=20.0, risk_per_trade_pct=100.0))  # force capital-bound sizing
    account = new_account(100_000.0)
    # capital-bound: cash 100,000 / price 100 = 1000 units -> notional 100,000 -> 100% exposure > 20% -> reject
    decision = engine.evaluate(_signal(reference_price=100.0, stop_price=95.0), account)
    assert not decision.approved
    assert VetoReason.MAX_EXPOSURE in decision.veto_reasons


# --- Capital --------------------------------------------------------------------


def test_capital_sufficient_is_approved():
    engine = RiskEngine(RiskConfig(risk_per_trade_pct=0.5))
    account = new_account(100_000.0)
    decision = engine.evaluate(_signal(reference_price=100.0, stop_price=95.0), account)
    assert decision.approved
    assert VetoReason.INSUFFICIENT_CAPITAL not in decision.veto_reasons


def test_insufficient_capital_reduces_quantity_and_can_veto_at_zero():
    engine = RiskEngine(RiskConfig(risk_per_trade_pct=50.0, max_exposure_pct=100.0))  # wide open exposure cap
    account = new_account(10.0)  # tiny account: can't even afford 1 unit at price 100

    decision = engine.evaluate(_signal(reference_price=100.0, stop_price=95.0), account)
    assert not decision.approved
    assert VetoReason.INSUFFICIENT_CAPITAL in decision.veto_reasons
