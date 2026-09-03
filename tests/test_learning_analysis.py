from datetime import datetime, timedelta, timezone

from decision_engine.models import Decision, DecisionLabel, RiskContext
from learning.analysis import (
    EvaluatedPrediction,
    build_learning_report,
    compare_by_config_version,
    compute_confidence_calibration,
    compute_regime_performance,
    compute_signal_quality,
)
from learning.regime import MarketRegime
from market.data_provider import OHLCV, OHLCVBar
from market_intelligence.models import CandidateScore
from predictions.models import PredictionEvaluation, PredictionOutcomeState, PredictionRecord

_START = datetime(2024, 1, 2)


def _candidate(composite: float = 1.0) -> CandidateScore:
    return CandidateScore(
        symbol="AAPL", as_of=_START, last_close=100.0, avg_daily_value=1_000_000.0, volume_ratio=1.1,
        trend_score=1.0, momentum_score=0.5, breakout_score=0.01, relative_strength_score=0.02,
        sector_strength_score=None, composite_score=composite, explanation=["fake"],
    )


def _decision(decision_id: str, *, config_version: str = "cfg1", composite: float | None = 1.0) -> Decision:
    return Decision(
        decision_id=decision_id, symbol="AAPL", as_of=datetime(2024, 1, 2, tzinfo=timezone.utc), label=DecisionLabel.BUY,
        rationale=["fake"], config_version=config_version,
        scanner_evidence=_candidate(composite) if composite is not None else None,
        research_evidence=None, market_context=None, risk_context=RiskContext.unknown(),
        narrative=None, narrative_unavailable_reason=None,
    )


def _prediction(prediction_id: str, decision_id: str, *, symbol: str = "AAPL") -> PredictionRecord:
    return PredictionRecord(
        prediction_id=prediction_id, decision_id=decision_id, symbol=symbol, created_at=datetime.now(timezone.utc),
        label=DecisionLabel.BUY, entry_price=100.0, stop_price=95.0, target_price=110.0, entry_time=_START,
        horizon_bars=20, interval="1d",
    )


def _evaluation(
    prediction_id: str, outcome: PredictionOutcomeState, *, actual_return: float | None = None,
    mfe: float | None = 0.0, mae: float | None = 0.0,
) -> PredictionEvaluation:
    return PredictionEvaluation(
        evaluation_id=f"eval-{prediction_id}", prediction_id=prediction_id, evaluated_at=datetime.now(timezone.utc),
        outcome=outcome, bars_observed=1, exit_time=None, exit_price=None, actual_return=actual_return,
        max_favorable_excursion=mfe, max_adverse_excursion=mae, detail="test",
    )


class _FakeProvider:
    def __init__(self, ohlcv_by_symbol: dict[str, OHLCV]):
        self._ohlcv_by_symbol = ohlcv_by_symbol

    def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
        return self._ohlcv_by_symbol[symbol]


def _rising_ohlcv(symbol: str, n: int = 250) -> OHLCV:
    bars = [
        OHLCVBar(timestamp=_START + timedelta(days=i), open=100 + i * 0.5, high=101 + i * 0.5, low=99 + i * 0.5, close=100 + i * 0.5, volume=1000.0)
        for i in range(n)
    ]
    return OHLCV(symbol=symbol, interval="1d", bars=bars)


# --- compare_by_config_version -----------------------------------------------


def test_compare_by_config_version_groups_correctly():
    items = [
        EvaluatedPrediction(_prediction("p1", "d1"), _evaluation("p1", PredictionOutcomeState.TARGET_HIT, actual_return=0.10), _decision("d1", config_version="cfgA")),
        EvaluatedPrediction(_prediction("p2", "d2"), _evaluation("p2", PredictionOutcomeState.STOP_HIT, actual_return=-0.05), _decision("d2", config_version="cfgA")),
        EvaluatedPrediction(_prediction("p3", "d3"), _evaluation("p3", PredictionOutcomeState.TARGET_HIT, actual_return=0.08), _decision("d3", config_version="cfgB")),
    ]
    result = compare_by_config_version(items)
    by_version = {r.config_version: r for r in result}

    assert by_version["cfgA"].total == 2
    assert by_version["cfgA"].win_rate == 0.5
    assert by_version["cfgB"].total == 1
    assert by_version["cfgB"].win_rate == 1.0


def test_compare_by_config_version_excludes_items_with_no_decision():
    items = [
        EvaluatedPrediction(_prediction("p1", "d1"), _evaluation("p1", PredictionOutcomeState.TARGET_HIT, actual_return=0.1), None),
        EvaluatedPrediction(_prediction("p2", "d2"), _evaluation("p2", PredictionOutcomeState.TARGET_HIT, actual_return=0.1), _decision("d2")),
    ]
    result = compare_by_config_version(items)
    assert sum(r.total for r in result) == 1


def test_compare_by_config_version_handles_no_resolved_predictions():
    items = [EvaluatedPrediction(_prediction("p1", "d1"), _evaluation("p1", PredictionOutcomeState.ACTIVE), _decision("d1"))]
    result = compare_by_config_version(items)
    assert result[0].win_rate is None
    assert result[0].profit_factor is None


# --- compute_regime_performance -----------------------------------------------


def test_compute_regime_performance_classifies_and_groups():
    provider = _FakeProvider({"AAPL": _rising_ohlcv("AAPL")})
    items = [
        EvaluatedPrediction(_prediction("p1", "d1"), _evaluation("p1", PredictionOutcomeState.TARGET_HIT, actual_return=0.1), _decision("d1")),
    ]
    # entry_time is _START, but the rising series only has ~1 bar at that point -> insufficient history -> UNKNOWN
    result = compute_regime_performance(items, provider=provider)
    assert result[0].regime == MarketRegime.UNKNOWN
    assert result[0].total == 1


# --- compute_confidence_calibration -------------------------------------------


def test_confidence_calibration_odd_count_median_goes_to_at_or_below():
    items = [
        EvaluatedPrediction(_prediction("p1", "d1"), _evaluation("p1", PredictionOutcomeState.TARGET_HIT, actual_return=0.1), _decision("d1", composite=1.0)),
        EvaluatedPrediction(_prediction("p2", "d2"), _evaluation("p2", PredictionOutcomeState.STOP_HIT, actual_return=-0.05), _decision("d2", composite=2.0)),
        EvaluatedPrediction(_prediction("p3", "d3"), _evaluation("p3", PredictionOutcomeState.TARGET_HIT, actual_return=0.2), _decision("d3", composite=3.0)),
    ]
    buckets = compute_confidence_calibration(items)
    above = next(b for b in buckets if b.bucket_label.startswith("Above"))
    at_or_below = next(b for b in buckets if b.bucket_label.startswith("At or below"))

    # median composite = 2.0 (the middle item) -> that item goes to at_or_below, only composite=3.0 is "above"
    assert above.total == 1
    assert at_or_below.total == 2


def test_confidence_calibration_even_count_splits_around_average_of_middle_two():
    items = [
        EvaluatedPrediction(_prediction("p1", "d1"), _evaluation("p1", PredictionOutcomeState.TARGET_HIT, actual_return=0.1), _decision("d1", composite=1.0)),
        EvaluatedPrediction(_prediction("p2", "d2"), _evaluation("p2", PredictionOutcomeState.STOP_HIT, actual_return=-0.05), _decision("d2", composite=2.0)),
        EvaluatedPrediction(_prediction("p3", "d3"), _evaluation("p3", PredictionOutcomeState.TARGET_HIT, actual_return=0.2), _decision("d3", composite=3.0)),
        EvaluatedPrediction(_prediction("p4", "d4"), _evaluation("p4", PredictionOutcomeState.TARGET_HIT, actual_return=0.15), _decision("d4", composite=4.0)),
    ]
    buckets = compute_confidence_calibration(items)
    above = next(b for b in buckets if b.bucket_label.startswith("Above"))
    at_or_below = next(b for b in buckets if b.bucket_label.startswith("At or below"))

    # median = (2.0+3.0)/2 = 2.5 -> composite 1.0,2.0 at-or-below; 3.0,4.0 above
    assert above.total == 2
    assert at_or_below.total == 2


def test_confidence_calibration_excludes_items_with_no_decision():
    # A BUY Decision with scanner_evidence=None cannot even be constructed
    # (decision_engine's own model_validator forbids it, per the Phase 21
    # report) -- the only real-world exclusion case is a missing Decision
    # entirely, e.g. a decision database that doesn't cover this prediction.
    items = [
        EvaluatedPrediction(_prediction("p1", "d1"), _evaluation("p1", PredictionOutcomeState.TARGET_HIT, actual_return=0.1), None),
    ]
    assert compute_confidence_calibration(items) == []


def test_confidence_calibration_empty_input_returns_empty_list():
    assert compute_confidence_calibration([]) == []


# --- compute_signal_quality ---------------------------------------------------


def test_signal_quality_averages_excursions_over_resolved_only():
    items = [
        EvaluatedPrediction(_prediction("p1", "d1"), _evaluation("p1", PredictionOutcomeState.TARGET_HIT, actual_return=0.1, mfe=0.12, mae=0.02), _decision("d1")),
        EvaluatedPrediction(_prediction("p2", "d2"), _evaluation("p2", PredictionOutcomeState.STOP_HIT, actual_return=-0.05, mfe=0.03, mae=0.06), _decision("d2")),
        EvaluatedPrediction(_prediction("p3", "d3"), _evaluation("p3", PredictionOutcomeState.ACTIVE, mfe=0.20, mae=0.0), _decision("d3")),
    ]
    quality = compute_signal_quality(items)

    assert quality.resolved == 2
    assert quality.average_favorable_excursion == (0.12 + 0.03) / 2
    assert quality.average_adverse_excursion == (0.02 + 0.06) / 2


def test_signal_quality_includes_items_with_no_decision():
    """Unlike strategy comparison / calibration, signal quality only needs
    PredictionEvaluation data -- a missing Decision must not exclude it."""
    items = [
        EvaluatedPrediction(_prediction("p1", "d1"), _evaluation("p1", PredictionOutcomeState.TARGET_HIT, actual_return=0.1, mfe=0.1, mae=0.0), None),
    ]
    quality = compute_signal_quality(items)
    assert quality.resolved == 1
    assert quality.average_favorable_excursion == 0.1


def test_signal_quality_empty_input_is_none_safe():
    quality = compute_signal_quality([])
    assert quality.resolved == 0
    assert quality.average_favorable_excursion is None
    assert quality.average_adverse_excursion is None


# --- build_learning_report -----------------------------------------------------


def test_build_learning_report_composes_everything_and_states_honest_notes():
    provider = _FakeProvider({"AAPL": _rising_ohlcv("AAPL")})
    items = [
        EvaluatedPrediction(_prediction("p1", "d1"), _evaluation("p1", PredictionOutcomeState.TARGET_HIT, actual_return=0.1), _decision("d1")),
    ]
    report = build_learning_report(items, provider=provider)

    assert report.total_predictions_considered == 1
    assert len(report.strategy_comparison) == 1
    assert len(report.regime_performance) == 1
    assert len(report.confidence_calibration) == 2
    assert report.signal_quality.resolved == 1
    assert any("Experiment Tracking" in note for note in report.notes)
    assert any("Model Comparison" in note for note in report.notes)


def test_build_learning_report_handles_zero_predictions():
    report = build_learning_report([], provider=_FakeProvider({}))
    assert report.total_predictions_considered == 0
    assert report.strategy_comparison == []
    assert report.regime_performance == []
    assert report.confidence_calibration == []
    assert report.signal_quality.resolved == 0
