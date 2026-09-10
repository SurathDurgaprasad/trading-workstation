"""H_MEANREV_011: tests for quant_research/mean_reversion_portfolio.py
-- the minimum multi-position, event-driven, shared-capital portfolio
simulator this codebase did not otherwise have.
"""
import pandas as pd
import pytest

from backtesting.costs import CostModel
from quant_research.market_behavior import SymbolDataset
from quant_research.mean_reversion_portfolio import (
    CandidateEntryEvent,
    PortfolioSchedulingResult,
    collect_candidate_events,
    schedule_portfolio,
    summarize_portfolio,
)

_ZERO_COST = CostModel(brokerage_per_fill=0.0, fees_pct=0.0, taxes_pct=0.0, entry_slippage_bps=0.0, exit_slippage_bps=0.0)


def _dataset(symbol: str, n: int, signal_bars: set[int], base_price: float = 100.0) -> SymbolDataset:
    """A synthetic dataset that fires the frozen predicate exactly on
    `signal_bars` (via zscore_close_20/relative_strength_20 set to
    clearly-triggering values there, and clearly non-triggering
    elsewhere), with a flat OHLC series (open==close each bar) so
    per-trade P&L is deterministic and easy to reason about in tests."""
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    rows = []
    for i in range(n):
        triggers = i in signal_bars
        rows.append({
            "open": base_price, "close": base_price, "high": base_price + 1.0, "low": base_price - 1.0,
            "zscore_close_20": -2.5 if triggers else 0.0,
            "relative_strength_20": -0.10 if triggers else 0.0,
        })
    frame = pd.DataFrame(rows, index=dates)
    return SymbolDataset(symbol=symbol, market="NSE", raw_market="NSE", frame=frame, development_end=None, validation_end=None)


# --- collect_candidate_events ----------------------------------------------------


def test_collect_candidate_events_finds_triggering_bars_only():
    datasets = {"AAA": _dataset("AAA", 30, {5, 15})}
    events = collect_candidate_events(datasets)
    assert [e.signal_idx for e in events] == [5, 15]
    assert all(e.symbol == "AAA" for e in events)


def test_collect_candidate_events_sorted_chronologically_across_symbols():
    datasets = {
        "BBB": _dataset("BBB", 30, {10}),
        "AAA": _dataset("AAA", 30, {5}),
    }
    events = collect_candidate_events(datasets)
    assert [(e.symbol, e.signal_idx) for e in events] == [("AAA", 5), ("BBB", 10)]


def test_collect_candidate_events_ties_broken_by_symbol_name():
    datasets = {
        "BBB": _dataset("BBB", 30, {5}),
        "AAA": _dataset("AAA", 30, {5}),
    }
    events = collect_candidate_events(datasets)
    assert [e.symbol for e in events] == ["AAA", "BBB"]


def test_collect_candidate_events_deterministic_replay():
    datasets = {"AAA": _dataset("AAA", 30, {5, 15}), "BBB": _dataset("BBB", 30, {10})}
    first = collect_candidate_events(datasets)
    second = collect_candidate_events(datasets)
    assert first == second


# --- schedule_portfolio -----------------------------------------------------------


def test_schedule_portfolio_accepts_within_capacity():
    datasets = {name: _dataset(name, 30, {5}) for name in ("AAA", "BBB", "CCC")}
    events = collect_candidate_events(datasets)
    result = schedule_portfolio(
        datasets, events, max_concurrent_positions=4, capital_per_position=1000.0,
        initial_capital=4000.0, holding_bars=3, cost_model=_ZERO_COST,
    )
    assert len(result.accepted_trades) == 3
    assert result.rejected_capacity_count == 0
    assert result.rejected_cash_count == 0


def test_schedule_portfolio_rejects_beyond_max_concurrent_positions():
    # 5 symbols all fire on the SAME bar -- only 4 should fit under the cap.
    datasets = {name: _dataset(name, 30, {5}) for name in ("AAA", "BBB", "CCC", "DDD", "EEE")}
    events = collect_candidate_events(datasets)
    result = schedule_portfolio(
        datasets, events, max_concurrent_positions=4, capital_per_position=1000.0,
        initial_capital=100_000.0, holding_bars=3, cost_model=_ZERO_COST,
    )
    assert len(result.accepted_trades) == 4
    assert result.rejected_capacity_count == 1


def test_schedule_portfolio_skips_symbol_with_already_open_position():
    # Same symbol fires twice before its first trade's exit (holding_bars=10).
    datasets = {"AAA": _dataset("AAA", 30, {5, 6})}
    events = collect_candidate_events(datasets)
    result = schedule_portfolio(
        datasets, events, max_concurrent_positions=4, capital_per_position=1000.0,
        initial_capital=100_000.0, holding_bars=10, cost_model=_ZERO_COST,
    )
    assert len(result.accepted_trades) == 1
    assert result.rejected_symbol_already_open_count == 1


def test_schedule_portfolio_releases_capacity_after_exit():
    # AAA fires at bar 0 with a short 3-bar hold (exits at bar 3); BBB
    # fires at bar 4, AFTER AAA's own exit -- both should be accepted
    # even with max_concurrent_positions=1.
    datasets = {"AAA": _dataset("AAA", 30, {0}), "BBB": _dataset("BBB", 30, {4})}
    events = collect_candidate_events(datasets)
    result = schedule_portfolio(
        datasets, events, max_concurrent_positions=1, capital_per_position=1000.0,
        initial_capital=100_000.0, holding_bars=3, cost_model=_ZERO_COST,
    )
    assert len(result.accepted_trades) == 2
    assert result.rejected_capacity_count == 0


def test_schedule_portfolio_rejects_when_cash_unavailable():
    datasets = {name: _dataset(name, 30, {5}) for name in ("AAA", "BBB")}
    events = collect_candidate_events(datasets)
    # capital_per_position=1000, initial_capital=1500 -- only room for ONE slot's worth of cash, even though capacity allows 4.
    result = schedule_portfolio(
        datasets, events, max_concurrent_positions=4, capital_per_position=1000.0,
        initial_capital=1500.0, holding_bars=3, cost_model=_ZERO_COST,
    )
    assert len(result.accepted_trades) == 1
    assert result.rejected_cash_count == 1


def test_schedule_portfolio_insufficient_future_data_is_not_a_capacity_or_cash_rejection():
    # Signal fires too close to the end of history for a full holding period.
    datasets = {"AAA": _dataset("AAA", 10, {8})}
    events = collect_candidate_events(datasets)
    result = schedule_portfolio(
        datasets, events, max_concurrent_positions=4, capital_per_position=1000.0,
        initial_capital=100_000.0, holding_bars=10, cost_model=_ZERO_COST,
    )
    assert len(result.accepted_trades) == 0
    assert result.rejected_insufficient_future_data_count == 1
    assert result.rejected_capacity_count == 0
    assert result.rejected_cash_count == 0


def test_schedule_portfolio_deterministic_replay():
    datasets = {name: _dataset(name, 40, {5, 20}) for name in ("AAA", "BBB", "CCC")}
    events = collect_candidate_events(datasets)
    kwargs = dict(max_concurrent_positions=2, capital_per_position=1000.0, initial_capital=5000.0, holding_bars=5, cost_model=CostModel.india_nse_intraday_2026())
    first = schedule_portfolio(datasets, events, **kwargs)
    second = schedule_portfolio(datasets, events, **kwargs)
    assert [t.net_pnl for t in first.accepted_trades] == [t.net_pnl for t in second.accepted_trades]
    assert first.rejected_capacity_count == second.rejected_capacity_count


# --- summarize_portfolio -----------------------------------------------------------


def test_summarize_portfolio_empty_result_has_no_fabricated_stats():
    result = PortfolioSchedulingResult()
    summary = summarize_portfolio(result, initial_capital=100_000.0, start_time=pd.Timestamp("2024-01-01"))
    assert summary.n_trades == 0
    assert summary.win_rate is None
    assert summary.worst_trade_net_pnl is None
    assert summary.top5_trades_pnl_share_pct is None


def test_summarize_portfolio_computes_gross_net_and_costs_correctly():
    datasets = {"AAA": _dataset("AAA", 30, {5}, base_price=100.0)}
    events = collect_candidate_events(datasets)
    cost_model = CostModel(brokerage_per_fill=10.0, fees_pct=0.0, taxes_pct=0.0, entry_slippage_bps=0.0, exit_slippage_bps=0.0)
    result = schedule_portfolio(
        datasets, events, max_concurrent_positions=1, capital_per_position=1000.0,
        initial_capital=100_000.0, holding_bars=3, cost_model=cost_model,
    )
    summary = summarize_portfolio(result, initial_capital=100_000.0, start_time=pd.Timestamp("2024-01-01"))
    assert summary.n_trades == 1
    # flat price -> zero gross pnl; only the flat brokerage (2 x 10) as cost.
    assert summary.gross_pnl == pytest.approx(0.0)
    assert summary.total_fixed_costs == pytest.approx(20.0)
    assert summary.net_pnl == pytest.approx(-20.0)


def test_summarize_portfolio_top5_concentration_share():
    datasets = {name: _dataset(name, 30, {5}) for name in ("AAA", "BBB", "CCC")}
    events = collect_candidate_events(datasets)
    result = schedule_portfolio(
        datasets, events, max_concurrent_positions=4, capital_per_position=1000.0,
        initial_capital=100_000.0, holding_bars=3, cost_model=_ZERO_COST,
    )
    summary = summarize_portfolio(result, initial_capital=100_000.0, start_time=pd.Timestamp("2024-01-01"))
    # flat prices -> zero net pnl per trade -> top5_share undefined (None), never fabricated.
    assert summary.top5_trades_pnl_share_pct is None


def test_summarize_portfolio_distinct_symbols_counted_correctly():
    datasets = {name: _dataset(name, 30, {5}) for name in ("AAA", "BBB")}
    events = collect_candidate_events(datasets)
    result = schedule_portfolio(
        datasets, events, max_concurrent_positions=4, capital_per_position=1000.0,
        initial_capital=100_000.0, holding_bars=3, cost_model=_ZERO_COST,
    )
    summary = summarize_portfolio(result, initial_capital=100_000.0, start_time=pd.Timestamp("2024-01-01"))
    assert summary.distinct_symbols == 2
