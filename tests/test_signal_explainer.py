from datetime import datetime

from market.context import MarketContext
from risk.contracts import Exposure, PositionSize, RiskDecision
from risk.veto import VetoReason
from schemas.explanation import SignalExplanation
from strategy.signal import ReasonCode, Side, Signal


def _sample_market_context() -> MarketContext:
    return MarketContext(
        symbol="AAPL", as_of=datetime(2026, 8, 24), price=310.34,
        sma_20=313.01, sma_50=310.50, rsi_14=48.23,
        macd=-1.49, macd_signal=-1.25, macd_histogram=-0.23,
        atr_14=6.04, volume_ratio=0.66, volume_trend="decreasing",
    )


def _sample_signal() -> Signal:
    return Signal(
        symbol="AAPL", generated_at=datetime(2026, 8, 24), side=Side.LONG,
        reference_price=310.34, stop_price=301.28, target_price=328.46,
        risk_reward=2.0, strategy_name="trend_momentum_baseline",
        reason_codes=[ReasonCode.TREND_CONFIRMED, ReasonCode.MOMENTUM_CONFIRMED, ReasonCode.VOLUME_CONFIRMED],
    )


def _sample_risk_decision(*, approved: bool) -> RiskDecision:
    position_size = PositionSize(quantity=50, risk_per_unit=9.06, total_risk=453.0, notional_value=15_517.0)
    return RiskDecision(
        approved=approved,
        position_size=position_size if approved else None,
        risk_amount=453.0 if approved else None,
        risk_percent=0.45 if approved else None,
        exposure=Exposure(position_notional=15_517.0, account_equity=100_000.0, exposure_pct=15.5),
        veto_reasons=[] if approved else [VetoReason.MAX_DRAWDOWN],
        explanation="Approved: 50 units, risk 453.00." if approved else "Rejected: MAX_DRAWDOWN.",
        risk_reduced=False,
        account_equity=100_000.0,
        current_drawdown_pct=2.1,
        daily_pnl=-120.0,
        consecutive_losses=0,
        requested_quantity=50,
        approved_quantity=50 if approved else 0,
    )


def test_explain_signal_returns_only_the_explanation_schema(monkeypatch):
    from agents import analyst, signal_explainer
    from tests.conftest import FakeChatModel

    fake_explanation = SignalExplanation(
        supporting_evidence=["SMA20 > SMA50 confirms an uptrend."],
        contradicting_evidence=["Volume trend is decreasing, weakening conviction."],
        narrative="A mixed setup: trend and momentum favor a long, but fading volume is a concern.",
    )
    fake_llm = FakeChatModel({SignalExplanation: fake_explanation})
    monkeypatch.setattr(analyst, "get_analyst_llm", lambda role: fake_llm)

    result = signal_explainer.explain_signal(
        market_context=_sample_market_context(),
        signal=_sample_signal(),
        risk_decision=_sample_risk_decision(approved=True),
    )

    assert isinstance(result, SignalExplanation)
    assert result is fake_explanation
    # Structural proof of "cannot mutate": the return type has no field
    # capable of holding a revised entry/stop/target/quantity/PnL at all.
    assert set(SignalExplanation.model_fields) == {"supporting_evidence", "contradicting_evidence", "narrative"}


def test_explain_signal_works_for_a_rejected_decision_too(monkeypatch):
    from agents import analyst, signal_explainer
    from tests.conftest import FakeChatModel

    fake_explanation = SignalExplanation(
        supporting_evidence=[], contradicting_evidence=["Drawdown limit breached."], narrative="Rejected for risk reasons.",
    )
    fake_llm = FakeChatModel({SignalExplanation: fake_explanation})
    monkeypatch.setattr(analyst, "get_analyst_llm", lambda role: fake_llm)

    result = signal_explainer.explain_signal(
        market_context=_sample_market_context(),
        signal=_sample_signal(),
        risk_decision=_sample_risk_decision(approved=False),
    )

    assert isinstance(result, SignalExplanation)
