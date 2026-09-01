import pandas as pd

from strategy.signal import ReasonCode, Side, Signal

# Baseline assumptions, fixed by design for Phase 3 — NOT tuned, NOT the
# result of a parameter search. See the Phase 3 implementation report for
# the reasoning. Change these only as an explicit, separate decision.
STOP_ATR_MULTIPLIER = 1.5
TARGET_RISK_REWARD = 2.0

_REQUIRED_COLUMNS = ("sma_20", "sma_50", "rsi_14", "macd", "macd_signal", "atr_14", "volume_trend")


class TrendMomentumBaseline:
    """Long-only trend+momentum+volume confirmation, ATR-based risk.

    Entry condition (ALL must hold on the generating bar):
      - trend:    SMA20 > SMA50
      - momentum: RSI14 > 50 AND MACD > MACD signal
      - volume:   volume_trend == "increasing"   ("supportive", defined as
                  rising volume per market/indicators.py's own classification
                  — "neutral" and "decreasing" are NOT supportive)

    No short side yet (see strategy/signal.py::Side — SHORT exists in the
    enum for a future strategy, this one never emits it).
    """

    name = "trend_momentum_baseline"
    version = "1.0"  # Phase 6: recorded on every signal/trade — bump explicitly if the rules ever change

    def generate_signal(
        self, indicator_series: pd.DataFrame, index: int, symbol: str
    ) -> Signal | None:
        row = indicator_series.iloc[index]

        if row[list(_REQUIRED_COLUMNS)].isna().any():
            return None  # insufficient history / missing ATR or volume data

        trend_confirmed = row["sma_20"] > row["sma_50"]
        momentum_confirmed = row["rsi_14"] > 50 and row["macd"] > row["macd_signal"]
        volume_confirmed = row["volume_trend"] == "increasing"

        if not (trend_confirmed and momentum_confirmed and volume_confirmed):
            return None

        reference_price = float(row["close"])
        atr = float(row["atr_14"])
        if atr <= 0:
            return None  # degenerate ATR, cannot size a stop

        stop_distance = atr * STOP_ATR_MULTIPLIER
        stop_price = reference_price - stop_distance
        target_price = reference_price + stop_distance * TARGET_RISK_REWARD

        return Signal(
            symbol=symbol,
            generated_at=indicator_series.index[index],
            side=Side.LONG,
            reference_price=reference_price,
            stop_price=stop_price,
            target_price=target_price,
            risk_reward=TARGET_RISK_REWARD,
            strategy_name=self.name,
            reason_codes=[
                ReasonCode.TREND_CONFIRMED,
                ReasonCode.MOMENTUM_CONFIRMED,
                ReasonCode.VOLUME_CONFIRMED,
            ],
        )
