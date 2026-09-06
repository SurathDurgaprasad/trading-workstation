# Pullback Continuation — Full Evaluation (Strategy Edge Discovery, Phase B)

Mission: "STRATEGY EDGE DISCOVERY — CONTROLLED RESEARCH ONLY," Phase B,
first entry hypothesis (mission's own "H_ENTRY_001 Pullback
Continuation"; corresponds to `strategy/hypothesis_registry.py`'s
existing `H_ENTRY_003`). `TrendMomentumBaseline` remains untouched;
`PullbackContinuationStrategy` (`strategy/pullback_continuation.py`) is
a new, independent `Strategy` implementation, plugged directly into the
unmodified `backtesting.engine.run_backtest`.

Real, cached 41-symbol universe (32 NSE, 9 US), 5 years daily bars, 0
symbols failed to fetch — the same universe and data used for every
other result in this session.

## Result: INSUFFICIENT_DATA — the rule is too restrictive to test

| Split | Trades | Verdict |
|---|---|---|
| Development | 14 | (below 30-trade floor) |
| Validation | 10 | (below 30-trade floor) |
| Out-of-sample | 5 | (below 30-trade floor) |
| **Total (pooled)** | **29** | still below 30 even pooled across all three splits |

**Base promotion evaluation: INSUFFICIENT_DATA.** "development,
validation, out_of_sample split(s) have fewer than 30 trades — nothing
can be concluded, positive or negative, until more data accumulates."
This is not a close call: the ENTIRE universe over 5 years produced 29
total trade opportunities under this rule, fewer than even one split's
own minimum sample floor.

**Why so few**: the entry condition is a five-way AND (uptrend,
net-bullish momentum, RSI14 ≥ 55 exactly two bars before entry, RSI14
in a narrow [40, 55] band on the entry bar itself, and a same-day
resumption close) — a considerably tighter filter than
`TrendMomentumBaseline`'s own three-way AND. The RSI-band-two-bars-ago
condition in particular requires a specific short-term shape (strength,
then cooling, then resumption) that only rarely materializes exactly at
that 2-bar cadence across daily bars.

## Everything else measured (context, not a verdict — the sample is too small for one)

Every downstream metric was still computed for completeness and honesty
(the mission's own "never silently discard a failed experiment" rule),
but **none of it should be read as evidence of an edge** — a 29-trade
sample cannot support one:

- Walk-forward: 6 folds, 2–9 trades each, every fold `INSUFFICIENT_DATA`.
- Regime: largest bucket (TRENDING_UP+NORMAL_VOLATILITY) has only 17
  trades — every bucket `INSUFFICIENT_DATA`.
- Units-corrected buy-and-hold comparison: candidate average total
  return +0.09% vs buy-and-hold +18.58% — decisively behind, though
  with only 29 trades total this reflects the strategy sitting in cash
  almost the entire 5-year period (uninvested time is a large part of
  why buy-and-hold's own continuous exposure dominates), not
  necessarily a per-trade quality problem.
- Random baseline: candidate pooled per-trade mean +0.69% vs random
  average +0.34%, 36.0% of 100 iterations at least as good — a
  directionally favorable point estimate, but from 29 trades this is
  noise, not a finding.
- Beats the frozen baseline's own per-trade mean (+0.69% vs −0.62%) —
  same caveat: not statistically meaningful at this sample size.
- NSE-cost-model sensitivity: verdict unchanged (`INSUFFICIENT_DATA`
  either way — the sample size problem dominates regardless of cost
  assumptions).
- Multiple-testing correction: moot — no split had enough data for an
  uncorrected verdict to begin with.

## Adversarial self-review

- **Insufficient sample size IS the finding here**, not a caveat on top
  of one — stated as the headline result, not buried.
- **Overfitting / parameter snooping**: none — the rule's five
  conditions and specific thresholds (RSI 55/40/55 bands, 2-bar
  lookback) were fixed BEFORE this run, not tuned against these 29
  trades' own outcome. They were also not tuned against any PRIOR
  result either (this is this rule's first real-data test).
- **Multiple testing / data mining risk going forward**: the mission's
  own explicit instruction applies directly here — loosening these
  thresholds and re-running until the trade count clears 30 would be
  exactly the "repeatedly adjust until profitable" anti-pattern the
  Experiment Discipline section forbids. That temptation is noted and
  deliberately not acted on.
- **Selection bias**: none — Pullback Continuation was the mission's
  own explicitly named first priority, not cherry-picked after seeing
  early results.

## Experiment registration

Registered as `H_ENTRY_003` (existing registry ID; this is the first
real test of that hypothesis) — experiment
`c45b9371-6e7e-41ad-87f0-35f1921ce17e`, manifest_hash
`0917622cd55969d2`, in `data/experiment_registry.db` (gitignored; this
document is the durable record).

## Verdict: does not demonstrate an edge, and cannot be evaluated further as designed

Per the mission's own allowed conclusions, this hypothesis is
**INCONCLUSIVE** (`strategy/hypothesis_registry.py`'s own definition —
"insufficient... sample size... to confidently support or reject" is an
exact match). It is not evidence against the underlying pullback idea;
it is evidence that THIS specific, five-condition implementation of it
fires too rarely to be tested on the available data. Per the mission's
explicit instruction, the correct response is NOT to loosen the rule
and re-run until it clears the sample floor — that would be exactly the
prohibited "adjust until profitable" pattern. The rule, as specified,
stops here.

## This triggers the mission's own stop condition

The mission states explicitly: "If H_EXIT_002 and the first entry
hypotheses fail: DO NOT KEEP RANDOMLY ADDING INDICATORS. Stop and
report: NO DEMONSTRATED EDGE." H_EXIT_002 was fully evaluated and
concluded INCONCLUSIVE, not promoted
(`docs/H_EXIT_002_FULL_EVALUATION.md`). The first entry hypothesis
(Pullback Continuation) has now also been fully evaluated and cannot
even be measured with confidence. Per this explicit instruction,
further entry hypotheses (Regime-Conditioned Strategy, Breakout
Quality) are NOT implemented — doing so now, immediately after two
consecutive non-promotable results, would risk exactly the pattern the
mission warns against. This session proceeds directly to the mission's
mandated Final Output instead.
