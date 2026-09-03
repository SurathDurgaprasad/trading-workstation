"""Phase 20 -- research intelligence models.

Roadmap's own critical requirement: "Every AI conclusion must include
Evidence, Source, Timestamp, Confidence, Unknowns." ResearchReport is
structured to make that requirement structural, not a prompt instruction
an LLM could ignore:
  - Evidence + Source + Timestamp: every NewsItem carries its own
    `source` and `published_at`, always populated BEFORE any LLM call --
    the AI never invents evidence, it only narrates what is already here.
  - Confidence + Unknowns: ResearchSummary's only two non-narrative
    fields, mirroring schemas/explanation.py's SignalExplanation --
    deliberately no field exists for a price, action, or recommendation,
    so the type system itself forecloses that, not just a prompt.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NewsItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    summary: str
    source: str
    url: str | None
    published_at: datetime
    """UTC-aware -- parsed from the source's own publish timestamp."""


class SectorInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    sector: str | None
    industry: str | None
    as_of: datetime
    """UTC-aware: when this classification was looked up -- sector/industry
    labels can be reclassified over time, this is not asserted as permanent."""


class ResearchSummary(BaseModel):
    """The LLM's ONLY allowed output shape. No entry/stop/target/quantity/
    action field exists here -- same type-level constraint as
    schemas.explanation.SignalExplanation."""

    model_config = ConfigDict(frozen=True)

    summary: str = Field(description="Plain-language synthesis of the evidence given, and only that evidence.")
    confidence: float = Field(ge=0, le=1, description="Confidence that the evidence is substantive and relevant -- not confidence in a trading outcome.")
    unknowns: list[str] = Field(description="Important questions this evidence does not answer.")


class ResearchReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    report_id: str
    symbol: str
    as_of: datetime
    """UTC-aware: when this report was generated -- see the same
    real-vs-construction-time distinction documented on
    market_data.models.InstrumentSnapshot.as_of."""

    news: list[NewsItem]
    sector: SectorInfo | None
    ai_summary: ResearchSummary | None
    ai_summary_unavailable_reason: str | None

    @classmethod
    def new_id(cls) -> str:
        return uuid.uuid4().hex
