"""Spec §9 (Phase 4.5): daily-loss behaviour proven through the actual
run_backtest loop with real multi-day timestamps — not just Account-level
unit tests (already covered in test_risk_account.py/test_risk_gates.py).
This proves account.roll_to_day() is wired correctly into engine.py itself,
and that no future day's information leaks into an earlier day's decision.
"""

from datetime import datetime

from backtesting.costs import CostModel
from backtesting.engine import run_backtest
from risk.config import RiskConfig
from strategy.signal import ReasonCode, Side, Signal
from tests.conftest import make_bar, make_indicator_series

_ZERO_COST = CostModel(brokerage_per_fill=0, fees_pct=0, taxes_pct=0, entry_slippage_bps=0, exit_slippage_bps=0)


class _ScriptedStrategy:
    """Fires a fixed, hand-picked Signal at exactly the given bar indices —
    lets the day-boundary test control precisely when trades are attempted,
    independent of TrendMomentumBaseline's own entry logic."""

    name = "scripted_test_strategy"

    def __init__(self, fire_at: set[int], *, stop_price: float, target_price: float):
        self._fire_at = fire_at
        self._stop_price = stop_price
        self._target_price = target_price
        self._fired = set()

    def generate_signal(self, indicator_series, index, symbol):
        if index not in self._fire_at or index in self._fired:
            return None
        self._fired.add(index)
        row = indicator_series.iloc[index]
        return Signal(
            symbol=symbol,
            generated_at=indicator_series.index[index],
            side=Side.LONG,
            reference_price=float(row["close"]),
            stop_price=self._stop_price,
            target_price=self._target_price,
            risk_reward=2.0,
            strategy_name=self.name,
            reason_codes=[ReasonCode.TREND_CONFIRMED],
        )


def test_daily_loss_halt_engages_within_a_day_and_clears_on_the_next_calendar_day():
    # Day 1: two losing round-trips, each big enough that the second alone
    # (or the pair) crosses a 3% daily-loss limit. Day 2: a fresh, otherwise
    # identical opportunity must be allowed to trade again.
    bars = []
    # bar 0: signal bar (flat close, qualifies structurally)
    bars.append(make_bar(close=100.0, open=100.0, high=100.5, low=99.5))
    # bar 1 (day 1): entry at open=100, stops out same bar at 90 -> big loss
    bars.append(make_bar(close=91.0, open=100.0, high=100.5, low=89.0))
    # bar 2 (day 1): signal bar again
    bars.append(make_bar(close=100.0, open=100.0, high=100.5, low=99.5))
    # bar 3 (day 1): entry, stops out again -> compounds the daily loss past 3%
    bars.append(make_bar(close=91.0, open=100.0, high=100.5, low=89.0))
    # bar 4 (day 1): a THIRD signal bar, still day 1 -> must be rejected (daily loss breached)
    bars.append(make_bar(close=100.0, open=100.0, high=100.5, low=99.5))
    # bar 5 (day 1): would-be entry bar (irrelevant if bar 4's signal is rejected)
    bars.append(make_bar(close=100.0, open=100.0, high=100.5, low=99.5))
    # bar 6 (day 2): a fresh signal bar on the new day -> must be allowed again
    bars.append(make_bar(close=100.0, open=100.0, high=100.5, low=99.5))
    # bar 7 (day 2): entry bar for bar 6's signal, no stop/target hit -> stays open
    bars.append(make_bar(close=100.0, open=100.0, high=105.0, low=99.5))

    index = [datetime(2026, 1, 1, 9), datetime(2026, 1, 1, 10), datetime(2026, 1, 1, 11),
             datetime(2026, 1, 1, 12), datetime(2026, 1, 1, 13), datetime(2026, 1, 1, 14),
             datetime(2026, 1, 2, 9), datetime(2026, 1, 2, 10)]
    series = make_indicator_series(bars)
    series.index = index

    strategy = _ScriptedStrategy(fire_at={0, 2, 4, 6}, stop_price=90.0, target_price=200.0)
    # risk_per_trade_pct raised so two full stop-outs (~2% of equity each)
    # actually compound past the 3% daily-loss limit within one day.
    risk_config = RiskConfig(
        risk_per_trade_pct=2.0, max_daily_loss_pct=3.0, max_drawdown_pct=100.0,
        max_consecutive_losses=100, consecutive_loss_hard_limit=100,
    )

    result = run_backtest(
        symbol="TEST", indicator_series=series, strategy=strategy,
        cost_model=_ZERO_COST, risk_config=risk_config, initial_capital=100_000.0,
    )

    records_by_bar_index = {series.index.get_loc(r.timestamp): r for r in result.signal_records}

    # bars 0 and 2 (day 1, before the loss accumulates past the limit): approved.
    assert records_by_bar_index[0].decision.approved
    assert records_by_bar_index[2].decision.approved

    # bar 4 (day 1, AFTER two losses breach the daily limit): rejected for MAX_DAILY_LOSS.
    from risk.veto import VetoReason
    assert not records_by_bar_index[4].decision.approved
    assert VetoReason.MAX_DAILY_LOSS in records_by_bar_index[4].decision.veto_reasons

    # bar 6 (day 2, a NEW calendar day): approved again -- the halt cleared.
    assert records_by_bar_index[6].decision.approved


def test_no_future_days_daily_loss_state_leaks_into_an_earlier_days_decision():
    """The engine processes bars strictly chronologically -- a day-3 loss
    must never be visible to a day-1 evaluation. Proven directly: mutate
    only a later day's bars and confirm the earlier day's recorded decision
    is unchanged."""
    def build(mutate_future: bool):
        bars = [
            make_bar(close=100.0, open=100.0, high=100.5, low=99.5),   # day1 bar0: signal
            make_bar(close=100.0, open=100.0, high=105.0, low=99.5),   # day1 bar1: entry, holds
            make_bar(close=100.0, open=100.0, high=100.5, low=99.5),   # day2 bar2: signal
            make_bar(
                close=(50.0 if mutate_future else 100.0), open=100.0,
                high=105.0, low=(40.0 if mutate_future else 99.5),
            ),  # day3 bar3: a huge future crash, only if mutate_future
        ]
        index = [
            datetime(2026, 1, 1, 9), datetime(2026, 1, 1, 10),
            datetime(2026, 1, 2, 9), datetime(2026, 1, 3, 9),
        ]
        series = make_indicator_series(bars)
        series.index = index
        strategy = _ScriptedStrategy(fire_at={0}, stop_price=90.0, target_price=200.0)
        return run_backtest(
            symbol="TEST", indicator_series=series, strategy=strategy,
            cost_model=_ZERO_COST, risk_config=RiskConfig(), initial_capital=100_000.0,
        )

    baseline = build(mutate_future=False)
    mutated = build(mutate_future=True)

    day1_decision_baseline = baseline.signal_records[0].decision
    day1_decision_mutated = mutated.signal_records[0].decision
    assert day1_decision_baseline.model_dump() == day1_decision_mutated.model_dump()
