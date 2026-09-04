import hashlib

from pydantic import BaseModel, ConfigDict, Field


class CriticConfig(BaseModel):
    """Every threshold here is a conservative, documented default -- none
    of it was tuned against a backtest, matching risk/config.py's
    RiskConfig's own stated posture for its thresholds."""

    model_config = ConfigDict(frozen=True)

    max_data_staleness_seconds: float = Field(
        default=432_000.0,  # 5 days
        gt=0,
        description=(
            "How old decision.market_context.as_of may be relative to `now` before DATA_FRESHNESS fails. "
            "5 days is sized for shadow-run's own --interval 1d default (spans a long weekend/holiday "
            "without a false failure) -- a caller running on an intraday interval should pass a tighter value."
        ),
    )
    future_timestamp_tolerance_seconds: float = Field(
        default=300.0, ge=0, description="Small clock-skew allowance before FUTURE_TIMESTAMP fails on a bar timestamp ahead of `now`."
    )
    min_volume_ratio: float | None = Field(
        default=0.5, description="Below this, VOLUME_CONFIRMATION warns. None disables the check entirely (never fabricates a threshold when the caller has no basis for one)."
    )
    min_risk_reward: float = Field(
        default=1.5,
        gt=0,
        description=(
            "Matches RiskConfig's own default for consistency. A SEPARATE, EARLIER, advisory-strength "
            "check -- risk.engine.RiskEngine's own INVALID_RISK_REWARD veto remains the authoritative "
            "enforcement; this only lets the critic flag it earlier, with its own reason, before risk "
            "sizing even runs."
        ),
    )
    downgrade_warning_threshold: int = Field(
        default=2, ge=1, description="This many evaluated, failed WARNING-severity checks triggers DOWNGRADE instead of APPROVE."
    )

    def version_id(self) -> str:
        """Deterministic identifier for "exactly these threshold values",
        identical construction to RiskConfig.version_id() -- two configs
        with identical fields always produce the same ID; any field
        change produces a different one, no manual version bumping to forget."""
        return hashlib.sha256(self.model_dump_json().encode("utf-8")).hexdigest()[:16]
