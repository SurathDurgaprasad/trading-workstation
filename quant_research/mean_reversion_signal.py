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

from backtesting.execution import OpenPosition, check_exit
from backtesting.trade import ExitReason, Trade
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


def _oversold_2std_trending_up(row: pd.Series) -> bool:
    """H_MEANREV_004 (strategy/hypothesis_registry.py): Candidate A's own
    frozen -2.0std threshold, with H_MEANREV_003's own regime gate added
    -- requires a `market_trend_regime` column (attached externally via
    quant_research.context_experiments.attach_external_regime-style
    forward-fill, the same machinery H_MEANREV_003 already used; this
    predicate does not compute it) equal to "TRENDING_UP". Isolates the
    entry-TIMING question (does gating on market regime help) from the
    exit mechanic, which stays completely unchanged from Candidate A."""
    if pd.isna(row.get("zscore_close_20")):
        return False
    return bool(row["zscore_close_20"] < -2.0 and row.get("market_trend_regime") == "TRENDING_UP")


def _oversold_1_5std_trending_up(row: pd.Series) -> bool:
    """H_MEANREV_004: Candidate B's own frozen -1.5std threshold, same
    regime gate as _oversold_2std_trending_up."""
    if pd.isna(row.get("zscore_close_20")):
        return False
    return bool(row["zscore_close_20"] < -1.5 and row.get("market_trend_regime") == "TRENDING_UP")


REGIME_GATED_CANDIDATES = {
    "A_oversold_2std_trending_up": _oversold_2std_trending_up,
    "B_oversold_1_5std_trending_up": _oversold_1_5std_trending_up,
}
"""H_MEANREV_004 -- kept as a SEPARATE dict from CANDIDATES rather than
merged into it, so H_MEANREV_001's own already-registered, frozen
candidate set is never silently mutated by a later hypothesis."""


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

    def __init__(self, candidate_name: str, candidates: dict | None = None, stop_atr_multiplier: float = STOP_ATR_MULTIPLIER):
        """`candidates` defaults to the original, frozen CANDIDATES dict
        (H_MEANREV_001) -- pass REGIME_GATED_CANDIDATES explicitly for
        H_MEANREV_004's own candidates rather than merging the two dicts,
        so neither hypothesis's own frozen candidate set can be silently
        mutated by the other. `stop_atr_multiplier` overrides ONLY the
        stop distance (target is still derived from it via the same
        TARGET_RISK_REWARD formula, so both move together) -- mirrors
        quant_research.cross_sectional_strategy.CrossSectionalLaggardStrategy's
        own identical parameter, added here for H_EXIT_005: a
        deliberately wide value makes the price-based stop/target
        practically unreachable, satisfying RiskEngine's structural
        requirement for a valid stop/target without letting either
        dominate exits -- the same technique H_XSECT_005 already used.
        Defaults to the ORIGINAL H_MEANREV_001/004 value, so not passing
        it reproduces their exact behavior unchanged."""
        self.candidate_name = candidate_name
        self._predicate = (candidates or CANDIDATES)[candidate_name]
        self.stop_atr_multiplier = stop_atr_multiplier
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

        stop_distance = atr * self.stop_atr_multiplier
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


@dataclass
class UniverseRegimeGatedMeanReversionExperimentResult:
    """H_MEANREV_004: same pooling shape as UniverseMeanReversionExperimentResult,
    keyed by REGIME_GATED_CANDIDATES instead of CANDIDATES."""

    development_trades: dict[str, list[Trade]] = field(default_factory=lambda: {name: [] for name in REGIME_GATED_CANDIDATES})
    validation_trades: dict[str, list[Trade]] = field(default_factory=lambda: {name: [] for name in REGIME_GATED_CANDIDATES})
    out_of_sample_trades: dict[str, list[Trade]] = field(default_factory=lambda: {name: [] for name in REGIME_GATED_CANDIDATES})
    failed_symbols: dict[str, str] = field(default_factory=dict)


def run_universe_regime_gated_mean_reversion_experiment(
    symbols: list[str],
    *,
    period: str = "10y",
    interval: str = "1d",
    initial_capital: float = 100_000.0,
    cost_model=None,
    benchmark_symbol: str = "^NSEI",
) -> UniverseRegimeGatedMeanReversionExperimentResult:
    """H_MEANREV_004 (strategy/hypothesis_registry.py): does H_MEANREV_003's
    raw finding (oversold entries gated on NIFTY's own TRENDING_UP
    regime) survive becoming a real, cost-aware, risk-sized trade?
    Mirrors run_universe_mean_reversion_experiment's own structure
    exactly, with two additions: (1) the benchmark's own trend regime is
    fetched ONCE (not per-symbol) via quant_research.context_experiments.
    build_benchmark_regime_series, then forward-filled onto each symbol's
    own calendar -- the identical alignment convention
    quant_research.context_experiments.attach_external_regime already
    uses for SymbolDataset objects, inlined here since this runner works
    on raw indicator_series DataFrames instead; (2) cost_model defaults
    to CostModel.india_nse_intraday_2026() -- H_MEANREV_001's own
    original runner used the generic, non-NSE-specific default
    CostModel() instead, a disclosed, deliberate improvement here, not a
    silent change (see the H_MEANREV_004 pre-registration S3)."""
    from backtesting.cache import CachedMarketDataProvider
    from backtesting.costs import CostModel
    from backtesting.engine import run_backtest
    from backtesting.splits import split_periods
    from market.data_provider import MarketDataError, get_market_data_provider
    from market.indicators import compute_indicator_series
    from quant_research.context_experiments import build_benchmark_regime_series

    cost_model = cost_model or CostModel.india_nse_intraday_2026()

    provider = CachedMarketDataProvider(get_market_data_provider())
    result = UniverseRegimeGatedMeanReversionExperimentResult()

    benchmark_regime = build_benchmark_regime_series(benchmark_symbol, period=period, interval=interval)
    if benchmark_regime is None:
        raise ValueError(f"Could not build a trend regime series for benchmark {benchmark_symbol!r}; cannot gate any candidate on it.")

    for symbol in symbols:
        try:
            ohlcv = provider.fetch_ohlcv(symbol, period=period, interval=interval)
            indicator_series = add_mean_reversion_columns(compute_indicator_series(ohlcv))
        except (MarketDataError, ValueError) as exc:
            result.failed_symbols[symbol] = str(exc)
            continue

        indicator_series["market_trend_regime"] = benchmark_regime.reindex(indicator_series.index, method="ffill")

        split = split_periods(indicator_series.index[0], indicator_series.index[-1])
        periods = {
            "development": (split.development_start, split.development_end, result.development_trades),
            "validation": (split.validation_start, split.validation_end, result.validation_trades),
            "out_of_sample": (split.out_of_sample_start, split.out_of_sample_end, result.out_of_sample_trades),
        }

        for candidate_name in REGIME_GATED_CANDIDATES:
            strategy: Strategy = MeanReversionSignalStrategy(candidate_name, candidates=REGIME_GATED_CANDIDATES)
            for period_label, (start, end, pooled_trades) in periods.items():
                sliced = indicator_series.loc[(indicator_series.index >= start) & (indicator_series.index <= end)]
                run_result = run_backtest(
                    symbol=symbol, indicator_series=sliced, strategy=strategy, cost_model=cost_model,
                    initial_capital=initial_capital, period_label=period_label,
                )
                pooled_trades[candidate_name].extend(run_result.trades)

    return result


def decide_completion_exit(
    open_position: OpenPosition, bar: pd.Series, *, bars_held: int, max_holding_bars: int,
) -> tuple[float, ExitReason] | None:
    """H_EXIT_005's own exit-priority rule, extracted as a pure function
    so it is directly unit-testable without the surrounding account/
    loop machinery. Checked in this order, matching the pre-
    registration's own frozen §5: (1) check_exit() -- the deliberately
    wide, practically-unreachable price stop/target, reused UNMODIFIED,
    still honestly recorded as STOP/TARGET on the rare chance it fires;
    (2) zscore_close_20 >= 0.0 -- the reversal thesis completing, this
    hypothesis's own new exit condition; (3) bars_held >= max_holding_bars
    -- the safety time cap. Returns None if none apply (position stays
    open). NaN-safe: a missing zscore_close_20 never satisfies (2) (NaN
    comparisons are always False)."""
    exit_outcome = check_exit(open_position, bar)
    if exit_outcome is not None:
        return exit_outcome

    zscore = bar.get("zscore_close_20")
    if zscore is not None and pd.notna(zscore) and float(zscore) >= 0.0:
        return float(bar["close"]), ExitReason.MEAN_REVERSION_COMPLETE

    if bars_held >= max_holding_bars:
        return float(bar["close"]), ExitReason.EXPIRED

    return None


DEFAULT_WIDE_STOP_ATR_MULTIPLIER = 20.0
"""H_EXIT_005: the SAME 'effectively unreachable' multiplier value
H_XSECT_004's own no_stop variant already used (see strategy/
hypothesis_registry.py's H_XSECT_004 entry), reused here rather than
inventing a new number. Not a search input; a single, fixed,
pre-registered constant."""


@dataclass
class UniverseMeanReversionCompletionExitExperimentResult:
    """H_EXIT_005: same pooling shape as UniverseRegimeGatedMeanReversionExperimentResult."""

    development_trades: dict[str, list[Trade]] = field(default_factory=lambda: {name: [] for name in REGIME_GATED_CANDIDATES})
    validation_trades: dict[str, list[Trade]] = field(default_factory=lambda: {name: [] for name in REGIME_GATED_CANDIDATES})
    out_of_sample_trades: dict[str, list[Trade]] = field(default_factory=lambda: {name: [] for name in REGIME_GATED_CANDIDATES})
    failed_symbols: dict[str, str] = field(default_factory=dict)


def run_universe_mean_reversion_completion_exit_experiment(
    symbols: list[str],
    *,
    period: str = "10y",
    interval: str = "1d",
    initial_capital: float = 100_000.0,
    cost_model=None,
    benchmark_symbol: str = "^NSEI",
    max_holding_bars: int | None = None,
    wide_stop_atr_multiplier: float = DEFAULT_WIDE_STOP_ATR_MULTIPLIER,
) -> UniverseMeanReversionCompletionExitExperimentResult:
    """H_EXIT_005 (strategy/hypothesis_registry.py): does H_MEANREV_004's
    TRENDING_UP-gated oversold entry survive becoming a real trade when
    exited on the reversal thesis itself completing (zscore_close_20
    recovering to >= 0.0 -- price back at its own trailing mean) or a
    20-bar safety cap, instead of the project's frozen ATR stop/target?

    DELIBERATELY a fully independent, self-contained bar-processing
    loop -- the SAME isolation posture backtesting/exit_experiments.py's
    own module docstring establishes for H_EXIT_001-004: this does NOT
    inject into or modify backtesting/engine.py's run_backtest() or
    backtesting/execution.py's shared check_exit()/OpenPosition/
    close_trade in any way. Those are the frozen baseline's own
    execution primitives; even an "optional" injection point was
    rejected there in favor of full isolation, and the same reasoning
    applies here. check_exit() is still called every bar, unmodified,
    against a deliberately wide (practically unreachable) stop/target
    (see MeanReversionSignalStrategy's own stop_atr_multiplier override)
    -- kept rather than removed so a genuine, if extremely unlikely,
    price-based stop/target hit is still honestly recorded as such,
    never silently absorbed into the new exit reason."""
    from backtesting.cache import CachedMarketDataProvider
    from backtesting.costs import CostModel
    from backtesting.execution import bar_day, close_trade
    from backtesting.exit_experiments import DEFAULT_MAX_HOLDING_BARS
    from backtesting.splits import split_periods
    from market.data_provider import MarketDataError, get_market_data_provider
    from market.indicators import compute_indicator_series
    from quant_research.context_experiments import build_benchmark_regime_series
    from risk.account import new_account
    from risk.engine import RiskEngine

    cost_model = cost_model or CostModel.india_nse_intraday_2026()
    max_holding_bars = max_holding_bars if max_holding_bars is not None else DEFAULT_MAX_HOLDING_BARS

    provider = CachedMarketDataProvider(get_market_data_provider())
    result = UniverseMeanReversionCompletionExitExperimentResult()

    benchmark_regime = build_benchmark_regime_series(benchmark_symbol, period=period, interval=interval)
    if benchmark_regime is None:
        raise ValueError(f"Could not build a trend regime series for benchmark {benchmark_symbol!r}; cannot gate any candidate on it.")

    risk_engine = RiskEngine()

    for symbol in symbols:
        try:
            ohlcv = provider.fetch_ohlcv(symbol, period=period, interval=interval)
            indicator_series = add_mean_reversion_columns(compute_indicator_series(ohlcv))
        except (MarketDataError, ValueError) as exc:
            result.failed_symbols[symbol] = str(exc)
            continue

        indicator_series["market_trend_regime"] = benchmark_regime.reindex(indicator_series.index, method="ffill")

        split = split_periods(indicator_series.index[0], indicator_series.index[-1])
        periods = {
            "development": (split.development_start, split.development_end, result.development_trades),
            "validation": (split.validation_start, split.validation_end, result.validation_trades),
            "out_of_sample": (split.out_of_sample_start, split.out_of_sample_end, result.out_of_sample_trades),
        }

        for candidate_name in REGIME_GATED_CANDIDATES:
            strategy = MeanReversionSignalStrategy(candidate_name, candidates=REGIME_GATED_CANDIDATES, stop_atr_multiplier=wide_stop_atr_multiplier)

            for period_label, (start, end, pooled_trades) in periods.items():
                sliced = indicator_series.loc[(indicator_series.index >= start) & (indicator_series.index <= end)]
                if sliced.empty:
                    continue

                account = new_account(initial_capital)
                trades: list[Trade] = []
                open_position: OpenPosition | None = None
                bars_held = 0

                n = len(sliced)
                for i in range(n):
                    bar = sliced.iloc[i]
                    timestamp = sliced.index[i]
                    account.roll_to_day(bar_day(timestamp))

                    if open_position is not None:
                        account.mark_to_market(float(bar["close"]))
                        bars_held += 1  # counts THIS bar -- matches run_time_based_exit_backtest's own EXPIRED convention
                        exit_outcome = decide_completion_exit(open_position, bar, bars_held=bars_held, max_holding_bars=max_holding_bars)

                        if exit_outcome is not None:
                            exit_price, exit_reason = exit_outcome
                            trade = close_trade(
                                open_position, exit_price=exit_price, exit_time=timestamp, exit_reason=exit_reason,
                                symbol=symbol, cost_model=cost_model,
                            )
                            exit_cost = cost_model.cost_for_fill(notional=exit_price * open_position.quantity)
                            account.close_position(exit_price=exit_price, exit_cost=exit_cost, net_pnl=trade.net_pnl)
                            trades.append(trade)
                            open_position = None
                            bars_held = 0

                    if open_position is None and i + 1 < n:
                        signal = strategy.generate_signal(sliced, i, symbol)
                        if signal is not None and signal.side == Side.LONG:
                            decision = risk_engine.evaluate(signal, account)
                            if decision.approved and decision.position_size is not None:
                                next_bar = sliced.iloc[i + 1]
                                raw_entry_price = float(next_bar["open"])
                                entry_price = cost_model.slippage_adjusted_price(price=raw_entry_price, side=signal.side, is_entry=True)

                                quantity = decision.position_size.quantity
                                if quantity * entry_price > account.cash:
                                    quantity = int(account.cash // entry_price) if entry_price > 0 else 0

                                if quantity >= 1:
                                    entry_cost = cost_model.cost_for_fill(notional=entry_price * quantity)
                                    account.open_position(quantity=quantity, entry_price=entry_price, entry_cost=entry_cost)
                                    open_position = OpenPosition(
                                        signal=signal, entry_time=sliced.index[i + 1], entry_price=entry_price,
                                        quantity=quantity, stop_price=signal.stop_price, target_price=signal.target_price,
                                    )
                                    bars_held = 0

                if open_position is not None:
                    last_bar = sliced.iloc[-1]
                    exit_price = cost_model.slippage_adjusted_price(price=float(last_bar["close"]), side=open_position.signal.side, is_entry=False)
                    trade = close_trade(
                        open_position, exit_price=exit_price, exit_time=sliced.index[-1], exit_reason=ExitReason.END_OF_DATA,
                        symbol=symbol, cost_model=cost_model,
                    )
                    exit_cost = cost_model.cost_for_fill(notional=exit_price * open_position.quantity)
                    account.close_position(exit_price=exit_price, exit_cost=exit_cost, net_pnl=trade.net_pnl)
                    trades.append(trade)

                pooled_trades[candidate_name].extend(trades)

    return result
