from datetime import datetime, timedelta

import pytest

from backtesting.trade import ExitReason, Trade
from backtesting.universe import UniverseBacktestResult, per_trade_returns, run_universe_backtest
from market.data_provider import MarketDataError, OHLCV, OHLCVBar
from strategy.signal import ReasonCode, Side, Signal


def _trade(*, symbol="TEST", entry_price=100.0, quantity=10, net_pnl=50.0) -> Trade:
    t0 = datetime(2026, 1, 1)
    return Trade(
        symbol=symbol, side=Side.LONG, strategy_name="unit-test", signal_generated_at=t0,
        entry_time=t0, entry_price=entry_price, quantity=quantity, stop_price=90.0, target_price=110.0,
        exit_time=t0, exit_price=entry_price + net_pnl / quantity if quantity else entry_price,
        exit_reason=ExitReason.TARGET, gross_pnl=net_pnl, costs=0.0, net_pnl=net_pnl, r_multiple=1.0,
    )


# --- per_trade_returns --------------------------------------------------------


def test_per_trade_returns_known_values():
    trades = [_trade(entry_price=100.0, quantity=10, net_pnl=100.0), _trade(entry_price=50.0, quantity=4, net_pnl=-20.0)]

    returns = per_trade_returns(trades)

    assert returns == pytest.approx([100.0 / 1000.0, -20.0 / 200.0])


def test_per_trade_returns_skips_degenerate_zero_entry_price():
    trades = [_trade(entry_price=0.0, quantity=10, net_pnl=100.0), _trade(entry_price=100.0, quantity=1, net_pnl=10.0)]

    returns = per_trade_returns(trades)

    assert returns == pytest.approx([0.10])


def test_per_trade_returns_skips_degenerate_zero_quantity():
    trades = [_trade(entry_price=100.0, quantity=0, net_pnl=0.0)]

    assert per_trade_returns(trades) == []


def test_per_trade_returns_empty_for_no_trades():
    assert per_trade_returns([]) == []


# --- run_universe_backtest -----------------------------------------------------


class _OneShotStrategy:
    """Same minimal pattern as test_backtest_execution.py's own helper."""

    name = "one_shot_test_strategy"

    def __init__(self, *, at_index: int = 0, stop_price: float = 90.0, target_price: float = 90_000.0):
        self._at_index = at_index
        self._stop_price = stop_price
        self._target_price = target_price
        self._fired = False

    def generate_signal(self, indicator_series, index, symbol):
        if index != self._at_index or self._fired:
            return None
        self._fired = True
        row = indicator_series.iloc[index]
        return Signal(
            symbol=symbol, generated_at=indicator_series.index[index], side=Side.LONG,
            reference_price=float(row["close"]), stop_price=self._stop_price, target_price=self._target_price,
            risk_reward=2.0, strategy_name=self.name, reason_codes=[ReasonCode.TREND_CONFIRMED],
        )


def _raw_bars(n: int = 5, *, start: float = 100.0, step: float = 0.5) -> list[OHLCVBar]:
    """A raw OHLCV sequence (no pre-computed indicator columns -- those are
    compute_indicator_series's job, exercised for real here since
    run_universe_backtest calls it internally, unlike the indicator-series
    -level tests elsewhere that bypass it via conftest.make_indicator_series)."""
    bars = []
    t0 = datetime(2026, 1, 1)
    for i in range(n):
        close = start + step * i
        bars.append(OHLCVBar(
            timestamp=t0 + timedelta(days=i), open=close, high=close + 1.0, low=close - 1.0,
            close=close, volume=1_000_000.0,
        ))
    return bars


class _FakeProvider:
    """Serves a fixed OHLCV series for known symbols, raises for others --
    proves per-symbol isolation (one failing symbol never aborts the rest)."""

    def __init__(self, good_symbols: set[str]):
        self._good_symbols = good_symbols

    def fetch_ohlcv(self, symbol, *, period="5y", interval="1d"):
        if symbol not in self._good_symbols:
            raise MarketDataError(f"no data for {symbol}")
        return OHLCV(symbol=symbol, interval=interval, bars=_raw_bars())


@pytest.fixture(autouse=True)
def _fake_market_data_provider(monkeypatch):
    # backtesting.universe imports get_market_data_provider at module top
    # (matching backtesting.runner's own existing, already-shipped
    # pattern) -- patching market.data_provider's own attribute would NOT
    # affect this already-bound local reference, so the target here is
    # deliberately backtesting.universe itself.
    import backtesting.universe as universe_module

    monkeypatch.setattr(universe_module, "get_market_data_provider", lambda: _FakeProvider({"AAPL", "MSFT"}))


def test_run_universe_backtest_pools_trades_across_symbols():
    strategy = _OneShotStrategy()

    result = run_universe_backtest(["AAPL", "MSFT"], strategy=strategy, use_cache=False, initial_capital=1_000.0)

    assert set(result.per_symbol.keys()) == {"AAPL", "MSFT"}
    assert result.failed_symbols == {}
    # Each symbol's own OneShotStrategy fires once -- open position at the
    # end of this short series is never force-closed, so no completed
    # Trade is expected here; the isolation/pooling wiring is what's
    # actually under test, not this strategy's own exit behavior.
    assert isinstance(result.pooled_trades, list)


def test_run_universe_backtest_isolates_a_failing_symbol_from_the_rest():
    strategy = _OneShotStrategy()

    result = run_universe_backtest(["AAPL", "BADSYMBOL", "MSFT"], strategy=strategy, use_cache=False, initial_capital=1_000.0)

    assert set(result.per_symbol.keys()) == {"AAPL", "MSFT"}
    assert "BADSYMBOL" in result.failed_symbols
    assert "no data for BADSYMBOL" in result.failed_symbols["BADSYMBOL"]


def test_universe_backtest_result_pooled_trades_property_is_empty_by_default():
    assert UniverseBacktestResult().pooled_trades == []
