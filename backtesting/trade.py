from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict

from strategy.signal import Side


class ExitReason(str, Enum):
    STOP = "STOP"
    TARGET = "TARGET"
    END_OF_DATA = "END_OF_DATA"
    # Phase (paper order fill lifecycle hardening) -- ONLY ever assigned by
    # PaperTradingEngine's own optional max_holding_bars force-close (see
    # paper/engine.py's _process_open_position), never by check_exit()
    # itself (backtesting/execution.py's check_exit only ever returns STOP
    # or TARGET) and never by the backtester (which only ever assigns
    # END_OF_DATA). predictions/tracker.py's own exit_reason == TARGET
    # check is unaffected -- it only ever sees check_exit()'s own STOP/
    # TARGET return value directly, never a caller-assigned override.
    EXPIRED = "EXPIRED"


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
