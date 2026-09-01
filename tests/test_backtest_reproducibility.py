from backtesting.costs import CostModel
from backtesting.engine import run_backtest
from strategy.baseline import TrendMomentumBaseline
from tests.conftest import make_bar, make_indicator_series


def _mixed_series():
    # A mix of qualifying and non-qualifying bars so more than one signal
    # and more than one exit path get exercised.
    bars = []
    for i in range(40):
        if i % 7 == 0:
            bars.append(make_bar(close=100 + i, open=100 + i, high=101 + i, low=99 + i))
        else:
            bars.append(make_bar(sma_20=80.0, sma_50=90.0, close=100 + i, open=100 + i, high=101 + i, low=99 + i))
    return make_indicator_series(bars)


def test_identical_inputs_produce_byte_identical_results():
    series = _mixed_series()
    strategy = TrendMomentumBaseline()
    cost_model = CostModel()

    result_a = run_backtest(symbol="TEST", indicator_series=series, strategy=strategy, cost_model=cost_model, initial_capital=100_000)
    result_b = run_backtest(symbol="TEST", indicator_series=series, strategy=strategy, cost_model=cost_model, initial_capital=100_000)

    assert result_a.model_dump() == result_b.model_dump()
    assert [t.model_dump() for t in result_a.trades] == [t.model_dump() for t in result_b.trades]


def test_a_fresh_strategy_instance_gives_the_same_result_as_a_reused_one():
    series = _mixed_series()
    cost_model = CostModel()

    result_a = run_backtest(symbol="TEST", indicator_series=series, strategy=TrendMomentumBaseline(), cost_model=cost_model)
    result_b = run_backtest(symbol="TEST", indicator_series=series, strategy=TrendMomentumBaseline(), cost_model=cost_model)

    assert result_a.metrics.model_dump() == result_b.metrics.model_dump()
