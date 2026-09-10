"""H_MEANREV_011 (docs/research/H_MEANREV_011_PORTFOLIO_CONSTRUCTION_
PREREGISTRATION.md, frozen design, committed before this module): the
minimum multi-position, event-driven, shared-capital portfolio
simulator this codebase does not otherwise have. Every prior backtest
in this project is either single-symbol with dedicated capital
(H_MEANREV_009/010) or a periodic full-basket rebalance (H_XSECT_005) --
neither models several SIMULTANEOUS, INDEPENDENTLY-TIMED positions
competing for a SHARED capital pool, which this hypothesis's own
research question requires.

Reuses, never recomputes: quant_research.mean_reversion_execution_
structure.compute_fixed_notional_trade (H_MEANREV_010's own function,
unmodified) for ALL per-trade price/cost/notional math;
backtesting.equity.build_equity_curve (unmodified) for the realized
equity/drawdown curve; quant_research.mean_reversion_signal.
_oversold_2std_relative_weak (the frozen H_MEANREV_006 entry,
unmodified) for signal detection.

The only genuinely new logic here is SCHEDULING: given a chronological
list of candidate signal events across many symbols, decide which are
accepted into a capital- and concurrency-constrained portfolio, and
compute the resulting realized-P&L/equity/concentration picture.
"""

from dataclasses import dataclass, field

import pandas as pd

from backtesting.costs import CostModel
from backtesting.equity import EquityPoint, build_equity_curve
from quant_research.mean_reversion_execution_structure import FixedNotionalTradeRecord, compute_fixed_notional_trade
from quant_research.mean_reversion_signal import _oversold_2std_relative_weak
from quant_research.market_behavior import SymbolDataset


@dataclass(frozen=True)
class CandidateEntryEvent:
    symbol: str
    signal_date: pd.Timestamp
    signal_idx: int


def collect_candidate_events(datasets: dict[str, SymbolDataset]) -> list[CandidateEntryEvent]:
    """Pure function: scans every symbol's own frame for every bar where
    the frozen _oversold_2std_relative_weak predicate fires -- reused
    unchanged, not reimplemented. Returns events sorted chronologically
    by signal_date (ties broken by symbol name for determinism, so a
    repeated run always produces an identical ordering -- deterministic
    replay)."""
    events: list[CandidateEntryEvent] = []
    for symbol, dataset in datasets.items():
        frame = dataset.frame
        hits = frame.apply(_oversold_2std_relative_weak, axis=1)
        matched_idx = [i for i, hit in enumerate(hits.fillna(False)) if hit]
        for i in matched_idx:
            events.append(CandidateEntryEvent(symbol=symbol, signal_date=frame.index[i], signal_idx=i))
    events.sort(key=lambda e: (e.signal_date, e.symbol))
    return events


@dataclass
class PortfolioSchedulingResult:
    accepted_trades: list[FixedNotionalTradeRecord] = field(default_factory=list)
    rejected_capacity_count: int = 0
    """Candidates rejected because MAX_CONCURRENT_POSITIONS was already reached."""
    rejected_cash_count: int = 0
    """Candidates rejected because capital_per_position exceeded currently available cash (a real, disclosed capital constraint -- NOT expected to be zero, since a losing stretch can shrink available cash below a slot's own fixed nominal size even with an open concurrency slot free)."""
    rejected_symbol_already_open_count: int = 0
    """Candidates skipped because that symbol already had an open position -- the same one-position-per-symbol convention H_MEANREV_009/010 both used."""
    rejected_insufficient_future_data_count: int = 0
    """Candidates accepted by capacity/cash but for which compute_fixed_notional_trade itself returned None (not enough future bars for a full h10 holding period, e.g. near the end of history)."""
    max_concurrent_positions_observed: int = 0


def schedule_portfolio(
    datasets: dict[str, SymbolDataset],
    events: list[CandidateEntryEvent],
    *,
    max_concurrent_positions: int,
    capital_per_position: float,
    initial_capital: float,
    holding_bars: int,
    cost_model: CostModel,
) -> PortfolioSchedulingResult:
    """Pure function, deterministic given its inputs -- no randomness, no
    I/O. Walks `events` in the chronological order collect_candidate_
    events already produced. Before considering each candidate, any
    currently-open position whose own (already-computed, deterministic)
    exit_time has passed is released first -- capital and its
    concurrency slot returned to the pool. The ACCEPT/REJECT decision
    itself uses ONLY information available at the candidate's own
    signal_date (current open-position count, current cash) -- never
    the candidate's own future outcome, which is computed via compute_
    fixed_notional_trade only AFTER a candidate is already accepted (the
    identical "compute the whole deterministic trade once accepted"
    pattern every prior backtest in this project already uses, not a
    new look-ahead risk)."""
    open_positions: list[FixedNotionalTradeRecord] = []
    symbols_open: set[str] = set()
    cash = initial_capital

    result = PortfolioSchedulingResult()

    for event in events:
        still_open = []
        for pos in open_positions:
            if pos.exit_time <= event.signal_date:
                cash += capital_per_position + pos.net_pnl
                symbols_open.discard(pos.symbol)
            else:
                still_open.append(pos)
        open_positions = still_open

        if event.symbol in symbols_open:
            result.rejected_symbol_already_open_count += 1
            continue

        if len(open_positions) >= max_concurrent_positions:
            result.rejected_capacity_count += 1
            continue

        if capital_per_position > cash:
            result.rejected_cash_count += 1
            continue

        frame = datasets[event.symbol].frame
        trade = compute_fixed_notional_trade(
            frame, symbol=event.symbol, signal_idx=event.signal_idx, holding_bars=holding_bars,
            capital_per_slot=capital_per_position, cost_model=cost_model,
        )
        if trade is None:
            result.rejected_insufficient_future_data_count += 1
            continue

        cash -= capital_per_position
        open_positions.append(trade)
        symbols_open.add(event.symbol)
        result.accepted_trades.append(trade)
        result.max_concurrent_positions_observed = max(result.max_concurrent_positions_observed, len(open_positions))

    return result


@dataclass(frozen=True)
class PortfolioSummary:
    n_trades: int
    gross_pnl: float
    total_fixed_costs: float
    total_variable_costs: float
    net_pnl: float
    win_rate: float | None
    worst_trade_net_pnl: float | None
    best_trade_net_pnl: float | None
    equity_curve: list[EquityPoint]
    max_drawdown_pct: float
    distinct_symbols: int
    top5_trades_pnl_share_pct: float | None
    """Top-5 trades' combined net_pnl as a % of total net_pnl -- the SAME concentration check H_MEANREV_010 already used. None (not a fabricated 0.0) if total net_pnl is exactly zero."""
    rejected_capacity_count: int
    rejected_cash_count: int
    rejected_symbol_already_open_count: int
    max_concurrent_positions_observed: int


def summarize_portfolio(result: PortfolioSchedulingResult, *, initial_capital: float, start_time: pd.Timestamp) -> PortfolioSummary:
    """Pure function -- reuses build_equity_curve (backtesting/equity.py,
    unmodified) for the realized equity/drawdown curve; everything else
    computed directly from the accepted-trade list. Deliberately does
    NOT route through backtesting.metrics.compute_performance_metrics,
    which requires Trade.r_multiple -- not a meaningful concept for
    fixed-notional (non-stop-distance-based) sizing."""
    trades = sorted(result.accepted_trades, key=lambda t: t.exit_time)
    n = len(trades)

    gross_pnl = sum(t.gross_pnl for t in trades)
    total_fixed_costs = sum(t.fixed_fee_cost for t in trades)
    total_variable_costs = sum(t.variable_cost for t in trades)
    net_pnl = sum(t.net_pnl for t in trades)

    wins = [t for t in trades if t.net_pnl > 0]
    win_rate = (len(wins) / n) if n > 0 else None
    worst = min((t.net_pnl for t in trades), default=None)
    best = max((t.net_pnl for t in trades), default=None)

    running_equity = initial_capital
    trade_equities: list[tuple[pd.Timestamp, float]] = []
    for t in trades:
        running_equity += t.net_pnl
        trade_equities.append((t.exit_time, running_equity))
    equity_curve = build_equity_curve(start_time=start_time, initial_capital=initial_capital, trade_equities=trade_equities)
    max_drawdown_pct = max((p.drawdown_pct for p in equity_curve), default=0.0)

    distinct_symbols = len({t.symbol for t in trades})

    top5_share: float | None = None
    if n > 0 and net_pnl != 0:
        sorted_desc = sorted((t.net_pnl for t in trades), reverse=True)
        top5_share = sum(sorted_desc[:5]) / net_pnl * 100

    return PortfolioSummary(
        n_trades=n, gross_pnl=gross_pnl, total_fixed_costs=total_fixed_costs, total_variable_costs=total_variable_costs,
        net_pnl=net_pnl, win_rate=win_rate, worst_trade_net_pnl=worst, best_trade_net_pnl=best,
        equity_curve=equity_curve, max_drawdown_pct=max_drawdown_pct, distinct_symbols=distinct_symbols,
        top5_trades_pnl_share_pct=top5_share, rejected_capacity_count=result.rejected_capacity_count,
        rejected_cash_count=result.rejected_cash_count, rejected_symbol_already_open_count=result.rejected_symbol_already_open_count,
        max_concurrent_positions_observed=result.max_concurrent_positions_observed,
    )
