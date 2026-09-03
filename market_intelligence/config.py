"""Phase 19 -- scanner thresholds and factor weights.

Every gate defaults to a no-op (0.0 / None) rather than a fabricated
cutoff: this project only sets a specific numeric threshold once it has
evidence for it (see e.g. quant_research/volume_signal.py's percentile fit).
No liquidity/volatility study has been run yet, so the defaults here
leave those gates structurally present -- matching the roadmap's own
Market Universe -> Liquidity Filter -> ... -> Candidate Ranking pipeline
-- but inert until a caller supplies a real, evidence-based value.

Factor weights default to equal (1.0 each) for the same reason: nothing
has been tuned against historical performance, so "equal weight until
proven otherwise" is the only defensible starting point.
"""

import hashlib

from pydantic import BaseModel, ConfigDict, Field


class ScannerConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_bars: int = Field(
        default=60, ge=51,
        description="Enough history for SMA50 (market.indicators' longest primitive) plus headroom for the scanner's own lookback windows.",
    )

    liquidity_lookback: int = Field(default=20, ge=1, description="Trading days averaged into avg_daily_value (close * volume).")
    min_avg_daily_value: float = Field(default=0.0, ge=0, description="Liquidity gate floor, in the symbol's own currency. 0.0 = no-op.")

    min_price: float = Field(default=0.0, ge=0, description="Price gate floor. 0.0 = no-op.")
    max_price: float | None = Field(default=None, description="Price gate ceiling. None = no-op.")

    min_volume_ratio: float = Field(default=0.0, ge=0, description="Volume gate floor on the last bar's volume_ratio (vs its 20d average). 0.0 = no-op.")

    min_atr_pct_of_price: float | None = Field(default=None, description="Volatility gate floor on atr_14/close. None = no-op.")
    max_atr_pct_of_price: float | None = Field(default=None, description="Volatility gate ceiling on atr_14/close. None = no-op.")

    breakout_lookback: int = Field(default=20, ge=2, description="Prior-bar window (excluding the current bar) a new high is measured against.")
    relative_strength_lookback: int = Field(default=20, ge=2, description="Trailing-return window for both relative-strength-vs-benchmark and sector strength.")

    weight_trend: float = Field(default=1.0, description="Composite score weight -- equal-weighted by default, not tuned.")
    weight_momentum: float = Field(default=1.0, description="Composite score weight -- equal-weighted by default, not tuned.")
    weight_breakout: float = Field(default=1.0, description="Composite score weight -- equal-weighted by default, not tuned.")
    weight_relative_strength: float = Field(default=1.0, description="Composite score weight -- equal-weighted by default, not tuned.")
    weight_sector_strength: float = Field(default=1.0, description="Composite score weight -- equal-weighted by default, not tuned.")

    def version_id(self) -> str:
        """Deterministic identifier for exactly these values -- same
        construction as risk.config.RiskConfig.version_id, so a ScanReport
        can record which exact config produced it without a manual
        version bump to forget."""
        return hashlib.sha256(self.model_dump_json().encode("utf-8")).hexdigest()[:16]
