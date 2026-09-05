"""Strategy science, Phase 5 -- the random-entry baseline the mission
explicitly demands: "the strategy must outperform the random baseline."
Isolates ENTRY TIMING as the only variable by reusing TrendMomentumBaseline's
own risk mechanics verbatim (ATR-based stop/target: STOP_ATR_MULTIPLIER,
TARGET_RISK_REWARD from strategy/baseline.py) -- identical holding/stop/
target-distance/position-sizing/cost assumptions, per the mission's own
explicit instruction, so a difference in outcome can only come from WHEN
a trade was entered, not how it was sized or exited.

RandomEntryStrategy structurally satisfies strategy.contracts.Strategy,
whose own docstring says "no randomness" -- a guideline for REAL trading
strategy candidates (which must be reproducible/explainable in the sense
of "the same market conditions always produce the same signal"). This
class is not a trading strategy candidate; it is a CONTROL for a
statistical comparison, and its randomness is fully bounded and
reproducible: entry indices are chosen once, up front, by an RNG the
caller injects explicitly (never global/unseeded randomness) -- the same
seed always produces the same entry indices, which is exactly what makes
a Monte Carlo run over many DIFFERENT seeds meaningful and reproducible
as a whole.
"""

import random
from dataclasses import dataclass, field

import pandas as pd

from backtesting.costs import CostModel
from backtesting.engine import run_backtest
from backtesting.trade import Trade
from risk.config import RiskConfig
from strategy.baseline import STOP_ATR_MULTIPLIER, TARGET_RISK_REWARD
from strategy.signal import ReasonCode, Side, Signal


class RandomEntryStrategy:
    """Fires a LONG signal at exactly `target_trade_count` bar indices
    (or fewer, if the series doesn't have that many bars with a usable
    ATR14), chosen uniformly at random from every ATR-eligible bar by the
    injected `rng`. `target_trade_count` should be set to the REAL
    strategy's own observed trade count for the SAME symbol/period, so
    the comparison isolates entry timing rather than also varying trade
    frequency."""

    name = "random_entry_baseline"
    version = "1.0"

    def __init__(self, *, target_trade_count: int, rng: random.Random):
        self._target_trade_count = target_trade_count
        self._rng = rng
        self._entry_indices: set[int] | None = None

    def _pick_indices(self, indicator_series: pd.DataFrame) -> set[int]:
        eligible = [
            i for i in range(len(indicator_series))
            if pd.notna(indicator_series.iloc[i].get("atr_14")) and float(indicator_series.iloc[i]["atr_14"]) > 0
        ]
        k = min(self._target_trade_count, len(eligible))
        if k <= 0:
            return set()
        return set(self._rng.sample(eligible, k))

    def generate_signal(self, indicator_series: pd.DataFrame, index: int, symbol: str) -> Signal | None:
        if self._entry_indices is None:
            self._entry_indices = self._pick_indices(indicator_series)
        if index not in self._entry_indices:
            return None

        row = indicator_series.iloc[index]
        atr = float(row["atr_14"])
        if atr <= 0:
            return None
        reference_price = float(row["close"])
        stop_distance = atr * STOP_ATR_MULTIPLIER
        stop_price = reference_price - stop_distance
        if stop_price <= 0:
            return None
        target_price = reference_price + stop_distance * TARGET_RISK_REWARD

        return Signal(
            symbol=symbol, generated_at=indicator_series.index[index], side=Side.LONG,
            reference_price=reference_price, stop_price=stop_price, target_price=target_price,
            risk_reward=TARGET_RISK_REWARD, strategy_name=self.name, reason_codes=[ReasonCode.RANDOM_BASELINE],
        )


@dataclass(frozen=True)
class MonteCarloIteration:
    seed: int
    pooled_trades: int
    mean_return_pct: float
    """Mean of per-trade net_pnl/(entry_price*quantity) across every
    trade this iteration's random entries produced, pooled across the
    whole universe -- the SAME "mean per-trade return" semantics
    backtesting.universe.per_trade_returns already uses, so this
    iteration's number is directly comparable to the real strategy's own
    pooled figure."""


@dataclass(frozen=True)
class RandomBaselineMonteCarloResult:
    iterations: list[MonteCarloIteration] = field(default_factory=list)
    real_strategy_mean_return_pct: float | None = None

    @property
    def fraction_random_at_least_as_good(self) -> float | None:
        """Fraction of Monte Carlo iterations whose pooled mean return was
        >= the real strategy's own pooled mean return -- a permutation-
        style p-value-like statistic answering "if entry timing were pure
        chance, how often would we see performance at least this good
        anyway". A HIGH fraction (close to 1.0) means the real strategy's
        result is unremarkable relative to random chance; a LOW fraction
        means random entries rarely did as well, i.e. entry timing itself
        carried real information. None only if no iterations were run or
        the real strategy's own return is unavailable."""
        if not self.iterations or self.real_strategy_mean_return_pct is None:
            return None
        at_least_as_good = sum(1 for it in self.iterations if it.mean_return_pct >= self.real_strategy_mean_return_pct)
        return at_least_as_good / len(self.iterations)


def _per_trade_returns(trades: list[Trade]) -> list[float]:
    return [t.net_pnl / (t.entry_price * t.quantity) for t in trades if t.entry_price > 0 and t.quantity > 0]


def run_random_baseline_monte_carlo(
    *,
    indicator_series_by_symbol: dict[str, pd.DataFrame],
    real_trade_counts_by_symbol: dict[str, int],
    iterations: int,
    initial_capital: float = 100_000.0,
    cost_model: CostModel | None = None,
    risk_config: RiskConfig | None = None,
    base_seed: int = 0,
) -> RandomBaselineMonteCarloResult:
    """One iteration = one full random-entry pass across every symbol in
    `indicator_series_by_symbol`, using that symbol's own
    `real_trade_counts_by_symbol` entry as the target trade count (0 if
    the symbol is missing from that mapping -- no random trades for a
    symbol the real strategy itself never traded, keeping the comparison
    honest rather than inventing activity that has nothing to compare
    against). Deterministic and reproducible: iteration i always uses
    seed `base_seed + i`, so re-running this with the same inputs
    reproduces byte-identical results."""
    all_iterations: list[MonteCarloIteration] = []

    for i in range(iterations):
        seed = base_seed + i
        pooled_trades: list[Trade] = []
        for symbol, indicator_series in indicator_series_by_symbol.items():
            target_count = real_trade_counts_by_symbol.get(symbol, 0)
            if target_count <= 0:
                continue
            strategy = RandomEntryStrategy(target_trade_count=target_count, rng=random.Random(f"{seed}:{symbol}"))
            result = run_backtest(
                symbol=symbol, indicator_series=indicator_series, strategy=strategy,
                cost_model=cost_model, initial_capital=initial_capital, risk_config=risk_config,
            )
            pooled_trades.extend(result.trades)

        returns = _per_trade_returns(pooled_trades)
        mean_return_pct = (sum(returns) / len(returns) * 100.0) if returns else 0.0
        all_iterations.append(MonteCarloIteration(seed=seed, pooled_trades=len(pooled_trades), mean_return_pct=mean_return_pct))

    return RandomBaselineMonteCarloResult(iterations=all_iterations)
