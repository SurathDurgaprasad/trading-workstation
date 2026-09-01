from datetime import datetime

from pydantic import BaseModel, ConfigDict

from risk.veto import VetoReason
from strategy.signal import Signal


class PositionSize(BaseModel):
    model_config = ConfigDict(frozen=True)

    quantity: int
    risk_per_unit: float
    total_risk: float
    notional_value: float


class Exposure(BaseModel):
    model_config = ConfigDict(frozen=True)

    position_notional: float
    account_equity: float
    exposure_pct: float


class RiskDecision(BaseModel):
    """The sole authority on whether a signal becomes a trade. `approved`
    is the only field the execution engine acts on; every other field is
    for observability (see risk/observability's aggregate reporting) — the
    engine never approves on missing/ambiguous data (see risk/engine.py's
    fail-closed structure: any veto reason present forces approved=False)."""

    model_config = ConfigDict(frozen=True)

    approved: bool
    position_size: PositionSize | None
    risk_amount: float | None
    risk_percent: float | None
    exposure: Exposure | None
    veto_reasons: list[VetoReason]
    explanation: str
    risk_reduced: bool = False  # True when sized at consecutive_loss_risk_multiplier, not the full risk_per_trade_pct

    # Account-state snapshot AT THE MOMENT of this decision (Phase 4.5 audit
    # trail, spec §13) — lets a future trade journal answer "why didn't the
    # strategy trade here?" without needing to replay the whole backtest.
    account_equity: float
    current_drawdown_pct: float
    daily_pnl: float
    consecutive_losses: int

    # The quantity risk sizing wanted BEFORE any capital-availability
    # reduction, vs. what was actually approved (0 if rejected). Distinct
    # numbers whenever INSUFFICIENT_CAPITAL reduced (rather than fully
    # zeroed) the size.
    requested_quantity: int
    approved_quantity: int


class SignalRecord(BaseModel):
    """One row per signal the strategy generated, whether approved or
    rejected — the observability requirement in spec §20."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    symbol: str
    signal: Signal
    decision: RiskDecision


class RiskSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    signals_generated: int
    signals_approved: int
    signals_rejected: int
    rejections_by_reason: dict[VetoReason, int]
    average_risk_amount: float | None
    maximum_risk_amount: float | None
    signals_risk_reduced: int  # approved AND sized at consecutive_loss_risk_multiplier
