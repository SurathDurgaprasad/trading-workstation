from datetime import datetime

from backtesting.splits import split_periods
from strategy.experiment_registry import build_experiment_record
from strategy.experiment_store import ExperimentRegistryStore
from strategy.manifest import freeze_trend_momentum_baseline_manifest
from strategy.promotion_gate import evaluate_promotion

_POSITIVE = [0.05] * 30
_NEGATIVE = [-0.05] * 30


def _record(hypothesis_id="H_TEST_001", universe=("AAPL",), returns=_NEGATIVE):
    manifest = freeze_trend_momentum_baseline_manifest(universe=universe)
    split = split_periods(datetime(2021, 1, 1), datetime(2026, 1, 1))
    evaluation = evaluate_promotion("trend_momentum_baseline", development_returns=returns, validation_returns=returns, out_of_sample_returns=returns)
    return build_experiment_record(hypothesis_id=hypothesis_id, manifest=manifest, period_split=split, evaluation=evaluation)


def test_record_and_get_round_trips_the_full_experiment(tmp_path):
    store = ExperimentRegistryStore(tmp_path / "experiments.db")
    record = _record()

    experiment_id = store.record_experiment(record)
    fetched = store.get(experiment_id)

    assert fetched == record


def test_get_returns_none_for_an_unknown_experiment_id(tmp_path):
    store = ExperimentRegistryStore(tmp_path / "experiments.db")
    assert store.get("does-not-exist") is None


def test_history_for_hypothesis_never_overwrites_a_past_experiment(tmp_path):
    store = ExperimentRegistryStore(tmp_path / "experiments.db")
    first = _record(hypothesis_id="H_TEST_001", returns=_NEGATIVE)
    second = _record(hypothesis_id="H_TEST_001", returns=_POSITIVE)
    store.record_experiment(first)
    store.record_experiment(second)

    history = store.history_for_hypothesis("H_TEST_001")

    assert len(history) == 2
    assert history[0].evaluation.verdict.value == "NEGATIVE"
    assert history[1].evaluation.verdict.value == "PROMOTED"


def test_history_for_manifest_hash_groups_by_exact_strategy_configuration(tmp_path):
    store = ExperimentRegistryStore(tmp_path / "experiments.db")
    aapl_only = _record(hypothesis_id="H_TEST_001", universe=("AAPL",))
    aapl_and_reliance = _record(hypothesis_id="H_TEST_002", universe=("AAPL", "RELIANCE.NS"))
    store.record_experiment(aapl_only)
    store.record_experiment(aapl_and_reliance)

    assert len(store.history_for_manifest_hash(aapl_only.manifest_hash)) == 1
    assert len(store.history_for_manifest_hash(aapl_and_reliance.manifest_hash)) == 1
    assert aapl_only.manifest_hash != aapl_and_reliance.manifest_hash


def test_all_experiments_returns_the_full_immutable_history(tmp_path):
    store = ExperimentRegistryStore(tmp_path / "experiments.db")
    store.record_experiment(_record(hypothesis_id="H_TEST_001"))
    store.record_experiment(_record(hypothesis_id="H_TEST_002"))
    store.record_experiment(_record(hypothesis_id="H_TEST_003"))

    all_records = store.all_experiments()

    assert len(all_records) == 3
    assert {r.hypothesis_id for r in all_records} == {"H_TEST_001", "H_TEST_002", "H_TEST_003"}


def test_recording_the_same_experiment_id_twice_raises_rather_than_overwriting(tmp_path):
    import sqlite3

    import pytest

    store = ExperimentRegistryStore(tmp_path / "experiments.db")
    record = _record()
    store.record_experiment(record)

    with pytest.raises(sqlite3.IntegrityError):
        store.record_experiment(record)  # SAME experiment_id, second insert -- must not silently overwrite

    assert len(store.all_experiments()) == 1  # the duplicate insert never landed


def test_records_persist_across_separate_store_instances_on_the_same_db_file(tmp_path):
    db_path = tmp_path / "experiments.db"
    store1 = ExperimentRegistryStore(db_path)
    record = _record()
    experiment_id = store1.record_experiment(record)
    store1.close()

    store2 = ExperimentRegistryStore(db_path)
    fetched = store2.get(experiment_id)

    assert fetched == record
