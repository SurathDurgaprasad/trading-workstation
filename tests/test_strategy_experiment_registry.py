from datetime import datetime

import pytest

from backtesting.splits import split_periods
from strategy.experiment_registry import ExperimentRecord, build_experiment_record
from strategy.manifest import freeze_trend_momentum_baseline_manifest
from strategy.promotion_gate import evaluate_promotion

_POSITIVE = [0.05] * 30
_NEGATIVE = [-0.05] * 30


def _real_manifest():
    return freeze_trend_momentum_baseline_manifest(universe=("AAPL", "RELIANCE.NS"))


def _real_split():
    return split_periods(datetime(2021, 1, 1), datetime(2026, 1, 1))


def _real_evaluation():
    return evaluate_promotion(
        "trend_momentum_baseline", development_returns=_NEGATIVE, validation_returns=_NEGATIVE, out_of_sample_returns=_NEGATIVE,
    )


def test_build_experiment_record_composes_real_components_without_recomputing_them():
    manifest = _real_manifest()
    split = _real_split()
    evaluation = _real_evaluation()

    record = build_experiment_record(hypothesis_id="H_TEST_001", manifest=manifest, period_split=split, evaluation=evaluation)

    assert record.hypothesis_id == "H_TEST_001"
    assert record.manifest_hash == manifest.manifest_hash()
    assert record.strategy_id == manifest.strategy_id
    assert record.strategy_version == manifest.strategy_version
    assert record.parameters == manifest.parameters
    assert record.symbol_universe == manifest.universe
    assert record.timeframe == manifest.timeframe
    assert record.data_period == manifest.data_period
    assert record.period_split == split
    assert record.evaluation == evaluation
    assert record.experiment_id  # a real, non-empty UUID string


def test_build_experiment_record_generates_a_fresh_unique_id_each_call():
    manifest, split, evaluation = _real_manifest(), _real_split(), _real_evaluation()

    a = build_experiment_record(hypothesis_id="H_TEST_001", manifest=manifest, period_split=split, evaluation=evaluation)
    b = build_experiment_record(hypothesis_id="H_TEST_001", manifest=manifest, period_split=split, evaluation=evaluation)

    assert a.experiment_id != b.experiment_id


def test_hypothesis_id_is_mandatory_and_cannot_be_blank():
    manifest, split, evaluation = _real_manifest(), _real_split(), _real_evaluation()

    with pytest.raises(ValueError):
        build_experiment_record(hypothesis_id="", manifest=manifest, period_split=split, evaluation=evaluation)

    with pytest.raises(ValueError):
        build_experiment_record(hypothesis_id="   ", manifest=manifest, period_split=split, evaluation=evaluation)


def test_experiment_record_is_frozen():
    record = build_experiment_record(hypothesis_id="H_TEST_001", manifest=_real_manifest(), period_split=_real_split(), evaluation=_real_evaluation())
    with pytest.raises(Exception):
        record.hypothesis_id = "H_TEST_002"
