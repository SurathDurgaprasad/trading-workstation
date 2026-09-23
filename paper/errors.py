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


class InvalidOrderTransitionError(Exception):
    """Autonomous hardening cycle: same rationale as
    InvalidPositionTransitionError, for PaperOrder. OrderStatus is
    PENDING/FILLED (paper/models.py) -- FILLED is terminal, there is no
    domain-supported path back to PENDING, and an order cannot be
    filled twice. Today's ONLY caller (paper/engine.py's
    _fill_pending_order) is already protected against a double-fill by
    process_bar's own transaction wrapping + get_pending_order's
    status='PENDING' filter (a second concurrent caller would see the
    order as already FILLED and never reach update_order for it at
    all) -- this guard is deliberate defense-in-depth at the data
    layer, matching the exact same posture PaperStore.update_position
    already takes, so a FUTURE caller (not just today's one) cannot
    silently corrupt an order's terminal state either."""

    def __init__(self, *, order_id: str, attempted_status: str):
        self.order_id = order_id
        self.attempted_status = attempted_status
        super().__init__(
            f"Cannot update order {order_id!r}: it is already FILLED "
            f"(attempted to set status={attempted_status!r}). FILLED is a terminal state."
        )


class DuplicateTradeForPositionError(Exception):
    """Continuous red-team follow-up, 2026-09-23 (G14, docs/MASTER_KNOWN_ISSUES.md):
    a position closes into a Trade at most once -- previously relied
    entirely on application discipline (a single call site,
    PaperTradingEngine._close_position, plus store.transaction()'s own
    atomicity) with no schema-level backstop, unlike every OTHER
    terminal-state transition in this project (Position/PaperOrder both
    raise a typed error via PaperStore.update_position/update_order).
    Raised by PaperStore.save_trade() when the DB-level
    UNIQUE(position_id) index (see
    PaperStore._migrate_trades_unique_position_id_index) is active and a
    second trade for the same position_id is attempted -- mirroring
    predictions/store.py's own DuplicatePredictionError pattern exactly.
    If the constraint is not active (a pre-existing database with
    unresolved historical duplicates), this is never raised, matching
    the prior behavior exactly."""

    def __init__(self, *, position_id: str):
        self.position_id = position_id
        super().__init__(
            f"Cannot save a trade for position {position_id!r}: a trade for this position already exists. "
            "A position may close into a Trade at most once."
        )
