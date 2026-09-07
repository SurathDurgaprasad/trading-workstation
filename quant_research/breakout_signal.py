"""H_BREAKOUT_001 (strategy/hypothesis_registry.py): does a genuine
Donchian-style breakout (close exceeds the prior 20-bar high) show
better forward continuation when accompanied by CONTEXT -- a prior
volatility contraction ("quiet before the breakout") or volume
expansion ("real participation") -- than a raw, unfiltered breakout?
Family C (breakout quality) per the BUILD THE REAL TRADING BRAIN
mission's own explicit family list: "Test whether BREAKOUT + CONTEXT +
LIQUIDITY + VOLATILITY produces better results than raw breakout" --
Candidate A below IS that "raw breakout" baseline; B and C are exactly
the VOLATILITY and LIQUIDITY context enhancements the mission names.

Reuses atr_pct_of_price and volume_ratio -- the former from
quant_research/alpha_features.py (Phase 10, already causal, already
tested), the latter already present in market.indicators.
compute_indicator_series's own standard output -- rather than
recomputing either. This module's only genuinely NEW column is the
Donchian high itself (a plain rolling max, causal by the same
"row i uses only rows <= i" construction as every other indicator in
this project) and a rolling median of atr_pct_of_price (needed to judge
"is CURRENT volatility low relative to this symbol's OWN recent
history," a per-symbol adaptive baseline, not an arbitrary fixed
number).

LONG-only, matching every other strategy in this project. Exit
structure deliberately reuses TrendMomentumBaseline's own frozen
stop/target constants, the same isolation posture every other
hypothesis candidate in this project already takes -- this experiment
tests the ENTRY signal only. DONCHIAN_LOOKBACK_BARS=20 (a standard,
widely-used Donchian window, matching this project's own repeated use
of 20 as a standard lookback elsewhere -- zscore_close_20,
trailing_return_20, volume_sma_20) and VOLATILITY_MEDIAN_LOOKBACK=60
are both fixed a priori, never searched over a grid, never tuned after
seeing any backtest result.
"""

from dataclasses import dataclass, field

import pandas as pd

from backtesting.trade import Trade
from strategy.baseline import STOP_ATR_MULTIPLIER, TARGET_RISK_REWARD
from strategy.contracts import Strategy
from strategy.signal import ReasonCode, Side, Signal

DONCHIAN_LOOKBACK_BARS = 20
VOLATILITY_MEDIAN_LOOKBACK = 60

_REQUIRED_COLUMNS = ("donchian_high_20", "atr_14")


def add_breakout_columns(indicator_series: pd.DataFrame) -> pd.DataFrame:
    """Returns a COPY of indicator_series with three additional causal
    columns. `atr_pct_of_price` comes from quant_research.alpha_features.
    add_alpha_features (market_series=None -- relative_strength_20 is
    also added as a side effect and left unused here). `donchian_high_20`
    is the highest HIGH of the PRIOR 20 bars (shift(1) before rolling,
    so today's own high never counts toward today's own ceiling -- the
    standard, correct Donchian breakout definition; without the shift,
    "today's high is a new 20-day high" would be trivially true on
    almost every bar). `atr_pct_median_60` is a rolling median of
    atr_pct_of_price over the trailing 60 bars -- a per-symbol adaptive
    "is volatility currently low FOR THIS STOCK" baseline, not an
    arbitrary fixed threshold."""
    from quant_research.alpha_features import add_alpha_features

    out = add_alpha_features(indicator_series, market_series=None)
    out["donchian_high_20"] = out["high"].shift(1).rolling(window=DONCHIAN_LOOKBACK_BARS, min_periods=DONCHIAN_LOOKBACK_BARS).max()
    out["atr_pct_median_60"] = out["atr_pct_of_price"].rolling(window=VOLATILITY_MEDIAN_LOOKBACK, min_periods=VOLATILITY_MEDIAN_LOOKBACK).median()
    return out


def _is_breakout(row: pd.Series) -> bool:
    if pd.isna(row.get("donchian_high_20")):
        return False
    return bool(row["close"] > row["donchian_high_20"])


def _raw_breakout(row: pd.Series) -> bool:
    """Candidate A: the "raw breakout" baseline this hypothesis's own
    B/C candidates are measured against -- no context filter at all."""
    return _is_breakout(row)


def _breakout_after_volatility_contraction(row: pd.Series) -> bool:
    """Candidate B (VOLATILITY context): a genuine breakout, but only
    when the symbol's own current volatility (atr_pct_of_price) is
    BELOW its own trailing 60-bar median -- "quiet before the move,"
    the classic volatility-squeeze-precedes-breakout premise (e.g.
    Bollinger/TTM squeeze indicators)."""
    if pd.isna(row.get("atr_pct_median_60")) or pd.isna(row.get("atr_pct_of_price")):
        return False
    return bool(_is_breakout(row) and row["atr_pct_of_price"] < row["atr_pct_median_60"])


def _breakout_with_volume_expansion(row: pd.Series) -> bool:
    """Candidate C (LIQUIDITY context): a genuine breakout accompanied
    by volume at least 50% above its own 20-day average on the
    breakout bar itself -- "real participation behind the move," a
    DIFFERENT role for volume_ratio than H_ENTRY_002's own already-
    tested (and REJECTED) trend-continuation filter use."""
    if pd.isna(row.get("volume_ratio")):
        return False
    return bool(_is_breakout(row) and row["volume_ratio"] > 1.5)


CANDIDATES = {
    "A_raw_breakout": _raw_breakout,
    "B_breakout_after_volatility_contraction": _breakout_after_volatility_contraction,
    "C_breakout_with_volume_expansion": _breakout_with_volume_expansion,
}


class BreakoutSignalStrategy:
    """STANDALONE signal generator -- ignores SMA20/50 crossover, RSI
    level, and MACD entirely (unlike TrendMomentumBaseline). Tests
    whether a Donchian-style breakout (optionally with context) alone
    carries enough information to justify a long entry, isolated from
    every trend-continuation condition already falsified in Family A.
    Implements the Strategy protocol; deliberately NOT registered in
    strategy/registry.py -- a research candidate, not a deployed
    strategy, the same posture every other hypothesis candidate in this
    project already takes."""

    def __init__(self, candidate_name: str):
        self.candidate_name = candidate_name
        self._predicate = CANDIDATES[candidate_name]
        self.name = f"breakout_signal+{candidate_name}"
        self.version = "breakout-001-candidate"

    def generate_signal(self, indicator_series: pd.DataFrame, index: int, symbol: str) -> Signal | None:
        row = indicator_series.iloc[index]
        if row[list(_REQUIRED_COLUMNS)].isna().any():
            return None
        if not self._predicate(row):
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
            reason_codes=[ReasonCode.BREAKOUT_CONFIRMED],
        )


@dataclass
class UniverseBreakoutExperimentResult:
    """One pooled trade list per candidate (A/B/C) per period, mirroring
    every other universe-level experiment runner's own pooling shape in
    this project so downstream evaluation (strategy.promotion_gate.
    evaluate_promotion, backtesting.universe.per_trade_returns) needs no
    new glue code."""

    development_trades: dict[str, list[Trade]] = field(default_factory=lambda: {name: [] for name in CANDIDATES})
    validation_trades: dict[str, list[Trade]] = field(default_factory=lambda: {name: [] for name in CANDIDATES})
    out_of_sample_trades: dict[str, list[Trade]] = field(default_factory=lambda: {name: [] for name in CANDIDATES})
    failed_symbols: dict[str, str] = field(default_factory=dict)
    """symbol -> human-readable reason it could not be backtested at all
    (cache miss, unparseable series) -- same per-symbol isolation
    posture as every other universe-level experiment runner in this
    project, never silently dropped."""


def run_universe_breakout_experiment(
    symbols: list[str],
    *,
    period: str = "5y",
    interval: str = "1d",
    initial_capital: float = 100_000.0,
) -> UniverseBreakoutExperimentResult:
    """H_BREAKOUT_001: does a Donchian-style breakout, optionally with
    volatility-contraction or volume-expansion context, show positive
    expectancy? Threshold-free by design (fixed a priori thresholds, no
    per-symbol development-period fitting needed). A self-contained
    fetch/compute/split/run loop, same reason as every other new-
    hypothesis runner this session: add_breakout_columns() must run
    between compute_indicator_series() and the backtest, a hook
    backtesting.runner.run_full_backtest exposes no support for."""
    from backtesting.cache import CachedMarketDataProvider
    from backtesting.engine import run_backtest
    from backtesting.splits import split_periods
    from market.data_provider import MarketDataError, get_market_data_provider
    from market.indicators import compute_indicator_series

    provider = CachedMarketDataProvider(get_market_data_provider())
    result = UniverseBreakoutExperimentResult()

    for symbol in symbols:
        try:
            ohlcv = provider.fetch_ohlcv(symbol, period=period, interval=interval)
            indicator_series = add_breakout_columns(compute_indicator_series(ohlcv))
        except (MarketDataError, ValueError) as exc:
            result.failed_symbols[symbol] = str(exc)
            continue

        split = split_periods(indicator_series.index[0], indicator_series.index[-1])
        periods = {
            "development": (split.development_start, split.development_end, result.development_trades),
            "validation": (split.validation_start, split.validation_end, result.validation_trades),
            "out_of_sample": (split.out_of_sample_start, split.out_of_sample_end, result.out_of_sample_trades),
        }

        for candidate_name in CANDIDATES:
            strategy: Strategy = BreakoutSignalStrategy(candidate_name)
            for period_label, (start, end, pooled_trades) in periods.items():
                sliced = indicator_series.loc[(indicator_series.index >= start) & (indicator_series.index <= end)]
                run_result = run_backtest(
                    symbol=symbol, indicator_series=sliced, strategy=strategy,
                    initial_capital=initial_capital, period_label=period_label,
                )
                pooled_trades[candidate_name].extend(run_result.trades)

    return result
