"""Weekend hardening, Phase 7 (strategy edge validation) -- a strategy's
own PerformanceMetrics mean nothing in isolation: a negative-PnL period
could still beat a market that fell further, and a positive-PnL period
could still lose to simply buying and holding. This module answers the
mission's explicit demand ("Compare against BUY_AND_HOLD baseline where
relevant") with the simplest possible baseline a real investor could have
achieved with ZERO strategy logic at all: buy at the first available
bar's open, hold to the last bar's close, no re-entry, no risk
management, no stop/target.

Deliberately not a second competing engine: reuses backtesting.equity.
build_equity_curve for the exact same drawdown definition the strategy's
own report already uses, so the two numbers are genuinely comparable
(not two different drawdown methodologies dressed up as "the same
metric"). Marked to market on every bar (not just per-trade, since
buy-and-hold has no "trades") -- a strictly MORE granular curve than the
strategy's own, so its drawdown is never understated relative to the
strategy's.
"""

import pandas as pd
from pydantic import BaseModel, ConfigDict

from backtesting.equity import build_equity_curve


class BuyAndHoldResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    period_label: str
    entry_price: float
    exit_price: float
    quantity: int
    initial_capital: float
    final_equity: float
    net_pnl: float
    return_pct: float
    max_drawdown_pct: float


def compute_buy_and_hold(
    indicator_series: pd.DataFrame, *, symbol: str, initial_capital: float = 100_000.0, period_label: str = "full",
) -> BuyAndHoldResult | None:
    """None only when the series is empty, or the first bar's open price
    alone exceeds the entire available capital (cannot buy even one
    share) -- never a fabricated zero-trade result standing in for a
    genuine "cannot compute" case, matching this project's own
    "never fabricate" discipline used throughout every other get_*/
    compute_* function in the codebase."""
    if indicator_series.empty:
        return None

    entry_price = float(indicator_series.iloc[0]["open"])
    if entry_price <= 0:
        return None
    quantity = int(initial_capital // entry_price)
    if quantity <= 0:
        return None

    trade_equities = [
        (timestamp, quantity * float(row["close"])) for timestamp, row in indicator_series.iterrows()
    ]
    equity_curve = build_equity_curve(
        start_time=indicator_series.index[0], initial_capital=initial_capital, trade_equities=trade_equities,
    )
    max_drawdown_pct = max((p.drawdown_pct for p in equity_curve), default=0.0)

    exit_price = float(indicator_series.iloc[-1]["close"])
    final_equity = quantity * exit_price
    net_pnl = final_equity - quantity * entry_price
    return_pct = (exit_price / entry_price - 1.0) * 100.0

    return BuyAndHoldResult(
        symbol=symbol, period_label=period_label, entry_price=entry_price, exit_price=exit_price,
        quantity=quantity, initial_capital=initial_capital, final_equity=final_equity,
        net_pnl=net_pnl, return_pct=return_pct, max_drawdown_pct=max_drawdown_pct,
    )
