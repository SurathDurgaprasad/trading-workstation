"""ml_research/expected_value.py -- the DECISION-LAYER boundary
(PHASE_1_IMPLEMENTATION_SPEC.md Section 9 / Section 1's "P(target first)
!= BUY" invariant, restated in the user's own Phase 1 mission message).

The model (baseline_model.py) outputs a probability. THIS module is where
that probability becomes an economic quantity -- and only an economic
quantity, never a BUY/SELL/EXIT label, never a position size, never a
stop or target (those already exist, computed by labels.py at label-
generation time, reused here unchanged as the payoff inputs). Nothing in
this module calls risk/engine.py, decision_engine/rules.py, or paper/ --
Phase 1 does not wire this into the live risk engine at all (explicitly
out of scope, PHASE_1_IMPLEMENTATION_SPEC.md Section 2).

Simplification, disclosed here and in the final report because the
frozen label scheme (labels.py) is binary (TARGET_FIRST=1 vs
STOP_OR_TIMEOUT=0, per the user's own Phase 1 mission message Section 8),
not the three-outcome scheme PHASE_1_IMPLEMENTATION_SPEC.md's own Section
9 formula sketch assumed: this module has only p_target available from
the model, not separate p_stop/p_timeout. The non-target probability mass
(1 - p_target) is treated as if it always realized the FULL stop-loss
return -- a conservative approximation (real timeout outcomes are
typically smaller-magnitude than a full stop), not an attempt to recover
a 3-way split the binary model was never trained to produce.
"""
from __future__ import annotations

import pandas as pd

from backtesting.costs import CostModel

COST_MODEL = CostModel.india_nse_intraday_2026()  # unmodified, frozen -- Section 7 of the pre-registration


def cost_fraction_round_trip(cost_model: CostModel, notional: float) -> float:
    """Entry AND exit cost as a fraction of notional -- CostModel.
    cost_for_fill is charged per fill, and a completed trade has exactly
    two fills (entry, exit), matching CostModel's own brokerage_per_fill
    convention exactly."""
    entry_cost = cost_model.cost_for_fill(notional=notional)
    exit_cost = cost_model.cost_for_fill(notional=notional)
    return (entry_cost + exit_cost) / notional


def compute_expected_value(frame: pd.DataFrame, *, p_target_col: str, notional_per_trade: float = 25_000.0) -> pd.DataFrame:
    """`frame` must carry entry_reference_price, stop_price, target_price,
    and `p_target_col`. Returns a copy with expected_gross_return and
    expected_net_return columns added -- these are the DECISION-LAYER
    inputs, never a decision themselves. `notional_per_trade` is used only
    to compute the cost fraction (CostModel's brokerage is a flat currency
    amount, so its % impact depends on position size) -- 25,000 matches
    this project's own established capital_per_position convention from
    the H_MEANREV_011 portfolio research, reused here for consistency,
    not re-derived."""
    out = frame.copy()
    target_return = (out["target_price"] - out["entry_reference_price"]) / out["entry_reference_price"]
    stop_return = (out["stop_price"] - out["entry_reference_price"]) / out["entry_reference_price"]  # negative
    p_target = out[p_target_col]

    out["expected_gross_return"] = p_target * target_return + (1.0 - p_target) * stop_return

    cost_frac = cost_fraction_round_trip(COST_MODEL, notional_per_trade)
    out["expected_net_return"] = out["expected_gross_return"] - cost_frac
    out["round_trip_cost_fraction"] = cost_frac
    return out


def deterministic_rule_expected_value(frame: pd.DataFrame, *, notional_per_trade: float = 25_000.0) -> pd.DataFrame:
    """The benchmark side of the comparison: the EXISTING deterministic
    rule (decision_engine.rules.classify's own corroboration logic,
    reduced here to its trend_score/momentum_score/composite_score gate
    since risk_context.has_open_position is not meaningful for this
    dataset -- see evaluate.py's own docstring for the full citation)
    produces a binary trade/no-trade decision, not a probability. Its
    own "expected value" for this comparison is simply its OWN realized
    return net of the SAME cost model, on trades it would have taken --
    zero (no trade, no cost, no return) on bars it would not have."""
    out = frame.copy()
    would_trade = (out["composite_score"] > 0) & (out["trend_score"] > 0) & (out["momentum_score"] > 0)
    cost_frac = cost_fraction_round_trip(COST_MODEL, notional_per_trade)
    out["deterministic_would_trade"] = would_trade
    out["deterministic_net_return"] = 0.0
    out.loc[would_trade, "deterministic_net_return"] = out.loc[would_trade, "realized_return"] - cost_frac
    return out
