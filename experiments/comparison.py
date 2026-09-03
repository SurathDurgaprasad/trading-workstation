"""Phase 37 -- experiment comparison: reuses learning.analysis's own
win-rate/average-return/profit-factor formula (imported directly, never
re-derived a third time) but computes it over each experiment's OWN
dataset/time boundary -- predictions whose decision shares the
experiment's config_version AND whose created_at falls within
[experiment.started_at, ended_at or now) -- rather than a config
version's lifetime aggregate. This is what makes it a genuine
per-experiment comparison instead of just another config_version
grouping (learning.analysis.compare_by_config_version already does the
latter, unchanged, for the lifetime view).
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from experiments.models import Experiment
from experiments.store import ExperimentStore
from learning.analysis import EvaluatedPrediction, _resolution_stats, _resolved_returns


@dataclass(frozen=True)
class ExperimentComparison:
    experiment: Experiment
    ended_at: datetime | None
    """None if still ongoing (no ENDED event recorded yet)."""
    total: int
    resolved: int
    win_rate: float | None
    average_return: float | None
    profit_factor: float | None


def _naive_utc(value: datetime) -> datetime:
    """Normalizes to a UTC-aware datetime regardless of whether `value`
    arrived naive -- avoids the exact naive/aware comparison bug Phase 33
    found in market.data_provider._to_timestamp / learning.regime.
    classify_regime_at. This project's own predictions/experiments are
    always created with an aware `datetime.now(timezone.utc)` in
    practice, but a caller-constructed value (e.g. in a test) might not
    be -- never assume."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def compare_experiments(experiments: list[Experiment], items: list[EvaluatedPrediction], store: ExperimentStore, *, now: datetime | None = None) -> list[ExperimentComparison]:
    resolved_now = now or datetime.now(timezone.utc)
    result = []
    for experiment in experiments:
        ended_at = store.ended_at(experiment.experiment_id)
        window_start = _naive_utc(experiment.started_at)
        window_end = _naive_utc(ended_at) if ended_at is not None else resolved_now

        in_window = [
            item for item in items
            if item.decision is not None
            and item.decision.config_version == experiment.config_version
            and window_start <= _naive_utc(item.prediction.created_at) <= window_end
        ]
        returns = _resolved_returns(in_window)
        win_rate, average_return, profit_factor = _resolution_stats(returns)
        result.append(ExperimentComparison(
            experiment=experiment, ended_at=ended_at, total=len(in_window), resolved=len(returns),
            win_rate=win_rate, average_return=average_return, profit_factor=profit_factor,
        ))
    return result
