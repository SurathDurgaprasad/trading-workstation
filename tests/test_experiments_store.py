from datetime import datetime, timedelta, timezone

import pytest

from experiments.models import ConfigType, Experiment, ExperimentEvent, ExperimentEventType
from experiments.store import ExperimentStore


def _experiment(experiment_id: str = "exp-1", *, started_at: datetime | None = None, config_version: str = "cfg-abc") -> Experiment:
    return Experiment(
        experiment_id=experiment_id, name="test experiment", description="fake", config_type=ConfigType.DECISION_ENGINE,
        config_version=config_version, started_at=started_at or datetime.now(timezone.utc),
    )


def _event(experiment_id: str, event_type: ExperimentEventType, *, occurred_at: datetime | None = None, event_id: str = "e1") -> ExperimentEvent:
    return ExperimentEvent(event_id=event_id, experiment_id=experiment_id, event_type=event_type, occurred_at=occurred_at or datetime.now(timezone.utc), detail="test")


@pytest.fixture
def store(tmp_path):
    s = ExperimentStore(tmp_path / "experiments.db")
    yield s
    s.close()


def test_save_and_get_experiment_round_trips(store):
    experiment = _experiment()
    store.save_experiment(experiment)
    fetched = store.get_experiment("exp-1")
    assert fetched == experiment


def test_get_experiment_returns_none_for_unknown_id(store):
    assert store.get_experiment("does-not-exist") is None


def test_list_experiments_orders_most_recent_first(store):
    store.save_experiment(_experiment("exp-1", started_at=datetime(2024, 1, 1, tzinfo=timezone.utc)))
    store.save_experiment(_experiment("exp-2", started_at=datetime(2024, 6, 1, tzinfo=timezone.utc)))
    result = store.list_experiments()
    assert [e.experiment_id for e in result] == ["exp-2", "exp-1"]


def test_is_ended_false_with_no_events(store):
    store.save_experiment(_experiment())
    assert store.is_ended("exp-1") is False


def test_is_ended_false_after_only_a_started_event(store):
    store.save_experiment(_experiment())
    store.save_event(_event("exp-1", ExperimentEventType.STARTED))
    assert store.is_ended("exp-1") is False


def test_is_ended_true_after_an_ended_event(store):
    store.save_experiment(_experiment())
    store.save_event(_event("exp-1", ExperimentEventType.STARTED, occurred_at=datetime(2024, 1, 1, tzinfo=timezone.utc), event_id="e1"))
    store.save_event(_event("exp-1", ExperimentEventType.ENDED, occurred_at=datetime(2024, 6, 1, tzinfo=timezone.utc), event_id="e2"))
    assert store.is_ended("exp-1") is True


def test_ended_at_returns_the_ended_event_timestamp(store):
    store.save_experiment(_experiment())
    ended_time = datetime(2024, 6, 1, tzinfo=timezone.utc)
    store.save_event(_event("exp-1", ExperimentEventType.ENDED, occurred_at=ended_time, event_id="e1"))
    assert store.ended_at("exp-1") == ended_time


def test_ended_at_none_when_not_ended(store):
    store.save_experiment(_experiment())
    assert store.ended_at("exp-1") is None


def test_list_events_for_experiment_orders_chronologically(store):
    store.save_experiment(_experiment())
    store.save_event(_event("exp-1", ExperimentEventType.STARTED, occurred_at=datetime(2024, 1, 1, tzinfo=timezone.utc), event_id="e1"))
    store.save_event(_event("exp-1", ExperimentEventType.NOTE, occurred_at=datetime(2024, 3, 1, tzinfo=timezone.utc), event_id="e2"))
    events = store.list_events_for_experiment("exp-1")
    assert [e.event_id for e in events] == ["e1", "e2"]


def test_latest_event_for_experiment_returns_the_most_recent(store):
    store.save_experiment(_experiment())
    store.save_event(_event("exp-1", ExperimentEventType.STARTED, occurred_at=datetime(2024, 1, 1, tzinfo=timezone.utc), event_id="e1"))
    store.save_event(_event("exp-1", ExperimentEventType.NOTE, occurred_at=datetime(2024, 3, 1, tzinfo=timezone.utc), event_id="e2"))
    latest = store.latest_event_for_experiment("exp-1")
    assert latest.event_id == "e2"


def test_latest_event_for_experiment_none_when_no_events(store):
    store.save_experiment(_experiment())
    assert store.latest_event_for_experiment("exp-1") is None


def test_no_update_methods_exist_experiments_are_append_only(store):
    assert not hasattr(store, "update_experiment")
    assert not hasattr(store, "update_event")


def test_store_persists_across_reconnect(tmp_path):
    db_path = tmp_path / "experiments.db"
    store1 = ExperimentStore(db_path)
    store1.save_experiment(_experiment())
    store1.close()

    store2 = ExperimentStore(db_path)
    assert store2.get_experiment("exp-1") is not None
    store2.close()
