"""Phase 21 -- decision intelligence models.

CRITICAL SAFETY FRAMING: a Decision is a LABEL (BUY/WATCH/AVOID/EXIT/
NO_ACTION) plus recorded evidence and rationale. It is not an order, not
an authorization, and no code path in decision_engine/ touches paper/,
risk/'s order-approval path, or any broker adapter. Converting a BUY
label into an actual paper trade remains a separate, unchanged, entirely
manual step (the existing `paper`/`paper-live` commands) -- this package
only adds a new READ of existing evidence and a new WRITE of a labeled
opinion about it.

Roadmap acceptance criteria, enforced structurally rather than by
convention:
  - "No recommendation without recorded evidence": a Decision whose label
    is not NO_ACTION cannot be constructed without scanner_evidence (see
    the model_validator below) -- the same "type system forecloses it"
    posture as schemas.explanation.SignalExplanation and
    research.models.ResearchSummary.
  - "Decision is reproducible": the label always comes from
    decision_engine.rules.classify, a pure function of typed inputs and
    DecisionConfig -- no randomness, no LLM involvement in the label
    itself (the LLM, if used, only narrates -- see DecisionNarrative).
  - "Decision version is stored": every Decision records
    DecisionConfig.version_id() as config_version.
"""

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from market.context import MarketContext
from market_intelligence.models import CandidateScore
from research.models import ResearchReport


class DecisionLabel(str, Enum):
    BUY = "BUY"
    WATCH = "WATCH"
    AVOID = "AVOID"
    EXIT = "EXIT"
    NO_ACTION = "NO_ACTION"


class RiskContext(BaseModel):
    """Deliberately narrow: whether a position is already held, and the
    account's current losing-streak count. NOT account-level circuit
    breakers (kill switch, drawdown, daily-loss limits) -- those remain
    risk/engine.py's unchanged job at actual order-approval time, a
    separate stage from this recommendation label (roadmap's own pipeline
    diagram places "Risk Filter" AFTER "Decision Engine", not as
    something the decision engine itself enforces)."""

    model_config = ConfigDict(frozen=True)

    has_open_position: bool = False
    consecutive_losses: int = 0
    note: str | None = None

    @classmethod
    def unknown(cls) -> "RiskContext":
        return cls(
            has_open_position=False,
            consecutive_losses=0,
            note="No account/risk data supplied -- treated as no open position, no loss-streak context.",
        )


class DecisionNarrative(BaseModel):
    """The LLM's ONLY allowed output shape -- one field, narration only.
    Cannot hold a label, price, or evidence override; mirrors
    schemas.explanation.SignalExplanation and research.models.
    ResearchSummary's same type-level constraint."""

    model_config = ConfigDict(frozen=True)

    narrative: str = Field(description="Plain-language explanation of why this already-decided label was reached, using only the recorded rationale/evidence.")


class DecisionReview(BaseModel):
    """Phase 25 -- the LLM's ONLY allowed output shape for an independent
    critique of an already-fixed Decision (agents/decision_reviewer.py).
    Same "cannot change the decision" type-level guarantee as
    DecisionNarrative: no field here can hold a revised label, price, or
    action -- this is adversarial review, not narration, but the
    constraint is identical."""

    model_config = ConfigDict(frozen=True)

    concerns: list[str] = Field(description="Specific reasons this decision might be wrong, weak, or premature, each grounded in the recorded evidence -- not generic caution.")
    supporting_points: list[str] = Field(description="Specific reasons the recorded evidence genuinely supports this decision.")
    overall_assessment: str = Field(description="A short, balanced summary weighing the above. Cannot state or imply a different label.")


class Decision(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision_id: str
    symbol: str
    as_of: datetime
    """UTC-aware: when this decision was generated."""

    label: DecisionLabel
    rationale: list[str]
    """Deterministic reasons from decision_engine.rules.classify -- always
    present, always the actual basis for `label`, independent of whether
    an AI narrative was also generated."""
    config_version: str

    scanner_evidence: CandidateScore | None
    research_evidence: ResearchReport | None
    market_context: MarketContext | None
    risk_context: RiskContext

    confidence: float | None = None
    """Phase 34 -- decision_engine.confidence.compute_confidence's score
    (0.0-1.0): fraction of available scanner factors agreeing with this
    decision's own direction. Deterministic, never LLM-derived. None only
    for a Decision built before this field existed, or with no
    scanner_evidence at all (NO_ACTION)."""
    confidence_explanation: str | None = None
    """The same computation's own explanation() string -- which factors
    agreed/disagreed, in plain language. Always present when `confidence`
    is, for provenance."""

    narrative: str | None
    narrative_unavailable_reason: str | None

    @model_validator(mode="after")
    def _recommendation_requires_evidence(self) -> "Decision":
        if self.label != DecisionLabel.NO_ACTION and self.scanner_evidence is None:
            raise ValueError(
                f"A {self.label.value} decision must be backed by recorded scanner evidence -- "
                "NO_ACTION is the only label allowed with no scanner_evidence."
            )
        return self

    @classmethod
    def new_id(cls) -> str:
        return uuid.uuid4().hex
