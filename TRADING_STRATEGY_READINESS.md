# Trading Strategy Readiness

Real-time strategy validation mission — the mission's own required
deliverable, distinguishing seven separate dimensions of readiness that
are frequently conflated in trading-system claims: **engineering is not
data quality is not strategy validity is not statistical confidence is
not paper-trading operation is not live-market verification is not
profitability.** A system can be ready on six of these and still have
zero evidence of an economic edge — that is, in fact, the exact
situation this document describes.

No claim below is inferred. Every row cites the file, command, or test
that produced it. Where evidence does not exist, the row says so
explicitly rather than being silently omitted.

---

## 1. Engineering readiness

**READY.** This is the dimension most thoroughly proven across this
entire multi-cycle campaign.

- 2418 passing tests (latest full regression, 0 failed) as of this
  document's own writing.
- Systematic mutation testing throughout — including several instances
  where a newly-written test was itself found too weak (survived a
  realistic mutant), strengthened, and re-verified, rather than
  dismissed or the mutant softened to force a pass.
- All 8 sacred live-execution-safety files (`live/dhan/broker_adapter.py`,
  `live/broker.py`, `live/pipeline.py`, `decision_engine/rules.py`,
  `decision_engine/engine.py`, `risk/engine.py`, `risk/sizing.py`,
  `main.py`) reviewed line-by-line after every change across the entire
  campaign; every diff to any of them additive, opt-in-gated, and
  reviewed before commit.
- Real OS-subprocess and multi-thread concurrency proof for the
  highest-value locking primitives (scheduler run-locks, paper-order
  idempotency, approval-decision CAS transitions).
- A previously-accepted resource-scaling limitation (`live/pipeline.py`'s
  indicator-history buffer, Cycle 34) is now genuinely fixed, not merely
  documented: bounded to 1000 bars, proven numerically equivalent to
  unbounded history (bit-for-bit identical by n=500 against real cached
  data), benchmarked 3.10x faster / 74.4% less peak memory over 4000
  bars with throughput that stabilizes instead of degrading. See
  `FINAL_FAILURE_MODE_ANALYSIS.md` entry #44.
- Real crash-boundary proofs exist for: orphaned HUMAN_APPROVED decisions
  at startup (Cycle 26), scheduler run-lock atomicity under real
  subprocess contention (Cycle 27), Dhan feed reconnect + replayed-tick
  rejection (Cycle 28), scheduler reclaim composed with paper-execution
  idempotency (Cycle 29).

## 2. Data readiness

**PARTIALLY READY, with one disclosed gap now closed and one still open.**

- Yahoo Finance is the actually-exercised historical/research data path
  throughout this project — real, not mocked, in every backtest/research
  command.
- Real India market context (NIFTY sector indices, India VIX) is wired
  into `market_intelligence/regime.py`, confirmed against real live data.
- **Closed this cycle**: predictions recorded at an intraday interval
  (the live-path's `--interval 1m` default) could never resolve through
  `python main.py evaluate`'s default period — a real, empirically-
  confirmed Yahoo Finance data-availability limit (1-minute bars capped
  at ~8 days of lookback), not a code bug in the strict sense, but a
  silent dead end the code did not account for. Fixed with
  `predictions.tracker.resolution_period_for_interval`. See
  `FINAL_FAILURE_MODE_ANALYSIS.md` entry #41.
- **Still open**: real-time Dhan tick data has REST authentication and
  WebSocket connectivity LIVE-VERIFIED this cycle (see Section 6 below),
  but actual live tick reception has not been verified end-to-end — the
  one real connectivity test available in this environment ran outside
  NSE market hours.

## 3. Strategy readiness

**NOT READY — no demonstrated edge, by design of the research process,
not by omission.**

This is a settled, frozen research conclusion, not a gap awaiting more
engineering. `docs/STRATEGY_EDGE_DISCOVERY_FINAL_OUTPUT.md` is the
canonical source:

- Two hypotheses were evaluated to this project's full standard
  (development / validation / out-of-sample / walk-forward / regime
  consistency / random-baseline comparison / statistical verdict):
  **H_EXIT_002** (partial profit-take at +1R) and **H_ENTRY_003**
  (Pullback Continuation entry timing). Neither reached the promotion
  bar (`evaluate_promotion_comprehensive` → `PROMOTED`).
- H_EXIT_002 showed the closest thing to a positive directional signal
  in this project's history (a real, non-degraded per-trade expectancy
  improvement over the frozen baseline) — but every split's confidence
  interval touches zero, it survives a Bonferroni multiple-testing
  correction as NOT significant, is inconsistent across walk-forward
  folds (5 of 6 are noise), and — the most important finding — does
  **not** translate into better total capital growth than the baseline
  it was meant to improve (−0.81% vs. the baseline's own −0.68%, both
  far behind buy-and-hold's +18.58% over the same period).
- H_ENTRY_003 could not even be measured: 29 total trades over 5 years
  across a 41-symbol universe is below this project's own
  `MIN_SAMPLE_SIZE_FOR_A_VERDICT = 30` floor.
- `python main.py readiness-check` itself states this outright, live,
  every time it runs: *"Active strategy: trend_momentum_baseline v1.0 --
  SCIENTIFIC VERDICT: NO DEMONSTRATED EDGE."*
- By this mission's own explicit, standing instruction, this conclusion
  is **preserved unchanged** — not re-tuned, not re-run against the same
  held-out data, not reframed as "insufficient evidence" when the actual
  evidence is negative/inconclusive.

## 4. Statistical readiness (methodology, not conclusion)

**READY as a methodology; the methodology's own conclusion is negative.**

- `learning/profitability.py` (Phase 41) is a real, working statistical
  evaluation engine: Wilson score intervals for win rate, a normal-
  approximation confidence interval for mean return (the actual basis
  for any verdict, not win rate alone), profit factor, max drawdown over
  a sequential trade-return equity curve, return volatility (explicitly
  NOT a Sharpe ratio — no time-normalization), sector/regime breakdowns.
- A stated, applied minimum-sample floor (`MIN_SAMPLE_SIZE_FOR_A_VERDICT
  = 30`) before any verdict is issued, and an honest
  `INSUFFICIENT_DATA`/`STATISTICALLY_MEANINGLESS`/`POSITIVE_PERFORMANCE`/
  `NEGATIVE_PERFORMANCE` verdict enum — never collapsing "not enough
  data" and "actually negative" into one label.
- Bonferroni multiple-testing correction is applied when evaluating more
  than one simultaneous hypothesis against the same dataset
  (`strategy/multiple_testing.py`, reused by
  `compute_profitability_report_from_returns`'s own `z` parameter).
- **Verified this cycle, not assumed**: this entire statistical engine
  already generalizes correctly to the NEW live-path prediction source
  (`decision_id = signal.stable_id()`, no `Decision` object) with zero
  new feature code — proven by a real test constructing exactly that
  shape and asserting the correct sub-reports include vs. gracefully
  exclude it. See `FINAL_FAILURE_MODE_ANALYSIS.md` entry #42.
- **Disclosed, unresolved methodological limitation, flagged repeatedly
  by this project's own adversarial reviews and never corrected**: every
  confidence interval computed throughout this project treats trades as
  independent draws. They are not — multiple trades on the same symbol
  share underlying price-series risk (autocorrelated, not i.i.d.). This
  is a real, acknowledged gap in rigor, not a hidden one.

## 5. Paper trading readiness

**PARTIALLY READY — the mechanism is real and hardened; the evidence
base is not yet accumulated.**

- Real, deterministic paper execution (`paper/engine.py`) is the sole
  execution path in this entire project — no code path anywhere places
  a real order (see `RealOrderPlacementDisabledError`, Section 6).
- **Closed this cycle**: `paper`, `live-sim`, and `paper-live` (the
  command this whole mission centers on) previously always defaulted to
  a generic cost model with ZERO STT/exchange charges for every fill —
  a silent, favorable-to-profitability cost understatement. Now have an
  explicit, disclosed `--cost-model india_nse_intraday_2026` opt-in
  (default unchanged for backward compatibility). See
  `FINAL_FAILURE_MODE_ANALYSIS.md` entry #43.
- **Closed this cycle**: the real-time paper-live path had no connection
  to this project's own immutable prediction ledger / automatic outcome-
  resolution machinery at all — every live signal was generated and
  (optionally) executed with zero prediction tracked. `live/prediction_
  recorder.py` now bridges this, opt-in via `--record-predictions`, with
  automatic periodic resolution via `--evaluate-every-n-bars` (default
  20) so evidence accumulates without a separate manual step. See
  `FINAL_FAILURE_MODE_ANALYSIS.md` entries #40/#41.
- **Not yet done**: no real-time paper-live session has actually been
  RUN outside of tests. The machinery is built, wired, and verified
  end-to-end against real cached data — but zero live-path predictions
  currently exist in `data/predictions.db`. A genuine paper track record
  requires actually operating the system, not just proving it works.
- **Separately, the research path's own forward-looking cohort**: 13
  predictions against real NSE symbols (entered 2026-09-03/04, 20-bar
  horizon); as of the last evaluation (2026-09-09), all 13 remain ACTIVE
  with zero resolved outcomes. The mechanism works; it has not yet
  produced usable evidence, positive or negative.

## 6. Live verification readiness

**PARTIALLY READY — connectivity newly verified this cycle; execution
remains, and will always remain, structurally disabled.**

- **Real broker order placement: structurally DISABLED, verified fresh
  this cycle by reading the actual source.**
  `live/dhan/broker_adapter.py::DisabledDhanOrderExecutor.place_order`
  unconditionally raises `RealOrderPlacementDisabledError`. No
  configuration flag, environment variable, or subclass override can
  change this without a source-code change. Not wired into any execution
  path anywhere in this project.
- **New this cycle**: real Dhan credentials became available in this
  environment for the first time in this entire campaign. With explicit
  user authorization, the existing, unmodified `python main.py
  readiness-check --deep` command was run against the real Dhan API
  (structurally read-only — one REST GET to `/fundlimit`, one WebSocket
  subscribe-to-receive, no order-path code touched). Result: REST
  authentication confirmed (real HTTP 200, 0.78s round-trip); WebSocket
  reached `CONNECTED` and subscribed successfully. See
  `FINAL_FAILURE_MODE_ANALYSIS.md` entry #45.
- **Still NOT live-verified**: actual live tick reception. The one real
  test available ran ~4 hours after NSE market close (19:22 IST), so no
  new tick data existed to receive regardless of connection health. This
  requires a re-run during real NSE trading hours (09:15–15:30 IST, a
  trading day) to close.
- No real order has ever been placed, attempted, or simulated-as-real at
  any point in this project's history.

## 7. Profitability

**CURRENT EVIDENCE IS NEGATIVE.** Not "insufficient evidence" — this
project has actually run the walk-forward evaluation and the result is
negative/inconclusive, not merely absent.

- ROC-AUC 0.575–0.615 across 4 walk-forward folds plus a held-out test
  (the earlier ML-baseline research line).
- `PromotionVerdict.NEGATIVE` on every single split, for both the
  trained model and the deterministic-rule benchmark evaluated against
  it. Transaction costs were included.
- The subsequent, more targeted hypothesis research
  (`docs/STRATEGY_EDGE_DISCOVERY_FINAL_OUTPUT.md`, Section 3 above)
  reached the same conclusion by a different, more rigorous route: NO
  hypothesis tested demonstrates a trading edge that survives its own
  statistical scrutiny.
- This conclusion is a **frozen, preserved research result** — by this
  mission's own explicit standing instruction, it is never revisited,
  reframed, re-tuned, or re-run against the same held-out data.
  `NO EVIDENCE OF ECONOMICALLY VIABLE EDGE IN THE CURRENT EXPERIMENT`
  stands.

---

## Required evidence table

| Requirement | Evidence | Result |
|---|---|---|
| Out-of-sample (OOS) performance | `ml_research/`'s held-out test split; `docs/STRATEGY_EDGE_DISCOVERY_FINAL_OUTPUT.md`'s OOS column for H_EXIT_002/H_ENTRY_003 | **NEGATIVE / MEANINGLESS / INSUFFICIENT_DATA** — no split demonstrates a positive, statistically distinguishable-from-zero result |
| Walk-forward validation | 4 folds (ML baseline) + 6 folds (H_EXIT_002); `strategy/walk_forward.py` (unmodified this campaign) | **NOT stationarity-consistent** — 1 of 6 H_EXIT_002 folds positive, 5 meaningless; ML baseline NEGATIVE on every fold |
| Transaction costs | `backtesting/costs.py::CostModel`, `india_nse_intraday_2026()` preset (STT/exchange charges/brokerage/slippage); included in every walk-forward/promotion evaluation above | **Included, and this cycle also wired into `paper`/`live-sim`/`paper-live` fills by explicit opt-in** (previously silently absent there — see `FINAL_FAILURE_MODE_ANALYSIS.md` entry #43) |
| Slippage | `CostModel.slippage_adjusted_price` — 5bps entry / 10bps exit (india preset), genuinely applied at every `paper/engine.py` fill | **Modeled, applied, disclosed** — not favorable-to-profitability by construction (worse fill price on both entry and exit) |
| Calibration | `learning/analysis.py::compute_real_confidence_calibration` (fixed LOW/MEDIUM/HIGH bands against `Decision.confidence`); `predictions/tracker.py::evaluate_prediction` (real outcome resolution) | **INSUFFICIENT DATA** — mechanism real and tested; the research-path cohort (13 predictions) has zero resolved outcomes; the live-path cohort has zero predictions recorded outside of tests |
| Positive expectancy | `learning/profitability.py::compute_profitability_report` — mean-return confidence interval is the actual basis, not win rate alone | **NOT DEMONSTRATED** — H_EXIT_002's directional improvement does not survive its own confidence interval or a Bonferroni correction; overall project conclusion is NEGATIVE/INCONCLUSIVE, never POSITIVE_PERFORMANCE |
| Drawdown | `compute_profitability_report`'s sequential trade-return equity curve max-drawdown; `backtesting/metrics.py::PerformanceMetrics.max_drawdown_pct` | **Measured where evaluated** (H_EXIT_002/baseline backtests); not independently a pass/fail gate — no promoted strategy exists to state a live-relevant drawdown figure for |
| Regime robustness | `learning/regime.py::classify_regime_at` + `compute_regime_performance`; `docs/STRATEGY_EDGE_DISCOVERY_FINAL_OUTPUT.md`'s Regime Consistency column | **NOT DEMONSTRATED** — no bucket outright NEGATIVE for H_EXIT_002, but 5 of 10 candidate buckets lack adequate sample size; genuinely unmeasured for those, not proven robust |
| Paper track record | `data/predictions.db` (research path, 13 predictions, 0 resolved); `live/prediction_recorder.py` (live path, built and tested this campaign, zero real sessions run outside tests) | **INSUFFICIENT DATA / NOT YET ACCUMULATED** — the machinery to accumulate this evidence is complete and verified; the evidence itself does not yet exist |
| Statistical confidence | `learning/profitability.py`'s Wilson/mean-return confidence intervals; `MIN_SAMPLE_SIZE_FOR_A_VERDICT = 30`; Bonferroni correction for multiple simultaneous hypotheses | **Methodology READY; underlying data INSUFFICIENT** for a live-path verdict, and the research-path verdict is NEGATIVE/INCONCLUSIVE where it does have enough data |
| Live validation | `python main.py readiness-check --deep` against the real Dhan API this cycle (`FINAL_FAILURE_MODE_ANALYSIS.md` entry #45) | **PARTIALLY VERIFIED** — REST auth + WebSocket connectivity LIVE-VERIFIED; live tick reception NOT LIVE-VERIFIED (tested outside market hours); order placement structurally disabled and untested by design |

---

## Bottom line

The **engineering** to build, record, resolve, evaluate, and report on a
real-time paper trading strategy is complete and unusually well-tested
for a project of this kind. The **strategy** running through that
engineering has been tested to a genuine scientific standard and does
not demonstrate a trading edge. These are two separate facts, and
neither one substitutes for the other: excellent engineering does not
create profitability, and the absence of profitability does not mean
the engineering is unfinished. Both are true here, and this document
states them as such.

**This platform is ready to accumulate real paper-trading evidence. It
is not, and should not be represented as, a system with a demonstrated
trading edge — in paper or in real money.**
