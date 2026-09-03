"""Phase 21 -- decision rule configuration.

Deliberately has no numeric composite-score threshold: Phase 19's own
report states its factor weights are "equal-weighted by default, not
tuned" -- no historical study has validated what composite_score value
means "good enough to buy." Rather than fabricate a magic-number cutoff
this project has no evidence for, decision_engine.rules.classify's BUY
rule is about SIGN AGREEMENT across independent factors (composite,
trend, momentum all positive), which is meaningful regardless of the
composite score's uncalibrated scale. The one behavioral knob this phase
exposes is whether that agreement is required at all.
"""

import hashlib

from pydantic import BaseModel, ConfigDict, Field


class DecisionConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    require_corroboration_for_buy: bool = Field(
        default=True,
        description=(
            "BUY requires composite_score, trend_score, and momentum_score to all be positive "
            "-- independent corroboration, not a single blended number's precise magnitude. "
            "When False, any positive composite_score is enough for BUY (a looser, less-defensible rule -- "
            "off by default)."
        ),
    )

    def version_id(self) -> str:
        """Same sha256-of-model_dump_json construction as risk.config.RiskConfig.version_id
        and market_intelligence.config.ScannerConfig.version_id."""
        return hashlib.sha256(self.model_dump_json().encode("utf-8")).hexdigest()[:16]
