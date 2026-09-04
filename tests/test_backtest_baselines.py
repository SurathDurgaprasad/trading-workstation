from datetime import datetime, timedelta

import pandas as pd
import pytest

from backtesting.baselines import compute_buy_and_hold


def _series(closes: list[float], *, opens: list[float] | None = None) -> pd.DataFrame:
    opens = opens or closes
    index = [datetime(2026, 1, 1) + timedelta(days=i) for i in range(len(closes))]
    return pd.DataFrame({"open": opens, "close": closes}, index=index)


def test_compute_buy_and_hold_known_gain():
    # Entry at 100 (10 shares from 1,000 capital), exit at 120 -> +20% return.
    series = _series([100.0, 110.0, 90.0, 120.0])

    result = compute_buy_and_hold(series, symbol="TEST", initial_capital=1_000.0)

    assert result is not None
    assert result.entry_price == 100.0
    assert result.exit_price == 120.0
    assert result.quantity == 10
    assert result.net_pnl == pytest.approx(200.0)
    assert result.return_pct == pytest.approx(20.0)


def test_compute_buy_and_hold_known_loss():
    series = _series([100.0, 80.0])

    result = compute_buy_and_hold(series, symbol="TEST", initial_capital=1_000.0)

    assert result is not None
    assert result.net_pnl == pytest.approx(-200.0)
    assert result.return_pct == pytest.approx(-20.0)


def test_compute_buy_and_hold_max_drawdown_reflects_the_worst_intermediate_dip():
    # Entry 100 -> peak 150 (at 10 shares, equity 1500) -> dip to 90 (equity
    # 900, a 40% drawdown from the 1500 peak) -> recovers to 140. The final
    # return is positive, but the max drawdown must still reflect the real
    # intermediate dip, not just start-vs-end.
    series = _series([100.0, 150.0, 90.0, 140.0])

    result = compute_buy_and_hold(series, symbol="TEST", initial_capital=1_000.0)

    assert result is not None
    assert result.max_drawdown_pct == pytest.approx(40.0)


def test_compute_buy_and_hold_uses_first_bars_open_not_close():
    # A gap-up open on bar 0 (open=100, close=105) must use 100 as the entry
    # price -- the earliest, most conservative real fill a buy-and-hold
    # investor could have gotten that day, not a same-bar close (look-ahead).
    series = _series([105.0, 110.0], opens=[100.0, 108.0])

    result = compute_buy_and_hold(series, symbol="TEST", initial_capital=1_000.0)

    assert result is not None
    assert result.entry_price == 100.0


def test_compute_buy_and_hold_returns_none_for_empty_series():
    assert compute_buy_and_hold(_series([]), symbol="TEST", initial_capital=1_000.0) is None


def test_compute_buy_and_hold_returns_none_when_capital_cannot_buy_one_share():
    series = _series([1_000_000.0, 1_100_000.0])

    assert compute_buy_and_hold(series, symbol="TEST", initial_capital=1_000.0) is None


def test_compute_buy_and_hold_returns_none_for_non_positive_entry_price():
    series = _series([0.0, 100.0], opens=[0.0, 100.0])

    assert compute_buy_and_hold(series, symbol="TEST", initial_capital=1_000.0) is None


def test_compute_buy_and_hold_carries_the_symbol_and_period_label_through():
    series = _series([100.0, 110.0])

    result = compute_buy_and_hold(series, symbol="RELIANCE.NS", initial_capital=1_000.0, period_label="out_of_sample")

    assert result is not None
    assert result.symbol == "RELIANCE.NS"
    assert result.period_label == "out_of_sample"
