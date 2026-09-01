"""Spec §17: edge-case failure modes not already covered elsewhere — a
zero or negative-equity account must never approve a trade."""

from datetime import date, datetime

from risk.account import Account
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


def _zero_equity_account() -> Account:
    return Account(initial_capital=100.0, cash=0.0, peak_equity=100.0, daily_start_equity=100.0)


def test_zero_cash_account_fails_closed_not_approved():
    engine = RiskEngine(RiskConfig())
    account = _zero_equity_account()

    decision = engine.evaluate(_signal(), account)

    assert not decision.approved
    assert decision.approved_quantity == 0


def test_zero_equity_exposure_calc_does_not_crash_with_a_zero_division():
    # account.equity == cash + open_position_notional == 0 here (both zero).
    engine = RiskEngine(RiskConfig())
    account = Account(initial_capital=0.0 + 1, cash=0.0, peak_equity=0.01, daily_start_equity=0.01)

    decision = engine.evaluate(_signal(), account)  # must not raise ZeroDivisionError

    assert not decision.approved


def test_daily_start_equity_of_zero_fails_closed_on_daily_loss_check():
    engine = RiskEngine(RiskConfig(max_daily_loss_pct=3.0))
    account = Account(initial_capital=1.0, cash=1.0, peak_equity=1.0, daily_start_equity=0.0)

    decision = engine.evaluate(_signal(), account)

    # daily_start_equity <= 0 means no safe reference point -> fail closed (risk/engine.py::_daily_loss_breached)
    from risk.veto import VetoReason
    assert VetoReason.MAX_DAILY_LOSS in decision.veto_reasons
    assert not decision.approved


def test_position_already_open_is_independently_enforced_even_if_other_checks_would_pass():
    engine = RiskEngine(RiskConfig())
    account = Account(initial_capital=100_000.0, cash=90_000.0, peak_equity=100_000.0, daily_start_equity=100_000.0)
    account.open_position_quantity = 10  # simulate an already-open position directly

    decision = engine.evaluate(_signal(), account)

    from risk.veto import VetoReason
    assert not decision.approved
    assert VetoReason.POSITION_ALREADY_OPEN in decision.veto_reasons


def test_roll_to_day_with_none_current_day_initializes_cleanly():
    account = Account(initial_capital=1_000.0, cash=1_000.0, peak_equity=1_000.0, daily_start_equity=1_000.0)
    assert account.current_day is None
    account.roll_to_day(date(2026, 1, 1))
    assert account.current_day == date(2026, 1, 1)
