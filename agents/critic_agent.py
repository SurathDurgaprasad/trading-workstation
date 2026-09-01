from agents.analyst import invoke_structured
from core.events import log_event
from schemas.critic import CriticAssessment
from state import TradingState


def critic_agent(state: TradingState) -> dict:
    market_context = state.get("market_context")
    market_lines = "\n".join(market_context.to_prompt_lines()) if market_context else "UNKNOWN"

    prompt = f"""
You are a devil's advocate.

OBSERVED MARKET DATA (computed by Python from live price history — treat as ground truth):

{market_lines}

KNOWLEDGE / STRATEGY DOCUMENTATION (retrieved reference material — may be generic, not specific to this symbol or moment):

{state.get("context", "")}

QUESTION:

{state.get("question", "")}

Find:

- Weak assumptions
- Hidden risks
- Failure scenarios
- Missing rules

Challenge the strategy aggressively. Specifically call out:

- Any indicator in OBSERVED MARKET DATA marked UNKNOWN, and what that missing data
  could hide.
- Any place where indicators conflict with each other (e.g. price above SMA20 but
  RSI overbought, or MACD histogram disagreeing with the SMA trend).
- Any place where the KNOWLEDGE / STRATEGY DOCUMENTATION makes a claim that the
  OBSERVED MARKET DATA does not currently support.

Do not produce generic "there are risks" filler — every point must reference a
specific value or gap above.
"""

    result = invoke_structured(
        role="critic",
        label="Critic Agent",
        prompt=prompt,
        schema=CriticAssessment,
    )
    log_event("critic_analysis_completed", symbol=state.get("symbol"))
    return {"critic_response": result}
