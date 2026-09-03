from datetime import datetime, timezone

import pytest

from experiments.models import ConfigType, Experiment, ExperimentEvent, ExperimentEventType


def _experiment(**overrides) -> Experiment:
    defaults = dict(
        experiment_id="exp-1", name="baseline corroboration rule", description="testing require_corroboration_for_buy=True",
        config_type=ConfigType.DECISION_ENGINE, config_version="cfg-abc123", started_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Experiment(**defaults)


def test_experiment_is_frozen():
    experiment = _experiment()
    with pytest.raises(Exception):
        experiment.name = "changed"


def test_experiment_new_id_produces_distinct_ids():
    assert Experiment.new_id() != Experiment.new_id()


def test_experiment_event_new_id_produces_distinct_ids():
    assert ExperimentEvent.new_id() != ExperimentEvent.new_id()


def test_experiment_event_is_frozen():
    event = ExperimentEvent(event_id="e1", experiment_id="exp-1", event_type=ExperimentEventType.STARTED, occurred_at=datetime.now(timezone.utc))
    with pytest.raises(Exception):
        event.detail = "changed"


def test_config_type_has_the_three_existing_versioned_configs():
    assert {c.value for c in ConfigType} == {"decision_engine", "scanner", "risk"}


def test_experiment_round_trips_through_json():
    experiment = _experiment()
    restored = Experiment.model_validate_json(experiment.model_dump_json())
    assert restored == experiment
