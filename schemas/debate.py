from pydantic import BaseModel, Field


class DebateSummary(BaseModel):
    agreements: str = Field(
        description="Points where the technical, risk, and critic views align."
    )
    disagreements: str = Field(
        description="Points of conflict between expert assessments."
    )
    consensus: str = Field(
        description="Reconciled consensus view after resolving conflicts."
    )
