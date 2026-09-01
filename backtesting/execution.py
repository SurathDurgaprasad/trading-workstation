"""The deterministic fill/exit model — extracted from backtesting/engine.py
in Phase 6 so it can be shared, unduplicated, between the backtester and
paper/engine.py. Was previously private to engine.py (`_check_exit` etc.);
promoted to a public module because it now has two real callers.

Nothing here changed behaviorally — same conservative same-bar-ambiguity
rule (stop wins), same cost/slippage application, same Trade construction.
"""

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from backtesting.costs import CostModel
from backtesting.trade import ExitReason, Trade
from strategy.signal import Signal

EXECUTION_MODEL_VERSION = "1.0"


@dataclass
class OpenPosition:
    signal: Signal
    entry_time: datetime
    entry_price: float
    quantity: int
    stop_price: float
    target_price: float


def check_exit(position: OpenPosition, bar: pd.Series) -> tuple[float, ExitReason] | None:
    """Conservative same-bar-ambiguity rule: if a single bar's high/low range
    could have hit both stop and target and we cannot know the intrabar
    order, assume the stop was hit first."""
    high, low = float(bar["high"]), float(bar["low"])
    hit_stop = low <= position.stop_price
    hit_target = high >= position.target_price

    if hit_stop:
        return position.stop_price, ExitReason.STOP
    if hit_target:
        return position.target_price, ExitReason.TARGET
    return None


def close_trade(
    position: OpenPosition,
    *,
    exit_price: float,
    exit_time: datetime,
    exit_reason: ExitReason,
    symbol: str,
    cost_model: CostModel,
) -> Trade:
    entry_notional = position.entry_price * position.quantity
    exit_notional = exit_price * position.quantity

    gross_pnl = (exit_price - position.entry_price) * position.quantity
    costs = cost_model.cost_for_fill(notional=entry_notional) + cost_model.cost_for_fill(notional=exit_notional)
    net_pnl = gross_pnl - costs

    initial_risk = (position.entry_price - position.stop_price) * position.quantity
    r_multiple = net_pnl / initial_risk if initial_risk > 0 else 0.0

    return Trade(
        symbol=symbol,
        side=position.signal.side,
        strategy_name=position.signal.strategy_name,
        signal_generated_at=position.signal.generated_at,
        entry_time=position.entry_time,
        entry_price=position.entry_price,
        quantity=position.quantity,
        stop_price=position.stop_price,
        target_price=position.target_price,
        exit_time=exit_time,
        exit_price=exit_price,
        exit_reason=exit_reason,
        gross_pnl=gross_pnl,
        costs=costs,
        net_pnl=net_pnl,
        r_multiple=r_multiple,
    )


def bar_day(timestamp):
    """Trading-day boundary is the bar's own timestamp date, in whatever
    timezone the data provider returns it — never the host machine's clock."""
    return pd.Timestamp(timestamp).date()
