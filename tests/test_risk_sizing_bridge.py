from datetime import datetime

import pytest

from decision_engine.models import Decision, DecisionLabel, RiskContext
from market.context import MarketContext
from market_intelligence.models import CandidateScore
from risk.account import new_account
from risk.sizing import SizingUnavailableError, build_signal_for_buy, size_decision
from strategy.baseline import STOP_ATR_MULTIPLIER, TARGET_RISK_REWARD
from strategy.signal import ReasonCode, Side


def _candidate() -> CandidateScore:
    return CandidateScore(
        symbol="AAPL", as_of=datetime(2024, 6, 1), last_close=190.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.1, trend_score=1.0, momentum_score=0.5, breakout_score=0.01,
        relative_strength_score=0.02, sector_strength_score=None, composite_score=1.5,
        explanation=["fake"],
    )


def _decision(label: DecisionLabel = DecisionLabel.BUY, symbol: str = "AAPL") -> Decision:
    return Decision(
        decision_id="dec-1", symbol=symbol, as_of=datetime(2024, 6, 1, 12, 0, 0), label=label,
        rationale=["fake rationale"], config_version="cfg1",
        scanner_evidence=_candidate() if label != DecisionLabel.NO_ACTION else None,
        research_evidence=None, market_context=None, risk_context=RiskContext.unknown(),
        narrative=None, narrative_unavailable_reason=None,
    )


def _market_context(*, symbol: str = "AAPL", price: float = 200.0, atr_14: float | None = 5.0) -> MarketContext:
    return MarketContext(symbol=symbol, as_of=datetime(2024, 6, 1), price=price, atr_14=atr_14)


# --- build_signal_for_buy ----------------------------------------------------


def test_build_signal_for_buy_uses_the_exact_baseline_stop_target_formula():
    decision = _decision(DecisionLabel.BUY)
    market_context = _market_context(price=200.0, atr_14=5.0)

    signal = build_signal_for_buy(decision, market_context)

    expected_stop_distance = 5.0 * STOP_ATR_MULTIPLIER
    assert signal.symbol == "AAPL"
    assert signal.side == Side.LONG
    assert signal.reference_price == 200.0
    assert signal.stop_price == pytest.approx(200.0 - expected_stop_distance)
    assert signal.target_price == pytest.approx(200.0 + expected_stop_distance * TARGET_RISK_REWARD)
    assert signal.risk_reward == TARGET_RISK_REWARD
    assert signal.reason_codes == [ReasonCode.DECISION_ENGINE_SCORED]
    assert signal.generated_at == market_context.as_of


@pytest.mark.parametrize("label", [DecisionLabel.WATCH, DecisionLabel.AVOID, DecisionLabel.EXIT, DecisionLabel.NO_ACTION])
def test_build_signal_for_buy_rejects_every_non_buy_label(label):
    decision = _decision(label)
    with pytest.raises(SizingUnavailableError):
        build_signal_for_buy(decision, _market_context())


def test_build_signal_for_buy_rejects_missing_atr():
    decision = _decision(DecisionLabel.BUY)
    with pytest.raises(SizingUnavailableError):
        build_signal_for_buy(decision, _market_context(atr_14=None))


def test_build_signal_for_buy_rejects_non_positive_atr():
    decision = _decision(DecisionLabel.BUY)
    with pytest.raises(SizingUnavailableError):
        build_signal_for_buy(decision, _market_context(atr_14=0.0))


def test_build_signal_for_buy_rejects_mismatched_symbols():
    decision = _decision(DecisionLabel.BUY, symbol="AAPL")
    with pytest.raises(SizingUnavailableError):
        build_signal_for_buy(decision, _market_context(symbol="MSFT"))


def test_build_signal_for_buy_refuses_a_degenerate_negative_stop():
    """Adversarial edge case: an ATR large enough that reference_price -
    ATR*STOP_ATR_MULTIPLIER goes non-positive must be refused, not silently
    handed to RiskEngine as a structurally-valid-looking but nonsensical stop."""
    decision = _decision(DecisionLabel.BUY)
    # price=10, ATR=10 -> stop_distance=15 -> stop_price=-5
    with pytest.raises(SizingUnavailableError):
        build_signal_for_buy(decision, _market_context(price=10.0, atr_14=10.0))


# --- size_decision -------------------------------------------------------------


def test_size_decision_approves_and_sizes_with_ample_capital():
    decision = _decision(DecisionLabel.BUY)
    account = new_account(100_000.0)

    risk_decision = size_decision(decision, market_context=_market_context(), account=account)

    assert risk_decision.approved is True
    assert risk_decision.position_size is not None
    assert risk_decision.position_size.quantity > 0
    assert risk_decision.account_equity == 100_000.0


def test_size_decision_rejects_cleanly_with_insufficient_capital():
    decision = _decision(DecisionLabel.BUY)
    account = new_account(10.0)  # far too little to buy even 1 share at reference_price=200

    risk_decision = size_decision(decision, market_context=_market_context(), account=account)

    assert risk_decision.approved is False
    assert risk_decision.veto_reasons


def test_size_decision_raises_for_a_non_buy_label():
    decision = _decision(DecisionLabel.WATCH)
    account = new_account(100_000.0)

    with pytest.raises(SizingUnavailableError):
        size_decision(decision, market_context=_market_context(), account=account)


def test_size_decision_uses_the_unmodified_risk_engine_not_a_new_methodology():
    """Same Signal, evaluated directly through RiskEngine, must produce the
    identical RiskDecision as size_decision -- proving no parallel sizing
    logic was introduced."""
    from risk.config import RiskConfig
    from risk.engine import RiskEngine

    decision = _decision(DecisionLabel.BUY)
    market_context = _market_context()
    account = new_account(100_000.0)
    config = RiskConfig()

    via_bridge = size_decision(decision, market_context=market_context, account=account, risk_config=config)

    signal = build_signal_for_buy(decision, market_context)
    direct = RiskEngine(config).evaluate(signal, new_account(100_000.0))

    assert via_bridge == direct
