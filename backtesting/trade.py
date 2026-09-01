from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict

from strategy.signal import Side


class ExitReason(str, Enum):
    STOP = "STOP"
    TARGET = "TARGET"
    END_OF_DATA = "END_OF_DATA"


class Trade(BaseModel):
    """A closed position — the deterministic engine's atomic record of what
    actually happened. Never touched by the LLM layer (see agents/*)."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    side: Side
    strategy_name: str
    signal_generated_at: datetime

    entry_time: datetime
    entry_price: float
    quantity: int
    stop_price: float
    target_price: float

    exit_time: datetime
    exit_price: float
    exit_reason: ExitReason

    gross_pnl: float
    costs: float
    net_pnl: float
    r_multiple: float
