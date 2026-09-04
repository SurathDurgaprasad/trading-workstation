from backtesting.baselines import compute_buy_and_hold
from backtesting.costs import CostModel
from backtesting.engine import run_backtest
from backtesting.report import format_backtest_report
from strategy.signal import ReasonCode, Side, Signal
from tests.conftest import make_bar, make_indicator_series

_ZERO_COST = CostModel(brokerage_per_fill=0.0, fees_pct=0.0, taxes_pct=0.0, entry_slippage_bps=0.0, exit_slippage_bps=0.0)


class _OneShotStrategy:
    """Same minimal pattern as test_backtest_execution.py's own helper --
    emits exactly one fixed signal, nothing else."""

    name = "one_shot_test_strategy"

    def __init__(self, *, at_index: int, stop_price: float, target_price: float):
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


def _series_and_result(*, strategy_bars, stop_price=90.0, target_price=90_000.0):
    series = make_indicator_series(strategy_bars)
    strategy = _OneShotStrategy(at_index=0, stop_price=stop_price, target_price=target_price)
    result = run_backtest(
        symbol="TEST", indicator_series=series, strategy=strategy, cost_model=_ZERO_COST, initial_capital=1_000.0,
    )
    return series, result


def test_baseline_comparison_section_shows_strategy_beating_buy_and_hold():
    # Strategy enters at bar 1's open (100.0) and target is set far away so
    # it never exits within this short series -- the backtest's own
    # open-position-still-active accounting isn't the point here, only that
    # the report's baseline section renders and compares correctly.
    bars = [
        make_bar(close=100.0),
        make_bar(open=100.0, high=101.0, low=99.0, close=100.5),
        make_bar(open=100.5, high=102.0, low=100.0, close=101.0),
    ]
    series, result = _series_and_result(strategy_bars=bars)
    baseline = compute_buy_and_hold(series, symbol="TEST", initial_capital=1_000.0)
    assert baseline is not None

    report = format_backtest_report(result, full_baseline=baseline)

    assert "BASELINE COMPARISON" in report
    assert f"buy & hold net PnL {baseline.net_pnl:,.2f}" in report
    assert "strategy beats buy & hold" in report or "strategy does NOT beat buy & hold" in report


def test_baseline_comparison_section_says_not_computed_when_baseline_is_none():
    bars = [make_bar(close=100.0), make_bar(open=100.0, high=101.0, low=99.0, close=100.5)]
    _, result = _series_and_result(strategy_bars=bars)

    report = format_backtest_report(result)

    assert "BASELINE COMPARISON" in report
    assert "(not computed" in report


def test_baseline_comparison_reports_all_four_periods_independently():
    bars = [make_bar(close=100.0), make_bar(open=100.0, high=101.0, low=99.0, close=100.5)]
    series, result = _series_and_result(strategy_bars=bars)
    baseline = compute_buy_and_hold(series, symbol="TEST", initial_capital=1_000.0)

    report = format_backtest_report(
        result, development=result, validation=None, out_of_sample=result,
        full_baseline=baseline, development_baseline=baseline, validation_baseline=None, out_of_sample_baseline=baseline,
    )

    assert report.count(f"buy & hold net PnL {baseline.net_pnl:,.2f}") == 3  # Full, Development, Out-of-Sample
    assert "(not computed" in report  # Validation, deliberately baseline=None
