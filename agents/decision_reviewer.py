"""Phase 25 -- AI Multi-Agent Market Research: the one genuinely new
agent this phase adds. See the Phase 25 report for why the roadmap's
other suggested agents (Market Analyst, Technical Analyst, News Analyst,
Sector Analyst, Risk Critic) are NOT duplicated here -- each already has
substantial coverage elsewhere (the existing `analyze` pipeline's
technical_agent/risk_agent/critic_agent, or research/summarizer.py's
evidence narration for news/sector).

review_decision provides an independent, adversarial second opinion on
an already-fixed decision_engine.models.Decision -- reusing
agents.analyst.invoke_structured exactly as every other AI feature in
this pipeline does (research_summarizer, decision_narrator). Same
"cannot change the decision" type-level guarantee: DecisionReview has no
field that could hold a revised label, price, or action (see
decision_engine/models.py).
"""

from agents.analyst import invoke_structured
from decision_engine.models import Decision, DecisionReview


def review_decision(decision: Decision) -> DecisionReview:
    rationale_lines = "\n".join(f"- {line}" for line in decision.rationale)

    research_summary_line = (
        decision.research_evidence.ai_summary.summary
        if decision.research_evidence is not None and decision.research_evidence.ai_summary is not None
        else "(no AI research summary available)"
    )
    news_lines = "\n".join(
        f"- [{item.published_at.isoformat()}] ({item.source}) {item.title}"
        for item in (decision.research_evidence.news if decision.research_evidence is not None else [])
    ) or "(no news evidence available)"

    prompt = f"""
You are an independent reviewer giving a second opinion on a decision ALREADY MADE by a
deterministic rules engine for {decision.symbol}. You are NOT deciding anything -- the
label below is fixed and you cannot change it, override it, or suggest a different one.
Your job is to find real weaknesses and real strengths in the evidence behind it.

LABEL: {decision.label.value}

DETERMINISTIC RATIONALE (the actual basis for this label):
{rationale_lines}

NEWS EVIDENCE:
{news_lines}

RESEARCH SUMMARY (if available):
{research_summary_line}

Provide:
- concerns: specific reasons this decision might be wrong, weak, or premature -- each grounded
  in the evidence above, not generic caution.
- supporting_points: specific reasons the evidence above genuinely supports this decision.
- overall_assessment: a short, balanced summary. You cannot state or imply a different label.
"""

    return invoke_structured(role="decision_reviewer", label="Decision Reviewer", prompt=prompt, schema=DecisionReview)
