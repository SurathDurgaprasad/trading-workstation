from datetime import datetime, timezone

from decision_engine.models import DecisionLabel
from predictions.models import (
    RESOLVED_STATES,
    PredictionEvaluation,
    PredictionOutcomeState,
    PredictionRecord,
    PredictionSummary,
)


def test_produced_states_are_all_recognized_enum_members():
    produced = {
        PredictionOutcomeState.ACTIVE, PredictionOutcomeState.TARGET_HIT, PredictionOutcomeState.STOP_HIT,
        PredictionOutcomeState.EXPIRED, PredictionOutcomeState.INSUFFICIENT_DATA,
    }
    assert produced.issubset(set(PredictionOutcomeState))


def test_roadmap_suggested_states_are_all_present_even_if_unproduced():
    # roadmap section 7.3's full suggested list -- recognized even though
    # this phase's evaluate_prediction only ever produces the 5 above.
    unproduced = {
        PredictionOutcomeState.PENDING, PredictionOutcomeState.INVALIDATED, PredictionOutcomeState.PARTIAL_SUCCESS,
        PredictionOutcomeState.MISSED_ENTRY, PredictionOutcomeState.CANCELLED,
    }
    assert unproduced.issubset(set(PredictionOutcomeState))
    assert len(PredictionOutcomeState) == 10


def test_resolved_states_is_exactly_target_and_stop_hit():
    assert set(RESOLVED_STATES) == {PredictionOutcomeState.TARGET_HIT, PredictionOutcomeState.STOP_HIT}


def test_prediction_record_is_frozen():
    record = PredictionRecord(
        prediction_id="p1", decision_id="d1", symbol="AAPL", created_at=datetime.now(timezone.utc),
        label=DecisionLabel.BUY, entry_price=100.0, stop_price=95.0, target_price=110.0,
        entry_time=datetime(2024, 1, 2), horizon_bars=20, interval="1d",
    )
    try:
        record.entry_price = 200.0
        assert False, "PredictionRecord should be immutable"
    except Exception:
        pass


def test_prediction_evaluation_is_frozen():
    evaluation = PredictionEvaluation(
        evaluation_id="e1", prediction_id="p1", evaluated_at=datetime.now(timezone.utc),
        outcome=PredictionOutcomeState.ACTIVE, bars_observed=0, exit_time=None, exit_price=None,
        actual_return=None, max_favorable_excursion=0.0, max_adverse_excursion=0.0, detail="test",
    )
    try:
        evaluation.outcome = PredictionOutcomeState.TARGET_HIT
        assert False, "PredictionEvaluation should be immutable"
    except Exception:
        pass


def test_new_id_helpers_produce_distinct_ids():
    assert PredictionRecord.new_id() != PredictionRecord.new_id()
    assert PredictionEvaluation.new_id() != PredictionEvaluation.new_id()


def test_prediction_summary_fields_are_optional_when_nothing_resolved():
    summary = PredictionSummary(
        total_predictions=0, active=0, target_hit=0, stop_hit=0, expired=0, insufficient_data=0,
        win_rate=None, average_return=None, profit_factor=None,
    )
    assert summary.win_rate is None
    assert summary.average_return is None
    assert summary.profit_factor is None
