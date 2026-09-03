"""Phase 21 -- deterministic decision rules.

`classify` is a pure function: identical (symbol, candidate, risk_context,
config) always produces the identical (label, rationale) -- the roadmap's
"decision is reproducible" acceptance criterion, satisfied by
construction rather than tested-in separately. No randomness, no I/O, no
LLM call anywhere in this module.

Rule shape, in order:
  1. Already holding this symbol -> evaluate hold vs. exit (never BUY --
     re-entering a held position is not this rule's job).
  2. No scanner evidence at all -> NO_ACTION (never guess).
  3. Not holding, evidence available -> BUY / WATCH / AVOID based on
     factor corroboration (see decision_engine/config.py).
"""

from decision_engine.config import DecisionConfig
from decision_engine.models import DecisionLabel, RiskContext
from market_intelligence.models import CandidateScore


def classify(
    *, symbol: str, candidate: CandidateScore | None, risk_context: RiskContext, config: DecisionConfig
) -> tuple[DecisionLabel, list[str]]:
    reasons: list[str] = []

    if risk_context.has_open_position:
        reasons.append(f"{symbol} is already held in the account -- evaluating hold vs. exit, not a fresh entry.")
        if candidate is None:
            # No evidence at all -- NO_ACTION regardless of holding status, consistent with the
            # not-holding branch below. WATCH/EXIT must always be backed by scanner evidence
            # (Decision's own model_validator enforces this structurally).
            reasons.append("No current scanner data available to evaluate against the held position.")
            return DecisionLabel.NO_ACTION, reasons
        if candidate.composite_score <= 0:
            reasons.append(f"Composite score {candidate.composite_score:+.2f} is no longer positive.")
            return DecisionLabel.EXIT, reasons
        reasons.append(f"Composite score {candidate.composite_score:+.2f} remains positive -- no exit signal yet.")
        return DecisionLabel.WATCH, reasons

    if candidate is None:
        reasons.append(f"No scanner data available for {symbol}.")
        return DecisionLabel.NO_ACTION, reasons

    if config.require_corroboration_for_buy:
        factors_agree = candidate.composite_score > 0 and candidate.trend_score > 0 and candidate.momentum_score > 0
        if factors_agree:
            reasons.append(
                f"Composite ({candidate.composite_score:+.2f}), trend ({candidate.trend_score:+.2f}), and "
                f"momentum ({candidate.momentum_score:+.2f}) all agree positively."
            )
            return DecisionLabel.BUY, reasons
        if candidate.composite_score > 0:
            reasons.append(
                f"Composite score {candidate.composite_score:+.2f} is positive, but trend/momentum do not "
                "both corroborate it -- insufficient agreement for BUY."
            )
            return DecisionLabel.WATCH, reasons
        reasons.append(f"Composite score {candidate.composite_score:+.2f} is not positive.")
        return DecisionLabel.AVOID, reasons

    if candidate.composite_score > 0:
        reasons.append(f"Composite score {candidate.composite_score:+.2f} is positive (corroboration rule disabled).")
        return DecisionLabel.BUY, reasons
    reasons.append(f"Composite score {candidate.composite_score:+.2f} is not positive.")
    return DecisionLabel.AVOID, reasons
