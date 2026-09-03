"""Phase 41 -- learning.profitability: pure functions over already-
evaluated predictions. No store, no network, no config anywhere in this
file."""

from datetime import datetime, timedelta, timezone

import pytest

from decision_engine.models import Decision, DecisionLabel, RiskContext
from learning.analysis import EvaluatedPrediction
from learning.profitability import (
    MIN_SAMPLE_SIZE_FOR_A_VERDICT,
    ProfitabilityReport,
    ProfitabilityVerdict,
    _max_drawdown,
    _wilson_score_interval,
    compute_profitability_report,
    compute_sector_performance,
)
from market_intelligence.models import CandidateScore
from predictions.models import PredictionEvaluation, PredictionOutcomeState, PredictionRecord
from research.models import ResearchReport, SectorInfo

_START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _candidate() -> CandidateScore:
    return CandidateScore(
        symbol="AAPL", as_of=datetime(2024, 1, 1), last_close=100.0, avg_daily_value=1_000_000.0, volume_ratio=1.1,
        trend_score=1.0, momentum_score=0.5, breakout_score=0.01, relative_strength_score=0.02,
        sector_strength_score=None, composite_score=1.5, explanation=["fake"],
    )


def _decision(decision_id: str, *, sector: str | None = None) -> Decision:
    research = None
    if sector is not None:
        research = ResearchReport(
            report_id="r1", symbol="AAPL", as_of=_START, news=[],
            sector=SectorInfo(symbol="AAPL", sector=sector, industry=None, as_of=_START),
            ai_summary=None, ai_summary_unavailable_reason=None,
        )
    return Decision(
        decision_id=decision_id, symbol="AAPL", as_of=_START, label=DecisionLabel.BUY,
        rationale=["fake"], config_version="cfg-A", scanner_evidence=_candidate(), research_evidence=research,
        market_context=None, risk_context=RiskContext.unknown(), narrative=None, narrative_unavailable_reason=None,
    )


def _item(i: int, actual_return: float | None, *, outcome=PredictionOutcomeState.TARGET_HIT, decision=None) -> EvaluatedPrediction:
    prediction = PredictionRecord(
        prediction_id=f"p{i}", decision_id=f"d{i}", symbol="AAPL", created_at=_START + timedelta(days=i),
        label=DecisionLabel.BUY, entry_price=100.0, stop_price=95.0, target_price=110.0,
        entry_time=_START + timedelta(days=i), horizon_bars=20, interval="1d",
    )
    evaluation = PredictionEvaluation(
        evaluation_id=f"e{i}", prediction_id=f"p{i}", evaluated_at=_START + timedelta(days=i, hours=1),
        outcome=outcome, bars_observed=5, exit_time=None, exit_price=None, actual_return=actual_return,
        max_favorable_excursion=0.05, max_adverse_excursion=0.01, detail="test",
    )
    return EvaluatedPrediction(prediction=prediction, evaluation=evaluation, decision=decision)


# --- verdict logic -------------------------------------------------------------


def test_empty_items_returns_the_empty_report():
    report = compute_profitability_report([])
    assert report.verdict == ProfitabilityVerdict.INSUFFICIENT_DATA
    assert report.sample_size == 0
    assert report == ProfitabilityReport.empty()


def test_below_minimum_sample_size_is_insufficient_data():
    items = [_item(i, 0.05) for i in range(MIN_SAMPLE_SIZE_FOR_A_VERDICT - 1)]
    report = compute_profitability_report(items)
    assert report.verdict == ProfitabilityVerdict.INSUFFICIENT_DATA
    assert report.sample_size == MIN_SAMPLE_SIZE_FOR_A_VERDICT - 1


def test_consistently_positive_returns_at_minimum_sample_size_is_positive_performance():
    items = [_item(i, 0.05) for i in range(MIN_SAMPLE_SIZE_FOR_A_VERDICT)]
    report = compute_profitability_report(items)
    assert report.verdict == ProfitabilityVerdict.POSITIVE_PERFORMANCE
    assert report.mean_return_ci_low > 0


def test_consistently_negative_returns_is_negative_performance():
    items = [_item(i, -0.05) for i in range(MIN_SAMPLE_SIZE_FOR_A_VERDICT)]
    report = compute_profitability_report(items)
    assert report.verdict == ProfitabilityVerdict.NEGATIVE_PERFORMANCE
    assert report.mean_return_ci_high < 0


def test_noisy_near_zero_returns_is_statistically_meaningless():
    # Alternating +/- large swings around a near-zero mean -- high variance,
    # so the CI for the mean must straddle zero even at n=40.
    items = [_item(i, 0.20 if i % 2 == 0 else -0.19) for i in range(40)]
    report = compute_profitability_report(items)
    assert report.verdict == ProfitabilityVerdict.STATISTICALLY_MEANINGLESS
    assert report.mean_return_ci_low <= 0.0 <= report.mean_return_ci_high


def test_unresolved_predictions_are_excluded_from_the_sample():
    resolved = [_item(i, 0.05) for i in range(MIN_SAMPLE_SIZE_FOR_A_VERDICT)]
    active = [_item(100 + i, None, outcome=PredictionOutcomeState.ACTIVE) for i in range(5)]
    report = compute_profitability_report(resolved + active)
    assert report.sample_size == MIN_SAMPLE_SIZE_FOR_A_VERDICT  # the 5 ACTIVE ones never counted


# --- descriptive statistics -----------------------------------------------------


def test_average_win_and_loss_and_expectancy_are_computed_correctly():
    # 20 wins at +10%, 10 losses at -5% -> win_rate=2/3, avg_win=0.10, avg_loss=-0.05
    items = [_item(i, 0.10) for i in range(20)] + [_item(20 + i, -0.05) for i in range(10)]
    report = compute_profitability_report(items)

    assert report.win_rate == pytest.approx(20 / 30)
    assert report.average_win == pytest.approx(0.10)
    assert report.average_loss == pytest.approx(-0.05)
    expected_expectancy = (20 / 30) * 0.10 + (10 / 30) * (-0.05)
    assert report.expectancy == pytest.approx(expected_expectancy)


def test_expectancy_equals_the_true_mean_return_even_with_a_breakeven_trade():
    """Regression: a return of exactly 0.0 counts in neither
    average_win (r>0) nor average_loss (r<0) -- expectancy must still
    equal the exact mean of ALL resolved returns, not the win/loss
    decomposition (which would silently drop the breakeven trade's
    weight and diverge from the true mean)."""
    items = [_item(i, 0.10) for i in range(10)] + [_item(10 + i, -0.10) for i in range(10)] + [_item(20, 0.0)]
    report = compute_profitability_report(items)

    true_mean = (10 * 0.10 + 10 * (-0.10) + 0.0) / 21
    assert report.expectancy == pytest.approx(true_mean)
    assert report.expectancy == pytest.approx(0.0)

    wrong_decomposed_formula = report.win_rate * report.average_win + (1 - report.win_rate) * report.average_loss
    assert report.expectancy != pytest.approx(wrong_decomposed_formula)  # proves the two formulas genuinely diverge here


def test_profit_factor_matches_learning_analysis_formula():
    items = [_item(i, 0.10) for i in range(20)] + [_item(20 + i, -0.05) for i in range(10)]
    report = compute_profitability_report(items)
    gains = 20 * 0.10
    losses = 10 * 0.05
    assert report.profit_factor == pytest.approx(gains / losses)


def test_max_drawdown_on_a_known_sequence():
    # +10%, +10%, -30%, +5% -- equity: 1.10, 1.21, 0.847, 0.8894
    # peak reaches 1.21, trough after the -30% is 0.847 -> drawdown = (1.21-0.847)/1.21
    dd = _max_drawdown([0.10, 0.10, -0.30, 0.05])
    assert dd == pytest.approx((1.21 - 0.847) / 1.21, rel=1e-3)


def test_max_drawdown_is_zero_for_an_all_winning_sequence():
    assert _max_drawdown([0.05, 0.05, 0.05]) == pytest.approx(0.0)


def test_max_drawdown_none_for_empty_sequence():
    assert _max_drawdown([]) is None


def test_wilson_score_interval_contains_the_point_estimate_and_is_within_bounds():
    low, high = _wilson_score_interval(21, 30)
    assert 0.0 <= low <= 21 / 30 <= high <= 1.0


def test_wilson_score_interval_handles_zero_trials():
    assert _wilson_score_interval(0, 0) == (0.0, 1.0)


def test_return_volatility_is_none_for_a_single_resolved_prediction():
    report = compute_profitability_report([_item(0, 0.05)])
    assert report.sample_size == 1
    assert report.return_volatility is None  # stdev needs at least 2 points
    assert report.verdict == ProfitabilityVerdict.INSUFFICIENT_DATA


def test_profitability_report_is_frozen():
    report = compute_profitability_report([])
    with pytest.raises(Exception):
        report.verdict = ProfitabilityVerdict.POSITIVE_PERFORMANCE


# --- sector performance ----------------------------------------------------------


def test_sector_performance_groups_by_recorded_sector():
    tech = _decision("d1", sector="Technology")
    healthcare = _decision("d2", sector="Healthcare")
    items = [
        _item(0, 0.10, decision=tech),
        _item(1, -0.05, decision=tech),
        _item(2, 0.20, decision=healthcare),
    ]
    result = compute_sector_performance(items)
    by_sector = {s.sector: s for s in result}
    assert by_sector["Technology"].total == 2
    assert by_sector["Technology"].win_rate == pytest.approx(0.5)
    assert by_sector["Healthcare"].total == 1
    assert by_sector["Healthcare"].win_rate == pytest.approx(1.0)


def test_sector_performance_groups_missing_sector_as_unknown():
    no_sector_decision = _decision("d1", sector=None)
    items = [_item(0, 0.10, decision=no_sector_decision), _item(1, 0.05, decision=None)]
    result = compute_sector_performance(items)
    assert len(result) == 1
    assert result[0].sector == "Unknown"
    assert result[0].total == 2


def test_sector_performance_empty_for_no_items():
    assert compute_sector_performance([]) == []
