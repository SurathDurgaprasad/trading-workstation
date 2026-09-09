"""H_XSECT_005 (strategy/hypothesis_registry.py) -- the mission's own
central execution-mechanics question: is H_XSECT_001's cross-sectional
laggard finding fundamentally a PORTFOLIO phenomenon rather than an
individual-stock trading signal? H_XSECT_002/004 tested it exclusively
as independent, single-symbol, stop/target-gated trades -- and every
variant tested so far (H_XSECT_002's original ATR stop, H_XSECT_004's
wide_stop AND no_stop) still retained a TARGET exit that fired well
before the 20-bar horizon in every one of those runs (confirmed by
their own exit-reason diagnostics: TARGET fired in 29-197 trades per
split, even under no_stop). That means NONE of them actually tested
the same fixed-horizon quantity H_XSECT_001's own raw measurement
reports -- this module is the first to.

This is an equal-weight, periodically-rebalanced PORTFOLIO backtest
that reproduces H_XSECT_001's own exact economic design: rank the full
universe by trailing 60-day return, form a basket of the CURRENT
bottom quintile (not "newly entered" -- H_XSECT_002/004's own
restriction, deliberately not carried over here: in a periodic,
non-overlapping rebalance design every basket is fresh by construction,
so "current membership on the rebalance date" is the design H_XSECT_
001's own raw measurement actually used, and the only sensible rule
for this design), hold for a PURE fixed 20-bar horizon with NO stop
and NO target of any kind, then close and re-rank the entire basket.

Rebalance cadence: every 20 trading bars, non-overlapping -- the SAME
cadence H_XSECT_001's own non-overlapping/independence re-sampling
check (docs/research/CROSS_SECTIONAL_RELATIVE_STRENGTH_REPORT.md S6.6)
already used and found the effect survived decisively (n=720,
mean=+1.526%, CI=[+0.927%,+2.126%]) -- reused, not a new pick.

Entry/exit bar arithmetic is DELIBERATELY matched to backtesting.
exit_experiments.run_time_based_exit_backtest's own EXPIRED-exit
convention (entry at the bar AFTER the signal/rebalance bar, using its
OPEN, slippage-adjusted; exit exactly `holding_bars` bars after the
SIGNAL bar's own index, using that bar's CLOSE) -- NOT H_XSECT_001's
own raw close-to-close-over-20-bars measurement, which has no entry
lag at all. This is a deliberate, disclosed choice for internal
consistency with every other executable backtest in this project
(H_XSECT_002/004 and everything before them) -- the raw-measurement-
vs-executable ENTRY TIMING gap remains a real, disclosed, untested
structural difference; see docs/research/
CROSS_SECTIONAL_RELATIVE_STRENGTH_REPORT.md's reconciliation section.

Reuses, never recomputes: quant_research.market_behavior.
build_universe_datasets/SymbolDataset (same causal per-symbol frames
every hypothesis in this project already relies on),
quant_research.cross_sectional.add_lookback_return_columns/
attach_bucket_membership_column (the SAME ranking algorithm H_XSECT_
001/002/003/004 already use, unchanged), backtesting.splits.
split_periods (same dev/val/oos convention), backtesting.costs.
CostModel's own cost_for_fill/slippage_adjusted_price (the SAME
formula backtesting.execution.close_trade/backtesting.universe.
per_trade_returns already use, applied per-position here since there
is no shared Trade/OpenPosition object for a stop-less, portfolio-
sized position)."""

from dataclasses import dataclass, field

import pandas as pd

from backtesting.costs import CostModel
from backtesting.exit_experiments import DEFAULT_MAX_HOLDING_BARS
from backtesting.splits import split_periods
from quant_research.cross_sectional import add_lookback_return_columns, attach_bucket_membership_column
from quant_research.cross_sectional_strategy import (
    BOTTOM_BUCKET_LABEL,
    BUCKET_COLUMN,
    DEFAULT_MIN_SYMBOLS_PER_DATE,
    DEFAULT_N_BUCKETS,
    DEFAULT_SCORE_LOOKBACK,
)
from quant_research.market_behavior import SymbolDataset, build_universe_datasets
from strategy.signal import Side

DEFAULT_REBALANCE_EVERY_BARS = 20
"""Non-overlapping, matching H_XSECT_001's own already-validated
independence-check cadence (see module docstring) -- a distinct
parameter from the holding period even though both happen to equal 20
in this configuration; kept as its own named constant rather than
silently reusing DEFAULT_MAX_HOLDING_BARS for a conceptually different
purpose."""


@dataclass(frozen=True)
class PortfolioPeriodResult:
    rebalance_date: pd.Timestamp
    period_label: str
    member_returns: dict[str, float]
    """symbol -> net (cost-aware) fractional return for that member's
    position this period -- the SAME net_pnl/entry_notional convention
    backtesting.universe.per_trade_returns already uses, computed
    per-position here rather than via a Trade object."""

    @property
    def portfolio_return(self) -> float:
        """Equal-weight mean of this period's member returns -- correct
        by construction since capital was already allocated equally
        across members at entry (see run_cross_sectional_laggard_
        portfolio_backtest), not a second weighting step."""
        if not self.member_returns:
            return 0.0
        return sum(self.member_returns.values()) / len(self.member_returns)


@dataclass
class PortfolioBacktestResult:
    periods: list[PortfolioPeriodResult] = field(default_factory=list)
    skipped_rebalances: int = 0
    """Rebalance dates with zero investable members -- e.g. still
    inside the score's own warm-up, or every Q5 member lacked enough
    future bars for a full holding period. Skipped entirely, never
    padded with a fabricated zero-return period."""

    def returns_for(self, period_label: str) -> list[float]:
        return [p.portfolio_return for p in self.periods if p.period_label == period_label]

    @property
    def development_returns(self) -> list[float]:
        return self.returns_for("development")

    @property
    def validation_returns(self) -> list[float]:
        return self.returns_for("validation")

    @property
    def out_of_sample_returns(self) -> list[float]:
        return self.returns_for("out_of_sample")


def _period_for_date(date: pd.Timestamp, development_end: pd.Timestamp, validation_end: pd.Timestamp) -> str:
    if date <= development_end:
        return "development"
    if date <= validation_end:
        return "validation"
    return "out_of_sample"


def select_reference_dataset(datasets: dict[str, SymbolDataset]) -> SymbolDataset:
    """H_XSECT_006: the reference for the shared rebalance calendar must
    be the dataset with the EARLIEST start date (i.e. the longest
    available history), not an arbitrary dict-order pick. The original
    32-symbol universe happened to share one common start date, so this
    never mattered for H_XSECT_005 -- but a wider universe can include
    recently-listed names with genuinely shorter history, and picking
    one of THOSE as the reference would silently truncate the rebalance
    calendar to their own shorter window, discarding real, available
    years of data for every other symbol. A symbol still missing on a
    given rebalance date is excluded from that period's own basket
    exactly as before (see run_cross_sectional_laggard_portfolio_
    backtest's own per-symbol membership check) -- this only changes
    which dates are considered at all."""
    return min(datasets.values(), key=lambda dataset: dataset.frame.index[0])


def compute_member_return(
    frame: pd.DataFrame, *, signal_idx: int, holding_bars: int, capital_per_slot: float, cost_model: CostModel,
) -> float | None:
    """The pure per-position calculation, extracted so it can be unit
    tested directly against a synthetic frame without a real market-data
    fetch -- the same "runner orchestrates, pure helper computes"
    separation this project's other full-universe runners rely on their
    own already-tested sub-components for. Bar arithmetic matches
    backtesting.exit_experiments.run_time_based_exit_backtest's own
    EXPIRED-exit convention exactly (see module docstring): entry at
    signal_idx+1's OPEN, exit at signal_idx+holding_bars's CLOSE.
    Returns None (never a fabricated 0.0) when there isn't enough
    future data for a full holding period, or entry_price/quantity
    would be non-positive."""
    entry_bar_idx = signal_idx + 1
    exit_bar_idx = signal_idx + holding_bars
    if exit_bar_idx >= len(frame):
        return None

    raw_entry_price = float(frame.iloc[entry_bar_idx]["open"])
    entry_price = cost_model.slippage_adjusted_price(price=raw_entry_price, side=Side.LONG, is_entry=True)
    if entry_price <= 0:
        return None
    quantity = int(capital_per_slot // entry_price)
    if quantity < 1:
        return None

    raw_exit_price = float(frame.iloc[exit_bar_idx]["close"])
    exit_price = cost_model.slippage_adjusted_price(price=raw_exit_price, side=Side.LONG, is_entry=False)

    entry_notional = entry_price * quantity
    exit_notional = exit_price * quantity
    gross_pnl = (exit_price - entry_price) * quantity
    costs = cost_model.cost_for_fill(notional=entry_notional) + cost_model.cost_for_fill(notional=exit_notional)
    net_pnl = gross_pnl - costs
    return net_pnl / entry_notional


def run_cross_sectional_laggard_portfolio_backtest(
    symbols: list[str],
    *,
    period: str = "10y",
    interval: str = "1d",
    initial_capital: float = 100_000.0,
    cost_model: CostModel | None = None,
    score_lookback: int = DEFAULT_SCORE_LOOKBACK,
    n_buckets: int = DEFAULT_N_BUCKETS,
    min_symbols_per_date: int = DEFAULT_MIN_SYMBOLS_PER_DATE,
    holding_bars: int = DEFAULT_MAX_HOLDING_BARS,
    rebalance_every_bars: int = DEFAULT_REBALANCE_EVERY_BARS,
) -> PortfolioBacktestResult:
    """H_XSECT_005: a genuine equal-weight, periodically-rebalanced
    cross-sectional portfolio, no stop, no target -- see module
    docstring for the full design rationale. cost_model defaults to
    CostModel.india_nse_intraday_2026(), the same realistic estimate
    every other H_XSECT_* backtest in this project uses."""
    cost_model = cost_model or CostModel.india_nse_intraday_2026()

    datasets: dict[str, SymbolDataset] = build_universe_datasets(symbols, period=period, interval=interval)
    result = PortfolioBacktestResult()
    if not datasets:
        return result

    for dataset in datasets.values():
        add_lookback_return_columns(dataset, lookbacks=(score_lookback,))

    attach_bucket_membership_column(
        datasets, score_column=f"trailing_return_{score_lookback}", column_name=BUCKET_COLUMN,
        n_buckets=n_buckets, min_symbols_per_date=min_symbols_per_date,
    )

    reference = select_reference_dataset(datasets)
    split = split_periods(reference.frame.index[0], reference.frame.index[-1])
    rebalance_dates = reference.frame.index[::rebalance_every_bars]

    for rebalance_date in rebalance_dates:
        period_label = _period_for_date(rebalance_date, split.development_end, split.validation_end)

        members = [
            symbol for symbol, dataset in datasets.items()
            if rebalance_date in dataset.frame.index and dataset.frame.loc[rebalance_date, BUCKET_COLUMN] == BOTTOM_BUCKET_LABEL
        ]
        if not members:
            result.skipped_rebalances += 1
            continue

        capital_per_slot = initial_capital / len(members)
        member_returns: dict[str, float] = {}

        for symbol in members:
            dataset = datasets[symbol]
            signal_idx = dataset.frame.index.get_loc(rebalance_date)
            member_return = compute_member_return(
                dataset.frame, signal_idx=signal_idx, holding_bars=holding_bars,
                capital_per_slot=capital_per_slot, cost_model=cost_model,
            )
            if member_return is not None:
                member_returns[symbol] = member_return

        if member_returns:
            result.periods.append(PortfolioPeriodResult(rebalance_date=rebalance_date, period_label=period_label, member_returns=member_returns))
        else:
            result.skipped_rebalances += 1

    return result
