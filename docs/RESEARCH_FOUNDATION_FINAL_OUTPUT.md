# Scientific Strategy Research Foundation — Final Output

Mission: "the current TrendMomentumBaseline is a frozen failed baseline;
build the scientific framework required to discover whether ANY strategy
variation has genuine edge without overfitting." This document is the
mandated final output — an evidence table, then what is proven,
disproven, remains hypothesis, and whether any edge has been
demonstrated. Source of truth is always the code, tests, and the real
41-symbol cached universe referenced below.

## Evidence table

| Component | Implemented | Unit Tested | Integration Tested | Real Data Tested | Reliable | Known Gaps |
|---|---|---|---|---|---|---|
| Experiment registry (`strategy/experiment_registry.py`, `strategy/experiment_store.py`) | Yes | Yes (11 tests) | Yes (real manifest+split+evaluation composed end to end) | Yes (2 real experiments persisted to `data/experiment_registry.db`) | Yes | No query-by-verdict or query-by-date-range helper yet; only by hypothesis_id/manifest_hash/all |
| Strategy manifest hashing (`strategy/manifest.py`) | Yes (pre-existing) | Yes | Yes | Yes | Yes | Only hashes `strategy/baseline.py` + `backtesting/execution.py` source; a change to `market/indicators.py`'s indicator math would not be detected |
| Market regime classifier (`backtesting/regime.py`) | Yes (pre-existing) | Yes, including 2 dedicated anti-look-ahead tests | Yes | Yes | Yes | UNKNOWN is returned (never a guess) during warm-up, but callers must handle that explicitly; not silently defaulted |
| Regime performance analysis | Yes | Yes | Yes | Yes (re-run this phase) | Yes | Only 2 of 6 (trend×volatility) buckets clear the 30-trade floor; the other 4 are genuinely unmeasured, not proven negative |
| Walk-forward validation (`backtesting/walk_forward.py`) | Yes (pre-existing) | Yes, including a leakage-detection test | Yes | Yes (re-run this phase) | Yes | 6 folds is a modest count; the smallest fold (33 trades) sits close to the sample floor |
| Promotion gate — base (`evaluate_promotion`) | Yes (pre-existing) | Yes | Yes | Yes | Yes | None found |
| Promotion gate — comprehensive (`evaluate_promotion_comprehensive`) | Yes (this phase) | Yes (9 tests) | Yes (real baseline evaluated end to end) | Yes | Yes, with one caveat found and fixed | `*_mean_return_pct` parameters require caller-supplied UNITS CONSISTENCY (per-trade mean, not total-period return) — documented explicitly in the function's own docstring after this phase's own audit caught the trap before it produced a wrong conclusion |
| Buy-and-hold comparison (`backtesting/baselines.py`) | Yes (pre-existing) | Yes | Yes | Yes (real 41-symbol average computed this phase) | Yes | None found |
| Random-entry Monte Carlo (`backtesting/random_baseline.py`) | Yes (pre-existing) | Yes | Yes | Yes | Yes | None found |
| Multiple testing correction (`strategy/multiple_testing.py`) | Yes (pre-existing) | Yes | Yes | Yes | Yes | Only applied to the 4 exit-hypothesis splits, not to every statistical comparison this project has ever run (see Brutal Self-Critic item 3) |
| Brutal self-critic audit (`docs/BRUTAL_SELF_CRITIC.md`) | Yes | N/A (a review, not code) | N/A | Yes | Yes | Is itself a point-in-time audit; must be re-run if the codebase changes materially |
| Survivorship-bias disclosure | Yes (newly documented this phase) | N/A | N/A | Yes | Yes | The bias is disclosed, not corrected — no delisted-company data exists to add |

## A. What is scientifically proven

- **`TrendMomentumBaseline`'s pooled result is confidently negative.**
  368 real trades, mean return −0.64%, 95% CI entirely below zero, profit
  factor 0.72 (dev/val/oos re-verified this phase: pooled per-trade mean
  −0.62%, consistent within normal re-run variance).
- **It loses decisively to a passive buy-and-hold strategy on the same
  universe.** Real, apples-to-apples comparison computed this phase: the
  strategy's own average TOTAL return per symbol over 5 years is −0.68%;
  a simple buy-and-hold over the identical symbols and period averages
  +18.58%. This is not a marginal underperformance.
- **Entry timing measurably underperforms random chance.** H_ENTRY_001:
  96.0% of 300 Monte Carlo random-entry iterations performed at least as
  well as the real strategy; re-verified this phase with a smaller,
  independent 50-iteration run (real strategy −0.62% vs. random
  baseline's own average −0.02%) — the same conclusion, reproduced.
- **The negative finding is not an artifact of one split, one fold, or
  too many simultaneous tests.** Confirmed independently by: the
  dev/val/oos split, 6 walk-forward folds (2 confidently negative, 0
  confidently positive), a 100-iteration execution-friction Monte Carlo
  (0% of iterations flipped sign), and a Bonferroni correction across the
  4 exit-hypothesis experiments (none survives as positive after
  correction).
- **No look-ahead leakage, no cross-period trade bleed, no parameter
  tuning against held-out data.** Verified by dedicated tests (this
  session's own leakage tests) and by `strategy/manifest.py`'s own
  content-hash mechanism, which would detect silent rule drift.
- **The 41-symbol universe is survivorship-biased**, and this makes the
  negative finding more credible, not less: a sample biased toward
  looking better than reality still produced a negative result.

## B. What is disproven

- **That `TrendMomentumBaseline` has a demonstrated trading edge.**
  Disproven by every independent method applied to it this project.
- **That the negative result is confined to one regime.** The dominant,
  best-sampled regime (TRENDING_UP + NORMAL_VOLATILITY, 283 trades) is
  itself confidently negative — the strategy does not merely fail in an
  unusual condition; it fails in the condition it actually trades in most.
- **That entry timing carries positive information.** Disproven
  decisively (96% of random iterations matched or beat it).

## C. What remains hypothesis (genuinely open, not yet tested to a
   conclusion)

- **H_ENTRY_002/003/004** (volume-confirmation-only, pullback entries,
  momentum-acceleration entries) — never implemented or tested at all.
- **The SIDEWAYS + NORMAL_VOLATILITY regime bucket** (50 trades,
  STATISTICALLY_MEANINGLESS) — not proven negative, not proven positive;
  genuinely inconclusive with adequate-but-not-large sample size.
- **H_EXIT_002 (partial profit-take at +1R)** — INCONCLUSIVE: every split
  shows a positive point-estimate expectancy with profit factor above 1.0
  and the effect growing out-of-sample, but no split reaches statistical
  significance. The single most promising unresolved thread from this
  entire research program — not evidence of an edge, but the closest
  thing to one found so far.
- **Every regime combination other than the two with ≥30 trades**
  (TRENDING_DOWN×any volatility, TRENDING_UP×HIGH/LOW volatility,
  SIDEWAYS×HIGH/LOW volatility) — genuinely unmeasured, not proven
  anything.
- **Whether a strategy variant could pass the new comprehensive
  promotion gate** (`evaluate_promotion_comprehensive`) — the gate itself
  is now built and real-data-tested, but no candidate has yet been run
  through it and reached PROMOTED.

## D. Does the system have any demonstrated trading edge yet?

**NO DEMONSTRATED EDGE.**

Every rule tested against the real 41-symbol universe — the frozen
baseline itself, its four exit-logic variants, and its entry-timing
component in isolation — has been evaluated through independent,
corroborating methods (a fixed dev/val/oos split, 6-fold walk-forward, a
100-iteration execution-robustness Monte Carlo, a 300-iteration
entry-timing Monte Carlo, a Bonferroni multiple-testing correction, and
now a real, apples-to-apples buy-and-hold total-return comparison) and
none has produced a confident, statistically decisive positive result.
The scientific framework built and extended this phase — a unified
experiment registry, a comprehensive promotion gate requiring the
candidate to beat real benchmarks (not just clear its own statistical
bar), and an independent brutal self-critic audit — exists specifically
so that if a genuine edge is found in future work, it will have to
survive exactly this level of scrutiny before being trusted. Nothing
found so far has survived it. The one thread worth continued attention
without overclaiming it is H_EXIT_002's consistent-but-not-yet-
significant positive signal — a hypothesis, not a finding.
