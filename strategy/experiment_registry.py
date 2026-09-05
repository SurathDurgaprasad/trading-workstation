"""Scientific strategy research foundation, Priority #1 -- a unified,
persistent Experiment Record tying together everything a future
researcher (or this project's own future self) needs to trust or
distrust a result: an experiment_id, a hypothesis_id, a strategy
manifest hash, its parameters, dataset provenance (symbol universe +
timeframe + the ACTUAL chronological date ranges used, not just a
request string like "5y"), and the development/validation/out-of-sample
evaluation itself.

Deliberately composes this project's own EXISTING machinery rather than
duplicating it:
  - strategy.manifest.StrategyManifest -- WHAT was tested (content-hashed
    entry/exit rules, parameters, cost model, universe/timeframe/period).
  - backtesting.splits.PeriodSplit -- WHEN, as actual chronological
    boundaries (already validated chronological/contiguous by that
    model's own validator).
  - strategy.promotion_gate.PromotionEvaluation -- the dev/val/oos
    verdict itself, computed by the SAME statistical standard used
    everywhere else in this project.
An ExperimentRecord never re-derives or duplicates the logic in any of
these; it only references their already-validated output.

Experiment Discipline's own explicit rule -- "never modify strategy code
without registering a hypothesis" -- is enforced STRUCTURALLY here, not
just by convention: hypothesis_id is a mandatory, non-blank field. There
is no code path to build an ExperimentRecord without one.
"""

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, field_validator

from backtesting.splits import PeriodSplit
from strategy.manifest import StrategyManifest
from strategy.promotion_gate import PromotionEvaluation


class ExperimentRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    experiment_id: str
    hypothesis_id: str
    """References strategy.hypothesis_registry's own vocabulary (e.g.
    "H_EXIT_005") when the experiment tests an already-cataloged
    hypothesis, or a new free-form ID when it doesn't yet exist there --
    ALWAYS required, never blank (see this module's own docstring)."""
    manifest_hash: str
    strategy_id: str
    strategy_version: str
    parameters: dict[str, float]
    symbol_universe: tuple[str, ...]
    timeframe: str
    data_period: str
    period_split: PeriodSplit
    """The ACTUAL chronological development/validation/out-of-sample
    date boundaries used for this specific run -- distinct from
    data_period (a fetch request like "5y"), which says how much history
    was asked for, not the exact split computed from what came back."""
    evaluation: PromotionEvaluation
    recorded_at: str
    """ISO timestamp this record was built -- provenance only, matching
    StrategyManifest.frozen_at's own convention."""

    @field_validator("hypothesis_id")
    @classmethod
    def _hypothesis_id_is_mandatory(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError(
                "hypothesis_id is mandatory -- every experiment must be registered against a hypothesis "
                "(Experiment Discipline's own rule: never modify strategy code without registering one)."
            )
        return value


def build_experiment_record(
    *,
    hypothesis_id: str,
    manifest: StrategyManifest,
    period_split: PeriodSplit,
    evaluation: PromotionEvaluation,
) -> ExperimentRecord:
    """Assembles a new ExperimentRecord from already-computed pieces --
    does not run a backtest, compute a manifest, or evaluate promotion
    itself; those remain the caller's own responsibility, using this
    project's existing functions for each (strategy.manifest.
    freeze_trend_momentum_baseline_manifest or a hand-built
    StrategyManifest, backtesting.splits.split_periods, strategy.
    promotion_gate.evaluate_promotion)."""
    return ExperimentRecord(
        experiment_id=str(uuid.uuid4()),
        hypothesis_id=hypothesis_id,
        manifest_hash=manifest.manifest_hash(),
        strategy_id=manifest.strategy_id,
        strategy_version=manifest.strategy_version,
        parameters=manifest.parameters,
        symbol_universe=manifest.universe,
        timeframe=manifest.timeframe,
        data_period=manifest.data_period,
        period_split=period_split,
        evaluation=evaluation,
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )
