"""H_MEANREV_008: tests for quant_research/risk_characterization.py --
summarize_forward_return_risk, the one new piece of production code
this hypothesis needs.
"""
import pytest

from quant_research.risk_characterization import summarize_forward_return_risk


def test_empty_returns_yields_all_none():
    s = summarize_forward_return_risk([], condition="c", market="NSE", horizon_bars=10)
    assert s.sample_size == 0
    assert s.p10 is None
    assert s.downside_deviation is None
    assert s.expected_shortfall_5pct is None
    assert s.loss_given_loss is None
    assert s.gain_given_win is None
    assert s.mean_to_downside_deviation is None


def test_percentiles_computed_correctly():
    returns = [float(x) for x in range(1, 101)]  # 1..100
    s = summarize_forward_return_risk(returns, condition="c", market="NSE", horizon_bars=10)
    assert s.sample_size == 100
    assert s.minimum == 1.0
    assert s.maximum == 100.0
    assert s.p10 == pytest.approx(10.9, abs=0.5)
    assert s.p90 == pytest.approx(90.1, abs=0.5)


def test_downside_deviation_uses_only_negative_returns():
    returns = [-0.10, -0.05, 0.02, 0.03, 0.04]
    s = summarize_forward_return_risk(returns, condition="c", market="NSE", horizon_bars=10)
    # downside deviation computed only over [-0.10, -0.05]
    import statistics
    expected = statistics.stdev([-0.10, -0.05])
    assert s.downside_deviation == pytest.approx(expected)


def test_downside_deviation_none_when_fewer_than_two_losses():
    returns = [-0.10, 0.02, 0.03, 0.04]
    s = summarize_forward_return_risk(returns, condition="c", market="NSE", horizon_bars=10)
    assert s.downside_deviation is None  # only 1 loss -- stdev undefined


def test_downside_deviation_none_when_no_losses():
    returns = [0.01, 0.02, 0.03]
    s = summarize_forward_return_risk(returns, condition="c", market="NSE", horizon_bars=10)
    assert s.downside_deviation is None
    assert s.loss_given_loss is None


def test_loss_given_loss_and_gain_given_win():
    returns = [-0.10, -0.20, 0.05, 0.15]
    s = summarize_forward_return_risk(returns, condition="c", market="NSE", horizon_bars=10)
    assert s.loss_given_loss == pytest.approx(-0.15)
    assert s.gain_given_win == pytest.approx(0.10)


def test_expected_shortfall_none_below_minimum_sample_size():
    returns = [-0.10] * 50 + [0.05] * 50  # n=100, below the 400 floor
    s = summarize_forward_return_risk(returns, condition="c", market="NSE", horizon_bars=10)
    assert s.expected_shortfall_5pct is None


def test_expected_shortfall_computed_above_minimum_sample_size():
    returns = [-1.0] * 20 + [0.01] * 380  # n=400, worst 5% (20 obs) are all -1.0
    s = summarize_forward_return_risk(returns, condition="c", market="NSE", horizon_bars=10)
    assert s.expected_shortfall_5pct is not None
    assert s.expected_shortfall_5pct == pytest.approx(-1.0, abs=0.05)


def test_mean_to_downside_deviation_ratio():
    returns = [-0.05, -0.15, 0.20, 0.20, 0.20]
    s = summarize_forward_return_risk(returns, condition="c", market="NSE", horizon_bars=10)
    mean_return = sum(returns) / len(returns)
    assert s.downside_deviation is not None and s.downside_deviation != 0
    assert s.mean_to_downside_deviation == pytest.approx(mean_return / s.downside_deviation)


def test_mean_to_downside_deviation_none_when_downside_deviation_none():
    returns = [0.01, 0.02, 0.03]  # no losses
    s = summarize_forward_return_risk(returns, condition="c", market="NSE", horizon_bars=10)
    assert s.mean_to_downside_deviation is None
