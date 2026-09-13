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
    schedule_portfolio_ranked,
    summarize_portfolio,
    zscore_close_20_rank_key,
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


# --- H_MEANREV_012: schedule_portfolio_ranked / zscore_close_20_rank_key ----------
#
# docs/research/H_MEANREV_012_SIGNAL_STRENGTH_SELECTION_PREREGISTRATION.md:
# the ONLY changed variable vs. H_MEANREV_011 is candidate-selection-under-
# contention (same-signal-date candidates ranked by the frozen
# zscore_close_20 key instead of alphabetically), so these tests focus on
# that one behavior -- everything else (accounting, h10 exit timing,
# costs, capacity, cash, one-position-per-symbol) is proven unchanged by
# construction (schedule_portfolio and schedule_portfolio_ranked both
# delegate to the identical shared _run_schedule engine) and confirmed
# directly below rather than assumed.


def _dataset_with_zscore(symbol: str, n: int, signal_bar_zscores: dict[int, float], base_price: float = 100.0) -> SymbolDataset:
    """Like _dataset, but the caller supplies a distinct zscore_close_20
    value per triggering bar (each still < -2.0, so every listed bar
    fires the frozen predicate) -- lets ranking tests construct several
    symbols with deliberately different signal strength on the SAME
    signal_date."""
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    rows = []
    for i in range(n):
        z = signal_bar_zscores.get(i)
        rows.append({
            "open": base_price, "close": base_price, "high": base_price + 1.0, "low": base_price - 1.0,
            "zscore_close_20": z if z is not None else 0.0,
            "relative_strength_20": -0.10 if z is not None else 0.0,
        })
    frame = pd.DataFrame(rows, index=dates)
    return SymbolDataset(symbol=symbol, market="NSE", raw_market="NSE", frame=frame, development_end=None, validation_end=None)


def test_schedule_portfolio_ranked_orders_simultaneous_signals_by_zscore_strength():
    # AAA/BBB/CCC/DDD all fire on the SAME bar with different
    # zscore_close_20 magnitudes; only 2 slots -- only the 2 MOST
    # NEGATIVE (most oversold) should be accepted, not the alphabetically
    # first 2.
    datasets = {
        "AAA": _dataset_with_zscore("AAA", 30, {5: -2.1}),
        "BBB": _dataset_with_zscore("BBB", 30, {5: -3.5}),
        "CCC": _dataset_with_zscore("CCC", 30, {5: -2.8}),
        "DDD": _dataset_with_zscore("DDD", 30, {5: -2.3}),
    }
    events = collect_candidate_events(datasets)
    result = schedule_portfolio_ranked(
        datasets, events, max_concurrent_positions=2, capital_per_position=1000.0,
        initial_capital=100_000.0, holding_bars=3, cost_model=_ZERO_COST, rank_key=zscore_close_20_rank_key,
    )
    assert {t.symbol for t in result.accepted_trades} == {"BBB", "CCC"}
    assert result.rejected_capacity_count == 2


def test_schedule_portfolio_ranked_differs_from_alphabetical_control_under_contention():
    datasets = {
        "AAA": _dataset_with_zscore("AAA", 30, {5: -2.1}),
        "BBB": _dataset_with_zscore("BBB", 30, {5: -3.5}),
        "CCC": _dataset_with_zscore("CCC", 30, {5: -2.8}),
        "DDD": _dataset_with_zscore("DDD", 30, {5: -2.3}),
    }
    events = collect_candidate_events(datasets)
    kwargs = dict(max_concurrent_positions=2, capital_per_position=1000.0, initial_capital=100_000.0, holding_bars=3, cost_model=_ZERO_COST)
    control = schedule_portfolio(datasets, events, **kwargs)
    ranked = schedule_portfolio_ranked(datasets, events, **kwargs, rank_key=zscore_close_20_rank_key)
    assert {t.symbol for t in control.accepted_trades} == {"AAA", "BBB"}
    assert {t.symbol for t in ranked.accepted_trades} == {"BBB", "CCC"}


def test_schedule_portfolio_ranked_respects_slot_limitation():
    # Each symbol's zscore is < -2.0 (so every one fires the frozen
    # predicate), with AAA the weakest (-2.1) and EEE the strongest (-3.3).
    datasets = {name: _dataset_with_zscore(name, 30, {5: -2.1 - 0.3 * i}) for i, name in enumerate(("AAA", "BBB", "CCC", "DDD", "EEE"))}
    events = collect_candidate_events(datasets)
    result = schedule_portfolio_ranked(
        datasets, events, max_concurrent_positions=4, capital_per_position=1000.0,
        initial_capital=100_000.0, holding_bars=3, cost_model=_ZERO_COST, rank_key=zscore_close_20_rank_key,
    )
    assert len(result.accepted_trades) == 4
    assert result.rejected_capacity_count == 1
    # EEE has the most negative zscore (-6.0) -> strongest -> must be
    # accepted; AAA has the weakest (-2.0) -> must be the one rejected.
    accepted_symbols = {t.symbol for t in result.accepted_trades}
    assert "EEE" in accepted_symbols
    assert "AAA" not in accepted_symbols


def test_schedule_portfolio_ranked_skips_symbol_with_already_open_position():
    datasets = {"AAA": _dataset_with_zscore("AAA", 30, {5: -2.5, 6: -3.0})}
    events = collect_candidate_events(datasets)
    result = schedule_portfolio_ranked(
        datasets, events, max_concurrent_positions=4, capital_per_position=1000.0,
        initial_capital=100_000.0, holding_bars=10, cost_model=_ZERO_COST, rank_key=zscore_close_20_rank_key,
    )
    assert len(result.accepted_trades) == 1
    assert result.rejected_symbol_already_open_count == 1


def test_schedule_portfolio_ranked_rejects_when_cash_unavailable():
    datasets = {
        "AAA": _dataset_with_zscore("AAA", 30, {5: -2.1}),
        "BBB": _dataset_with_zscore("BBB", 30, {5: -3.5}),
    }
    events = collect_candidate_events(datasets)
    result = schedule_portfolio_ranked(
        datasets, events, max_concurrent_positions=4, capital_per_position=1000.0,
        initial_capital=1500.0, holding_bars=3, cost_model=_ZERO_COST, rank_key=zscore_close_20_rank_key,
    )
    assert len(result.accepted_trades) == 1
    assert result.rejected_cash_count == 1
    # BBB (-3.5, stronger) must be the one accepted ahead of AAA.
    assert result.accepted_trades[0].symbol == "BBB"


def test_schedule_portfolio_ranked_equal_strength_tie_break_by_symbol_name():
    datasets = {
        "BBB": _dataset_with_zscore("BBB", 30, {5: -2.5}),
        "AAA": _dataset_with_zscore("AAA", 30, {5: -2.5}),
    }
    events = collect_candidate_events(datasets)
    result = schedule_portfolio_ranked(
        datasets, events, max_concurrent_positions=1, capital_per_position=1000.0,
        initial_capital=100_000.0, holding_bars=3, cost_model=_ZERO_COST, rank_key=zscore_close_20_rank_key,
    )
    assert [t.symbol for t in result.accepted_trades] == ["AAA"]


def test_schedule_portfolio_ranked_deterministic_replay():
    datasets = {name: _dataset_with_zscore(name, 40, {5: -2.5, 20: -3.1}) for name in ("AAA", "BBB", "CCC")}
    events = collect_candidate_events(datasets)
    kwargs = dict(max_concurrent_positions=2, capital_per_position=1000.0, initial_capital=5000.0, holding_bars=5, cost_model=CostModel.india_nse_intraday_2026(), rank_key=zscore_close_20_rank_key)
    first = schedule_portfolio_ranked(datasets, events, **kwargs)
    second = schedule_portfolio_ranked(datasets, events, **kwargs)
    assert [t.net_pnl for t in first.accepted_trades] == [t.net_pnl for t in second.accepted_trades]
    assert [t.symbol for t in first.accepted_trades] == [t.symbol for t in second.accepted_trades]


def test_schedule_portfolio_alphabetical_control_remains_reproducible_alongside_ranked_module():
    # The presence of schedule_portfolio_ranked in this module must not
    # change schedule_portfolio's own frozen alphabetical behavior --
    # H_MEANREV_011's own control.
    datasets = {name: _dataset(name, 30, {5}) for name in ("AAA", "BBB", "CCC", "DDD", "EEE")}
    events = collect_candidate_events(datasets)
    result = schedule_portfolio(
        datasets, events, max_concurrent_positions=4, capital_per_position=1000.0,
        initial_capital=100_000.0, holding_bars=3, cost_model=_ZERO_COST,
    )
    assert {t.symbol for t in result.accepted_trades} == {"AAA", "BBB", "CCC", "DDD"}
    assert result.rejected_capacity_count == 1


def test_schedule_portfolio_ranked_accounting_h10_and_costs_unchanged_when_uncontended():
    # No contention (single symbol) -- schedule_portfolio_ranked must
    # produce IDENTICAL trade accounting, exit timing, and costs to
    # schedule_portfolio, since ranking only reorders WITHIN a date-group
    # and both delegate to the same accept/reject engine.
    datasets = {"AAA": _dataset_with_zscore("AAA", 30, {5: -2.5}, base_price=100.0)}
    events = collect_candidate_events(datasets)
    cost_model = CostModel(brokerage_per_fill=10.0, fees_pct=0.0, taxes_pct=0.0, entry_slippage_bps=0.0, exit_slippage_bps=0.0)
    kwargs = dict(max_concurrent_positions=1, capital_per_position=1000.0, initial_capital=100_000.0, holding_bars=3, cost_model=cost_model)
    control = schedule_portfolio(datasets, events, **kwargs)
    ranked = schedule_portfolio_ranked(datasets, events, **kwargs, rank_key=zscore_close_20_rank_key)
    assert [t.net_pnl for t in control.accepted_trades] == [t.net_pnl for t in ranked.accepted_trades]
    assert [t.exit_time for t in control.accepted_trades] == [t.exit_time for t in ranked.accepted_trades]
    assert [t.fixed_fee_cost for t in control.accepted_trades] == [t.fixed_fee_cost for t in ranked.accepted_trades]
    assert [t.variable_cost for t in control.accepted_trades] == [t.variable_cost for t in ranked.accepted_trades]


def test_zscore_close_20_rank_key_reads_only_the_signal_bar_not_future_bars():
    dataset = _dataset_with_zscore("AAA", 30, {5: -2.5})
    event = CandidateEntryEvent(symbol="AAA", signal_date=dataset.frame.index[5], signal_idx=5)
    baseline = zscore_close_20_rank_key(event, {"AAA": dataset})

    # Mutate every bar AFTER the signal index to an extreme,
    # ranking-reversing value -- the key must be unaffected, since it may
    # read only information available at the signal's own timestamp.
    mutated_frame = dataset.frame.copy()
    mutated_frame.iloc[6:, mutated_frame.columns.get_loc("zscore_close_20")] = -99.0
    mutated_dataset = SymbolDataset(symbol="AAA", market="NSE", raw_market="NSE", frame=mutated_frame, development_end=None, validation_end=None)
    mutated = zscore_close_20_rank_key(event, {"AAA": mutated_dataset})

    assert mutated == baseline == -2.5


def test_schedule_portfolio_ranked_ignores_future_bars_beyond_each_signal_idx():
    datasets = {
        "AAA": _dataset_with_zscore("AAA", 30, {5: -2.1}),
        "BBB": _dataset_with_zscore("BBB", 30, {5: -3.5}),
    }
    events = collect_candidate_events(datasets)
    kwargs = dict(max_concurrent_positions=1, capital_per_position=1000.0, initial_capital=100_000.0, holding_bars=3, cost_model=_ZERO_COST, rank_key=zscore_close_20_rank_key)
    baseline = schedule_portfolio_ranked(datasets, events, **kwargs)

    # Mutate a bar strictly AFTER each symbol's own signal_idx to an
    # extreme value that would reverse the ranking if it leaked into the
    # rank key -- acceptance must be unaffected.
    mutated = {}
    for symbol, ds in datasets.items():
        frame = ds.frame.copy()
        frame.iloc[6, frame.columns.get_loc("zscore_close_20")] = 99.0 if symbol == "BBB" else -99.0
        mutated[symbol] = SymbolDataset(symbol=symbol, market="NSE", raw_market="NSE", frame=frame, development_end=None, validation_end=None)
    mutated_events = collect_candidate_events(mutated)
    mutated_result = schedule_portfolio_ranked(mutated, mutated_events, **kwargs)

    assert {t.symbol for t in baseline.accepted_trades} == {t.symbol for t in mutated_result.accepted_trades} == {"BBB"}
