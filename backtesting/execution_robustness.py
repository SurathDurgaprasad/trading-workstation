"""Strategy science, Phase 8 (Monte Carlo execution-robustness) --
distinct from Phase 5's entry-TIMING Monte Carlo (backtesting.
random_baseline, H_ENTRY_001): that module asks "does WHEN a signal is
generated carry information" by randomizing entry timing while keeping
execution mechanics fixed. This module asks a different question --
"is the strategy's own verdict (this project's own repeated
NEGATIVE_PERFORMANCE finding) an artifact of the backtest's own
necessarily-approximate execution assumptions (perfect fills at the
very next bar's open, one fixed slippage figure), or does it hold up
across a wide range of realistic execution friction?"

Keeps the REAL strategy's REAL signals and the REAL, unmodified exit
mechanics (backtesting.execution.check_exit/close_trade) fixed;
randomizes ONLY the entry-fill side, per iteration:
  - missed fills: some signals never get filled at all (a real order
    can be rejected, or price can gap through the expected level before
    the order executes)
  - delayed fills: some signals fill ONE extra bar later than the
    standard "next bar's open" assumption (a real order can take
    longer than one bar to actually execute)
  - slippage magnitude: each fill's own entry slippage is drawn from a
    random multiplier of the cost model's own baseline
    entry_slippage_bps, rather than always applying the exact same
    fixed figure

Fully reproducible: every iteration uses a seeded random.Random (never
global/unseeded randomness), matching backtesting.random_baseline's own
established convention -- the same seed always produces the same
perturbations.
"""

import random
from dataclasses import dataclass, field

import pandas as pd

from backtesting.costs import CostModel
from backtesting.execution import OpenPosition, bar_day, check_exit, close_trade
from backtesting.trade import ExitReason, Trade
from risk.account import new_account
from risk.config import RiskConfig
from risk.engine import RiskEngine
from strategy.contracts import Strategy
from strategy.signal import Side


@dataclass(frozen=True)
class ExecutionRobustnessConfig:
    missed_fill_probability: float = 0.05
    """Probability a real, risk-approved signal simply never gets
    filled at all -- simulating a rejected order or a price gap through
    the expected entry level before the order could execute."""
    fill_delay_probability: float = 0.15
    """Probability a fill happens ONE extra bar later than the standard
    next-bar-open assumption -- simulating real-world order latency."""
    slippage_multiplier_range: tuple[float, float] = (0.5, 3.0)
    """Each fill's own entry slippage is cost_model.entry_slippage_bps
    times a value drawn uniformly from this range, rather than always
    applying the exact fixed baseline figure."""


def _per_trade_returns(trades: list[Trade]) -> list[float]:
    return [t.net_pnl / (t.entry_price * t.quantity) for t in trades if t.entry_price > 0 and t.quantity > 0]


def run_execution_robust_backtest(
    *,
    symbol: str,
    indicator_series: pd.DataFrame,
    strategy: Strategy,
    cost_model: CostModel | None = None,
    initial_capital: float = 100_000.0,
    risk_config: RiskConfig | None = None,
    config: ExecutionRobustnessConfig | None = None,
    rng: random.Random,
) -> list[Trade]:
    """One randomized-execution pass over a single symbol. Reuses
    backtesting.execution's own OpenPosition/check_exit/close_trade
    UNMODIFIED for the exit side -- only entry-fill mechanics (missed
    fill / delayed fill / randomized slippage) are perturbed. The risk-
    sizing DECISION is still made at signal-generation time (bar i),
    exactly like the standard engine -- a delayed fill uses whatever
    quantity was already approved, applied to whatever price the market
    actually offers at the later fill bar, the same way a real trader
    sizes a position based on where they intended to enter and then
    takes whatever fill they actually get."""
    cost_model = cost_model or CostModel()
    config = config or ExecutionRobustnessConfig()
    risk_engine = RiskEngine(risk_config)

    if indicator_series.empty:
        return []

    account = new_account(initial_capital)
    trades: list[Trade] = []
    open_position: OpenPosition | None = None
    pending_fill: tuple[int, object, int] | None = None  # (fill_index, signal, requested_quantity)

    n = len(indicator_series)
    for i in range(n):
        bar = indicator_series.iloc[i]
        timestamp = indicator_series.index[i]
        account.roll_to_day(bar_day(timestamp))

        if pending_fill is not None and pending_fill[0] == i:
            _, signal, requested_quantity = pending_fill
            pending_fill = None

            raw_entry_price = float(bar["open"])
            slippage_multiplier = rng.uniform(*config.slippage_multiplier_range)
            perturbed_bps = cost_model.entry_slippage_bps * slippage_multiplier
            # LONG-only entry: pay slightly more, matching CostModel.
            # slippage_adjusted_price's own long-entry formula exactly,
            # just with a randomized bps figure instead of the fixed one.
            entry_price = raw_entry_price + raw_entry_price * perturbed_bps / 10_000

            quantity = requested_quantity
            if quantity * entry_price > account.cash:
                quantity = int(account.cash // entry_price) if entry_price > 0 else 0

            if quantity >= 1:
                entry_cost = cost_model.cost_for_fill(notional=entry_price * quantity)
                account.open_position(quantity=quantity, entry_price=entry_price, entry_cost=entry_cost)
                open_position = OpenPosition(
                    signal=signal, entry_time=timestamp, entry_price=entry_price,
                    quantity=quantity, stop_price=signal.stop_price, target_price=signal.target_price,
                )

        if open_position is not None:
            account.mark_to_market(float(bar["close"]))
            exit_outcome = check_exit(open_position, bar)
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

        if open_position is None and pending_fill is None and i + 1 < n:
            signal = strategy.generate_signal(indicator_series, i, symbol)
            if signal is not None and signal.side == Side.LONG:
                decision = risk_engine.evaluate(signal, account)
                if decision.approved and decision.position_size is not None:
                    if rng.random() >= config.missed_fill_probability:
                        fill_index = i + 1
                        if rng.random() < config.fill_delay_probability and i + 2 < n:
                            fill_index = i + 2
                        pending_fill = (fill_index, signal, decision.position_size.quantity)
                    # else: missed fill -- this signal is simply never traded

    if open_position is not None:
        last_bar = indicator_series.iloc[-1]
        exit_price = cost_model.slippage_adjusted_price(price=float(last_bar["close"]), side=open_position.signal.side, is_entry=False)
        trade = close_trade(
            open_position, exit_price=exit_price, exit_time=indicator_series.index[-1], exit_reason=ExitReason.END_OF_DATA,
            symbol=symbol, cost_model=cost_model,
        )
        exit_cost = cost_model.cost_for_fill(notional=exit_price * open_position.quantity)
        account.close_position(exit_price=exit_price, exit_cost=exit_cost, net_pnl=trade.net_pnl)
        trades.append(trade)

    return trades


@dataclass(frozen=True)
class ExecutionRobustnessIteration:
    seed: int
    pooled_trades: int
    mean_return_pct: float
    """Mean per-trade return (net_pnl / (entry_price*quantity)), pooled
    across the whole universe for this iteration -- the SAME semantics
    backtesting.universe.per_trade_returns and backtesting.
    random_baseline's own MonteCarloIteration already use."""


@dataclass(frozen=True)
class ExecutionRobustnessMonteCarloResult:
    iterations: list[ExecutionRobustnessIteration] = field(default_factory=list)
    baseline_mean_return_pct: float | None = None
    """Set by the caller (matching backtesting.random_baseline's own
    convention) to the REAL, unperturbed strategy's own pooled mean
    return -- the reference point every iteration is compared against."""

    @property
    def fraction_flipping_sign_from_baseline(self) -> float | None:
        """Fraction of iterations whose pooled mean return's SIGN
        differs from the baseline (unperturbed) strategy's own sign --
        answers "how fragile is the strategy's own verdict to
        reasonable execution friction alone, with the SAME real signals
        and SAME real exit rule." A HIGH fraction means the conclusion
        is fragile (easily flips under realistic friction); a LOW
        fraction means the conclusion is robust to execution
        assumptions. None if no iterations were run or the baseline is
        unavailable."""
        if not self.iterations or self.baseline_mean_return_pct is None:
            return None
        baseline_positive = self.baseline_mean_return_pct > 0
        flips = sum(1 for it in self.iterations if (it.mean_return_pct > 0) != baseline_positive)
        return flips / len(self.iterations)


def run_execution_robustness_monte_carlo(
    indicator_series_by_symbol: dict[str, pd.DataFrame],
    *,
    strategy: Strategy,
    iterations: int,
    initial_capital: float = 100_000.0,
    cost_model: CostModel | None = None,
    risk_config: RiskConfig | None = None,
    config: ExecutionRobustnessConfig | None = None,
    base_seed: int = 0,
) -> ExecutionRobustnessMonteCarloResult:
    """One iteration = one full randomized-execution pass across every
    symbol in indicator_series_by_symbol, pooling trades across the
    universe. Deterministic and reproducible: iteration i always uses
    seed base_seed + i (per-symbol RNGs derived from f"{seed}:{symbol}",
    matching backtesting.random_baseline's own convention exactly)."""
    cost_model = cost_model or CostModel()
    config = config or ExecutionRobustnessConfig()

    all_iterations: list[ExecutionRobustnessIteration] = []
    for i in range(iterations):
        seed = base_seed + i
        pooled_trades: list[Trade] = []
        for symbol, indicator_series in indicator_series_by_symbol.items():
            rng = random.Random(f"{seed}:{symbol}")
            trades = run_execution_robust_backtest(
                symbol=symbol, indicator_series=indicator_series, strategy=strategy, cost_model=cost_model,
                initial_capital=initial_capital, risk_config=risk_config, config=config, rng=rng,
            )
            pooled_trades.extend(trades)

        returns = _per_trade_returns(pooled_trades)
        mean_return_pct = (sum(returns) / len(returns) * 100.0) if returns else 0.0
        all_iterations.append(ExecutionRobustnessIteration(seed=seed, pooled_trades=len(pooled_trades), mean_return_pct=mean_return_pct))

    return ExecutionRobustnessMonteCarloResult(iterations=all_iterations)
