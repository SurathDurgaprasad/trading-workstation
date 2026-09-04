"""Deterministic decision critic -- structured result models.

Sits between decision_engine (TRADE PROPOSAL) and risk (RISK ENGINE) in
the pipeline: decision_engine.rules.classify decides BUY/WATCH/AVOID
from scanner evidence alone; this package independently re-examines an
already-proposed BUY against evidence classify() never looks at (market
context indicators, data freshness, regime, existing exposure, kill
switch) and can veto or downgrade paper execution before risk.engine
ever sizes it.

Distinct from agents/critic_agent.py (the older LLM "devil's advocate"
in the analyze/ LangGraph pipeline): that one only ever produces prose
for a human to read and has no authority over anything. Everything here
is pure, deterministic Python -- no LLM, no I/O, no randomness -- and
its verdict has real authority (see critic/engine.py's evaluate()).
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict


class CriticVerdict(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    DOWNGRADE = "DOWNGRADE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class CriticCheckSeverity(str, Enum):
    HARD = "HARD"
    """A failure here is disqualifying on its own -- drives REJECT."""
    WARNING = "WARNING"
    """A failure here is a concern, not disqualifying alone -- enough of
    them accumulated drives DOWNGRADE (see CriticConfig.downgrade_warning_threshold)."""


class CriticCheckName(str, Enum):
    """Every value here corresponds to a check actually implemented in
    critic/engine.py -- no placeholder/future reasons (same posture
    risk/veto.py's VetoReason documents for itself)."""

    KILL_SWITCH = "KILL_SWITCH"
    FUTURE_TIMESTAMP = "FUTURE_TIMESTAMP"
    DATA_FRESHNESS = "DATA_FRESHNESS"
    TRADE_STRUCTURE = "TRADE_STRUCTURE"
    DUPLICATE_EXPOSURE = "DUPLICATE_EXPOSURE"
    EVIDENCE_COMPLETENESS_SCANNER = "EVIDENCE_COMPLETENESS_SCANNER"
    EVIDENCE_COMPLETENESS_MARKET_CONTEXT = "EVIDENCE_COMPLETENESS_MARKET_CONTEXT"
    EVIDENCE_COMPLETENESS_RESEARCH = "EVIDENCE_COMPLETENESS_RESEARCH"
    VOLUME_CONFIRMATION = "VOLUME_CONFIRMATION"
    INDICATOR_CONTRADICTION = "INDICATOR_CONTRADICTION"
    REGIME_CONFLICT = "REGIME_CONFLICT"
    RISK_REWARD = "RISK_REWARD"
    CONFIDENCE_INTEGRITY = "CONFIDENCE_INTEGRITY"


class CriticCheck(BaseModel):
    """One named check's outcome. Always recorded, whether it ran or
    not -- `evaluated=False` (never a silently-omitted row) is how an
    unavailable input (e.g. no benchmark_context supplied) is told apart
    from a genuinely passing check, matching this project's "never
    fabricate, an absent input is never treated as a pass" discipline
    (market_intelligence.regime.SectorStrength's empty-tuple-not-guessed
    posture, decision_engine.confidence's unavailable_factors, etc.)."""

    model_config = ConfigDict(frozen=True)

    name: CriticCheckName
    evaluated: bool
    passed: bool
    """Meaningless when evaluated is False -- always True in that case,
    by convention, so a check that never ran can never accidentally be
    counted as a failure."""
    severity: CriticCheckSeverity
    detail: str


class CriticAssessment(BaseModel):
    """The critic's full, structured, auditable output. Every check run
    is included, pass or fail, evaluated or not -- `failed_checks`/
    `warnings` are a derived convenience view over `checks`, not a
    separate source of truth."""

    model_config = ConfigDict(frozen=True)

    verdict: CriticVerdict
    checks: tuple[CriticCheck, ...]
    failed_checks: tuple[str, ...]
    """CriticCheckName values for evaluated=True, passed=False, HARD-severity checks."""
    warnings: tuple[str, ...]
    """CriticCheckName values for evaluated=True, passed=False, WARNING-severity checks."""
    reasons: tuple[str, ...]
    """Human-readable summary of what actually drove the verdict."""
    config_version: str
