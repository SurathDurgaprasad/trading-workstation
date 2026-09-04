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


def test_save_and_get_prediction_round_trips_a_real_risk_decision(tmp_path):
    """Mission auditability requirement: the persisted trade plan
    (quantity/capital/risk amount) must survive the ACTUAL sqlite
    store round trip, not just an in-memory JSON round trip."""
    from decision_engine.models import Decision, RiskContext
    from market.context import MarketContext
    from market_intelligence.models import CandidateScore
    from risk.account import new_account
    from risk.sizing import size_decision

    candidate = CandidateScore(
        symbol="AAPL", as_of=datetime(2024, 1, 1), last_close=100.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.1, trend_score=1.0, momentum_score=0.5, breakout_score=0.01,
        relative_strength_score=0.02, sector_strength_score=None, composite_score=1.5, explanation=["fake"],
    )
    decision = Decision(
        decision_id="dec-1", symbol="AAPL", as_of=datetime(2024, 1, 1, tzinfo=timezone.utc), label=DecisionLabel.BUY,
        rationale=["fake"], config_version="cfg1", scanner_evidence=candidate, research_evidence=None,
        market_context=None, risk_context=RiskContext.unknown(), narrative=None, narrative_unavailable_reason=None,
    )
    market_context = MarketContext(symbol="AAPL", as_of=datetime(2024, 1, 1), price=100.0, atr_14=2.5)
    risk_decision = size_decision(decision, market_context=market_context, account=new_account(20_000.0))

    prediction = PredictionRecord(
        prediction_id="p-sized", decision_id="dec-1", symbol="AAPL", created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        label=DecisionLabel.BUY, entry_price=100.0, stop_price=95.0, target_price=110.0, entry_time=datetime(2024, 1, 2),
        horizon_bars=20, interval="1d", risk_decision=risk_decision,
    )

    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(prediction)
    fetched = store.get_prediction("p-sized")
    store.close()

    assert fetched is not None
    assert fetched.risk_decision is not None
    assert fetched.risk_decision.account_equity == 20_000.0
    assert fetched.risk_decision.position_size.quantity == risk_decision.position_size.quantity
    assert fetched == prediction


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


def test_list_predictions_for_symbol_filters_and_orders_most_recent_first(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(_prediction("p1", symbol="AAPL", created_at=datetime(2024, 1, 1, tzinfo=timezone.utc)))
    store.save_prediction(_prediction("p2", symbol="MSFT", created_at=datetime(2024, 1, 2, tzinfo=timezone.utc)))
    store.save_prediction(_prediction("p3", symbol="AAPL", created_at=datetime(2024, 1, 3, tzinfo=timezone.utc)))

    result = store.list_predictions_for_symbol("AAPL")

    store.close()
    assert [p.prediction_id for p in result] == ["p3", "p1"]  # most recent first, MSFT excluded


def test_list_predictions_for_symbol_normalizes_case(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(_prediction("p1", symbol="AAPL"))
    result = store.list_predictions_for_symbol("aapl")
    store.close()
    assert len(result) == 1


def test_list_predictions_for_symbol_empty_for_unknown_symbol(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(_prediction("p1", symbol="AAPL"))
    result = store.list_predictions_for_symbol("ZZZZ")
    store.close()
    assert result == []


def test_list_predictions_for_symbol_respects_limit(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    for i in range(5):
        store.save_prediction(_prediction(f"p{i}", symbol="AAPL", created_at=datetime(2024, 1, 1 + i, tzinfo=timezone.utc)))
    result = store.list_predictions_for_symbol("AAPL", limit=2)
    store.close()
    assert len(result) == 2


def test_has_prediction_for_entry_true_after_saving_one(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    entry_time = datetime(2024, 6, 1)
    store.save_prediction(_prediction("p1", symbol="AAPL", created_at=entry_time).model_copy(update={"entry_time": entry_time}))
    result = store.has_prediction_for_entry("AAPL", entry_time)
    store.close()
    assert result is True


def test_has_prediction_for_entry_false_for_a_different_bar(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(_prediction("p1", symbol="AAPL").model_copy(update={"entry_time": datetime(2024, 6, 1)}))
    result = store.has_prediction_for_entry("AAPL", datetime(2024, 6, 2))
    store.close()
    assert result is False


def test_has_prediction_for_entry_false_for_a_different_symbol(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    entry_time = datetime(2024, 6, 1)
    store.save_prediction(_prediction("p1", symbol="AAPL").model_copy(update={"entry_time": entry_time}))
    result = store.has_prediction_for_entry("MSFT", entry_time)
    store.close()
    assert result is False


def test_has_prediction_for_entry_false_when_nothing_recorded(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    result = store.has_prediction_for_entry("AAPL", datetime(2024, 6, 1))
    store.close()
    assert result is False


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
