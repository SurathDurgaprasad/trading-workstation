# Final Product Readiness Report

Branch: `final-product-hardening`, merged forward to `main` after every
cycle (`main == origin/main` verified at every commit). Current HEAD:
`c8fbc16`. Companion documents: `FINAL_PRODUCT_CAPABILITY_MATRIX.md`
(the authoritative per-requirement evidence table this report
summarizes), `FINAL_FAILURE_MODE_ANALYSIS.md` (39 numbered entries),
`tests/failure_injection/failure_matrix.yaml` (110 executable rows),
`ARCHITECTURE.md`, `SECURITY.md`.

This report supersedes the version of itself written at the end of an
earlier three-pass hardening campaign (that version's own historical
content — clean-install proof, Claude-Code-independence proof, the
original documentation suite — remains true and is not re-litigated
here). Since that version, a further **35-cycle autonomous adversarial
hardening campaign** ran against this same codebase: systematic
mutation testing, real OS-subprocess and multi-thread concurrency
attacks, crash/restart/recovery injection against real temporary SQLite
files, and a full reality/profitability audit against the actual local
databases. Two of the defects found and fixed in that campaign reached
**CRITICAL** severity — both are described below, in full, because a
report that omitted them would misrepresent what this system actually
is.

This document is deliberately honest about scope. It states what is
proven, with evidence, what remains unverified, and what is explicitly
disabled by design — not what would make the product look most
complete.

---

## 1. Does the implementation satisfy the original specification?

**PARTIALLY.**

The engineering specification (safe, deterministic, auditable, paper-only
trading platform with a structurally-disabled live-execution path) is
satisfied — see Section 9 (Engineering readiness: READY).

The *trading* specification — a system that generates genuine economic
edge — is **not** satisfied by present evidence: the frozen ML research
verdict is `PromotionVerdict.NEGATIVE` on every walk-forward fold, and no
paper-trading or live track record exists yet that could establish edge
independently. This is not an engineering gap; it is an open scientific
question the codebase itself states honestly (see Section 7).

Exceptions/unmet items, all previously disclosed and none unsafe:
- No official NSE/BSE/SEBI data API exists — permanently out of this
  project's control, unfixable, correctly worked around via Yahoo
  Finance.
- Dashboard authentication is not implemented — deliberately deferred
  for the current single-operator, loopback-only threat model.
- No demonstrated live or long-duration paper-trading track record
  exists (see Section 7's profitability-evidence hierarchy: this
  project currently sits at Level 4, transaction-cost-adjusted
  walk-forward, with a negative result — Levels 5–8 have not been
  attempted).

## 2. What is actually implemented?

A layered pipeline (data → validation → indicators → strategy → risk →
decision → paper execution → persistence → learning/tracking), a
deterministic risk/decision core with zero LLM involvement, a
signal_id-keyed idempotent paper-trading engine, a kill switch and
account-level circuit breakers now proven to hold even across
mid-flight process crashes and TOCTOU races, a scheduler with
process-level-proven mutual exclusion and crash recovery, a real Dhan
WebSocket data-source implementation (untested against a live account),
a structurally-disabled real-broker-order path, an MCP server, a
dashboard, and a ~30-subcommand CLI. Full detail: `FINAL_PRODUCT_CAPABILITY_MATRIX.md`.

## 3. What is actually verified?

- **Unit**: thousands of tests across `risk/`, `paper/`, `market/`,
  `predictions/`, `scheduler/`.
- **Integration**: `tests/test_dhan_pipeline_integration.py`,
  `tests/test_scheduler_runner.py` (real signal generation → real risk
  evaluation → real paper submission, only market/news/sector data
  providers faked).
- **End-to-end**: the full market-data → decision → paper-execution
  chain, proven to reject INVALID data before any decision is computed.
- **Concurrency**: real Python threads with `threading.Barrier`/`Event`
  synchronization (cycles 15, 19, 20, 23, 25) AND real, independent OS
  subprocesses (`subprocess.Popen`, cycle 27) for the scheduler's core
  locking primitive.
- **Subprocess-level**: `SchedulerRunStore.try_start_run`'s mutual
  exclusion, proven atomic under two genuinely separate OS processes
  with independent SQLite connections, 10 repetitions.
- **Restart/recovery**: real temp-file SQLite databases, real "process
  crashed here" simulation at named transaction boundaries, real fresh
  store/pipeline instances standing in for a restarted process (cycles
  8, 15, 20, 22, 26, 29).
- **External-provider verification**: **not performed**. Every Dhan-
  related test uses dependency-injected fake transports. No test in
  this project's history has run against real Dhan credentials.
- **Mutation testing**: systematic, repeated, and — critically —
  sometimes **failed on the first attempt and was caught**: cycle 24's
  17-mutant campaign against `risk/engine.py` (all killed); cycles 27
  and 28 each independently found and fixed an initially-too-weak new
  test via this same discipline before trusting it as evidence.

## 4. What is simulated or mocked?

- **Dhan market data**: real client library (`websocket-client`), real
  WebSocket protocol handling — but every test drives it through a
  dependency-injected fake transport. `SIMULATED / VERIFIED`, never
  `REAL PROVIDER / VERIFIED`.
- **`MockBrokerAdapter`**: not a broker connection at all — delegates
  entirely to `PaperTradingEngine`. The name describes a Protocol-
  conformance rehearsal, not simulated broker access.
- **`DisabledDhanOrderExecutor`**: exists specifically to make real
  order placement impossible; every method unconditionally raises.
- **News/sector/market-context providers** in the scheduler's own test
  suite: faked, by that suite's own long-standing, explicit convention
  (not hidden — every affected test file states this in its own module
  docstring).
- **The 32-trade `data/paper_trading.db` history**: on direct
  inspection this cycle, this is a **batch replay of ~5 years of cached
  AAPL (a US stock) historical data through the paper engine, run in one
  sitting on 2026-08-25** — mechanical engine-validation evidence, not a
  live or forward-looking paper-trading track record, and not evidence
  about Indian-market performance. `data/live_sim_trading.db` (the
  engine actually wired to the live pipeline) is confirmed empty.

## 5. Is the system live?

Answered separately, per this campaign's own standing rule against
collapsing these into one word:

| Axis | Status |
|---|---|
| Live-capable market data | YES — real `websocket-client` transport, real Dhan REST client |
| Live-verified market data | **NO** — never run against real credentials in this environment |
| Paper execution | YES, real, the sole exercised execution path |
| Broker connectivity (read-only) | YES, live-capable (`DhanAccountReader`), not live-verified |
| Real broker order execution | **NO** — structurally, unconditionally disabled (`RealOrderPlacementDisabledError`), no bypass exists anywhere in the codebase |
| Live-money operation | **NOT ENABLED, NOT AUTHORIZED, NOT ATTEMPTED** |

## 6. Can it actually trade?

- **Paper**: **YES.**
- **Broker-connected (data only, no orders)**: **YES**, for market data
  and read-only account/fund/position access — unverified against a
  live account.
- **Real-money**: **NO.** Structurally impossible without a deliberate
  source-code change to remove `RealOrderPlacementDisabledError` and
  wire a real execution adapter into the pipeline — neither of which
  exists, and neither of which this campaign was authorized to do (and
  did not do).

## 7. Is it profitable?

> **CURRENT EVIDENCE IS NEGATIVE.**

Not "insufficient evidence" — this project has actually run the
walk-forward evaluation, and the result is negative, not merely absent.

- ROC-AUC 0.575–0.615 across 4 walk-forward folds plus a held-out test.
- `PromotionVerdict.NEGATIVE` on **every single split**, for both the
  trained model and the deterministic-rule benchmark it was evaluated
  against.
- Transaction costs were included in that evaluation.
- Canonical source: `docs/STRATEGY_EDGE_DISCOVERY_FINAL_OUTPUT.md`.
  Surfaced live by the running `readiness-check` CLI command itself
  (verified this cycle): *"Active strategy: trend_momentum_baseline v1.0
  -- SCIENTIFIC VERDICT: NO DEMONSTRATED EDGE."*
- This is a frozen, settled research conclusion. It has not been
  revisited, reframed, re-tuned, or re-run against the same held-out
  data at any point across this entire campaign, by explicit standing
  instruction.
- Separately: `data/predictions.db` holds 13 live forward predictions
  against real NSE symbols (entered 2026-09-03/04, 20-bar horizon); as
  of the last evaluation (2026-09-09) **all 13 remain ACTIVE with zero
  resolved outcomes** — the live calibration mechanism works, but
  produces no usable evidence yet, positive or negative.

**Evidence-hierarchy position**: Level 4 (cost-adjusted walk-forward,
negative). Levels 5–8 (out-of-sample paper trading, long-duration paper
trading, controlled live trading, statistically credible live evidence)
have not been attempted.

## 8. What does the current quantitative evidence say?

| Field | Value |
|---|---|
| Dataset | `ml_research/`'s own held-out and walk-forward splits |
| Methodology | 4 walk-forward folds + 1 held-out test |
| Leakage controls | Purge/embargo, temporal ordering — implemented and unmodified across this entire campaign (`ml_research/` is zero-diff) |
| ROC-AUC | 0.575–0.615 |
| Promotion verdict | `NEGATIVE` on every fold, model and benchmark alike |
| Transaction costs | Included in the evaluation |
| Expectancy | Not economically positive after costs (the direct basis for the NEGATIVE verdict) |
| Limitations | Single research pass; not re-run with new features/thresholds this campaign (deliberately, to avoid manufacturing a result by repeated tuning against the same test set) |

This conclusion is preserved unchanged.

## 9. Engineering readiness

**READY.**

35 adversarial hardening cycles; 2378 passing tests (final regression, 0 failed); a 110-row
executable failure-injection matrix; 39 documented, evidence-graded
failure-mode entries; systematic mutation testing (including two
instances where the campaign's own new tests were themselves caught as
initially too weak and fixed before being trusted); real OS-subprocess
and multi-thread concurrency proof for the highest-value locking
primitives; a bounded, measured soak test finding no leak (one accepted,
documented long-session limitation). All 8 sacred live-execution-safety
files (`live/dhan/broker_adapter.py`, `live/broker.py`,
`live/pipeline.py`, `decision_engine/rules.py`,
`decision_engine/engine.py`, `risk/engine.py`, `risk/sizing.py`,
`main.py`) reviewed line-by-line after every cycle; zero-diff except for
five deliberate, individually-reviewed, purely-additive changes to
`live/pipeline.py`.

## 10. Safety readiness

**READY.**

No known open HIGH or CRITICAL defect. Two CRITICAL defects were found
and fixed during this campaign, both in the live-approval/execution
path, both closed with regression tests that were mutation-tested and
shown to fail against the pre-fix code:

- **A PENDING order could fill after the kill switch or an account
  circuit breaker activated mid-flight** (cycle 24) — the live pipeline
  had no equivalent of the guard `paper/advance.py`'s batch path already
  carried; fixed with `allow_new_fill`, proven never to block managing
  an already-open position.
- **A TOCTOU window let `approve_pending()` execute after the kill
  switch activated between its ownership claim and `submit_signal()`**
  (cycle 25) — fixed with a second kill-switch check placed immediately
  before execution, proven both deterministically and with a real,
  properly-synchronized two-process race.

Live order execution remains structurally, unconditionally disabled.

## 11. Trading-strategy readiness

**INSUFFICIENT EVIDENCE** to authorize any capital deployment,
and current directional evidence is negative, not merely absent (see
Section 7).

## 12. Live-money readiness

**NOT READY**, and not attempted: real order placement is structurally
disabled by design; enabling it would require a deliberate, separate,
explicitly-authorized product decision this campaign was never asked to
make and did not make.

---

## Final capability table (summary — full detail in `FINAL_PRODUCT_CAPABILITY_MATRIX.md`)

| Capability | Implemented | Integrated | Tested | Externally Verified | Real | Safe | Production Ready | Evidence |
|---|---|---|---|---|---|---|---|---|
| Market data (Yahoo) | Yes | Yes | Yes | Yes (real provider, unofficial API) | Yes | Yes | Yes | Extensive |
| Market data (Dhan WebSocket) | Yes | Yes | Yes (fake transport) | **No** | Yes (real library) | Yes | Live-capable, not live-verified | Cycles 21/22/23/28 |
| Indicators | Yes | Yes | Yes | N/A | Yes | Yes | Yes | Cycle 10 property tests |
| Deterministic decision/risk engine | Yes | Yes | Yes | N/A | Yes | Yes, mutation-tested | Yes | Cycle 24 (17/17 mutants killed) |
| Kill switch / circuit breakers | Yes | Yes | Yes | N/A | Yes | Yes, mutation-tested | Yes | Cycles 4/24/25 |
| Paper execution | Yes | Yes | Yes | N/A | Yes | Yes | Yes | Extensive |
| Real broker execution | No (disabled by design) | No | N/A | N/A | N/A | Yes (safe by exclusion) | N/A | `RealOrderPlacementDisabledError` |
| Scheduler | Yes | Yes | Yes | Yes (real OS subprocesses) | Yes | Yes | Yes | Cycles 8/27/29 |
| Crash/restart recovery | Yes | Yes | Yes | Yes (real temp SQLite) | Yes | Yes | Yes | Cycles 8/15/20/22/26/29 |
| MCP server | Yes | Yes | Yes | N/A | Yes | Yes | Yes | Cycle 11 |
| Dashboard | Yes | Yes | Yes | N/A | Yes | Partially (no auth, deliberate) | Yes for the intended threat model | — |
| LLM/RAG | Yes | Yes | Partial | N/A | Yes | Yes (structurally excluded from risk/execution) | Yes | Zero-diff sacred files |
| Trading edge / profitability | Research attempted | N/A | Yes (walk-forward) | N/A | Yes | N/A | **No** | `PromotionVerdict.NEGATIVE` |
| Live prediction calibration | Yes | Yes | Yes (mechanism) | N/A | Yes | Yes | Data insufficient | 13 predictions, 0 resolved |

## Final remaining-risk table

| Risk | Severity | Impact | Mitigation | Acceptable? |
|---|---|---|---|---|
| Dhan data path never live-verified | MEDIUM | Real-account behavior (auth edge cases, real rate limits, real malformed frames) unproven | Extensive simulated-protocol testing; structurally cannot place real orders even if data misbehaves | Yes, for a paper-only deployment |
| No demonstrated trading edge | HIGH (to any capital-deployment decision), N/A to engineering safety | A live/paper deployment expecting profit would be unsupported by evidence | Verdict is surfaced live by the CLI itself, not hidden | Yes, as long as no capital is deployed on this basis |
| Indicator-history buffer unbounded (`_SymbolBuffer.bars`) | LOW | Memory/compute grow for a multi-month continuous session without restart | Documented; project's own operating model is per-session, not multi-month-continuous | Yes |
| Dashboard has no authentication | LOW–MEDIUM if exposed beyond loopback | Unauthorized access to a locally-reachable dashboard | Documented single-operator/loopback threat model | Yes, for the stated deployment model only |
| Fresh clean-install not re-run this specific cycle | LOW | Small chance of an undetected install-time regression | `requirements.txt` confirmed unchanged since the last full clean-install verification (cycle 18); ~15 full-suite runs on the existing venv this campaign, all passing | Yes |
| Live prediction calibration sample size (13, 0 resolved) | N/A to safety, HIGH to any calibration claim | No live accuracy claim can currently be supported | None needed — no such claim is made | Yes |

---

## Claims audit

Every claim below was checked against actual code/evidence this cycle,
not assumed from prior documentation:

- **"Live trading"**: never claimed as enabled. Correctly described
  throughout as structurally disabled.
- **"Real-time"**: not claimed for Dhan data (live-capable, not
  live-verified); Yahoo data is correctly described as delayed/EOD-
  or-intraday-batch, not tick-real-time.
- **"AI-powered"**: the LLM/RAG layer is real and integrated, but
  verified (via zero-diff sacred files across the entire campaign) to
  have no path into risk, sizing, execution, or kill-switch decisions —
  described accordingly, never as "AI execution."
- **"Exactly-once"**: never claimed. This campaign's own settled,
  evidence-backed characterization is **effectively-once** (signal_id-
  keyed idempotency, proven under concurrency and crash injection, not
  a mathematical exactly-once guarantee).
- **"Production-ready"**: used only with its scope stated —
  engineering-production-ready, explicitly NOT a claim of trading
  profitability or live-money readiness.
- **"Guaranteed"**: not used for anything this campaign could not
  actually prove (guarantees are scoped: "no duplicate execution
  proven under X conditions," never bare "guaranteed").
- **"Profitable"**: never claimed. The actual, current, negative
  verdict is stated plainly in Sections 7–8 above and by the running
  CLI itself.
- **"High accuracy"**: not claimed for the ML baseline (ROC-AUC
  0.575–0.615 is reported as-is, not characterized as "high").
- **"Autonomous trading"**: the system can autonomously generate paper
  decisions on a schedule; it cannot autonomously place a real order
  under any configuration.

---

## Known limitations (disclosed, not unsafe) — carried forward, still accurate

1. Gap detection (missing bars) in `market_data/validation.py` is a
   heuristic, not calendar-aware.
2. Broader systematic chaos testing (simulated disk-full, simulated
   multi-service simultaneous outage) beyond the targeted
   failure-injection tests was not built as a standalone suite.
3. Dashboard has no authentication — safe only for the current
   loopback/single-operator deployment model.
4. No full non-secret-scan security audit (static analysis tooling,
   dependency license audit) beyond `pip-audit` (re-run fresh this
   cycle, 53 advisories across 8 already-triaged packages, no new
   vulnerable package) and the targeted injection/credential checks.
5. SQLite stores have no automatic retention/archival policy —
   deliberately: every one is exactly the "critical trading state" this
   project's own rule forbids automatically deleting.
6. Performance profiling beyond this cycle's own bounded soak test has
   not been done.
7. `_SymbolBuffer.bars` (indicator history) has no eviction policy —
   see the remaining-risk table above.

None of the above represent unsafe behavior. Live order execution
remains structurally blocked; the deterministic risk/decision core is
untouched (zero-diff across all 35 cycles of this campaign); every
safety-critical restart/recovery/concurrency path attacked was found
already correct or was closed with a real fix, a regression test, and
mutation-test evidence.

## Remaining external dependencies

- Dhan credentials and live connectivity remain unavailable in this
  development environment.
- Yahoo Finance's continued availability and rate limits (unofficial,
  free-tier API) remain an external dependency with no official
  NSE/BSE/SEBI alternative.
- Ollama's continued availability for the critic/RAG advisory layer
  (confirmed non-blocking to the deterministic core).

---

## Definitive verdict

**Live trading: DISABLED, structurally, by design.**
**Can it place a real order: NO.**
**Is it profitable: CURRENT EVIDENCE IS NEGATIVE.**
**Engineering readiness: READY.**
**Safety readiness: READY.**
**Trading-strategy readiness: INSUFFICIENT EVIDENCE (evidence that exists is negative).**
**Live-money readiness: NOT READY.**

This is a safe, resilient, independently-operable, extensively
adversarially-hardened **paper-trading research platform**. It is not,
and does not claim to be, a demonstrated source of trading profit. The
distinction between those two things — engineering quality and trading
edge — is the single most important fact in this report, and this
campaign's entire final cycle sequence (27–35) existed specifically to
make sure that distinction was never allowed to blur.
