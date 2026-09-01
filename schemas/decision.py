from pydantic import BaseModel, Field

from schemas.enums import TradingAction


class TradingDecision(BaseModel):
    decision: TradingAction = Field(
        description="Final trading recommendation."
    )
    confidence: int = Field(
        ge=0,
        le=100,
        description="Confidence score from 0 to 100.",
    )
    entry_strategy: str = Field(
        description="Recommended entry approach and conditions."
    )
    stop_loss: str = Field(description="Stop loss level and rationale.")
    reasoning: str = Field(description="Explanation supporting the decision.")
    risks: str = Field(description="Key risks that could invalidate the decision.")
