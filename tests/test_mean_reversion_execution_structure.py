"""H_MEANREV_010: tests for quant_research/mean_reversion_execution_
structure.py -- Candidate 2's fixed-notional sizing, modeled on
quant_research.cross_sectional_portfolio.compute_member_return
(H_XSECT_005's own already-tested pure function, not modified here).
"""
import pandas as pd
import pytest

from backtesting.costs import CostModel
from quant_research.mean_reversion_execution_structure import (
    FixedNotionalTradeRecord,
    UniverseFixedNotionalExperimentResult,
    compute_fixed_notional_trade,
    run_universe_fixed_notional_time_exit_experiment,
)

_ZERO_COST_MODEL = CostModel(brokerage_per_fill=0.0, fees_pct=0.0, taxes_pct=0.0, entry_slippage_bps=0.0, exit_slippage_bps=0.0)


def _frame(opens: list[float], closes: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=len(opens), freq="D")
    return pd.DataFrame({"open": opens, "close": closes, "high": closes, "low": closes}, index=dates)


# --- compute_fixed_notional_trade -----------------------------------------------


def test_compute_fixed_notional_trade_matches_expired_bar_arithmetic_zero_cost():
    """signal_idx=0, holding_bars=3 -> entry at bar 1's open, exit at
    bar 3's close -- the SAME bar arithmetic compute_member_return/
    run_time_based_exit_backtest's own EXPIRED exit uses."""
    frame = _frame(opens=[100.0, 100.0, 100.0, 100.0], closes=[100.0, 100.0, 100.0, 110.0])
    trade = compute_fixed_notional_trade(frame, symbol="TEST", signal_idx=0, holding_bars=3, capital_per_slot=10_000.0, cost_model=_ZERO_COST_MODEL)
    assert trade is not None
    assert trade.entry_price == pytest.approx(100.0)
    assert trade.exit_price == pytest.approx(110.0)
    assert trade.net_return == pytest.approx(0.10)
    assert trade.gross_return == pytest.approx(0.10)


def test_compute_fixed_notional_trade_returns_none_when_insufficient_future_data():
    frame = _frame(opens=[100.0, 100.0], closes=[100.0, 100.0])
    trade = compute_fixed_notional_trade(frame, symbol="TEST", signal_idx=0, holding_bars=5, capital_per_slot=10_000.0, cost_model=_ZERO_COST_MODEL)
    assert trade is None


def test_compute_fixed_notional_trade_none_when_capital_too_small_for_one_share():
    frame = _frame(opens=[1000.0, 1000.0], closes=[1000.0, 1000.0])
    trade = compute_fixed_notional_trade(frame, symbol="TEST", signal_idx=0, holding_bars=1, capital_per_slot=500.0, cost_model=_ZERO_COST_MODEL)
    assert trade is None


def test_compute_fixed_notional_trade_fixed_fee_cost_is_two_times_brokerage():
    frame = _frame(opens=[100.0, 100.0], closes=[100.0, 100.0])
    cost_model = CostModel(brokerage_per_fill=20.0, fees_pct=0.0, taxes_pct=0.0, entry_slippage_bps=0.0, exit_slippage_bps=0.0)
    trade = compute_fixed_notional_trade(frame, symbol="TEST", signal_idx=0, holding_bars=1, capital_per_slot=10_000.0, cost_model=cost_model)
    assert trade is not None
    assert trade.fixed_fee_cost == pytest.approx(40.0)
    assert trade.variable_cost == pytest.approx(0.0)


def test_compute_fixed_notional_trade_variable_cost_is_percentage_of_notional():
    frame = _frame(opens=[100.0, 100.0], closes=[100.0, 100.0])
    cost_model = CostModel(brokerage_per_fill=0.0, fees_pct=1.0, taxes_pct=0.0, entry_slippage_bps=0.0, exit_slippage_bps=0.0)
    trade = compute_fixed_notional_trade(frame, symbol="TEST", signal_idx=0, holding_bars=1, capital_per_slot=10_000.0, cost_model=cost_model)
    assert trade is not None
    assert trade.fixed_fee_cost == pytest.approx(0.0)
    # 1% fee on entry notional + 1% fee on exit notional (flat price, same notional each side)
    expected_variable = 2 * trade.entry_notional * 0.01
    assert trade.variable_cost == pytest.approx(expected_variable)


def test_compute_fixed_notional_trade_total_cost_equals_gross_minus_net():
    frame = _frame(opens=[100.0, 100.0], closes=[100.0, 108.0])
    cost_model = CostModel.india_nse_intraday_2026()
    trade = compute_fixed_notional_trade(frame, symbol="TEST", signal_idx=0, holding_bars=1, capital_per_slot=50_000.0, cost_model=cost_model)
    assert trade is not None
    assert trade.gross_pnl - trade.total_cost == pytest.approx(trade.net_pnl)


def test_compute_fixed_notional_trade_sizes_quantity_from_capital_per_slot():
    """A larger capital_per_slot buys proportionally more shares --
    verified via the flat brokerage fee's shrinking relative drag on a
    larger position, mirroring compute_member_return's own equivalent
    test."""
    frame = _frame(opens=[100.0, 100.0], closes=[100.0, 105.0])
    cost_model = CostModel.india_nse_intraday_2026()
    small = compute_fixed_notional_trade(frame, symbol="TEST", signal_idx=0, holding_bars=1, capital_per_slot=1_000.0, cost_model=cost_model)
    large = compute_fixed_notional_trade(frame, symbol="TEST", signal_idx=0, holding_bars=1, capital_per_slot=100_000.0, cost_model=cost_model)
    assert small is not None and large is not None
    assert large.quantity > small.quantity
    assert large.net_return > small.net_return


# --- run_universe_fixed_notional_time_exit_experiment ---------------------------


def _ohlcv_with_dip(n, seed_close=500.0, dip_at=100):
    """A mostly-flat series with a real multi-bar decline (reaches a
    real negative zscore_close_20) followed by a market-lagging
    recovery, so a real relative_strength_20-gated signal is reachable."""
    from market.data_provider import OHLCV

    bars = []
    close = seed_close
    for i in range(n):
        if dip_at <= i < dip_at + 8:
            close -= 12.0
        else:
            close += 0.2
        bars.append({"Open": close - 0.2, "High": close + 1.0, "Low": close - 1.0, "Close": close, "Volume": 1_000_000.0})
    frame = pd.DataFrame(bars, index=pd.date_range("2024-01-01", periods=n, freq="D"))
    return OHLCV.from_dataframe(symbol="TEST", interval="1d", frame=frame)


@pytest.fixture
def _fake_universe_provider(monkeypatch):
    from market.data_provider import MarketDataError

    class _Provider:
        def __init__(self, good_symbols):
            self._good = good_symbols

        def fetch_ohlcv(self, symbol, *, period="10y", interval="1d"):
            if symbol not in self._good:
                raise MarketDataError(f"no data for {symbol}")
            return _ohlcv_with_dip(300)

    def _apply(good_symbols):
        import market.data_provider as market_data_provider_module

        monkeypatch.setattr(market_data_provider_module, "get_market_data_provider", lambda: _Provider(good_symbols))

        import backtesting.cache as cache_module

        monkeypatch.setattr(cache_module, "CachedMarketDataProvider", lambda inner: inner)

    return _apply


def test_run_universe_fixed_notional_time_exit_experiment_pools_across_symbols(_fake_universe_provider):
    _fake_universe_provider({"AAA", "BBB", "^NSEI"})

    result = run_universe_fixed_notional_time_exit_experiment(["AAA", "BBB"], capital_per_slot=100_000.0)

    assert isinstance(result, UniverseFixedNotionalExperimentResult)
    assert result.failed_symbols == {}
    all_trades = result.development_trades + result.validation_trades + result.out_of_sample_trades
    assert all(isinstance(t, FixedNotionalTradeRecord) for t in all_trades)


def test_run_universe_fixed_notional_time_exit_experiment_isolates_a_failing_symbol(_fake_universe_provider):
    _fake_universe_provider({"AAA", "^NSEI"})

    result = run_universe_fixed_notional_time_exit_experiment(["AAA", "BADSYMBOL"], capital_per_slot=100_000.0)

    assert "BADSYMBOL" in result.failed_symbols
    assert "AAA" not in result.failed_symbols


def test_run_universe_fixed_notional_time_exit_experiment_never_overlaps_positions(_fake_universe_provider):
    """One position at a time per symbol: no two trades for the same
    symbol/period should have overlapping entry/exit windows."""
    _fake_universe_provider({"AAA", "^NSEI"})

    result = run_universe_fixed_notional_time_exit_experiment(["AAA"], capital_per_slot=100_000.0, max_holding_bars=10)

    for trades in (result.development_trades, result.validation_trades, result.out_of_sample_trades):
        sorted_trades = sorted(trades, key=lambda t: t.entry_time)
        for prev, cur in zip(sorted_trades, sorted_trades[1:]):
            assert cur.entry_time > prev.exit_time
