"""H_XSECT_005: tests for quant_research/cross_sectional_portfolio.py
-- the equal-weight, periodically-rebalanced portfolio reproduction of
H_XSECT_001's own exact economic design."""

import pandas as pd
import pytest

from backtesting.costs import CostModel
from quant_research.cross_sectional_portfolio import (
    PortfolioBacktestResult,
    PortfolioPeriodResult,
    compute_member_return,
)

_ZERO_COST_MODEL = CostModel(brokerage_per_fill=0.0, fees_pct=0.0, taxes_pct=0.0, entry_slippage_bps=0.0, exit_slippage_bps=0.0)


def _frame(opens: list[float], closes: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=len(opens), freq="D")
    return pd.DataFrame({"open": opens, "close": closes, "high": closes, "low": closes}, index=dates)


# --- compute_member_return --------------------------------------------------


def test_compute_member_return_matches_expired_bar_arithmetic_zero_cost():
    """signal_idx=0, holding_bars=3 -> entry at bar 1's open, exit at
    bar 3's close (signal_idx + holding_bars), the SAME bar arithmetic
    backtesting.exit_experiments.run_time_based_exit_backtest's own
    EXPIRED exit uses."""
    frame = _frame(opens=[100.0, 100.0, 100.0, 100.0], closes=[100.0, 100.0, 100.0, 110.0])
    result = compute_member_return(frame, signal_idx=0, holding_bars=3, capital_per_slot=10_000.0, cost_model=_ZERO_COST_MODEL)
    assert result is not None
    # entry at bar 1 open=100, exit at bar 3 close=110, zero cost -> +10%
    assert result == pytest.approx(0.10)


def test_compute_member_return_returns_none_when_insufficient_future_data():
    """Not enough bars for a full holding period -- must return None,
    never a fabricated 0.0 or a partial-period return."""
    frame = _frame(opens=[100.0, 100.0], closes=[100.0, 100.0])
    result = compute_member_return(frame, signal_idx=0, holding_bars=5, capital_per_slot=10_000.0, cost_model=_ZERO_COST_MODEL)
    assert result is None


def test_compute_member_return_applies_realistic_costs():
    frame = _frame(opens=[100.0, 100.0], closes=[100.0, 100.0])
    cost_model = CostModel.india_nse_intraday_2026()
    result = compute_member_return(frame, signal_idx=0, holding_bars=1, capital_per_slot=10_000.0, cost_model=cost_model)
    assert result is not None
    # flat price, but slippage + fees + brokerage must produce a net NEGATIVE return
    assert result < 0.0


def test_compute_member_return_sizes_quantity_from_capital_per_slot():
    """A larger capital_per_slot should buy proportionally more shares
    -- verified indirectly via the flat brokerage fee's shrinking
    relative drag on a larger position (same % price move, smaller
    capital = more negative return from the same flat ₹20 fee)."""
    frame = _frame(opens=[100.0, 100.0], closes=[100.0, 105.0])
    cost_model = CostModel.india_nse_intraday_2026()
    small = compute_member_return(frame, signal_idx=0, holding_bars=1, capital_per_slot=1_000.0, cost_model=cost_model)
    large = compute_member_return(frame, signal_idx=0, holding_bars=1, capital_per_slot=100_000.0, cost_model=cost_model)
    assert small is not None and large is not None
    assert large > small  # the flat brokerage fee drags the smaller position down more


def test_compute_member_return_none_when_capital_too_small_for_one_share():
    frame = _frame(opens=[1000.0, 1000.0], closes=[1000.0, 1000.0])
    result = compute_member_return(frame, signal_idx=0, holding_bars=1, capital_per_slot=500.0, cost_model=_ZERO_COST_MODEL)
    assert result is None


# --- PortfolioPeriodResult / PortfolioBacktestResult --------------------------------------------------


def test_portfolio_return_is_equal_weight_mean_of_members():
    period = PortfolioPeriodResult(
        rebalance_date=pd.Timestamp("2024-01-01"), period_label="development",
        member_returns={"A": 0.10, "B": -0.02, "C": 0.04},
    )
    assert period.portfolio_return == pytest.approx((0.10 - 0.02 + 0.04) / 3)


def test_portfolio_return_is_zero_for_empty_period():
    period = PortfolioPeriodResult(rebalance_date=pd.Timestamp("2024-01-01"), period_label="development", member_returns={})
    assert period.portfolio_return == 0.0


def test_backtest_result_filters_returns_by_period_label():
    result = PortfolioBacktestResult(periods=[
        PortfolioPeriodResult(rebalance_date=pd.Timestamp("2024-01-01"), period_label="development", member_returns={"A": 0.05}),
        PortfolioPeriodResult(rebalance_date=pd.Timestamp("2024-02-01"), period_label="validation", member_returns={"A": 0.03}),
        PortfolioPeriodResult(rebalance_date=pd.Timestamp("2024-03-01"), period_label="out_of_sample", member_returns={"A": -0.01}),
        PortfolioPeriodResult(rebalance_date=pd.Timestamp("2024-04-01"), period_label="development", member_returns={"A": 0.02}),
    ])
    assert result.development_returns == pytest.approx([0.05, 0.02])
    assert result.validation_returns == pytest.approx([0.03])
    assert result.out_of_sample_returns == pytest.approx([-0.01])
