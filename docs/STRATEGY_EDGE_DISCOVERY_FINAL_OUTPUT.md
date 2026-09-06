# Strategy Edge Discovery — Final Output

Mission: "STRATEGY EDGE DISCOVERY — CONTROLLED RESEARCH ONLY." Phase A
finished H_EXIT_002's full 12-step evaluation
(`docs/H_EXIT_002_FULL_EVALUATION.md`). Phase B tested the first
entry-side hypothesis, Pullback Continuation
(`docs/H_ENTRY_PULLBACK_EVALUATION.md`). Both concluded without a
promotable result, which — per the mission's own explicit instruction
("If H_EXIT_002 and the first entry hypotheses fail: DO NOT KEEP
RANDOMLY ADDING INDICATORS. Stop and report: NO DEMONSTRATED EDGE.")
— triggers the mission's stop condition. `strategy/baseline.py`
(`TrendMomentumBaseline`) remains untouched and frozen throughout this
entire mission; nothing here changes the live paper-trading strategy or
any risk control.

## Evidence table

Rows above the divider are this mission's own two full evaluations
(persisted in `data/experiment_registry.db` via
`strategy/experiment_store.py`, real experiment IDs shown). Rows below
are earlier-session results, included for completeness — these were
NOT re-run with walk-forward/regime analysis this mission, so those two
columns are marked "not run for this hypothesis" rather than implying
a result that doesn't exist.

| Hypothesis | Experiment ID | Trade Count (dev/val/oos) | Development | Validation | OOS | Walk-Forward | Regime Consistency | Random Comparison | Statistical Verdict | Promotion Status |
|---|---|---|---|---|---|---|---|---|---|---|
| **H_EXIT_002** — partial profit-take at +1R | `5dc42faf-1e09-4c38-9272-d18e3da57219` | 343 / 149 / 160 | +0.13% (MEANINGLESS) | +0.22% (MEANINGLESS) | +0.49% (MEANINGLESS) | 1 of 6 folds POSITIVE, 5 MEANINGLESS — not stationarity-consistent | No bucket NEGATIVE; dominant bucket improved from NEGATIVE (baseline) to MEANINGLESS | Beats random (16.0% of 100 iterations ≥ candidate) | **INCONCLUSIVE** | **NOT PROMOTED** |
| **H_ENTRY_003 / mission's "Pullback Continuation"** | `c45b9371-6e7e-41ad-87f0-35f1921ce17e` | 14 / 10 / 5 (29 total) | INSUFFICIENT_DATA | INSUFFICIENT_DATA | INSUFFICIENT_DATA | All 6 folds INSUFFICIENT_DATA (2–9 trades each) | All buckets INSUFFICIENT_DATA (largest: 17 trades) | Directionally favorable (36.0%) but n=29, not meaningful | **INSUFFICIENT_DATA** | **NOT PROMOTED** |
| — earlier-session results (context) — | | | | | | | | | | |
| H_EXIT_001 — breakeven stop at +1R | N/A (pre-registry) | 179 / 114 / 123 | -1.07% (NEGATIVE) | -0.56% (MEANINGLESS) | -0.65% (NEGATIVE) | not run for this hypothesis | not run for this hypothesis | not run for this hypothesis | REJECTED | NOT PROMOTED |
| H_EXIT_003 — ATR trailing stop | N/A (pre-registry) | 221 / 127 / 130 | -0.48% (NEGATIVE) | -0.67% (NEGATIVE) | -0.19% (MEANINGLESS) | not run for this hypothesis | not run for this hypothesis | not run for this hypothesis | REJECTED | NOT PROMOTED |
| H_EXIT_004 — 20-bar time-based exit | N/A (pre-registry) | 216 / 112 / 118 | -0.75% (NEGATIVE) | -0.54% (MEANINGLESS) | -0.36% (MEANINGLESS) | not run for this hypothesis | not run for this hypothesis | not run for this hypothesis | REJECTED | NOT PROMOTED |
| H_ENTRY_001 — trend-confirmation entry timing vs random | N/A (pre-registry) | pooled, 368 real trades | n/a (single-period Monte Carlo, not dev/val/oos) | — | — | not run | not run | 96.0% of 300 random iterations ≥ real strategy | SUPPORTED (negative finding: entry timing underperforms random) | N/A — a finding about the frozen baseline itself, not a promotion candidate |

**Reconciling with the base `evaluate_promotion()` verdict labels**:
H_EXIT_002's underlying dev/val/oos verdicts are all
`STATISTICALLY_MEANINGLESS` (point estimates positive, confidence
intervals touch zero) — the base evaluator reads three
`STATISTICALLY_MEANINGLESS` splits with all-positive point estimates as
`INCONCLUSIVE`, not `REJECTED`. H_ENTRY_003 (Pullback)'s splits are all
below the 30-trade floor — the base evaluator reads any split below
that floor as `INSUFFICIENT_DATA`, taking priority over every other
rule.

## Answers to the mission's own closing questions

### 1. Did any hypothesis show a demonstrated edge?

**No.** Two hypotheses were evaluated to the mission's full standard
this session and neither cleared the promotion bar. H_EXIT_002 showed a
real, consistent, non-degraded DIRECTIONAL improvement in per-trade
expectancy over the frozen baseline — the closest thing to a positive
signal found in this entire research program — but it does not reach
statistical significance in any split, is not consistent across
walk-forward folds (5 of 6 are noise), and — the most important
finding — does NOT translate into better total capital growth than the
baseline it was meant to improve on (−0.81% vs the baseline's own
−0.68%, both far behind buy-and-hold's +18.58%). Pullback Continuation
could not even be measured: 29 total trades over 5 years across 41
symbols is too restrictive a rule to test.

### 2. Is the evidence statistically meaningful?

**No, on both counts, for different reasons.** H_EXIT_002: every split
(development, validation, out-of-sample, and all 6 walk-forward folds
individually) has a confidence interval that touches zero, and a
Bonferroni multiple-testing correction (family_size=3) confirms no
split survives correction as positive. Pullback Continuation: the
sample size (29 trades total) is below this project's own
`MIN_SAMPLE_SIZE_FOR_A_VERDICT=30` floor even pooled across all three
splits — there is not enough data to say anything statistically,
positive or negative.

### 3. Would you trust either of these for paper trading?

**No.** Neither reaches this project's own `evaluate_promotion_comprehensive`
`PROMOTED` verdict, and the ₹20,000 paper-capital validation baseline
deserves the same rigor as real capital would — promoting either
candidate now would mean paper-trading on a coin flip dressed up as a
result. H_EXIT_002 additionally has a real, sobering counter-finding
(worse total capital growth than the baseline) that argues against it
even informally. Pullback Continuation simply has not been tested
enough to have an opinion about.

### 4. What remains hypothesis (genuinely untested)?

- **H_ENTRY_002 (Regime-Conditioned Strategy)** and **H_ENTRY_003 /
  mission's "Breakout Quality"** — never implemented, per the mission's
  own stop condition; not because they are believed to be worse ideas,
  but because implementing them immediately after two consecutive
  non-promotable results would risk exactly the "keep randomly adding
  indicators" pattern the mission explicitly forbids.
- **A looser or differently-shaped pullback rule** — this session's
  specific 5-condition, 2-bar-RSI-shape implementation produced too few
  trades to test; a different pullback definition might fire often
  enough to be measurable, but per the mission's own instruction this
  was deliberately NOT attempted by iterating on the same data.
- **Every regime bucket without adequate sample size** in either
  evaluation (5 of 10 candidate-H_EXIT_002 buckets; all 4
  candidate-Pullback buckets) — genuinely unmeasured, not proven
  anything.
- **Trade-dependence correction** — flagged again this session (see
  both evaluation docs' adversarial reviews): every confidence interval
  computed throughout this entire project treats trades as independent
  draws, which they are not (multiple trades per symbol share
  underlying price-series risk). This has never been corrected for, in
  this mission or any prior phase.

### 5. What should be tested next?

Two options, in order of how directly they follow from this session's
own findings rather than starting a fresh, unrelated direction:

1. **Investigate WHY H_EXIT_002's per-trade improvement doesn't
   translate to total-return improvement.** This is a real, structural
   question this session surfaced but did not resolve — understanding
   it (e.g., does partial-taking systematically reduce compounding on
   the strategy's own best trades?) is more valuable than testing a
   brand-new hypothesis, because it explains a genuine tension in
   already-gathered evidence rather than gathering more.
2. **If entry-side research resumes**, do so with a hypothesis
   registered and its exact trigger rule specified BEFORE checking how
   often it would have fired historically — Pullback Continuation's
   rule was reasonable in concept but its trade-frequency was not
   sanity-checked against the real data before commitment, which is
   why it produced an untestable sample. A rough trade-frequency
   estimate against the real cache, done honestly BEFORE full
   commitment to a specific multi-condition rule, would avoid repeating
   this outcome.

Both remain genuinely open. **No hypothesis tested this mission
demonstrates a trading edge. This is a successful research result, not
a failure of the research process** — the mission's own framework
(experiment registry, comprehensive promotion gate, walk-forward,
regime analysis, multiple-testing correction, adversarial self-review)
worked exactly as intended: it let a real, honest directional signal
(H_EXIT_002) be investigated thoroughly and still correctly concluded
"not enough" rather than being talked into a false positive.
