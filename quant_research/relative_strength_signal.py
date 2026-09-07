"""H_RELSTRENGTH_001 (strategy/hypothesis_registry.py): does a stock's
own relative strength versus its market (recent return minus the
benchmark's own recent return) predict its forward continuation?

Honest scope note, stated up front rather than left implicit: this
tests SINGLE-SYMBOL relative strength as a standalone entry signal, NOT
the mission's own "Potential structure" for Family D (rank the whole
universe, select the strongest percentile, cross-sectional selection).
A true cross-sectional ranking/selection backtest needs a portfolio-
level engine that rebalances across the whole universe on a shared
calendar -- a genuinely different, larger capability this project's
existing backtesting/engine.py (single-symbol, bar-by-bar) does not
have, and building one was judged out of proportion to test ONE
hypothesis first ("do not add a giant feature blindly" -- the mission's
own explicit instruction). This module answers a real, narrower,
still-independent question first; if it shows promise, the
cross-sectional engine becomes a justified follow-up, not a
speculative one.

Reuses quant_research/alpha_features.py's own relative_strength_20
(Phase 10, already causal, already unit-tested: trailing_return_20 of
the symbol minus the trailing_return_20 of its own benchmark index,
aligned via a causal-safe forward-fill) rather than recomputing it.
Benchmark choice matches alpha_features.py's own documented convention:
^NSEI for ".NS"/".BO" symbols, ^GSPC otherwise.

LONG-only, matching every other strategy in this project. Exit
structure deliberately reuses TrendMomentumBaseline's own frozen
stop/target constants, the same isolation posture every other
hypothesis candidate in this project already takes -- this experiment
tests the ENTRY signal only.

Thresholds (0.0, 0.05, 0.10) are fixed a priori -- a monotonic dose-
response ladder (any outperformance / meaningful / strong), never
searched over a grid, never tuned after seeing any backtest result.
"""

from dataclasses import dataclass, field

import pandas as pd

from backtesting.trade import Trade
from strategy.baseline import STOP_ATR_MULTIPLIER, TARGET_RISK_REWARD
from strategy.contracts import Strategy
from strategy.signal import ReasonCode, Side, Signal

_REQUIRED_COLUMNS = ("relative_strength_20", "atr_14")


def benchmark_symbol_for(symbol: str) -> str:
    """Matches quant_research/alpha_features.py's own documented
    convention exactly (its module docstring: "^GSPC for US symbols,
    ^NSEI for Indian symbols")."""
    normalized = symbol.strip().upper()
    if normalized.endswith(".NS") or normalized.endswith(".BO"):
        return "^NSEI"
    return "^GSPC"


def add_relative_strength_column(indicator_series: pd.DataFrame, benchmark_series: pd.DataFrame | None) -> pd.DataFrame:
    """Returns a COPY of indicator_series with relative_strength_20 added,
    via quant_research.alpha_features.add_alpha_features (market_series=
    benchmark_series) -- the other four alpha_features columns are added
    as a side effect and left unused here, cheaper than reimplementing
    just this one."""
    from quant_research.alpha_features import add_alpha_features

    return add_alpha_features(indicator_series, market_series=benchmark_series)


def _any_outperformance(row: pd.Series) -> bool:
    """Candidate A: any positive relative strength at all -- the loosest,
    most frequently-firing bar."""
    if pd.isna(row.get("relative_strength_20")):
        return False
    return bool(row["relative_strength_20"] > 0.0)


def _meaningful_outperformance(row: pd.Series) -> bool:
    """Candidate B: at least 5 percentage points of trailing 20-bar
    outperformance versus the benchmark -- a stricter, less frequently-
    firing bar than Candidate A."""
    if pd.isna(row.get("relative_strength_20")):
        return False
    return bool(row["relative_strength_20"] > 0.05)


def _strong_outperformance(row: pd.Series) -> bool:
    """Candidate C: at least 10 percentage points of trailing 20-bar
    outperformance -- tests whether stronger relative strength is MORE
    predictive (a monotonic dose-response question), the strictest of
    the three."""
    if pd.isna(row.get("relative_strength_20")):
        return False
    return bool(row["relative_strength_20"] > 0.10)


CANDIDATES = {
    "A_any_outperformance": _any_outperformance,
    "B_meaningful_outperformance": _meaningful_outperformance,
    "C_strong_outperformance": _strong_outperformance,
}


class RelativeStrengthSignalStrategy:
    """STANDALONE signal generator -- ignores SMA20/50 crossover, RSI
    level, MACD, and volume entirely (unlike TrendMomentumBaseline).
    Tests whether relative_strength_20 alone carries enough information
    to justify a long entry, isolated from every trend-continuation
    condition already falsified in Family A. Implements the Strategy
    protocol; deliberately NOT registered in strategy/registry.py -- a
    research candidate, not a deployed strategy, the same posture every
    other hypothesis candidate in this project already takes."""

    def __init__(self, candidate_name: str):
        self.candidate_name = candidate_name
        self._predicate = CANDIDATES[candidate_name]
        self.name = f"relative_strength_signal+{candidate_name}"
        self.version = "relstrength-001-candidate"

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
            reason_codes=[ReasonCode.RELATIVE_STRENGTH_CONFIRMED],
        )


@dataclass
class UniverseRelativeStrengthExperimentResult:
    """One pooled trade list per candidate (A/B/C) per period, mirroring
    every other universe-level experiment runner's own pooling shape in
    this project so downstream evaluation (strategy.promotion_gate.
    evaluate_promotion, backtesting.universe.per_trade_returns) needs no
    new glue code."""

    development_trades: dict[str, list[Trade]] = field(default_factory=lambda: {name: [] for name in CANDIDATES})
    validation_trades: dict[str, list[Trade]] = field(default_factory=lambda: {name: [] for name in CANDIDATES})
    out_of_sample_trades: dict[str, list[Trade]] = field(default_factory=lambda: {name: [] for name in CANDIDATES})
    failed_symbols: dict[str, str] = field(default_factory=dict)
    """symbol -> human-readable reason it (or its own benchmark) could
    not be fetched/backtested at all -- same per-symbol isolation
    posture as every other universe-level experiment runner in this
    project, never silently dropped."""


def run_universe_relative_strength_experiment(
    symbols: list[str],
    *,
    period: str = "5y",
    interval: str = "1d",
    initial_capital: float = 100_000.0,
) -> UniverseRelativeStrengthExperimentResult:
    """H_RELSTRENGTH_001: does a LONG entry on positive relative_strength_20
    show positive expectancy? Threshold-free by design (fixed a priori
    thresholds, no per-symbol development-period fitting needed). A
    self-contained fetch/compute/split/run loop (mirroring
    backtesting.runner.run_full_backtest's own internal structure,
    including its exact inclusive-both-ends period-boundary convention)
    rather than a direct call to that shared function, since it also
    needs each symbol's own benchmark series fetched and passed through
    add_relative_strength_column() -- a second data source
    run_full_backtest has no concept of."""
    from backtesting.cache import CachedMarketDataProvider
    from backtesting.engine import run_backtest
    from backtesting.splits import split_periods
    from market.data_provider import MarketDataError, get_market_data_provider
    from market.indicators import compute_indicator_series

    provider = CachedMarketDataProvider(get_market_data_provider())
    result = UniverseRelativeStrengthExperimentResult()

    for symbol in symbols:
        try:
            ohlcv = provider.fetch_ohlcv(symbol, period=period, interval=interval)
            indicator_series = compute_indicator_series(ohlcv)
            benchmark_ohlcv = provider.fetch_ohlcv(benchmark_symbol_for(symbol), period=period, interval=interval)
            benchmark_series = compute_indicator_series(benchmark_ohlcv)
            indicator_series = add_relative_strength_column(indicator_series, benchmark_series)
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
            strategy: Strategy = RelativeStrengthSignalStrategy(candidate_name)
            for period_label, (start, end, pooled_trades) in periods.items():
                sliced = indicator_series.loc[(indicator_series.index >= start) & (indicator_series.index <= end)]
                run_result = run_backtest(
                    symbol=symbol, indicator_series=sliced, strategy=strategy,
                    initial_capital=initial_capital, period_label=period_label,
                )
                pooled_trades[candidate_name].extend(run_result.trades)

    return result
