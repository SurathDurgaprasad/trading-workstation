"""Strategy science -- H_ENTRY_004 (strategy/hypothesis_registry.py):
momentum ACCELERATION, not merely momentum LEVEL. TrendMomentumBaseline's
own RSI14>50 and MACD>signal conditions are absolute-LEVEL checks -- they
do not distinguish momentum that is still building from momentum that has
already peaked and is now fading from a high level.

Deliberately NOT registered in strategy/registry.py -- same posture as
strategy/regime_filters.py and quant_research/volume_signal.py: research
candidates for one validation experiment, not a second deployed strategy.
Reachable only by importing this module directly.

Each filter answers exactly one question: "should this otherwise-valid
signal from the unchanged inner strategy be allowed?" -- it can only
SUPPRESS a signal, the same FilteredStrategy contract every other
regime/volume/acceleration candidate in this project already follows.

Causality: rsi_delta_3/macd_histogram_delta_3 are pandas .diff(3), which
at row i reads only rows i and i-3 -- both already <= i, so no new
look-ahead risk beyond what rsi_14/macd_histogram themselves already
guarantee (market/indicators.py's own causal-by-construction contract,
"a value at row i is derived only from rows <= i"). DELTA_LOOKBACK_BARS=3
is chosen a priori (a short, standard lookback for a short-horizon "is
this still accelerating right now" question) -- not searched over a
grid, not tuned after seeing any backtest result.

Threshold-free by design (unlike quant_research/volume_signal.py's
per-symbol dev-fit percentiles): each predicate is a fixed ">0" check
on a signed delta, so no per-symbol development-period fitting step is
needed here -- run_universe_momentum_acceleration_experiment() below is
correspondingly simpler than volume_signal.py's own universe runner.
"""

from dataclasses import dataclass, field

import pandas as pd

from backtesting.trade import Trade
from strategy.contracts import Strategy
from strategy.regime_filters import FilteredStrategy

DELTA_LOOKBACK_BARS = 3


def add_momentum_acceleration_columns(indicator_series: pd.DataFrame) -> pd.DataFrame:
    """Returns a COPY of indicator_series with two additional causal
    columns. Purely additive -- does not modify market/indicators.py or
    its output in any way; TrendMomentumBaseline reads only its own named
    columns and ignores extras, the same posture
    strategy.regime_filters.add_regime_columns already established."""
    out = indicator_series.copy()
    out["rsi_delta_3"] = out["rsi_14"].diff(DELTA_LOOKBACK_BARS)
    out["macd_histogram_delta_3"] = out["macd_histogram"].diff(DELTA_LOOKBACK_BARS)
    return out


def _rsi_accelerating(row: pd.Series) -> bool:
    """Candidate A: RSI14 itself is higher than it was 3 bars ago --
    momentum is still building, not merely above the baseline's own
    static RSI>50 threshold (which says nothing about direction of
    change)."""
    if pd.isna(row.get("rsi_delta_3")):
        return False  # insufficient history -- fail closed, same posture as every other predicate in this project
    return bool(row["rsi_delta_3"] > 0)


def _macd_histogram_widening(row: pd.Series) -> bool:
    """Candidate B: the MACD-signal gap (histogram) is wider than it was
    3 bars ago -- the baseline's own MACD>signal condition only checks
    the SIGN of this gap, never whether it is growing or shrinking."""
    if pd.isna(row.get("macd_histogram_delta_3")):
        return False
    return bool(row["macd_histogram_delta_3"] > 0)


def _both_accelerating(row: pd.Series) -> bool:
    """Candidate C: both RSI and MACD histogram must be accelerating
    simultaneously -- tests whether requiring agreement between two
    independent momentum measures narrows to a higher-quality subset,
    the same "require both" logic as regime_filters.py's own Candidate C."""
    return _rsi_accelerating(row) and _macd_histogram_widening(row)


CANDIDATES = {
    "A_rsi_accelerating": _rsi_accelerating,
    "B_macd_histogram_widening": _macd_histogram_widening,
    "C_both_accelerating": _both_accelerating,
}


@dataclass
class UniverseMomentumAccelerationExperimentResult:
    """One pooled trade list per candidate (A/B/C) per period, mirroring
    quant_research.volume_signal.UniverseVolumeFilterExperimentResult's
    own pooling shape exactly, so downstream evaluation
    (strategy.promotion_gate.evaluate_promotion,
    backtesting.universe.per_trade_returns) needs no new glue code."""

    development_trades: dict[str, list[Trade]] = field(default_factory=lambda: {name: [] for name in CANDIDATES})
    validation_trades: dict[str, list[Trade]] = field(default_factory=lambda: {name: [] for name in CANDIDATES})
    out_of_sample_trades: dict[str, list[Trade]] = field(default_factory=lambda: {name: [] for name in CANDIDATES})
    failed_symbols: dict[str, str] = field(default_factory=dict)
    """symbol -> human-readable reason it could not be backtested at all
    (cache miss, unparseable series) -- same per-symbol isolation posture
    as every other universe-level experiment runner in this project,
    never silently dropped."""


def run_universe_momentum_acceleration_experiment(
    symbols: list[str],
    *,
    period: str = "5y",
    interval: str = "1d",
    initial_capital: float = 100_000.0,
) -> UniverseMomentumAccelerationExperimentResult:
    """H_ENTRY_004: does gating TrendMomentumBaseline's own signal on
    momentum ACCELERATION (rather than merely momentum LEVEL) improve
    pooled expectancy? A self-contained fetch/compute/split/run loop
    (mirroring backtesting.runner.run_full_backtest's own internal
    structure, including its exact inclusive-both-ends period-boundary
    convention) rather than a direct call to run_full_backtest itself:
    add_momentum_acceleration_columns() must run between
    compute_indicator_series() and the backtest, and run_full_backtest
    exposes no hook for that -- duplicating this modest orchestration
    here was judged lower-risk than adding a transform hook to the
    shared runner every other hypothesis in this project's history also
    depends on ("do not modify... unless absolutely required")."""
    from backtesting.cache import CachedMarketDataProvider
    from backtesting.engine import run_backtest
    from backtesting.splits import split_periods
    from market.data_provider import MarketDataError, get_market_data_provider
    from market.indicators import compute_indicator_series
    from strategy.baseline import TrendMomentumBaseline

    provider = CachedMarketDataProvider(get_market_data_provider())
    result = UniverseMomentumAccelerationExperimentResult()

    for symbol in symbols:
        try:
            ohlcv = provider.fetch_ohlcv(symbol, period=period, interval=interval)
            indicator_series = add_momentum_acceleration_columns(compute_indicator_series(ohlcv))
        except (MarketDataError, ValueError) as exc:
            result.failed_symbols[symbol] = str(exc)
            continue

        split = split_periods(indicator_series.index[0], indicator_series.index[-1])
        periods = {
            "development": (split.development_start, split.development_end, result.development_trades),
            "validation": (split.validation_start, split.validation_end, result.validation_trades),
            "out_of_sample": (split.out_of_sample_start, split.out_of_sample_end, result.out_of_sample_trades),
        }

        for candidate_name, predicate in CANDIDATES.items():
            strategy: Strategy = FilteredStrategy(
                inner=TrendMomentumBaseline(), filter_name=candidate_name, predicate=predicate,
            )
            for period_label, (start, end, pooled_trades) in periods.items():
                sliced = indicator_series.loc[(indicator_series.index >= start) & (indicator_series.index <= end)]
                run_result = run_backtest(
                    symbol=symbol, indicator_series=sliced, strategy=strategy,
                    initial_capital=initial_capital, period_label=period_label,
                )
                pooled_trades[candidate_name].extend(run_result.trades)

    return result
