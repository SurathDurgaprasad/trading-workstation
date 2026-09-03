from datetime import datetime, timedelta, timezone

import pytest

from decision_engine.models import Decision, DecisionLabel, RiskContext
from experiments.comparison import compare_experiments
from experiments.models import ConfigType, Experiment
from experiments.store import ExperimentStore
from learning.analysis import EvaluatedPrediction
from market_intelligence.models import CandidateScore
from predictions.models import PredictionEvaluation, PredictionOutcomeState, PredictionRecord


def _candidate() -> CandidateScore:
    return CandidateScore(
        symbol="AAPL", as_of=datetime(2024, 1, 1), last_close=100.0, avg_daily_value=1_000_000.0, volume_ratio=1.1,
        trend_score=1.0, momentum_score=0.5, breakout_score=0.01, relative_strength_score=0.02,
        sector_strength_score=None, composite_score=1.5, explanation=["fake"],
    )


def _decision(decision_id: str, config_version: str) -> Decision:
    return Decision(
        decision_id=decision_id, symbol="AAPL", as_of=datetime(2024, 1, 2, tzinfo=timezone.utc), label=DecisionLabel.BUY,
        rationale=["fake"], config_version=config_version, scanner_evidence=_candidate(), research_evidence=None,
        market_context=None, risk_context=RiskContext.unknown(), narrative=None, narrative_unavailable_reason=None,
    )


def _prediction(prediction_id: str, decision_id: str, *, created_at: datetime) -> PredictionRecord:
    return PredictionRecord(
        prediction_id=prediction_id, decision_id=decision_id, symbol="AAPL", created_at=created_at,
        label=DecisionLabel.BUY, entry_price=100.0, stop_price=95.0, target_price=110.0,
        entry_time=datetime(2024, 1, 2), horizon_bars=20, interval="1d",
    )


def _evaluation(prediction_id: str, outcome: PredictionOutcomeState, *, actual_return: float | None = None) -> PredictionEvaluation:
    return PredictionEvaluation(
        evaluation_id=f"eval-{prediction_id}", prediction_id=prediction_id, evaluated_at=datetime.now(timezone.utc),
        outcome=outcome, bars_observed=5, exit_time=None, exit_price=None, actual_return=actual_return,
        max_favorable_excursion=0.05, max_adverse_excursion=0.01, detail="test",
    )


def _experiment(experiment_id: str, config_version: str, *, started_at: datetime) -> Experiment:
    return Experiment(
        experiment_id=experiment_id, name=f"experiment {experiment_id}", description="fake",
        config_type=ConfigType.DECISION_ENGINE, config_version=config_version, started_at=started_at,
    )


@pytest.fixture
def store(tmp_path):
    s = ExperimentStore(tmp_path / "experiments.db")
    yield s
    s.close()


def test_compare_experiments_computes_win_rate_within_the_window(store):
    experiment = _experiment("exp-1", "cfg-A", started_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
    store.save_experiment(experiment)

    items = [
        EvaluatedPrediction(
            _prediction("p1", "d1", created_at=datetime(2024, 1, 5, tzinfo=timezone.utc)),
            _evaluation("p1", PredictionOutcomeState.TARGET_HIT, actual_return=0.1),
            _decision("d1", "cfg-A"),
        ),
        EvaluatedPrediction(
            _prediction("p2", "d2", created_at=datetime(2024, 1, 6, tzinfo=timezone.utc)),
            _evaluation("p2", PredictionOutcomeState.STOP_HIT, actual_return=-0.05),
            _decision("d2", "cfg-A"),
        ),
    ]

    result = compare_experiments([experiment], items, store)

    assert len(result) == 1
    assert result[0].total == 2
    assert result[0].resolved == 2
    assert result[0].win_rate == pytest.approx(0.5)


def test_compare_experiments_excludes_predictions_before_the_start_boundary(store):
    experiment = _experiment("exp-1", "cfg-A", started_at=datetime(2024, 6, 1, tzinfo=timezone.utc))
    store.save_experiment(experiment)

    items = [
        EvaluatedPrediction(
            _prediction("p1", "d1", created_at=datetime(2024, 1, 5, tzinfo=timezone.utc)),  # BEFORE the experiment started
            _evaluation("p1", PredictionOutcomeState.TARGET_HIT, actual_return=0.1),
            _decision("d1", "cfg-A"),
        ),
    ]

    result = compare_experiments([experiment], items, store)
    assert result[0].total == 0


def test_compare_experiments_excludes_predictions_after_the_end_boundary(store):
    from experiments.models import ExperimentEvent, ExperimentEventType

    experiment = _experiment("exp-1", "cfg-A", started_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
    store.save_experiment(experiment)
    store.save_event(ExperimentEvent(
        event_id="e1", experiment_id="exp-1", event_type=ExperimentEventType.ENDED,
        occurred_at=datetime(2024, 3, 1, tzinfo=timezone.utc),
    ))

    items = [
        EvaluatedPrediction(
            _prediction("p1", "d1", created_at=datetime(2024, 6, 1, tzinfo=timezone.utc)),  # AFTER the experiment ended
            _evaluation("p1", PredictionOutcomeState.TARGET_HIT, actual_return=0.1),
            _decision("d1", "cfg-A"),
        ),
    ]

    result = compare_experiments([experiment], items, store)
    assert result[0].total == 0
    assert result[0].ended_at == datetime(2024, 3, 1, tzinfo=timezone.utc)


def test_compare_experiments_excludes_a_different_config_version(store):
    experiment = _experiment("exp-1", "cfg-A", started_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
    store.save_experiment(experiment)

    items = [
        EvaluatedPrediction(
            _prediction("p1", "d1", created_at=datetime(2024, 1, 5, tzinfo=timezone.utc)),
            _evaluation("p1", PredictionOutcomeState.TARGET_HIT, actual_return=0.1),
            _decision("d1", "cfg-B"),  # different config version
        ),
    ]

    result = compare_experiments([experiment], items, store)
    assert result[0].total == 0


def test_compare_experiments_excludes_items_with_no_decision(store):
    experiment = _experiment("exp-1", "cfg-A", started_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
    store.save_experiment(experiment)

    items = [
        EvaluatedPrediction(
            _prediction("p1", "d1", created_at=datetime(2024, 1, 5, tzinfo=timezone.utc)),
            _evaluation("p1", PredictionOutcomeState.TARGET_HIT, actual_return=0.1),
            None,
        ),
    ]

    result = compare_experiments([experiment], items, store)
    assert result[0].total == 0


def test_compare_experiments_two_experiments_isolated_by_config_version_and_window(store):
    exp_a = _experiment("exp-A", "cfg-A", started_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
    exp_b = _experiment("exp-B", "cfg-B", started_at=datetime(2024, 6, 1, tzinfo=timezone.utc))
    store.save_experiment(exp_a)
    store.save_experiment(exp_b)

    items = [
        EvaluatedPrediction(
            _prediction("p1", "d1", created_at=datetime(2024, 2, 1, tzinfo=timezone.utc)),
            _evaluation("p1", PredictionOutcomeState.TARGET_HIT, actual_return=0.1), _decision("d1", "cfg-A"),
        ),
        EvaluatedPrediction(
            _prediction("p2", "d2", created_at=datetime(2024, 7, 1, tzinfo=timezone.utc)),
            _evaluation("p2", PredictionOutcomeState.STOP_HIT, actual_return=-0.05), _decision("d2", "cfg-B"),
        ),
    ]

    result = compare_experiments([exp_a, exp_b], items, store)
    by_id = {c.experiment.experiment_id: c for c in result}
    assert by_id["exp-A"].total == 1
    assert by_id["exp-A"].win_rate == pytest.approx(1.0)
    assert by_id["exp-B"].total == 1
    assert by_id["exp-B"].win_rate == pytest.approx(0.0)


def test_compare_experiments_empty_list_returns_empty():
    class _FakeStore:
        def ended_at(self, experiment_id):
            return None

    assert compare_experiments([], [], _FakeStore()) == []


def test_compare_experiments_no_predictions_in_window_gives_none_stats(store):
    experiment = _experiment("exp-1", "cfg-A", started_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
    store.save_experiment(experiment)
    result = compare_experiments([experiment], [], store)
    assert result[0].total == 0
    assert result[0].win_rate is None
