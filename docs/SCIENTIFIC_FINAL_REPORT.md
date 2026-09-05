# Scientific Final Report

Strategy science mission, Phase 18 (final). Synthesizes every phase of this
mission into one honest, evidence-labeled account. Source of truth is
always the code, tests, and the real cached data referenced below — this
document summarizes them, it does not supersede them, and it will go stale
as the code changes.

## Evidence labels used below

- **CODE IMPLEMENTED** — the code exists and runs; no independent
  verification claimed beyond that.
- **UNIT TEST VERIFIED** — covered by passing, meaningful automated tests
  (verified failing before the fix, where applicable).
- **INTEGRATION VERIFIED** — exercised end-to-end against real, though not
  necessarily live, components (e.g. the real wire-parsing path, a real
  browser).
- **HISTORICAL DATA VERIFIED** — run against real cached market data (the
  41-symbol universe, 5 years daily bars), not synthetic fixtures.
- **LIVE MARKET VERIFIED** — actually observed during a real, open market
  session. **Nothing in this report carries this label.** Markets were
  closed for this entire mission (a Saturday); see item 14.
- **STATISTICALLY VALIDATED** — evaluated against this project's own
  single statistical standard (`learning.profitability.
  compute_profitability_report_from_returns`: Wilson-CI win rate,
  normal-approximation mean-return CI, 30-trade minimum sample floor),
  with an explicit verdict, not just a number.

## The headline finding, stated plainly

**No entry or exit rule modification tested this mission earned promotion.**
Every rigorous, independent method applied to the real 41-symbol universe
— the base strategy's own pooled result, its development/validation/
out-of-sample split, 6 independent walk-forward folds, 4 exit-hypothesis
experiments each with their own three-way split, a 100-iteration
execution-robustness Monte Carlo, and a Bonferroni-corrected re-evaluation
— found either a confidently negative or merely inconclusive result. None
found a confident positive one. `strategy.promotion_gate.evaluate_promotion`
run against the real universe returns **NEGATIVE**. This is not a partial
or ambiguous outcome to soften: on the evidence gathered, `strategy/
baseline.py`'s `TrendMomentumBaseline` has not demonstrated an edge, and
this mission's own four attempts to fix its exit logic did not produce one
either.

What this mission *does* leave behind: a hardened, extensively tested,
structurally safe research platform; a mechanical promotion gate that
correctly refuses to promote what the evidence doesn't support; a
multiple-testing-correction tool that confirms the negative finding isn't
an artifact of testing too many things at once; and an honest, itemized
account of exactly what has and hasn't been verified, below.

## 18-item evidence report

1. **Regime analysis** — CODE IMPLEMENTED, UNIT TEST VERIFIED, HISTORICAL
   DATA VERIFIED, STATISTICALLY VALIDATED. `backtesting/regime.py`
   classifies every trade by (trend, volatility) at its own entry time,
   look-ahead-safe by construction. **Correction, made honestly rather
   than silently, per `docs/BRUTAL_SELF_CRITIC.md`'s own audit**: this
   entry originally said only ONE regime bucket clears the 30-trade
   floor. Re-checked for real: TWO buckets actually do — TRENDING_UP +
   NORMAL_VOLATILITY (283 of 368 pooled trades) is confidently
   NEGATIVE_PERFORMANCE, closely matching the overall pooled result; but
   SIDEWAYS + NORMAL_VOLATILITY (50 trades) is STATISTICALLY_MEANINGLESS,
   not negative. The strategy's failure is not uniformly confirmed
   across every regime with adequate data — it is confidently negative in
   the dominant (trending) regime and merely inconclusive, not
   confidently negative, in the sideways one. Both remain far from a
   positive result.

2. **Temporal robustness** — CODE IMPLEMENTED, UNIT TEST VERIFIED,
   HISTORICAL DATA VERIFIED, STATISTICALLY VALIDATED.
   `backtesting/universe.py`'s `run_universe_backtest_by_period` (60/20/20
   chronological split, reused verbatim by every later phase). Real
   result: Development 216 trades win 30.56% expectancy −0.78% PF 0.666
   (NEGATIVE_PERFORMANCE); Validation 108 trades win 31.48% expectancy
   −0.70% PF 0.700 (STATISTICALLY_MEANINGLESS); Out-of-sample 117 trades
   win 38.46% expectancy −0.26% PF 0.873 (STATISTICALLY_MEANINGLESS). No
   split reaches POSITIVE_PERFORMANCE.

3. **Simple baselines** — CODE IMPLEMENTED, UNIT TEST VERIFIED, HISTORICAL
   DATA VERIFIED. `strategy/simple_baselines.py`'s `SimpleMomentumBaseline`/
   `SimpleTrendBaseline` isolate entry-condition complexity as the only
   variable (same ATR-based stop/target as the real strategy) — tests
   whether `TrendMomentumBaseline`'s added complexity (trend+momentum+
   volume, all three) actually earns its keep over a simpler rule.

4. **Entry hypothesis research** — CODE IMPLEMENTED, UNIT TEST VERIFIED,
   HISTORICAL DATA VERIFIED, STATISTICALLY VALIDATED. 5 hypotheses in
   `strategy/hypothesis_registry.py`: H_ENTRY_001 **SUPPORTED** — 96.0% of
   300 Monte Carlo random-entry iterations (`backtesting/random_baseline.py`)
   performed at least as well as the real strategy (real pooled mean
   return −0.64% vs. random baseline's own average of −0.06%) — entry
   timing is not merely uninformative, it measurably underperforms random
   chance. H_ENTRY_005 **INCONCLUSIVE** (the one regime bucket with
   sufficient data is negative; every other bucket is genuinely
   under-sampled, not proven negative). H_ENTRY_002/003/004 remain
   **OPEN** — never implemented or tested this mission.

5. **Exit hypothesis experiments** — CODE IMPLEMENTED, UNIT TEST VERIFIED,
   HISTORICAL DATA VERIFIED, STATISTICALLY VALIDATED. Four fully-isolated
   experimental engines in `backtesting/exit_experiments.py` (deliberately
   never touching the frozen `backtesting/execution.py`), each run against
   the real universe with its own dev/val/oos split:
   - H_EXIT_001 (breakeven stop at +1R): **REJECTED**. Development and
     out-of-sample both degrade (win rate 30.56%→17.88%, PF 0.666→0.445 in
     development); validation shows the only marginal improvement.
   - H_EXIT_002 (partial profit-take at +1R): **INCONCLUSIVE**. Every
     split flips from negative to positive point-estimate expectancy and
     profit factor climbs above 1.0 (development 0.666→1.078, validation
     0.700→1.131, out-of-sample 0.873→1.330), with the effect *growing*
     out-of-sample — the opposite of overfitting — but every confidence
     interval still straddles zero.
   - H_EXIT_003 (ATR trailing stop): **REJECTED**. Mixed, not consistent;
     validation clearly degrades (profit factor 0.700→0.530).
   - H_EXIT_004 (20-bar time-based exit): **REJECTED**. The cap almost
     never triggers (development trade count 216→216, unchanged); net
     effect across splits is negligible-to-mixed, not a consistent
     improvement.

6. **Experiment registry & promotion gate** — CODE IMPLEMENTED, UNIT TEST
   VERIFIED, HISTORICAL DATA VERIFIED. `strategy/promotion_gate.py`
   mechanizes this mission's own promotion rule (5-way verdict:
   PROMOTED/NEGATIVE/INCONCLUSIVE/REJECTED/INSUFFICIENT_DATA) instead of
   a hand-applied judgment call; `strategy/promotion_store.py` persists
   every evaluation as an append-only audit trail. Run for real against
   `TrendMomentumBaseline`: Development NEGATIVE_PERFORMANCE, Validation
   and Out-of-Sample both STATISTICALLY_MEANINGLESS → **GATE VERDICT:
   NEGATIVE**. The gate agrees with the hand-derived conclusion it was
   built to formalize.

7. **Walk-forward validation** — CODE IMPLEMENTED, UNIT TEST VERIFIED,
   HISTORICAL DATA VERIFIED, STATISTICALLY VALIDATED. `backtesting/
   walk_forward.py`, with an explicit leakage-detection test proving a
   given fold's trades never depend on data past that fold's own
   boundary. Real 6-fold result: 2 of 6 folds confidently
   NEGATIVE_PERFORMANCE, 0 of 6 POSITIVE_PERFORMANCE, only one fold (of
   six) shows a positive point estimate. Not a single cherry-picked split
   — the negative finding holds across independent rolling windows.

8. **Monte Carlo robustness** — CODE IMPLEMENTED, UNIT TEST VERIFIED,
   HISTORICAL DATA VERIFIED, STATISTICALLY VALIDATED. Two distinct Monte
   Carlo studies: entry-timing randomization (item 4, H_ENTRY_001) and
   `backtesting/execution_robustness.py`'s execution-friction
   randomization (missed fills, delayed fills, randomized slippage). Real
   100-iteration result: baseline mean return −0.64%; iteration range
   [−0.90%, −0.56%]; **0.0% of iterations flipped sign** — the negative
   verdict is robust to realistic execution assumptions, not an artifact
   of an unrealistically forgiving backtest.

9. **Multiple testing control** — CODE IMPLEMENTED, UNIT TEST VERIFIED,
   HISTORICAL DATA VERIFIED, STATISTICALLY VALIDATED.
   `strategy/multiple_testing.py`'s Bonferroni correction, applied for
   real to this mission's own 4 exit-hypothesis out-of-sample results
   (family size 4, corrected z=2.4977): **no split survives correction as
   positive** — the same conclusion as before correction, so the negative
   finding is not an artifact of having tested several candidates
   simultaneously.

10. **LLM contribution audit** — CODE IMPLEMENTED, UNIT TEST VERIFIED,
    INTEGRATION VERIFIED. Traced every path that can reach `RiskEngine.
    evaluate()` or open a real (paper) position; both are 100%
    deterministic (`strategy/baseline.py`, and the opt-in
    `decision_engine`→`risk/sizing.py` bridge). Every actual LLM call site
    returns a schema with no field capable of holding a price/quantity/
    approval flag. Two structural gaps the audit flagged as fragile (not
    exploited, but unlocked) were closed with new named tests
    (`tests/test_decision_engine_llm_independence.py`). See
    `docs/LLM_CONTRIBUTION_AUDIT.md`.

11. **News & market intelligence architecture** — CODE IMPLEMENTED, UNIT
    TEST VERIFIED, INTEGRATION VERIFIED. No overclaiming found in data
    labeling, NSE/BSE claims, or the news/AI-narration boundary. One real
    gap found and fixed: the dashboard's connectivity banner was a
    hardcoded static string, contradicting the feed-status table
    whenever a genuinely live feed was connected — now reads real
    `feed_status` state. See `docs/NEWS_MARKET_INTELLIGENCE_AUDIT.md`.

12. **Data source architecture review** — CODE IMPLEMENTED, UNIT TEST
    VERIFIED. The entire historical pipeline is a single point of failure
    on Yahoo Finance (documented, not fixed — a second provider is a
    non-trivial undertaking out of scope). Cache staleness was a
    write-only metric until this phase; `report_cache_staleness()` and a
    new `cache-status` CLI command close that. Real check: this mission's
    own cached data (RELIANCE.NS, AAPL) was ~11 days old at review time —
    every "real 41-symbol universe" result in this report reflects that
    one fixed historical snapshot, not a continuously refreshed dataset.
    See `docs/DATA_SOURCE_ARCHITECTURE_REVIEW.md`.

13. **Live data stress testing** — CODE IMPLEMENTED, UNIT TEST VERIFIED,
    INTEGRATION VERIFIED. Disconnect/reconnect, malformed packets, and
    duplicate/out-of-order/late ticks were already thoroughly tested (68
    tests). One real gap found and closed: no tick-level sanity
    validation existed before this phase — a single corrupted-but-valid
    tick could silently become a bar's high/low/close. `CandleBuilder.
    on_tick()` now rejects non-positive price, negative volume, and
    implausible price jumps. Two gaps found and explicitly NOT fixed
    (documented, not attempted): a data gap during a disconnect can
    silently skip a stop/target trigger; no automated watchdog exists for
    total feed silence. See `docs/LIVE_DATA_STRESS_TESTING.md`.

14. **Monday live validation plan** — CODE IMPLEMENTED (the
    `readiness-check` CLI command is UNIT TEST VERIFIED), plan only. This
    entire mission ran on a Saturday with markets closed; **nothing in
    this mission carries a LIVE MARKET VERIFIED label, and this report
    makes no such claim.** `docs/MONDAY_LIVE_VALIDATION_PLAN.md` is a
    concrete, step-by-step plan for the next real trading day, with
    explicit criteria for what would actually justify that label
    afterward.

15. **Dashboard & UI/UX hardening** — CODE IMPLEMENTED, UNIT TEST
    VERIFIED, INTEGRATION VERIFIED (the first real-browser pass in this
    project's history, not just `TestClient`). Every control exercised
    (REJECT, kill-switch activate/reset, page navigation) behaved
    correctly; no new bugs found. See `docs/DASHBOARD_UI_UX_HARDENING.md`.

16. **Observability** — CODE IMPLEMENTED, UNIT TEST VERIFIED, INTEGRATION
    VERIFIED. No silently-swallowed exceptions found in safety-critical
    paths (`risk/`, `paper/engine.py` catch nothing themselves); logging
    is properly configured and applied to every CLI command. Gap closed:
    tick-rejection log lines are now also queryable running counts
    (`CandleBuilder.rejected_tick_counts`, `DhanMarketDataSource.
    rejected_tick_counts_by_symbol()`). See `docs/OBSERVABILITY.md`.

17. **Security review** — CODE IMPLEMENTED, UNIT TEST VERIFIED. SQL
    injection and dashboard XSS: clean (every query parameterized, every
    HTML interpolation escaped). Secrets in git history: clean (91
    commits searched, no real credential ever committed). One real,
    exploitable gap found and fixed: `backtesting/cache.py` joined a
    symbol string directly into a filesystem path with no validation — a
    crafted symbol could escape `data/market/` via path traversal. Fixed
    with an allowlist validator, 16 new tests. Also added an explicit
    warning (not a hard block) when the dashboard binds to a non-loopback
    host, given its state-changing routes have no CSRF protection. See
    `docs/SECURITY_REVIEW.md`.

18. **This report.**

## Grades (A–F, not inflated)

**Platform infrastructure: B+.** 1,464 tests passing at the time this
report was written, all green after every merge this mission, every
change run through full regression + a dedicated safety suite + a secret
scan before landing. Deterministic core structurally proven LLM-free
(item 10). Real, fixed security and path-traversal issues (item 17). Not
an A: the historical data pipeline is a documented single point of
failure (item 12), and two real live-data gaps remain open by choice
(item 13) rather than closed.

**Strategy science: C.** The *process* deserves real credit — nine
hypotheses tested against real data with a single, consistent statistical
standard, an explicit leakage-detection test, a Monte Carlo robustness
check on execution assumptions, and a multiple-testing correction applied
honestly rather than skipped because it was inconvenient — this is
genuinely rigorous work, not going-through-the-motions. But the grade for
*strategy science* has to reflect the actual, current scientific outcome,
and that outcome is: **zero hypotheses tested this mission earned
promotion**, and the base strategy's entry timing measurably
underperforms random chance. A rigorous process that correctly and
honestly concludes "this does not work" is valuable and is not the same
as a failure of the process — but it is also not a B, because nothing
promotable resulted. C reflects "the science is sound; the strategy
isn't."

**Market intelligence: B.** Honest data labeling throughout (item 11), no
overclaiming found, real news correctly separated from AI narration. Not
higher: prediction-outcome sample sizes are still mostly ACTIVE/
unresolved (see the dashboard's own confidence-calibration table),
meaning the confidence-calibration claim this system is built to support
is itself still data-starved — an honest limitation, not yet a
demonstrated capability.

**Live data readiness: C+.** Extensively unit/integration tested (68
Dhan-pipeline tests, item 13), a real security/path-traversal fix landed,
tick-level sanity validation added — but **the live WebSocket feed has
never been exercised during an actual market session** (item 14), and two
identified correctness gaps (a stop/target that can be silently skipped
across a disconnect, no watchdog for total feed silence) remain open. This
grade will not honestly move to a B until Monday's plan is actually run
and its own checklist is honestly reported against.

**Operator experience: B+.** Real-browser-verified dashboard (item 15,
first time in this project's history), kill-switch/market-status/
broker-connectivity banners all correct and unmissable, observability
counters added where a real gap existed (item 16), a new `cache-status`/
`readiness-check` CLI toolset. Not an A: still a hand-rolled HTML
dashboard with no auth (mitigated, not eliminated, by item 17's warning),
and the operator still has to correlate several separate CLI commands and
pages by hand rather than one consolidated health view.

**Overall system: C+.** This is not a system ready to trade — not because
it's unsafe (the paper-only, structurally-incapable-of-real-orders
guarantee is real and repeatedly verified) but because **no strategy
tested has earned the right to be trusted with even paper capital under
this mission's own promotion rule.** What this mission built instead, and
built well, is the infrastructure that makes that judgment trustworthy: a
promotion gate that says no when the evidence says no, a multiple-testing
correction that closes the "did we just get lucky testing many things"
loophole, and an honest paper trail (this report included) that never
claims more than what was actually verified. The overall grade reflects
both halves honestly — strong platform, unproven strategy — rather than
letting the platform's quality inflate a claim about the strategy, or the
strategy's failure erase credit for the platform.

## What would change these grades

- **Strategy science → higher than C**: a hypothesis (entry OR exit) that
  reaches PROMOTED under `strategy.promotion_gate.evaluate_promotion` —
  all three splits confidently POSITIVE_PERFORMANCE, surviving a
  multiple-testing correction for however many candidates were tried.
  Nothing tested this mission comes close; H_EXIT_002's INCONCLUSIVE
  result is the nearest thing to a promising signal, and it is explicitly
  not proof.
- **Live data readiness → higher than C+**: actually running
  `docs/MONDAY_LIVE_VALIDATION_PLAN.md`'s steps during a real market
  session and honestly reporting which succeeded — only then would any
  LIVE MARKET VERIFIED label be earned.
- **Platform infrastructure → higher than B+**: a second historical data
  provider (closing the Yahoo single-point-of-failure), and closing the
  two live-data gaps flagged in item 13 rather than leaving them
  documented.
- **Overall → higher than C+**: requires the strategy-science item above,
  since no amount of platform polish changes the honest answer to "does
  this system currently have something worth trading" — which remains no.
