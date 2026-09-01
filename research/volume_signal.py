"""Phase 11 — volume signal confirmation study. Tests the frozen Phase 10
`volume_ratio` feature (market.indicators.compute_volume_ratio_series,
UNCHANGED — reused directly from indicator_series, never recomputed here)
as a standalone, causal trading signal, and as a filter over the frozen
TrendMomentumBaseline (via strategy.regime_filters.FilteredStrategy, reused
unchanged from Phase 9). This is a confirmation study, not feature
engineering — no new volume indicator, no combinatorial search.

Direction and thresholds come from Phase 10's own evidence, not a fresh
search: Phase 10 found HIGHER volume_ratio associated with HIGHER forward
5-day returns (pooled OOS Spearman rho=+0.044, top-quintile mean +0.25% vs.
bottom-quintile +0.08%), so every candidate below is LONG-biased, never
short. Thresholds reuse Phase 10's own quintile methodology exactly: the
20th/80th percentile of volume_ratio, fit ONLY on each symbol's
development-period data and then FROZEN — applied unchanged to validation
and out-of-sample. No percentile grid was searched; no threshold was chosen
after seeing a profitability result.

Exit structure deliberately reuses TrendMomentumBaseline's own stop/target
constants (strategy.baseline.STOP_ATR_MULTIPLIER, TARGET_RISK_REWARD) — the
"fixed risk-based exit structure" the Phase 11 spec asks for, chosen
specifically so this experiment isolates the value of the ENTRY signal
rather than exit design. No maximum holding period is imposed: positions
exit only via stop/target/end-of-data, identical to every existing
strategy's execution model — a time-based exit would require new code in
backtesting/execution.py, which this phase avoids on principle ("do not
modify... unless absolutely required").
"""

import pandas as pd

from strategy.baseline import STOP_ATR_MULTIPLIER, TARGET_RISK_REWARD
from strategy.signal import ReasonCode, Side, Signal

_REQUIRED_COLUMNS = ("volume_ratio", "atr_14")


def dev_fit_volume_thresholds(dev_volume_ratio: pd.Series) -> tuple[float, float] | None:
    """(p20, p80), fit ONLY on development-period volume_ratio — frozen and
    reused unchanged for validation/OOS, the identical discipline Phase 10
    used for its own quintile buckets."""
    clean = dev_volume_ratio.dropna()
    if len(clean) < 50:
        return None
    p20, p80 = clean.quantile([0.2, 0.8])
    return float(p20), float(p80)


def _high_volume(volume_ratio: float, p20: float, p80: float) -> bool:
    """Candidate A: high-volume long. Direct reading of Phase 10's dominant
    finding — volume_ratio above the symbol's own development-period 80th
    percentile."""
    return volume_ratio > p80


def _low_volume(volume_ratio: float, p20: float, p80: float) -> bool:
    """Candidate B: low-volume long. A falsification arm: Phase 10's bottom
    quintile (Q1_bottom, mean +0.08%) was NOT clearly negative — the
    second-weakest of five, not the worst. Tests whether a low-volume entry
    also carries positive information, or whether the effect is specific to
    elevated volume as Candidate A assumes."""
    return volume_ratio < p20


def _extreme_volume(volume_ratio: float, p20: float, p80: float) -> bool:
    """Candidate C: two-sided extreme volume (either tail). Motivated by
    Phase 10's own bucket shape being non-monotonic (Q2, not Q1, was the
    single WORST bucket) — tests whether "unusual" volume in either
    direction is more informative than "normal" (middle) volume."""
    return volume_ratio > p80 or volume_ratio < p20


CANDIDATES = {
    "A_high_volume": _high_volume,
    "B_low_volume": _low_volume,
    "C_extreme_volume": _extreme_volume,
}


class VolumeSignalStrategy:
    """STANDALONE signal generator — ignores SMA/RSI/MACD entirely (unlike
    TrendMomentumBaseline). Tests whether volume_ratio alone carries enough
    information to justify a long entry, isolated from every other
    condition. Implements the Strategy protocol; deliberately NOT registered
    in strategy/registry.py — a research candidate, not a deployed strategy,
    the same posture Phase 9's FilteredStrategy took. One instance is scoped
    to exactly one symbol's frozen, development-fit thresholds."""

    def __init__(self, candidate_name: str, p20: float, p80: float):
        self.candidate_name = candidate_name
        self._predicate = CANDIDATES[candidate_name]
        self._p20 = p20
        self._p80 = p80
        self.name = f"volume_signal_standalone+{candidate_name}"
        self.version = "11.0-candidate"

    def generate_signal(self, indicator_series: pd.DataFrame, index: int, symbol: str) -> Signal | None:
        row = indicator_series.iloc[index]
        if row[list(_REQUIRED_COLUMNS)].isna().any():
            return None
        if not self._predicate(float(row["volume_ratio"]), self._p20, self._p80):
            return None

        reference_price = float(row["close"])
        atr = float(row["atr_14"])
        if atr <= 0:
            return None

        stop_distance = atr * STOP_ATR_MULTIPLIER
        stop_price = reference_price - stop_distance
        target_price = reference_price + stop_distance * TARGET_RISK_REWARD

        return Signal(
            symbol=symbol, generated_at=indicator_series.index[index], side=Side.LONG,
            reference_price=reference_price, stop_price=stop_price, target_price=target_price,
            risk_reward=TARGET_RISK_REWARD, strategy_name=self.name,
            reason_codes=[ReasonCode.VOLUME_CONFIRMED],
        )


def make_volume_predicate(candidate_name: str, p20: float, p80: float):
    """A row -> bool predicate for strategy.regime_filters.FilteredStrategy
    (Phase 9, reused unchanged), scoped to one symbol's frozen thresholds —
    used to answer "does volume_ratio improve TrendMomentumBaseline"
    (incremental value), as opposed to VolumeSignalStrategy's standalone
    question above."""
    predicate_fn = CANDIDATES[candidate_name]

    def _predicate(row: pd.Series) -> bool:
        if pd.isna(row.get("volume_ratio")):
            return False
        return predicate_fn(float(row["volume_ratio"]), p20, p80)

    return _predicate
