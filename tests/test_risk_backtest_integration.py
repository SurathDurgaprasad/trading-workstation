from backtesting.costs import CostModel
from backtesting.engine import run_backtest
from risk.config import RiskConfig
from strategy.baseline import TrendMomentumBaseline
from tests.conftest import make_bar, make_indicator_series


def _mixed_series(n: int = 60):
    bars = []
    for i in range(n):
        if i % 6 == 0:
            bars.append(make_bar(close=100 + i, open=100 + i, high=101 + i, low=99 + i))
        else:
            bars.append(make_bar(sma_20=80.0, sma_50=90.0, close=100 + i, open=100 + i, high=101 + i, low=99 + i))
    return make_indicator_series(bars)


def test_run_backtest_reproduces_identically_with_a_risk_engine_attached():
    series = _mixed_series()
    strategy = TrendMomentumBaseline()
    risk_config = RiskConfig()

    result_a = run_backtest(symbol="TEST", indicator_series=series, strategy=strategy, risk_config=risk_config)
    result_b = run_backtest(symbol="TEST", indicator_series=series, strategy=strategy, risk_config=risk_config)

    assert result_a.model_dump() == result_b.model_dump()


def test_aggressive_drawdown_limit_actually_vetoes_trades():
    """Demonstrates the risk layer is operational, not decorative (spec §29):
    an artificially tiny max_drawdown should produce rejections once the
    account has taken any real loss, without touching the strategy at all."""
    series = _mixed_series(n=80)
    strategy = TrendMomentumBaseline()  # unchanged

    permissive = run_backtest(
        symbol="TEST", indicator_series=series, strategy=strategy,
        risk_config=RiskConfig(max_drawdown_pct=100.0, max_daily_loss_pct=100.0, max_exposure_pct=100.0),
    )
    aggressive = run_backtest(
        symbol="TEST", indicator_series=series, strategy=strategy,
        risk_config=RiskConfig(max_drawdown_pct=0.01),  # effectively zero tolerance
    )

    assert permissive.risk_summary.signals_generated == aggressive.risk_summary.signals_generated
    assert aggressive.risk_summary.signals_rejected > permissive.risk_summary.signals_rejected
    assert len(aggressive.trades) <= len(permissive.trades)


def test_aggressive_exposure_limit_rejects_every_signal_deterministically():
    series = _mixed_series(n=40)
    strategy = TrendMomentumBaseline()

    result = run_backtest(
        symbol="TEST", indicator_series=series, strategy=strategy,
        risk_config=RiskConfig(max_exposure_pct=0.001),  # unattainable
    )

    assert result.risk_summary.signals_generated > 0
    assert result.trades == []
    assert result.risk_summary.rejections_by_reason  # something was recorded as a reason
    from risk.veto import VetoReason
    assert VetoReason.MAX_EXPOSURE in result.risk_summary.rejections_by_reason


def test_risk_summary_signal_count_matches_number_of_flat_bars_the_strategy_qualified_on():
    series = _mixed_series(n=40)
    strategy = TrendMomentumBaseline()

    result = run_backtest(symbol="TEST", indicator_series=series, strategy=strategy)
    assert result.risk_summary.signals_generated == len(result.signal_records)
    assert result.risk_summary.signals_approved + result.risk_summary.signals_rejected == result.risk_summary.signals_generated
