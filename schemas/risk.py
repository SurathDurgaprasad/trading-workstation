from pydantic import BaseModel, Field


class RiskAssessment(BaseModel):
    position_sizing: str = Field(
        description="Recommended position size relative to capital."
    )
    risk_reward: str = Field(description="Risk/reward ratio assessment.")
    stop_loss: str = Field(description="Stop loss placement and rationale.")
    capital_protection: str = Field(
        description="Measures to protect capital under adverse conditions."
    )
