"""Phase 9 — regime-filter hypothesis candidates layered over the frozen
Phase 8 control strategy (strategy.baseline.TrendMomentumBaseline,
UNCHANGED — never imported here in a way that could mutate it).

Deliberately NOT registered in strategy/registry.py: these are research
candidates for a single validation experiment, not a second deployed
strategy — the registry's own docstring says "exactly one entry,
deliberately," and this phase's own rule is "do not deploy any changed
combination." Reachable only by importing this module directly, the same
way the Phase 9 experiment scripts do.

Each filter answers exactly one question: "should this otherwise-valid
signal from the unchanged inner strategy be allowed?" It can only SUPPRESS
a signal — it never invents one, never touches its price/stop/target/side,
and never bypasses RiskEngine (the inner Strategy runs first, unmodified;
its Signal is passed through byte-for-byte or discarded, nothing in
between).

Causality: both regime columns added below (sma_200, atr_median_100) are
pure rolling/window functions of price/ATR history up to and including the
row's own bar — the identical causal-by-construction pattern already
audited for every other indicator column in market/indicators.py (see
tests/test_backtest_lookahead.py and test_backtest_lookahead_real_data.py).
No column here reads a future row, and neither predicate below reads
anything but the row it's given.
"""

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from market.indicators import compute_sma
from strategy.contracts import Strategy
from strategy.signal import Signal

# Pre-committed BEFORE any candidate result was inspected (spec's explicit
# anti-overfitting/anti-data-snooping rule) -- see the Phase 9 report's
# "candidate rationale" section for why each constant was chosen, not tuned.
BROAD_TREND_SMA_PERIOD = 200  # a standard, widely-used "primary trend" window
VOL_REGIME_LOOKBACK = 100  # ~5 months of trailing daily bars, an adaptive per-symbol vol reference


def add_regime_columns(indicator_series: pd.DataFrame) -> pd.DataFrame:
    """Returns a COPY of indicator_series with two additional causal
    columns. Does not modify market/indicators.py or its output in any way
    — this is Phase-9-only and purely additive. Safe to feed to the
    UNCHANGED control strategy too: TrendMomentumBaseline reads only its
    own named columns and ignores extras."""
    out = indicator_series.copy()
    out["sma_200"] = compute_sma(out["close"], BROAD_TREND_SMA_PERIOD)
    out["atr_median_100"] = out["atr_14"].rolling(window=VOL_REGIME_LOOKBACK, min_periods=VOL_REGIME_LOOKBACK).median()
    return out


def _trend_filter_ok(row: pd.Series) -> bool:
    """Candidate A: broad trend confirmation — close above its own 200-bar
    SMA. Rationale: Phase 8 found strong-uptrend quarters profitable and
    sideways/down quarters not; SMA20/50 alone is a short-horizon crossover
    that can flip inside a broader non-trending regime. Price-vs-SMA200 is
    one of the most standard, non-cherry-picked "primary trend" checks in
    technical analysis — chosen for that reason, not because it was
    searched for and happened to help."""
    if pd.isna(row.get("sma_200")):
        return False  # insufficient history -- fail closed, same posture as the baseline's own NaN handling
    return bool(row["close"] > row["sma_200"])


def _vol_filter_ok(row: pd.Series) -> bool:
    """Candidate B: volatility-state confirmation — current ATR14 at or
    below its own trailing 100-bar median. Rationale: Phase 8 found
    low-volatility quarters profitable (+0.34R) and high-volatility
    quarters not (-0.28R); this is a causal, adaptive, per-symbol proxy for
    "is this an elevated-volatility regime right now," built only from the
    ATR column the strategy already computes — no new price data source, no
    retrospective quarter labels."""
    if pd.isna(row.get("atr_median_100")):
        return False
    return bool(row["atr_14"] <= row["atr_median_100"])


def _combo_filter_ok(row: pd.Series) -> bool:
    """Candidate C: both A and B must hold. Rationale: Phase 8's regime
    cross-tab suggested trend and volatility are each independently
    informative; this directly tests whether requiring both narrows the
    trade set to a higher-quality subset — at the explicit, expected cost
    of materially fewer trades. This is candidate concept #6 from the
    Phase 9 spec's own list ("combination of trend + volatility")."""
    return _trend_filter_ok(row) and _vol_filter_ok(row)


CANDIDATES: dict[str, Callable[[pd.Series], bool]] = {
    "A_broad_trend_sma200": _trend_filter_ok,
    "B_low_volatility_regime": _vol_filter_ok,
    "C_trend_and_low_vol": _combo_filter_ok,
}


@dataclass
class FilteredStrategy:
    """Composes an UNCHANGED inner Strategy with a causal regime predicate.
    Implements the Strategy protocol (generate_signal/name/version) so it
    drops into run_backtest / PaperTradingEngine / replay_historical exactly
    like TrendMomentumBaseline does, with zero changes to any of them."""

    inner: Strategy
    filter_name: str
    predicate: Callable[[pd.Series], bool]
    version: str = "9.0-candidate"

    @property
    def name(self) -> str:
        return f"{self.inner.name}+{self.filter_name}"

    def generate_signal(self, indicator_series: pd.DataFrame, index: int, symbol: str) -> Signal | None:
        signal = self.inner.generate_signal(indicator_series, index, symbol)
        if signal is None:
            return None
        row = indicator_series.iloc[index]
        if not self.predicate(row):
            return None
        return signal
