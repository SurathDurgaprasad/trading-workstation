# Final Release Remaining Work

Prioritized against the release-gate mission's own P0-P3 order. Each
item below is grounded in file:line evidence gathered by a fresh
read-only codebase survey against the CURRENT code (not the prior
reports), run at the start of this phase. Status is updated in place
as items are closed; nothing is marked closed without a fix + a real
test proving it (KNOWN DEFECT -> ROOT CAUSE -> CODE FIX -> REGRESSION
TEST -> FAILURE-INJECTION TEST WHERE APPROPRIATE -> FULL REGRESSION ->
DOCUMENT -> CLOSE, per the mission's hard release rule).

---

## P0 -- data correctness, time correctness, trading safety, state/persistence, live-trading prevention

| # | Item | Evidence | Status |
|---|---|---|---|
| P0-1 | **No OHLCV data-quality validation layer exists anywhere.** No check for high>=low/open/close, low<=open/close, duplicate timestamps, timestamp monotonicity, or gap/missing-bar detection. `OHLCV.from_dataframe` only drops NaN rows. | `market/data_provider.py:104-141` (no sort/dedup/monotonic check, repo-wide grep confirms no such logic exists elsewhere) | **CLOSED** -- root fix: `OHLCV.from_dataframe` now also drops rows with an impossible OHLC relationship (`market/data_provider.py::_row_has_valid_ohlc_relationship`), the same mechanism it already used for NaN rows. New `market_data/validation.py::validate_ohlcv` adds series-level HEALTHY/DEGRADED/INVALID checks (duplicates, ordering, gaps, symbol identity, staleness). 34 new tests (`tests/test_market_data.py`, `tests/test_market_data_validation.py`). |
| P0-2 | **INVALID data is not structurally prevented from reaching prediction/decision/paper-trade.** | Same as P0-1 | **CLOSED** -- `market_intelligence/scanner.py`'s `_screen_symbol`/`_fetch_benchmark` (the actual scan -> `decision_engine` -> paper-trade choke point) now call `validate_ohlcv` right after fetch and exclude the symbol (`ExcludedCandidate`, never scored) on INVALID, the same pattern already used for a fetch failure. New failure-injection test: `test_invalid_data_quality_is_excluded_not_scored`. |
| P0-3 | **Two missed datetime-normalization duplication spots**, reimplementing `core.timeutil.as_utc_aware`'s exact logic inline instead of importing it -- the same bug class the consolidation was meant to close. | `dashboard/app.py:220-222`, `live/dhan/clock_skew.py:94-96` | **CLOSED** -- both now delegate to `core.timeutil.as_utc_aware`; targeted tests re-confirmed passing (zero behavior change). |
| P0-4 | **Paper position state transitions are not guarded.** `paper/store.py::update_position()` has no `WHERE status = 'OPEN'` guard and no CHECK constraint; `paper/engine.py::_close_position()` never re-verifies the position is still OPEN before closing. A closed->open or double-close transition is prevented only by caller discipline, not by the data layer. | `paper/store.py:232-236`, `paper/engine.py:331-384`, `paper/models.py:76-78` | **CLOSED** -- `update_position()` now guards with `WHERE status != 'CLOSED'` and raises a new `paper.errors.InvalidPositionTransitionError` (loud, not a silent no-op) on a 0-row update against an existing position; `ValueError` for a nonexistent one. 4 new tests in `tests/test_paper_store.py`; full `paper/` suite (135 tests) re-confirmed passing with no behavior change on the normal path. |
| P0-5 | **Live order execution: re-confirmed structurally blocked.** Zero `requests.post/put/delete` anywhere in the repo; `DisabledDhanOrderExecutor` unconditionally raises on every order method; it is constructed only in `tests/test_dhan_no_real_orders.py`, never in production code; no MCP tool places orders. | `live/dhan/broker_adapter.py:28-37,66-73`, repo-wide grep, `tests/test_dhan_no_real_orders.py` | **CLOSED -- verified this phase, no code change needed** |
| P0-6 | **LLM/Ollama failure isolation: re-confirmed correct.** `decision_engine/engine.py` and `research/summarizer.py` both wrap LLM calls in try/except that degrades to a non-fatal `narrative_unavailable_reason` field rather than raising. | `decision_engine/engine.py:109-117`, `research/summarizer.py:110-117` | **CLOSED -- verified this phase, no code change needed** |

## P1 -- failure recovery, database integrity, provider resilience, paper execution, scheduler

| # | Item | Evidence | Status |
|---|---|---|---|
| P1-1 | **Predictions duplicate prevention is application-level only, non-atomic.** `predictions/store.py::has_prediction_for_entry()` and `direction_forecast_store.py::has_forecast_for_bar()` are check-then-insert with no spanning transaction and no DB `UNIQUE` constraint on the real natural key (symbol+entry_time / symbol+as_of) -- only a PK on a UUID surrogate. Two concurrent callers (manual run overlapping a scheduled run) could both pass the check and double-insert. | `predictions/store.py:24-30,86-98`, `predictions/direction_forecast_store.py:21-26,82-87` | **CLOSED** -- both stores now migrate in a real `entry_time`/`as_of` column (via new shared `core.sqlite_util.ensure_column`, backfilled from each pre-existing row's own `data_json`, never guessed) and attempt a genuine `UNIQUE(symbol, entry_time\|as_of)` index (new shared `core.sqlite_util.try_create_unique_index`) -- soft-fails to `duplicate_prevention_enforced_at_db_level = False` rather than crashing startup or deleting data if an already-deployed DB has pre-existing duplicates. `save_prediction`/`save_forecast` now raise typed `DuplicatePredictionError`/`DuplicateForecastError` on a real constraint hit. Confirmed both call sites in `main.py` already check `has_prediction_for_entry`/`has_forecast_for_bar` first, so this is purely a race backstop, not a behavior change on the normal path. 8 new tests across `tests/test_predictions_store.py`/`tests/test_direction_forecast_store.py`/`tests/test_core_sqlite_util.py`, including a simulated pre-migration on-disk schema and a simulated pre-existing-duplicate database. `live/state_store.py`'s own pre-existing `_ensure_column` was consolidated into the same shared helper it now shares with these two stores. |
| P1-2 | **No schema-version tracking on any of the 12 stores** (`PRAGMA user_version` or equivalent -- zero repo-wide hits). Only `live/state_store.py` has a migration helper (`_ensure_column`); the other 11 have none. | Table gathered this phase (12 stores audited) | **PARTIALLY CLOSED**. The additive-column migration helper (`live/state_store.py`'s former private `_ensure_column`) is now a shared `core.sqlite_util.ensure_column`, used by 3 stores (`live/state_store.py`, `predictions/store.py`, `predictions/direction_forecast_store.py` -- see P1-1). `integrity_check()`/`db_size_bytes()` (previously on 3 of 12 stores) are now on **all 12** -- the 9 that lacked them (`experiments`, `decision_engine`, `strategy/promotion_store`, `strategy/experiment_store`, `predictions/store`, `predictions/direction_forecast_store`, `research`, `market_intelligence/store`, `market_intelligence/regime_store`) each gained both methods, delegating to the same shared `core.sqlite_util` functions; 18 new tests confirm each. **Still open**: no `PRAGMA user_version`/schema-version table on any store (a real remaining gap -- the additive-column pattern this phase extended answers "can a column be safely added," not "what version is this schema, and can a caller detect/require a specific one"), and 9 of 12 stores still have no migration mechanism AT ALL (only the 3 above ever needed one so far) -- deferred, a genuinely separate, larger undertaking than the integrity/size-check extension. |
| P1-3 | **Unified health system does not exist.** `readiness-check` covers only some subsystems (Dhan credential presence, one DB, kill switch, session/holiday, disk-write probe); `cache-status` is separate; Ollama health (`check_ollama_availability`) is never called from `readiness-check`; store integrity is not surfaced from `readiness-check` at all (though `integrity_check()` itself is now on all 12 stores, per P1-2). | `main.py:2970-3079` (`readiness-check`), `main.py:2908` (`cache-status`), `llm/provider.py:98` | **OPEN -- deferred, see below** |
| P1-4 | Scheduler per-job timeout, `last_success_at` tracking, overlapping-slot fairness. | Carried from `FINAL_FAILURE_MODE_ANALYSIS.md` #17 | **PARTIALLY CLOSED**. `SchedulerRunStore` gained `last_successful_run_for_slot()`/`last_failed_run_for_slot()`/`distinct_slot_names()`, surfaced in `schedule status`'s new "Per-slot summary" section (last success timestamp, last failure timestamp + its error, per configured slot) -- 8 new tests across `tests/test_scheduler_store.py`/`tests/test_cli_schedule.py`. **Per-job timeout deliberately NOT implemented**: `scheduler/runner.py::_execute_slot` calls `main.py` command functions in-process and synchronously (no subprocess, no thread) -- a naive `threading.Thread(...).join(timeout=...)` wrapper would not actually stop a slow/hung call (e.g. a blocked network request inside it); the tick would report "timed out" while the original call keeps running unsupervised in the background, potentially completing its own DB writes after the scheduler has already moved on and started something else -- a worse failure mode than the current one (a hang that is at least visible as a stuck RUNNING lock, reclaimed by `reclaim_stale_locks` on the next tick). A REAL preemptive timeout needs subprocess isolation, a genuinely larger architectural change than this item's own scope justifies without separate evidence the in-process design cannot be hardened another way; disclosed here rather than shipping a timeout that doesn't actually bound anything. Overlapping-slot fairness remains open, undocumented, lower priority than the above.

## P2 -- unified health, observability, installation, operations, security

| # | Item | Evidence | Status |
|---|---|---|---|
| P2-1 | Installation docs (`README.md`, `requirements.txt`, `.env.example`) re-verified sufficient for a clean install from scratch; `.env.example` covers the one real env-var surface (Dhan credentials) completely -- LLM/Ollama config is hardcoded, not env-driven, so nothing is missing there either. | `README.md:75-132`, `.env.example`, `core/config.py` | **CLOSED -- verified this phase, no gap found** |
| P2-2 | Dedicated `INSTALLATION.md`/`USER_GUIDE.md`/`OPERATIONS_GUIDE.md`/`TROUBLESHOOTING.md`/`ARCHITECTURE.md`/`SECURITY.md` document suite. | Carried from `FINAL_PRODUCT_READINESS_REPORT.md` | **OPEN -- deferred, README/phase-docs remain the de facto operations reference** |
| P2-3 | Security re-audit (secret scan, dependency audit, log redaction audit). | Carried from prior phase | **OPEN -- deferred, no new surface introduced this phase** |

## P3 -- performance, UX, research/intelligence

Explicitly not touched this phase, per the mission's own rule ("do not
work on P3 while a P0/P1 release blocker remains"). The Phase 1
research verdict (no demonstrated economic edge) remains frozen and is
not being revisited.

---

## Defects found via the regression discipline itself (not pre-planned)

- **Fixture bugs exposed by the new P1-1 DB constraint** (not a defect in the constraint): `tests/test_predictions_store.py` (4 tests) and `tests/test_cli_experiment.py` (2 tests, via its shared `_seed_resolved_predictions` helper) used a hardcoded, identical `entry_time` across multiple predictions for the same symbol -- data no real caller would ever legitimately produce (has_prediction_for_entry would have refused it), but previously allowed because no DB-level constraint existed to catch it. Root-caused (not weakened/skipped): each fixture now varies `entry_time` per prediction; `_seed_resolved_predictions` additionally gained an `entry_day_offset` parameter so its two same-symbol call sites (baseline vs. candidate config) cannot collide with each other either. Full regression re-confirmed 0 failures after the fix. This is exactly the kind of real, load-bearing correctness gap the new constraint was built to surface -- the fixtures were quietly relying on behavior the DB-level guarantee now correctly forbids.

## Execution plan for this phase

Given real session scope, this phase focuses on closing every P0 item
that is actually open (P0-1 through P0-4) with real fixes and tests,
plus the highest-value, well-scoped P1 item (P1-1, since it's a small,
targeted DB constraint addition directly adjacent to work already done
this session on the same stores). P1-2/P1-3/P1-4 and all of P2 beyond
verification are being explicitly deferred -- each is a genuinely large
undertaking (a shared migration framework across 12 stores; a unified
health service spanning 10+ subsystems) that would not receive the
same fix-with-tests rigor as the P0 items if compressed into this same
session. This is disclosed here, not silently dropped, and will be
carried into the final release-candidate report as a known remaining
blocker to a "READY" verdict.
