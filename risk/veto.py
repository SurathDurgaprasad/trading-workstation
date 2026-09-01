from enum import Enum


class VetoReason(str, Enum):
    """Every value here corresponds to a check actually implemented in
    risk/engine.py — no placeholder/future reasons."""

    INVALID_SIGNAL = "INVALID_SIGNAL"
    INVALID_STOP = "INVALID_STOP"
    INVALID_RISK_REWARD = "INVALID_RISK_REWARD"
    ZERO_POSITION_SIZE = "ZERO_POSITION_SIZE"
    INSUFFICIENT_CAPITAL = "INSUFFICIENT_CAPITAL"
    MAX_EXPOSURE = "MAX_EXPOSURE"
    MAX_DAILY_LOSS = "MAX_DAILY_LOSS"
    MAX_DRAWDOWN = "MAX_DRAWDOWN"
    CONSECUTIVE_LOSS_LIMIT = "CONSECUTIVE_LOSS_LIMIT"
    POSITION_ALREADY_OPEN = "POSITION_ALREADY_OPEN"
