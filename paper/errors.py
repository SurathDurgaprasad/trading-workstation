"""Phase 7A: structured errors for the continuous bar-ingestion path.
Kept separate from paper/engine.py the same way agents/errors.py and
llm/errors.py are split out from their respective modules in this project.
"""

from datetime import datetime


class OutOfOrderBarError(Exception):
    """Raised when a bar arrives with a timestamp strictly before the last
    bar already processed for that symbol (spec Phase 7A §7). Deliberately
    NOT raised for an exact repeat of the last timestamp — that case is a
    duplicate, handled as an idempotent no-op (BarOutcome.DUPLICATE_SKIPPED),
    not an error (spec §6 vs §7 are different situations: a benign resend
    vs. a genuine ordering fault)."""

    def __init__(self, *, symbol: str, incoming_timestamp: datetime, last_processed_timestamp: datetime):
        self.symbol = symbol
        self.incoming_timestamp = incoming_timestamp
        self.last_processed_timestamp = last_processed_timestamp
        super().__init__(
            f"Out-of-order bar for {symbol}: incoming timestamp {incoming_timestamp} is "
            f"before the last processed timestamp {last_processed_timestamp}."
        )


class InvalidPositionTransitionError(Exception):
    """Final-product-hardening: CLOSED is the position state machine's one
    terminal state (paper/models.py::PositionStatus is OPEN/CLOSED,
    closing is a one-way door -- there is no domain-supported path back
    to OPEN, and a position cannot be closed twice). Raised by
    PaperStore.update_position() when a mutation targets a position
    that is already CLOSED, rather than allowing a silent no-op or an
    unconditional overwrite. A caller reaching this has a real bug
    (e.g. two exit paths racing on the same position) worth surfacing
    loudly, not swallowing."""

    def __init__(self, *, position_id: str, attempted_status: str):
        self.position_id = position_id
        self.attempted_status = attempted_status
        super().__init__(
            f"Cannot update position {position_id!r}: it is already CLOSED "
            f"(attempted to set status={attempted_status!r}). CLOSED is a terminal state."
        )
