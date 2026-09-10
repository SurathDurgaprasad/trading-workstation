"""H_MEANREV_008 (docs/research/H_MEANREV_008_RISK_CHARACTERIZATION_
PREREGISTRATION.md, frozen design, committed before this module): does
a bucket's larger mean forward return come with proportionally or
disproportionately worse downside/tail risk?

`quant_research.market_behavior.summarize_forward_returns` already
reports mean/median/win_rate/std_dev/CI/p5/p95 -- pure measurement,
no I/O, no look-ahead of its own (the caller already decided which
returns belong in the list). This module adds the missing
distributional/downside statistics the risk-characterization question
needs, computed the same way, over the same kind of return list,
without touching or duplicating anything `summarize_forward_returns`
already computes.

Standard, well-understood, sample-size-appropriate metrics only -- no
"sophisticated" risk statistics introduced for appearance.
"""

from dataclasses import dataclass

import pandas as pd

_MIN_OBSERVATIONS_FOR_EXPECTED_SHORTFALL = 400
"""expected_shortfall_5pct is the mean of the worst 5% of observations
-- below this many total observations, that slice itself has fewer
than 20 points, too few for a stable tail-mean estimate. Reported as
None (never fabricated) below this floor, matching this project's own
INSUFFICIENT_DATA discipline elsewhere."""


@dataclass(frozen=True)
class ForwardReturnRiskSummary:
    """Distributional/downside statistics for one list of forward
    returns -- a companion to (not a replacement for)
    quant_research.market_behavior.ForwardReturnSummary, which already
    covers mean/median/win_rate/std_dev/CI/p5/p95."""

    condition: str
    market: str
    horizon_bars: int
    sample_size: int
    p10: float | None
    p25: float | None
    p75: float | None
    p90: float | None
    minimum: float | None
    maximum: float | None
    downside_deviation: float | None
    """Standard deviation computed over NEGATIVE returns only (a
    standard semi-deviation measure) -- None if sample_size == 0 or no
    observation is negative."""
    expected_shortfall_5pct: float | None
    """Mean of the worst 5% of observations (a standard tail-mean
    measure) -- None below _MIN_OBSERVATIONS_FOR_EXPECTED_SHORTFALL,
    never estimated from too few points."""
    loss_given_loss: float | None
    """Mean return conditional on return < 0 -- None if no observation
    is negative."""
    gain_given_win: float | None
    """Mean return conditional on return > 0 -- None if no observation
    is positive."""
    mean_to_downside_deviation: float | None
    """mean_return / downside_deviation -- a simple, clearly-labeled
    descriptive ratio. Explicitly NOT evidence of a tradeable edge on
    its own; always reported alongside the full distribution and n,
    never in isolation. None if downside_deviation is None or zero, or
    if mean_return is None."""


def summarize_forward_return_risk(
    returns: list[float], *, condition: str, market: str, horizon_bars: int,
) -> ForwardReturnRiskSummary:
    """Pure function: no I/O, no look-ahead of its own -- the caller
    already decided which returns belong in this list, the identical
    posture quant_research.market_behavior.summarize_forward_returns
    already uses."""
    n = len(returns)
    if n == 0:
        return ForwardReturnRiskSummary(
            condition=condition, market=market, horizon_bars=horizon_bars, sample_size=0,
            p10=None, p25=None, p75=None, p90=None, minimum=None, maximum=None,
            downside_deviation=None, expected_shortfall_5pct=None,
            loss_given_loss=None, gain_given_win=None, mean_to_downside_deviation=None,
        )

    series = pd.Series(returns)
    mean_return = float(series.mean())

    p10 = float(series.quantile(0.10))
    p25 = float(series.quantile(0.25))
    p75 = float(series.quantile(0.75))
    p90 = float(series.quantile(0.90))
    minimum = float(series.min())
    maximum = float(series.max())

    losses = series[series < 0]
    gains = series[series > 0]
    downside_deviation = float(losses.std(ddof=1)) if len(losses) >= 2 else None
    loss_given_loss = float(losses.mean()) if len(losses) > 0 else None
    gain_given_win = float(gains.mean()) if len(gains) > 0 else None

    expected_shortfall_5pct = None
    if n >= _MIN_OBSERVATIONS_FOR_EXPECTED_SHORTFALL:
        tail_cutoff = series.quantile(0.05)
        tail = series[series <= tail_cutoff]
        if len(tail) > 0:
            expected_shortfall_5pct = float(tail.mean())

    mean_to_downside_deviation = None
    if downside_deviation is not None and downside_deviation != 0:
        mean_to_downside_deviation = mean_return / downside_deviation

    return ForwardReturnRiskSummary(
        condition=condition, market=market, horizon_bars=horizon_bars, sample_size=n,
        p10=p10, p25=p25, p75=p75, p90=p90, minimum=minimum, maximum=maximum,
        downside_deviation=downside_deviation, expected_shortfall_5pct=expected_shortfall_5pct,
        loss_given_loss=loss_given_loss, gain_given_win=gain_given_win,
        mean_to_downside_deviation=mean_to_downside_deviation,
    )
