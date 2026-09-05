from datetime import datetime, timedelta

import pandas as pd
import pytest

from backtesting.forensics import (
    breakdown_by_exit_reason,
    compute_trade_excursion,
    summarize_excursions,
)
from backtesting.trade import ExitReason, Trade
from strategy.signal import Side


def _series(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """(open, high, low, close) rows, one per day starting 2026-01-01."""
    index = [datetime(2026, 1, 1) + timedelta(days=i) for i in range(len(rows))]
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=index)


def _trade(*, entry_time, exit_time, entry_price=100.0, stop_price=90.0, net_pnl=50.0, exit_reason=ExitReason.TARGET, r_multiple=1.0) -> Trade:
    return Trade(
        symbol="TEST", side=Side.LONG, strategy_name="unit-test", signal_generated_at=entry_time,
        entry_time=entry_time, entry_price=entry_price, quantity=10, stop_price=stop_price, target_price=120.0,
        exit_time=exit_time, exit_price=entry_price + net_pnl / 10, exit_reason=exit_reason,
        gross_pnl=net_pnl, costs=0.0, net_pnl=net_pnl, r_multiple=r_multiple,
    )


# --- compute_trade_excursion ---------------------------------------------------


def test_compute_trade_excursion_known_mfe_and_mae():
    series = _series([
        (100.0, 101.0, 99.0, 100.0),   # day 0: entry
        (100.0, 115.0, 95.0, 110.0),   # day 1: high 115 (mfe), low 95 (mae)
        (110.0, 112.0, 108.0, 109.0),  # day 2: exit
    ])
    t0, t2 = series.index[0], series.index[2]
    trade = _trade(entry_time=t0, exit_time=t2, entry_price=100.0)

    excursion = compute_trade_excursion(trade, series)

    assert excursion is not None
    assert excursion.mfe_pct == pytest.approx((115.0 - 100.0) / 100.0)
    assert excursion.mae_pct == pytest.approx((100.0 - 95.0) / 100.0)
    assert excursion.bars_held == 3


def test_compute_trade_excursion_returns_none_when_window_has_no_bars():
    series = _series([(100.0, 101.0, 99.0, 100.0)])
    far_future = datetime(2030, 1, 1)
    trade = _trade(entry_time=far_future, exit_time=far_future + timedelta(days=1))

    assert compute_trade_excursion(trade, series) is None


def test_compute_trade_excursion_never_negative():
    # A trade that only ever moved in ONE direction still has a
    # well-defined (zero, not negative) opposite excursion.
    series = _series([(100.0, 100.0, 100.0, 100.0), (100.0, 105.0, 100.0, 105.0)])
    t0, t1 = series.index[0], series.index[1]
    trade = _trade(entry_time=t0, exit_time=t1, entry_price=100.0)

    excursion = compute_trade_excursion(trade, series)

    assert excursion is not None
    assert excursion.mae_pct == 0.0


# --- breakdown_by_exit_reason ---------------------------------------------------


def test_breakdown_by_exit_reason_separates_stop_target_and_end_of_data():
    t0 = datetime(2026, 1, 1)
    trades = [
        _trade(entry_time=t0, exit_time=t0, exit_reason=ExitReason.STOP, net_pnl=-100.0, r_multiple=-1.0),
        _trade(entry_time=t0, exit_time=t0, exit_reason=ExitReason.STOP, net_pnl=-100.0, r_multiple=-1.0),
        _trade(entry_time=t0, exit_time=t0, exit_reason=ExitReason.TARGET, net_pnl=200.0, r_multiple=2.0),
        _trade(entry_time=t0, exit_time=t0, exit_reason=ExitReason.END_OF_DATA, net_pnl=10.0, r_multiple=0.1),
    ]

    buckets = breakdown_by_exit_reason(trades)

    by_reason = {b.exit_reason: b for b in buckets}
    assert by_reason[ExitReason.STOP].count == 2
    assert by_reason[ExitReason.STOP].win_rate_pct == 0.0
    assert by_reason[ExitReason.STOP].mean_net_pnl == pytest.approx(-100.0)
    assert by_reason[ExitReason.TARGET].count == 1
    assert by_reason[ExitReason.TARGET].win_rate_pct == 100.0
    assert by_reason[ExitReason.END_OF_DATA].count == 1
    # Ordered by count descending -- the two STOP trades outnumber the others.
    assert buckets[0].exit_reason == ExitReason.STOP


def test_breakdown_by_exit_reason_empty_for_no_trades():
    assert breakdown_by_exit_reason([]) == []


# --- summarize_excursions -------------------------------------------------------


def test_summarize_excursions_flags_losers_with_large_favorable_excursion():
    t0 = datetime(2026, 1, 1)
    # Loser with a big MFE relative to its own risk (entry 100, stop 90 ->
    # 10% initial risk; MFE of 8% is 80% of that risk -- flagged at the
    # default 50% threshold) -- a trade that WAS winning, then reversed.
    losing_trade_with_run_up = _trade(entry_time=t0, exit_time=t0, entry_price=100.0, stop_price=90.0, net_pnl=-50.0)

    from backtesting.forensics import TradeExcursion

    excursions = [
        TradeExcursion(trade=losing_trade_with_run_up, mfe_pct=0.08, mae_pct=0.10, bars_held=5),
        TradeExcursion(trade=_trade(entry_time=t0, exit_time=t0, entry_price=100.0, stop_price=90.0, net_pnl=-50.0), mfe_pct=0.01, mae_pct=0.10, bars_held=2),
        TradeExcursion(trade=_trade(entry_time=t0, exit_time=t0, entry_price=100.0, stop_price=90.0, net_pnl=50.0), mfe_pct=0.20, mae_pct=0.02, bars_held=3),
    ]

    summary = summarize_excursions(excursions)

    assert summary is not None
    assert summary.trade_count == 3
    assert summary.losers_with_large_mfe_count == 1  # only the first loser qualifies
    assert summary.losers_with_large_mfe_pct_of_losers == pytest.approx(50.0)  # 1 of 2 losers


def test_summarize_excursions_returns_none_for_empty_list():
    assert summarize_excursions([]) is None
