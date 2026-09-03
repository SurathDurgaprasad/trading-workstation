"""Phase 41 -- profitability evidence framework.

The roadmap's own rule: "the system must NOT claim profitability."
Every function here is a read-only, pure computation over already-
persisted, already-evaluated predictions (the same `EvaluatedPrediction`
list learning.analysis's other functions consume) -- nothing here
executes a trade, backtests a hypothetical, or estimates future
performance.

learning.analysis already computes win_rate/average_return/profit_factor.
What was missing, and is the entire point of this module, is an HONEST
VERDICT: is there enough resolved history to say anything at all, and
if so, is the observed average return actually distinguishable from
zero -- or could a small, noisy sample just as easily have produced this
exact number by chance. The verdict is deliberately keyed on the mean
RETURN's own confidence interval (not a bare win-rate percentage): a
strategy with an asymmetric risk/reward can be genuinely profitable
with a sub-50% win rate, so win rate alone cannot answer "is this
working" -- expectancy can.

`MIN_SAMPLE_SIZE_FOR_A_VERDICT` and the normal-approximation confidence
interval both mirror learning.adaptation's own established, stated
rule-of-thumb threshold (n=30, a conventional CLT-approximation
floor) -- reused deliberately, not re-derived, so this project states
ONE number for "how much evidence is enough," not two different ones
in two different places.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from learning.analysis import EvaluatedPrediction

MIN_SAMPLE_SIZE_FOR_A_VERDICT = 30
"""Same rule-of-thumb as learning.adaptation.MIN_SAMPLE_SIZE_FOR_PROMOTION
-- a conventional floor for a normal approximation to be reasonable, not
a guarantee of significance. Even at this size, a personal trading
system's sample is small; every verdict's own reasoning text says so."""

_CONFIDENCE_Z = 1.96
"""z-score for a 95% confidence interval under a normal approximation
-- a standard, stated default, not tuned against any result in this
project."""


class ProfitabilityVerdict(str, Enum):
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    """Fewer than MIN_SAMPLE_SIZE_FOR_A_VERDICT resolved predictions --
    not enough history to say anything, positive or negative."""
    STATISTICALLY_MEANINGLESS = "STATISTICALLY_MEANINGLESS"
    """Enough samples to compute a confidence interval, but that interval
    for the mean per-trade return STRADDLES zero -- the observed average
    cannot be distinguished from noise at the stated confidence level."""
    POSITIVE_PERFORMANCE = "POSITIVE_PERFORMANCE"
    """The mean return's confidence interval lies entirely above zero."""
    NEGATIVE_PERFORMANCE = "NEGATIVE_PERFORMANCE"
    """The mean return's confidence interval lies entirely below zero."""


class SectorPerformance(BaseModel):
    model_config = ConfigDict(frozen=True)

    sector: str
    """The sector label research.models.SectorInfo recorded for this
    symbol at decision time, or "Unknown" when no sector was available
    (e.g. an index/derivative symbol, or a provider that returned none)
    -- never fabricated."""
    total: int
    resolved: int
    win_rate: float | None
    average_return: float | None


class ProfitabilityReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    sample_size: int
    """Count of RESOLVED predictions with a recorded return -- the
    denominator behind every statistic below."""
    win_rate: float | None
    win_rate_ci_low: float | None
    win_rate_ci_high: float | None
    """95% Wilson score interval for the win rate -- informational
    context; the verdict itself is keyed on mean return, not this."""
    average_win: float | None
    """Mean return of winning trades only. None if there were no wins."""
    average_loss: float | None
    """Mean return of losing trades only (negative). None if there were no losses."""
    expectancy: float | None
    """The exact mean of every resolved trade's return (equal to
    average_return) -- the expected return of one trade, the single
    number that actually answers "is this strategy working," unlike win
    rate alone. Deliberately NOT reconstructed from win_rate * average_win
    + loss_rate * average_loss: that decomposition silently misattributes
    any breakeven trade (a return of exactly 0.0, counted in neither
    average_win nor average_loss) and would diverge from the true mean
    whenever one exists -- the direct mean is always correct."""
    profit_factor: float | None
    """Same definition learning.analysis._resolution_stats already
    uses: gross gains / abs(gross losses)."""
    max_drawdown: float | None
    """Largest peak-to-trough decline of a SEQUENTIAL, compounding
    equity curve built by applying each resolved trade's return in
    entry-time order. This is a trade-return sequence, not a real
    day-by-day account equity curve (trades may not be exclusive
    positions) -- an approximation, stated as such."""
    return_volatility: float | None
    """Sample standard deviation of per-trade returns. Explicitly NOT a
    Sharpe ratio -- there is no time-normalization (trades are not
    evenly spaced, and this project tracks no risk-free rate) -- see
    the reasoning text for this caveat whenever it's shown."""
    mean_return_ci_low: float | None
    mean_return_ci_high: float | None
    """95% confidence interval for the mean per-trade return -- THIS is
    what `verdict` is actually computed from."""
    verdict: ProfitabilityVerdict
    reasoning: list[str]
    """Every number and threshold that produced `verdict`, in order --
    fully auditable without re-running the computation."""

    @classmethod
    def empty(cls) -> "ProfitabilityReport":
        return cls(
            sample_size=0, win_rate=None, win_rate_ci_low=None, win_rate_ci_high=None,
            average_win=None, average_loss=None, expectancy=None, profit_factor=None,
            max_drawdown=None, return_volatility=None, mean_return_ci_low=None, mean_return_ci_high=None,
            verdict=ProfitabilityVerdict.INSUFFICIENT_DATA, reasoning=["No resolved predictions available."],
        )


def _wilson_score_interval(wins: int, n: int, *, z: float = _CONFIDENCE_Z) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    phat = wins / n
    denominator = 1 + z**2 / n
    center = (phat + z**2 / (2 * n)) / denominator
    margin = (z * math.sqrt((phat * (1 - phat) + z**2 / (4 * n)) / n)) / denominator
    return (max(0.0, center - margin), min(1.0, center + margin))


def _sample_stdev(values: list[float]) -> float | None:
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(variance)


def _mean_confidence_interval(values: list[float], *, z: float = _CONFIDENCE_Z) -> tuple[float, float] | None:
    n = len(values)
    stdev = _sample_stdev(values)
    if stdev is None:
        return None
    mean = sum(values) / n
    margin = z * stdev / math.sqrt(n)
    return (mean - margin, mean + margin)


def _max_drawdown(returns_in_order: list[float]) -> float | None:
    if not returns_in_order:
        return None
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns_in_order:
        equity *= (1 + r)
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)
    return max_dd


def compute_profitability_report(items: list["EvaluatedPrediction"]) -> ProfitabilityReport:
    from learning.analysis import _resolution_stats, _resolved_returns

    chronological = sorted(items, key=lambda item: item.prediction.entry_time)
    returns = _resolved_returns(chronological)
    n = len(returns)

    if n == 0:
        return ProfitabilityReport.empty()

    win_rate, average_return, profit_factor = _resolution_stats(returns)
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]
    average_win = (sum(wins) / len(wins)) if wins else None
    average_loss = (sum(losses) / len(losses)) if losses else None
    expectancy = average_return  # the exact mean of every resolved return -- see the field's own docstring for why this is not reconstructed from win/loss averages

    win_ci_low, win_ci_high = _wilson_score_interval(len(wins), n)
    mean_ci = _mean_confidence_interval(returns)
    max_dd = _max_drawdown(returns)
    volatility = _sample_stdev(returns)

    reasoning: list[str] = [
        f"{n} resolved prediction(s) with a recorded return (minimum required for any verdict: {MIN_SAMPLE_SIZE_FOR_A_VERDICT}).",
    ]

    if n < MIN_SAMPLE_SIZE_FOR_A_VERDICT:
        reasoning.append(f"Sample size below {MIN_SAMPLE_SIZE_FOR_A_VERDICT} -- not enough history to say anything, positive or negative.")
        verdict = ProfitabilityVerdict.INSUFFICIENT_DATA
    elif mean_ci is None:
        reasoning.append("Could not compute a confidence interval for the mean return (degenerate sample).")
        verdict = ProfitabilityVerdict.INSUFFICIENT_DATA
    else:
        ci_low, ci_high = mean_ci
        reasoning.append(f"Mean per-trade return: {average_return:+.2%}, 95% CI [{ci_low:+.2%}, {ci_high:+.2%}].")
        if ci_low <= 0.0 <= ci_high:
            reasoning.append("The confidence interval straddles zero -- this average return cannot be distinguished from noise at 95% confidence.")
            verdict = ProfitabilityVerdict.STATISTICALLY_MEANINGLESS
        elif ci_low > 0.0:
            reasoning.append("The confidence interval lies entirely above zero.")
            verdict = ProfitabilityVerdict.POSITIVE_PERFORMANCE
        else:
            reasoning.append("The confidence interval lies entirely below zero.")
            verdict = ProfitabilityVerdict.NEGATIVE_PERFORMANCE
        reasoning.append(
            "This is a normal-approximation interval over a still-small sample for a trading system -- "
            "treat it as directional evidence, not proof, and never as a guarantee of future performance."
        )

    return ProfitabilityReport(
        sample_size=n, win_rate=win_rate, win_rate_ci_low=win_ci_low, win_rate_ci_high=win_ci_high,
        average_win=average_win, average_loss=average_loss, expectancy=expectancy, profit_factor=profit_factor,
        max_drawdown=max_dd, return_volatility=volatility,
        mean_return_ci_low=mean_ci[0] if mean_ci else None, mean_return_ci_high=mean_ci[1] if mean_ci else None,
        verdict=verdict, reasoning=reasoning,
    )


def compute_sector_performance(items: list["EvaluatedPrediction"]) -> list[SectorPerformance]:
    from learning.analysis import _resolution_stats, _resolved_returns

    groups: dict[str, list] = {}
    for item in items:
        sector = "Unknown"
        if item.decision is not None and item.decision.research_evidence is not None and item.decision.research_evidence.sector is not None:
            sector = item.decision.research_evidence.sector.sector or "Unknown"
        groups.setdefault(sector, []).append(item)

    result = []
    for sector, group in groups.items():
        returns = _resolved_returns(group)
        win_rate, average_return, _ = _resolution_stats(returns)
        result.append(SectorPerformance(sector=sector, total=len(group), resolved=len(returns), win_rate=win_rate, average_return=average_return))
    return sorted(result, key=lambda s: s.sector)
