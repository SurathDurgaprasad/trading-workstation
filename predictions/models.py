"""Phase 23 -- shadow prediction models.

Roadmap section 7 ("Continuous Prediction and Learning System"): every
meaningful recommendation is recorded as a prediction, and the system
keeps monitoring it whether or not the user acts on it. Section 7.3
suggests ten outcome states; this phase's evaluation logic (predictions/
tracker.py) can only honestly PRODUCE five of them from real subsequent
market data -- ACTIVE, TARGET_HIT, STOP_HIT, EXPIRED, INSUFFICIENT_DATA.
The other five are recognized (a typo or an unhandled future state fails
clearly) but never produced this phase, for stated reasons:
  - MISSED_ENTRY assumes a limit-style order that may never fill; every
    prediction here is entered immediately at the sizing bar's own close
    (risk.sizing.build_signal_for_buy), so entry is never "missed."
  - INVALIDATED / PARTIAL_SUCCESS / CANCELLED all require a judgment call
    (was the original thesis invalidated? was a partial exit a
    "success"?) this project has no evidence-based rule for yet -- the
    same "recognized future extension, never silently faked" posture
    market_data.universe.py already applies to unimplemented NIFTY modes.

Immutability, matching roadmap section 13's own principle: a
PredictionRecord is never updated in place. What happens to it later is
written as a SEPARATE PredictionEvaluation row referencing it by ID --
predictions/store.py has no update_prediction/update_evaluation method
at all.
"""

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from decision_engine.models import DecisionLabel
from risk.contracts import RiskDecision


class PredictionOutcomeState(str, Enum):
    ACTIVE = "ACTIVE"
    TARGET_HIT = "TARGET_HIT"
    STOP_HIT = "STOP_HIT"
    EXPIRED = "EXPIRED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

    # Recognized per the roadmap's own suggested state list (section 7.3)
    # but not produced by this phase's evaluation logic -- see the module
    # docstring above for why each one is deferred, not implemented.
    PENDING = "PENDING"
    INVALIDATED = "INVALIDATED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    MISSED_ENTRY = "MISSED_ENTRY"
    CANCELLED = "CANCELLED"


RESOLVED_STATES = (PredictionOutcomeState.TARGET_HIT, PredictionOutcomeState.STOP_HIT)


class PredictionRecord(BaseModel):
    """Immutable. entry_price/stop_price/target_price come directly from a
    risk.sizing.build_signal_for_buy-produced Signal -- this module never
    re-derives stop/target math of its own."""

    model_config = ConfigDict(frozen=True)

    prediction_id: str
    decision_id: str
    symbol: str
    created_at: datetime
    """UTC-aware: when this prediction was recorded."""
    label: DecisionLabel
    """Always BUY this phase -- see predictions/tracker.py's create_prediction."""

    entry_price: float
    stop_price: float
    target_price: float
    entry_time: datetime
    """The bar this was sized against (Signal.generated_at) -- monitoring
    only ever looks at bars strictly after this timestamp."""

    horizon_bars: int
    interval: str

    risk_decision: RiskDecision | None = None
    """Mission requirement (auditability §15 -- "TRADE PLAN: entry, stop,
    target, quantity, capital, risk amount... persistent structured
    records are required, not logs"): the FULL risk.sizing.size_decision()
    output computed at prediction time, when the caller supplied capital/
    risk-config to compute one (predict/shadow-run's optional
    --initial-capital et al). None for any prediction recorded WITHOUT
    that info (the historical default, and still fully valid -- a
    prediction's price-level correctness is independent of what capital
    was configured when it was recorded) -- never fabricated, never
    backfilled onto an existing row. Reuses risk.contracts.RiskDecision
    verbatim rather than inventing a second, competing "sizing record"
    shape."""

    @model_validator(mode="after")
    def _prices_must_be_sanely_ordered(self) -> "PredictionRecord":
        """Phase 36 audit finding: nothing previously stopped a
        PredictionRecord from being constructed with a degenerate price
        ordering (e.g. stop_price >= entry_price) -- the invariant held
        only because risk.sizing.build_signal_for_buy's own upstream
        guards happened to always produce a sane Signal. Enforced here
        too, structurally, so a future caller that builds a
        PredictionRecord any other way cannot silently produce a
        nonsensical shadow prediction (a "stop" above entry, or a
        "target" below entry) -- fail closed at construction time, the
        same "type system forecloses it" posture Decision's own
        model_validator already applies to evidence-backed labels."""
        if not (self.stop_price < self.entry_price < self.target_price):
            raise ValueError(
                f"Degenerate price ordering for a BUY prediction: stop_price={self.stop_price:.4f}, "
                f"entry_price={self.entry_price:.4f}, target_price={self.target_price:.4f} -- "
                "a long prediction requires stop_price < entry_price < target_price."
            )
        return self

    @classmethod
    def new_id(cls) -> str:
        return uuid.uuid4().hex


class PredictionEvaluation(BaseModel):
    """A separate, later-appended row -- never a mutation of
    PredictionRecord. Re-evaluating an ACTIVE prediction later adds
    ANOTHER row, not an update to this one; predictions/store.py's
    latest_evaluation_for_prediction reads the newest by evaluated_at."""

    model_config = ConfigDict(frozen=True)

    evaluation_id: str
    prediction_id: str
    evaluated_at: datetime
    """UTC-aware: when this evaluation was computed (not a bar timestamp)."""

    outcome: PredictionOutcomeState
    bars_observed: int
    exit_time: datetime | None
    exit_price: float | None
    actual_return: float | None
    """(exit_price / entry_price - 1) once resolved (TARGET_HIT/STOP_HIT); None otherwise."""
    max_favorable_excursion: float | None
    """Best fractional move in the predicted direction observed so far (e.g. 0.05 = +5%)."""
    max_adverse_excursion: float | None
    """Worst fractional move against the prediction observed so far, as a positive magnitude."""
    detail: str

    @classmethod
    def new_id(cls) -> str:
        return uuid.uuid4().hex


class PredictionSummary(BaseModel):
    """Roadmap's target long-term architecture places basic "evaluation"
    and "performance metrics" under predictions/ itself, distinct from
    the separate future learning/ package's cross-strategy comparison and
    confidence calibration (roadmap Phase 24) -- this is that basic,
    Level-1-only tracking (win rate / average return / profit factor),
    deliberately not strategy comparison or calibration."""

    model_config = ConfigDict(frozen=True)

    total_predictions: int
    active: int
    target_hit: int
    stop_hit: int
    expired: int
    insufficient_data: int

    win_rate: float | None = Field(description="target_hit / (target_hit + stop_hit); None if nothing has resolved yet.")
    average_return: float | None = Field(description="Mean actual_return over resolved (TARGET_HIT/STOP_HIT) evaluations; None if none resolved.")
    profit_factor: float | None = Field(
        description="Sum of positive resolved returns / abs(sum of negative resolved returns); "
        "None if nothing resolved or there are no losing predictions to divide by."
    )
