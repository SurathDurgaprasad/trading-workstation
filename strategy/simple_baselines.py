"""Strategy science, Phase 3 (simple baselines) -- the mission's own
question: "does the complex filter [TrendMomentumBaseline's trend AND
momentum AND volume confirmation] outperform simpler explanations?"

Both classes below reuse TrendMomentumBaseline's own ATR-based stop/
target risk mechanics verbatim (STOP_ATR_MULTIPLIER, TARGET_RISK_REWARD
from strategy/baseline.py) so ENTRY-CONDITION COMPLEXITY is the only
variable -- the same isolation principle backtesting.random_baseline.
RandomEntryStrategy already established for entry TIMING. Deliberately
NOT registered in strategy/registry.py, whose own module docstring
states an intentional constraint ("Exactly one entry, deliberately...
not a strategy factory") -- these are comparison-only baselines,
constructed directly by callers that need them, mirroring
RandomEntryStrategy's own identical precedent (also never registered).
"""

import pandas as pd

from strategy.baseline import STOP_ATR_MULTIPLIER, TARGET_RISK_REWARD
from strategy.signal import ReasonCode, Side, Signal


def _build_signal(indicator_series: pd.DataFrame, index: int, symbol: str, strategy_name: str) -> Signal | None:
    row = indicator_series.iloc[index]
    atr = row.get("atr_14")
    if pd.isna(atr) or float(atr) <= 0:
        return None
    reference_price = float(row["close"])
    stop_distance = float(atr) * STOP_ATR_MULTIPLIER
    stop_price = reference_price - stop_distance
    if stop_price <= 0:
        return None
    target_price = reference_price + stop_distance * TARGET_RISK_REWARD
    return Signal(
        symbol=symbol, generated_at=indicator_series.index[index], side=Side.LONG,
        reference_price=reference_price, stop_price=stop_price, target_price=target_price,
        risk_reward=TARGET_RISK_REWARD, strategy_name=strategy_name, reason_codes=[ReasonCode.MOMENTUM_CONFIRMED],
    )


class SimpleMomentumBaseline:
    """Entry condition: close > SMA20. Nothing else -- no trend
    confirmation, no volume, no RSI/MACD. Deliberately simple, per the
    mission's own "avoid overengineering" instruction. Fires on every
    eligible bar where the condition holds (not rate-limited to match
    any other strategy's trade count) -- unlike RandomEntryStrategy,
    this comparison is about whether a SIMPLER RULE is competitive, not
    about isolating entry timing alone, so a different (looser, more
    frequent) trade cadence than TrendMomentumBaseline is expected and
    is itself part of what's being measured."""

    name = "simple_momentum_baseline"
    version = "1.0"

    def generate_signal(self, indicator_series: pd.DataFrame, index: int, symbol: str) -> Signal | None:
        row = indicator_series.iloc[index]
        close, sma_20 = row.get("close"), row.get("sma_20")
        if pd.isna(close) or pd.isna(sma_20) or not (float(close) > float(sma_20)):
            return None
        return _build_signal(indicator_series, index, symbol, self.name)


class SimpleTrendBaseline:
    """Entry condition: SMA20 > SMA50. Nothing else -- the SAME
    directional comparison TrendMomentumBaseline's own trend leg uses,
    isolated from its momentum/volume conditions entirely."""

    name = "simple_trend_baseline"
    version = "1.0"

    def generate_signal(self, indicator_series: pd.DataFrame, index: int, symbol: str) -> Signal | None:
        row = indicator_series.iloc[index]
        sma_20, sma_50 = row.get("sma_20"), row.get("sma_50")
        if pd.isna(sma_20) or pd.isna(sma_50) or not (float(sma_20) > float(sma_50)):
            return None
        return _build_signal(indicator_series, index, symbol, self.name)
