"""New models this phase, and why each one is genuinely new rather than a
duplicate of something that already exists (spec §1/step 1's forensic
requirement):

- Signal, RiskDecision, Account, Trade are REUSED as-is (strategy.signal,
  risk.contracts, risk.account, backtesting.trade) — none are redefined here.
- PaperOrder is new because nothing in the backtester ever represents a
  "signal was approved, but the fill price isn't known yet" state — the
  backtester has the whole DataFrame upfront and computes entry/exit
  synchronously in one loop iteration. Paper trading is a two-phase process
  (order now, fill on the next bar) precisely because it does NOT have
  tomorrow's bar yet — even in historical replay, this phase models it that
  way on purpose, to match how live/streaming operation will actually work.
- PaperFill is new because Trade (backtesting.trade.Trade) only exists at
  CLOSE time, bundling entry+exit into one record. Paper trading needs the
  entry fill and exit fill as separate, individually-persisted events before
  they're combined into a closed Trade.
- Position is new: the backtester's OpenPosition (backtesting.execution) is
  an in-memory dataclass, never persisted, never queried by symbol. Phase 6
  needs a persisted, queryable "what's open right now" record.
- JournalEntry is new: nothing else answers "what happened to signal X and
  why" as a single addressable row. It stores IDs (signal_id,
  risk_decision_id, order_id, position_id, trade_id), not copies of the
  objects themselves (spec §12 — "preserve references, don't duplicate").
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict

from backtesting.trade import ExitReason
from strategy.signal import Side


class OrderStatus(str, Enum):
    PENDING = "PENDING"  # approved by risk, awaiting the next bar's open to fill
    FILLED = "FILLED"


class PaperOrder(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: str
    signal_id: str
    symbol: str
    side: Side
    quantity: int
    requested_price: float  # the signal's reference_price — informational, never the fill price
    order_type: str = "MARKET"  # only market orders are implemented; no LIMIT/STOP order types exist
    status: OrderStatus
    created_at: datetime
    stop_price: float
    target_price: float


class FillKind(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


class PaperFill(BaseModel):
    model_config = ConfigDict(frozen=True)

    fill_id: str
    order_id: str
    symbol: str
    quantity: int
    fill_price: float
    fees: float
    slippage_amount: float
    timestamp: datetime
    fill_kind: FillKind


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class Position(BaseModel):
    """Persisted, queryable-by-symbol open/closed position. Distinct from
    backtesting.execution.OpenPosition (an in-memory-only dataclass used
    inside one run_backtest() call) — this one survives a restart."""

    model_config = ConfigDict(frozen=True)

    position_id: str
    symbol: str
    status: PositionStatus
    signal_id: str
    entry_order_id: str
    entry_fill_id: str
    entry_time: datetime
    entry_price: float
    quantity: int
    stop_price: float
    target_price: float
    exit_fill_id: str | None = None
    exit_time: datetime | None = None
    exit_price: float | None = None
    exit_reason: ExitReason | None = None
    trade_id: str | None = None


class JournalOutcome(str, Enum):
    REJECTED = "REJECTED"
    SKIPPED_ALREADY_ACTIVE = "SKIPPED_ALREADY_ACTIVE"  # risk said approved, but a position/order was already active for this symbol
    APPROVED_PENDING = "APPROVED_PENDING"
    APPROVED_FILLED_OPEN = "APPROVED_FILLED_OPEN"
    APPROVED_FILLED_CLOSED = "APPROVED_FILLED_CLOSED"


class JournalEntry(BaseModel):
    """One row per signal, evolving as the signal's outcome becomes known.
    References IDs into the other tables rather than embedding full copies
    of Signal/RiskDecision/Position/Trade (spec §12)."""

    model_config = ConfigDict(frozen=True)

    journal_entry_id: str
    signal_id: str
    symbol: str
    risk_decision_id: str
    order_id: str | None
    position_id: str | None
    trade_id: str | None
    outcome: JournalOutcome
    strategy_name: str
    strategy_version: str
    risk_config_version: str
    execution_model_version: str
    created_at: datetime
    updated_at: datetime
