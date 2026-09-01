from pydantic import BaseModel, Field


class SignalExplanation(BaseModel):
    """The LLM's ONLY allowed output shape when narrating a deterministic
    Signal/RiskDecision. Deliberately has no entry/stop/target/quantity/PnL
    field — the type system itself makes mutation of those impossible, not
    just a prompt instruction the model could ignore."""

    supporting_evidence: list[str] = Field(description="Observed data points consistent with the signal/decision.")
    contradicting_evidence: list[str] = Field(description="Observed data points that argue against it.")
    narrative: str = Field(description="A short, plain-language explanation of why this decision was made.")
