from datetime import datetime

from decision_engine.config import DecisionConfig
from decision_engine.models import DecisionLabel, RiskContext
from decision_engine.rules import classify
from market_intelligence.models import CandidateScore


def _candidate(*, composite: float, trend: float = 0.0, momentum: float = 0.0) -> CandidateScore:
    return CandidateScore(
        symbol="AAPL", as_of=datetime(2024, 6, 1), last_close=190.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.1, trend_score=trend, momentum_score=momentum, breakout_score=0.01,
        relative_strength_score=0.02, sector_strength_score=None, composite_score=composite,
        explanation=["fake"],
    )


def _no_position() -> RiskContext:
    return RiskContext(has_open_position=False)


def _holding() -> RiskContext:
    return RiskContext(has_open_position=True)


# --- no scanner evidence -----------------------------------------------------


def test_no_candidate_and_no_position_gives_no_action():
    label, reasons = classify(symbol="AAPL", candidate=None, risk_context=_no_position(), config=DecisionConfig())
    assert label == DecisionLabel.NO_ACTION
    assert reasons


def test_no_candidate_while_holding_gives_no_action_not_watch():
    # Regression: WATCH/EXIT must always carry scanner evidence -- Decision's own
    # model_validator rejects a non-NO_ACTION label with scanner_evidence=None, so this
    # branch must agree with the not-holding branch rather than returning WATCH with
    # nothing behind it (see tests/test_decision_engine_engine.py's crash-reproduction test).
    label, reasons = classify(symbol="AAPL", candidate=None, risk_context=_holding(), config=DecisionConfig())
    assert label == DecisionLabel.NO_ACTION


# --- not holding: BUY / WATCH / AVOID ----------------------------------------


def test_all_factors_positive_gives_buy():
    candidate = _candidate(composite=1.5, trend=1.0, momentum=0.5)
    label, reasons = classify(symbol="AAPL", candidate=candidate, risk_context=_no_position(), config=DecisionConfig())
    assert label == DecisionLabel.BUY
    assert any("agree positively" in r for r in reasons)


def test_positive_composite_without_corroboration_gives_watch():
    candidate = _candidate(composite=0.5, trend=-0.2, momentum=0.1)
    label, reasons = classify(symbol="AAPL", candidate=candidate, risk_context=_no_position(), config=DecisionConfig())
    assert label == DecisionLabel.WATCH
    assert any("insufficient agreement" in r for r in reasons)


def test_non_positive_composite_gives_avoid():
    candidate = _candidate(composite=-0.3, trend=-1.0, momentum=-0.5)
    label, reasons = classify(symbol="AAPL", candidate=candidate, risk_context=_no_position(), config=DecisionConfig())
    assert label == DecisionLabel.AVOID


def test_zero_composite_is_not_positive_and_gives_avoid():
    candidate = _candidate(composite=0.0, trend=1.0, momentum=1.0)
    label, _ = classify(symbol="AAPL", candidate=candidate, risk_context=_no_position(), config=DecisionConfig())
    assert label == DecisionLabel.AVOID


def test_corroboration_disabled_allows_buy_on_composite_alone():
    candidate = _candidate(composite=0.4, trend=-0.1, momentum=-0.1)
    config = DecisionConfig(require_corroboration_for_buy=False)
    label, reasons = classify(symbol="AAPL", candidate=candidate, risk_context=_no_position(), config=config)
    assert label == DecisionLabel.BUY
    assert any("corroboration rule disabled" in r for r in reasons)


def test_corroboration_disabled_still_avoids_on_non_positive_composite():
    candidate = _candidate(composite=-0.1)
    config = DecisionConfig(require_corroboration_for_buy=False)
    label, _ = classify(symbol="AAPL", candidate=candidate, risk_context=_no_position(), config=config)
    assert label == DecisionLabel.AVOID


# --- holding: WATCH / EXIT ----------------------------------------------------


def test_holding_with_positive_composite_gives_watch():
    candidate = _candidate(composite=0.8, trend=1.0, momentum=1.0)
    label, reasons = classify(symbol="AAPL", candidate=candidate, risk_context=_holding(), config=DecisionConfig())
    assert label == DecisionLabel.WATCH
    assert any("no exit signal yet" in r for r in reasons)


def test_holding_with_non_positive_composite_gives_exit():
    candidate = _candidate(composite=-0.2, trend=-1.0, momentum=-0.5)
    label, reasons = classify(symbol="AAPL", candidate=candidate, risk_context=_holding(), config=DecisionConfig())
    assert label == DecisionLabel.EXIT
    assert any("no longer positive" in r for r in reasons)


def test_holding_with_zero_composite_gives_exit():
    candidate = _candidate(composite=0.0)
    label, _ = classify(symbol="AAPL", candidate=candidate, risk_context=_holding(), config=DecisionConfig())
    assert label == DecisionLabel.EXIT


# --- determinism / reproducibility -------------------------------------------


def test_classify_is_a_pure_function_of_its_inputs():
    candidate = _candidate(composite=0.9, trend=0.5, momentum=0.3)
    risk_context = _no_position()
    config = DecisionConfig()

    result1 = classify(symbol="AAPL", candidate=candidate, risk_context=risk_context, config=config)
    result2 = classify(symbol="AAPL", candidate=candidate, risk_context=risk_context, config=config)

    assert result1 == result2
