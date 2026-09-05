from backtesting.costs import CostModel
from strategy.manifest import (
    StrategyManifest,
    freeze_trend_momentum_baseline_manifest,
    manifest_matches_current_code,
)


def test_freeze_trend_momentum_baseline_manifest_records_known_parameters():
    manifest = freeze_trend_momentum_baseline_manifest(universe=("AAPL", "RELIANCE.NS"))

    assert manifest.strategy_id == "trend_momentum_baseline"
    assert manifest.strategy_version == "1.0"
    assert manifest.parameters == {"stop_atr_multiplier": 1.5, "target_risk_reward": 2.0}
    assert manifest.universe == ("AAPL", "RELIANCE.NS")
    assert manifest.timeframe == "1d"
    assert manifest.data_period == "5y"
    assert manifest.cost_model_name == "default"


def test_freeze_trend_momentum_baseline_manifest_records_custom_cost_model():
    custom = CostModel(brokerage_per_fill=20.0, fees_pct=0.01, taxes_pct=0.05, entry_slippage_bps=5.0, exit_slippage_bps=5.0)
    manifest = freeze_trend_momentum_baseline_manifest(universe=("AAPL",), cost_model=custom)

    assert manifest.cost_model_name == "custom"
    assert manifest.cost_model_params["fees_pct"] == 0.01


def test_manifest_hash_is_stable_for_identical_configuration():
    a = freeze_trend_momentum_baseline_manifest(universe=("AAPL",))
    b = freeze_trend_momentum_baseline_manifest(universe=("AAPL",))

    # frozen_at differs (each call records "now") but the semantic
    # configuration is identical -- the hash must not depend on when it
    # was recorded.
    assert a.frozen_at != b.frozen_at
    assert a.manifest_hash() == b.manifest_hash()


def test_manifest_hash_changes_when_universe_differs():
    a = freeze_trend_momentum_baseline_manifest(universe=("AAPL",))
    b = freeze_trend_momentum_baseline_manifest(universe=("AAPL", "MSFT"))

    assert a.manifest_hash() != b.manifest_hash()


def test_manifest_hash_changes_when_cost_model_differs():
    a = freeze_trend_momentum_baseline_manifest(universe=("AAPL",))
    b = freeze_trend_momentum_baseline_manifest(universe=("AAPL",), cost_model=CostModel(brokerage_per_fill=999.0))

    assert a.manifest_hash() != b.manifest_hash()


def test_manifest_matches_current_code_is_true_for_a_freshly_frozen_manifest():
    manifest = freeze_trend_momentum_baseline_manifest(universe=("AAPL",))

    assert manifest_matches_current_code(manifest) is True


def test_manifest_matches_current_code_is_false_when_entry_rules_hash_is_stale():
    manifest = freeze_trend_momentum_baseline_manifest(universe=("AAPL",))
    stale = manifest.model_copy(update={"entry_rules_hash": "0000000000000000"})

    assert manifest_matches_current_code(stale) is False


def test_manifest_matches_current_code_is_false_when_exit_rules_hash_is_stale():
    manifest = freeze_trend_momentum_baseline_manifest(universe=("AAPL",))
    stale = manifest.model_copy(update={"exit_rules_hash": "0000000000000000"})

    assert manifest_matches_current_code(stale) is False


def test_manifest_round_trips_through_json():
    manifest = freeze_trend_momentum_baseline_manifest(universe=("AAPL", "TCS.NS"))

    restored = StrategyManifest.model_validate_json(manifest.model_dump_json())

    assert restored == manifest
    assert restored.manifest_hash() == manifest.manifest_hash()
