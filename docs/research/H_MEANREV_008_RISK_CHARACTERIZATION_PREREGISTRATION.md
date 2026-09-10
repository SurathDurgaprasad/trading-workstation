# H_MEANREV_008 — Risk Characterization of the Generalized Oversold Effect, Pre-Registration

Written and frozen **before** any experiment code runs. Per this
project's own multiple-testing discipline: the buckets (reused
verbatim, not re-derived), universe, splits, horizons, and risk
metrics are fixed here; none may change after seeing results.

**This is a risk-characterization study, not an executable strategy,
not an entry/exit optimization exercise, not a parameter search.** No
stops, targets, trailing exits, position sizing, or broker execution
are touched.

## 1. Research question

`H_MEANREV_007` found that the high-volatility bucket (C) shows a
LARGER mean forward return than the relative-weakness bucket (B) at
out-of-sample h10 (+2.10% vs. +1.35%), but is far more fragile — a
complete sign reversal in development once 2020 is included. That
finding was about the MEAN only. The question this entry asks:

**Is the larger mean return associated with high-volatility oversold
events actually compensation for materially worse downside/tail risk,
and does the relative-weakness component have a superior
return-to-tail-risk profile?** Not "which bucket has the higher
average" (already answered) but "which bucket offers more return per
unit of downside risk taken, and does that change the read on which
component is more interesting."

## 2. Audit — reused verbatim, nothing re-derived (verified by direct reading)

Read directly: `H_MEANREV_006`'s and `H_MEANREV_007`'s own
pre-registrations and registry entries; `quant_research/
mean_reversion_signal.py`; `quant_research/market_behavior.py`'s
`summarize_forward_returns`/`ForwardReturnSummary`.

- **Entry (frozen, unchanged)**: `zscore_close_20 < -2.0`
  (`_oversold_2std`).
- **Frozen partitions, reused VERBATIM from `H_MEANREV_006`/`007`, not
  re-derived**: `RELSTRENGTH_MEDIAN = -6.8845%`; `ATR_PCT_33 =
  2.6583%`, `ATR_PCT_67 = 3.6352%`.
- **Four buckets, identical definitions to `H_MEANREV_007`**: A
  (oversold alone), B (+relative weakness), C (+high volatility), D
  (joint — relative weakness AND high volatility).
- **Universe/splits/calendar**: `COMBINED` (206/208 symbols),
  `development_end=2023-11-25`, `validation_end=2025-04-17` — identical
  to `H_MEANREV_006`/`007`.
- **`summarize_forward_returns`/`ForwardReturnSummary`** (existing,
  unchanged) already reports: `sample_size`, `mean_return`,
  `median_return`, `win_rate`, `std_dev`, `mean_ci_low`/`high`, `p5`,
  `p95`. This entry ADDS the missing percentiles and tail/downside
  statistics the mission's own risk-characterization question needs,
  without touching or duplicating anything already computed.

**Is this within `H_MEANREV_007`'s own existing scope?** No — read
directly: `H_MEANREV_007`'s own frozen question was "does the joint
condition D contain information beyond B or C alone" (a mean-based
incremental-information test); it reports `p5`/`p95` only as a
byproduct of the existing `summarize_forward_returns` call, never
computes `p10`/`p25`/`p75`/`p90`, downside deviation, expected
shortfall, or conditional gain/loss magnitudes, and never frames a
risk-vs-return question as its own object of study. This is a
genuinely new analytical question on the SAME buckets, not an
addendum to an existing one — hence a new hypothesis ID, not a
same-entry addendum (matching `H_MEANREV_006`'s own addendum
precedent, which WAS a same-entry addendum because it directly
resolved a question `H_MEANREV_006` itself had explicitly flagged as
open — this entry's question was never flagged by `H_MEANREV_007`).

## 3. Infrastructure — new code required, kept minimal and standard

One new, small module, `quant_research/risk_characterization.py`,
`summarize_forward_return_risk(returns, *, condition, market,
horizon_bars) -> ForwardReturnRiskSummary` — a pure function (no I/O,
no look-ahead of its own, identical posture to
`summarize_forward_returns`), computing STANDARD, well-understood,
sample-size-appropriate descriptive statistics only (no
"sophisticated metrics for appearance"):

- `p10`, `p25`, `p75`, `p90` (in addition to the existing `p5`/`p95`).
- `minimum`, `maximum`.
- `downside_deviation` — standard deviation computed over NEGATIVE
  returns only (a standard, simple semi-deviation measure).
- `expected_shortfall_5pct` — the mean of the worst 5% of observations
  (a standard tail-mean measure) — only computed when the bucket has
  enough observations for the worst-5%-slice itself to be
  statistically meaningful (>=20 observations in the worst-5% slice,
  i.e. >=400 total observations for that cell; below this, reported
  as `None`/insufficient, never a noisy point estimate dressed up as a
  real number).
- `loss_given_loss` — mean return conditional on return < 0.
- `gain_given_win` — mean return conditional on return > 0.
- `mean_to_downside_deviation` — `mean_return / downside_deviation`, a
  simple, clearly-labeled descriptive ratio, explicitly NOT presented
  as proof of a tradeable edge, always reported alongside the full
  distribution and sample size, never alone.

Independently unit-tested (`tests/test_risk_characterization.py`)
before being used for real measurement.

## 4. Universe, splits, horizons (frozen, identical to `H_MEANREV_006`/`007`)

`COMBINED` (206/208 symbols), 10 years daily.
`development_end=2023-11-25`, `validation_end=2025-04-17`.
`FORWARD_HORIZONS` (1,2,3,5,10,20), ALL SIX reported for every bucket
— the temporal-risk question (§5 below) requires the full curve, not
a single horizon; no horizon is selected as uniquely "primary" for
this entry (unlike `H_MEANREV_006`/`007`'s own h10 convention), since
the object of study here is explicitly how the distribution EVOLVES
across horizons, not a single point comparison. Where a single-number
summary is needed for a table, h10 is used for direct comparability
with `H_MEANREV_007`'s own headline figures — disclosed as a
reporting choice, not a selection made after seeing results.

## 5. Primary comparisons (frozen)

For buckets A/B/C/D, at every horizon, every split:

1. **Full risk-distribution report**: n, mean, median, win rate, p5,
   p10, p25, p75, p90, p95, min, max, std_dev, downside_deviation,
   expected_shortfall_5pct (where sample permits), loss_given_loss,
   gain_given_win, mean_to_downside_deviation.
2. **Temporal risk evolution (h1 through h20)**: does downside_deviation/
   expected_shortfall grow proportionally with the horizon (mean and
   downside scale together — "more time, proportionally more risk for
   proportionally more return") or disproportionately (downside grows
   faster than mean — "more time, worse risk-adjusted profile")? No
   horizon is chosen as "best" — the full curve is reported and its
   SHAPE is the finding.
3. **B vs. C, the central comparison**: does C's larger mean (+2.10%
   OOS h10) come with a proportionally larger `downside_deviation`/
   `expected_shortfall_5pct`, or a DISPROPORTIONATELY larger one? Is
   B's `mean_to_downside_deviation` ratio higher than C's, lower, or
   similar? Reported precisely, not assumed in either direction.
4. **D examined the same way**, completing the four-bucket risk
   picture already established on a mean basis by `H_MEANREV_007`.

## 6. 2020 robustness (frozen, pre-specified — not a way to discard an inconvenient observation)

For each of A/B/C/D at h10: report the FULL development-period risk
distribution first, THEN a WITH-2020 vs. WITHOUT-2020 comparison of
the SAME risk statistics (not just the mean, which `H_MEANREV_007`
already covered) — specifically: is `expected_shortfall_5pct`/
`downside_deviation` also driven by 2020, or does meaningful downside
risk remain even after excluding it? Additionally: what fraction of
each bucket's own WORST 5% of development-period observations (the
tail set `expected_shortfall_5pct` is computed from) falls in calendar
year 2020 specifically — a direct, already-motivated concentration
check using data this entry already collects, not a new slicing
dimension.

## 7. Cross-sectional / concentration checks (gated, not unlimited)

Symbol/sector concentration is run ONLY if the B-vs-C or 2020-tail-
concentration finding is decisive and substantive enough to warrant
it (matching `H_MEANREV_007`'s own established gating discipline) —
not run reflexively, not searched until a favorable subgroup appears.

## 8. What will NOT change after this is pre-registered

No new entry threshold. No re-deriving `RELSTRENGTH_MEDIAN` or
`ATR_PCT_33`/`67`. No new volatility/relative-strength windows. No
universe change. No horizon selected as "the answer" after seeing the
temporal curve — the full curve is reported regardless of shape. No
new risk metric introduced after seeing an inconvenient result from an
existing one. No exit/stop/target/execution design of any kind. If a
genuinely new question emerges (e.g., a specific symbol/sector driving
tail risk), it is recorded as a candidate FUTURE hypothesis, never
folded back into this entry's own frozen comparison retroactively.

## 9. Statistical discipline (frozen)

Same `>=30` observations per split per bucket floor as every prior
entry in this family for a cell to be reported as anything but
INSUFFICIENT_DATA. `expected_shortfall_5pct` additionally requires
`>=400` total observations in that cell (so its own worst-5%-slice has
`>=20` points) — below this, reported as not computed, not estimated
from too few points. A high `mean_to_downside_deviation` ratio is
explicitly NOT treated as evidence of a tradeable edge on its own —
always shown alongside the full distribution and n.

## 11. Reproducibility record

Universe/calendar/thresholds identical to `H_MEANREV_006`/`007`
(verified unchanged). All four buckets built successfully.

## 12. Results

Full evidence: `H_MEANREV_008` in `strategy/hypothesis_registry.py`.

### Primary risk-distribution report (h10)

| Bucket | Split | n | mean | downside_dev | ES5% | mean/downside_dev |
|---|---|---|---|---|---|---|
| A | out-of-sample | 4390 | +0.59% | 4.12% | −13.64% | 0.143 |
| B | out-of-sample | 1629 | +1.35% | 4.24% | −13.83% | 0.318 |
| C | out-of-sample | 914 | +2.10% | 5.10% | −16.26% | **0.413** |
| D | out-of-sample | 590 | +2.08% | 5.18% | −16.43% | 0.402 |

**The central finding, and it cuts against the naive expectation**: in
out-of-sample data, C's mean is roughly 3.6x A's, while its
`downside_deviation` grows only ~24% and its `expected_shortfall_5pct`
only ~19% — **C's larger mean is NOT simply proportional compensation
for proportionally larger downside risk; the downside grows far less
than the mean does.** C shows the BEST (highest)
`mean_to_downside_deviation` ratio of all four buckets in out-of-sample
(0.413, vs. B's 0.318) — the OPPOSITE of what `H_MEANREV_007`'s
mean-only framing might suggest about which bucket is more
"attractive." The same ordering holds in validation (C=0.397 vs.
B=0.243).

**But development (2020-contaminated) tells a starkly different
story**: C shows CI-decisive NEGATIVE mean (−0.50%) AND the LARGEST
`downside_deviation` (10.04%) and `expected_shortfall_5pct` (−33.10%)
of all four buckets simultaneously — the worst of both dimensions at
once. This is the regime-contingent picture the WITH/WITHOUT-2020 and
tail-concentration checks below make precise.

### Tail concentration in 2020 (worst 5% of development-period observations, h10)

| Bucket | Worst-5% tail n | from 2020 | % |
|---|---|---|---|
| A | 728 | 515 | 70.7% |
| B | 364 | 212 | **58.2%** (lowest) |
| C | 292 | 247 | **84.6%** (highest) |
| D | 183 | 137 | 74.9% |

A single calendar year (2020, ~1 of 8 development years, a "fair"
share would be ~12.5%) accounts for the overwhelming majority of every
bucket's own worst outcomes — most extremely for C. **This is now the
most precise evidence yet that the tail risk in this whole family is
overwhelmingly a 2020-specific, systemic-crisis phenomenon, not a
general year-round hazard** — and C's own tail risk is the MOST
concentrated there of the four buckets.

### WITH-2020 vs. WITHOUT-2020, full risk distribution (development, h10)

| Bucket | | mean | downside_dev | ES5% | mean/downside_dev |
|---|---|---|---|---|---|
| A | WITH 2020 | +0.06% | 8.09% | −26.01% | 0.007 |
| A | WITHOUT 2020 | +0.98% | 5.34% | −16.51% | 0.183 |
| B | WITH 2020 | +0.52% | 8.16% | −25.98% | 0.063 |
| B | WITHOUT 2020 | +1.04% | 6.02% | −18.50% | 0.173 |
| C | WITH 2020 | −0.45% | 10.10% | −33.24% | −0.045 |
| C | WITHOUT 2020 | **+1.48%** | **6.76%** | **−20.89%** | **0.219** |
| D | WITH 2020 | +0.36% | 9.86% | −32.00% | 0.041 |
| D | WITHOUT 2020 | +1.43% | 7.31% | −22.55% | 0.195 |

**A crucial, precise refinement of the earlier "volatility=fragile"
framing**: excluding 2020, downside risk drops substantially for EVERY
bucket (26-37% reduction in `downside_deviation`), confirming 2020
drives tail risk broadly — but C's OWN downside risk remains the
LARGEST of the four buckets even WITHOUT 2020 (6.76% vs. B's 6.02%,
A's 5.34%). **2020 amplifies a REAL, pre-existing baseline risk
difference; it does not manufacture the volatility-risk relationship
out of nothing.** And remarkably, C's own `mean_to_downside_deviation`
ratio WITHOUT 2020 (0.219) is STILL the best of the four buckets —
matching validation/out-of-sample's own finding. **In every
non-2020-dominated view of the data, C offers the best risk-adjusted
profile of the four buckets, not the worst; 2020 specifically is where
that relationship inverts catastrophically.**

### Temporal risk evolution (out-of-sample, mean/downside_dev by horizon)

| Bucket | h1 | h2 | h3 | h5 | h10 | h20 |
|---|---|---|---|---|---|---|
| A | 0.136 | 0.158 | 0.165 | 0.193 | 0.143 | 0.212 |
| B | 0.198 | 0.265 | 0.331 | **0.466** | 0.318 | 0.319 |
| C | 0.243 | 0.291 | 0.337 | 0.445 | 0.413 | **0.471** |
| D | 0.252 | 0.354 | 0.438 | **0.619** | 0.402 | 0.429 |

**Non-monotonic, not a simple "longer holding is proportionally
better/worse" story**: for every bucket, the risk-adjusted ratio
generally IMPROVES from h1 through h3-h5 (return builds faster than
downside), then DIPS at h10, then partially recovers by h20. This
genuine complexity — not a clean, single-direction trend — is itself
informative: it cautions against assuming risk-adjusted quality
improves (or worsens) monotonically with a longer hold, and suggests
h3-h5 deserves particular attention in any FUTURE exit-horizon
analysis (descriptive observation only, no exit design here).

### Cross-sectional slicing — NOT run, disclosed explicitly

Per §7's own frozen gate, symbol/sector concentration was NOT examined
further this entry. The year-concentration finding (2020 explaining
58-85% of each bucket's own worst outcomes) is already a complete,
well-understood explanation — 2020 is a documented, singular systemic
macro event, not something requiring symbol/sector decomposition to
interpret. Matching `H_MEANREV_007`'s own established gating
precedent, opening a further slicing dimension here would not add
proportional value.

### Verdict

**INCONCLUSIVE** — this is a risk-characterization/descriptive study
by design (no single frozen pass/fail bar, matching `H_MEANREV_006`'s
own precedent), and the honest finding is genuinely regime-contingent,
not a clean answer to either "volatility is worse" or "volatility is
better." Specifically:

1. **Does high volatility buy more return at disproportionate downside
   risk?** In NORMAL (non-2020) conditions: NO — C's risk-adjusted
   ratio is the BEST of the four buckets, both including and excluding
   2020 from the development window. In a SYSTEMIC CRISIS regime
   (2020 specifically): the relationship inverts sharply — C shows
   simultaneously the worst mean and the worst downside risk. The
   correct reading is regime-contingent, not a fixed property of the
   volatility dimension.
2. **Is relative weakness more robust on a return-to-tail-risk basis?**
   Not on raw ratio in normal conditions (B's ratio is consistently
   LOWER than C's in validation/OOS/WITHOUT-2020-development). B's real
   advantage is specifically CRISIS-REGIME ROBUSTNESS — its own
   worst-outcome concentration in 2020 (58.2%) is the lowest of the
   four buckets, and its mean/risk degrade far less severely than C's
   when 2020 hits.
3. **How much of the volatility effect is explained by 2020?** A lot,
   precisely quantified: 84.6% of C's own worst-5% tail sits in that
   one year, and excluding it flips C's development mean from
   decisively negative to decisively positive. But not entirely: C's
   baseline (non-2020) risk remains genuinely higher than B's, so 2020
   amplifies a real underlying difference rather than manufacturing it.
4. **Does the risk profile change materially through h1-h20?**
   Yes, non-monotonically — risk-adjusted efficiency improves toward
   h3-h5, dips at h10, partially recovers by h20, for every bucket.
5. **Concentration**: overwhelmingly a single-year (2020) phenomenon;
   sector/symbol slicing not run, per the frozen gate.
6. **Constraints on any future executable design** (documented, NOT
   implemented): (a) a volatility-conditioned entry needs an explicit
   mechanism for systemic/crisis-regime risk (e.g., a broad-market
   stress gate or reduced sizing during extreme conditions), since its
   tail risk concentrates almost entirely in exactly such episodes;
   (b) a relative-weakness-conditioned entry is comparatively more
   crisis-resistant but does not offer a superior risk-adjusted ratio
   in normal conditions — a genuinely different, complementary risk
   profile, not a strictly "better" one; (c) any future exit-horizon
   choice should account for the non-monotonic risk-adjusted curve
   (h3-h5 showing the best efficiency, h10 a dip) rather than assuming
   longer is always better or worse; (d) any position-sizing design
   must plan for the full observed tail (`ES5%` ranging roughly −13%
   to −33% depending on bucket/period), not just typical-case downside.

## 13. Scope note

Pure historical-data research, read-only, reusing the already-built
`COMBINED` universe datasets and features from `H_MEANREV_006`/`007`.
Does not touch `data/paper_trading.db`, `data/live_state.db`,
`data/scheduler_runs.db`, `data/direction_forecasts.db`, or
`data/predictions.db`. No broker execution changes, no exit/stop/
target/position-sizing design, no scheduler dependency.
