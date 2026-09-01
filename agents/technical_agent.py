from agents.analyst import invoke_structured
from core.events import log_event
from schemas.technical import TechnicalAnalysis
from state import TradingState


def technical_agent(state: TradingState) -> dict:
    market_context = state.get("market_context")
    market_lines = "\n".join(market_context.to_prompt_lines()) if market_context else "UNKNOWN"

    prompt = f"""
You are a senior technical analyst.

OBSERVED MARKET DATA (computed by Python from live price history — treat as ground truth):

{market_lines}

KNOWLEDGE / STRATEGY DOCUMENTATION (retrieved reference material — may be generic, not specific to this symbol or moment):

{state.get("context", "")}

QUESTION:

{state.get("question", "")}

Analyze:

- Trend
- Support / Resistance
- VWAP
- Entry quality
- Exit quality

Base every claim about price, indicators, or volume ONLY on the OBSERVED MARKET DATA above.
Where a value is UNKNOWN, say so explicitly instead of inventing a number.
Use the KNOWLEDGE / STRATEGY DOCUMENTATION only for qualitative context, not as a market-data source.
"""

    result = invoke_structured(
        role="technical",
        label="Technical Agent",
        prompt=prompt,
        schema=TechnicalAnalysis,
    )
    log_event("technical_analysis_completed", symbol=state.get("symbol"))
    return {"technical_response": result}
