# Final Product Readiness Report

Branch: `final-product-hardening`, merged forward to `main` after every
cycle (`main == origin/main` verified at every commit). Current HEAD:
`4cba014`. Companion documents: `FINAL_PRODUCT_CAPABILITY_MATRIX.md`
(the authoritative per-requirement evidence table this report
summarizes), `FINAL_FAILURE_MODE_ANALYSIS.md` (48 numbered entries),
`TRADING_STRATEGY_READINESS.md` (the seven-dimension strategy-readiness
breakdown this report's Sections 7/11 summarize), `tests/
failure_injection/failure_matrix.yaml` (110 executable rows),
`ARCHITECTURE.md`, `SECURITY.md`.

This report supersedes the version of itself written at the end of an
earlier three-pass hardening campaign (that version's own historical
content — clean-install proof, Claude-Code-independence proof, the
original documentation suite — remains true and is not re-litigated
here). Since that version, a **35-cycle autonomous adversarial
hardening campaign** ran against this same codebase, followed by a
further **"real-time strategy validation" mission** (entries #40-#48 of
`FINAL_FAILURE_MODE_ANALYSIS.md`) that built the missing bridge between
the live/paper-live path and this project's existing prediction-ledger/
outcome-resolution/statistical-evaluation machinery, and found and
closed several real, previously-undetected defects along the way:
systematic mutation testing, real OS-subprocess and multi-thread
concurrency attacks, crash/restart/recovery injection against real
temporary SQLite files, a full reality/profitability audit against the
actual local databases, and — new this mission — the first real
Dhan-account connectivity verification in this project's history. Two
of the defects found and fixed across this whole body of work reached
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
decision → paper execution → prediction ledger → automatic outcome
resolution → statistical evaluation → persistence → learning/tracking),
a deterministic risk/decision core with zero LLM involvement, a
signal_id-keyed idempotent paper-trading engine, a kill switch and
account-level circuit breakers now proven to hold even across
mid-flight process crashes and TOCTOU races, a scheduler with
process-level-proven mutual exclusion and crash recovery, a real Dhan
WebSocket data-source implementation (**REST authentication and
WebSocket connectivity now live-verified against a real account this
mission — see Section 5**), a structurally-disabled real-broker-order
path, an MCP server, a dashboard, and a ~30-subcommand CLI.

**New this mission**: `live/prediction_recorder.py` bridges the real-time
paper-live path into this project's existing (previously
scanner-research-only) immutable prediction ledger and automatic
outcome-resolution engine, opt-in via `--record-predictions`, with
automatic periodic re-evaluation (`--evaluate-every-n-bars`) so evidence
accumulates without a separate manual step. A real, previously-silent
Yahoo Finance data-availability defect that would have permanently
blocked this from ever working for intraday predictions was found and
fixed (`predictions.tracker.resolution_period_for_interval`). A real,
silent, favorable-to-profitability cost-model defect (`paper`/
`live-sim`/`paper-live` never applying real India transaction costs by
default) was found and fixed. Cycle 34's own "accepted limitation"
(`live/pipeline.py`'s unbounded indicator buffer) is now a genuine,
proven-equivalent, benchmarked fix, not a documented limitation. Full
detail: `FINAL_PRODUCT_CAPABILITY_MATRIX.md`, `FINAL_FAILURE_MODE_
ANALYSIS.md` entries #40-#48.

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
- **External-provider verification**: **performed for the first time this
  mission.** Every automated test still uses dependency-injected fake
  transports (unchanged, and correctly so — a test suite should not
  depend on live network/credentials). This mission found real Dhan
  credentials available in this environment and, with explicit user
  authorization, ran the existing `readiness-check --deep` command
  against the real Dhan API: REST authentication confirmed (real HTTP
  200 from `/fundlimit`), WebSocket connectivity confirmed (real
  `CONNECTED` state, successful subscription). See `FINAL_FAILURE_MODE_
  ANALYSIS.md` entry #45. **A follow-on, full-session market-hours live
  validation on 2026-09-15** (`docs/LIVE_MARKET_VALIDATION_REPORT_2026-09-15.md`)
  then closed the specific tick-reception gap entry #45 left open: 322
  real 1-minute bars for RELIANCE.NS across ~5.5 real market hours,
  including a real, live stale-tick event correctly suppressed by the
  freshness guard, a clean restart, and a clean recovery from an abrupt
  kill. Zero trading signals occurred that session (a real, honest null
  result) — so prediction recording, automatic resolution, and
  cost-adjusted paper execution remain unexercised under a genuinely
  live-generated signal specifically, a real, disclosed, separate gap
  from tick reception itself.
- **Crash-atomicity of the new prediction-recording write path**:
  verified against the real SQLite engine this mission, not only
  reasoned about — a manually-abandoned mid-transaction write (the exact
  state a SIGKILL leaves) produces zero partial state, and a committed
  write survives an abrupt, non-graceful connection loss. See entry #46.
- **Clean install**: re-verified for the first time since Cycle 18, this
  mission — a genuinely independent `venv` (Python 3.12.10, a different
  minor version than the dev venv's 3.14), `pip install -r
  requirements.txt` unmodified, then a real end-to-end smoke run:
  `health`, `readiness-check`, this mission's own 151 new/modified
  tests, and a full `paper-live --record-predictions` → `evaluate` cycle
  against real cached AAPL data (7 predictions recorded, all 7 resolved:
  3 TARGET_HIT, 4 STOP_HIT). One real, precisely root-caused installation
  artifact was found and correctly scoped as NOT an application defect
  (a Windows `MAX_PATH` limitation in an unrelated transitive dependency,
  triggered only by unusually deep install paths — see entry #48).
- **Mutation testing**: systematic, repeated, and — critically —
  sometimes **failed on the first attempt and was caught**: cycle 24's
  17-mutant campaign against `risk/engine.py` (all killed); cycles 27
  and 28 each independently found and fixed an initially-too-weak new
  test via this same discipline before trusting it as evidence.

## 4. What is simulated or mocked?

- **Dhan market data**: real client library (`websocket-client`), real
  WebSocket protocol handling — every AUTOMATED TEST still drives it
  through a dependency-injected fake transport (`SIMULATED / VERIFIED`
  for the test suite itself, unchanged). REST authentication, WebSocket
  connectivity, AND actual live tick reception are all now `REAL
  PROVIDER / VERIFIED` (entry #45's connectivity check, closed out by
  the 2026-09-15 full-session market-hours validation — 322 real bars).
  Trading-signal generation under that real data, and everything
  downstream of a signal (prediction recording, resolution, cost-
  adjusted paper execution), remain `SIMULATED / VERIFIED` only — the
  live session produced zero signals, so those stages were not exercised
  against real data end-to-end.
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
| Live-verified market data (REST auth + WebSocket connectivity) | **YES**, real HTTP 200 + real `CONNECTED` state against a real Dhan account (entry #45) |
| Live-verified market data (actual tick reception) | **YES — 2026-09-15**, 322 real 1-minute bars for RELIANCE.NS across a full ~5.5-hour NSE session (`docs/LIVE_MARKET_VALIDATION_REPORT_2026-09-15.md`), including a real, live stale-tick event correctly suppressed |
| Paper execution | YES, real, the sole exercised execution path |
| Broker connectivity (read-only) | Underlying REST client proven live-working this mission; `DhanAccountReader`'s own specific methods not yet directly exercised |
| Real broker order execution | **NO** — structurally, unconditionally disabled (`RealOrderPlacementDisabledError`), no bypass exists anywhere in the codebase |
| Live-money operation | **NOT ENABLED, NOT AUTHORIZED, NOT ATTEMPTED** |

## 6. Can it actually trade?

- **Paper**: **YES.**
- **Broker-connected (data only, no orders)**: **YES**, for market data
  and read-only account/fund/position access — REST authentication,
  WebSocket connectivity, AND actual live tick reception are all now
  live-verified against a real account (entry #45; 2026-09-15 full-
  session validation). The specific `DhanAccountReader` position/holding
  methods remain unverified.
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
- **New this mission**: the live/paper-live path can now ALSO contribute
  to this same evidence base (`live/prediction_recorder.py`,
  `--record-predictions`), and this project's entire statistical
  evaluation engine (`learning/analysis.py`, `learning/profitability.py`)
  was verified this mission to already generalize correctly to that new
  prediction source with zero new feature code. This closes the
  MACHINERY gap for accumulating Levels 5-8 evidence — it does not, and
  cannot by itself, produce that evidence: zero real-time paper-live
  sessions have been run outside of tests, so `data/predictions.db`
  currently holds zero live-path predictions. See
  `TRADING_STRATEGY_READINESS.md` for the full seven-dimension breakdown
  (engineering / data / strategy / statistics / paper trading / live
  verification / profitability kept explicitly separate).

**Evidence-hierarchy position**: Level 4 (cost-adjusted walk-forward,
negative). Levels 5–8 (out-of-sample paper trading, long-duration paper
trading, controlled live trading, statistically credible live evidence)
have not been attempted — the machinery to attempt them is now complete
and verified, the attempt itself has not yet been made.

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

35 adversarial hardening cycles, plus a further "real-time strategy
validation" mission (entries #40-#48) and a "multi-symbol hardening
pass" mission preparing the first 15-symbol live-paper session (entries
#49-#53); 2500 passing tests (final regression, 0 failed); a 110-row
executable failure-injection matrix; 53 documented, evidence-graded
failure-mode entries; systematic mutation testing throughout, including
this mission's own new work (period-resolution logic, cost-model
wiring, the bounded indicator buffer, and the crash-atomicity tests all
mutation-tested and confirmed-killed) and the multi-symbol hardening
pass's own six real defects (a non-atomic Dhan instrument-map cache
write, a Windows `os.replace()` concurrency bug, an environment-
inheritance bug that broke a real subprocess launch, a silent missing-
log-file gap, an undercounted bar count, and a silent CLI-subcommand
misrouting bug — each found via a real test, fixed, and mutation-
confirmed); two instances in the earlier campaign where its own new
tests were themselves caught as initially too weak and fixed before
being trusted; real OS-subprocess and multi-thread concurrency proof
for the highest-value locking primitives, now extended to the Dhan
instrument-map cache's own concurrent-download path; a bounded,
measured soak test finding no leak (one previously-accepted limitation
from that soak test — `live/pipeline.py`'s unbounded indicator-history
buffer — is now a genuine fix, not a documented limitation: bounded to
1000 bars, proven numerically equivalent to unbounded history,
benchmarked 3.10x faster / 74.4% less peak memory over 4000 bars with
throughput that stabilizes instead of degrading — see
`FINAL_FAILURE_MODE_ANALYSIS.md` entry #44). All 8 sacred
live-execution-safety files (`live/dhan/broker_adapter.py`,
`live/broker.py`, `live/pipeline.py`, `decision_engine/rules.py`,
`decision_engine/engine.py`, `risk/engine.py`, `risk/sizing.py`,
`main.py`) reviewed line-by-line after every cycle across both the
original campaign and every mission since; `live/pipeline.py` in
particular remained a hard zero-diff through the entire multi-symbol
hardening pass, per that mission's own explicit constraint (multi-
symbol operation is achieved via N independent single-symbol processes,
never a single process modified to juggle several symbols — see entry
#51); every diff to any of them additive, opt-in-gated, and reviewed
before commit.

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
Section 7). See `TRADING_STRATEGY_READINESS.md` for the full breakdown
across the seven dimensions this mission's own spec requires kept
separate (engineering / data / strategy / statistics / paper trading /
live verification / profitability) plus the required evidence table (OOS
performance, walk-forward, costs, slippage, calibration, positive
expectancy, drawdown, regime robustness, paper track record, statistical
confidence, live validation).

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
| Market data (Dhan WebSocket) | Yes | Yes | Yes (fake transport) | **REST auth + connectivity + tick reception: all Yes** | Yes (real library) | Yes | Connectivity and tick reception both live-verified | Cycles 21/22/23/28; entry #45; 2026-09-15 session |
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
| Live prediction calibration (research path) | Yes | Yes | Yes (mechanism) | N/A | Yes | Yes | Data insufficient | 13 predictions, 0 resolved |
| Live prediction calibration (live/paper-live path) | Yes (new this mission) | Yes (`--record-predictions`) | Yes (unit + real-CLI end-to-end) | N/A | Yes | Yes | Data does not yet exist (0 live sessions run) | Entries #40/#41/#46 |
| Cost model realism (paper/live-sim/paper-live) | Yes (new this mission) | Yes (`--cost-model`) | Yes, mutation-tested | N/A | Yes | Yes | Yes, opt-in | Entry #43 |
| Bounded indicator-history buffer | Yes (new this mission) | Yes | Yes, mutation-tested + benchmarked | N/A | Yes | Yes | Yes | Entry #44 |

## Final remaining-risk table

| Risk | Severity | Impact | Mitigation | Acceptable? |
|---|---|---|---|---|
| Live-generated trading signal, prediction recording, and cost-adjusted execution never exercised together against real market data | MEDIUM (was: tick reception itself, now closed 2026-09-15) | 322 real bars, real tick reception, real freshness enforcement (including one genuine live stale-tick event, correctly suppressed) are ALL now live-verified; zero trading signals occurred that session, so the downstream chain (prediction ledger -> resolution -> cost-adjusted P&L) has not yet been exercised end-to-end against a live-generated signal specifically | Mechanism independently verified via cached historical data and a clean-install smoke run (entries #40/#41/#48); structurally cannot place real orders even if a live signal does occur; further live sessions (ideally on a trending day, or a broader universe) would close this | Yes, for a paper-only deployment |
| A real, unexplained ~15-minute Dhan tick-delivery gap occurred near market close (2026-09-15), with `state` remaining `CONNECTED` throughout (not a reported disconnect) | LOW-MEDIUM | If recurring, a gap like this would not be visible as a "disconnected" state on the dashboard/health check, only as an absence of new bars; the existing freshness guard safely suppressed the one late bar that arrived, so no incorrect trade could have resulted | Root cause undetermined (Dhan-side, out of this project's visibility); recommend instrumenting explicit bar-to-bar inter-arrival monitoring for future sessions, per `docs/LIVE_MARKET_VALIDATION_REPORT_2026-09-15.md`'s own recommendation | Yes — safely absorbed by an existing control, disclosed rather than hidden |
| No demonstrated trading edge | HIGH (to any capital-deployment decision), N/A to engineering safety | A live/paper deployment expecting profit would be unsupported by evidence | Verdict is surfaced live by the CLI itself, not hidden; `TRADING_STRATEGY_READINESS.md` states it explicitly across every relevant dimension | Yes, as long as no capital is deployed on this basis |
| Dashboard has no authentication | LOW–MEDIUM if exposed beyond loopback | Unauthorized access to a locally-reachable dashboard | Documented single-operator/loopback threat model | Yes, for the stated deployment model only |
| Clean install on an unusually deep Windows install path can hit a `langsmith`/`xxhash` `MAX_PATH` DLL-load failure | LOW | `ollama` reports DEGRADED via a DLL error instead of the normal "not reachable" message, and pytest's own plugin autoload can crash collection, ONLY when installed under an install path within a few characters of Windows' 260-char `MAX_PATH` limit | **Re-verified this mission with a genuine fresh install** (entry #48): root-caused to an unrelated `langsmith` transitive dependency, not this project's own code; the project's own real dev venv path (155 chars) is unaffected; `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` works around it for tests specifically | Yes -- avoid extremely deep install paths; not a code defect |
| Live prediction calibration sample size — research path (13, 0 resolved) AND live path (0 predictions, 0 sessions run) | N/A to safety, HIGH to any calibration claim | No live accuracy claim can currently be supported for either source | None needed — no such claim is made; the live-path machinery to accumulate this evidence is now complete and verified (entries #40/#41/#46) | Yes |
| No GST/stamp duty in the India cost-model preset | LOW | `--cost-model india_nse_intraday_2026` slightly understates real costs even when explicitly opted into | Documented, disclosed in the preset's own docstring and every startup print | Yes |

---

## Claims audit

Every claim below was checked against actual code/evidence this cycle,
not assumed from prior documentation:

- **"Live trading"**: never claimed as enabled. Correctly described
  throughout as structurally disabled.
- **"Real-time"**: connectivity (REST auth + WebSocket) AND actual live
  tick data flowing through the full bar-construction/freshness pipeline
  are both now live-verified for Dhan (entry #45; 2026-09-15 session,
  322 real bars). What is NOT yet claimed: a live-generated trading
  signal flowing all the way through prediction recording, resolution,
  and cost-adjusted execution — that specific chain has not occurred
  against real data yet (zero signals in the one live session run so
  far), and this report does not claim otherwise. Yahoo data is
  correctly described as delayed/EOD-or-intraday-batch, not
  tick-real-time.
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
6. Performance profiling beyond this cycle's own bounded soak test and
   this mission's own before/after buffer-bound benchmark has not been
   done.
7. ~~`_SymbolBuffer.bars` (indicator history) has no eviction policy~~ —
   **CLOSED this mission**, see `FINAL_FAILURE_MODE_ANALYSIS.md` entry
   #44 and the remaining-risk table above (now removed from that table).
8. GST and stamp duty are not modeled even in the `india_nse_intraday_
   2026` cost preset — a documented, disclosed approximation.
9. ~~Live Dhan tick reception has not been verified end-to-end~~ —
   **CLOSED 2026-09-15**: a full-session market-hours `paper-live
   --source dhan` run processed 322 real bars across ~5.5 hours,
   including a real, live stale-tick event correctly suppressed by the
   freshness guard. See `docs/LIVE_MARKET_VALIDATION_REPORT_2026-09-15.md`.
10. Installing this project at an unusually deep Windows filesystem path
    (within a few characters of the 260-char `MAX_PATH` limit) can
    trigger a DLL-load failure in an unrelated `langsmith` transitive
    dependency (`ollama` shows DEGRADED via a DLL error instead of the
    normal message; pytest's plugin autoload can crash). Re-verified
    this mission (entry #48) as NOT a defect in this project's own code
    — the project's own real install path is well under the limit and
    unaffected; disclosed as installation guidance.
11. A prediction recorded by the live `paper-live --record-predictions`
    path, its automatic outcome resolution, and cost-adjusted paper
    execution have never yet occurred together against a real,
    live-generated trading signal — the one full-session live validation
    run (2026-09-15) produced zero signals (a genuine null result, not a
    failure). The underlying mechanism is separately verified via cached
    historical data and a clean-install smoke run (entries #40/#41/#48).
12. A real, unexplained ~15-minute Dhan tick-delivery gap occurred near
    market close during the 2026-09-15 session, with the feed's own
    reported `state` remaining `CONNECTED` throughout (not a reported
    disconnect). Safely absorbed by the existing freshness guard (the
    one late bar that arrived was correctly suppressed, not traded on);
    root cause undetermined (Dhan-side, outside this project's
    visibility). See that report's own dedicated section and
    recommendation.
13. Python's own stdout block-buffering, when `paper-live`'s output is
    redirected to a file (the only practical way to run an unattended
    multi-hour session), can hide live progress for up to roughly two
    hours before a natural flush — found and fixed live, this is an
    invocation-time concern (`PYTHONUNBUFFERED=1` / `python -u`), not an
    application defect; documented as the correct operational practice
    for any future long-running, log-redirected live session.

None of the above represent unsafe behavior. Live order execution
remains structurally blocked; the deterministic risk/decision core is
untouched (zero-diff across all 35 cycles of the original campaign and
every cycle of this mission); every safety-critical restart/recovery/
concurrency path attacked was found already correct or was closed with
a real fix, a regression test, and mutation-test evidence.

## Remaining external dependencies

- Dhan credentials became available in this environment for the first
  time this mission, and REST authentication, WebSocket connectivity,
  AND actual live tick reception are all now live-verified (entry #45;
  2026-09-15 full-session validation) — but there is no guarantee these
  credentials remain valid or present in any future environment.
- Yahoo Finance's continued availability and rate limits (unofficial,
  free-tier API) remain an external dependency with no official
  NSE/BSE/SEBI alternative. A real, previously-undetected Yahoo Finance
  data-availability limit for intraday intervals was found and worked
  around this mission (entry #41) — Yahoo genuinely does not retain
  1-minute bars older than ~8 days, a hard external constraint, not a
  bug.
- Ollama's continued availability for the critic/RAG advisory layer
  (confirmed non-blocking to the deterministic core).

---

## Definitive verdict

**Live trading: DISABLED, structurally, by design.**
**Can it place a real order: NO.**
**Is market data connectivity live-verified: YES — REST auth, WebSocket connection, AND actual live tick reception (322 real bars, ~5.5-hour NSE session, 2026-09-15).**
**Is it profitable: CURRENT EVIDENCE IS NEGATIVE.**
**Engineering readiness: READY.**
**Safety readiness: READY.**
**Trading-strategy readiness: INSUFFICIENT EVIDENCE (evidence that exists is negative).**
**Live-money readiness: NOT READY.**

This is a safe, resilient, independently-operable, extensively
adversarially-hardened **paper-trading research platform**, now with a
real, verified, end-to-end bridge from real-time signal generation
through immutable prediction recording, automatic outcome resolution,
and statistical evaluation — machinery this mission built, fixed real
defects in, proved generalizes correctly, and has now been run for a
full real NSE market session (322 real bars, one clean restart, one
clean recovery from an abrupt kill, one real stale-tick event safely
suppressed). What has NOT yet happened: a live-generated trading signal
flowing through that full chain — the one live session run so far
produced zero signals, an honest null result, not a failure, and not
grounds to claim more than was observed. It is not, and does not claim
to be, a demonstrated source of trading profit. The distinction between
those two things — engineering quality and trading edge — is the single
most important fact in this report, and this campaign's original final
cycle sequence (27–35), this mission's own work, and the 2026-09-15
live session all existed specifically to make sure that distinction was
never allowed to blur. See `TRADING_STRATEGY_READINESS.md` and
`docs/LIVE_MARKET_VALIDATION_REPORT_2026-09-15.md` for the complete,
dimension-by-dimension and session-by-session statements of this same
fact.
