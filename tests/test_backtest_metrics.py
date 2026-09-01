import math
from datetime import datetime, timedelta

from backtesting.equity import build_equity_curve
from backtesting.metrics import compute_performance_metrics
from backtesting.trade import ExitReason, Trade
from strategy.signal import Side


def _trade(net_pnl: float, *, gross_pnl: float | None = None, costs: float = 0.0, r: float = 0.0, day: int = 0) -> Trade:
    t0 = datetime(2026, 1, 1) + timedelta(days=day)
    return Trade(
        symbol="TEST",
        side=Side.LONG,
        strategy_name="unit-test",
        signal_generated_at=t0,
        entry_time=t0,
        entry_price=100.0,
        quantity=1,
        stop_price=90.0,
        target_price=110.0,
        exit_time=t0 + timedelta(days=1),
        exit_price=100.0 + net_pnl,
        exit_reason=ExitReason.TARGET if net_pnl > 0 else ExitReason.STOP,
        gross_pnl=gross_pnl if gross_pnl is not None else net_pnl,
        costs=costs,
        net_pnl=net_pnl,
        r_multiple=r,
    )


def test_known_trade_sequence_produces_exact_metrics():
    # 3 winners of +100 (r=+2), 2 losers of -50 (r=-1). Known by construction.
    trades = [
        _trade(100.0, r=2.0, day=0),
        _trade(100.0, r=2.0, day=2),
        _trade(-50.0, r=-1.0, day=4),
        _trade(100.0, r=2.0, day=6),
        _trade(-50.0, r=-1.0, day=8),
    ]
    equity_curve = build_equity_curve(
        start_time=datetime(2026, 1, 1),
        initial_capital=10_000.0,
        trade_equities=_running_equity(trades, start=10_000.0),
    )

    metrics = compute_performance_metrics(trades, equity_curve)

    assert metrics.total_trades == 5
    assert metrics.winning_trades == 3
    assert metrics.losing_trades == 2
    assert math.isclose(metrics.win_rate_pct, 60.0)
    assert math.isclose(metrics.net_pnl, 300.0 - 100.0)  # 3*100 - 2*50 = 200.0
    assert math.isclose(metrics.gross_pnl, 200.0)
    assert math.isclose(metrics.average_trade, 200.0 / 5)
    assert math.isclose(metrics.average_winner, 100.0)
    assert math.isclose(metrics.average_loser, -50.0)
    # profit factor = gross profit / gross loss = 300 / 100 = 3.0
    assert math.isclose(metrics.profit_factor, 3.0)
    # expectancy / average R = mean([2, 2, -1, 2, -1]) = 4/5 = 0.8
    assert math.isclose(metrics.expectancy, 0.8)
    assert math.isclose(metrics.average_r, 0.8)
    assert metrics.largest_win == 100.0
    assert metrics.largest_loss == -50.0
    assert metrics.max_consecutive_losses == 1  # losses never occur back-to-back here


def test_max_consecutive_losses_counts_a_real_streak():
    trades = [
        _trade(100.0, day=0),
        _trade(-10.0, day=2),
        _trade(-10.0, day=4),
        _trade(-10.0, day=6),
        _trade(100.0, day=8),
    ]
    equity_curve = build_equity_curve(
        start_time=datetime(2026, 1, 1), initial_capital=1_000.0, trade_equities=_running_equity(trades, start=1_000.0)
    )
    metrics = compute_performance_metrics(trades, equity_curve)
    assert metrics.max_consecutive_losses == 3


def test_profit_factor_is_none_not_infinite_with_no_losses():
    trades = [_trade(50.0, day=0), _trade(75.0, day=2)]
    equity_curve = build_equity_curve(
        start_time=datetime(2026, 1, 1), initial_capital=1_000.0, trade_equities=_running_equity(trades, start=1_000.0)
    )
    metrics = compute_performance_metrics(trades, equity_curve)
    assert metrics.profit_factor is None
    assert metrics.average_loser is None
    assert metrics.largest_loss is None


def test_max_drawdown_from_a_known_equity_path():
    # equity: 1000 -> 1200 (peak) -> 900 -> 1100
    # drawdown at 900 relative to peak 1200 = (1200-900)/1200 = 25%
    trades = [_trade(200.0, day=0), _trade(-300.0, day=2), _trade(200.0, day=4)]
    equity_curve = build_equity_curve(
        start_time=datetime(2026, 1, 1), initial_capital=1_000.0, trade_equities=_running_equity(trades, start=1_000.0)
    )
    metrics = compute_performance_metrics(trades, equity_curve)
    assert math.isclose(metrics.max_drawdown_pct, 25.0)


def test_empty_trade_list_produces_zeroed_not_crashing_metrics():
    equity_curve = build_equity_curve(start_time=datetime(2026, 1, 1), initial_capital=1_000.0, trade_equities=[])
    metrics = compute_performance_metrics([], equity_curve)

    assert metrics.total_trades == 0
    assert metrics.win_rate_pct == 0.0
    assert metrics.profit_factor is None
    assert metrics.average_r is None


def _running_equity(trades: list[Trade], *, start: float) -> list[tuple[datetime, float]]:
    equity = start
    out = []
    for t in trades:
        equity += t.net_pnl
        out.append((t.exit_time, equity))
    return out
