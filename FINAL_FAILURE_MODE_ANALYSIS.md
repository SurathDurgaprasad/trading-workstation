# Final Failure Mode Analysis

Each scenario: FAILURE -> DETECTION -> SAFE RESPONSE -> RECOVERY -> USER
VISIBILITY. Evidence is labeled per scenario as one of:
**[VERIFIED-TEST]** (a real test exercises this, cited by path),
**[VERIFIED-CODE]** (confirmed by direct code reading this session, no
test forces the path), or **[ASSUMED]** (plausible from architecture,
not independently re-confirmed this session). See `FINAL_PRODUCT_AUDIT.md`
for the component map this analysis is built against.

---

### 1. Market data provider (yfinance) unreachable or returns an error

- **FAILURE**: network outage, yfinance API change, rate limiting.
- **DETECTION**: `YahooFinanceProvider` calls raise; callers catch exceptions at the fetch boundary.
- **SAFE RESPONSE**: `CachedMarketDataProvider` falls back to last-known-good cached data; scanner/decision paths that require fresh data refuse to produce a signal rather than using stale data silently mislabeled as fresh (staleness is checked, not ignored).
- **RECOVERY**: automatic on next successful fetch; no manual intervention needed.
- **USER VISIBILITY**: `cache-status` and `daily-report` surface staleness explicitly; dashboard shows data age.
- **Evidence**: **[VERIFIED-CODE]** (`backtesting/cache.py`, `market/data_provider.py` read this session) + pre-existing test coverage for cache fallback. Not re-run live against an actual yfinance outage this session.

### 2. Malformed or impossible OHLCV data (e.g., high < low, non-monotonic timestamps, duplicate bars)

- **FAILURE**: upstream data provider returns corrupt or out-of-order data.
- **DETECTION**: **partial** -- candle-builder rejection counters exist (`docs/OBSERVABILITY.md`) for the live tick path; no equivalent explicit OHLC-sanity validation layer exists for the historical/cache data path.
- **SAFE RESPONSE**: not formally defined as a deterministic health-status model (FRESH/STALE/INVALID) for this specific failure class.
- **RECOVERY**: N/A -- undefined.
- **USER VISIBILITY**: none dedicated.
- **Evidence**: **[ASSUMED]** gap, disclosed. This is the mission's own explicitly-named "data-quality layer" requirement (mission section on data-quality) and remains unimplemented this session. **This is a real, open P1 item**, not fabricated as solved.

### 3. LLM/RAG provider (Claude API) unreachable, rate-limited, or returns malformed output

- **FAILURE**: API outage, auth failure, malformed JSON response from the model.
- **DETECTION**: try/except around LLM calls in the critic/RAG layer.
- **SAFE RESPONSE**: the deterministic decision core does not depend on LLM output for BUY/SELL/HOLD -- LLM-derived context (e.g. critic narrative) is advisory/explanatory, not gating, confirmed by the earlier context-pipeline audit finding that market-context severity is capped at WARNING and WARNING does not block APPROVE. LLM failure should not prevent a decision from being reached.
- **RECOVERY**: automatic retry or graceful omission of the LLM-derived field on next cycle.
- **USER VISIBILITY**: partial -- an LLM failure is logged, not surfaced as a first-class dashboard status.
- **Evidence**: **[VERIFIED-TEST]** `tests/test_failure_handling.py::test_rag_store_not_found_gives_actionable_error` (seen in this session's regression output) covers one RAG failure path. The broader "LLM DOWN -> SYSTEM CONTINUES" claim is **[VERIFIED-CODE]** by architecture (decision path does not call the LLM), not independently re-tested end-to-end this session with the API forcibly disabled.

### 4. Dhan broker unreachable / WebSocket disconnect

- **FAILURE**: network issue, Dhan-side outage.
- **DETECTION**: connection-state tracking in `live/dhan/` adapters.
- **SAFE RESPONSE**: no order placement is attempted without a live, authenticated session; paper-execution continues unaffected since it never touches Dhan.
- **RECOVERY**: reconnect logic exists in the adapter layer (not re-verified against a real Dhan outage this session -- no credentials in this environment).
- **USER VISIBILITY**: connection status in live-state.
- **Evidence**: **[ASSUMED]**, consistent with prior-session code reading; **not independently re-verified this session** (no Dhan credentials available in this environment).

### 5. Live order execution attempted despite structural disablement

- **FAILURE**: a code path attempts to place a real order.
- **DETECTION**: `tests/test_dhan_no_real_orders.py` -- a dedicated "critical safety test" asserting the real-order code path is unreachable/disabled.
- **SAFE RESPONSE**: order placement is structurally blocked regardless of credentials, reachability, or model output ("LIVE ORDER -> BLOCKED BY DEFAULT" is enforced in code, not just policy).
- **RECOVERY**: N/A -- this is a permanent safety invariant, not a recoverable-from state.
- **USER VISIBILITY**: any attempted live order would raise/log loudly rather than silently no-op.
- **Evidence**: **[VERIFIED-TEST]** `tests/test_dhan_no_real_orders.py` (ran clean in both this session's regression runs: 1976 and 1989 passed). This session's own `git diff --stat main` confirmed zero changes to `live/dhan/broker_adapter.py`, `live/broker.py`, `live/pipeline.py`, `decision_engine/rules.py`, `risk/engine.py` -- the live-execution-safety path is untouched by this session's work.

### 6. SQLite database corruption

- **FAILURE**: disk error, power loss mid-write, filesystem issue.
- **DETECTION**: `PRAGMA integrity_check`, now exposed via `core.sqlite_util.integrity_check()` on 3 of 12 stores (scheduler, paper, live_state -- the three most safety/state-critical).
- **SAFE RESPONSE**: not automatically invoked on every startup; an operator must run the check explicitly (no automatic startup self-diagnostic wired to it yet).
- **RECOVERY**: manual -- restore from a backup or accept data loss on the affected store; no automated repair.
- **USER VISIBILITY**: only if the operator runs the check.
- **Evidence**: **[VERIFIED-CODE]** the capability exists and is tested (`tests/test_core_sqlite_util.py`, plus new tests in `test_paper_store.py`/`test_live_state_store.py` this session, both passing). **Gap, disclosed**: not wired into automatic startup diagnostics; 9 of 12 stores still lack the capability entirely.

### 7. SQLite lock contention (scheduler + dashboard + CLI concurrent access)

- **FAILURE**: two processes touch the same DB file simultaneously.
- **DETECTION**: `sqlite3.OperationalError: database is locked` would previously surface at the default 5s stdlib timeout.
- **SAFE RESPONSE**: **fixed this session** -- WAL mode (concurrent readers do not block on an in-progress writer, verified by a real threading test) + 30s busy_timeout (vs. the previous 5s default) on all 12 stores, reducing but not eliminating lock-contention failures under sustained concurrent load.
- **RECOVERY**: automatic once the contending transaction completes, within the timeout window.
- **USER VISIBILITY**: an unresolved lock past 30s still raises, visibly, rather than hanging silently.
- **Evidence**: **[VERIFIED-TEST]** `tests/test_core_sqlite_util.py` includes a genuine concurrent-reader-not-blocked-by-writer test using real threads, not a mock.

### 8. Disk full / write failure

- **FAILURE**: host disk fills up (market data cache, DB growth, logs).
- **DETECTION**: none dedicated -- would surface as a raw `OSError`/`sqlite3.OperationalError` at the point of write.
- **SAFE RESPONSE**: undefined; no disk-space health check exists.
- **RECOVERY**: manual (operator frees space).
- **USER VISIBILITY**: only via the raw exception in logs.
- **Evidence**: **[ASSUMED]** gap, disclosed. Not addressed this session; a real, open item under "resource-safety monitoring" from the mission.

### 9. Scheduler job raises an unexpected exception mid-slot

- **FAILURE**: any exception inside `_execute_slot` (e.g. a downstream command failure).
- **DETECTION**: pre-existing `except (Exception, SystemExit)` boundary around `_execute_slot` specifically (with its own documented historical incident: an uncaught `SystemExit` previously orphaned a lock).
- **SAFE RESPONSE**: the run is marked FAILED, the lock is released; the scheduler loop itself is not killed.
- **RECOVERY**: automatic on the next scheduled tick.
- **USER VISIBILITY**: `schedule status`/`list_runs` shows the FAILED run with an error message.
- **Evidence**: **[VERIFIED-TEST]** pre-existing coverage in `tests/test_scheduler_runner.py`, re-confirmed passing in both regression runs this session. Unmodified this session.

### 10. Scheduler tick-setup phase raises (lock reclaim, holiday check, slot selection)

- **FAILURE**: e.g. a database error while checking `active_lock()` before any slot has even started.
- **DETECTION**: previously **undetected as a distinct case** -- this code ran outside the `_execute_slot` exception boundary and could propagate uncaught out of `run_tick`, crashing a single `schedule tick` CLI invocation.
- **SAFE RESPONSE**: **fixed this session** -- the entire setup phase is now wrapped in its own outer exception boundary, returning a clean `TickResult(ran=False, reason=...)` instead of raising.
- **RECOVERY**: automatic on the next tick; no orphaned state since no slot was ever started.
- **USER VISIBILITY**: the failure reason is captured in the returned `TickResult` rather than an unhandled traceback.
- **Evidence**: **[VERIFIED-TEST]** new `tests/test_scheduler_runner.py::test_run_tick_does_not_crash_on_a_lock_acquisition_failure`, a real failure-injection test (monkeypatches `active_lock` to raise), passing in both regression runs.

### 11. Process crash / restart while a scheduler run is RUNNING

- **FAILURE**: the host process is killed (OOM, crash, manual kill, machine reboot) mid-run.
- **DETECTION**: on next startup, `reclaim_stale_locks(staleness_seconds=...)` finds RUNNING rows older than the staleness threshold.
- **SAFE RESPONSE**: such rows are marked RECLAIMED, releasing the lock so a new run can start; the on-disk RUNNING row (not an in-memory lock) is what makes this survive the crash.
- **RECOVERY**: automatic on next scheduler startup/tick.
- **USER VISIBILITY**: `list_runs()` shows the RECLAIMED status and the elapsed-time detail message.
- **Evidence**: **[VERIFIED-CODE]** read `scheduler/store.py::reclaim_stale_locks` in full this session (see docstring cited above); pre-existing test coverage, unmodified this session, re-confirmed passing.

### 12. Process crash / restart while a paper position is open

- **FAILURE**: process killed with an open paper position.
- **DETECTION**: `PaperStore` persists position state to disk on every transition, not just at shutdown.
- **SAFE RESPONSE**: on restart, the position is read back from disk exactly as it was, not lost or duplicated.
- **RECOVERY**: automatic.
- **USER VISIBILITY**: dashboard/CLI reflect the recovered state immediately.
- **Evidence**: **[VERIFIED-TEST]** `tests/test_paper_restart.py` (pre-existing, unmodified, confirmed passing in this session's regressions).

### 13. Kill-switch state lost on restart

- **FAILURE**: an operator activates the kill switch, then the process restarts.
- **DETECTION**: N/A -- the switch state itself is the thing being checked, freshly, on every call.
- **SAFE RESPONSE**: `LiveStateStore`'s kill-switch read has zero caching -- it is read fresh from disk on every check, so a restart cannot silently "forget" an active kill switch.
- **RECOVERY**: N/A -- nothing to recover, the state was never held only in memory.
- **USER VISIBILITY**: kill-switch status is queryable at any time and reflects disk truth.
- **Evidence**: **[VERIFIED-TEST]** `tests/test_live_state_store.py:131-140` (a real restart test, confirmed present and passing, per this session's own re-verification against the current file).

### 14. Config file missing or malformed at startup

- **FAILURE**: a required config file (risk config, scheduler config, critic config) is absent or has invalid syntax/values.
- **DETECTION**: dependent on each config loader's own validation (pydantic models raise on invalid shape where used); no single unified "config health" pre-flight check across all config sources.
- **SAFE RESPONSE**: inconsistent across subsystems -- some fail fast with a clear pydantic ValidationError, others may silently fall back to a hardcoded default.
- **RECOVERY**: manual (operator fixes the config file).
- **USER VISIBILITY**: varies -- a pydantic validation error is clear; a silent default fallback is not visible at all.
- **Evidence**: **[ASSUMED]** gap, disclosed. The mission's own "configuration-layer discipline" section names this as unresolved; not addressed this session.

### 15. Clock skew on the host machine

- **FAILURE**: the dev/host machine's system clock drifts from true time.
- **DETECTION/SAFE RESPONSE**: a known, stable, already-handled dev-machine NTP issue (~-130s skew) -- prior sessions confirmed this is accounted for in timestamp comparisons where it matters; it is not something to "fix" at the system-clock level.
- **RECOVERY**: N/A (not a code defect).
- **USER VISIBILITY**: N/A.
- **Evidence**: **[ASSUMED]**, carried from persistent project memory of this environment, not re-verified this session.

### 16. Duplicate prediction/order-intent record written twice

- **FAILURE**: a retried call or race condition causes the same logical prediction to be inserted twice.
- **DETECTION**: **app-level only** -- `predictions/store.py` and `predictions/direction_forecast_store.py` prevent duplicates in application logic, not via a database-level `UNIQUE` constraint.
- **SAFE RESPONSE**: relies on the application never having a code path that double-inserts; not enforced as a hard invariant by the schema itself.
- **RECOVERY**: N/A if it happens -- would require manual dedup.
- **USER VISIBILITY**: none dedicated.
- **Evidence**: **[VERIFIED-CODE]** confirmed via schema reading in a prior phase of this session (noted in Pending Tasks); **real, disclosed gap**, not fixed this session.

### 17. Overlapping custom scheduler slot windows

- **FAILURE**: two configured slots have overlapping time windows.
- **DETECTION**: `due_slot()` selection logic has no documented fairness guarantee for this case.
- **SAFE RESPONSE**: undefined -- whichever slot the selection logic happens to pick first wins; not a documented, intentional priority order.
- **RECOVERY**: N/A.
- **USER VISIBILITY**: none dedicated.
- **Evidence**: **[ASSUMED]** gap, disclosed, not fixed this session.

### 18. Cache staleness silently treated as fresh

- **FAILURE**: `report_cache_staleness`'s `cache_root` bound-default parameter previously made test isolation (and, by the same mechanism, any runtime override) silently ineffective.
- **DETECTION**: **fixed this session** -- root-caused (not merely worked around) as a classic Python mutable/bound-default-evaluated-at-definition-time gotcha; a new `--cache-root` CLI flag now threads an explicit override through where needed.
- **SAFE RESPONSE**: staleness threshold now imports `critic/config.py`'s canonical value for `daily-report` rather than a second, driftable hardcoded literal.
- **RECOVERY**: N/A -- this was a latent correctness bug, now closed.
- **USER VISIBILITY**: the staleness warning message is now dynamic, reflecting the actual configured threshold rather than a hardcoded "5 days" string that could silently diverge from the real value.
- **Evidence**: **[VERIFIED-TEST]** `tests/test_daily_report.py`'s 3 rewritten, fully hermetic tests, passing in both regression runs. **Residual, disclosed gap**: `cache-status`'s 30-day and `readiness-check`'s 7-day thresholds remain separate, undocumented-as-intentional divergent values from this same `daily-report` threshold -- not unified this session.

### 19. Naive/aware datetime comparison raises `TypeError: can't compare offset-naive and offset-aware datetimes`

- **FAILURE**: historically recurring (named "Phase 33/37/42" bug class in code comments) -- market-data timestamps (naive) compared against record-metadata timestamps (aware) without normalization.
- **DETECTION**: previously each of 10+ call sites reimplemented its own ad-hoc fix independently (one file, `predictions/tracker.py`, had two different implementations of the same fix).
- **SAFE RESPONSE**: **consolidated this session** into `core/timeutil.py` with an explicit, documented two-case policy (`to_naive` for market/bar data, `as_utc_aware` for record/system metadata) plus a third function (`match_index_awareness`) for the bidirectional case of matching a scalar to an existing DataFrame index's own awareness.
- **RECOVERY**: N/A -- centralizing the policy prevents a 4th independent reinvention, it does not itself recover from a live occurrence.
- **USER VISIBILITY**: would previously surface as a raw `TypeError` traceback; now governed by one tested, documented module.
- **Evidence**: **[VERIFIED-TEST]** new `tests/test_core_timeutil.py` (13 tests) plus zero-behavior-change confirmed via the full regression (1989 passed, 0 failed) across every migrated call site.

### 20. Model promotion or strategy threshold mutated automatically based on live performance

- **FAILURE**: a learning/feedback loop silently promotes a model or changes a live-trading threshold without human review.
- **DETECTION**: N/A -- this is a designed-against scenario, not a monitored one.
- **SAFE RESPONSE**: `strategy/promotion_gate.py::evaluate_promotion` produces a verdict (`PROMOTED`/`NEGATIVE`/`INCONCLUSIVE`/`REJECTED`/`INSUFFICIENT_DATA`); nothing in the codebase auto-applies a `PROMOTED` verdict to live configuration -- promotion requires a manual, separate action.
- **RECOVERY**: N/A.
- **USER VISIBILITY**: the verdict is computed and reported, not silently acted on.
- **Evidence**: **[VERIFIED-CODE]** confirmed via reading `strategy/promotion_gate.py` and `learning/profitability.py` in this and prior sessions; unmodified (except the datetime-normalization delegation, zero behavior change) this session.

---

## Summary of residual, disclosed P0/P1 gaps from this analysis

These are the concrete items this analysis surfaces as still open, in
priority order, carried into `FINAL_PRODUCT_READINESS_REPORT.md`:

- **P1**: no explicit OHLC/data-quality validation layer (#2).
- **P1**: no unified disk-space / resource-safety monitoring (#8).
- **P1**: no automatic startup self-diagnostic invoking `integrity_check` (#6).
- **P1**: migration mechanism (`_ensure_column`-equivalent) exists on only 1 of 12 stores (#6, structurally).
- **P2**: app-level-only (not DB-level `UNIQUE`) duplicate prevention for predictions (#16).
- **P2**: no per-job scheduler timeout; no documented fairness guarantee for overlapping custom slot windows (#17).
- **P2**: config-loading behavior is inconsistent across subsystems -- no unified fail-fast/health-check layer (#14).
- **P2**: cache-staleness thresholds remain divergent across 3 CLI commands, not fully unified (#18, residual).

No P0 (live-trading-safety, temporal-integrity, or state-persistence-
correctness) defect was found or left unresolved by this analysis.
