# Research methodology

How every hypothesis in this project's 69-entry research history was tested, and why
negative results are preserved rather than discarded. This document describes the
*method*; see [`RESEARCH_RESULTS.md`](RESEARCH_RESULTS.md) for the outcomes it
produced.

## Why negative results are retained

A research registry that only shows winners is not evidence of a working process — it's
survivorship bias in documentation form. `strategy/hypothesis_registry.py` records
**every** hypothesis considered, with a real `evidence` field that must cite something
actually measured, never a plausible-sounding guess. A hypothesis's status
(`OPEN`/`SUPPORTED`/`REJECTED`/`INCONCLUSIVE`) is set only after a real experiment ran.
This is the single most load-bearing convention in the project: it is what makes "0
promoted out of 69" a *credible* claim rather than an assertion.

## Preregistration

Every hypothesis is written down — description, rationale, expected effect, dataset
restrictions, exact experiment design, success criteria, and failure criteria — **before
its result is inspected**. This blocks the most common form of quiet research bias:
adjusting a threshold, a lookback window, or a universe *after* seeing what makes the
result look better. Preregistrations for the more complex hypotheses additionally live
as standalone documents under [`research/`](research/) (e.g.
`H_MEANREV_010_EXECUTION_STRUCTURE_PREREGISTRATION.md`), written before that
hypothesis's own experiment ran.

## Development / validation / out-of-sample splits

`backtesting/splits.py::split_periods` applies a fixed, non-data-dependent 60/20/20
chronological split to every backtest — development, validation, out-of-sample. The
split boundaries are a property of the *time range*, never chosen to flatter a result.
A verdict requires evidence from all three periods; a single strong development-period
result, on its own, proves nothing (`strategy/promotion_gate.py`'s mechanical logic: any
period below the minimum sample floor is `INSUFFICIENT_DATA`; any period confidently
negative disqualifies regardless of the others; only all three periods confidently
positive reaches `PROMOTED`).

## Leakage prevention

Every experiment documents, before running, how it rules out:

- **Look-ahead**: signal-generating features are strictly backward-looking (rolling
  windows, `pct_change(N)`, causal indicator computation in `market/indicators.py`).
  Forward-return *label* columns (`fwd_return_h = close.shift(-h)/close - 1`) are the
  one deliberate exception — clearly named, and never fed back into a signal.
- **Same-date cross-sectional leakage**: cross-sectional scores (rank, z-score) are
  computed using only that same date's cross-section across symbols, never a future
  date's values (`quant_research/cross_sectional.py`,
  `quant_research/cross_sectional_relative.py`).
- **Event-timestamp leakage**: for corporate-event studies, the "information timestamp"
  is scrutinized explicitly — e.g. the final edge-discovery mission's `H_EVENT_002`
  disclosed, rather than hid, that its 5-trading-day pre-event entry point relies on an
  *inferred* (not directly verified) regulatory disclosure requirement, not a directly
  observed announcement timestamp. Where a leakage risk could not be ruled out, the
  hypothesis is rejected on that basis alone, independent of what the price pattern
  showed.
- **Purge/embargo**: applied where overlapping labels could otherwise let information
  from one trade's outcome window bleed into an adjacent one's feature window, in the
  multi-testing/embargo passes described in the continuous red-team reports.

## Transaction costs and slippage

`backtesting/costs.py::CostModel` — a realistic NSE intraday preset
(`india_nse_intraday_2026()`) applies ₹20 flat brokerage per fill, NSE exchange fees
(0.375%), STT (2.5%), and 5–10 bps entry/exit slippage, for a realistic round-trip cost
of roughly 0.21% before the flat brokerage. Every hypothesis that reaches an executable
design stage applies this cost model; several hypotheses (e.g. `H_MEANREV_009`) show a
real gross edge that is entirely destroyed once realistic costs are applied — the fixed
brokerage fee dominates at the position sizes a real retail account would use. One
disclosed gap: `H_MEANREV_001` used the generic, non-NSE-specific default `CostModel()`
rather than the NSE preset — found and disclosed during the 2026-09-23 remediation
pass; the correction only pushes an already-rejected result more negative, so no rerun
was required.

## Portfolio realism

A signal-level positive return is not evidence a retail account could have captured it.
Where a hypothesis reached a serious executable-design stage, it was tested under fixed
account size, maximum concurrent positions, realistic position-quantity rounding, and
capital allocation across overlapping trades
(`quant_research/mean_reversion_portfolio.py`, `quant_research/cross_sectional_portfolio.py`).
This step is what killed the two strongest raw signals in the project's history
(`H_XSECT_001`, `H_MEANREV_014`) — both measured a real effect, and both failed once
realistic portfolio construction (signal clustering, capacity limits, stop-dominated
loss distributions) was applied.

## Statistical significance and multiple testing

Every verdict is keyed to a 95% confidence interval on the mean per-trade or per-bucket
return (`learning/profitability.py::compute_profitability_report_from_returns`), not a
bare win-rate percentage or a point estimate. A result whose confidence interval
straddles zero is `STATISTICALLY_MEANINGLESS`, regardless of how large the point
estimate looks. `strategy/multiple_testing.py` applies a Bonferroni-style correction
(a wider z-score for the family of simultaneous tests) when a research program runs
several related hypotheses against the same dataset — e.g. the derivatives program's
`family_size=4` correction, and the final edge-discovery mission's own 5-hypothesis
correction (§13 of `EDGE_DISCOVERY_FINAL_REPORT.md`). A result that only survives
*before* this correction is not treated as promoted.

## Survivorship and point-in-time universe

Most of the registry applies today's current F&O-eligible symbol universe uniformly
across a historical window — a disclosed, unresolved limitation
(`docs/MASTER_KNOWN_ISSUES.md`, item R1). One research chain
(`H_MEANREV_010`→`H_MEANREV_014`) built and applied a genuine point-in-time universe
from real, dated NSE F&O bhavcopy archives (350 distinct symbols ever eligible across a
10-year window, including several companies that later defaulted or delisted — DHFL, JP
Associates, Reliance Capital). Applying it flipped a previously-inconclusive
development-period result to a clear, CI-decisive negative, exposing real survivorship
bias in the uncorrected version.

## Failure criteria and stopping rules

Every preregistration states its own failure criteria in advance — not merely its
success criteria. A hypothesis is closed, not iterated on, when: required data does not
exist, leakage cannot be ruled out, out-of-sample fails, realistic costs destroy the
effect, portfolio sizing destroys the effect, the effect disappears across regimes or
eras, the multiple-testing correction destroys significance, or the result depends on a
single symbol, date range, or tiny sample. The project's own explicit rule, reused
verbatim across research missions: **do not generate another variant to rescue a failed
branch** — the purpose is discovery, not rescue. This is why, for example, the
mean-reversion family stopped at `H_MEANREV_014` rather than continuing to
`H_MEANREV_015` with a different parameter after `H_MEANREV_014` failed at the
portfolio-realism stage.

## Promotion criteria

`strategy/promotion_gate.py::evaluate_promotion` (and its stricter sibling,
`evaluate_promotion_comprehensive`, which additionally requires beating buy-and-hold, a
random-entry Monte Carlo baseline, and every walk-forward fold and regime bucket): a
hypothesis is `PROMOTED` only if development, validation, and out-of-sample periods are
**all three** confidently positive. Anything else — mixed signs, any period
confidently negative, any period below the sample floor — is `REJECTED`,
`INCONCLUSIVE`, or `NEGATIVE`. No hypothesis in this project's history has ever reached
`PROMOTED`.

## Adversarial review

After clusters of related hypotheses, a dedicated adversarial pass asks: did we
accidentally retest a closed family, did we optimize against validation, did
survivorship enter, was multiple testing understated, are costs realistic, is the
sample adequate, are we mistaking statistical significance for economic significance,
and — the hardest one to self-apply honestly — are we continuing because the evidence
is promising, or because we don't want to stop. See §14 of
[`EDGE_DISCOVERY_FINAL_REPORT.md`](EDGE_DISCOVERY_FINAL_REPORT.md) for a worked example
of this audit.
