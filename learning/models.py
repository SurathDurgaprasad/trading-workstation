"""Phase 24 -- performance learning models.

Roadmap Phase 24's own hard rule: "No automatic strategy modification
without: Versioning, Evaluation, Rollback Capability, Audit Trail."
Nothing in this package writes to decision_engine.config.DecisionConfig,
risk.config.RiskConfig, or any other configuration -- this is read-only
analysis over Phase 23's prediction/evaluation history, full stop.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from learning.regime import MarketRegime


class StrategyPerformance(BaseModel):
    """Grouped by Decision.config_version -- the only real "strategy
    variant" concept that currently exists (decision_engine.rules.classify
    has exactly one deterministic rule with one toggleable config flag).
    Not a fabricated multi-strategy comparison."""

    model_config = ConfigDict(frozen=True)

    config_version: str
    total: int
    resolved: int
    win_rate: float | None
    average_return: float | None
    profit_factor: float | None


class RegimePerformance(BaseModel):
    model_config = ConfigDict(frozen=True)

    regime: MarketRegime
    total: int
    resolved: int
    win_rate: float | None
    average_return: float | None


class CalibrationBucket(BaseModel):
    """"Confidence calibration" here concretely means "does a higher
    market_intelligence.CandidateScore.composite_score predict a better
    outcome" -- decision_engine.models.Decision has no numeric
    stated-confidence field of its own yet, so this is not literal
    probability calibration. A simple two-bucket median split, not
    quartiles/quintiles, given typically small prediction counts for a
    personal tool."""

    model_config = ConfigDict(frozen=True)

    bucket_label: str
    total: int
    resolved: int
    win_rate: float | None
    average_return: float | None


class SignalQualityReport(BaseModel):
    """Aggregates of PredictionEvaluation.max_favorable_excursion /
    max_adverse_excursion, which Phase 23 already computes and stores --
    no new data collection needed here."""

    model_config = ConfigDict(frozen=True)

    resolved: int
    average_favorable_excursion: float | None
    average_adverse_excursion: float | None


class LearningReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated_at: datetime
    total_predictions_considered: int
    strategy_comparison: list[StrategyPerformance]
    regime_performance: list[RegimePerformance]
    confidence_calibration: list[CalibrationBucket]
    real_confidence_calibration: list[CalibrationBucket] = []
    """Phase 34 -- calibration against decision_engine.confidence's real,
    deterministic score (fixed LOW/MEDIUM/HIGH bands), distinct from
    `confidence_calibration` above (a composite-score median-split
    proxy, kept for continuity). Empty for any prediction set with no
    Decision.confidence recorded (e.g. all pre-Phase-34 decisions)."""
    signal_quality: SignalQualityReport
    notes: list[str]
    """Honest statements of what this report does NOT cover -- e.g.
    Experiment Tracking and Model Comparison, recognized roadmap features
    with no implementation this phase, not silently faked."""
