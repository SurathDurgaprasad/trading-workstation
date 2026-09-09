"""H_XSECT_001 (strategy/hypothesis_registry.py) -- the real, cost-aware,
risk-sized backtest docs/research/CROSS_SECTIONAL_RELATIVE_STRENGTH_
REPORT.md's own §10 recommended as next step #1: "build the minimal
Strategy-protocol wrapper ... and run it through the existing cost-
aware/risk-sized backtesting machinery -- a real backtest, not just the
raw price-behavior measurement."

Frozen, pre-specified rule (report §8, NOT tuned after seeing this
module's own results): enter LONG at close when a stock is NEWLY in
the bottom quintile (Q5) of the whole 32-symbol universe ranked by
trailing 60-day return (the report's own strongest configuration, §5),
hold up to 20 bars (backtesting.exit_experiments.
DEFAULT_MAX_HOLDING_BARS -- the SAME cap H_MEANREV_002/H_RELSTRENGTH_001
already use), exit early only on a genuine stop/target hit. Stop/target
sizing reuses strategy/baseline.py's own frozen STOP_ATR_MULTIPLIER/
TARGET_RISK_REWARD constants unchanged -- this experiment tests the
cross-sectional ENTRY signal only, the same isolation posture every
other hypothesis candidate in this project already takes.

Cannot reuse backtesting.exit_experiments.
run_universe_time_based_exit_experiment directly: that function
internally fetches+builds each symbol's OWN indicator_series with no
way to inject the precomputed, whole-universe bucket-membership column
this signal depends on. Mirrors that function's own internal structure
instead -- the same precedent quant_research/relative_strength_signal.py's
own run_universe_relative_strength_experiment already established for
an analogous reason (injecting a benchmark-relative column
run_full_backtest has no concept of) -- but computes bucket membership
ONCE, across the whole universe, before any per-symbol backtest runs,
reusing quant_research.market_behavior.build_universe_datasets and
quant_research.cross_sectional.attach_bucket_membership_column
completely unchanged.
"""

from dataclasses import dataclass, field

import pandas as pd

from backtesting.costs import CostModel
from backtesting.exit_experiments import DEFAULT_MAX_HOLDING_BARS, run_time_based_exit_backtest
from backtesting.splits import split_periods
from backtesting.trade import Trade
from quant_research.cross_sectional import add_lookback_return_columns, attach_bucket_membership_column
from quant_research.market_behavior import SymbolDataset, build_universe_datasets
from strategy.baseline import STOP_ATR_MULTIPLIER, TARGET_RISK_REWARD
from strategy.contracts import Strategy
from strategy.signal import ReasonCode, Side, Signal

DEFAULT_SCORE_LOOKBACK = 60
"""Report §5's own strongest, pre-specified configuration -- not
re-tuned here."""

DEFAULT_N_BUCKETS = 5
DEFAULT_MIN_SYMBOLS_PER_DATE = 15
"""Matches quant_research.cross_sectional.rank_cross_sectionally's own
"at least half the universe" guard, the same measurement this backtest
is turning into a real trade."""

BOTTOM_BUCKET_LABEL = "Q5"
BUCKET_COLUMN = "xsect_bucket_60"


class CrossSectionalLaggardStrategy:
    """Implements the Strategy protocol. Reads a precomputed
    BUCKET_COLUMN (attached once, across the whole universe, by
    attach_bucket_membership_column) rather than computing anything
    itself -- a single-symbol backtest loop has no visibility into the
    rest of the universe (backtesting/exit_experiments.py's own
    bar-by-bar design), so this is the only way a cross-sectional
    signal can reach it -- the same "compute once, attach as a column"
    pattern RelativeStrengthSignalStrategy already established for its
    own benchmark-relative column."""

    def __init__(self, bucket_column: str = BUCKET_COLUMN, bottom_bucket_label: str = BOTTOM_BUCKET_LABEL):
        self.bucket_column = bucket_column
        self.bottom_bucket_label = bottom_bucket_label
        self.name = "cross_sectional_laggard"
        self.version = "xsect-001-q5-60d"

    def generate_signal(self, indicator_series: pd.DataFrame, index: int, symbol: str) -> Signal | None:
        if index == 0:
            return None
        row = indicator_series.iloc[index]
        prev_row = indicator_series.iloc[index - 1]

        bucket = row.get(self.bucket_column)
        if pd.isna(bucket) or bucket != self.bottom_bucket_label:
            return None
        prev_bucket = prev_row.get(self.bucket_column)
        if not pd.isna(prev_bucket) and prev_bucket == self.bottom_bucket_label:
            return None  # not a NEW entry into the bottom bucket -- report's own frozen rule

        if pd.isna(row.get("atr_14")) or pd.isna(row.get("close")):
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
            reason_codes=[ReasonCode.CROSS_SECTIONAL_LAGGARD],
        )


@dataclass
class CrossSectionalBacktestResult:
    development_trades: list[Trade] = field(default_factory=list)
    validation_trades: list[Trade] = field(default_factory=list)
    out_of_sample_trades: list[Trade] = field(default_factory=list)
    failed_symbols: dict[str, str] = field(default_factory=dict)
    n_symbols_ranked: int = 0
    """How many symbols got at least one non-NaN bucket assignment --
    a sanity check the universe-wide ranking step actually ran, never
    inferred from trade counts alone."""


def _slice(frame: pd.DataFrame, start, end) -> pd.DataFrame:
    return frame.loc[(frame.index >= start) & (frame.index <= end)]


def run_cross_sectional_laggard_backtest(
    symbols: list[str],
    *,
    period: str = "5y",
    interval: str = "1d",
    initial_capital: float = 100_000.0,
    cost_model: CostModel | None = None,
    score_lookback: int = DEFAULT_SCORE_LOOKBACK,
    n_buckets: int = DEFAULT_N_BUCKETS,
    min_symbols_per_date: int = DEFAULT_MIN_SYMBOLS_PER_DATE,
    max_holding_bars: int = DEFAULT_MAX_HOLDING_BARS,
) -> CrossSectionalBacktestResult:
    """The real, cost-aware, risk-sized backtest report §10 step 1
    asked for. cost_model defaults to CostModel.india_nse_intraday_2026()
    -- the SAME realistic ~0.21% round-trip estimate the report's own
    cost-sensitivity check (§6.1) used as its benchmark, not the
    zero-cost default run_time_based_exit_backtest would otherwise
    silently apply."""
    cost_model = cost_model or CostModel.india_nse_intraday_2026()

    datasets: dict[str, SymbolDataset] = build_universe_datasets(symbols, period=period, interval=interval)
    result = CrossSectionalBacktestResult()
    for symbol in symbols:
        if symbol not in datasets:
            result.failed_symbols[symbol] = "could not build SymbolDataset (market-data fetch failure)"

    if not datasets:
        return result

    for dataset in datasets.values():
        add_lookback_return_columns(dataset, lookbacks=(score_lookback,))

    attach_bucket_membership_column(
        datasets, score_column=f"trailing_return_{score_lookback}", column_name=BUCKET_COLUMN,
        n_buckets=n_buckets, min_symbols_per_date=min_symbols_per_date,
    )
    result.n_symbols_ranked = sum(1 for dataset in datasets.values() if dataset.frame[BUCKET_COLUMN].notna().any())

    reference = next(iter(datasets.values()))
    split = split_periods(reference.frame.index[0], reference.frame.index[-1])
    strategy: Strategy = CrossSectionalLaggardStrategy()

    for symbol, dataset in datasets.items():
        for label, start, end, bucket in (
            ("development", split.development_start, split.development_end, result.development_trades),
            ("validation", split.validation_start, split.validation_end, result.validation_trades),
            ("out_of_sample", split.out_of_sample_start, split.out_of_sample_end, result.out_of_sample_trades),
        ):
            sliced = _slice(dataset.frame, start, end)
            if sliced.empty:
                continue
            try:
                period_result = run_time_based_exit_backtest(
                    symbol=symbol, indicator_series=sliced, strategy=strategy, cost_model=cost_model,
                    initial_capital=initial_capital, period_label=label, max_holding_bars=max_holding_bars,
                )
            except ValueError as exc:
                result.failed_symbols[symbol] = str(exc)
                continue
            bucket.extend(period_result.trades)

    return result
