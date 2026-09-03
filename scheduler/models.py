"""Phase 28 -- operational scheduling & continuous shadow mode.

A `RunRecord` is the audit trail of one scheduler-triggered execution
(one slot, one attempt). Append-only in intent: a run is INSERTed as
RUNNING, then exactly one later UPDATE sets finished_at/status/detail --
never a full rewrite, matching every other store in this project
(predictions/decisions/scans/research are all insert-then-append,
never mutate-in-place-repeatedly).

Two runs of the SAME slot on the SAME trading day are different
RunRecords with different `run_id`s -- idempotency ("did this slot
already run today") is a QUERY over this table (see
scheduler/store.py's `has_completed_today`), not a uniqueness
constraint on (slot_name, run_date), because an intraday slot is
legitimately allowed to run more than once per day (every
`frequency_minutes`).
"""

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class RunStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RECLAIMED = "RECLAIMED"
    """A RUNNING record whose process never reported back (crash, kill
    -9, power loss) -- reclaimed on a later tick/restart so the lock
    does not block forever. Distinct from FAILED (a run that started,
    executed, and raised) so an audit reader can tell "it broke" from
    "the process disappeared" apart at a glance."""


class SlotAction(str, Enum):
    SHADOW_RUN = "shadow_run"
    """Full scan -> research -> decide -> predict pass (evaluate/learn
    tail included unless the slot config says otherwise)."""
    EVALUATE_AND_LEARN = "evaluate_and_learn"
    """Only checks outstanding predictions against real subsequent data
    and prints the learning report -- no new scan/research/decide, for
    a post-market slot where a fresh BUY entry would be meaningless
    (the session is over)."""


class RunRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    slot_name: str
    run_date: str
    """IST calendar date (YYYY-MM-DD) this run belongs to -- NOT the UTC
    date of started_at, which can differ near midnight IST. Every
    idempotency/frequency check in scheduler/config.py keys off this
    field, never off started_at's own date."""
    started_at: datetime
    finished_at: datetime | None = None
    status: RunStatus
    detail: str = ""
    error: str | None = None

    @classmethod
    def new_id(cls) -> str:
        return uuid.uuid4().hex


class TickResult(BaseModel):
    """What one `scheduler.runner.run_tick` call actually did -- the
    return value both the CLI's `schedule tick` and `schedule loop`
    print from, and what tests assert against instead of scraping
    stdout."""

    model_config = ConfigDict(frozen=True)

    ran: bool
    reason: str
    """Always populated: either why nothing ran, or a short human-
    readable summary of what did."""
    slot_name: str | None = None
    run_id: str | None = None
    reclaimed_run_ids: tuple[str, ...] = ()
