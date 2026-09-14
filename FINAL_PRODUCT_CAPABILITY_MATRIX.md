# Final Product Capability Matrix

Produced at the close of autonomous hardening cycle 30, against 2376
passing tests, a 110-row executable failure-injection matrix
(`tests/failure_injection/failure_matrix.yaml`), and 38 documented
failure-mode entries (`FINAL_FAILURE_MODE_ANALYSIS.md`). This document is
the authoritative capability inventory the campaign's own mission asked
for: every material capability classified against actual code and
evidence, not architecture intent.

**Status values** (no other values are used below):
`IMPLEMENTED` · `VERIFIED` · `PARTIALLY_VERIFIED` · `SIMULATED` ·
`MOCKED` · `DISABLED_BY_DESIGN` · `NOT_IMPLEMENTED` · `UNKNOWN`

A capability can carry more than one status where that's the honest
answer (e.g. `IMPLEMENTED, VERIFIED` for code that is both real and
tested; `SIMULATED, NOT LIVE-VERIFIED` for code that is real but never
run against a live external service).

---

## 1. Market data

| Capability | Status | Evidence | Limitation |
|---|---|---|---|
| Yahoo Finance intraday (5-min bars, ~60-day window) | IMPLEMENTED, VERIFIED | `market_data/providers/yahoo.py`, exercised throughout `tests/`, this campaign's own `_ScriptedStrategy`/`TrendMomentumBaseline` tests | Delayed data, not tick-level real-time |
| India VIX + NSE sector indices | IMPLEMENTED, VERIFIED | `market_intelligence/regime.py` (per prior-cycle memory, re-affirmed unchanged this campaign) | Sourced via Yahoo, not an official NSE feed |
| NSE/BSE/SEBI direct feed | NOT_IMPLEMENTED | — | No official public API exists; documented, unchanged limitation across the whole campaign |
| Dhan WebSocket live market data | IMPLEMENTED, live-capable; **NOT live-verified** | `live/dhan/market_data_source.py::_WebsocketClientTransport` (verified this session: real `websocket-client==1.9.0` library, real `WebSocketApp`, not mocked in production code) | Never run against a real Dhan account/credentials in this environment — every existing test uses `transport_factory` dependency injection with a fake transport. Evidence grade: SIMULATED / VERIFIED throughout this campaign's own failure matrix, never REAL PROVIDER / VERIFIED |
| Data validation (HEALTHY/DEGRADED/INVALID) | IMPLEMENTED, VERIFIED | `market_data/validation.py::validate_ohlcv`, wired into `market_intelligence/scanner.py`; end-to-end test proves INVALID symbols produce zero decisions/orders | — |
| Duplicate-bar rejection | IMPLEMENTED, VERIFIED | `paper/engine.py::process_bar` (Phase 7A), cycle 22/23/28 hardening; process-level and cross-source proof (cycle 28) | — |
| Out-of-order-bar rejection | IMPLEMENTED, VERIFIED | `OutOfOrderBarError`, `CandleBuilder`'s late/out-of-order guard (cycle 28's own full-pipeline proof) | — |
| Stale-bar suppression | IMPLEMENTED, VERIFIED | `live/freshness.py::FreshnessPolicy`, cycle 22 closed the stale-fill gap, cycle 24 closed the kill-switch/circuit-breaker gap for deferred fills | — |
| Bounded feed queue (memory safety) | IMPLEMENTED, VERIFIED | `DhanMarketDataSource._bar_queue`, cycle 21, drop-oldest policy, never-blocking `put_nowait()` | — |
| Reconnect / self-healing | IMPLEMENTED, VERIFIED | Cycle 8 (CONNECTING-timeout watchdog), cycle 28 (in-process reconnect + replay-rejection proven end-to-end) | Real-provider reconnect behavior itself is SIMULATED / VERIFIED only |
| Missing-bar / gap handling | IMPLEMENTED (observational only) | `paper/engine.py::_GAP_WARNING_THRESHOLD` — logs, never rejects (deliberate: "do not invent market-calendar logic") | No real market-calendar awareness (weekends/holidays are handled at the scheduler level, not the bar-gap level) |

## 2. Indicators / features

| Capability | Status | Evidence | Limitation |
|---|---|---|---|
| SMA / RSI / ATR / MACD / volume analysis | IMPLEMENTED, VERIFIED | `market/indicators.py`, 14 bounded Hypothesis property tests (cycle 10) | — |
| Indicator-history buffer integrity under duplicate/out-of-order bars | IMPLEMENTED, VERIFIED | Cycle 23's fix (buffer append gated on dedup/ordering outcome), cycle 28's cross-source re-confirmation | — |
| Regime / sector / breadth context | PARTIALLY_VERIFIED | Per prior-cycle memory: NIFTY regime wired into the critic but at WARNING severity only, downstream `DOWNGRADE == APPROVE`, so it has **zero live decision effect** today; breadth is not wired at all | Not independently re-verified this session — flagged `UNKNOWN (needs re-check)` if this exact wiring is safety-relevant to a future decision |

## 3. Strategy / signal generation

| Capability | Status | Evidence | Limitation |
|---|---|---|---|
| `TrendMomentumBaseline` (deterministic rule strategy) | IMPLEMENTED, VERIFIED | `strategy/baseline.py`, the strategy actually exercised by every scheduler/pipeline test in this campaign | This is the ACTIVE strategy for the tested paths; any other named strategy in `strategy/` not driven by `main.py`'s default wiring should be treated as EXPERIMENTAL, not independently re-audited this cycle |
| ML baseline (`ml_research/`) | IMPLEMENTED, tested, **frozen research artifact — never a production signal** | `FINAL_PRODUCT_READINESS_REPORT.md` (re-read this cycle): ROC-AUC 0.575–0.615 across 4 walk-forward folds + held-out test, `PromotionVerdict.NEGATIVE` on every split | See Section 9 (Profitability) — this is the single most important limitation in the whole matrix |
| No-trade logic | IMPLEMENTED | Risk/decision-engine veto set (structural + account-level), extensively mutation-tested cycle 24 (17/17 realistic mutants killed) | Frequency/calibration of no-trade decisions not freshly re-measured this cycle |

## 4. Decision engine / risk

| Capability | Status | Evidence | Limitation |
|---|---|---|---|
| Deterministic decision engine (no LLM in the loop) | IMPLEMENTED, VERIFIED, DISABLED_BY_DESIGN for LLM influence | `decision_engine/`, zero-diff sacred file across all 30 cycles (`git diff --stat` re-verified every cycle) | — |
| NaN/Inf rejection | IMPLEMENTED, VERIFIED, mutation-tested | `risk/engine.py` cycle 7 fix, cycle 24's 17-mutant campaign killed every realistic mutation | — |
| Structural signal validation (stop/target/side) | IMPLEMENTED, VERIFIED, mutation-tested | Cycle 24 | — |
| Account-level circuit breakers (drawdown/daily-loss/consecutive-loss) | IMPLEMENTED, VERIFIED, mutation-tested | Cycle 24 (all boundary mutants killed); cycle 24 ALSO found and fixed a CRITICAL gap where these breakers could be bypassed for a deferred PENDING-order fill in the live path | — |
| Kill switch | IMPLEMENTED, VERIFIED, mutation-tested | Cycle 4 (original), cycle 24 (deferred-fill bypass fixed), cycle 25 (TOCTOU race during `approve_pending()` fixed, both deterministically and via real 2-process/thread concurrency) | — |
| Position sizing | IMPLEMENTED, VERIFIED, mutation-tested | `risk/sizing.py`, zero-diff sacred file, cycle 24's property test `test_approved_risk_never_exceeds_the_configured_budget` | — |
| Exposure limits | IMPLEMENTED, VERIFIED, mutation-tested | Cycle 24 | — |
| Human-approval workflow | IMPLEMENTED, VERIFIED, mutation-tested | `live/pipeline.py::approve_pending/reject_pending`, cycles 19/20/23/25/26 (concurrency, crash-recovery, TOCTOU) | Structurally cannot accept a client-supplied quantity/stop/target (proven by signature inspection, `tests/test_approval_security.py`) |
| Crash-orphaned decision reconciliation | IMPLEMENTED, VERIFIED, mutation-tested | Cycle 26 — new automatic startup reconciliation, never resurrects execution | — |

## 5. Execution

| Capability | Status | Evidence | Limitation |
|---|---|---|---|
| Paper execution engine | IMPLEMENTED, VERIFIED | `paper/engine.py`, the sole execution path exercised by every test in this campaign | — |
| Paper order idempotency | IMPLEMENTED, VERIFIED, mutation-tested | Cycle 15 (TOCTOU fix), cycle 29 (composition with scheduler reclaim proven) | Effectively-once, not mathematically exactly-once — explicitly the honest characterization this campaign settled on (cycle 26) |
| Real broker order placement | **DISABLED_BY_DESIGN** | `live/dhan/broker_adapter.py::DisabledDhanOrderExecutor.place_order` unconditionally raises `RealOrderPlacementDisabledError`; verified fresh this session by reading the actual source, not documentation; not wired into any execution path anywhere | No configuration flag, environment variable, or subclass override can change this without a source-code change |
| `MockBrokerAdapter` | IMPLEMENTED, MOCKED (paper-only) | `live/broker.py` — delegates entirely to `PaperTradingEngine`, verified fresh this session | Not a broker connection of any kind — the name is a Protocol-conformance rehearsal, not real broker access |
| `DhanAccountReader` (real fund/position/holding read access) | IMPLEMENTED, live-capable, **NOT live-verified** | `live/dhan/broker_adapter.py` — genuine read-only REST calls, no mutation methods exist | Never exercised against a real Dhan account in this environment |
| Cost model (slippage, brokerage) | IMPLEMENTED | `backtesting/costs.py::CostModel`, applied in both backtest and paper fills | STT/GST/SEBI charges/stamp duty realism not freshly re-audited this cycle — flagged `UNKNOWN`, carried forward from prior campaign phases without independent re-verification here |

## 6. Persistence / recovery / concurrency

| Capability | Status | Evidence | Limitation |
|---|---|---|---|
| SQLite WAL + busy-timeout convention | IMPLEMENTED, VERIFIED | `core/sqlite_util.py`, used by every store in the project | — |
| Scheduler overlap prevention | IMPLEMENTED, VERIFIED, mutation-tested, process-level | `scheduler/store.py::try_start_run` (`BEGIN IMMEDIATE`), cycle 27's real-OS-subprocess proof | — |
| Scheduler crash/restart recovery | IMPLEMENTED, VERIFIED, mutation-tested | Cycle 8 (`reclaim_stale_locks`), cycle 29 (composed with paper-execution idempotency) | — |
| Approval-decision crash recovery | IMPLEMENTED, VERIFIED, mutation-tested | Cycle 26 | — |
| Kill-switch persistence across restart | IMPLEMENTED, VERIFIED | Cycle 8 | — |
| Position/order terminal-state guards | IMPLEMENTED, VERIFIED | Pre-campaign + reaffirmed unchanged (`InvalidPositionTransitionError`/`InvalidOrderTransitionError`) | — |
| Concurrency evidence type | Real threads AND real OS subprocesses | Threads: cycles 15/19/20/23/25. Subprocesses: cycle 27 (scheduler lock) | Not every mechanism has BOTH thread- and process-level proof; threads are the norm, subprocess-level proof is reserved for the highest-value single primitive (`try_start_run`) |

## 7. Scheduler / automation

| Capability | Status | Evidence | Limitation |
|---|---|---|---|
| `schedule tick` (single due-slot execution) | IMPLEMENTED, VERIFIED | `scheduler/runner.py::run_tick`, extensively tested | — |
| `schedule loop` (continuous polling) | IMPLEMENTED | `main.py` CLI | Long-run soak of `schedule loop` specifically not freshly re-measured this cycle (see Section 11) |
| Holiday/weekend gating | IMPLEMENTED, VERIFIED | `scheduler/config.py::ScheduleConfig.is_holiday`, `current_market_session` | — |
| Scheduler config validation (malformed YAML) | IMPLEMENTED, VERIFIED | Cycle 12 | — |

## 8. MCP / dashboard / CLI / observability

| Capability | Status | Evidence | Limitation |
|---|---|---|---|
| MCP server | IMPLEMENTED, VERIFIED | `mcp_server/server.py`, `mcp_server/observability.py`; cycle 11 closed a real crash-boundary defect (raw `ValidationError` → `ToolError`) | Every MCP tool converges on the same deterministic `RiskEngine`/kill-switch controls — verified cycle 11, not re-derived from scratch this cycle |
| Dashboard | IMPLEMENTED, VERIFIED | `dashboard/app.py`, `dashboard/intelligence.py`; feed-status, kill-switch, pending-approval display all exercised in tests | Dashboard authentication: NOT_IMPLEMENTED, deliberately deferred (single-operator, loopback-only threat model — documented in `FINAL_FAILURE_MODE_ANALYSIS.md`'s summary) |
| CLI surface | IMPLEMENTED, VERIFIED | `main.py`, ~30 real subcommands confirmed present this session (`backtest`, `paper`, `live-sim`, `paper-live`, `dashboard`, `scan`, `regime`, `daily-report`, `research`, `decide`, `size`, `predict`, `evaluate`, `learn`, `experiment`, `hypothesis-registry`, `review`, `shadow-run`, `schedule tick/loop/status`, `health`, `readiness-check`, `cache-status`, `universe`) | — |
| Health / readiness | IMPLEMENTED, VERIFIED | `core/health.py`, `main.py health`/`readiness-check`, wired into the startup gate (refuses to start `paper-live`/`schedule tick`/`schedule loop` on a FAILED critical dependency) | — |
| Prediction/outcome tracking | IMPLEMENTED, VERIFIED (mechanism); **INSUFFICIENT DATA** (calibration) | `predictions/direction_forecast.py`, `predictions/tracker.py`, `predictions/store.py`. **Directly queried `data/predictions.db` this cycle** (real local data, not memory): 13 predictions (`KOTAKBANK.NS`×6, `RELIANCE.NS`×4, `DIVISLAB.NS`×1, `GRASIM.NS`×1, `MSFT`×1), entered 2026-09-03/04, 20-bar horizon. Latest evaluation per prediction (as of 2026-09-09): **all 13 still `ACTIVE`, 0–2 of 20 bars observed, zero resolved outcomes.** | Real calibration evidence does not yet exist — the mechanism works, but no prediction has run its full horizon. Cannot support ANY calibration/accuracy claim today. |

## 9. Profitability / quantitative research

| Capability | Status | Evidence | Limitation |
|---|---|---|---|
| Walk-forward validation | IMPLEMENTED, VERIFIED | `ml_research/`, 4 folds + held-out test, re-cited from `FINAL_PRODUCT_READINESS_REPORT.md` this cycle | — |
| Leakage/purge/embargo controls | IMPLEMENTED, VERIFIED | Prior campaign phases (unchanged, zero-diff across this entire 30-cycle campaign — `ml_research/` was never touched) | — |
| Transaction-cost-adjusted evaluation | IMPLEMENTED, VERIFIED | Part of the same walk-forward evaluation producing the NEGATIVE promotion verdict | — |
| Demonstrated economic edge | **NOT_IMPLEMENTED / evidence is negative** | `PromotionVerdict.NEGATIVE` on every fold, for both the model and the deterministic-rule benchmark | This is a frozen, settled research verdict, preserved unchanged by explicit standing instruction across every cycle of this campaign — see Section "Profitability Verdict" below |
| Paper-trading track record | **NOT genuine forward paper trading — a mechanical replay-validation artifact** | **Directly queried `data/paper_trading.db` this cycle** (real local data, not memory): 32 trades, single symbol `AAPL` (a US stock, not an Indian NSE symbol), `entry_time` spanning 2021-11-18 to 2026-07-31, but every trade's `created_at` clusters within seconds of each other on 2026-08-25 — this is a BATCH REPLAY of ~5 years of cached historical AAPL data through the paper engine in one sitting (`main.py`'s `paper run` command: "Replay a symbol's cached history through the paper engine"), not live forward-looking paper trading of Indian markets. Win rate 43.75% (14/32), total net P&L **+$1,331.83 on $100,000 initial capital (+1.33% over the full replayed period)**. | This is engine-mechanics validation evidence only — single non-Indian symbol, not out-of-sample, not walk-forward, not a track record of the system's actual live decision pipeline. It must NOT be cited as paper-trading evidence of edge, and the small positive return on one replayed US symbol does not contradict, strengthen, or relate to the separate, authoritative `ml_research/` walk-forward verdict below. `data/live_sim_trading.db` (the OTHER paper engine, per project convention) is confirmed empty (0 trades) — no live-pipeline paper history exists at all yet. |

## 10. LLM / AI

| Capability | Status | Evidence | Limitation |
|---|---|---|---|
| LLM narration/explanation | IMPLEMENTED | `agents/`/narration modules referenced throughout prior campaign context | Not independently re-audited this session line-by-line |
| LLM structurally excluded from risk/execution/kill-switch/sizing | VERIFIED | `risk/engine.py`, `decision_engine/`, `risk/sizing.py` are all zero-diff sacred files across the ENTIRE 30-cycle campaign; no LLM import or call exists in any of them (verified by their own module-level docstrings and this campaign's own repeated `git diff --stat` checks) | — |

## 11. Resource exhaustion / stability

| Capability | Status | Evidence | Limitation |
|---|---|---|---|
| Bounded feed queue | IMPLEMENTED, VERIFIED | Cycle 21 | — |
| Log rotation | IMPLEMENTED, VERIFIED | Cycle 16 audit: `core/logging.py::RotatingFileHandler`, 10MB × 5 backups | — |
| Bounded retry loops | IMPLEMENTED, VERIFIED | Cycle 16 audit | — |
| Finite soak test (this campaign) | IMPLEMENTED, VERIFIED | Cycle 34 — 9,000 ticks / 3 symbols through a real `DhanMarketDataSource` -> `LiveSimPipeline` -> `PaperTradingEngine` -> SQLite chain: no thread leak, bar queue held bounded at 0/200 throughout, DB growth proportional (78 KB), memory allocation proportional to work done (`tracemalloc`) | One accepted, documented, low-severity limitation found: `_SymbolBuffer.bars` (the indicator-history buffer) has no eviction policy and grew unbounded (2,999 entries/symbol by test end); acceptable at this project's actual per-session operating scale, would only matter for a multi-month continuously-running process. See `FINAL_FAILURE_MODE_ANALYSIS.md` entry #39 |

## 12. Security

| Capability | Status | Evidence | Limitation |
|---|---|---|---|
| Dependency vulnerability triage | IMPLEMENTED, VERIFIED | Cycle 17 — 8-row `pip-audit` triage table in `SECURITY.md`, all findings assessed not-exploitable. **Fresh `pip-audit` re-run this cycle** (53 advisories, same 8 packages: `aiohttp`, `chromadb`, `torch`, `pypdf`, `langsmith`, `pydantic-settings`, `pip`, `setuptools`) — identical risk surface to cycle 17's triage, no new vulnerable package introduced since | Advisory IDs/counts shift slightly release-to-release as the vulnerability database is updated; the underlying reachability/exploitability analysis (none of these libraries process untrusted input in this project's actual usage) is unchanged and still applies |
| Secret handling | PARTIALLY_VERIFIED | No secrets committed (verified via this campaign's own git-status discipline at every commit); no dedicated fresh secret-scan run this session | — |

---

## Profitability verdict (preserved, not re-derived this cycle)

> **NO EVIDENCE OF ECONOMICALLY VIABLE EDGE IN THE CURRENT EXPERIMENT.**

ROC-AUC 0.575–0.615 across 4 walk-forward folds plus a held-out test;
`PromotionVerdict.NEGATIVE` on every split, for both the model and the
deterministic-rule benchmark. This is the correct, current, and complete
profitability conclusion. It is not weakened, reframed, or upgraded by
this document.

## Live verdict (established this cycle from direct source inspection)

- **Market data**: live-capable (Dhan WebSocket, real library), **not
  live-verified** (no credentials exercised in this environment). Yahoo
  Finance intraday is the actually-exercised data path.
- **Paper execution**: real, integrated, the sole execution path.
- **Broker execution**: implemented-and-disabled by explicit design
  (`RealOrderPlacementDisabledError`, no bypass exists).
- **Live-money operation**: not enabled, not authorized, not attempted.

## Can it actually trade?

- **Paper**: YES.
- **Broker-connected (data only)**: YES (Dhan WebSocket data, unverified
  against a live account).
- **Real-money**: NO — structurally disabled.
