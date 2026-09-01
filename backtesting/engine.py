from datetime import datetime

import pandas as pd
from pydantic import BaseModel, ConfigDict

from backtesting.costs import CostModel
from backtesting.equity import EquityPoint, build_equity_curve
from backtesting.execution import OpenPosition, bar_day, check_exit, close_trade
from backtesting.metrics import PerformanceMetrics, compute_performance_metrics
from backtesting.trade import ExitReason, Trade
from risk.account import Account, new_account
from risk.config import RiskConfig
from risk.contracts import RiskSummary, SignalRecord
from risk.engine import RiskEngine, summarize_risk
from strategy.contracts import Strategy
from strategy.signal import Side, Signal


class BacktestResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    symbol: str
    strategy_name: str
    period_label: str
    start: datetime
    end: datetime
    initial_capital: float
    final_equity: float
    trades: list[Trade]
    equity_curve: list[EquityPoint]
    metrics: PerformanceMetrics
    risk_summary: RiskSummary
    signal_records: list[SignalRecord]


def run_backtest(
    *,
    symbol: str,
    indicator_series: pd.DataFrame,
    strategy: Strategy,
    cost_model: CostModel | None = None,
    initial_capital: float = 100_000.0,
    risk_config: RiskConfig | None = None,
    period_label: str = "full",
) -> BacktestResult:
    """Chronological, bar-by-bar replay. No LLM call, no randomness, no
    network access — `indicator_series` must already be fully computed
    (see market.indicators.compute_indicator_series).

    Signal generated at bar i (using only rows <= i, guaranteed by
    compute_indicator_series' rolling/ewm construction) is eligible for entry
    at bar i+1's open. See tests/test_backtest_lookahead.py.

    Every signal is passed through RiskEngine.evaluate(signal, account)
    before it can open a position (Phase 4) — this replaces Phase 3's
    unconstrained fixed-fractional placeholder. See risk/engine.py.

    Fill/exit mechanics (OpenPosition, check_exit, close_trade) live in
    backtesting/execution.py — Phase 6's paper trading engine shares that
    exact code rather than reimplementing it.
    """
    cost_model = cost_model or CostModel()
    risk_engine = RiskEngine(risk_config)

    if indicator_series.empty:
        raise ValueError(f"No indicator data for {symbol}; cannot backtest an empty series.")

    account = new_account(initial_capital)
    trades: list[Trade] = []
    trade_equities: list[tuple[datetime, float]] = []
    signal_records: list[SignalRecord] = []
    open_position: OpenPosition | None = None

    n = len(indicator_series)
    for i in range(n):
        bar = indicator_series.iloc[i]
        timestamp = indicator_series.index[i]

        account.roll_to_day(bar_day(timestamp))

        if open_position is not None:
            account.mark_to_market(float(bar["close"]))
            exit_outcome = check_exit(open_position, bar)
            if exit_outcome is not None:
                exit_price, exit_reason = exit_outcome
                trade = close_trade(
                    open_position,
                    exit_price=exit_price,
                    exit_time=timestamp,
                    exit_reason=exit_reason,
                    symbol=symbol,
                    cost_model=cost_model,
                )
                exit_cost = cost_model.cost_for_fill(notional=exit_price * open_position.quantity)
                account.close_position(exit_price=exit_price, exit_cost=exit_cost, net_pnl=trade.net_pnl)

                trades.append(trade)
                trade_equities.append((timestamp, account.equity))
                open_position = None

        if open_position is None and i + 1 < n:
            signal = strategy.generate_signal(indicator_series, i, symbol)
            if signal is not None and signal.side == Side.LONG:
                decision = risk_engine.evaluate(signal, account)
                signal_records.append(
                    SignalRecord(timestamp=timestamp, symbol=symbol, signal=signal, decision=decision)
                )

                if decision.approved and decision.position_size is not None:
                    next_bar = indicator_series.iloc[i + 1]
                    raw_entry_price = float(next_bar["open"])
                    entry_price = cost_model.slippage_adjusted_price(
                        price=raw_entry_price, side=signal.side, is_entry=True
                    )

                    # A gap between the signal bar's close (what sizing used)
                    # and the actual next-bar-open fill can, rarely, make the
                    # approved quantity no longer affordable — re-check
                    # against cash at the ACTUAL fill price rather than
                    # silently letting cash go negative.
                    quantity = decision.position_size.quantity
                    if quantity * entry_price > account.cash:
                        quantity = int(account.cash // entry_price) if entry_price > 0 else 0

                    if quantity >= 1:
                        entry_cost = cost_model.cost_for_fill(notional=entry_price * quantity)
                        account.open_position(quantity=quantity, entry_price=entry_price, entry_cost=entry_cost)
                        open_position = OpenPosition(
                            signal=signal,
                            entry_time=indicator_series.index[i + 1],
                            entry_price=entry_price,
                            quantity=quantity,
                            stop_price=signal.stop_price,
                            target_price=signal.target_price,
                        )

    if open_position is not None:
        last_bar = indicator_series.iloc[-1]
        exit_price = cost_model.slippage_adjusted_price(
            price=float(last_bar["close"]), side=open_position.signal.side, is_entry=False
        )
        trade = close_trade(
            open_position,
            exit_price=exit_price,
            exit_time=indicator_series.index[-1],
            exit_reason=ExitReason.END_OF_DATA,
            symbol=symbol,
            cost_model=cost_model,
        )
        exit_cost = cost_model.cost_for_fill(notional=exit_price * open_position.quantity)
        account.close_position(exit_price=exit_price, exit_cost=exit_cost, net_pnl=trade.net_pnl)

        trades.append(trade)
        trade_equities.append((indicator_series.index[-1], account.equity))

    equity_curve = build_equity_curve(
        start_time=indicator_series.index[0],
        initial_capital=initial_capital,
        trade_equities=trade_equities,
    )
    metrics = compute_performance_metrics(trades, equity_curve)
    risk_summary = summarize_risk(signal_records)

    return BacktestResult(
        symbol=symbol,
        strategy_name=strategy.name,
        period_label=period_label,
        start=indicator_series.index[0],
        end=indicator_series.index[-1],
        initial_capital=initial_capital,
        final_equity=account.equity,
        trades=trades,
        equity_curve=equity_curve,
        metrics=metrics,
        risk_summary=risk_summary,
        signal_records=signal_records,
    )
