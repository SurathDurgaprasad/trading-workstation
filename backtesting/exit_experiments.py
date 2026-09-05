"""Strategy science, Phase 5 (exit hypothesis experiments) -- H_EXIT_001:
move the stop to breakeven once a position reaches +1R unrealized
profit; H_EXIT_002: close half the position at +1R while the remainder
keeps running unmodified; H_EXIT_003: replace the fixed target entirely
with an ATR-based trailing stop (see strategy/hypothesis_registry.py's
own records for the rationale and success/failure criteria).

CRITICAL DESIGN CONSTRAINT: this module is DELIBERATELY a fully
independent, self-contained bar-processing loop -- it does NOT inject
into or modify backtesting/engine.py's run_backtest() or
backtesting/execution.py's shared check_exit()/OpenPosition/close_trade
in any way. Those are the FROZEN baseline's own execution primitives
(strategy/manifest.py's own exit_rules_hash is defined as a hash of
backtesting/execution.py's source specifically so any change there is
detectable) -- paper/engine.py's LIVE trading path also depends on them
unmodified. Even an "optional, backward-compatible" injection point
was deliberately rejected in favor of full isolation: this is research
code, and the highest-priority concern (per the mission's own repeated
instruction) is that the baseline's historical results must never
change, even subtly, even by accident.

Reuses Trade/ExitReason/CostModel/RiskEngine/Account/Signal/Side
UNMODIFIED from their existing modules -- only the entry-fill mechanics
(copied, not shared, from backtesting/engine.py's own loop) and the new
breakeven-tracking exit logic are specific to this module.
"""

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd
from pydantic import BaseModel, ConfigDict

from backtesting.costs import CostModel
from backtesting.equity import EquityPoint, build_equity_curve
from backtesting.execution import bar_day
from backtesting.metrics import PerformanceMetrics, compute_performance_metrics
from backtesting.trade import ExitReason, Trade
from risk.account import new_account
from risk.config import RiskConfig
from risk.engine import RiskEngine
from strategy.contracts import Strategy
from strategy.signal import Side


@dataclass
class _BreakevenOpenPosition:
    """Deliberately NOT backtesting.execution.OpenPosition -- that
    dataclass has only ONE stop_price field, which close_trade() also
    uses to compute r_multiple's own initial_risk. Mutating it in place
    to implement a breakeven move would silently corrupt every
    subsequent r_multiple calculation for this position (the "risk"
    denominator would shrink to ~0 the moment the stop moves to
    breakeven). This class keeps the ORIGINAL risk distance
    (original_stop_price) and the CURRENT effective stop
    (current_stop_price, which starts equal to original_stop_price and
    may move to entry_price exactly once) explicitly separate."""

    signal: object
    entry_time: datetime
    entry_price: float
    quantity: int
    original_stop_price: float
    current_stop_price: float
    target_price: float
    best_price_seen: float
    moved_to_breakeven: bool = False


def _check_exit_with_breakeven(position: _BreakevenOpenPosition, bar: pd.Series) -> tuple[float, ExitReason] | None:
    """Same conservative same-bar-ambiguity rule as backtesting.execution.
    check_exit (stop wins if both could have been touched in one bar) --
    applied against position.current_stop_price, which may already have
    moved to breakeven by the time this is called. The breakeven move
    itself is evaluated FIRST, using this bar's own high, before
    checking whether stop/target was hit THIS bar -- a position that
    reaches +1R and reverses to stop out in the SAME bar correctly exits
    at the NEW (breakeven) stop, not the original one, matching what a
    real breakeven-stop order resting at the exchange would do."""
    high, low = float(bar["high"]), float(bar["low"])
    position.best_price_seen = max(position.best_price_seen, high)

    if not position.moved_to_breakeven:
        initial_risk = position.entry_price - position.original_stop_price
        if initial_risk > 0:
            unrealized_r = (position.best_price_seen - position.entry_price) / initial_risk
            if unrealized_r >= 1.0:
                position.current_stop_price = position.entry_price
                position.moved_to_breakeven = True

    hit_stop = low <= position.current_stop_price
    hit_target = high >= position.target_price
    if hit_stop:
        return position.current_stop_price, ExitReason.STOP
    if hit_target:
        return position.target_price, ExitReason.TARGET
    return None


def _close_breakeven_trade(
    position: _BreakevenOpenPosition, *, exit_price: float, exit_time: datetime, exit_reason: ExitReason,
    symbol: str, cost_model: CostModel,
) -> Trade:
    entry_notional = position.entry_price * position.quantity
    exit_notional = exit_price * position.quantity

    gross_pnl = (exit_price - position.entry_price) * position.quantity
    costs = cost_model.cost_for_fill(notional=entry_notional) + cost_model.cost_for_fill(notional=exit_notional)
    net_pnl = gross_pnl - costs

    # ALWAYS the ORIGINAL risk distance, never the (possibly moved)
    # current_stop_price -- this is exactly the bug this module's own
    # docstring explains reusing backtesting.execution.OpenPosition
    # would silently cause.
    initial_risk = (position.entry_price - position.original_stop_price) * position.quantity
    r_multiple = net_pnl / initial_risk if initial_risk > 0 else 0.0

    return Trade(
        symbol=symbol, side=position.signal.side, strategy_name=position.signal.strategy_name,
        signal_generated_at=position.signal.generated_at, entry_time=position.entry_time,
        entry_price=position.entry_price, quantity=position.quantity, stop_price=position.original_stop_price,
        target_price=position.target_price, exit_time=exit_time, exit_price=exit_price, exit_reason=exit_reason,
        gross_pnl=gross_pnl, costs=costs, net_pnl=net_pnl, r_multiple=r_multiple,
    )


class BreakevenExperimentResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    symbol: str
    period_label: str
    trades: list[Trade]
    equity_curve: list[EquityPoint]
    metrics: PerformanceMetrics


def run_breakeven_stop_backtest(
    *,
    symbol: str,
    indicator_series: pd.DataFrame,
    strategy: Strategy,
    cost_model: CostModel | None = None,
    initial_capital: float = 100_000.0,
    risk_config: RiskConfig | None = None,
    period_label: str = "full",
) -> BreakevenExperimentResult:
    """H_EXIT_001: identical entry mechanics to backtesting.engine.
    run_backtest (same strategy.generate_signal call, same RiskEngine.
    evaluate gate, same next-bar-open fill with slippage, same cash/
    quantity checks) -- the ONLY behavioral difference is the exit
    check, which moves the stop to breakeven once the position reaches
    +1R unrealized profit. When price never reaches +1R for a given
    trade, this produces BYTE-IDENTICAL results to run_backtest (proven
    by tests/test_backtest_exit_experiments.py's own control-case test)."""
    cost_model = cost_model or CostModel()
    risk_engine = RiskEngine(risk_config)

    if indicator_series.empty:
        raise ValueError(f"No indicator data for {symbol}; cannot backtest an empty series.")

    account = new_account(initial_capital)
    trades: list[Trade] = []
    trade_equities: list[tuple[datetime, float]] = []
    open_position: _BreakevenOpenPosition | None = None

    n = len(indicator_series)
    for i in range(n):
        bar = indicator_series.iloc[i]
        timestamp = indicator_series.index[i]

        account.roll_to_day(bar_day(timestamp))

        if open_position is not None:
            account.mark_to_market(float(bar["close"]))
            exit_outcome = _check_exit_with_breakeven(open_position, bar)
            if exit_outcome is not None:
                exit_price, exit_reason = exit_outcome
                trade = _close_breakeven_trade(
                    open_position, exit_price=exit_price, exit_time=timestamp, exit_reason=exit_reason,
                    symbol=symbol, cost_model=cost_model,
                )
                exit_cost = cost_model.cost_for_fill(notional=exit_price * open_position.quantity)
                account.close_position(exit_price=exit_price, exit_cost=exit_cost, net_pnl=trade.net_pnl)

                trades.append(trade)
                trade_equities.append((timestamp, account.equity))
                open_position = None

        if open_position is None and i + 1 < n:
            signal = strategy.generate_signal(indicator_series, i, symbol)
            if signal is not None and signal.side == Side.LONG:
                decision = risk_engine.evaluate(signal, account)

                if decision.approved and decision.position_size is not None:
                    next_bar = indicator_series.iloc[i + 1]
                    raw_entry_price = float(next_bar["open"])
                    entry_price = cost_model.slippage_adjusted_price(price=raw_entry_price, side=signal.side, is_entry=True)

                    quantity = decision.position_size.quantity
                    if quantity * entry_price > account.cash:
                        quantity = int(account.cash // entry_price) if entry_price > 0 else 0

                    if quantity >= 1:
                        entry_cost = cost_model.cost_for_fill(notional=entry_price * quantity)
                        account.open_position(quantity=quantity, entry_price=entry_price, entry_cost=entry_cost)
                        open_position = _BreakevenOpenPosition(
                            signal=signal, entry_time=indicator_series.index[i + 1], entry_price=entry_price,
                            quantity=quantity, original_stop_price=signal.stop_price, current_stop_price=signal.stop_price,
                            target_price=signal.target_price, best_price_seen=entry_price,
                        )

    if open_position is not None:
        last_bar = indicator_series.iloc[-1]
        exit_price = cost_model.slippage_adjusted_price(price=float(last_bar["close"]), side=open_position.signal.side, is_entry=False)
        trade = _close_breakeven_trade(
            open_position, exit_price=exit_price, exit_time=indicator_series.index[-1], exit_reason=ExitReason.END_OF_DATA,
            symbol=symbol, cost_model=cost_model,
        )
        exit_cost = cost_model.cost_for_fill(notional=exit_price * open_position.quantity)
        account.close_position(exit_price=exit_price, exit_cost=exit_cost, net_pnl=trade.net_pnl)
        trades.append(trade)
        trade_equities.append((indicator_series.index[-1], account.equity))

    equity_curve = build_equity_curve(start_time=indicator_series.index[0], initial_capital=initial_capital, trade_equities=trade_equities)
    metrics = compute_performance_metrics(trades, equity_curve)

    return BreakevenExperimentResult(symbol=symbol, period_label=period_label, trades=trades, equity_curve=equity_curve, metrics=metrics)


@dataclass
class UniverseBreakevenExperimentResult:
    development_trades: list[Trade]
    validation_trades: list[Trade]
    out_of_sample_trades: list[Trade]
    failed_symbols: dict[str, str]


def _slice_period(indicator_series: pd.DataFrame, start, end) -> pd.DataFrame:
    return indicator_series.loc[(indicator_series.index >= start) & (indicator_series.index <= end)]


def run_universe_breakeven_experiment(
    symbols: list[str],
    *,
    strategy: Strategy,
    period: str = "5y",
    interval: str = "1d",
    initial_capital: float = 100_000.0,
    cost_model: CostModel | None = None,
    risk_config: RiskConfig | None = None,
) -> UniverseBreakevenExperimentResult:
    """Mirrors backtesting.universe.run_universe_backtest_by_period's own
    structure (fetch, split via backtesting.splits.split_periods, pool
    each period's trades across the universe, isolate one failing
    symbol from the rest) but drives run_breakeven_stop_backtest instead
    of the standard engine for each period slice -- so H_EXIT_001 gets
    the SAME development/validation/out-of-sample promotion discipline
    every other strategy candidate in this project is held to."""
    from backtesting.cache import CachedMarketDataProvider
    from backtesting.splits import split_periods
    from market.data_provider import MarketDataError, get_market_data_provider
    from market.indicators import compute_indicator_series

    provider = CachedMarketDataProvider(get_market_data_provider())
    result = UniverseBreakevenExperimentResult(development_trades=[], validation_trades=[], out_of_sample_trades=[], failed_symbols={})

    for symbol in symbols:
        try:
            ohlcv = provider.fetch_ohlcv(symbol, period=period, interval=interval)
            indicator_series = compute_indicator_series(ohlcv)
        except (MarketDataError, ValueError) as exc:
            result.failed_symbols[symbol] = str(exc)
            continue

        split = split_periods(indicator_series.index[0], indicator_series.index[-1])

        for label, start, end, bucket in (
            ("development", split.development_start, split.development_end, result.development_trades),
            ("validation", split.validation_start, split.validation_end, result.validation_trades),
            ("out_of_sample", split.out_of_sample_start, split.out_of_sample_end, result.out_of_sample_trades),
        ):
            sliced = _slice_period(indicator_series, start, end)
            if sliced.empty:
                continue
            period_result = run_breakeven_stop_backtest(
                symbol=symbol, indicator_series=sliced, strategy=strategy, cost_model=cost_model,
                initial_capital=initial_capital, risk_config=risk_config, period_label=label,
            )
            bucket.extend(period_result.trades)

    return result


# =================================================================
# H_EXIT_002: partial profit-take at +1R, remainder runs unmodified
# =================================================================


@dataclass
class _PartialExitOpenPosition:
    """Tracks a position that may be split into two Trade legs: a
    partial-take at +1R (half the ORIGINAL quantity, floor-divided) and
    a remainder that keeps the original stop/target unchanged. Same
    isolation rationale as _BreakevenOpenPosition -- this is NOT
    backtesting.execution.OpenPosition, which has no notion of a
    quantity that shrinks mid-position or of a single entry fee that
    must be pro-rated across two exit legs rather than charged twice."""

    signal: object
    entry_time: datetime
    entry_price: float
    original_quantity: int
    remaining_quantity: int
    stop_price: float
    target_price: float
    partial_exit_price: float
    partial_quantity: int
    """floor(original_quantity / 2); 0 means the position is too small to
    split, so the partial-take check never fires and this behaves
    exactly like the standard engine."""
    entry_cost_total: float
    """The ONE real entry fill's cost, charged in full to account.cash at
    open_position() time -- each leg's own Trade.costs later gets only a
    pro-rata SHARE of this figure, never the full amount twice."""
    partial_taken: bool = False


def _check_exit_with_partial(position: _PartialExitOpenPosition, bar: pd.Series) -> tuple[float, ExitReason, int] | None:
    """Same conservative same-bar-ambiguity rule as backtesting.execution.
    check_exit: STOP takes priority over TARGET, and both take priority
    over a partial-take -- if a single bar could have hit the stop (or
    the real target) AND crossed the +1R partial level, assume the
    worse-case ordering (stop/target already closes the WHOLE remaining
    quantity, so there is nothing left to give partial credit for)."""
    high, low = float(bar["high"]), float(bar["low"])
    hit_stop = low <= position.stop_price
    hit_target = high >= position.target_price

    if hit_stop:
        return position.stop_price, ExitReason.STOP, position.remaining_quantity
    if hit_target:
        return position.target_price, ExitReason.TARGET, position.remaining_quantity
    if not position.partial_taken and position.partial_quantity > 0 and high >= position.partial_exit_price:
        return position.partial_exit_price, ExitReason.PARTIAL_TARGET, position.partial_quantity
    return None


def _close_partial_leg(
    position: _PartialExitOpenPosition, *, exit_price: float, exit_time: datetime, exit_reason: ExitReason,
    quantity_closed: int, symbol: str, cost_model: CostModel,
) -> Trade:
    gross_pnl = (exit_price - position.entry_price) * quantity_closed
    entry_cost_portion = position.entry_cost_total * (quantity_closed / position.original_quantity)
    exit_cost = cost_model.cost_for_fill(notional=exit_price * quantity_closed)
    costs = entry_cost_portion + exit_cost
    net_pnl = gross_pnl - costs

    initial_risk = (position.entry_price - position.stop_price) * quantity_closed
    r_multiple = net_pnl / initial_risk if initial_risk > 0 else 0.0

    return Trade(
        symbol=symbol, side=position.signal.side, strategy_name=position.signal.strategy_name,
        signal_generated_at=position.signal.generated_at, entry_time=position.entry_time,
        entry_price=position.entry_price, quantity=quantity_closed, stop_price=position.stop_price,
        target_price=position.target_price, exit_time=exit_time, exit_price=exit_price, exit_reason=exit_reason,
        gross_pnl=gross_pnl, costs=costs, net_pnl=net_pnl, r_multiple=r_multiple,
    )


def _partial_close_account(account, *, quantity_closed: int, exit_price: float, exit_cost: float, net_pnl: float) -> None:
    """risk.account.Account.close_position() always fully closes (single-
    position, all-or-nothing accounting -- see its own docstring), so a
    partial close needs this bespoke helper instead of modifying
    risk/account.py itself (same isolation posture as this module's
    H_EXIT_001 code). Mirrors close_position()'s own bookkeeping exactly,
    scoped to only the closed portion; the entry fee was already
    deducted in full at open_position() time, so only the (real,
    separate) exit fee for THIS leg is deducted here -- never a second
    entry deduction."""
    proceeds = quantity_closed * exit_price
    account.cash += proceeds - exit_cost
    account.realized_pnl += net_pnl
    account.total_trades += 1
    account.consecutive_losses = account.consecutive_losses + 1 if net_pnl < 0 else 0
    account.open_position_quantity -= quantity_closed
    account.open_position_cost_basis -= quantity_closed * account.open_position_entry_price
    account.mark_to_market(exit_price)


class PartialProfitExperimentResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    symbol: str
    period_label: str
    trades: list[Trade]
    equity_curve: list[EquityPoint]
    metrics: PerformanceMetrics


def run_partial_profit_backtest(
    *,
    symbol: str,
    indicator_series: pd.DataFrame,
    strategy: Strategy,
    cost_model: CostModel | None = None,
    initial_capital: float = 100_000.0,
    risk_config: RiskConfig | None = None,
    period_label: str = "full",
) -> PartialProfitExperimentResult:
    """H_EXIT_002: identical entry mechanics to backtesting.engine.
    run_backtest -- the ONLY behavioral difference is that once a
    position reaches +1R unrealized profit, HALF the original quantity
    (floor-divided) is closed at that exact price, and the remainder
    keeps running with the ORIGINAL, unmodified stop/target. When a
    position never reaches +1R, or is too small to split (quantity < 2),
    this produces BYTE-IDENTICAL results to run_backtest (proven by
    tests/test_backtest_exit_experiments.py's own control-case tests)."""
    cost_model = cost_model or CostModel()
    risk_engine = RiskEngine(risk_config)

    if indicator_series.empty:
        raise ValueError(f"No indicator data for {symbol}; cannot backtest an empty series.")

    account = new_account(initial_capital)
    trades: list[Trade] = []
    trade_equities: list[tuple[datetime, float]] = []
    open_position: _PartialExitOpenPosition | None = None

    n = len(indicator_series)
    for i in range(n):
        bar = indicator_series.iloc[i]
        timestamp = indicator_series.index[i]

        account.roll_to_day(bar_day(timestamp))

        if open_position is not None:
            account.mark_to_market(float(bar["close"]))
            exit_outcome = _check_exit_with_partial(open_position, bar)
            if exit_outcome is not None:
                exit_price, exit_reason, quantity_closed = exit_outcome
                trade = _close_partial_leg(
                    open_position, exit_price=exit_price, exit_time=timestamp, exit_reason=exit_reason,
                    quantity_closed=quantity_closed, symbol=symbol, cost_model=cost_model,
                )
                exit_cost = cost_model.cost_for_fill(notional=exit_price * quantity_closed)

                if exit_reason == ExitReason.PARTIAL_TARGET:
                    _partial_close_account(account, quantity_closed=quantity_closed, exit_price=exit_price, exit_cost=exit_cost, net_pnl=trade.net_pnl)
                    trades.append(trade)
                    trade_equities.append((timestamp, account.equity))
                    open_position.remaining_quantity -= quantity_closed
                    open_position.partial_taken = True
                else:
                    account.close_position(exit_price=exit_price, exit_cost=exit_cost, net_pnl=trade.net_pnl)
                    trades.append(trade)
                    trade_equities.append((timestamp, account.equity))
                    open_position = None

        if open_position is None and i + 1 < n:
            signal = strategy.generate_signal(indicator_series, i, symbol)
            if signal is not None and signal.side == Side.LONG:
                decision = risk_engine.evaluate(signal, account)

                if decision.approved and decision.position_size is not None:
                    next_bar = indicator_series.iloc[i + 1]
                    raw_entry_price = float(next_bar["open"])
                    entry_price = cost_model.slippage_adjusted_price(price=raw_entry_price, side=signal.side, is_entry=True)

                    quantity = decision.position_size.quantity
                    if quantity * entry_price > account.cash:
                        quantity = int(account.cash // entry_price) if entry_price > 0 else 0

                    if quantity >= 1:
                        entry_cost = cost_model.cost_for_fill(notional=entry_price * quantity)
                        account.open_position(quantity=quantity, entry_price=entry_price, entry_cost=entry_cost)

                        risk_per_share = entry_price - signal.stop_price
                        partial_quantity = quantity // 2 if quantity >= 2 else 0

                        open_position = _PartialExitOpenPosition(
                            signal=signal, entry_time=indicator_series.index[i + 1], entry_price=entry_price,
                            original_quantity=quantity, remaining_quantity=quantity, stop_price=signal.stop_price,
                            target_price=signal.target_price, partial_exit_price=entry_price + risk_per_share,
                            partial_quantity=partial_quantity, entry_cost_total=entry_cost,
                        )

    if open_position is not None:
        last_bar = indicator_series.iloc[-1]
        exit_price = cost_model.slippage_adjusted_price(price=float(last_bar["close"]), side=open_position.signal.side, is_entry=False)
        trade = _close_partial_leg(
            open_position, exit_price=exit_price, exit_time=indicator_series.index[-1], exit_reason=ExitReason.END_OF_DATA,
            quantity_closed=open_position.remaining_quantity, symbol=symbol, cost_model=cost_model,
        )
        exit_cost = cost_model.cost_for_fill(notional=exit_price * open_position.remaining_quantity)
        account.close_position(exit_price=exit_price, exit_cost=exit_cost, net_pnl=trade.net_pnl)
        trades.append(trade)
        trade_equities.append((indicator_series.index[-1], account.equity))

    equity_curve = build_equity_curve(start_time=indicator_series.index[0], initial_capital=initial_capital, trade_equities=trade_equities)
    metrics = compute_performance_metrics(trades, equity_curve)

    return PartialProfitExperimentResult(symbol=symbol, period_label=period_label, trades=trades, equity_curve=equity_curve, metrics=metrics)


@dataclass
class UniversePartialProfitExperimentResult:
    development_trades: list[Trade] = field(default_factory=list)
    validation_trades: list[Trade] = field(default_factory=list)
    out_of_sample_trades: list[Trade] = field(default_factory=list)
    failed_symbols: dict[str, str] = field(default_factory=dict)


def run_universe_partial_profit_experiment(
    symbols: list[str],
    *,
    strategy: Strategy,
    period: str = "5y",
    interval: str = "1d",
    initial_capital: float = 100_000.0,
    cost_model: CostModel | None = None,
    risk_config: RiskConfig | None = None,
) -> UniversePartialProfitExperimentResult:
    """Mirrors run_universe_breakeven_experiment's own structure exactly
    (fetch, split via backtesting.splits.split_periods, pool each
    period's trades across the universe, isolate one failing symbol from
    the rest) but drives run_partial_profit_backtest instead, so
    H_EXIT_002 gets the SAME development/validation/out-of-sample
    promotion discipline as every other candidate."""
    from backtesting.cache import CachedMarketDataProvider
    from backtesting.splits import split_periods
    from market.data_provider import MarketDataError, get_market_data_provider
    from market.indicators import compute_indicator_series

    provider = CachedMarketDataProvider(get_market_data_provider())
    result = UniversePartialProfitExperimentResult()

    for symbol in symbols:
        try:
            ohlcv = provider.fetch_ohlcv(symbol, period=period, interval=interval)
            indicator_series = compute_indicator_series(ohlcv)
        except (MarketDataError, ValueError) as exc:
            result.failed_symbols[symbol] = str(exc)
            continue

        split = split_periods(indicator_series.index[0], indicator_series.index[-1])

        for label, start, end, bucket in (
            ("development", split.development_start, split.development_end, result.development_trades),
            ("validation", split.validation_start, split.validation_end, result.validation_trades),
            ("out_of_sample", split.out_of_sample_start, split.out_of_sample_end, result.out_of_sample_trades),
        ):
            sliced = _slice_period(indicator_series, start, end)
            if sliced.empty:
                continue
            period_result = run_partial_profit_backtest(
                symbol=symbol, indicator_series=sliced, strategy=strategy, cost_model=cost_model,
                initial_capital=initial_capital, risk_config=risk_config, period_label=label,
            )
            bucket.extend(period_result.trades)

    return result


# ==========================================================================
# H_EXIT_003: ATR-based trailing stop replaces the fixed target entirely
# ==========================================================================


@dataclass
class _TrailingStopOpenPosition:
    """No target_price at all -- the trailing stop is the ONLY exit
    mechanism (besides end-of-data). current_stop_price only ever
    ratchets UP (never down), and the level used to check a given bar's
    low is always the level established as of the END of the PREVIOUS
    bar -- never one computed from that same bar's own high -- so a
    single bar can never both justify a higher trail AND exit on that
    newly-justified level (see _check_exit_with_trailing_stop's own
    docstring)."""

    signal: object
    entry_time: datetime
    entry_price: float
    quantity: int
    original_stop_price: float
    current_stop_price: float
    highest_high_seen: float


def _check_exit_with_trailing_stop(position: _TrailingStopOpenPosition, bar: pd.Series) -> tuple[float, ExitReason] | None:
    """Checks THIS bar's low against the stop level already established
    by PRIOR bars first; only afterward does it use THIS bar's own high
    to (possibly) ratchet the level up for the NEXT bar's check. This
    ordering means a bar whose high would justify a higher trail can
    never also exit on that same newly-justified level within the same
    bar -- deliberately more conservative than the target/stop
    same-bar-ambiguity rule used elsewhere (which assumes the worst
    case), since here the ambiguity is about a level the market hasn't
    actually confirmed as touched yet."""
    high, low = float(bar["high"]), float(bar["low"])

    if low <= position.current_stop_price:
        return position.current_stop_price, ExitReason.TRAILING_STOP

    from strategy.baseline import STOP_ATR_MULTIPLIER

    position.highest_high_seen = max(position.highest_high_seen, high)
    atr = bar.get("atr_14")
    if atr is not None and not pd.isna(atr) and float(atr) > 0:
        candidate_stop = position.highest_high_seen - STOP_ATR_MULTIPLIER * float(atr)
        if candidate_stop > position.current_stop_price:
            position.current_stop_price = candidate_stop

    return None


def _close_trailing_trade(
    position: _TrailingStopOpenPosition, *, exit_price: float, exit_time: datetime, exit_reason: ExitReason,
    symbol: str, cost_model: CostModel,
) -> Trade:
    entry_notional = position.entry_price * position.quantity
    exit_notional = exit_price * position.quantity

    gross_pnl = (exit_price - position.entry_price) * position.quantity
    costs = cost_model.cost_for_fill(notional=entry_notional) + cost_model.cost_for_fill(notional=exit_notional)
    net_pnl = gross_pnl - costs

    initial_risk = (position.entry_price - position.original_stop_price) * position.quantity
    r_multiple = net_pnl / initial_risk if initial_risk > 0 else 0.0

    return Trade(
        symbol=symbol, side=position.signal.side, strategy_name=position.signal.strategy_name,
        signal_generated_at=position.signal.generated_at, entry_time=position.entry_time,
        entry_price=position.entry_price, quantity=position.quantity, stop_price=position.original_stop_price,
        target_price=position.entry_price,  # no fixed target in this experiment; recorded as entry_price (N/A placeholder)
        exit_time=exit_time, exit_price=exit_price, exit_reason=exit_reason,
        gross_pnl=gross_pnl, costs=costs, net_pnl=net_pnl, r_multiple=r_multiple,
    )


class TrailingStopExperimentResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    symbol: str
    period_label: str
    trades: list[Trade]
    equity_curve: list[EquityPoint]
    metrics: PerformanceMetrics


def run_trailing_stop_backtest(
    *,
    symbol: str,
    indicator_series: pd.DataFrame,
    strategy: Strategy,
    cost_model: CostModel | None = None,
    initial_capital: float = 100_000.0,
    risk_config: RiskConfig | None = None,
    period_label: str = "full",
) -> TrailingStopExperimentResult:
    """H_EXIT_003: identical entry mechanics to backtesting.engine.
    run_backtest -- the strategy's OWN fixed target_price is never used
    to exit; the ONLY exit mechanisms are the ATR-based trailing stop
    (ratchets up, using the SAME 1.5x-ATR multiplier strategy/baseline.py
    already uses for the original stop distance, recomputed from each
    bar's own current atr_14) and end-of-data force-close."""
    cost_model = cost_model or CostModel()
    risk_engine = RiskEngine(risk_config)

    if indicator_series.empty:
        raise ValueError(f"No indicator data for {symbol}; cannot backtest an empty series.")

    account = new_account(initial_capital)
    trades: list[Trade] = []
    trade_equities: list[tuple[datetime, float]] = []
    open_position: _TrailingStopOpenPosition | None = None

    n = len(indicator_series)
    for i in range(n):
        bar = indicator_series.iloc[i]
        timestamp = indicator_series.index[i]

        account.roll_to_day(bar_day(timestamp))

        if open_position is not None:
            account.mark_to_market(float(bar["close"]))
            exit_outcome = _check_exit_with_trailing_stop(open_position, bar)
            if exit_outcome is not None:
                exit_price, exit_reason = exit_outcome
                trade = _close_trailing_trade(
                    open_position, exit_price=exit_price, exit_time=timestamp, exit_reason=exit_reason,
                    symbol=symbol, cost_model=cost_model,
                )
                exit_cost = cost_model.cost_for_fill(notional=exit_price * open_position.quantity)
                account.close_position(exit_price=exit_price, exit_cost=exit_cost, net_pnl=trade.net_pnl)

                trades.append(trade)
                trade_equities.append((timestamp, account.equity))
                open_position = None

        if open_position is None and i + 1 < n:
            signal = strategy.generate_signal(indicator_series, i, symbol)
            if signal is not None and signal.side == Side.LONG:
                decision = risk_engine.evaluate(signal, account)

                if decision.approved and decision.position_size is not None:
                    next_bar = indicator_series.iloc[i + 1]
                    raw_entry_price = float(next_bar["open"])
                    entry_price = cost_model.slippage_adjusted_price(price=raw_entry_price, side=signal.side, is_entry=True)

                    quantity = decision.position_size.quantity
                    if quantity * entry_price > account.cash:
                        quantity = int(account.cash // entry_price) if entry_price > 0 else 0

                    if quantity >= 1:
                        entry_cost = cost_model.cost_for_fill(notional=entry_price * quantity)
                        account.open_position(quantity=quantity, entry_price=entry_price, entry_cost=entry_cost)
                        open_position = _TrailingStopOpenPosition(
                            signal=signal, entry_time=indicator_series.index[i + 1], entry_price=entry_price,
                            quantity=quantity, original_stop_price=signal.stop_price, current_stop_price=signal.stop_price,
                            highest_high_seen=entry_price,
                        )

    if open_position is not None:
        last_bar = indicator_series.iloc[-1]
        exit_price = cost_model.slippage_adjusted_price(price=float(last_bar["close"]), side=open_position.signal.side, is_entry=False)
        trade = _close_trailing_trade(
            open_position, exit_price=exit_price, exit_time=indicator_series.index[-1], exit_reason=ExitReason.END_OF_DATA,
            symbol=symbol, cost_model=cost_model,
        )
        exit_cost = cost_model.cost_for_fill(notional=exit_price * open_position.quantity)
        account.close_position(exit_price=exit_price, exit_cost=exit_cost, net_pnl=trade.net_pnl)
        trades.append(trade)
        trade_equities.append((indicator_series.index[-1], account.equity))

    equity_curve = build_equity_curve(start_time=indicator_series.index[0], initial_capital=initial_capital, trade_equities=trade_equities)
    metrics = compute_performance_metrics(trades, equity_curve)

    return TrailingStopExperimentResult(symbol=symbol, period_label=period_label, trades=trades, equity_curve=equity_curve, metrics=metrics)


@dataclass
class UniverseTrailingStopExperimentResult:
    development_trades: list[Trade] = field(default_factory=list)
    validation_trades: list[Trade] = field(default_factory=list)
    out_of_sample_trades: list[Trade] = field(default_factory=list)
    failed_symbols: dict[str, str] = field(default_factory=dict)


def run_universe_trailing_stop_experiment(
    symbols: list[str],
    *,
    strategy: Strategy,
    period: str = "5y",
    interval: str = "1d",
    initial_capital: float = 100_000.0,
    cost_model: CostModel | None = None,
    risk_config: RiskConfig | None = None,
) -> UniverseTrailingStopExperimentResult:
    """Mirrors run_universe_breakeven_experiment's/run_universe_partial_profit_experiment's
    own structure exactly, driving run_trailing_stop_backtest instead, so
    H_EXIT_003 gets the SAME development/validation/out-of-sample
    promotion discipline as every other candidate."""
    from backtesting.cache import CachedMarketDataProvider
    from backtesting.splits import split_periods
    from market.data_provider import MarketDataError, get_market_data_provider
    from market.indicators import compute_indicator_series

    provider = CachedMarketDataProvider(get_market_data_provider())
    result = UniverseTrailingStopExperimentResult()

    for symbol in symbols:
        try:
            ohlcv = provider.fetch_ohlcv(symbol, period=period, interval=interval)
            indicator_series = compute_indicator_series(ohlcv)
        except (MarketDataError, ValueError) as exc:
            result.failed_symbols[symbol] = str(exc)
            continue

        split = split_periods(indicator_series.index[0], indicator_series.index[-1])

        for label, start, end, bucket in (
            ("development", split.development_start, split.development_end, result.development_trades),
            ("validation", split.validation_start, split.validation_end, result.validation_trades),
            ("out_of_sample", split.out_of_sample_start, split.out_of_sample_end, result.out_of_sample_trades),
        ):
            sliced = _slice_period(indicator_series, start, end)
            if sliced.empty:
                continue
            period_result = run_trailing_stop_backtest(
                symbol=symbol, indicator_series=sliced, strategy=strategy, cost_model=cost_model,
                initial_capital=initial_capital, risk_config=risk_config, period_label=label,
            )
            bucket.extend(period_result.trades)

    return result
