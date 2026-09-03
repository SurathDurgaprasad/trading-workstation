"""Phase 21 -- decision orchestration.

`make_decision` is the only public entry point: gathers already-computed
evidence (a market_intelligence.CandidateScore, a research.ResearchReport,
a market.context.MarketContext, a RiskContext -- ALL optional except
risk_context, which defaults to RiskContext.unknown()), calls
decision_engine.rules.classify for the deterministic label, then
OPTIONALLY asks an LLM to narrate that already-fixed label -- never to
decide it. Same never-blocks-on-Ollama posture as research.summarizer.
build_research_report and main.py's _try_ai_explain.

Technical Analysis (MarketContext) and Research Evidence are recorded on
the Decision as supporting context but do NOT drive classify's label in
this phase -- see the Phase 21 report's known-limitations section for
why, and what a future phase would need to change that responsibly.
"""

import logging
from datetime import datetime, timezone

from decision_engine.config import DecisionConfig
from decision_engine.confidence import compute_confidence
from decision_engine.models import Decision, RiskContext
from decision_engine.rules import classify
from market.context import MarketContext
from market_intelligence.models import CandidateScore
from research.models import ResearchReport

logger = logging.getLogger(__name__)


def narrate_decision(decision: Decision) -> str:
    # Deferred: importing agents.analyst pulls in langchain_core -- callers
    # that never reach this function (e.g. `decide --no-narrative`) must
    # not pay that cost, same discipline as research/summarizer.py.
    from agents.analyst import invoke_structured
    from decision_engine.models import DecisionNarrative

    rationale_lines = "\n".join(f"- {line}" for line in decision.rationale)
    research_line = (
        decision.research_evidence.ai_summary.summary
        if decision.research_evidence is not None and decision.research_evidence.ai_summary is not None
        else "(no AI research summary available)"
    )

    prompt = f"""
You are narrating a decision ALREADY MADE by a deterministic rules engine for {decision.symbol}.
You are NOT deciding anything -- the label below is fixed and you cannot change it, override it,
or suggest a different one.

LABEL: {decision.label.value}

DETERMINISTIC RATIONALE (the actual basis for this label):
{rationale_lines}

RESEARCH CONTEXT (supporting background only, did not determine the label):
{research_line}

Write a short, plain-language narrative (2-4 sentences) explaining this label to a human reader,
using only the evidence above. Do not state or imply a different label, a price target, or
investment advice.
"""

    result = invoke_structured(role="decision_narrator", label="Decision Narrator", prompt=prompt, schema=DecisionNarrative)
    return result.narrative


def make_decision(
    symbol: str,
    *,
    candidate: CandidateScore | None = None,
    research: ResearchReport | None = None,
    market_context: MarketContext | None = None,
    risk_context: RiskContext | None = None,
    config: DecisionConfig | None = None,
    include_narrative: bool = True,
    now: datetime | None = None,
) -> Decision:
    normalized = symbol.strip().upper()
    config = config or DecisionConfig()
    resolved_risk_context = risk_context or RiskContext.unknown()
    decision_time = now or datetime.now(timezone.utc)

    label, rationale = classify(symbol=normalized, candidate=candidate, risk_context=resolved_risk_context, config=config)
    confidence_breakdown = compute_confidence(candidate)

    decision = Decision(
        decision_id=Decision.new_id(),
        symbol=normalized,
        as_of=decision_time,
        label=label,
        rationale=rationale,
        config_version=config.version_id(),
        scanner_evidence=candidate,
        research_evidence=research,
        market_context=market_context,
        risk_context=resolved_risk_context,
        confidence=confidence_breakdown.score,
        confidence_explanation=confidence_breakdown.explanation(),
        narrative=None,
        narrative_unavailable_reason=None,
    )

    if not include_narrative:
        return decision

    try:
        from llm.provider import check_ollama_availability

        check_ollama_availability()
        narrative = narrate_decision(decision)
        return decision.model_copy(update={"narrative": narrative})
    except Exception as exc:  # noqa: BLE001 -- AI narration must never block a decision
        logger.info("Decision narrative unavailable for %s, continuing without it: %s", normalized, exc)
        return decision.model_copy(update={"narrative_unavailable_reason": f"AI narrative unavailable: {exc}"})
