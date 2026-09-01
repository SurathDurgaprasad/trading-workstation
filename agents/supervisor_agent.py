from agents.analyst import invoke_structured
from core.events import log_event
from schemas.debate import DebateSummary
from schemas.decision import TradingDecision
from state import TradingState


def supervisor_agent(state: TradingState) -> dict:
    debate: DebateSummary = state["debate_response"]
    market_context = state.get("market_context")
    market_lines = "\n".join(market_context.to_prompt_lines()) if market_context else "UNKNOWN"

    prompt = f"""
You are the Chief Investment Officer.

Question:

{state.get("question", "")}


OBSERVED MARKET DATA:

{market_lines}


Consensus Analysis:

{debate.model_dump_json(indent=2)}


Produce a final trading decision (action, confidence 0-100, entry strategy, stop
loss, reasoning, and key risks) grounded strictly in the OBSERVED MARKET DATA and
the consensus analysis above. This is an analytical opinion, not an instruction to
execute a trade.
"""

    result = invoke_structured(
        role="supervisor",
        label="Supervisor Agent",
        prompt=prompt,
        schema=TradingDecision,
    )
    log_event("decision_completed", symbol=state.get("symbol"), action=result.decision.value)
    return {"final_decision": result}
