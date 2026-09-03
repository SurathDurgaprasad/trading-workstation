from datetime import datetime, timezone

from decision_engine.models import DecisionLabel
from predictions.models import PredictionEvaluation, PredictionOutcomeState, PredictionRecord
from predictions.store import PredictionStore


def _prediction(prediction_id: str = "p1", symbol: str = "AAPL", created_at: datetime | None = None) -> PredictionRecord:
    return PredictionRecord(
        prediction_id=prediction_id, decision_id="dec-1", symbol=symbol,
        created_at=created_at or datetime(2024, 1, 1, tzinfo=timezone.utc), label=DecisionLabel.BUY,
        entry_price=100.0, stop_price=95.0, target_price=110.0, entry_time=datetime(2024, 1, 2),
        horizon_bars=20, interval="1d",
    )


def _evaluation(
    prediction_id: str = "p1", evaluation_id: str = "e1", outcome=PredictionOutcomeState.ACTIVE,
    evaluated_at: datetime | None = None,
) -> PredictionEvaluation:
    return PredictionEvaluation(
        evaluation_id=evaluation_id, prediction_id=prediction_id, evaluated_at=evaluated_at or datetime(2024, 1, 3, tzinfo=timezone.utc),
        outcome=outcome, bars_observed=1, exit_time=None, exit_price=None, actual_return=None,
        max_favorable_excursion=0.0, max_adverse_excursion=0.0, detail="test",
    )


def test_save_and_get_prediction_round_trips(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    prediction = _prediction()
    store.save_prediction(prediction)

    assert store.get_prediction("p1") == prediction
    store.close()


def test_get_prediction_returns_none_for_unknown_id(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    assert store.get_prediction("does-not-exist") is None
    store.close()


def test_save_and_list_evaluations_round_trip(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(_prediction())
    store.save_evaluation(_evaluation())

    evaluations = store.list_evaluations_for_prediction("p1")
    assert len(evaluations) == 1
    assert evaluations[0].evaluation_id == "e1"
    store.close()


def test_latest_evaluation_for_prediction_returns_the_most_recent(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(_prediction())
    store.save_evaluation(_evaluation("p1", "e-old", PredictionOutcomeState.ACTIVE, datetime(2024, 1, 3, tzinfo=timezone.utc)))
    store.save_evaluation(_evaluation("p1", "e-new", PredictionOutcomeState.TARGET_HIT, datetime(2024, 1, 10, tzinfo=timezone.utc)))

    latest = store.latest_evaluation_for_prediction("p1")
    assert latest.evaluation_id == "e-new"
    assert latest.outcome == PredictionOutcomeState.TARGET_HIT
    store.close()


def test_latest_evaluation_for_prediction_returns_none_when_never_evaluated(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(_prediction())
    assert store.latest_evaluation_for_prediction("p1") is None
    store.close()


def test_list_predictions_needing_evaluation_includes_never_evaluated_and_active(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(_prediction("p1"))  # never evaluated
    store.save_prediction(_prediction("p2"))
    store.save_evaluation(_evaluation("p2", "e2", PredictionOutcomeState.ACTIVE))
    store.save_prediction(_prediction("p3"))
    store.save_evaluation(_evaluation("p3", "e3", PredictionOutcomeState.TARGET_HIT))

    pending = store.list_predictions_needing_evaluation()
    pending_ids = {p.prediction_id for p in pending}

    assert pending_ids == {"p1", "p2"}
    assert "p3" not in pending_ids  # resolved -- done, never re-queued
    store.close()


def test_list_predictions_needing_evaluation_excludes_expired_and_insufficient_data(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(_prediction("p1"))
    store.save_evaluation(_evaluation("p1", "e1", PredictionOutcomeState.EXPIRED))
    store.save_prediction(_prediction("p2"))
    store.save_evaluation(_evaluation("p2", "e2", PredictionOutcomeState.INSUFFICIENT_DATA))

    assert store.list_predictions_needing_evaluation() == []
    store.close()


def test_list_all_evaluations_returns_every_row_including_superseded_ones(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(_prediction())
    store.save_evaluation(_evaluation("p1", "e-old", PredictionOutcomeState.ACTIVE, datetime(2024, 1, 3, tzinfo=timezone.utc)))
    store.save_evaluation(_evaluation("p1", "e-new", PredictionOutcomeState.TARGET_HIT, datetime(2024, 1, 10, tzinfo=timezone.utc)))

    all_evaluations = store.list_all_evaluations()
    assert len(all_evaluations) == 2
    store.close()


def test_no_update_methods_exist_predictions_and_evaluations_are_append_only(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    assert not hasattr(store, "update_prediction")
    assert not hasattr(store, "update_evaluation")
    store.close()


def test_store_persists_across_reconnect(tmp_path):
    db_path = tmp_path / "predictions.db"
    store = PredictionStore(db_path)
    store.save_prediction(_prediction())
    store.save_evaluation(_evaluation())
    store.close()

    reopened = PredictionStore(db_path)
    assert reopened.get_prediction("p1") is not None
    assert reopened.latest_evaluation_for_prediction("p1") is not None
    reopened.close()
