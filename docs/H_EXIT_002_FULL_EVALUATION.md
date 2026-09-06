# H_EXIT_002 — Full 12-Step Evaluation (Strategy Edge Discovery, Phase A)

Mission: "STRATEGY EDGE DISCOVERY — CONTROLLED RESEARCH ONLY." Phase A
required finishing H_EXIT_002 (partial profit-take at +1R) through a
full protocol before any new entry hypothesis (Phase B) could begin.
`TrendMomentumBaseline` (`strategy/baseline.py`) remains untouched and
frozen throughout — every result here comes from
`backtesting/exit_experiments.py`'s fully isolated
`run_partial_profit_backtest`, which changes only the exit mechanic
(closes floor(qty/2) at +1R, remainder keeps the original stop/target).

Real, cached 41-symbol universe (32 NSE, 9 US), 5 years daily bars, 0
symbols failed to fetch. Every number below comes from a real backtest
run against this data this session — nothing is estimated or
extrapolated.

## 1–3. Hypothesis, registration, frozen parameters

- **Hypothesis** (`strategy/hypothesis_registry.py`'s existing
  `H_EXIT_002` record): taking partial profit at +1R while the
  remainder runs unmodified improves risk-adjusted expectancy over the
  frozen baseline's all-or-nothing stop/target.
- **Honest chronology note**: `run_partial_profit_backtest` was
  implemented in an earlier phase of this session, before this
  mission's "register before implementation" instruction existed. This
  evaluation registers the experiment formally for the first time
  (`strategy/experiment_registry.py` / `strategy/experiment_store.py`)
  but implementation itself predates registration — stated plainly
  rather than implying a false chronology.
- **Frozen manifest**: a dedicated `StrategyManifest` was built for
  this variant (not the plain baseline's own manifest, since the exit
  mechanic differs): `entry_rules_hash` from `strategy/baseline.py`'s
  source (entry logic is byte-identical to the baseline — unchanged),
  `exit_rules_hash` from `backtesting/exit_experiments.py`'s source
  (the actual modified exit mechanic — deliberately NOT
  `backtesting/execution.py`'s hash, which would not reflect what this
  variant actually does at exit time), parameters
  `{stop_atr_multiplier, target_risk_reward, partial_fraction: 0.5,
  partial_trigger_r: 1.0}`. `manifest_hash=73efc5d505280902`.
  Registered as experiment `5dc42faf-1e09-4c38-9272-d18e3da57219` in
  `data/experiment_registry.db` (gitignored; this document is the
  durable record).

## 4–6. Development / validation / out-of-sample (default cost model)

Reproduced exactly the trade counts from earlier this session (confirms
determinism — same code, same cache, same result):

| Split | Candidate trade-records | Standard baseline trades | Candidate expectancy | Verdict |
|---|---|---|---|---|
| Development | 343 | 216 | +0.128% | STATISTICALLY_MEANINGLESS |
| Validation | 149 | 108 | +0.222% | STATISTICALLY_MEANINGLESS |
| Out-of-sample | 160 | 117 | +0.493% | STATISTICALLY_MEANINGLESS |

**Base promotion evaluation: INCONCLUSIVE.** "Every split's
point-estimate expectancy is positive... but at least one split's
confidence interval still straddles zero — not yet statistically
decisive." Matches the hypothesis registry's own prior finding exactly.

## 7. Walk-forward validation (6 folds, pooled across the universe)

Newly possible this phase: `backtesting/walk_forward.py`'s
`run_walk_forward_validation` was extended with an optional
`backtest_runner` parameter (default unchanged; existing callers and
tests unaffected — see commit `25d7766`) so it could drive
`run_partial_profit_backtest` instead of the standard engine, reusing
the SAME leakage-safe N-fold splitting/pooling logic rather than a
duplicated implementation.

| Fold | Trades | Expectancy | Verdict |
|---|---|---|---|
| 0 | 47 | −0.048% | STATISTICALLY_MEANINGLESS |
| 1 | 103 | −0.025% | STATISTICALLY_MEANINGLESS |
| 2 | 142 | +0.031% | STATISTICALLY_MEANINGLESS |
| 3 | 105 | **+1.140%** | **POSITIVE_PERFORMANCE** |
| 4 | 119 | +0.295% | STATISTICALLY_MEANINGLESS |
| 5 | 134 | +0.532% | STATISTICALLY_MEANINGLESS |

**Not walk-forward consistent in the strong sense.** No fold is
NEGATIVE_PERFORMANCE (a real positive), but only 1 of 6 folds reaches a
confident positive verdict — the other 5 are statistically
indistinguishable from zero, and 2 of those 5 have a slightly negative
point estimate. This is a materially weaker signal than "the effect
holds across independent windows" would imply; it is closer to "no
fold is decisively bad, one fold happens to be decisively good."

## 8. Regime analysis (candidate's own trades)

| Regime | n | Verdict |
|---|---|---|
| TRENDING_UP + NORMAL_VOLATILITY (dominant bucket) | 385 | STATISTICALLY_MEANINGLESS |
| SIDEWAYS + NORMAL_VOLATILITY | 58 | STATISTICALLY_MEANINGLESS |
| TRENDING_UP + UNKNOWN (warm-up) | 112 | STATISTICALLY_MEANINGLESS |
| SIDEWAYS + UNKNOWN (warm-up) | 39 | STATISTICALLY_MEANINGLESS |
| UNKNOWN + UNKNOWN (warm-up) | 32 | STATISTICALLY_MEANINGLESS |
| 5 smaller buckets | <30 each | INSUFFICIENT_DATA (unmeasured, not proven anything) |

**One genuine, real finding**: the dominant regime bucket
(TRENDING_UP + NORMAL_VOLATILITY) flips from the standard baseline's
own NEGATIVE_PERFORMANCE (283 trades, established earlier this session)
to STATISTICALLY_MEANINGLESS for the candidate (385 trade-records) —
no longer confidently negative. This is a real, if modest, improvement:
the partial-take mechanic removes the decisive negative result in the
strategy's own most common trading condition. No regime bucket with
adequate data is negative for the candidate → `regime_consistent=True`.

## 9. Mandatory comparisons

- **Frozen baseline (previous_baseline)**: standard engine's own pooled
  per-trade mean, recomputed fresh this run over the identical dev/val/oos
  windows: **−0.6206%**. Candidate's pooled per-trade-record mean:
  **+0.2391%**. Candidate beats the frozen baseline on this metric
  (`beats_previous_baseline=True`).
- **Random-entry Monte Carlo** (100 iterations, seeded, entry counts
  matched to the standard engine's own real per-symbol trade counts —
  the SAME "isolate entry timing" convention `H_ENTRY_001` established):
  random average −0.0494%; only **16.0%** of iterations performed at
  least as well as the candidate (`beats_random_baseline=True`). Note
  this tests the FULL entry+exit combination, not entry timing alone —
  H_EXIT_002's entries are identical to the standard baseline's, whose
  own entries underperformed 96% of random iterations (H_ENTRY_001).
  The improvement here is attributable to the exit mechanic, not to any
  change in entry timing.
- **Buy-and-hold — UNITS-CORRECTED** (this project's own established
  units trap, see `docs/BRUTAL_SELF_CRITIC.md` item 8): comparing
  TOTAL period return to TOTAL period return, not per-trade mean to
  total return. Buy-and-hold average total return across the universe:
  **+18.58%**. Candidate's own average TOTAL return per symbol over the
  same full period: **−0.81%**.

  **This is the single most important finding of this evaluation, and
  it cuts against a positive read of H_EXIT_002**: despite an improved
  per-trade-record expectancy, the candidate's own total capital growth
  over the full 5-year period is not just far behind buy-and-hold — it
  is **marginally worse than the standard baseline's own total return
  (−0.68%, established earlier this session)**. A per-trade metric
  improving while total capital return does not (and slightly worsens)
  is a genuine, reportable tension, not a contradiction to explain
  away: partial-taking profit at +1R locks in smaller, more frequent
  gains but caps the upside of the trades that go on to hit the full
  2:1 target, and the net effect on compounded capital growth over the
  candidate's own trade sequence is slightly negative relative to the
  baseline it was meant to improve on.

## 10. Cost / slippage sensitivity

Default `CostModel()` vs `CostModel.india_nse_intraday_2026()` (STT,
NSE exchange fees, ₹20 Dhan brokerage, realistic slippage):

| Split | Default expectancy | NSE-cost expectancy |
|---|---|---|
| Development | +0.128% | +0.068% |
| Validation | +0.222% | +0.161% |
| Out-of-sample | +0.493% | +0.433% |

Expectancy shrinks materially under realistic costs (development's
edge roughly halves) but stays positive in every split; the verdict
stays INCONCLUSIVE under both cost models — not a costs artifact, but
a real erosion worth noting: this candidate's already-thin,
not-yet-significant edge is meaningfully cost-sensitive.

## 11. Multiple testing correction

Within-experiment family (development, validation, out-of-sample),
Bonferroni-corrected z=2.394 (family_size=3): all three splits remain
STATISTICALLY_MEANINGLESS under both the uncorrected and corrected
confidence level — no verdict changes, because none was positive to
begin with. `any_verdict_survives_correction_as_positive=False`. (This
is narrower than the session's earlier family-of-4 exit-hypothesis
correction — see `docs/BRUTAL_SELF_CRITIC.md` item 3's own honest
disclosure about correction scope; both apply here to the same
underlying conclusion.)

## 12. Adversarial self-review (H_EXIT_002-specific)

- **Look-ahead / data leakage**: none introduced. Walk-forward folds
  use the same leakage-tested splitting logic as the standard baseline
  (`test_walk_forward_fold_trades_never_depend_on_data_past_that_folds_own_end`,
  now proven to also hold with a custom `backtest_runner`). Regime
  classification reads only prior bars.
- **Survivorship bias**: inherited from the underlying 41-symbol cache
  (see `docs/BRUTAL_SELF_CRITIC.md` item 2) — applies identically here.
- **Selection bias**: none — this is the SAME hypothesis already
  registered and evaluated earlier this session; no cherry-picking of
  which exit variant to deepen (H_EXIT_002 was the mission's own
  explicit priority).
- **Multiple testing bias**: addressed directly in step 11.
- **Overfitting**: no parameter was tuned against this run's own
  validation/OOS data — the +1R trigger and 50% partial-close fraction
  are fixed constants from the ORIGINAL hypothesis design, unchanged.
- **Parameter snooping**: none — same reasoning as overfitting.
- **Insufficient sample size**: dev/val/oos all clear 30 trades easily;
  5 of 10 regime buckets and all 6 walk-forward folds clear it too; the
  5 smaller regime buckets remain genuinely unmeasured.
- **Non-stationarity**: directly tested by walk-forward — the result is
  NOT stationarity-consistent (5 of 6 folds indistinguishable from
  zero, only 1 decisively positive), a real caution against assuming
  the pooled dev/val/oos result reflects a stable effect through time.
- **Transaction-cost sensitivity**: directly tested (step 10) — edge
  survives realistic NSE costs but shrinks substantially.
- **Regime concentration**: the dominant regime (385 of ~654
  trade-records) drives most of the pooled result; it is itself only
  STATISTICALLY_MEANINGLESS, not positive, so the pooled INCONCLUSIVE
  verdict is not being propped up by a small favorable regime hidden
  inside a large neutral one.
- **Dependence between trades**: unaddressed by this or any prior
  phase of this project — multiple trades per symbol are not
  statistically independent draws, and the confidence intervals
  computed throughout (here and elsewhere) do not correct for this.
  Stated as an open limitation, not newly discovered this phase.

## Final verdict: INCONCLUSIVE — not promoted

Per the mission's own allowed conclusions, this is reported as
**INCONCLUSIVE**, not forced positive. Summary of what changed and what
didn't relative to the prior (dev/val/oos-only) finding:

- **Unchanged**: base dev/val/oos verdict (INCONCLUSIVE), trade counts
  (fully reproducible), the beats-random-baseline and
  beats-previous-baseline comparisons (both True, per-trade metric).
- **New, positive**: the dominant regime bucket is no longer
  confidently negative (real improvement over the standard baseline in
  its own most common condition); no walk-forward fold is confidently
  negative; the edge survives realistic transaction costs.
- **New, negative**: walk-forward consistency is much weaker than a
  single pooled result suggests (5 of 6 folds are noise); and, most
  importantly, the units-corrected total-return comparison shows the
  candidate's own overall capital growth is NOT better than the frozen
  baseline's — a genuinely sobering result that a per-trade-only
  analysis would have missed entirely.

**This is the mission's own stated stop-condition trigger for the exit
side**: H_EXIT_002, the most promising thread from the prior phase, has
now been evaluated to the mission's full standard and does not clear
the bar. Combined with H_EXIT_001/003/004 (all REJECTED) and
H_ENTRY_001 (SUPPORTED negative — entry timing measurably
underperforms random), the exit-side research program is exhausted:
no exit-logic variant tested so far demonstrates a real edge. Phase B
(entry-side hypotheses, starting with Pullback Continuation) proceeds
next per the mission's own instruction, with the explicit understanding
that if it also fails, the mission's stop condition applies and no
further indicators should be added.
