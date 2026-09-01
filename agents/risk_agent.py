from agents.analyst import invoke_structured
from core.events import log_event
from schemas.risk import RiskAssessment
from state import TradingState


def risk_agent(state: TradingState) -> dict:
    market_context = state.get("market_context")
    market_lines = "\n".join(market_context.to_prompt_lines()) if market_context else "UNKNOWN"

    prompt = f"""
You are a professional risk manager.

OBSERVED MARKET DATA (computed by Python from live price history — treat as ground truth):

{market_lines}

KNOWLEDGE / STRATEGY DOCUMENTATION (retrieved reference material — may be generic, not specific to this symbol or moment):

{state.get("context", "")}

QUESTION:

{state.get("question", "")}

Analyze:

- Position sizing
- Risk/Reward
- Stop loss
- Capital protection

Ground stop-loss and volatility discussion in the OBSERVED ATR14 and price above.
Do NOT invent a specific account size, capital amount, or currency figure — no capital
amount has been provided. Speak in relative/percentage terms, or state that position
sizing cannot be quantified without a stated account size.
Clearly separate what is Observed (from market data), Calculated (derived from it),
Suggested (your recommendation), and Unknown (not available).
"""

    result = invoke_structured(
        role="risk",
        label="Risk Agent",
        prompt=prompt,
        schema=RiskAssessment,
    )
    log_event("risk_analysis_completed", symbol=state.get("symbol"))
    return {"risk_response": result}
