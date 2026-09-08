"""NSE PREDICTION ENGINE mission: tests for predictions/direction_forecast.py
-- outcome tracking for UP/DOWN/NO_EDGE forecasts, structurally separate
from predictions/tracker.py's BUY-price-level PredictionRecord.
"""
from datetime import datetime, timedelta, timezone

import pytest

from decision_engine.direction import DirectionalAssessment, DirectionLabel
from market.data_provider import MarketDataError, OHLCV, OHLCVBar
from predictions.direction_forecast import (
    DirectionForecastRecord,
    evaluate_forecast,
    summarize_forecasts,
)

_AS_OF = datetime(2024, 1, 10)


def _assessment(label: DirectionLabel, symbol: str = "RELIANCE.NS", confidence: float = 0.8) -> DirectionalAssessment:
    return DirectionalAssessment(
        symbol=symbol, label=label, confidence=confidence,
        bullish_evidence=("Trend (+1.00)",), bearish_evidence=(), contradicting_evidence=(), unavailable_factors=(),
    )


def _forecast(label: DirectionLabel = DirectionLabel.UP, *, reference_price: float = 100.0, horizon_bars: int = 3) -> DirectionForecastRecord:
    return DirectionForecastRecord.from_assessment(
        _assessment(label), as_of=_AS_OF, reference_price=reference_price, horizon_bars=horizon_bars,
    )


def _bars_from(as_of: datetime, closes: list[float]) -> list[OHLCVBar]:
    bars = []
    for i, close in enumerate(closes):
        ts = as_of + timedelta(days=i + 1)
        bars.append(OHLCVBar(timestamp=ts, open=close, high=close * 1.001, low=close * 0.999, close=close, volume=100_000.0))
    return bars


class _FakeProvider:
    def __init__(self, bars: list[OHLCVBar]):
        self._bars = bars

    def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
        return OHLCV(symbol=symbol, interval=interval, bars=self._bars)


class _FailingProvider:
    def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
        raise MarketDataError("simulated outage")


def test_from_assessment_carries_direction_and_confidence_and_evidence():
    forecast = _forecast(DirectionLabel.UP)
    assert forecast.direction == DirectionLabel.UP
    assert forecast.confidence == 0.8
    assert forecast.bullish_evidence == ("Trend (+1.00)",)


def test_evaluate_forecast_unresolved_when_no_bars_yet():
    forecast = _forecast(horizon_bars=3)
    provider = _FakeProvider([])
    result = evaluate_forecast(forecast, provider=provider)
    assert result.resolved is False
    assert result.bars_observed == 0
    assert result.actual_return is None


def test_evaluate_forecast_unresolved_before_horizon_reached():
    forecast = _forecast(horizon_bars=5)
    provider = _FakeProvider(_bars_from(_AS_OF, [101.0, 102.0]))
    result = evaluate_forecast(forecast, provider=provider)
    assert result.resolved is False
    assert result.bars_observed == 2


def test_evaluate_forecast_up_correct_when_price_rose():
    forecast = _forecast(DirectionLabel.UP, reference_price=100.0, horizon_bars=3)
    provider = _FakeProvider(_bars_from(_AS_OF, [101.0, 102.0, 110.0]))
    result = evaluate_forecast(forecast, provider=provider)
    assert result.resolved is True
    assert result.correct is True
    assert result.actual_return == pytest.approx(0.10)


def test_evaluate_forecast_up_incorrect_when_price_fell():
    forecast = _forecast(DirectionLabel.UP, reference_price=100.0, horizon_bars=3)
    provider = _FakeProvider(_bars_from(_AS_OF, [99.0, 98.0, 90.0]))
    result = evaluate_forecast(forecast, provider=provider)
    assert result.resolved is True
    assert result.correct is False
    assert result.actual_return == pytest.approx(-0.10)


def test_evaluate_forecast_down_correct_when_price_fell():
    forecast = _forecast(DirectionLabel.DOWN, reference_price=100.0, horizon_bars=3)
    provider = _FakeProvider(_bars_from(_AS_OF, [99.0, 98.0, 90.0]))
    result = evaluate_forecast(forecast, provider=provider)
    assert result.resolved is True
    assert result.correct is True


def test_evaluate_forecast_no_edge_never_graded_correct_or_incorrect():
    forecast = _forecast(DirectionLabel.NO_EDGE, reference_price=100.0, horizon_bars=3)
    provider = _FakeProvider(_bars_from(_AS_OF, [101.0, 102.0, 110.0]))
    result = evaluate_forecast(forecast, provider=provider)
    assert result.resolved is True
    assert result.correct is None
    assert result.actual_return is not None


def test_evaluate_forecast_data_fetch_failure_is_unresolved_not_a_crash():
    forecast = _forecast()
    result = evaluate_forecast(forecast, provider=_FailingProvider())
    assert result.resolved is False
    assert "outage" in result.detail


def test_evaluate_forecast_anomalous_gap_treated_as_unresolved_not_fabricated_outcome():
    """A >=50% single-bar move looks like an unadjusted stock split, not a
    real, gradeable directional outcome -- must never be silently scored."""
    forecast = _forecast(DirectionLabel.UP, reference_price=100.0, horizon_bars=3)
    provider = _FakeProvider(_bars_from(_AS_OF, [101.0, 250.0, 260.0]))
    result = evaluate_forecast(forecast, provider=provider)
    assert result.resolved is False
    assert "implausible" in result.detail


def test_summarize_forecasts_computes_accuracy_excluding_no_edge():
    up_correct = _forecast(DirectionLabel.UP)
    up_wrong = _forecast(DirectionLabel.UP)
    no_edge = _forecast(DirectionLabel.NO_EDGE)
    forecasts_by_id = {f.forecast_id: f for f in (up_correct, up_wrong, no_edge)}

    now = datetime.now(timezone.utc)
    evaluations = [
        _make_eval(up_correct.forecast_id, now, resolved=True, correct=True, actual_return=0.05),
        _make_eval(up_wrong.forecast_id, now, resolved=True, correct=False, actual_return=-0.03),
        _make_eval(no_edge.forecast_id, now, resolved=True, correct=None, actual_return=0.01),
    ]

    summary = summarize_forecasts(evaluations, forecasts_by_id)
    assert summary.total == 3
    assert summary.resolved == 3
    assert summary.correct == 1
    assert summary.incorrect == 1
    assert summary.no_edge == 1
    assert summary.accuracy == pytest.approx(0.5)
    assert summary.average_return == pytest.approx((0.05 + -0.03) / 2)


def test_summarize_forecasts_dedupes_to_latest_evaluation_per_forecast():
    forecast = _forecast(DirectionLabel.UP)
    forecasts_by_id = {forecast.forecast_id: forecast}
    older = _make_eval(forecast.forecast_id, datetime(2024, 1, 1, tzinfo=timezone.utc), resolved=False)
    newer = _make_eval(forecast.forecast_id, datetime(2024, 1, 5, tzinfo=timezone.utc), resolved=True, correct=True, actual_return=0.02)

    summary = summarize_forecasts([older, newer], forecasts_by_id)
    assert summary.total == 1
    assert summary.resolved == 1
    assert summary.correct == 1


def _make_eval(forecast_id, evaluated_at, *, resolved, correct=None, actual_return=None):
    from predictions.direction_forecast import DirectionForecastEvaluation

    return DirectionForecastEvaluation(
        evaluation_id=DirectionForecastEvaluation.new_id(), forecast_id=forecast_id, evaluated_at=evaluated_at,
        resolved=resolved, bars_observed=3, actual_return=actual_return, correct=correct, detail="test",
    )
