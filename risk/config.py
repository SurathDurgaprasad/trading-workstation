import hashlib

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RiskConfig(BaseModel):
    """Every threshold here is a conservative, documented default — none of
    it was tuned against the AAPL backtest. Percent fields are percentage
    points (e.g. 3.0 means 3%, not 0.03)."""

    model_config = ConfigDict(frozen=True)

    risk_per_trade_pct: float = Field(default=0.5, gt=0, description="Spec's own suggested conservative default.")
    max_daily_loss_pct: float = Field(default=3.0, gt=0, description="Matches the blueprint's 3%-of-equity daily halt.")
    max_drawdown_pct: float = Field(
        default=10.0,
        gt=0,
        description=(
            "Matches the blueprint's 10%-drawdown 'Critical' tier: 'All trading "
            "suspended... Human intervention required.' No automatic recovery is "
            "intentional here — see risk/engine.py's module docstring."
        ),
    )
    max_exposure_pct: float = Field(default=25.0, gt=0, description="Matches the blueprint's 25% max portfolio exposure.")

    max_consecutive_losses: int = Field(
        default=3,
        ge=1,
        description=(
            "Matches the blueprint's 'Consecutive Loss Control' threshold. Reaching "
            "this does NOT reject trades — it reduces risk-per-trade by "
            "consecutive_loss_risk_multiplier (blueprint: 'Position size reduced by "
            "50% for next 5 trades') so the account can still trade its way out. "
            "Only consecutive_loss_hard_limit rejects outright."
        ),
    )
    consecutive_loss_risk_multiplier: float = Field(
        default=0.5, gt=0, le=1.0, description="Blueprint's exact figure: reduce risk-per-trade by 50% during a loss streak."
    )
    consecutive_loss_hard_limit: int = Field(
        default=6,
        ge=1,
        description=(
            "Circuit breaker: reject outright if losses continue even at reduced "
            "size. Not from the blueprint (which never specifies a hard reject for "
            "this rule) — a defensible secondary backstop, default 2x the soft "
            "limit. Set equal to max_consecutive_losses to recover Phase 4's "
            "original immediate-reject behavior."
        ),
    )

    min_risk_reward: float = Field(default=1.5, gt=0, description="Spec's own example threshold; baseline strategy always offers 2.0.")

    @model_validator(mode="after")
    def _hard_limit_not_below_soft_limit(self) -> "RiskConfig":
        if self.consecutive_loss_hard_limit < self.max_consecutive_losses:
            raise ValueError("consecutive_loss_hard_limit must be >= max_consecutive_losses.")
        return self

    def version_id(self) -> str:
        """Deterministic identifier for "exactly these threshold values"
        (Phase 6 spec §14 — "which exact rules produced this trade?", not a
        vague label like "latest"). Two configs with identical fields always
        produce the same ID; any field change produces a different one —
        no manual version bumping to forget."""
        return hashlib.sha256(self.model_dump_json().encode("utf-8")).hexdigest()[:16]
