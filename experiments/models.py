"""Phase 37 -- experiment tracking.

An Experiment is a NAMED, REGISTERED record of "I am deliberately running
this configuration, starting now, for this reason" -- distinct from the
config's own deterministic version_id (decision_engine.config.
DecisionConfig.version_id / market_intelligence.config.ScannerConfig.
version_id / risk.config.RiskConfig.version_id all already exist and are
reused here unchanged, never re-derived). Without a registry, "which
config versions were deliberately tried, when, and why" could only be
inferred after the fact from decision history -- this makes that
deliberate.

Same append-only, two-table pattern predictions/store.py already
established: `experiments` is written once per experiment and never
updated; what happens to it later (ended, annotated) is always a NEW
row in `experiment_events`, referencing the original by experiment_id.
Current status (ongoing vs. ended) is DERIVED from the latest event,
never stored as a mutable field -- "never overwrite historical
performance," the roadmap's own rule for this phase, applied here to
the experiment's own record too.
"""

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class ConfigType(str, Enum):
    """Which of this project's existing, unmodified versioned configs
    this experiment is tracking -- not a new config system of its own."""

    DECISION_ENGINE = "decision_engine"
    SCANNER = "scanner"
    RISK = "risk"


class ExperimentEventType(str, Enum):
    STARTED = "STARTED"
    ENDED = "ENDED"
    NOTE = "NOTE"


class Experiment(BaseModel):
    """Immutable. `config_version` is copied from the relevant existing
    config's own `.version_id()` at registration time -- never
    recomputed or re-derived later, so a comparison always groups by
    exactly the version that was actually in effect during this
    experiment's window."""

    model_config = ConfigDict(frozen=True)

    experiment_id: str
    name: str
    description: str
    config_type: ConfigType
    config_version: str
    started_at: datetime
    """UTC-aware: the experiment's own declared start of its dataset/time
    boundary -- predictions created before this are never attributed to
    this experiment, even if they happen to share the same config_version
    (e.g. a config re-used in an earlier, separately-registered run)."""

    @classmethod
    def new_id(cls) -> str:
        return uuid.uuid4().hex


class ExperimentEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    experiment_id: str
    event_type: ExperimentEventType
    occurred_at: datetime
    detail: str = ""

    @classmethod
    def new_id(cls) -> str:
        return uuid.uuid4().hex
