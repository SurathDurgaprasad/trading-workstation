from datetime import datetime, timezone

from decision_engine.direction import DirectionalAssessment, DirectionLabel
from predictions.direction_forecast import DirectionForecastEvaluation, DirectionForecastRecord
from predictions.direction_forecast_store import DirectionForecastStore

_AS_OF = datetime(2024, 1, 10)


def _assessment(label=DirectionLabel.UP, symbol="RELIANCE.NS") -> DirectionalAssessment:
    return DirectionalAssessment(
        symbol=symbol, label=label, confidence=0.7,
        bullish_evidence=("Trend (+1.00)",), bearish_evidence=(), contradicting_evidence=(), unavailable_factors=(),
    )


def _forecast(symbol="RELIANCE.NS", as_of=_AS_OF, label=DirectionLabel.UP) -> DirectionForecastRecord:
    return DirectionForecastRecord.from_assessment(_assessment(label, symbol), as_of=as_of, reference_price=100.0, horizon_bars=5)


def test_save_and_get_round_trips(tmp_path):
    store = DirectionForecastStore(tmp_path / "forecasts.db")
    forecast = _forecast()
    store.save_forecast(forecast)

    fetched = store.get_forecast(forecast.forecast_id)
    assert fetched == forecast
    store.close()


def test_get_forecast_returns_none_for_unknown_id(tmp_path):
    store = DirectionForecastStore(tmp_path / "forecasts.db")
    assert store.get_forecast("does-not-exist") is None
    store.close()


def test_has_forecast_for_bar_detects_duplicate(tmp_path):
    store = DirectionForecastStore(tmp_path / "forecasts.db")
    forecast = _forecast()
    store.save_forecast(forecast)

    assert store.has_forecast_for_bar("RELIANCE.NS", _AS_OF) is True
    assert store.has_forecast_for_bar("RELIANCE.NS", datetime(2024, 2, 1)) is False
    assert store.has_forecast_for_bar("TCS.NS", _AS_OF) is False
    store.close()


def test_list_forecasts_needing_evaluation_excludes_resolved(tmp_path):
    store = DirectionForecastStore(tmp_path / "forecasts.db")
    resolved = _forecast(symbol="RESOLVED.NS")
    unresolved = _forecast(symbol="UNRESOLVED.NS")
    store.save_forecast(resolved)
    store.save_forecast(unresolved)

    store.save_evaluation(DirectionForecastEvaluation(
        evaluation_id=DirectionForecastEvaluation.new_id(), forecast_id=resolved.forecast_id,
        evaluated_at=datetime.now(timezone.utc), resolved=True, bars_observed=5, actual_return=0.02, correct=True, detail="resolved",
    ))
    store.save_evaluation(DirectionForecastEvaluation(
        evaluation_id=DirectionForecastEvaluation.new_id(), forecast_id=unresolved.forecast_id,
        evaluated_at=datetime.now(timezone.utc), resolved=False, bars_observed=1, actual_return=None, correct=None, detail="still open",
    ))

    needing = store.list_forecasts_needing_evaluation()
    assert {f.forecast_id for f in needing} == {unresolved.forecast_id}
    store.close()


def test_latest_evaluation_for_forecast_returns_the_newest(tmp_path):
    store = DirectionForecastStore(tmp_path / "forecasts.db")
    forecast = _forecast()
    store.save_forecast(forecast)

    older = DirectionForecastEvaluation(
        evaluation_id=DirectionForecastEvaluation.new_id(), forecast_id=forecast.forecast_id,
        evaluated_at=datetime(2024, 1, 11, tzinfo=timezone.utc), resolved=False, bars_observed=1, actual_return=None, correct=None, detail="early",
    )
    newer = DirectionForecastEvaluation(
        evaluation_id=DirectionForecastEvaluation.new_id(), forecast_id=forecast.forecast_id,
        evaluated_at=datetime(2024, 1, 15, tzinfo=timezone.utc), resolved=True, bars_observed=5, actual_return=0.03, correct=True, detail="resolved",
    )
    store.save_evaluation(older)
    store.save_evaluation(newer)

    latest = store.latest_evaluation_for_forecast(forecast.forecast_id)
    assert latest.evaluation_id == newer.evaluation_id
    store.close()


def test_store_persists_across_reconnect(tmp_path):
    db_path = tmp_path / "forecasts.db"
    store = DirectionForecastStore(db_path)
    store.save_forecast(_forecast())
    store.close()

    reopened = DirectionForecastStore(db_path)
    assert len(reopened.list_forecasts()) == 1
    reopened.close()
