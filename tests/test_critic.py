"""The deterministic critic (critic/): independently re-examines an
already-proposed BUY. Pure-function tests -- no I/O, no LLM, no
network, matching decision_engine/risk's own test style exactly."""

from datetime import datetime, timedelta, timezone

import pytest

from critic.config import CriticConfig
from critic.engine import CriticUnavailableError, evaluate
from critic.models import CriticCheckName, CriticVerdict
from decision_engine.models import Decision, DecisionLabel, RiskContext
from market.context import MarketContext
from market_intelligence.models import CandidateScore
from market_intelligence.regime import BenchmarkContext
from research.models import ResearchReport
from strategy.signal import ReasonCode, Side, Signal

_NOW = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)


def _candidate(**overrides) -> CandidateScore:
    base = dict(
        symbol="AAPL", as_of=_NOW - timedelta(hours=1), last_close=190.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.1, trend_score=1.0, momentum_score=0.5, breakout_score=0.01,
        relative_strength_score=0.02, sector_strength_score=None, composite_score=1.5,
        explanation=["fake"],
    )
    base.update(overrides)
    return CandidateScore(**base)


def _market_context(**overrides) -> MarketContext:
    base = dict(symbol="AAPL", as_of=_NOW - timedelta(hours=1), price=190.0, macd_histogram=0.5)
    base.update(overrides)
    return MarketContext(**base)


def _research() -> ResearchReport:
    return ResearchReport(report_id="r1", symbol="AAPL", as_of=_NOW, news=[], sector=None, ai_summary=None, ai_summary_unavailable_reason=None)


def _decision(**overrides) -> Decision:
    base = dict(
        decision_id="dec1", symbol="AAPL", as_of=_NOW, label=DecisionLabel.BUY,
        rationale=["fake"], config_version="cfg1", scanner_evidence=_candidate(),
        research_evidence=_research(), market_context=_market_context(), risk_context=RiskContext.unknown(),
        confidence=0.8, confidence_explanation="fake", narrative=None, narrative_unavailable_reason=None,
    )
    base.update(overrides)
    return Decision(**base)


def _signal(**overrides) -> Signal:
    base = dict(
        symbol="AAPL", generated_at=_NOW - timedelta(hours=1), side=Side.LONG,
        reference_price=190.0, stop_price=185.0, target_price=200.0, risk_reward=2.0,
        strategy_name="unit-test", reason_codes=[ReasonCode.TREND_CONFIRMED],
    )
    base.update(overrides)
    return Signal(**base)


# --- basic contract ---------------------------------------------------------


def test_evaluate_rejects_a_non_buy_decision_clearly():
    with pytest.raises(CriticUnavailableError):
        evaluate(_decision(label=DecisionLabel.WATCH), _signal())


def test_evaluate_rejects_a_symbol_mismatch():
    with pytest.raises(CriticUnavailableError):
        evaluate(_decision(), _signal(symbol="MSFT"))


# --- APPROVE ------------------------------------------------------------------


def test_approve_on_a_clean_fully_evidenced_buy():
    assessment = evaluate(_decision(), _signal(), now=_NOW)
    assert assessment.verdict == CriticVerdict.APPROVE
    assert assessment.failed_checks == ()
    assert assessment.warnings == ()
    # Full transparency: every check ran, even the ones that passed.
    assert len(assessment.checks) == len(CriticCheckName)


# --- REJECT (HARD checks) ------------------------------------------------------


def test_reject_when_kill_switch_is_active():
    assessment = evaluate(_decision(), _signal(), now=_NOW, kill_switch_active=True)
    assert assessment.verdict == CriticVerdict.REJECT
    assert CriticCheckName.KILL_SWITCH.value in assessment.failed_checks


def test_kill_switch_not_evaluated_when_state_not_supplied():
    assessment = evaluate(_decision(), _signal(), now=_NOW)
    check = next(c for c in assessment.checks if c.name == CriticCheckName.KILL_SWITCH)
    assert check.evaluated is False


def test_reject_on_a_future_timestamped_market_context():
    future_context = _market_context(as_of=_NOW + timedelta(hours=2))
    assessment = evaluate(_decision(market_context=future_context), _signal(), now=_NOW)
    assert assessment.verdict == CriticVerdict.REJECT
    assert CriticCheckName.FUTURE_TIMESTAMP.value in assessment.failed_checks


def test_reject_on_stale_data_past_the_configured_limit():
    stale_context = _market_context(as_of=_NOW - timedelta(days=10))
    config = CriticConfig(max_data_staleness_seconds=86_400.0)  # 1 day
    assessment = evaluate(_decision(market_context=stale_context), _signal(), now=_NOW, config=config)
    assert assessment.verdict == CriticVerdict.REJECT
    assert CriticCheckName.DATA_FRESHNESS.value in assessment.failed_checks


def test_reject_on_an_existing_pending_order():
    assessment = evaluate(_decision(), _signal(), now=_NOW, existing_pending_order=True)
    assert assessment.verdict == CriticVerdict.REJECT
    assert CriticCheckName.DUPLICATE_EXPOSURE.value in assessment.failed_checks


def test_reject_on_an_existing_open_position():
    assessment = evaluate(_decision(), _signal(), now=_NOW, existing_open_position=True)
    assert assessment.verdict == CriticVerdict.REJECT
    assert CriticCheckName.DUPLICATE_EXPOSURE.value in assessment.failed_checks


def test_reject_on_a_degenerate_signal_structure():
    """Defense in depth: build_signal_for_buy already guarantees sane
    ordering, but the critic must not assume that forever -- a signal
    built any other way with a bad structure must still be caught."""
    bad_signal = _signal(stop_price=195.0)  # stop above entry -- degenerate for a LONG
    assessment = evaluate(_decision(), bad_signal, now=_NOW)
    assert assessment.verdict == CriticVerdict.REJECT
    assert CriticCheckName.TRADE_STRUCTURE.value in assessment.failed_checks


def test_reject_when_scanner_evidence_is_somehow_missing():
    """Should be structurally impossible via Decision's own model_validator
    for a BUY, but the critic checks it anyway -- never assume an
    upstream invariant holds forever."""
    decision = _decision().model_copy(update={"scanner_evidence": None})
    # model_copy bypasses the validator (frozen model construction check
    # only runs on __init__), so this genuinely exercises the check.
    assessment = evaluate(decision, _signal(), now=_NOW)
    assert assessment.verdict == CriticVerdict.REJECT
    assert CriticCheckName.EVIDENCE_COMPLETENESS_SCANNER.value in assessment.failed_checks


# --- INSUFFICIENT_EVIDENCE ------------------------------------------------------


def test_insufficient_evidence_when_no_market_context_and_no_research():
    assessment = evaluate(_decision(market_context=None, research_evidence=None), _signal(), now=_NOW)
    assert assessment.verdict == CriticVerdict.INSUFFICIENT_EVIDENCE


def test_not_insufficient_evidence_when_only_market_context_is_missing():
    """Research evidence alone is enough to avoid INSUFFICIENT_EVIDENCE --
    missing market context is instead just one WARNING among several."""
    assessment = evaluate(_decision(market_context=None), _signal(), now=_NOW)
    assert assessment.verdict != CriticVerdict.INSUFFICIENT_EVIDENCE


def test_a_hard_reject_takes_priority_over_insufficient_evidence():
    """Regression (found via self-review before this was ever wired into
    a live path, not observed as a failure): when a clear, independently-
    verifiable HARD failure (kill switch active) coincides with thin
    evidence (no market_context, no research), REJECT must win --
    'reject, and here is exactly why' is strictly more actionable than
    'insufficient evidence', and must never be masked by it."""
    assessment = evaluate(
        _decision(market_context=None, research_evidence=None), _signal(), now=_NOW, kill_switch_active=True,
    )
    assert assessment.verdict == CriticVerdict.REJECT
    assert CriticCheckName.KILL_SWITCH.value in assessment.failed_checks


# --- DOWNGRADE (accumulated WARNINGs) --------------------------------------------


def test_downgrade_when_warning_threshold_is_reached():
    """Two independent, genuine warnings (weak volume + poor risk/reward)
    on an otherwise fully-evidenced decision -- neither alone is
    disqualifying, but together they cross the default threshold of 2."""
    weak_volume_candidate = _candidate(volume_ratio=0.1)
    decision = _decision(scanner_evidence=weak_volume_candidate)
    weak_rr_signal = _signal(risk_reward=1.0)  # below CriticConfig's default 1.5 minimum

    assessment = evaluate(decision, weak_rr_signal, now=_NOW)

    assert assessment.verdict == CriticVerdict.DOWNGRADE
    assert CriticCheckName.VOLUME_CONFIRMATION.value in assessment.warnings
    assert CriticCheckName.RISK_REWARD.value in assessment.warnings


def test_single_warning_alone_does_not_downgrade():
    weak_rr_signal = _signal(risk_reward=1.0)
    assessment = evaluate(_decision(), weak_rr_signal, now=_NOW)
    assert assessment.verdict == CriticVerdict.APPROVE
    assert CriticCheckName.RISK_REWARD.value in assessment.warnings


def test_downgrade_threshold_is_configurable():
    config = CriticConfig(downgrade_warning_threshold=1)
    weak_rr_signal = _signal(risk_reward=1.0)
    assessment = evaluate(_decision(), weak_rr_signal, now=_NOW, config=config)
    assert assessment.verdict == CriticVerdict.DOWNGRADE


# --- indicator contradiction / regime conflict -----------------------------------


def test_indicator_contradiction_warns_when_macd_disagrees_with_momentum():
    contradictory_context = _market_context(macd_histogram=-0.5)  # candidate.momentum_score is +0.5
    assessment = evaluate(_decision(market_context=contradictory_context), _signal(), now=_NOW)
    assert CriticCheckName.INDICATOR_CONTRADICTION.value in assessment.warnings


def test_indicator_contradiction_not_evaluated_without_macd_data():
    context_no_macd = _market_context(macd_histogram=None)
    assessment = evaluate(_decision(market_context=context_no_macd), _signal(), now=_NOW)
    check = next(c for c in assessment.checks if c.name == CriticCheckName.INDICATOR_CONTRADICTION)
    assert check.evaluated is False


def test_regime_conflict_warns_on_a_downtrend_benchmark():
    hostile_regime = BenchmarkContext(
        symbol="^NSEI", trend_regime="DOWNTREND", volatility_regime="NORMAL_VOLATILITY",
        last_close=20000.0, atr_pct_of_price=0.01, atr_pct_vs_trailing_average=1.0,
    )
    assessment = evaluate(_decision(), _signal(), now=_NOW, benchmark_context=hostile_regime)
    assert CriticCheckName.REGIME_CONFLICT.value in assessment.warnings


def test_regime_conflict_not_evaluated_without_a_benchmark_context():
    assessment = evaluate(_decision(), _signal(), now=_NOW)
    check = next(c for c in assessment.checks if c.name == CriticCheckName.REGIME_CONFLICT)
    assert check.evaluated is False


def test_regime_conflict_not_evaluated_when_regime_is_unknown():
    unknown_regime = BenchmarkContext(
        symbol=None, trend_regime="UNKNOWN", volatility_regime="UNKNOWN",
        last_close=None, atr_pct_of_price=None, atr_pct_vs_trailing_average=None,
    )
    assessment = evaluate(_decision(), _signal(), now=_NOW, benchmark_context=unknown_regime)
    check = next(c for c in assessment.checks if c.name == CriticCheckName.REGIME_CONFLICT)
    assert check.evaluated is False


# --- confidence integrity --------------------------------------------------------


def test_confidence_integrity_warns_when_confidence_is_absent():
    assessment = evaluate(_decision(confidence=None, confidence_explanation=None), _signal(), now=_NOW)
    assert CriticCheckName.CONFIDENCE_INTEGRITY.value in assessment.warnings


# --- config versioning (mirrors RiskConfig.version_id's own contract) -----------


def test_config_version_id_is_stable_for_identical_config():
    assert CriticConfig().version_id() == CriticConfig().version_id()


def test_config_version_id_changes_when_a_field_changes():
    assert CriticConfig().version_id() != CriticConfig(min_risk_reward=3.0).version_id()


def test_assessment_carries_the_config_version():
    assessment = evaluate(_decision(), _signal(), now=_NOW)
    assert assessment.config_version == CriticConfig().version_id()
