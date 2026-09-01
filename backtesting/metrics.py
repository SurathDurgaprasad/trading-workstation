from pydantic import BaseModel, ConfigDict

from backtesting.equity import EquityPoint
from backtesting.trade import Trade


class PerformanceMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float

    gross_pnl: float
    total_costs: float
    net_pnl: float

    average_trade: float
    average_winner: float | None
    average_loser: float | None
    profit_factor: float | None  # None = no losing trades, ratio is undefined (not infinite)

    average_r: float | None  # == expectancy in R, per the blueprint's own "expectancy > 0.25R" framing
    expectancy: float | None

    largest_win: float | None
    largest_loss: float | None
    max_consecutive_losses: int
    max_drawdown_pct: float


def compute_performance_metrics(
    trades: list[Trade], equity_curve: list[EquityPoint]
) -> PerformanceMetrics:
    total_trades = len(trades)
    winners = [t for t in trades if t.net_pnl > 0]
    losers = [t for t in trades if t.net_pnl < 0]

    gross_pnl = sum(t.gross_pnl for t in trades)
    total_costs = sum(t.costs for t in trades)
    net_pnl = sum(t.net_pnl for t in trades)

    gross_profit = sum(t.net_pnl for t in winners)
    gross_loss = abs(sum(t.net_pnl for t in losers))

    win_rate_pct = (len(winners) / total_trades * 100) if total_trades else 0.0
    average_trade = (net_pnl / total_trades) if total_trades else 0.0
    average_winner = (gross_profit / len(winners)) if winners else None
    average_loser = (-gross_loss / len(losers)) if losers else None
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

    r_multiples = [t.r_multiple for t in trades]
    average_r = (sum(r_multiples) / len(r_multiples)) if r_multiples else None
    expectancy = average_r  # mean R-multiple across all trades

    largest_win = max((t.net_pnl for t in winners), default=None)
    largest_loss = min((t.net_pnl for t in losers), default=None)

    max_consecutive_losses = _max_consecutive_losses(trades)
    max_drawdown_pct = max((p.drawdown_pct for p in equity_curve), default=0.0)

    return PerformanceMetrics(
        total_trades=total_trades,
        winning_trades=len(winners),
        losing_trades=len(losers),
        win_rate_pct=win_rate_pct,
        gross_pnl=gross_pnl,
        total_costs=total_costs,
        net_pnl=net_pnl,
        average_trade=average_trade,
        average_winner=average_winner,
        average_loser=average_loser,
        profit_factor=profit_factor,
        average_r=average_r,
        expectancy=expectancy,
        largest_win=largest_win,
        largest_loss=largest_loss,
        max_consecutive_losses=max_consecutive_losses,
        max_drawdown_pct=max_drawdown_pct,
    )


def _max_consecutive_losses(trades: list[Trade]) -> int:
    longest = current = 0
    for trade in trades:
        if trade.net_pnl < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest
