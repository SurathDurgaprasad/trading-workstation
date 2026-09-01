import math
from datetime import datetime

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


def test_normal_position_sizing_matches_the_documented_formula():
    # risk_per_trade=1%, equity=100,000 -> risk_budget=1,000; risk_per_unit=100-95=5 -> quantity=200
    engine = RiskEngine(RiskConfig(risk_per_trade_pct=1.0))
    account = new_account(100_000.0)

    decision = engine.evaluate(_signal(reference_price=100.0, stop_price=95.0), account)

    assert decision.approved
    assert decision.position_size.quantity == 200
    assert math.isclose(decision.position_size.risk_per_unit, 5.0)
    assert math.isclose(decision.position_size.total_risk, 1_000.0)
    assert math.isclose(decision.position_size.notional_value, 200 * 100.0)


def test_fractional_risk_budget_floors_down_not_rounds():
    # risk_budget = 100,000 * 0.5% = 500; risk_per_unit = 7 -> 500/7 = 71.43 -> floor to 71
    engine = RiskEngine(RiskConfig(risk_per_trade_pct=0.5))
    account = new_account(100_000.0)

    decision = engine.evaluate(_signal(reference_price=100.0, stop_price=93.0), account)

    assert decision.approved
    assert decision.position_size.quantity == 71


def test_zero_quantity_when_risk_budget_smaller_than_one_units_risk():
    # A tiny account: risk_budget = 10 * 0.5% = 0.05; risk_per_unit = 5 -> quantity 0 -> ZERO_POSITION_SIZE
    engine = RiskEngine(RiskConfig(risk_per_trade_pct=0.5))
    account = new_account(10.0)

    decision = engine.evaluate(_signal(reference_price=100.0, stop_price=95.0), account)

    assert not decision.approved
    assert VetoReason.ZERO_POSITION_SIZE in decision.veto_reasons


def test_very_tight_stop_produces_a_large_quantity_still_capital_bounded():
    # risk_per_unit = 0.01 -> nominal quantity huge, capped by capital (100,000
    # cash / 100 price = 1000 units). Exposure is opened up here specifically
    # to isolate capital-bounding from the separate exposure gate (which has
    # its own dedicated tests in test_risk_gates.py).
    engine = RiskEngine(RiskConfig(risk_per_trade_pct=0.5, max_exposure_pct=100.0))
    account = new_account(100_000.0)

    decision = engine.evaluate(_signal(reference_price=100.0, stop_price=99.99), account)

    assert decision.approved
    assert decision.position_size.quantity <= 1000


def test_very_wide_stop_produces_a_small_quantity():
    engine = RiskEngine(RiskConfig(risk_per_trade_pct=0.5))
    account = new_account(100_000.0)

    decision = engine.evaluate(_signal(reference_price=100.0, stop_price=20.0), account)  # risk_per_unit = 80

    assert decision.approved
    # risk_budget = 500 -> 500/80 = 6.25 -> 6
    assert decision.position_size.quantity == 6


def test_invalid_stop_at_or_above_entry_is_rejected():
    engine = RiskEngine(RiskConfig())
    account = new_account(100_000.0)

    decision = engine.evaluate(_signal(reference_price=100.0, stop_price=100.0), account)
    assert not decision.approved
    assert VetoReason.INVALID_STOP in decision.veto_reasons

    decision2 = engine.evaluate(_signal(reference_price=100.0, stop_price=105.0), account)
    assert not decision2.approved
    assert VetoReason.INVALID_STOP in decision2.veto_reasons


@pytest.mark.parametrize("risk_pct", [0.1, 0.5, 1.0, 2.0])
def test_normal_risk_percentages_all_produce_a_positive_quantity(risk_pct):
    # Checks sizing math in isolation (position_size is always populated once
    # computable, even when a *different* gate like exposure separately
    # rejects the trade — that interaction has its own tests elsewhere).
    engine = RiskEngine(RiskConfig(risk_per_trade_pct=risk_pct))
    account = new_account(100_000.0)

    decision = engine.evaluate(_signal(), account)
    assert decision.position_size is not None
    assert decision.position_size.quantity >= 1


def test_zero_or_negative_risk_percent_is_rejected_by_config_validation():
    with pytest.raises(Exception):
        RiskConfig(risk_per_trade_pct=0.0)
    with pytest.raises(Exception):
        RiskConfig(risk_per_trade_pct=-1.0)


def test_excessive_risk_percentage_is_still_computed_but_then_vetoed_on_exposure():
    engine = RiskEngine(RiskConfig(risk_per_trade_pct=50.0))  # deliberately extreme
    account = new_account(100_000.0)

    decision = engine.evaluate(_signal(reference_price=100.0, stop_price=95.0), account)

    # risk_budget = 50,000; risk_per_unit=5 -> nominal 10,000 units * 100 = 1,000,000 notional > cash
    # capital-bound: 100,000 cash / 100 price = 1000 units; that notional (100,000) is 100% of
    # equity, over the 25% default exposure cap -> rejected, but the sizing math is still reported.
    assert decision.position_size.quantity == 1000
    assert VetoReason.MAX_EXPOSURE in decision.veto_reasons
    assert not decision.approved
