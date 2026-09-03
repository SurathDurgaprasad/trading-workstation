from datetime import datetime

from decision_engine.engine import make_decision
from decision_engine.models import DecisionLabel, DecisionNarrative, RiskContext
from market_intelligence.models import CandidateScore


def _candidate(*, composite: float = 1.5, trend: float = 1.0, momentum: float = 0.5) -> CandidateScore:
    return CandidateScore(
        symbol="AAPL", as_of=datetime(2024, 6, 1), last_close=190.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.1, trend_score=trend, momentum_score=momentum, breakout_score=0.01,
        relative_strength_score=0.02, sector_strength_score=None, composite_score=composite,
        explanation=["fake"],
    )


def test_make_decision_without_narrative_returns_a_pure_deterministic_label():
    decision = make_decision("AAPL", candidate=_candidate(), include_narrative=False)

    assert decision.label == DecisionLabel.BUY
    assert decision.narrative is None
    assert decision.narrative_unavailable_reason is None
    assert decision.symbol == "AAPL"
    assert decision.scanner_evidence is not None
    assert decision.risk_context == RiskContext.unknown()


def test_make_decision_normalizes_symbol_case():
    decision = make_decision("aapl", candidate=_candidate(), include_narrative=False)
    assert decision.symbol == "AAPL"


def test_make_decision_no_action_when_no_candidate():
    decision = make_decision("AAPL", candidate=None, include_narrative=False)
    assert decision.label == DecisionLabel.NO_ACTION
    assert decision.scanner_evidence is None


def test_make_decision_does_not_crash_when_holding_with_no_scanner_evidence():
    """Regression for a bug found by self-audit: classify() used to return WATCH here
    with no candidate, which Decision's own model_validator then rejected (WATCH requires
    scanner_evidence) -- make_decision would raise ValueError instead of returning a
    Decision. Fixed in decision_engine/rules.py; this proves it end-to-end through
    make_decision, not just classify() in isolation."""
    decision = make_decision("AAPL", candidate=None, risk_context=RiskContext(has_open_position=True), include_narrative=False)

    assert decision.label == DecisionLabel.NO_ACTION
    assert decision.scanner_evidence is None


def test_make_decision_includes_narrative_when_available(monkeypatch):
    from agents import analyst
    from llm import provider as llm_provider
    from tests.conftest import FakeChatModel

    fake_narrative = DecisionNarrative(narrative="A deterministic BUY, corroborated across factors.")
    monkeypatch.setattr(analyst, "get_analyst_llm", lambda role: FakeChatModel({DecisionNarrative: fake_narrative}))
    monkeypatch.setattr(llm_provider, "check_ollama_availability", lambda **kwargs: None)

    decision = make_decision("AAPL", candidate=_candidate())

    assert decision.narrative == fake_narrative.narrative
    assert decision.narrative_unavailable_reason is None
    # The narrative cannot have changed the label -- it was fixed before the LLM was ever called.
    assert decision.label == DecisionLabel.BUY


def test_make_decision_degrades_gracefully_when_ollama_unavailable(monkeypatch):
    from llm import provider as llm_provider

    def _raise_unavailable(**kwargs):
        raise RuntimeError("Ollama is not reachable at http://localhost:11434")

    monkeypatch.setattr(llm_provider, "check_ollama_availability", _raise_unavailable)

    decision = make_decision("AAPL", candidate=_candidate())

    assert decision.narrative is None
    assert decision.narrative_unavailable_reason is not None
    assert "not reachable" in decision.narrative_unavailable_reason
    # The deterministic label is unaffected by the AI layer failing.
    assert decision.label == DecisionLabel.BUY


def test_make_decision_respects_include_narrative_false(monkeypatch):
    from llm import provider as llm_provider

    called = []
    monkeypatch.setattr(llm_provider, "check_ollama_availability", lambda **kwargs: called.append(True))

    decision = make_decision("AAPL", candidate=_candidate(), include_narrative=False)

    assert decision.narrative is None
    assert decision.narrative_unavailable_reason is None
    assert called == []


def test_narrate_decision_returns_only_the_narrative_schema(monkeypatch):
    from agents import analyst
    from decision_engine.engine import narrate_decision
    from decision_engine.models import Decision
    from tests.conftest import FakeChatModel

    fake_narrative = DecisionNarrative(narrative="Explaining the fixed label.")
    monkeypatch.setattr(analyst, "get_analyst_llm", lambda role: FakeChatModel({DecisionNarrative: fake_narrative}))

    decision = make_decision("AAPL", candidate=_candidate(), include_narrative=False)
    result = narrate_decision(decision)

    assert result == fake_narrative.narrative
    # Structural proof: DecisionNarrative has no field that could hold a label/price/action.
    assert set(DecisionNarrative.model_fields) == {"narrative"}
