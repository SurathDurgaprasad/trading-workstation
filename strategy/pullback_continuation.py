"""Strategy science, STRATEGY EDGE DISCOVERY mission Phase B --
H_ENTRY_001 in this mission's own naming; corresponds to the existing
strategy/hypothesis_registry.py's H_ENTRY_003 ("Pullback entries...
outperform breakout-style confirmation entries"), tested here for the
first time. TrendMomentumBaseline's own entry condition fires only
AFTER trend+momentum+volume all align simultaneously -- by
construction, this can mean buying into a move that has already run,
rather than a genuine continuation. This strategy instead waits for a
short pullback (RSI14 cooling from a recent push) within the SAME
underlying uptrend, entering on the bar that resumes upward.

Isolates ENTRY CONDITION as the only variable: reuses
TrendMomentumBaseline's own ATR-based stop/target risk mechanics
verbatim (STOP_ATR_MULTIPLIER, TARGET_RISK_REWARD) -- the SAME
isolation principle strategy/simple_baselines.py and
backtesting/random_baseline.py already established. Plugs directly into
backtesting.engine.run_backtest UNMODIFIED: entry-signal generation is
the strategy.contracts.Strategy extension point every other strategy
variant in this project already uses (only H_EXIT_* hypotheses, which
change EXIT mechanics, need backtesting/exit_experiments.py's own
isolated bar-processing loop). Deliberately NOT registered in
strategy/registry.py (same precedent as SimpleMomentumBaseline/
SimpleTrendBaseline/RandomEntryStrategy -- a comparison-only variant,
not a production strategy candidate).
"""

import pandas as pd

from strategy.baseline import STOP_ATR_MULTIPLIER, TARGET_RISK_REWARD
from strategy.signal import ReasonCode, Side, Signal

PULLBACK_LOOKBACK_BARS = 2
"""How far back to look for evidence of a recent, real bullish push
before the pullback -- a short, "still the same swing" window, not a
multi-week lookback that could span into a genuinely different move."""
RECENT_STRENGTH_RSI_THRESHOLD = 55.0
"""RSI14 at least this high PULLBACK_LOOKBACK_BARS ago is the evidence
that "a real push happened" -- a moderate strength threshold above the
baseline's own >50 momentum condition, not tuned against any backtest
result."""
PULLBACK_RSI_LOW = 40.0
PULLBACK_RSI_HIGH = 55.0
"""The cooled-off zone the entry bar's own RSI14 must sit in: enough of
a pullback to be genuine (below the recent-strength threshold) but not
so deep it signals a trend break (below 40 reads as "momentum
reversing", not "healthy pullback")."""


class PullbackContinuationStrategy:
    """Entry condition (ALL must hold on the generating bar):
      - trend:      SMA20 > SMA50 (same uptrend context as the baseline)
      - momentum:   MACD > MACD signal (net-bullish, but NOT requiring
                    RSI14 > 50 at the entry bar itself -- a genuine
                    pullback cools RSI below that level temporarily)
      - pullback:   RSI14 was >= RECENT_STRENGTH_RSI_THRESHOLD
                    PULLBACK_LOOKBACK_BARS bars ago (a real recent push
                    happened) AND RSI14 now sits in
                    [PULLBACK_RSI_LOW, PULLBACK_RSI_HIGH] (has cooled,
                    without breaking down)
      - resumption: today's close > yesterday's close (price is already
                    turning back up on this exact bar)

    Deliberately does NOT require the baseline's own volume condition --
    a single-variable change from immediate-alignment entry to
    pullback-and-resume entry, not a combination of multiple new rules
    (per the mission's own "one hypothesis at a time" instruction)."""

    name = "pullback_continuation"
    version = "1.0"

    def generate_signal(self, indicator_series: pd.DataFrame, index: int, symbol: str) -> Signal | None:
        if index < PULLBACK_LOOKBACK_BARS + 1:
            return None  # not enough history for the lookback plus a "yesterday" bar

        row = indicator_series.iloc[index]
        prior_row = indicator_series.iloc[index - 1]
        lookback_row = indicator_series.iloc[index - PULLBACK_LOOKBACK_BARS]

        required = (
            row.get("sma_20"), row.get("sma_50"), row.get("macd"), row.get("macd_signal"),
            row.get("rsi_14"), row.get("atr_14"), row.get("close"), prior_row.get("close"),
            lookback_row.get("rsi_14"),
        )
        if any(pd.isna(v) for v in required):
            return None

        trend_confirmed = float(row["sma_20"]) > float(row["sma_50"])
        momentum_confirmed = float(row["macd"]) > float(row["macd_signal"])
        recent_strength = float(lookback_row["rsi_14"]) >= RECENT_STRENGTH_RSI_THRESHOLD
        pulled_back = PULLBACK_RSI_LOW <= float(row["rsi_14"]) <= PULLBACK_RSI_HIGH
        resuming = float(row["close"]) > float(prior_row["close"])

        if not (trend_confirmed and momentum_confirmed and recent_strength and pulled_back and resuming):
            return None

        reference_price = float(row["close"])
        atr = float(row["atr_14"])
        if atr <= 0:
            return None

        stop_distance = atr * STOP_ATR_MULTIPLIER
        stop_price = reference_price - stop_distance
        if stop_price <= 0:
            return None
        target_price = reference_price + stop_distance * TARGET_RISK_REWARD

        return Signal(
            symbol=symbol, generated_at=indicator_series.index[index], side=Side.LONG,
            reference_price=reference_price, stop_price=stop_price, target_price=target_price,
            risk_reward=TARGET_RISK_REWARD, strategy_name=self.name,
            reason_codes=[ReasonCode.TREND_CONFIRMED, ReasonCode.PULLBACK_CONFIRMED],
        )
