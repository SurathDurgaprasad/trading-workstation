from datetime import datetime

from risk.account import new_account
from risk.config import RiskConfig
from risk.contracts import SignalRecord
from risk.engine import RiskEngine, summarize_risk
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


def test_rejected_signals_are_not_silently_discarded():
    engine = RiskEngine(RiskConfig(min_risk_reward=5.0))  # deliberately unreachable
    account = new_account(100_000.0)

    signal = _signal(risk_reward=2.0)
    decision = engine.evaluate(signal, account)
    record = SignalRecord(timestamp=datetime(2026, 1, 1), symbol="TEST", signal=signal, decision=decision)

    assert not decision.approved
    assert record.decision.veto_reasons == [VetoReason.INVALID_RISK_REWARD]
    # the full signal is preserved on the record, not just a pass/fail bit
    assert record.signal.reference_price == 100.0


def test_summarize_risk_counts_generated_approved_rejected():
    engine = RiskEngine(RiskConfig(min_risk_reward=1.5))
    account = new_account(100_000.0)

    records = []
    for risk_reward in (2.0, 2.0, 0.5, 2.0, 0.5):  # 3 approved, 2 rejected
        signal = _signal(risk_reward=risk_reward)
        decision = engine.evaluate(signal, account)
        records.append(SignalRecord(timestamp=datetime(2026, 1, 1), symbol="TEST", signal=signal, decision=decision))

    summary = summarize_risk(records)

    assert summary.signals_generated == 5
    assert summary.signals_approved == 3
    assert summary.signals_rejected == 2
    assert summary.rejections_by_reason[VetoReason.INVALID_RISK_REWARD] == 2


def test_summarize_risk_rejection_counts_by_reason_only_include_reasons_that_actually_occurred():
    engine = RiskEngine(RiskConfig())
    account = new_account(100_000.0)
    signal = _signal()
    decision = engine.evaluate(signal, account)
    records = [SignalRecord(timestamp=datetime(2026, 1, 1), symbol="TEST", signal=signal, decision=decision)]

    summary = summarize_risk(records)

    assert VetoReason.MAX_DAILY_LOSS not in summary.rejections_by_reason  # never happened, must not appear as a 0-entry


def test_summarize_risk_average_and_maximum_risk_are_over_approved_trades_only():
    engine = RiskEngine(RiskConfig(risk_per_trade_pct=1.0, min_risk_reward=1.5))
    account = new_account(100_000.0)

    approved_signal = _signal(reference_price=100.0, stop_price=95.0)  # risk_per_unit=5, qty=200, total_risk=1000
    rejected_signal = _signal(risk_reward=0.5)

    records = [
        SignalRecord(
            timestamp=datetime(2026, 1, 1), symbol="TEST", signal=approved_signal,
            decision=engine.evaluate(approved_signal, account),
        ),
        SignalRecord(
            timestamp=datetime(2026, 1, 1), symbol="TEST", signal=rejected_signal,
            decision=engine.evaluate(rejected_signal, account),
        ),
    ]

    summary = summarize_risk(records)
    assert summary.average_risk_amount == 1_000.0
    assert summary.maximum_risk_amount == 1_000.0


def test_summarize_risk_handles_no_signals_at_all():
    summary = summarize_risk([])
    assert summary.signals_generated == 0
    assert summary.average_risk_amount is None
    assert summary.maximum_risk_amount is None
    assert summary.rejections_by_reason == {}
