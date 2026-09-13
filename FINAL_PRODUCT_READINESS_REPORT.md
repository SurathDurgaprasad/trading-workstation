# Final Product Readiness Report

Branch: `final-product-hardening` (not yet merged to `main` as of this
report; commits `30242e5` then `c470305`). Companion documents:
`FINAL_PRODUCT_AUDIT.md`, `FINAL_FAILURE_MODE_ANALYSIS.md`,
`FINAL_RELEASE_REMAINING_WORK.md` (the live, itemized punch list this
report summarizes). Full regression: **2035 passed, 0 failed**
(re-run after every change across both hardening passes).

This report is deliberately honest about scope. The originating
mission (55 sections, then a 37-section release-gate follow-up) is a
genuine production-hardening campaign, not completable end-to-end in
one or two sessions. What follows separates what has actually been
hardened and tested across both passes from what remains open, rather
than overstating completion.

---

**Architecture**: Stable, layered (data -> features -> prediction ->
decision -> risk -> execution -> persistence -> learning), unchanged in
shape this session. Datetime handling was structurally consolidated
(`core/timeutil.py`) and SQLite connection/integrity handling was
structurally consolidated (`core/sqlite_util.py`), closing two real
cross-cutting duplication risks without altering the architecture.

**Data**: Yahoo Finance intraday (5-min bars, ~60-day window) plus
India VIX and sector indices; NSE/BSE/SEBI have no official API (known,
prior finding, unchanged). A data-quality validation layer now exists
(`market_data/validation.py::validate_ohlcv`, HEALTHY/DEGRADED/INVALID)
and is wired into `market_intelligence/scanner.py` -- the actual
scan -> decision -> paper-trade choke point -- so INVALID data
(duplicate/non-chronological timestamps, symbol-identity mismatch) is
excluded before any indicator or decision computation sees it, and
`market/data_provider.py::OHLCV.from_dataframe` now also drops
individual rows with an impossible OHLC relationship (high<low etc),
extending the same silent-drop mechanism it already used for NaN rows.
Gap detection (missing bars) and staleness are DEGRADED-level findings,
visible but not blocking. Cache-staleness reporting was fixed at the
root cause in the prior pass (a bound-default parameter defeating
overrides), not patched.

**Prediction**: The Phase 1 ML baseline (`ml_research/`) is a
completed, isolated research artifact: ROC-AUC 0.575-0.615 across 4
walk-forward folds plus a held-out test, with both the model and the
deterministic-rule benchmark scoring `PromotionVerdict.NEGATIVE` on
every split -- **no demonstrated edge**, a settled, frozen research
verdict from Phase 1, not revisited or reframed this session. The
model remains a forecasting component (`P(target first)`), never a
direct trading signal, by construction.

**Decision**: `decision_engine/` deterministic rules unmodified this
session; unchanged in behavior. Model/decision separation preserved.

**Risk**: `risk/engine.py` unmodified this session (confirmed via `git
diff --stat main` -- not in the 28 changed files).

**Paper trading**: Working, hardened across both passes (WAL mode, 30s
busy timeout, `integrity_check()`/`db_size_bytes()` on `PaperStore`).
The position state machine is now guarded at the data layer:
`PaperStore.update_position()` enforces CLOSED as a terminal state
(`WHERE status != 'CLOSED'`), raising a new
`paper.errors.InvalidPositionTransitionError` on a double-close or
reopen attempt instead of allowing it silently -- previously prevented
only by caller discipline. Restart-recovery of open positions has real,
pre-existing test coverage (`tests/test_paper_restart.py`), re-confirmed
passing; the new guard was confirmed to change nothing on the normal
path (full `paper/` suite, 135 tests, unaffected).

**Dashboard**: Working, unmodified this session. No authentication if
exposed beyond loopback (known, accepted for the current single-operator
threat model; not a new finding).

**CLI**: Working, ~30 subcommands, unmodified this session except the
new `--cache-root` flag on `daily-report`.

**Persistence**: All 12 SQLite stores use WAL mode + a 30s busy timeout
(was: no WAL, 5s stdlib default), verified via a real threading-based
concurrent-reader-not-blocked-by-writer test. `integrity_check()`/
`db_size_bytes()` now cover **all 12 stores** (was 3 of 12 -- the
9 that lacked them each gained both, delegating to the same shared
`core.sqlite_util` functions). `predictions/store.py` and
`predictions/direction_forecast_store.py` now enforce real DB-level
`UNIQUE(symbol, entry_time)`/`UNIQUE(symbol, as_of)` constraints via a
migration (a real, previously-app-level-only-and-non-atomic
duplicate-prevention gap, now closed) -- the migration backfills the
new column from each pre-existing row's own `data_json` and skips the
index gracefully (reporting `duplicate_prevention_enforced_at_db_level
= False`, never crashing startup or deleting data) if an
already-deployed database happens to already contain duplicates. The
additive-column migration helper (`live/state_store.py`'s former
private `_ensure_column`) is now shared (`core.sqlite_util.ensure_column`),
used by 3 of 12 stores. **Still open**: no `PRAGMA user_version`/
schema-version tracking on any store, and 9 of 12 have no migration
mechanism at all (only the 3 that needed one so far have it) --
disclosed, deferred, a genuinely larger undertaking than the
integrity/size-check extension.

**Recovery**: Scheduler restart recovery via on-disk RUNNING-row
reclamation (`reclaim_stale_locks`) is pre-existing and unmodified, with
existing test coverage. Scheduler tick-setup-phase exception safety is
**new this session** (previously, a failure in lock acquisition/holiday
checking could propagate uncaught out of `run_tick`; now it returns a
clean `TickResult` instead), backed by a new failure-injection test.
Kill-switch state is read fresh from disk on every call (zero caching,
confirmed via re-reading `live/state_store.py` and its existing restart
test at `tests/test_live_state_store.py:131-140`) -- unmodified and
re-verified, not newly built.

**Security**: Unchanged from the prior `docs/SECURITY_REVIEW.md`
findings (SQL injection clean, XSS clean, path traversal fixed, no
secrets in git history); this session's own new code was spot-checked
for the same classes (no string-interpolated SQL introduced, no
secrets touched) and introduces no new surface. No full re-audit was
run this session (disclosed scope choice, not a gap in the underlying
security posture).

**Observability**: `docs/OBSERVABILITY.md`'s existing candle-builder
rejection counters are real and unchanged. No unified, single-command
health view spanning data/model/database/scheduler/prediction/decision/
paper-trading status exists yet (disclosed gap).

**Documentation**: `README.md`, `PROJECT_GOAL_AND_ROADMAP.md`, and 40+
phase-report documents are extensive and genuinely useful for
understanding the system's history and design. The specific
`INSTALLATION.md`/`USER_GUIDE.md`/`OPERATIONS_GUIDE.md`/
`TROUBLESHOOTING.md`/`ARCHITECTURE.md`/`SECURITY.md` suite the mission
requests does **not** exist as discrete documents (disclosed gap).

**Testing**: 2035 tests passing, 0 failing, after every change across
both hardening passes, including a real threading-based concurrency
test and real failure-injection tests (scheduler setup-phase failure,
INVALID market data, a double-close position transition, a duplicate
prediction race). Growth across both passes: +13 (`core/timeutil`),
+11 (`core/sqlite_util`, incl. `ensure_column`/`try_create_unique_index`),
+34 (`market_data/validation.py` + the OHLC-relationship row filter),
+4 (position state-machine guard), +8 (predictions/forecast duplicate
prevention), +18 (integrity/size checks across the 9 previously-
uncovered stores), +2 (scheduler/cache-staleness fixes from the first
pass). 9 pre-existing tests were fixed at the root cause across both
passes: 3 from flaky/environment-dependent cache-staleness assumptions
(first pass), and 6 from a fixture bug the new prediction-duplicate
constraint correctly surfaced -- multiple same-symbol predictions
sharing one hardcoded `entry_time`, data no real caller could
legitimately produce (second pass; fixtures corrected, constraint not
weakened). Chaos/failure-injection testing beyond the handful of
targeted tests above was not built as a systematic suite (disclosed
gap against the mission's broader "chaos testing" ask).

---

## Known limitations (disclosed, not unsafe)

1. Gap detection (missing bars) in `market_data/validation.py` is a heuristic (not calendar-aware -- a genuine market holiday/weekend can also trigger it), reported DEGRADED not INVALID; no OHLC-sanity check runs on the offline `ml_research`/`quant_research` data paths, only the live scanner path.
2. No unified startup self-diagnostic command producing DEGRADED vs SAFE-STOP status across all subsystems.
3. No `PRAGMA user_version`/schema-version tracking on any of the 12 stores; a real migration mechanism (beyond additive-column backfill) exists on only 3 of 12.
4. No per-job scheduler timeout; no documented fairness guarantee for overlapping custom scheduler slot windows; no `last_success_at` tracking in `SchedulerRunStore`.
5. Cache-staleness thresholds remain divergent across `daily-report` (canonical, fixed), `cache-status` (30 days), and `readiness-check` (hardcoded 7 days) -- not fully unified.
6. Config-loading validation is inconsistent across subsystems -- some fail fast with a clear error, others may silently fall back to a default.
7. No unified health/observability dashboard spanning every subsystem in one view.
8. No dedicated `INSTALLATION.md`/`USER_GUIDE.md`/`OPERATIONS_GUIDE.md`/`TROUBLESHOOTING.md`/`ARCHITECTURE.md`/`SECURITY.md` document suite (README and phase-history docs are extensive but not organized this way).
9. Clean-install / no-Claude-Code-dependency verification was not explicitly re-run as a standalone test across either pass.
10. Chaos/failure-injection testing is limited to the handful of targeted tests listed above (scheduler setup failure, INVALID data exclusion, position double-close, prediction duplicate race); broader systematic chaos testing (provider outage simulation, disk-full simulation, DB corruption simulation) was not built.
11. Dashboard has no authentication; safe only for the current loopback/single-operator deployment model.
12. No formal security re-audit was run this pass (the prior `docs/SECURITY_REVIEW.md` findings are unchanged; this pass's own new code was spot-checked, not independently re-audited).

**Closed since the first hardening pass** (previously listed here, now
resolved with tests -- see `FINAL_RELEASE_REMAINING_WORK.md` for full
evidence): data-quality validation layer now exists and gates the
scanner; `integrity_check()`/`db_size_bytes()` now cover all 12 stores,
not 3; predictions duplicate-prevention is now a real DB-level
constraint, not application-level only; paper position state
transitions are now guarded (CLOSED is enforced as terminal).

None of the above represent unsafe behavior: live order execution
remains structurally blocked (`tests/test_dhan_no_real_orders.py`,
confirmed unmodified and passing across both passes), the deterministic
risk/decision core is untouched, and every safety-critical
restart/recovery path that was checked (kill-switch, paper-position
restart, scheduler-lock reclamation) was found already correct and left
as-is.

## Remaining external dependencies

- Dhan credentials and live connectivity are not available in this
  development environment; live-broker behavior beyond the
  structurally-enforced no-real-orders invariant is not independently
  re-verified against a real Dhan session this session.
- Yahoo Finance's continued availability and rate limits (unofficial,
  free-tier API) remain an external dependency with no official
  NSE/BSE/SEBI alternative.
- The Claude/LLM API's continued availability for the critic/RAG layer
  (confirmed non-blocking to the deterministic core, per failure-mode
  analysis #3).

## Remaining research uncertainty

The Phase 1 ML baseline demonstrated **no statistically meaningful
edge** over the deterministic benchmark (ROC-AUC 0.575-0.615, both
model and benchmark scoring `NEGATIVE` on every walk-forward fold and
the held-out test). This is a settled, frozen research result from
this project's own Phase 1 work -- it is reported here as unresolved
*research* uncertainty (whether a genuinely predictive signal exists
in this feature set at all), not as an engineering defect. No attempt
was made this session, or should be made without a new, separately
pre-registered experiment, to revisit, reframe, or extract a positive
result from that finding.

---

**Live trading: DISABLED**
**Claude Code runtime dependency: NONE** (the hardened system --
scheduler, dashboard, CLI, MCP server, paper engine, decision engine --
runs as ordinary Python processes with no dependency on Claude Code,
an IDE, or any AI agent at runtime; AI involvement is confined to the
optional, non-blocking critic/RAG advisory layer, which the system
continues to operate correctly without per failure-mode analysis #3)
**Release recommendation: NOT READY**

Rationale: across both hardening passes, every P0 item identified by a
fresh, evidence-based re-audit has been closed with a real fix and a
test proving it -- datetime duplication, SQLite concurrency resilience,
a scheduler uncaught-exception path, a genuine cache-staleness
correctness bug, a previously-nonexistent data-quality validation
layer now gating the scan->decision->paper-trade path, an unguarded
paper-position state machine, and app-level-only prediction
duplicate-prevention now backed by a real DB constraint. The
live-trading-safety boundary was re-verified untouched after every
single change (`git diff --stat main`, both passes). However, the
mission's own Definition of Done still spans unified observability, a
full documentation suite, systematic chaos testing, schema-version
tracking, and a broader migration mechanism across all 12 stores that
remain genuinely unimplemented, not merely undocumented. Per the
mission's own standard ("a final product can have known limitations, it
cannot have known unsafe behavior"), the system is safe to continue
operating in paper-trading mode as it has been, but does not yet meet
the bar for being declared the final, independently-operable product
this mission defines. The concrete next-priority items are the P1-2
(remainder)/P1-3/P1-4/P2 rows in `FINAL_RELEASE_REMAINING_WORK.md`.
