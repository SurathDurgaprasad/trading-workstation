"""H_MEANREV_010 (docs/research/H_MEANREV_010_EXECUTION_STRUCTURE_
PREREGISTRATION.md, frozen design, committed before this module):
does H_MEANREV_009's own demonstrated gross edge survive a DIFFERENT
execution/sizing/cost structure -- without changing the frozen entry
(quant_research.mean_reversion_signal._oversold_2std_relative_weak) or
the frozen h10 exit horizon, and without a parameter search?

Candidate 2 (fixed-notional sizing) is the only genuinely new
computation this module adds. Its own bar arithmetic and cost calls are
modeled directly on quant_research.cross_sectional_portfolio.
compute_member_return (H_XSECT_005's own already-tested pure function,
NOT modified here) -- the same "entry at signal_idx+1's open, exit at
signal_idx+holding_bars's close, both slippage-adjusted" convention
backtesting.exit_experiments.run_time_based_exit_backtest's own
EXPIRED-exit path already uses. The only reason this is a new function
rather than a direct call to compute_member_return is that
compute_member_return returns only the net fractional return -- this
entry's own pre-registration (S8) requires the full gross/fixed-fee/
variable-cost/notional/quantity breakdown, which compute_member_return
does not expose.

Candidate 3 (zero-fixed-fee diagnostic) needs no new code at all: it is
quant_research.mean_reversion_signal.run_universe_relative_weakness_time_exit_experiment
(H_MEANREV_009's own unmodified runner) called with a CostModel whose
brokerage_per_fill=0.0 -- an already-configurable field, not a new
capability.
"""

from dataclasses import dataclass, field

import pandas as pd

from backtesting.costs import CostModel
from backtesting.splits import split_periods
from quant_research.mean_reversion_signal import _oversold_2std_relative_weak
from strategy.signal import Side


@dataclass(frozen=True)
class FixedNotionalTradeRecord:
    """Candidate 2's own per-trade record -- the full breakdown
    quant_research.cross_sectional_portfolio.compute_member_return does
    not expose (it returns only the net fractional return)."""

    symbol: str
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    quantity: int
    gross_pnl: float
    fixed_fee_cost: float
    """2 x cost_model.brokerage_per_fill (entry + exit fills)."""
    variable_cost: float
    """Percentage fees/taxes/slippage-adjusted-price effect, entry + exit combined -- everything in cost_model.cost_for_fill() beyond the flat brokerage component."""
    net_pnl: float
    entry_notional: float

    @property
    def net_return(self) -> float:
        return self.net_pnl / self.entry_notional

    @property
    def gross_return(self) -> float:
        return self.gross_pnl / self.entry_notional

    @property
    def total_cost(self) -> float:
        return self.fixed_fee_cost + self.variable_cost


def compute_fixed_notional_trade(
    frame: pd.DataFrame, *, symbol: str, signal_idx: int, holding_bars: int, capital_per_slot: float, cost_model: CostModel,
) -> FixedNotionalTradeRecord | None:
    """Pure function, directly unit-testable against a synthetic frame --
    the same 'runner orchestrates, pure helper computes' separation
    compute_member_return itself uses. Bar arithmetic matches
    compute_member_return/run_time_based_exit_backtest's own EXPIRED-exit
    convention exactly: entry at signal_idx+1's OPEN, exit at
    signal_idx+holding_bars's CLOSE, both slippage-adjusted. Returns None
    (never a fabricated record) when there isn't enough future data for
    a full holding period, or entry_price/quantity would be
    non-positive -- the identical fail-closed posture compute_member_return
    already established."""
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

    entry_fill_cost = cost_model.cost_for_fill(notional=entry_notional)
    exit_fill_cost = cost_model.cost_for_fill(notional=exit_notional)
    fixed_fee_cost = 2 * cost_model.brokerage_per_fill
    variable_cost = (entry_fill_cost - cost_model.brokerage_per_fill) + (exit_fill_cost - cost_model.brokerage_per_fill)
    net_pnl = gross_pnl - fixed_fee_cost - variable_cost

    return FixedNotionalTradeRecord(
        symbol=symbol, entry_time=frame.index[entry_bar_idx], entry_price=entry_price,
        exit_time=frame.index[exit_bar_idx], exit_price=exit_price, quantity=quantity,
        gross_pnl=gross_pnl, fixed_fee_cost=fixed_fee_cost, variable_cost=variable_cost,
        net_pnl=net_pnl, entry_notional=entry_notional,
    )


@dataclass
class UniverseFixedNotionalExperimentResult:
    development_trades: list[FixedNotionalTradeRecord] = field(default_factory=list)
    validation_trades: list[FixedNotionalTradeRecord] = field(default_factory=list)
    out_of_sample_trades: list[FixedNotionalTradeRecord] = field(default_factory=list)
    failed_symbols: dict[str, str] = field(default_factory=dict)


def run_universe_fixed_notional_time_exit_experiment(
    symbols: list[str],
    *,
    period: str = "10y",
    interval: str = "1d",
    capital_per_slot: float = 100_000.0,
    cost_model: CostModel | None = None,
    benchmark_symbol: str = "^NSEI",
    max_holding_bars: int = 10,
) -> UniverseFixedNotionalExperimentResult:
    """H_MEANREV_010 Candidate 2: the frozen _oversold_2std_relative_weak
    entry (reused UNCHANGED from quant_research.mean_reversion_signal,
    not reimplemented here), sized via compute_fixed_notional_trade
    instead of RiskEngine's stop-distance-dependent sizing. One position
    at a time per symbol (matching H_MEANREV_009's own account-based
    architecture's economic behavior): after a trade opens, no new entry
    is considered until max_holding_bars bars later, mirroring
    RiskEngine's own account.open_positions > 0 hard veto without
    needing an Account/RiskEngine object (compute_fixed_notional_trade
    is a pure per-position calculation, not a stateful account)."""
    from backtesting.cache import CachedMarketDataProvider
    from market.data_provider import MarketDataError, get_market_data_provider
    from market.indicators import compute_indicator_series
    from quant_research.alpha_features import add_alpha_features

    cost_model = cost_model or CostModel.india_nse_intraday_2026()

    provider = CachedMarketDataProvider(get_market_data_provider())
    result = UniverseFixedNotionalExperimentResult()

    benchmark_ohlcv = provider.fetch_ohlcv(benchmark_symbol, period=period, interval=interval)
    benchmark_series = compute_indicator_series(benchmark_ohlcv)

    for symbol in symbols:
        try:
            ohlcv = provider.fetch_ohlcv(symbol, period=period, interval=interval)
            indicator_series = add_alpha_features(compute_indicator_series(ohlcv), market_series=benchmark_series)
        except (MarketDataError, ValueError) as exc:
            result.failed_symbols[symbol] = str(exc)
            continue

        split = split_periods(indicator_series.index[0], indicator_series.index[-1])
        periods = {
            "development": (split.development_start, split.development_end, result.development_trades),
            "validation": (split.validation_start, split.validation_end, result.validation_trades),
            "out_of_sample": (split.out_of_sample_start, split.out_of_sample_end, result.out_of_sample_trades),
        }

        for period_label, (start, end, pooled_trades) in periods.items():
            sliced = indicator_series.loc[(indicator_series.index >= start) & (indicator_series.index <= end)]
            if sliced.empty:
                continue

            n = len(sliced)
            i = 0
            while i < n:
                row = sliced.iloc[i]
                if _oversold_2std_relative_weak(row):
                    trade = compute_fixed_notional_trade(
                        sliced, symbol=symbol, signal_idx=i, holding_bars=max_holding_bars,
                        capital_per_slot=capital_per_slot, cost_model=cost_model,
                    )
                    if trade is not None:
                        pooled_trades.append(trade)
                        i += max_holding_bars  # one position at a time, matching H_MEANREV_009's own economics
                        continue
                i += 1

    return result
