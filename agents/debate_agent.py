from agents.analyst import invoke_structured
from core.events import log_event
from schemas.critic import CriticAssessment
from schemas.debate import DebateSummary
from schemas.risk import RiskAssessment
from schemas.technical import TechnicalAnalysis
from state import TradingState


def debate_agent(state: TradingState) -> dict:
    technical: TechnicalAnalysis = state["technical_response"]
    risk: RiskAssessment = state["risk_response"]
    critic: CriticAssessment = state["critic_response"]

    prompt = f"""
Three experts reviewed the same trading opportunity.

Technical Analyst:

{technical.model_dump_json(indent=2)}


Risk Manager:

{risk.model_dump_json(indent=2)}


Devil's Advocate:

{critic.model_dump_json(indent=2)}


Tasks:

1. Identify agreements.
2. Identify disagreements.
3. Resolve conflicts.
4. Produce a consensus view.
"""

    result = invoke_structured(
        role="debate",
        label="Debate Agent",
        prompt=prompt,
        schema=DebateSummary,
    )
    log_event("debate_completed", symbol=state.get("symbol"))
    return {"debate_response": result}
