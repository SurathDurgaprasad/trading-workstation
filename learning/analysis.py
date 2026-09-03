"""Phase 24 -- read-only performance analysis over Phase 23's prediction
history. Every function here is a pure function of already-loaded data;
none of them touch a store or a configuration object. The CLI layer
(main.py's `learn` command) is the only place that joins
predictions.store.PredictionStore with decision_engine.store.
DecisionStore into the EvaluatedPrediction list these functions consume.

win_rate/average_return/profit_factor is the SAME formula
predictions.tracker.summarize_predictions already uses (a resolved
LONG-only prediction's actual_return sign IS its win/loss signal, by
construction of build_signal_for_buy's stop < entry < target ordering)
-- factored into _resolution_stats here so the three functions below
that need it never risk drifting into a different formula from each
other, without importing across predictions/ -> learning/ (the wrong
direction; predictions/ has no dependency on learning/).
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from decision_engine.models import Decision
from learning.models import CalibrationBucket, LearningReport, RegimePerformance, SignalQualityReport, StrategyPerformance
from learning.regime import classify_regime_at
from market.data_provider import MarketDataProvider
from predictions.models import RESOLVED_STATES, PredictionEvaluation, PredictionRecord


@dataclass(frozen=True)
class EvaluatedPrediction:
    prediction: PredictionRecord
    evaluation: PredictionEvaluation
    """The LATEST evaluation for this prediction -- never an older,
    superseded one."""
    decision: Decision | None
    """None if the originating decision_id could not be found in the
    DecisionStore (e.g. a different database, or purged history) --
    degrades gracefully rather than crashing; see each function's own
    handling of a None decision below."""


def _resolution_stats(returns: list[float]) -> tuple[float | None, float | None, float | None]:
    if not returns:
        return None, None, None
    wins = sum(1 for r in returns if r > 0)
    win_rate = wins / len(returns)
    average_return = sum(returns) / len(returns)
    gains = sum(r for r in returns if r > 0)
    losses = sum(r for r in returns if r < 0)
    profit_factor = (gains / abs(losses)) if losses < 0 else None
    return win_rate, average_return, profit_factor


def _resolved_returns(items: list[EvaluatedPrediction]) -> list[float]:
    return [
        item.evaluation.actual_return for item in items
        if item.evaluation.outcome in RESOLVED_STATES and item.evaluation.actual_return is not None
    ]


def compare_by_config_version(items: list[EvaluatedPrediction]) -> list[StrategyPerformance]:
    groups: dict[str, list[EvaluatedPrediction]] = {}
    for item in items:
        if item.decision is None:
            continue
        groups.setdefault(item.decision.config_version, []).append(item)

    result = []
    for config_version, group in groups.items():
        returns = _resolved_returns(group)
        win_rate, average_return, profit_factor = _resolution_stats(returns)
        result.append(StrategyPerformance(
            config_version=config_version, total=len(group), resolved=len(returns),
            win_rate=win_rate, average_return=average_return, profit_factor=profit_factor,
        ))
    return sorted(result, key=lambda s: s.config_version)


def compute_regime_performance(
    items: list[EvaluatedPrediction], *, provider: MarketDataProvider, period: str = "2y"
) -> list[RegimePerformance]:
    groups = {}
    for item in items:
        regime = classify_regime_at(
            item.prediction.symbol, item.prediction.entry_time,
            provider=provider, period=period, interval=item.prediction.interval,
        )
        groups.setdefault(regime, []).append(item)

    result = []
    for regime, group in groups.items():
        returns = _resolved_returns(group)
        win_rate, average_return, _ = _resolution_stats(returns)
        result.append(RegimePerformance(regime=regime, total=len(group), resolved=len(returns), win_rate=win_rate, average_return=average_return))
    return sorted(result, key=lambda r: r.regime.value)


def compute_confidence_calibration(items: list[EvaluatedPrediction]) -> list[CalibrationBucket]:
    scored = [item for item in items if item.decision is not None and item.decision.scanner_evidence is not None]
    if not scored:
        return []

    scores = sorted(item.decision.scanner_evidence.composite_score for item in scored)
    n = len(scores)
    # Odd n: the exact middle score. Even n: the average of the two middle
    # scores (may not equal any actual score). Either way, "above" is
    # strictly greater than this threshold and "at or below" includes the
    # threshold itself -- well-defined and shown in the bucket label so a
    # reader never has to guess which side the boundary landed on.
    median = scores[n // 2] if n % 2 == 1 else (scores[n // 2 - 1] + scores[n // 2]) / 2

    above = [item for item in scored if item.decision.scanner_evidence.composite_score > median]
    at_or_below = [item for item in scored if item.decision.scanner_evidence.composite_score <= median]

    buckets = []
    for label, group in ((f"Above median composite ({median:.2f})", above), (f"At or below median composite ({median:.2f})", at_or_below)):
        returns = _resolved_returns(group)
        win_rate, average_return, _ = _resolution_stats(returns)
        buckets.append(CalibrationBucket(bucket_label=label, total=len(group), resolved=len(returns), win_rate=win_rate, average_return=average_return))
    return buckets


_CONFIDENCE_BUCKETS = (
    (0.0, 0.5, "LOW confidence (<50%)"),
    (0.5, 0.8, "MEDIUM confidence (50-80%)"),
    (0.8, 1.01, "HIGH confidence (>=80%)"),  # 1.01 so a real 1.0 (100%) score is included in the top bucket
)


def compute_real_confidence_calibration(items: list[EvaluatedPrediction]) -> list[CalibrationBucket]:
    """Phase 34 -- genuine calibration against decision_engine.confidence's
    real, deterministic score (Decision.confidence), NOT the composite-
    score median-split proxy `compute_confidence_calibration` above uses.
    Fixed bucket boundaries (not a moving median) so a reader can compare
    across different scans/runs on stable, interpretable terms: does a
    HIGH-confidence decision actually resolve better than a LOW one?

    Only considers items whose Decision actually has a `confidence` score
    (None for any Decision built before this phase, or with no
    scanner_evidence) -- never fabricates a score for one that lacks it."""
    scored = [item for item in items if item.decision is not None and item.decision.confidence is not None]
    if not scored:
        return []

    buckets = []
    for low, high, label in _CONFIDENCE_BUCKETS:
        group = [item for item in scored if low <= item.decision.confidence < high]
        returns = _resolved_returns(group)
        win_rate, average_return, _ = _resolution_stats(returns)
        buckets.append(CalibrationBucket(bucket_label=label, total=len(group), resolved=len(returns), win_rate=win_rate, average_return=average_return))
    return buckets


def compute_signal_quality(items: list[EvaluatedPrediction]) -> SignalQualityReport:
    # Unlike strategy comparison / calibration, this only needs
    # PredictionEvaluation data -- a missing Decision does not exclude an
    # item here, since MFE/MAE never came from the Decision in the first place.
    resolved = [item for item in items if item.evaluation.outcome in RESOLVED_STATES]
    mfe_values = [item.evaluation.max_favorable_excursion for item in resolved if item.evaluation.max_favorable_excursion is not None]
    mae_values = [item.evaluation.max_adverse_excursion for item in resolved if item.evaluation.max_adverse_excursion is not None]

    return SignalQualityReport(
        resolved=len(resolved),
        average_favorable_excursion=(sum(mfe_values) / len(mfe_values)) if mfe_values else None,
        average_adverse_excursion=(sum(mae_values) / len(mae_values)) if mae_values else None,
    )


def build_learning_report(
    items: list[EvaluatedPrediction], *, provider: MarketDataProvider, now: datetime | None = None
) -> LearningReport:
    return LearningReport(
        generated_at=now or datetime.now(timezone.utc),
        total_predictions_considered=len(items),
        strategy_comparison=compare_by_config_version(items),
        regime_performance=compute_regime_performance(items, provider=provider),
        confidence_calibration=compute_confidence_calibration(items),
        real_confidence_calibration=compute_real_confidence_calibration(items),
        signal_quality=compute_signal_quality(items),
        notes=[
            "Experiment Tracking is not implemented this phase -- no experiment-tracking framework exists in this system yet.",
            "Model Comparison is not implemented this phase -- there is exactly one deterministic decision rule "
            "(decision_engine.rules.classify) with one toggleable flag, not multiple competing models; see "
            "strategy_comparison (grouped by DecisionConfig.version_id) for the closest available comparison.",
            "confidence_calibration (composite-score median split) is a legacy proxy kept for continuity -- "
            "real_confidence_calibration (Phase 34) uses decision_engine.confidence's actual deterministic "
            "score against fixed LOW/MEDIUM/HIGH bands and is the more meaningful of the two.",
        ],
    )
