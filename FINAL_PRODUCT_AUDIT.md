# Final Product Audit

A fresh system map for the "final product" hardening phase, on branch
`final-product-hardening`. Builds on, does not blindly trust,
`AUDIT_BASELINE.json`/`AUDIT_GAPS.md` (the Phase 0.5 forensic audit) --
every claim below is re-verified against the repository as it stands
now, after this session's hardening changes, not assumed carried over.

Companion documents: `FINAL_FAILURE_MODE_ANALYSIS.md`,
`FINAL_PRODUCT_READINESS_REPORT.md` (the release gate verdict).

---

## 1. System component map

| Component | Current state | Key dependencies | Test coverage | Production readiness |
|---|---|---|---|---|
| CLI (`main.py`) | Working, ~30 subcommands | argparse only | Extensive (`tests/test_cli*.py`) | High |
| Dashboard (`dashboard/app.py`) | Working, 7 Starlette routes, server-rendered HTML | `paper/`, `live/`, `decision_engine/` stores | `tests/test_dashboard*.py` | High for local/loopback use; no auth if exposed off-loopback (disclosed, accepted for the stated threat model) |
| MCP server (`mcp_server/server.py`) | Working, 23 read/paper-only tools, zero order-placement tools | `paper/`, `live/workstation.py` | `tests/test_mcp_*.py` | High |
| Scheduler (`scheduler/`) | Working, hardened this session (setup-phase exception boundary added) | `SchedulerRunStore` | `tests/test_scheduler_*.py`, 1 new failure-injection test | Medium -- no per-job timeout, no fairness guarantee across overlapping custom-config windows (disclosed, not fixed this session) |
| Risk engine (`risk/engine.py`) | Working, deterministic, unmodified this session | `risk/config.py` | Extensive | High |
| Paper trading (`paper/`) | Working, hardened across two passes (WAL, busy timeout, integrity_check; position state machine now guarded -- CLOSED enforced as terminal, `InvalidPositionTransitionError` on a double-close/reopen attempt) | `PaperStore`, `backtesting/execution.py` | Extensive, incl. real restart tests and a new state-transition guard test | High |
| Market data quality (`market_data/validation.py`, new) | Working: series-level HEALTHY/DEGRADED/INVALID validation (duplicates, ordering, gaps, symbol identity, staleness), gating `market_intelligence/scanner.py`'s scan -> decision -> paper-trade path; `market/data_provider.py::OHLCV.from_dataframe` also drops rows with an impossible OHLC relationship | `live/freshness.py`, `core/timeutil.py` | New, dedicated (34 tests across `tests/test_market_data_validation.py`, `tests/test_market_data.py`, `tests/test_market_intelligence_scanner.py`) | High for what it covers; offline `ml_research`/`quant_research` paths not yet gated (disclosed) |
| Live pipeline (`live/`) | Working (paper-execution-only), unmodified this session except `_naive`→`to_naive` delegation (zero behavior change, verified) | `LiveStateStore`, Dhan adapters | Extensive | High for safety; Dhan real-connectivity itself untested in this environment (no credentials) |
| Dhan integration (`live/dhan/`) | Real order execution structurally disabled (independently re-verified twice this session's predecessor phases); WebSocket/REST code unmodified this session | Dhan credentials (absent in this environment) | Extensive, incl. a dedicated "critical safety test" | High for safety; live connectivity unverified here |
| Decision engine (`decision_engine/`) | Working, deterministic, unmodified this session | Scanner, research stores | Extensive | High |
| ML research (`ml_research/`) | Working, offline/research-only, architecturally isolated (Phase 1 of this project's own prior work) | scikit-learn, pyarrow | 15 leakage tests, a release gate | High for what it is (a research pipeline, not a live component) |
| Quant research (`quant_research/`) | Working, offline/research-only, architecturally isolated | pandas/numpy | Extensive | High for what it is |
| Databases (12 SQLite stores) | **Hardened across two passes**: WAL mode + 30s busy timeout on all 12; `PRAGMA integrity_check`/`db_size_bytes` now on **all 12** (closed a 3/12 gap); `predictions`/`direction_forecast` stores gained a real DB-level `UNIQUE(symbol, entry_time\|as_of)` constraint (migrated, backfilled, gracefully soft-fails on pre-existing duplicate data); shared `ensure_column`/`try_create_unique_index` migration primitives now exist in `core.sqlite_util`, used by 3/12 stores | sqlite3 stdlib | Extensive, plus `tests/test_core_sqlite_util.py` (incl. a real concurrent-reader-not-blocked-by-writer test) and new migration/duplicate-prevention tests across `predictions`/`direction_forecast` stores | Medium-High -- meaningfully improved; no `PRAGMA user_version`/schema-version tracking anywhere, and a migration mechanism beyond additive-column exists on only 3/12 stores, remain real, disclosed gaps |
| Datetime handling | **Hardened this session**: consolidated from 4+ independently-duplicated `_naive`/`_naive_utc` helpers (one file had two different ones) across 10+ files into `core/timeutil.py`, with a documented two-case policy | pandas | New `tests/test_core_timeutil.py` (13 tests) + every existing call site's own pre-existing coverage, re-verified passing | High -- the recurring bug CLASS (Phase 33/37/42) is now centralized, not merely patched a 4th time |
| Cache staleness | **Fixed this session, not patched**: the real bug behind 3 previously-"pre-existing" test failures (`report_cache_staleness`'s `cache_root` was a bound default `main.py` never threaded through, defeating test isolation) is fixed via a new `--cache-root` CLI flag; the duplicated, drift-prone `STALE_DATA_END_SECONDS` literal now imports `critic/config.py`'s own value instead of a second hardcoded copy | `backtesting/cache.py`, `critic/config.py` | 3 tests rewritten to be fully hermetic (no dependency on real on-disk `data/market/` freshness) | Medium -- the underlying "4 call sites, 3 thresholds, 2 timestamp bases" inconsistency (`daily-report` vs `cache-status` vs `readiness-check` vs `critic`) is now down to 3 call sites sharing one canonical value for `daily-report`, but `cache-status`'s 30-day and `readiness-check`'s hardcoded 7-day thresholds remain separate, undocumented-as-intentional divergences -- a real, disclosed remaining gap |
| Security posture | Unchanged from `docs/SECURITY_REVIEW.md`'s own prior findings (SQL injection clean, XSS clean, path traversal fixed, secrets-in-git-history clean) -- re-spot-checked this session's own new code (no SQL string interpolation introduced, no secrets touched) | -- | `tests/test_dhan_no_real_orders.py`, `tests/test_dhan_credential_security.py` | High |
| Documentation | `README.md` exists and is extensive; `PROJECT_GOAL_AND_ROADMAP.md`, `docs/PHASE_HISTORY.md`, and 40+ phase-report docs exist. **No dedicated `INSTALLATION.md`/`USER_GUIDE.md`/`OPERATIONS_GUIDE.md`/`TROUBLESHOOTING.md`/`ARCHITECTURE.md`/`SECURITY.md` exist as the mission requests** | -- | N/A | Low against the mission's own specific documentation-suite requirement; Medium against "can a reader understand the system" (README is genuinely thorough) |
| Observability | `docs/OBSERVABILITY.md` documents an existing, real, targeted addition (candle-builder rejection counters); no consolidated health-dashboard/single-command health-check exists across every subsystem the mission names (data/model/database/scheduler/prediction/decision/paper-trading health as ONE view) | -- | Partial (`readiness-check`, `cache-status` exist as separate commands) | Medium -- real pieces exist, not unified |

## 2. Failure modes -- see `FINAL_FAILURE_MODE_ANALYSIS.md` for the full table

## 3. What changed in the first hardening pass (commit `30242e5`; summary -- full detail in the commit message itself)

1. `core/timeutil.py` (new) -- consolidates the naive/aware datetime normalization policy, replacing 4+ independently-duplicated implementations across 10 files with two documented, tested functions (`to_naive`, `as_utc_aware`) plus a third for the DataFrame-index-matching case (`match_index_awareness`).
2. `core/sqlite_util.py` (new) -- consolidates SQLite connection setup (WAL mode + 30s busy timeout) and integrity-check/size-reporting capability, replacing 12 independent `sqlite3.connect(...)` call sites and de-duplicating `scheduler/store.py`'s own prior `integrity_check`/`db_size_bytes` implementation.
3. `main.py`'s `daily-report` cache-staleness check: real bug fixed (bound-default `cache_root` parameter), not a symptom patch -- new `--cache-root` flag, and the threshold now imports `critic/config.py`'s own value instead of a duplicated literal.
4. `scheduler/runner.py`: the tick-setup phase (lock reclaim, active-lock check, slot selection, lock acquisition) is now wrapped in its own exception boundary, closing a real gap where an unexpected failure there (e.g. a database error under contention) would previously propagate uncaught out of `run_tick` -- surfaced in `schedule tick`'s own single-shot CLI invocation as a raw crash, not just a scheduler-loop concern.
5. `paper/store.py` and `live/state_store.py` gained `integrity_check()`/`db_size_bytes()` methods (previously only `scheduler/store.py` had this capability, despite these two being the most safety-critical stores in the project).
6. `tests/test_daily_report.py`'s 3 previously-"pre-existing, unrelated" failures are now genuinely fixed at the root cause, with tests rewritten to be fully hermetic.

Full regression after every change above: **1976 passed, 0 failed** (baseline before this pass's hardening work: 1963 collected, 1960 passed / 3 failed from the pre-existing cache-staleness bug -- now 0 failed).

## 3b. What changed in the second hardening pass, the release-gate follow-up (commit `c470305`)

1. `market_data/validation.py` (new) -- series-level OHLCV data-quality validation (HEALTHY/DEGRADED/INVALID), wired into `market_intelligence/scanner.py`'s `_screen_symbol`/`_fetch_benchmark` so INVALID data is excluded before any decision-relevant computation sees it. `market/data_provider.py::OHLCV.from_dataframe` also now drops individual rows with an impossible OHLC relationship.
2. Two missed datetime-normalization duplication spots (`dashboard/app.py`, `live/dhan/clock_skew.py`) migrated to `core.timeutil.as_utc_aware`.
3. `paper/store.py::update_position()` now guards CLOSED as a terminal position state, raising a new `paper.errors.InvalidPositionTransitionError` on a double-close/reopen attempt instead of silently allowing it.
4. `predictions/store.py` and `predictions/direction_forecast_store.py` now enforce real DB-level `UNIQUE(symbol, entry_time)`/`UNIQUE(symbol, as_of)` constraints via a migration (backfilled from each row's own `data_json`, gracefully soft-failing on pre-existing duplicate data rather than crashing startup or deleting rows). New shared `core.sqlite_util.ensure_column`/`try_create_unique_index` back this; `live/state_store.py`'s own prior private `_ensure_column` now delegates to the same shared helper.
5. `integrity_check()`/`db_size_bytes()` extended from 3 of 12 stores to **all 12**.
6. Found and fixed via the regression discipline itself: 6 pre-existing test fixtures (`test_predictions_store.py`, `test_cli_experiment.py`) relied on a hardcoded, identical `entry_time` across multiple same-symbol predictions -- data no real caller could legitimately produce, now correctly rejected by the new DB constraint. Fixtures corrected to vary `entry_time`, the constraint itself was not weakened.

Full regression after every change above: **2035 passed, 0 failed**.

## 3c. What changed in the third hardening pass, the final release-gate campaign (commits `339e16a` through `7ac5a33`)

1. Schema-version tracking (`PRAGMA user_version`) wired into all 12 stores via new shared `core.sqlite_util.get_schema_version`/`set_schema_version`/`ensure_schema_version`, closing the migration-mechanism gap the second pass left open.
2. `scheduler/config.py::ScheduleSlot` gained `__post_init__` validation (a real config-logic gap: an inverted/zero-width eligibility window or a non-positive `frequency_minutes` previously produced a slot that could never become due, silently).
3. Two real restart-recovery gaps closed (found by a dedicated coverage survey): scheduler lock reclamation across a REAL process restart, and duplicate-bar-replay-after-restart.
4. A new, real end-to-end test proves invalid market data can never produce a decision/prediction/paper order, through the actual `run_shadow_run_command --paper-execute` path, not a reimplementation.
5. New `core/health.py` -- one unified health model consumed identically by a new `python main.py health` command and a new dashboard `/health` route.
6. A real `pip-audit` dependency scan found and fixed one exploitable-in-principle CVE (`langchain`, bumped as defense-in-depth) and disclosed two more confirmed not exploitable in this project's actual usage (`chromadb`'s networked-server CVEs -- this project only uses it embedded/local).
7. A genuine clean-install test (fresh clone, fresh venv, one `pytest` run) found and fixed a real dependency-pin defect (`langchain-core` pinned below what the `langchain` bump above actually required) invisible to the already-upgraded dev venv.
8. A provider-failure-matrix survey (16 named scenarios) found 9 already tested and closed the 4 genuinely missing, including one real code defect: `live/dhan/rest_client.py::DhanRestClient._get()` let a transport-level exception propagate raw instead of wrapping it in `DhanRestError` like every other provider in the project.
9. New `main.py::_run_startup_gate` -- `paper-live`/`schedule tick`/`schedule loop` now refuse to start if a critical dependency is broken (SAFE_STOP), consuming the same unified health model.
10. Full documentation suite written: `INSTALLATION.md`, `USER_GUIDE.md`, `OPERATIONS_GUIDE.md`, `TROUBLESHOOTING.md`, `ARCHITECTURE.md`, `SECURITY.md`.

Full regression after every change above: **2120 passed, 0 failed**. Live-order-execution safety path re-confirmed untouched via `git diff --stat` after every one of these commits.

## 4. What this audit did NOT re-derive from scratch

Given the volume of already-verified findings in `AUDIT_BASELINE.json`
(kill-switch persistence, live-order-execution structural disablement,
XSS/SQL-injection/path-traversal cleanliness, the RAG/LLM architecture,
the decision-vector reconstruction), this audit re-verified only what
this session's own changes could plausibly have affected (via `git diff
--stat main`, confirming exactly which 28 files changed and that none
of them touch `live/dhan/broker_adapter.py`, `live/broker.py`,
`live/pipeline.py`'s execution logic, `decision_engine/rules.py`, or
`risk/engine.py`'s sizing/veto logic) rather than re-running a full
independent audit of unchanged subsystems. This is a deliberate,
disclosed scope choice, not an oversight.
