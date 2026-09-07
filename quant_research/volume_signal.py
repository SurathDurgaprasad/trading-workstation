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

from dataclasses import dataclass, field

import pandas as pd

from backtesting.trade import Trade
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


@dataclass
class UniverseVolumeFilterExperimentResult:
    """AUTONOMOUS RESEARCH MISSION (BUILD THE REAL TRADING BRAIN) --
    H_ENTRY_002 (strategy/hypothesis_registry.py) has been marked OPEN
    since this module was first written: Phase 11 built and unit-tested
    the 3 candidates above, but nothing ever ran them through the full
    universe-level dev/val/oos protocol every other hypothesis in this
    project's history was held to. This is that missing runner. One
    pooled trade list per candidate (A/B/C) per period, mirroring
    backtesting.universe.run_universe_backtest_by_period's own pooling
    shape exactly, so downstream evaluation (strategy.promotion_gate.
    evaluate_promotion, backtesting.universe.per_trade_returns) needs no
    new glue code."""

    development_trades: dict[str, list[Trade]] = field(default_factory=lambda: {name: [] for name in CANDIDATES})
    validation_trades: dict[str, list[Trade]] = field(default_factory=lambda: {name: [] for name in CANDIDATES})
    out_of_sample_trades: dict[str, list[Trade]] = field(default_factory=lambda: {name: [] for name in CANDIDATES})
    failed_symbols: dict[str, str] = field(default_factory=dict)
    """symbol, or "symbol:candidate_name" for a candidate-specific
    failure -> human-readable reason it could not be backtested at all
    (cache miss, unparseable series) -- same per-symbol isolation
    posture as backtesting.universe.UniverseBacktestResult.failed_symbols,
    never silently dropped."""
    insufficient_threshold_symbols: dict[str, int] = field(default_factory=dict)
    """symbol -> its own development-period non-NaN volume_ratio row
    count, for any symbol where dev_fit_volume_thresholds returned None
    (fewer than its own 50-row floor). This symbol contributes to NO
    candidate's pooled trades -- never silently treated as 0 trades, an
    honest exclusion distinct from a genuine backtest failure above."""


def run_universe_volume_filter_experiment(
    symbols: list[str],
    *,
    period: str = "5y",
    interval: str = "1d",
    initial_capital: float = 100_000.0,
) -> UniverseVolumeFilterExperimentResult:
    """H_ENTRY_002: does volume_ratio, as a FILTER layered over the frozen
    TrendMomentumBaseline, improve pooled expectancy over the unfiltered
    baseline? Honest scope note: TrendMomentumBaseline already requires
    its OWN binary volume_trend=="increasing" condition (strategy/
    baseline.py) -- this experiment tests whether a STRICTER, continuous,
    development-period-quantile-based volume bar adds further value
    beyond that existing loose gate, not "volume vs. no volume at all".

    Per symbol: fits p20/p80 ONLY on that symbol's own development-period
    volume_ratio (dev_fit_volume_thresholds, frozen before validation/
    out-of-sample are ever touched -- the same anti-data-snooping
    discipline every other hypothesis in this project's history has
    followed; the development slice uses backtesting.runner's own
    inclusive-both-ends boundary convention exactly, so the rows used to
    fit thresholds are identical to the rows actually backtested as
    "development"), then runs each of the 3 CANDIDATES as a
    FilteredStrategy wrapping a fresh TrendMomentumBaseline instance
    through backtesting.runner.run_full_backtest UNCHANGED. Unlike
    backtesting/exit_experiments.py's fully isolated bar-processing loop,
    this experiment touches no exit mechanics at all (same frozen
    stop/target as the baseline), so it needs no new engine code -- it
    is a pure consumer of already-tested, already-trusted infrastructure.
    """
    from backtesting.cache import CachedMarketDataProvider
    from backtesting.runner import run_full_backtest
    from backtesting.splits import split_periods
    from market.data_provider import MarketDataError, get_market_data_provider
    from market.indicators import compute_indicator_series
    from strategy.baseline import TrendMomentumBaseline
    from strategy.regime_filters import FilteredStrategy

    provider = CachedMarketDataProvider(get_market_data_provider())
    result = UniverseVolumeFilterExperimentResult()

    for symbol in symbols:
        try:
            ohlcv = provider.fetch_ohlcv(symbol, period=period, interval=interval)
            indicator_series = compute_indicator_series(ohlcv)
        except (MarketDataError, ValueError) as exc:
            result.failed_symbols[symbol] = str(exc)
            continue

        split = split_periods(indicator_series.index[0], indicator_series.index[-1])
        dev_slice = indicator_series.loc[
            (indicator_series.index >= split.development_start) & (indicator_series.index <= split.development_end)
        ]
        thresholds = dev_fit_volume_thresholds(dev_slice["volume_ratio"])
        if thresholds is None:
            result.insufficient_threshold_symbols[symbol] = int(dev_slice["volume_ratio"].dropna().shape[0])
            continue
        p20, p80 = thresholds

        for candidate_name in CANDIDATES:
            strategy = FilteredStrategy(
                inner=TrendMomentumBaseline(), filter_name=f"volume_{candidate_name}",
                predicate=make_volume_predicate(candidate_name, p20, p80),
            )
            try:
                run_result = run_full_backtest(
                    symbol=symbol, strategy=strategy, period=period, interval=interval,
                    initial_capital=initial_capital, use_cache=True,
                )
            except (MarketDataError, ValueError) as exc:
                result.failed_symbols[f"{symbol}:{candidate_name}"] = str(exc)
                continue
            result.development_trades[candidate_name].extend(run_result.development.trades)
            result.validation_trades[candidate_name].extend(run_result.validation.trades)
            result.out_of_sample_trades[candidate_name].extend(run_result.out_of_sample.trades)

    return result
