# Final Product Readiness Report

Branch: `final-product-hardening` (not yet merged to `main` as of this
report). Companion documents: `FINAL_PRODUCT_AUDIT.md`,
`FINAL_FAILURE_MODE_ANALYSIS.md`. Full regression: **1989 passed, 0
failed** (`hardening_regression2.log`, run after every change in this
session).

This report is deliberately honest about scope. The originating
mission (55 sections) is a genuine production-hardening campaign, not
completable end-to-end in one session. What follows separates what was
actually hardened and tested this session from what remains open,
rather than overstating completion.

---

**Architecture**: Stable, layered (data -> features -> prediction ->
decision -> risk -> execution -> persistence -> learning), unchanged in
shape this session. Datetime handling was structurally consolidated
(`core/timeutil.py`) and SQLite connection/integrity handling was
structurally consolidated (`core/sqlite_util.py`), closing two real
cross-cutting duplication risks without altering the architecture.

**Data**: Yahoo Finance intraday (5-min bars, ~60-day window) plus
India VIX and sector indices; NSE/BSE/SEBI have no official API (known,
prior finding, unchanged). No formal OHLC-sanity/data-quality
validation layer exists yet (disclosed gap, see failure-mode analysis
#2). Cache-staleness reporting was fixed at the root cause this
session (a bound-default parameter defeating overrides), not patched.

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

**Paper trading**: Working, hardened this session (WAL mode, 30s busy
timeout, new `integrity_check()`/`db_size_bytes()` methods on
`PaperStore`). Restart-recovery of open positions has real, pre-existing
test coverage (`tests/test_paper_restart.py`), re-confirmed passing.

**Dashboard**: Working, unmodified this session. No authentication if
exposed beyond loopback (known, accepted for the current single-operator
threat model; not a new finding).

**CLI**: Working, ~30 subcommands, unmodified this session except the
new `--cache-root` flag on `daily-report`.

**Persistence**: All 12 SQLite stores now use WAL mode + a 30s busy
timeout (was: no WAL, 5s stdlib default), verified via a real
threading-based concurrent-reader-not-blocked-by-writer test. 3 of 12
stores (scheduler, paper, live_state -- the most safety-critical) now
expose `integrity_check()`; 9 of 12 do not yet. Only 1 of 12 has a
schema-migration mechanism (`_ensure_column`-equivalent); the other 11
do not (disclosed gap).

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

**Testing**: 1989 tests passing, 0 failing, after every change in this
session, including a real threading-based concurrency test and a real
failure-injection test for the scheduler (not merely more assertions on
existing paths). Test suite growth this session: +13 (`core/timeutil`),
+6 (`core/sqlite_util`), +6 (integrity/size checks on `paper`/
`live_state` stores), +1 (scheduler failure injection); 3 pre-existing
tests were fixed from flaky/environment-dependent to fully hermetic.
Chaos/failure-injection testing beyond this one new scheduler test was
not expanded this session (disclosed gap against the mission's broader
"chaos testing" ask).

---

## Known limitations (disclosed, not unsafe)

1. No formal data-quality validation layer for OHLC sanity (missing/duplicate/non-monotonic bars, impossible high/low/close relationships).
2. No unified startup self-diagnostic command producing DEGRADED vs SAFE-STOP status across all subsystems.
3. `integrity_check()` exists on 3 of 12 SQLite stores, not all 12; no automatic invocation at startup on any of them yet.
4. Schema-migration mechanism exists on 1 of 12 stores; the other 11 have no equivalent for future schema changes.
5. Predictions duplicate-prevention is application-level only, not enforced by a database `UNIQUE` constraint.
6. No per-job scheduler timeout; no documented fairness guarantee for overlapping custom scheduler slot windows.
7. Cache-staleness thresholds remain divergent across `daily-report` (now canonical, fixed), `cache-status` (30 days), and `readiness-check` (hardcoded 7 days) -- not fully unified.
8. Config-loading validation is inconsistent across subsystems -- some fail fast with a clear error, others may silently fall back to a default.
9. No unified health/observability dashboard spanning every subsystem in one view.
10. No dedicated `INSTALLATION.md`/`USER_GUIDE.md`/`OPERATIONS_GUIDE.md`/`TROUBLESHOOTING.md`/`ARCHITECTURE.md`/`SECURITY.md` document suite (README and phase-history docs are extensive but not organized this way).
11. Clean-install / no-Claude-Code-dependency verification was not explicitly re-run this session as a standalone test.
12. Chaos/failure-injection testing is limited to the one new scheduler test; broader chaos testing (provider outage simulation, disk-full simulation, DB corruption simulation) was not built this session.
13. Dashboard has no authentication; safe only for the current loopback/single-operator deployment model.

None of the above represent unsafe behavior: live order execution
remains structurally blocked (`tests/test_dhan_no_real_orders.py`,
confirmed unmodified and passing), the deterministic risk/decision core
is untouched, and every safety-critical restart/recovery path that was
checked (kill-switch, paper-position restart, scheduler-lock
reclamation) was found already correct and left as-is.

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

Rationale: this session closed real, verified P0/P1-adjacent gaps
(datetime duplication, SQLite concurrency resilience, a scheduler
uncaught-exception path, a genuine cache-staleness correctness bug) with
tests proving each fix, and left the live-trading-safety boundary
completely untouched and re-verified intact. However, the mission's own
Definition of Done spans data-quality validation, unified observability,
a full documentation suite, broader chaos testing, and several
database-hardening items (migration mechanism, DB-level uniqueness
constraints, startup self-diagnostics) that remain genuinely
unimplemented, not merely undocumented. Per the mission's own standard
("a final product can have known limitations, it cannot have known
unsafe behavior"), the system is safe to continue operating in
paper-trading mode as it has been, but does not yet meet the bar for
being declared the final, independently-operable product this mission
defines. The concrete next-priority items are listed above in
`FINAL_FAILURE_MODE_ANALYSIS.md`'s summary, in P1/P2 order.
