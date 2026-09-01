from pydantic import BaseModel, Field


class CriticAssessment(BaseModel):
    weak_assumptions: list[str] = Field(
        description="Weak or unsupported assumptions in the strategy."
    )
    hidden_risks: list[str] = Field(
        description="Risks not explicitly addressed by the strategy."
    )
    failure_scenarios: list[str] = Field(
        description="Scenarios where the strategy is likely to fail."
    )
    missing_rules: list[str] = Field(
        description="Rules or safeguards absent from the strategy."
    )
