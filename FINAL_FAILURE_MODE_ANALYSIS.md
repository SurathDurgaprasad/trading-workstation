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
- **DETECTION**: **fixed in the release-gate pass** -- `market_data/validation.py::validate_ohlcv` classifies a series HEALTHY/DEGRADED/INVALID (duplicate/non-chronological timestamps, symbol-identity mismatch, gaps, staleness); `market/data_provider.py::OHLCV.from_dataframe` also drops individual rows with an impossible OHLC relationship (high<low, close outside [low,high]), the same mechanism it already used for NaN rows. Live-tick-path candle-builder rejection counters (`docs/OBSERVABILITY.md`) remain a separate, pre-existing detection layer for that different path.
- **SAFE RESPONSE**: `market_intelligence/scanner.py`'s `_screen_symbol`/`_fetch_benchmark` exclude the symbol (`ExcludedCandidate`, never scored) on an INVALID report -- the exact "INVALID DATA -> NO PREDICTION/DECISION" rule this mission requires, verified by a dedicated failure-injection test.
- **RECOVERY**: automatic on the next fetch of clean data; no manual intervention needed.
- **USER VISIBILITY**: the exclusion reason (`"Data quality: ..."`) is visible in the scan report's `excluded` list, the same place a fetch failure already surfaces.
- **Evidence**: **[VERIFIED-TEST]** `tests/test_market_intelligence_scanner.py::test_invalid_data_quality_is_excluded_not_scored`, `tests/test_market_data_validation.py` (11 tests), `tests/test_market_data.py::test_ohlcv_from_dataframe_filters_rows_with_impossible_ohlc_relationships`. **Residual, disclosed gap**: gap/missing-bar detection is a non-calendar-aware heuristic (DEGRADED, not INVALID -- a real market holiday can also trigger it); the offline `ml_research`/`quant_research` data paths are not yet gated by this validator, only the live scanner path.

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

- **FAILURE**: disk error, power loss mid-write, filesystem issue, or the file being overwritten by something else.
- **DETECTION**: two layers now. (1) **Autonomous hardening cycle 1 addition**: `core.sqlite_util.connect()` -- the ONE place every store opens its connection -- detects a corrupt/non-SQLite file automatically on every single connection attempt (not just when an operator remembers to run a check), raising a clear `DatabaseCorruptedError` naming the file instead of a raw `sqlite3.DatabaseError`. (2) `PRAGMA integrity_check`, exposed via `core.sqlite_util.integrity_check()` on all 12 stores, for a deeper on-demand scan an operator can run explicitly (e.g. after long unattended operation).
- **SAFE RESPONSE**: a corrupted file now fails LOUDLY and IMMEDIATELY at the first connection attempt (layer 1), rather than only being caught if/when an operator happens to run an explicit integrity check (layer 2). This closes what this document previously listed as a disclosed gap ("still not automatically invoked on every startup").
- **RECOVERY**: manual -- restore from a backup or accept data loss on the affected store; no automated repair (unchanged).
- **USER VISIBILITY**: the `DatabaseCorruptedError` message itself, at the moment any command tries to open the affected store -- documented in `TROUBLESHOOTING.md`. `integrity_check()` remains available for a proactive, deeper scan.
- **Evidence**: **[VERIFIED-TEST]** `tests/test_core_sqlite_util.py::test_connect_against_a_corrupted_file_raises_a_clear_database_corrupted_error` and `test_connect_against_a_truncated_file_also_raises_the_clear_error` (autonomous hardening cycle 1); `PRAGMA integrity_check` coverage unchanged from the prior pass. **Residual, disclosed gap**: still no single CLI command surfacing all 12 stores' `integrity_check()` results together in one pass (`python main.py health --check-integrity`-style aggregation does not yet exist for every store, though `core.health.collect_system_health`'s database check does aggregate a `PRAGMA integrity_check` across every configured, existing store's path).

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
- **USER VISIBILITY**: kill-switch status is queryable at any time and reflects disk truth. **Autonomous hardening cycle 4 addition**: activating or resetting the kill switch (from any caller -- CLI or dashboard) now also emits a `logger.warning`, so the event is visible in a `--log-file`-backed log stream, not only by actively polling status. Previously this state change left zero trace in application logs at all.
- **Evidence**: **[VERIFIED-TEST]** `tests/test_live_state_store.py:131-140` (a real restart test, confirmed present and passing, per this session's own re-verification against the current file); `tests/test_live_state_store.py::test_activate_kill_switch_logs_a_warning_with_the_reason`/`test_reset_kill_switch_logs_a_warning` (autonomous hardening cycle 4).

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

- **FAILURE**: a retried call or race condition (e.g. a manual `predict` CLI invocation overlapping a scheduled `daily-report` run against the same `predictions.db`) causes the same logical symbol+entry-bar prediction to be inserted twice.
- **DETECTION**: **fixed in the release-gate pass** -- `predictions/store.py` and `predictions/direction_forecast_store.py` now migrate in a real `entry_time`/`as_of` column (backfilled from each pre-existing row's own `data_json`) and attempt a genuine `UNIQUE(symbol, entry_time)`/`UNIQUE(symbol, as_of)` index at the database level, not just an application-level check.
- **SAFE RESPONSE**: `save_prediction`/`save_forecast` now raise a typed `DuplicatePredictionError`/`DuplicateForecastError` on a genuine constraint hit; both real `main.py` call sites already check `has_prediction_for_entry`/`has_forecast_for_bar` first, so this is a race backstop, not a behavior change on the normal single-writer path (confirmed: 113 prediction/forecast/tracker tests unaffected). If an already-deployed database happens to already contain duplicate rows (possible under the old app-level-only prevention), the unique index is skipped gracefully -- `duplicate_prevention_enforced_at_db_level = False` -- rather than crashing startup or deleting the pre-existing rows.
- **RECOVERY**: N/A for the constraint itself (it prevents new duplicates going forward); a database already carrying historical duplicates is not automatically deduplicated (disclosed -- see mission's own "never delete critical trading state automatically" rule).
- **USER VISIBILITY**: `duplicate_prevention_enforced_at_db_level` is queryable on the store instance; not yet surfaced through a CLI/dashboard health view (that gap remains -- see scenario/gap summary below).
- **Evidence**: **[VERIFIED-TEST]** 8 new tests across `tests/test_predictions_store.py`, `tests/test_direction_forecast_store.py`, `tests/test_core_sqlite_util.py`, including a simulated pre-migration on-disk schema and a simulated pre-existing-duplicate database exercising the graceful-degradation path.

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

### 21. A single stored row's `data_json` is malformed or tampered with, independent of whole-file corruption

- **FAILURE**: a specific row's JSON no longer matches the Pydantic model expected to read it back -- distinct from #6 (whole-FILE corruption): the file opens fine, `PRAGMA integrity_check` reports "ok," but one row's content is bad (external tampering, or corruption isolated to that row's page).
- **DETECTION**: **autonomous hardening cycle 1/2 addition** -- every one of the 12 stores' `Model.model_validate_json(row)` read call sites now goes through `core.sqlite_util.parse_model_json()`, which raises a clear `MalformedRowError` naming the model and row identifier.
- **SAFE RESPONSE**: previously, this raised a raw `pydantic.ValidationError` (or, for the one dataclass-based store, a raw `KeyError`/`TypeError`) straight out of the store -- functionally still fail-closed (the bad read still fails rather than silently returning wrong data) but with a traceback an operator has to interpret rather than a named, actionable error.
- **RECOVERY**: manual -- the row's data is genuinely unreconstructable from what's stored; see `TROUBLESHOOTING.md`'s dedicated entry.
- **USER VISIBILITY**: the error names the model and row identifier directly, rather than requiring the operator to decode a Pydantic traceback.
- **Evidence**: **[VERIFIED-TEST]** one dedicated malformed-row test per store, all 12 stores (`tests/test_core_sqlite_util.py`, `tests/test_paper_store.py`, `tests/test_predictions_store.py`, `tests/test_scheduler_store.py`, `tests/test_decision_engine_store.py`, `tests/test_market_intelligence_regime_store.py`, and equivalents for the remaining 6 stores), all passing in the full regression (2142 passed at the time this coverage completed).

### 22. A scheduled slot fails EVERY tick for a sustained period (e.g. a multi-hour provider outage)

- **FAILURE**: `schedule loop` keeps retrying the next tick (as designed, since a single bad tick is normal), but every tick for one slot keeps failing with no success in between.
- **DETECTION**: previously **undetected by `core.health.collect_system_health`** -- each failed tick correctly finishes with status=FAILED and releases its lock, so the old scheduler health check (active-lock-only) reported HEALTHY throughout an actual, ongoing production problem. **Autonomous hardening cycle 3 addition**: `SchedulerRunStore.consecutive_failures_for_slot()` + `core.health._check_scheduler` now report DEGRADED once any slot reaches 3 consecutive non-COMPLETED runs (FAILED or RECLAIMED), naming the slot, the streak length, and the last failure's actual reason.
- **SAFE RESPONSE**: purely a visibility fix -- `schedule loop` itself already retried correctly; scheduler remains an OPTIONAL health component (this never escalates past overall DEGRADED, never blocks the startup gate).
- **RECOVERY**: automatic -- the DEGRADED status clears itself the next time the slot completes successfully; no manual reset needed.
- **USER VISIBILITY**: `python main.py health`, the dashboard `/health` route, and `schedule status`'s existing per-slot last-success/last-failure summary all surface it now.
- **Evidence**: **[VERIFIED-TEST]** `tests/test_scheduler_store.py` (7 new tests for `consecutive_failures_for_slot`'s edge cases) and `tests/test_core_health.py` (3 new tests for the health-check integration), all passing in the full regression (2152 passed).

---

## Summary of residual, disclosed P0/P1 gaps from this analysis

Updated after the final release-gate hardening pass (commits `339e16a`
through `7ac5a33`). Every P0 and P1 item previously listed here as open
is now CLOSED -- see `FINAL_RELEASE_REMAINING_WORK.md` for the complete,
itemized, evidence-backed table (every item terminal: CLOSED /
EXTERNALLY BLOCKED / ACCEPTED LIMITATION) and
`FINAL_RELEASE_CANDIDATE_REPORT.md` for the final criterion-by-criterion
verdict. Specifically, since the previous version of this summary:
schema-version tracking now exists on all 12 stores (`core.sqlite_util`,
`PRAGMA user_version`); a unified health system (`core/health.py`)
now exists, consumed identically by the CLI (`python main.py health`)
and the dashboard (`/health`); a real startup gate
(`main.py::_run_startup_gate`) now refuses to start `paper-live`/
`schedule tick`/`schedule loop` on a FAILED critical dependency;
per-slot scheduler last-success/last-failure tracking exists; a
provider-failure-injection matrix (16 named scenarios) was surveyed and
triaged, closing 4 genuine gaps including one real code defect
(`DhanRestClient._get()` not wrapping transport failures); a real
`pip-audit` dependency scan and repo-wide secret scan were both run.

Remaining, all formally accepted/deferred with stated reasoning, none
representing unsafe behavior:

- **P2 (accepted limitation)**: no per-job scheduler timeout -- the in-process, synchronous execution model means a thread-based timeout would not actually stop a hung call; a real fix needs subprocess isolation, out of scope without separate justification (documented in `OPERATIONS_GUIDE.md`).
- **P2 (accepted limitation)**: cache-staleness thresholds differ across `daily-report`/`cache-status`/`readiness-check` -- re-examined and confirmed these answer genuinely different questions (live-decision safety vs. historical-cache/backtest relevance), not an inconsistency to unify.
- **P2 (accepted limitation)**: `core/config.py`'s `Settings` has no range validation -- zero untrusted-input path exists today, verified by grep.
- **P2 (deferred, disclosed)**: no dashboard authentication -- out of scope for the current single-operator, loopback-only threat model.
- **P2 (deferred, disclosed)**: no automatic SQLite retention/archival policy -- deliberately, since these stores are exactly the "critical trading state" the mission's own rule forbids automatically deleting.
- **P2/P3 (deferred, disclosed)**: no full non-secret-scan security audit (static analysis, license audit) beyond `pip-audit` and the targeted injection/credential checks; no performance profiling (correctly deferred until after correctness, per the mission's own priority order).

No P0 or P1 (live-trading-safety, temporal-integrity, state-persistence-
correctness, data-quality, provider-resilience, or scheduler-resilience)
defect remains open at the conclusion of this campaign.
