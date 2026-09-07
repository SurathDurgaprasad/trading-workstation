"""H_MEANREV_001 (strategy/hypothesis_registry.py): short-term mean
reversion -- a symbol trading unusually far BELOW its own recent 20-day
average tends to partially revert toward it, a genuinely INDEPENDENT
market mechanism from Family A (trend continuation), which every
H_ENTRY_*/H_EXIT_* hypothesis tested so far has been some variant of.

Reuses quant_research/alpha_features.py's own zscore_close_20 (Phase 10,
already causal, already unit-tested) and strategy/regime_filters.py's
own sma_200 broad-trend column (Phase 9) rather than recomputing either
-- this module only adds NEW logic where none already exists: the
candidate predicates themselves and the standalone Strategy/universe
runner needed to actually test them.

LONG-only, matching every other strategy in this project. Exit
structure deliberately reuses TrendMomentumBaseline's own frozen
stop/target constants (STOP_ATR_MULTIPLIER, TARGET_RISK_REWARD) -- the
same isolation posture quant_research/volume_signal.py's
VolumeSignalStrategy already established, so this experiment tests the
ENTRY signal only, never confounding it with a new exit design.

Thresholds (-2.0, -1.5) are fixed a priori (the standard, widely-cited
"2 standard deviations" oversold threshold, and a less extreme variant)
-- never searched over a grid, never tuned after seeing any backtest
result.
"""

from dataclasses import dataclass, field

import pandas as pd

from backtesting.trade import Trade
from strategy.baseline import STOP_ATR_MULTIPLIER, TARGET_RISK_REWARD
from strategy.contracts import Strategy
from strategy.signal import ReasonCode, Side, Signal

_REQUIRED_COLUMNS = ("zscore_close_20", "atr_14")


def add_mean_reversion_columns(indicator_series: pd.DataFrame) -> pd.DataFrame:
    """Returns a COPY of indicator_series with zscore_close_20 (via
    quant_research.alpha_features.add_alpha_features, market_series=None
    -- relative_strength_20 is also added as a side effect but left NaN
    and unused here, cheaper than reimplementing just the zscore piece)
    and sma_200 (via strategy.regime_filters.add_regime_columns) added.
    Both are purely additive, causal-by-construction reuses of existing,
    already-tested modules -- no new feature math in this function."""
    from quant_research.alpha_features import add_alpha_features
    from strategy.regime_filters import add_regime_columns

    out = add_alpha_features(indicator_series, market_series=None)
    out = add_regime_columns(out)
    return out


def _oversold_2std(row: pd.Series) -> bool:
    """Candidate A: the standard, widely-cited "2 standard deviations
    below the mean" oversold threshold -- chosen for being a common,
    non-cherry-picked convention, not because it was searched for."""
    if pd.isna(row.get("zscore_close_20")):
        return False
    return bool(row["zscore_close_20"] < -2.0)


def _oversold_1_5std(row: pd.Series) -> bool:
    """Candidate B: a less extreme, more frequently-firing threshold --
    tests whether requiring a truly extreme deviation (Candidate A) is
    necessary, or whether a milder oversold reading is already enough."""
    if pd.isna(row.get("zscore_close_20")):
        return False
    return bool(row["zscore_close_20"] < -1.5)


def _oversold_within_uptrend(row: pd.Series) -> bool:
    """Candidate C: Candidate A's threshold, but only within a stock
    whose own longer-term trend (price above its 200-bar SMA) is still
    up -- "buy a sharp dip, not a structural decline," avoiding the
    classic "catching a falling knife" failure mode a pure
    oversold-anywhere rule risks. Reuses strategy.regime_filters's own
    sma_200 column and NaN-during-warmup handling exactly."""
    if pd.isna(row.get("zscore_close_20")) or pd.isna(row.get("sma_200")):
        return False
    return bool(row["zscore_close_20"] < -2.0 and row["close"] > row["sma_200"])


CANDIDATES = {
    "A_oversold_2std": _oversold_2std,
    "B_oversold_1_5std": _oversold_1_5std,
    "C_oversold_within_uptrend": _oversold_within_uptrend,
}


class MeanReversionSignalStrategy:
    """STANDALONE signal generator -- ignores SMA20/50 crossover, RSI
    level, and MACD entirely (unlike TrendMomentumBaseline). Tests
    whether zscore_close_20 alone (optionally combined with the broad
    sma_200 trend context for Candidate C) carries enough information to
    justify a long entry, isolated from every trend-continuation
    condition. Implements the Strategy protocol; deliberately NOT
    registered in strategy/registry.py -- a research candidate, not a
    deployed strategy, the same posture every other hypothesis
    candidate in this project already takes."""

    def __init__(self, candidate_name: str):
        self.candidate_name = candidate_name
        self._predicate = CANDIDATES[candidate_name]
        self.name = f"mean_reversion_signal+{candidate_name}"
        self.version = "meanrev-001-candidate"

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
            reason_codes=[ReasonCode.MEAN_REVERSION_OVERSOLD],
        )


@dataclass
class UniverseMeanReversionExperimentResult:
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


def run_universe_mean_reversion_experiment(
    symbols: list[str],
    *,
    period: str = "5y",
    interval: str = "1d",
    initial_capital: float = 100_000.0,
) -> UniverseMeanReversionExperimentResult:
    """H_MEANREV_001: does a LONG entry on a large negative zscore_close_20
    show positive expectancy? Threshold-free by design (fixed a priori
    thresholds, no per-symbol development-period fitting needed, unlike
    quant_research/volume_signal.py's own runner) -- a self-contained
    fetch/compute/split/run loop mirroring backtesting.runner.
    run_full_backtest's own internal structure (including its exact
    inclusive-both-ends period-boundary convention), needed because
    add_mean_reversion_columns() must run between compute_indicator_series()
    and the backtest, a hook run_full_backtest does not expose (the same
    reason strategy/momentum_acceleration.py's own runner is
    self-contained rather than calling run_full_backtest directly)."""
    from backtesting.cache import CachedMarketDataProvider
    from backtesting.engine import run_backtest
    from backtesting.splits import split_periods
    from market.data_provider import MarketDataError, get_market_data_provider
    from market.indicators import compute_indicator_series

    provider = CachedMarketDataProvider(get_market_data_provider())
    result = UniverseMeanReversionExperimentResult()

    for symbol in symbols:
        try:
            ohlcv = provider.fetch_ohlcv(symbol, period=period, interval=interval)
            indicator_series = add_mean_reversion_columns(compute_indicator_series(ohlcv))
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
            strategy: Strategy = MeanReversionSignalStrategy(candidate_name)
            for period_label, (start, end, pooled_trades) in periods.items():
                sliced = indicator_series.loc[(indicator_series.index >= start) & (indicator_series.index <= end)]
                run_result = run_backtest(
                    symbol=symbol, indicator_series=sliced, strategy=strategy,
                    initial_capital=initial_capital, period_label=period_label,
                )
                pooled_trades[candidate_name].extend(run_result.trades)

    return result
