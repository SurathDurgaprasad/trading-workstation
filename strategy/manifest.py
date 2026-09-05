"""Strategy science, Phase 1 -- a frozen, reproducible, content-hashed
record of exactly what a strategy configuration IS, so a future
experiment (Phase 2) can never silently drift from what "the baseline"
meant when it was measured. Every experiment must reference a manifest
by its content hash, not a mutable name string.

TrendMomentumBaseline's entry/exit rules are hardcoded Python logic, not
data-driven parameters -- there is no mechanical way to extract and hash
"the rules themselves" without either executing arbitrary code
introspection (fragile, over-engineered for what this needs) or hashing
the relevant module's own source text. This does the latter, split into
two genuinely distinct pieces:
  - entry_rules_hash: strategy/baseline.py's own source (the strategy-
    specific entry condition AND the stop/target levels it computes at
    signal time).
  - exit_rules_hash: backtesting/execution.py's own source (the SHARED
    bar-by-bar fill/exit mechanics -- same-bar-ambiguity rule, cost/
    slippage application -- every strategy in this project reuses
    unmodified, per that module's own docstring).
A manifest is only as trustworthy as this hash: if the underlying source
changes without re-freezing a new manifest, the hash mismatch is the
mechanism that reveals the drift -- see manifest_matches_current_code().
"""

import hashlib
import inspect
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict

from backtesting.costs import CostModel


class StrategyManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy_id: str
    strategy_version: str
    entry_rules_hash: str
    exit_rules_hash: str
    parameters: dict[str, float]
    cost_model_name: str
    cost_model_params: dict[str, float]
    universe: tuple[str, ...]
    timeframe: str
    data_period: str
    frozen_at: str
    """ISO timestamp this manifest was recorded -- a provenance field, not
    part of the configuration's own identity (excluded from manifest_hash
    for exactly that reason)."""

    def manifest_hash(self) -> str:
        """Content hash of the semantic configuration only (excludes
        frozen_at) -- two manifests describing the identical strategy/
        cost-model/universe/timeframe/period combination hash identically
        regardless of when each was built. This is what an Experiment
        (Phase 2) should reference, not the mutable strategy_id string."""
        payload = self.model_dump_json(exclude={"frozen_at"})
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _hash_module_source(module) -> str:
    return hashlib.sha256(inspect.getsource(module).encode()).hexdigest()[:16]


def freeze_trend_momentum_baseline_manifest(
    *,
    universe: tuple[str, ...],
    timeframe: str = "1d",
    data_period: str = "5y",
    cost_model: CostModel | None = None,
) -> StrategyManifest:
    """The formally frozen Phase 7 baseline strategy -- see
    strategy/baseline.py's own module docstring for the exact entry/stop/
    target rules this hashes. `universe`/`timeframe`/`data_period` are
    NOT properties of the strategy itself (the same strategy can be
    tested against different universes) but ARE part of what makes one
    experiment's result comparable to another's, so they are recorded
    here rather than left implicit."""
    import backtesting.execution as execution_module
    import strategy.baseline as baseline_module
    from strategy.baseline import STOP_ATR_MULTIPLIER, TARGET_RISK_REWARD, TrendMomentumBaseline

    cost_model = cost_model or CostModel()

    return StrategyManifest(
        strategy_id=TrendMomentumBaseline.name,
        strategy_version=TrendMomentumBaseline.version,
        entry_rules_hash=_hash_module_source(baseline_module),
        exit_rules_hash=_hash_module_source(execution_module),
        parameters={"stop_atr_multiplier": STOP_ATR_MULTIPLIER, "target_risk_reward": TARGET_RISK_REWARD},
        cost_model_name="default" if cost_model == CostModel() else "custom",
        cost_model_params=cost_model.model_dump(),
        universe=tuple(universe),
        timeframe=timeframe,
        data_period=data_period,
        frozen_at=datetime.now(timezone.utc).isoformat(),
    )


def manifest_matches_current_code(manifest: StrategyManifest) -> bool:
    """True only if strategy/baseline.py and backtesting/execution.py's
    source text is BYTE-IDENTICAL to what this manifest was frozen
    against -- the mechanism that reveals silent rule drift. A caller
    about to trust a manifest's own historical results as still
    representative of "what the code does today" should check this
    first; False means the manifest describes a strategy that no longer
    exists in the code, and any comparison against it is invalid."""
    import backtesting.execution as execution_module
    import strategy.baseline as baseline_module

    return (
        manifest.entry_rules_hash == _hash_module_source(baseline_module)
        and manifest.exit_rules_hash == _hash_module_source(execution_module)
    )
