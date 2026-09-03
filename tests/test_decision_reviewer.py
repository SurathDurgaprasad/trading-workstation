from datetime import datetime, timezone

from decision_engine.models import Decision, DecisionLabel, DecisionReview, RiskContext
from market_intelligence.models import CandidateScore


def _candidate() -> CandidateScore:
    return CandidateScore(
        symbol="AAPL", as_of=datetime(2024, 6, 1), last_close=190.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.1, trend_score=1.0, momentum_score=0.5, breakout_score=0.01,
        relative_strength_score=0.02, sector_strength_score=None, composite_score=1.5,
        explanation=["Trend: uptrend -> score +1.00"],
    )


def _decision() -> Decision:
    return Decision(
        decision_id="dec-1", symbol="AAPL", as_of=datetime(2024, 6, 1, tzinfo=timezone.utc), label=DecisionLabel.BUY,
        rationale=["Composite, trend, and momentum all agree positively."], config_version="cfg1",
        scanner_evidence=_candidate(), research_evidence=None, market_context=None,
        risk_context=RiskContext.unknown(), narrative=None, narrative_unavailable_reason=None,
    )


def test_review_decision_returns_only_the_review_schema(monkeypatch):
    from agents import analyst, decision_reviewer
    from tests.conftest import FakeChatModel

    fake_review = DecisionReview(
        concerns=["Composite score is un-tuned per the Phase 19 report."],
        supporting_points=["Trend and momentum both corroborate the composite score."],
        overall_assessment="A defensible BUY given the recorded evidence, with the usual un-tuned-weights caveat.",
    )
    monkeypatch.setattr(analyst, "get_analyst_llm", lambda role: FakeChatModel({DecisionReview: fake_review}))

    result = decision_reviewer.review_decision(_decision())

    assert result is fake_review
    # Structural proof: no field exists that could hold a label/price/action.
    assert set(DecisionReview.model_fields) == {"concerns", "supporting_points", "overall_assessment"}


def test_review_decision_handles_no_research_evidence_gracefully(monkeypatch):
    from agents import analyst, decision_reviewer
    from tests.conftest import FakeChatModel

    fake_review = DecisionReview(concerns=[], supporting_points=["ok"], overall_assessment="fine")
    captured_prompts = []

    class _CapturingFakeChatModel(FakeChatModel):
        def with_structured_output(self, schema):
            runnable = super().with_structured_output(schema)
            original_invoke = runnable.invoke

            def _invoke(prompt):
                captured_prompts.append(prompt)
                return original_invoke(prompt)

            runnable.invoke = _invoke
            return runnable

    monkeypatch.setattr(analyst, "get_analyst_llm", lambda role: _CapturingFakeChatModel({DecisionReview: fake_review}))

    decision_reviewer.review_decision(_decision())

    assert captured_prompts
    assert "no news evidence available" in captured_prompts[0].lower() or "no AI research summary available" in captured_prompts[0]


def test_review_decision_works_for_a_no_action_decision_with_no_scanner_evidence(monkeypatch):
    # Unlike risk.sizing.build_signal_for_buy / predictions.tracker.create_prediction
    # (both BUY-only, since they need concrete price levels), review_decision is
    # deliberately label-agnostic -- reviewing "why NO_ACTION" is just as meaningful
    # as reviewing a BUY, and NO_ACTION is the one label allowed with no
    # scanner_evidence at all (see decision_engine's own model_validator).
    from agents import analyst, decision_reviewer
    from tests.conftest import FakeChatModel

    no_action = Decision(
        decision_id="dec-2", symbol="AAPL", as_of=datetime(2024, 6, 1, tzinfo=timezone.utc), label=DecisionLabel.NO_ACTION,
        rationale=["No scanner data available for AAPL."], config_version="cfg1", scanner_evidence=None,
        research_evidence=None, market_context=None, risk_context=RiskContext.unknown(),
        narrative=None, narrative_unavailable_reason=None,
    )
    fake_review = DecisionReview(concerns=[], supporting_points=[], overall_assessment="Nothing to act on yet.")
    monkeypatch.setattr(analyst, "get_analyst_llm", lambda role: FakeChatModel({DecisionReview: fake_review}))

    result = decision_reviewer.review_decision(no_action)

    assert result is fake_review
