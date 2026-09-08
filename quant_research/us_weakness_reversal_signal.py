"""H_MEANREV_002 (strategy/hypothesis_registry.py): does US-only extreme
5-day price weakness show a real, forward-positive reversal that
SURVIVES becoming an actual, cost-aware, risk-sized strategy -- not
just a raw price-behavior observation?

This candidate came from quant_research/market_behavior.py's own broad
68-condition sweep (TRADING BRAIN EXECUTION LOOP mission, Part D-E),
then survived every adversarial check applied to it (Part I):
decisive positive mean forward return (95% CI excludes zero) at
h=2,3,5,10 across development, validation, AND out-of-sample with a
threshold FROZEN from development data only; not concentrated in any
single symbol; survives up to a 60bps round-trip cost assumption; and
at h=5 specifically, remains decisive even under a conservative
Bonferroni correction for the full 68-condition sweep it was selected
from. This module is the necessary next step per the mission's own
explicit ordering (Part J: "DO NOT build strategies first... only
after identifying a positive conditional market behavior") -- turning
that raw finding into a real, simulated, cost-aware trade to see if it
survives the harder bar.

FROZEN_WEAKNESS_THRESHOLD below is not a parameter to tune -- it is the
exact 5th percentile of the real US-pooled development-period
trailing_return_5 distribution (n=4928), computed once via
quant_research/market_behavior.py against the real 9-symbol US universe
and hardcoded here verbatim. Refitting it against validation/OOS data,
or after seeing this module's own backtest result, would be exactly
the data-snooping this project's entire discipline exists to prevent.

Computes trailing_return_5 INLINE from indicator_series['close'] at
generate_signal() time rather than as a precomputed column -- this
means, unlike every other new hypothesis this session, this strategy
needs NO custom runner at all: backtesting.runner.run_full_backtest and
backtesting.exit_experiments.run_universe_time_based_exit_experiment
both already accept any Strategy-protocol object and are reused here
completely unchanged.
"""

import pandas as pd

from strategy.baseline import STOP_ATR_MULTIPLIER, TARGET_RISK_REWARD
from strategy.signal import ReasonCode, Side, Signal

FROZEN_WEAKNESS_THRESHOLD = -0.053477
"""5th percentile of real US-pooled development-period trailing_return_5
(n=4928), computed 2026-09-08 via quant_research/market_behavior.py
against AAPL/AMZN/GOOGL/JNJ/JPM/MSFT/NVDA/WMT/XOM, 5y daily bars, 60/20/20
chronological split. Frozen -- never recomputed or refit by this module."""

TIME_EXIT_HOLDING_BARS = 5
"""The one forward horizon that remained decisive positive under a
Bonferroni correction for the full 68-condition sweep this candidate
was selected from, in ALL THREE of development/validation/out-of-sample
-- not an arbitrary choice, but not re-derived from a grid search
either; a single, pre-committed value informed directly by the raw
finding that motivated this module's own existence."""


class USWeaknessReversalStrategy:
    """STANDALONE signal generator -- ignores SMA/RSI/MACD/volume
    entirely (unlike TrendMomentumBaseline). A frozen-threshold
    trailing-5-day-return condition, isolated from every trend-
    continuation condition already falsified in Family A. Implements
    the Strategy protocol; deliberately NOT registered in
    strategy/registry.py -- a research candidate, not a deployed
    strategy, the same posture every other hypothesis candidate in
    this project already takes."""

    name = "us_weakness_reversal"
    version = "meanrev-002-candidate"

    def generate_signal(self, indicator_series: pd.DataFrame, index: int, symbol: str) -> Signal | None:
        if index < 5:
            return None  # insufficient history for a 5-bar trailing return -- fail closed

        close = indicator_series["close"]
        prior_close = close.iloc[index - 5]
        if pd.isna(prior_close) or float(prior_close) <= 0:
            return None
        trailing_return_5 = float(close.iloc[index]) / float(prior_close) - 1

        if trailing_return_5 >= FROZEN_WEAKNESS_THRESHOLD:
            return None

        row = indicator_series.iloc[index]
        atr = row.get("atr_14")
        if atr is None or pd.isna(atr) or float(atr) <= 0:
            return None

        reference_price = float(row["close"])
        stop_distance = float(atr) * STOP_ATR_MULTIPLIER
        stop_price = reference_price - stop_distance
        target_price = reference_price + stop_distance * TARGET_RISK_REWARD

        return Signal(
            symbol=symbol, generated_at=indicator_series.index[index], side=Side.LONG,
            reference_price=reference_price, stop_price=stop_price, target_price=target_price,
            risk_reward=TARGET_RISK_REWARD, strategy_name=self.name,
            reason_codes=[ReasonCode.MEAN_REVERSION_OVERSOLD],
        )
