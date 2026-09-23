# Master Known-Issues List

Consolidated, evidence-labeled inventory, last updated 2026-09-23, covering: the 2026-09-22
full-system red-team pass (commit `501dbf0`, see `docs/FULL_SYSTEM_RED_TEAM_2026-09-22.md`), the
2026-09-22 continuous-loop follow-on pass (`docs/CONTINUOUS_FULL_SYSTEM_RED_TEAM_FINAL_2026-09-22.md`),
and the 2026-09-23 open-issues remediation pass (`docs/FINAL_OPEN_ISSUES_REMEDIATION_2026-09-23.md`)
that resolved most items the earlier two passes left open. Every entry below has a real `Status`;
nothing is listed without one. IDs prefixed `F` are from the first pass, `G` from the
continuous-loop pass (`G9-B` added 2026-09-23), `R` are research-methodology items. R3-R6 were
investigated and classified in the 2026-09-23 pass (none required reopening a verdict); R1-R2
(below) are carried over from the 2026-09-22 pass, not re-investigated tonight, and remain
`RESEARCH_DECISION_REQUIRED`. This file supersedes ad hoc "known issue" mentions scattered across
older reports for anything it lists — where this file and an older report disagree, this file is
the newer, independently re-verified state.

---

### F1 — CandleBuilder `close` reflected arrival order, not exchange-time order

- **Severity**: High
- **Component**: `live/dhan/candle_builder.py`
- **Status**: FIXED
- **Evidence**: `bar.close` could equal an out-of-order tick's price instead of the
  chronologically-latest one within a bucket.
- **Reproduction**: `tests/test_dhan_candle_builder.py::test_close_reflects_the_chronologically_latest_tick_not_the_most_recently_arrived_one`
- **Root cause**: `close` was overwritten unconditionally on every merged tick, regardless of the
  tick's own exchange timestamp relative to what was already merged.
- **Fix**: commit `c7c9bb7` — `close`/`last_source_timestamp` now only advance when the incoming
  tick's timestamp is `>=` the latest already merged.
- **Test**: see Reproduction above; also `::test_close_still_advances_normally_when_ticks_arrive_in_chronological_order`.
- **Residual risk**: none for this specific mechanism. See G3 for a second-order defect this fix
  itself introduced, since fixed.

### F2 — NaN/Inf ticks not rejected in CandleBuilder

- **Severity**: High
- **Component**: `live/dhan/candle_builder.py`
- **Status**: FIXED
- **Evidence**: `nan <= 0`, `nan > threshold`, `inf <= 0` all evaluate `False`, so NaN/Inf passed
  every existing validity gate.
- **Reproduction**: `tests/test_dhan_candle_builder.py::test_non_finite_price_is_rejected_never_merged_into_a_bucket`
- **Root cause**: no explicit finiteness check anywhere in the tick-validation gate.
- **Fix**: commit `c7c9bb7` — explicit `math.isfinite()` check added first, before other gates.
- **Test**: see Reproduction; also `::test_a_nan_price_never_permanently_poisons_the_deviation_gate_for_later_ticks`.
- **Residual risk**: none identified.

### F3 — No time-based worker staleness detection ("healthy but actually dead")

- **Severity**: High
- **Component**: `live/fleet_supervisor.py`, `live/heartbeat.py`
- **Status**: FIXED
- **Evidence**: `docs/DHAN_FEED_INTERRUPTION_1514_INVESTIGATION_2026-09-22.md` documents the real
  2026-09-17 incident this describes.
- **Reproduction**: `tests/test_fleet_supervisor.py::test_check_worker_health_unresponsive_when_heartbeat_is_stale_even_with_ordinary_log_lines`
- **Root cause**: `check_worker_health` had no time component at all.
- **Fix**: commit `552894e` — new `WorkerHealth.UNRESPONSIVE`, checked via `heartbeat.json` age
  (300s threshold) before the log-content scan.
- **Test**: see Reproduction; 5 more tests in the same file.
- **Residual risk**: detection only, not auto-recovery (deliberate scope). Second-order review
  confirmed the 300s threshold is safe for every `--interval` value (heartbeat cadence is bounded
  by the feed-queue poll timeout, ~5s, independent of bar interval) — see
  `docs/CONTINUOUS_FULL_SYSTEM_RED_TEAM_FINAL_2026-09-22.md` §19.

### F4 — Partial fleet launch orphaned already-spawned workers

- **Severity**: Medium
- **Component**: `main.py::run_fleet_supervise_command`
- **Status**: FIXED (and its own cleanup path hardened further — see G4)
- **Evidence**: launch loop ran before the `try/finally: shutdown_fleet(handles)` block.
- **Reproduction**: `tests/test_cli.py::test_run_fleet_supervise_command_cleans_up_already_launched_workers_when_a_later_one_fails_to_launch`
- **Root cause**: missing exception boundary around the launch loop specifically.
- **Fix**: commit `552894e`.
- **Test**: see Reproduction.
- **Residual risk**: none for the original scenario; see G4 for a second-order gap in the fix
  itself, since closed.

### F5 — Corrupted venv interpreter raised an uncaught OSError

- **Severity**: Medium
- **Component**: `live/environment_guard.py`
- **Status**: FIXED
- **Evidence**: `venv_python.exists()` doesn't distinguish "valid interpreter" from "corrupted
  binary."
- **Reproduction**: `tests/test_environment_guard.py::test_ensure_running_under_project_venv_fails_loudly_not_with_a_raw_traceback_when_the_venv_python_is_corrupted`
- **Root cause**: no `try/except` around the re-exec `subprocess.run` call.
- **Fix**: commit `552894e`.
- **Test**: see Reproduction.
- **Residual risk**: none identified; second-order review independently confirmed `except OSError`
  is exhaustive for this call's real failure surface (no `timeout=`/`check=True` passed).

### F6 — Pre-existing Hypothesis flake in `test_market_indicators_properties.py`

- **Severity**: Medium
- **Component**: `tests/test_market_indicators_properties.py`
- **Status**: FIXED (investigated, root-caused, then re-scoped — see G5)
- **Evidence**: failed twice during full-suite runs, never in isolation; `derandomize=True` rules
  out a genuine data-dependent bug.
- **Root cause**: Hypothesis's own data-generation wall-clock budget, sensitive to concurrent load
  in a 2700+-test suite — not an indicator defect.
- **Fix**: commit `09ee9fc` (initial fix, applied too broadly), narrowed in the continuous-loop
  pass — see G5.
- **Test**: `tests/test_market_indicators_properties.py::test_compute_sma_never_raises_regardless_of_length_vs_period`, stable across the full 2746+-test suite.
- **Residual risk**: none.

### G1 — `dashboard/intelligence.py` store-connection leaks on the exception path

- **Severity**: Medium
- **Component**: `dashboard/intelligence.py`
- **Status**: FIXED
- **Evidence**: 10 functions closed their store with a bare `.close()` call, with real computation
  (confidence calibration, profitability reports) happening between open and close — inconsistent
  with `live/workstation.py`/`live/fleet_summary.py`'s own established `try/finally` convention for
  the identical operation.
- **Reproduction**: code inspection (an exception raised mid-computation left the connection
  unclosed on that path); no dedicated new test added (behavior-preserving refactor, covered by
  existing dashboard/intelligence tests exercising the happy path).
- **Root cause**: inconsistent application of an already-established pattern.
- **Fix**: this pass — every function now wraps its store use in `try/finally`.
- **Test**: `tests/test_dashboard.py` (existing suite, re-verified green after the change).
- **Residual risk**: none identified.

### G2 — `get_live_sim_status()` hardcoded `source: MOCK` regardless of real feed source

- **Severity**: Medium
- **Component**: `live/workstation.py`, surfaced via `mcp_server/server.py::get_live_sim_status_tool`
- **Status**: FIXED
- **Evidence**: dormant on the dashboard itself (never rendered there), but surfaced verbatim to
  any MCP client — would falsely report `source: MOCK` during a genuine `--source dhan` session.
- **Reproduction**: `tests/test_live_workstation.py::test_get_live_sim_status_reports_the_real_source_from_feed_status`
- **Root cause**: literal hardcoded dict values, never actually derived from anything.
- **Fix**: this pass — derives an honest answer from `live_state.db`'s own `feed_status` table
  (`UNKNOWN` if no data yet, `MIXED` if symbols disagree, never guessed).
- **Test**: see Reproduction; 2 more tests in the same file; existing MCP test
  (`tests/test_mcp_live_workstation.py::test_get_live_sim_status_tool_reflects_a_pending_approval`)
  re-verified green (the mock-source scenario it exercises correctly derives `SIMULATED`/`MOCK`
  from real feed_status data now, not a hardcoded string).
- **Residual risk**: none identified.

### G3 — CRITICAL second-order defect: the F1 fix broke redelivery-duplicate detection

- **Severity**: High
- **Component**: `live/dhan/candle_builder.py`
- **Status**: FIXED (found and closed within the same session as F1, before any live use)
- **Evidence**: found by a dedicated adversarial second-order review of F1's own diff.
- **Reproduction**: `tests/test_dhan_candle_builder.py::test_a_genuine_redelivery_of_an_out_of_order_tick_still_does_not_double_count_volume`
  (failed against the F1-only code: `bar.volume` was 20 instead of the correct 15).
- **Root cause**: F1 made `last_source_timestamp`/`close` track the chronological-MAX tick, but the
  redelivery-duplicate check compared against those same fields — a real wire-redelivery of an
  out-of-order tick no longer matched, so its volume was double-counted.
- **Fix**: this pass — added `last_merged_timestamp`/`last_merged_price` (unconditional, arrival
  order) as a separate pair of fields used ONLY by the redelivery check, decoupled from
  `close`/`last_source_timestamp` (chronological order, used for the bar's own OHLC).
- **Test**: see Reproduction.
- **Residual risk**: none identified for this mechanism.

### G4 — Launch-failure cleanup handler wasn't itself exception-safe

- **Severity**: Low
- **Component**: `main.py::run_fleet_supervise_command`
- **Status**: FIXED
- **Evidence**: found by the same second-order review, targeting F4's own diff.
- **Reproduction**: `tests/test_cli.py::test_run_fleet_supervise_command_still_reports_the_original_failure_when_cleanup_itself_raises`
- **Root cause**: `shutdown_fleet(handles)` (and the `print()` calls around it) had no exception
  boundary inside the new `except Exception` block — a failure during cleanup (e.g. a broken
  stdout pipe) would replace the clean `SystemExit(1)` report with a raw traceback.
- **Fix**: this pass — wrapped in its own `try/except Exception`, logs and continues to the
  original `SystemExit(1)` regardless.
- **Test**: see Reproduction.
- **Residual risk**: none identified.

### G5 — Hypothesis health-check suppression applied too broadly

- **Severity**: Low
- **Component**: `tests/test_market_indicators_properties.py`
- **Status**: FIXED
- **Evidence**: F6's own fix suppressed `HealthCheck.too_slow` on the SHARED `_PROPERTY_SETTINGS`
  object used by all 14 property tests in the file, not just the one that actually flaked —
  silently disabling genuine speed-regression detection for the other 13, permanently.
- **Root cause**: over-broad scope of the original fix.
- **Fix**: this pass — reverted `_PROPERTY_SETTINGS` to its original (no suppression), added a
  separate `_FLAKY_UNDER_LOAD_SETTINGS` applied only to the one flaky test.
- **Test**: `tests/test_market_indicators_properties.py` (all 14 tests re-verified green).
- **Residual risk**: none identified.

### G6 — No path-separator rejection in `symbol_runtime_paths`

- **Severity**: Low (not currently exploitable)
- **Component**: `live/runtime_layout.py`
- **Status**: FIXED (defensive hardening)
- **Evidence**: a `symbol` value could in principle contain `/`, `\`, or `..`, resolving the
  derived path outside the intended `runtime_dir` tree.
- **Reproduction**: `tests/test_runtime_layout.py::test_a_symbol_containing_a_path_separator_or_parent_reference_is_rejected`
- **Root cause**: symbol normalization only handled case/whitespace, not path-shaped characters.
- **Fix**: this pass — explicit rejection added.
- **Test**: see Reproduction; also `::test_an_ordinary_dotted_symbol_still_works` (regression
  guard for legitimate `SYMBOL.NS`-shaped names).
- **Residual risk**: none — every current caller already sources `symbol` from trusted,
  operator-supplied input (CLI args, local YAML), so this is defense-in-depth, not a fix to an
  active exploit path.

### G9 — Dashboard/single-workstation dual-writer risk

- **Severity**: High (scoped narrowly — does not affect the fleet workflow)
- **Component**: `paper/engine.py`, `paper/store.py`, `live/workstation.py`
- **Status**: FIXED (2026-09-23 remediation pass)
- **Evidence**: `get_live_engine()` caches a `PaperTradingEngine` singleton for the dashboard
  process's entire lifetime; `self.account` was loaded once (`PaperTradingEngine.__init__`) and
  never refreshed. `submit_signal()`'s RiskEngine evaluation used this same cached `self.account`,
  not a fresh re-read from the store; `process_bar`'s own account mutations could likewise
  silently overwrite a concurrently-running second process's committed changes (a lost update).
- **Investigation** (full writer/reader map, before any fix): traced every writer and reader of
  `data/live_sim_trading.db`'s `account` row. Writers: `PaperTradingEngine.submit_signal`
  (evaluates risk against `self.account`, does not mutate it), `process_bar`/`close_at_end_of_data`
  (mutate `self.account` in place via `roll_to_day`/`mark_to_market`/`open_position`/
  `close_position`, then `store.save_account`). Readers: the same three methods, plus
  `live/workstation.py`'s display functions. Confirmed `PaperStore`'s connection is
  `isolation_level=None` (autocommit) + WAL, so a fresh `SELECT` outside an open transaction
  always sees the latest committed state from another process — the gap was purely that nothing
  ever issued that fresh read. Confirmed `store.transaction()` used plain `BEGIN` (SQLite
  DEFERRED), so two processes could both pass a check-then-act read (e.g. `get_pending_order`)
  before either's write landed — a genuine cross-process TOCTOU independent of the account-caching
  issue. Confirmed the account model is single-position-only (`risk/account.py`), so two
  *different* symbols cannot both hold an open position in one account, naturally limiting (but
  not eliminating — a lost update to `cash`/`peak_equity`/`daily_pnl` remains possible) one class
  of dual-writer scenario.
- **Root cause**: a single-writer-per-process design (correct in isolation) combined with a
  documented, intended use case (dashboard + CLI simultaneously) that violates that assumption.
- **Scope**: affects the single-symbol workstation pages (`/`, `/signals`, `/portfolio`) that use
  `get_live_engine()`/`data/live_sim_trading.db`. The fleet workflow (`/fleet`, `fleet-supervise`,
  `fleet-summary`) is NOT affected — each symbol's runtime directory is fully isolated, and
  `/fleet` reads via fresh, short-lived store connections per request, never a cached engine.
- **Fix** (chosen architecture: option (b) from the earlier report — always re-fetch fresh state
  immediately before any write-path decision, rather than making the dashboard read-only or
  routing through the supervisor, since dashboard approve/reject is a required, documented
  control and the fleet already has full process-level isolation as its own single-writer
  guarantee):
  1. `PaperTradingEngine.refresh_account()` (`paper/engine.py`) — a fresh `store.get_account()`
     read, called at the top of `submit_signal`'s transaction, `process_bar`'s transaction,
     `close_at_end_of_data`'s transaction, AND (2026-09-23, same pass) at the top of every
     read-only display function in `live/workstation.py` (`get_account_state`, `get_risk_state`,
     `get_risk_halt_reasons`, `get_live_sim_status`, `get_risk_decision_for_pending`) — closing
     both the write-path safety issue and the read-path "dashboard shows stale P&L" issue.
  2. `PaperStore.transaction()` now issues `BEGIN IMMEDIATE`, not plain `BEGIN` — acquires
     SQLite's own RESERVED lock atomically at the start of the transaction (a native OS-level
     file lock, so a crashed holder cannot leave it stale — the OS releases it when the process's
     file descriptor closes) instead of only at the first write, closing the cross-process
     check-then-act race for order/position creation. A losing transaction waits (existing 30s
     busy timeout) or fails loudly with `sqlite3.OperationalError: database is locked` — never
     silently proceeds against stale data.
- **Second-order effects found and fixed in the SAME pass**: two existing tests
  (`tests/test_paper_advance.py::test_advance_holds_back_a_stale_pending_order_on_max_daily_loss`,
  `tests/test_live_workstation.py::test_get_risk_halt_reasons_reflects_a_real_consecutive_loss_hard_limit_breach`)
  mutated `engine.account` directly in memory without persisting, as a test-isolation shortcut —
  a state this engine can never legitimately be in during real operation (every real mutation
  persists before any other call could observe it). `refresh_account()` correctly discarded that
  artificial, unpersisted state, exactly as it must; both tests were fixed to persist their
  injected state via `store.save_account(...)`, matching what real code always does.
- **Test**: `tests/test_paper_engine.py::test_submit_signal_sees_a_second_processs_committed_account_changes`,
  `::test_two_engine_instances_racing_different_signals_for_the_same_symbol_never_both_open_an_order`
  (real cross-process concurrency, two connections on one file db, `threading.Barrier`-synchronized).
- **Residual risk**: none identified for the read/write staleness this fix targets. See G9-B
  below for one narrower remaining gap found during the concurrency red-team of this fix.
- **Second call site found during the fresh final red-team pass (Part 19, 2026-09-23)**:
  `mcp_server/server.py` has its OWN separate module-level `_paper_engine` singleton (a SEPARATE
  account, `data/paper_trading.db`, not the same file as the dashboard's
  `data/live_sim_trading.db` — but `main.py paper ...` (a distinct CLI command from `paper-live`)
  defaults to that SAME file, so a long-running MCP server process (e.g. Claude Desktop connected)
  alongside a manual `main.py paper ...` run is the identical defect class). The write-path
  (`paper_trade_signal_tool` -> `submit_signal`) was ALREADY automatically protected — the fix
  lives inside `PaperTradingEngine` itself, not the caller — but `get_account_tool`/
  `get_paper_status_tool` read `engine.account` directly without refreshing first, the same
  display-staleness gap already closed for `live/workstation.py`. Fixed the same way: both now
  call `engine.refresh_account()` before reading. Test: `tests/test_mcp_paper.py`/
  `tests/test_mcp_server.py` (35 tests, re-verified green; no dedicated new test added — this is
  the same, already-tested `refresh_account()` mechanism applied at two more call sites).

### G9-B — `PaperTradingEngine.account` still not refreshed inside `_fill_pending_order`/`_process_open_position`/`_close_position`'s own sub-steps mid-transaction

- **Severity**: Low (narrow — would require a THIRD account-mutating call to interleave inside an
  already-`BEGIN IMMEDIATE`-locked transaction, which `BEGIN IMMEDIATE` itself prevents for any
  OTHER process, so this is only a same-process, same-call reentrancy question)
- **Component**: `paper/engine.py`
- **Status**: `ACCEPTED_RISK` — investigated, not a reachable defect
- **Evidence**: `refresh_account()` is called once at the top of `process_bar`'s transaction; the
  internal helpers it calls afterward (`_fill_pending_order`, `_process_open_position`,
  `_close_position`) all mutate the SAME `self.account` object refreshed at the top, never
  re-reading again mid-transaction.
- **Investigation**: since `BEGIN IMMEDIATE` (G9 fix) guarantees no OTHER process's transaction can
  interleave between this transaction's start and its commit, and `process_bar` makes no reentrant
  call back into itself or into `submit_signal` while its own transaction is open, there is no
  window in which `self.account` could go stale AFTER the top-of-transaction refresh within a
  single `process_bar` call. Confirmed by direct code reading of all three helpers: no store reads
  of `account` occur in any of them (they only mutate the in-memory object already refreshed).
- **Decision**: no fix needed — this is the lock working as intended, not a gap.

### G10 — No Starlette exception handler on the dashboard

- **Severity**: Low
- **Component**: `dashboard/app.py`
- **Status**: FIXED (2026-09-23 remediation pass)
- **Evidence**: a corrupted DB file (`DatabaseCorruptedError`) or any other uncaught exception in a
  route handler produced a raw 500/traceback rather than a clean error page.
- **Fix**: `Starlette(routes=[...], exception_handlers={Exception: _handle_uncaught_exception})` —
  a single, generic, safety-neutral handler: logs the real exception+traceback server-side via
  `logger.exception`, returns a clean, self-contained (no live DB/workstation reads of its own —
  see the second-order finding below) 500 HTML page to the browser.
- **Second-order bug found and fixed in the SAME pass**: the first version of this handler reused
  `_page()` for visual consistency, but `_page()` itself renders live banners
  (`_broker_connectivity_banner()` and friends) that read the exact same workstation/DB state that
  could be the thing failing — a genuinely corrupted DB would make the error page ITSELF raise a
  second, unhandled exception, defeating the fix. Caught by this fix's own regression test before
  ever being committed as the final version. Rewritten to be fully self-contained (a static HTML
  string, zero live reads).
- **Test**: `tests/test_dashboard.py::test_an_uncaught_exception_in_a_route_returns_a_clean_page_not_a_raw_traceback`
  (also proves the second-order fix: the SAME test forces `get_feed_status` to always raise,
  which would break `_page()`'s own banners too, and asserts a real, non-empty response body),
  `::test_other_pages_are_unaffected_by_the_new_exception_handler`.
- **Residual risk**: none identified.

### G11 — `/api/state`'s docstring claimed a polling script that doesn't exist

- **Severity**: Low (documentation-only)
- **Component**: `dashboard/app.py`
- **Status**: FIXED (2026-09-23 remediation pass, documentation correction only)
- **Evidence**: the route's own docstring said a "small vanilla-JS snippet... polls it to update
  DOM nodes in place"; `_page()`'s own docstring made the same claim. Grep-confirmed: no
  `<script>`/`fetch`/`setInterval` exists anywhere in `dashboard/app.py`. The only real refresh
  mechanism is the 15s `<meta http-equiv="refresh">` full-page reload.
- **Fix**: both docstrings corrected to state the real, current behavior honestly (the endpoint is
  real, correct, and safe, but unused by any client-side code today) rather than implementing the
  described-but-never-built polling feature, which would be new frontend scope beyond this pass —
  a deliberate, disclosed decision, not an oversight. Also noted: since no client-side polling
  exists, Part 7's "polling response race" concern does not currently apply to this dashboard;
  that protection would need to be added AT THE SAME TIME as any future polling script, using each
  response's own `as_of` timestamp to discard an out-of-order reply.
- **Residual risk**: none functionally — purely a documentation-accuracy gap, now closed.

### G12 — `CandleBuilder` cross-thread reads had no lock (dormant)

- **Severity**: Low (not reachable in production today)
- **Component**: `live/dhan/candle_builder.py`, `live/dhan/market_data_source.py`
- **Status**: FIXED (2026-09-23 remediation pass, defensive hardening — confirmed still dormant)
- **Evidence**: `last_known_price`/`last_known_timestamp` (properties), `flush()`, and
  `rejected_tick_counts` (a plain dict) were read with no synchronization while `on_tick()`
  mutates the same state from the WebSocket receive thread. Confirmed still genuinely dormant
  (repo-wide search: no production caller of `market_data_source.py`'s `last_known_price`/
  `partial_candle`/`rejected_tick_counts_by_symbol` wrappers exists outside tests). Confirmed
  relying on GIL atomicity was never actually correct for a COMPOUND read (price paired with its
  own timestamp, across two separate attribute reads) even under a GIL build, and this Python
  3.14 install is confirmed (`sys._is_gil_enabled()`) to be a build where free-threaded (no-GIL)
  mode is a real, selectable option for this exact interpreter version.
- **Fix**: `CandleBuilder.__init__` gained `self._lock = threading.Lock()`. `on_tick` is now a
  thin wrapper (`with self._lock: return self._on_tick_locked(...)`) around its unchanged
  original body (renamed `_on_tick_locked`, avoiding a large, risky re-indentation of a ~270-line
  method). The three read paths (`last_known_price`, `last_known_timestamp`, `flush()`) are each
  individually lock-protected. New `last_known_price_and_timestamp()` reads the pair ATOMICALLY
  under one lock acquisition — the two individually-locked properties are each safe alone, but
  calling them separately (as `market_data_source.py`'s `last_known_price()` wrapper used to) is
  still a compound operation across two lock acquisitions, so a caller could observe a price from
  one tick paired with a timestamp from a later one; `market_data_source.py` now uses the new
  atomic accessor. New `rejected_tick_counts_snapshot()` (lock-protected copy) replaces
  `market_data_source.py`'s direct `dict(builder.rejected_tick_counts)` read.
- **Deadlock analysis**: a single, non-reentrant lock; `CandleBuilder` is documented pure (no I/O,
  no network), and no locked method calls another locked method — cannot deadlock by construction.
- **Test**: `tests/test_dhan_candle_builder.py::test_on_tick_and_last_known_price_and_timestamp_survive_real_concurrent_contention`
  (real threads, 2000 ticks, proves no torn/mismatched pair ever observed and no hang),
  `::test_rejected_tick_counts_snapshot_is_a_real_copy_not_a_live_reference`.
- **Residual risk**: none today — still dormant/unwired. Flagged as a landmine for whoever
  eventually wires these into the dashboard: the synchronization is now already in place.

### G13 — Second-order: a poisoned first tick can freeze `close` for a whole bucket

- **Severity**: Low (requires an already-anomalous upstream tick)
- **Component**: `live/dhan/candle_builder.py`
- **Status**: OPEN — re-investigated 2026-09-23, disclosed, deliberately not fixed
- **Evidence**: found by the second-order review of F1. If a bucket's first-arriving tick carries
  an anomalously large (but not rejected) timestamp, `close` freezes at that tick's value for the
  rest of the bucket instead of self-correcting on the next in-order tick (the pre-F1 behavior).
- **Root cause**: an interaction between F1's own chronological-ordering fix and an already-narrow
  external corruption class (a tick that passes existing timestamp-skew/plausibility gates but is
  still anomalous).
- **Re-investigation (2026-09-23)**: confirmed no cheap fix exists. The only correct fix would be
  a two-tick-agreement confirmation mechanism for the bucket-SEED tick specifically, analogous to
  `_baseline_confirmed`/`_pending_candidate_timestamp` (the cold-start mechanism this class
  already has) — but that mechanism itself was only reached correctly after TWO real production
  incidents (2026-09-17, 2026-09-21) exposed successive gaps in simpler designs. Building an
  analogous mechanism now, under this mission's own "no speculative rewrites" rule, for a
  compound-precondition edge case (an upstream tick that already evaded BOTH the deviation AND
  timestamp-plausibility gates) risks repeating that same history inside one pass instead of two
  incidents' worth of real evidence.
- **Decision**: not fixed — genuinely cannot be fixed safely and cheaply right now, per the above.
  Disclosed, not hidden. Revisit if a real incident is ever traced to this pattern.
- **Residual risk**: low, narrow, unchanged from the prior pass's assessment.

### G14 — `trades` table lacked schema-level `UNIQUE(position_id)`

- **Severity**: Low (was mitigated by application discipline; now enforced at the DB level)
- **Component**: `paper/store.py`, `paper/errors.py`
- **Status**: FIXED (2026-09-23 remediation pass)
- **Evidence**: durability that a position closes at most once relied entirely on application
  discipline (single call site + transactional atomicity), not a schema constraint — unlike every
  OTHER terminal-state transition in this project (Position/PaperOrder both raise a typed error at
  the store level via `update_position`/`update_order`).
- **Fix**: `PaperStore._migrate_trades_unique_position_id_index()` — mirrors
  `predictions/store.py`'s own established `try_create_unique_index` migration pattern exactly.
  No column backfill needed (`position_id` was always populated, NOT NULL) — purely an additive
  `CREATE UNIQUE INDEX IF NOT EXISTS`. Exposed via
  `store.trade_position_uniqueness_enforced_at_db_level` (mirroring
  `duplicate_prevention_enforced_at_db_level`'s naming). `save_trade()` now catches the resulting
  `sqlite3.IntegrityError` and raises the new, typed `paper.errors.DuplicateTradeForPositionError`
  — mirroring `DuplicatePredictionError`'s exact pattern. If a pre-existing database already has
  duplicate `position_id` rows in `trades` (never observed in this project's own databases), index
  creation is skipped rather than crashing startup or deleting data — same soft-fail-and-report
  posture as every other migration of this kind in this project.
- **Test**: `tests/test_paper_store.py::test_new_paper_store_has_trade_position_uniqueness_enforced_at_db_level`,
  `::test_saving_a_second_trade_for_the_same_position_raises` (drives a REAL position through
  submit/fill/stop-close, then proves a second `save_trade` for the same position is rejected),
  `::test_two_connections_racing_to_save_a_trade_for_the_same_position_never_both_succeed` (real
  cross-process concurrency test — two connections on one file db, `threading.Barrier`-
  synchronized, proves the DB constraint, not application ordering, is what prevents the
  double-write), `::test_migration_disables_the_unique_index_gracefully_when_preexisting_duplicate_trades_exist`
  (raw-sqlite3-seeded pre-existing-duplicate scenario — confirms graceful degradation, no data
  loss, matching `predictions/store.py`'s own equivalent migration test).
- **Residual risk**: none identified.

### R1 — Point-in-time universe correction is not wired into the shared backtest engine

- **Severity**: Medium (methodology gap, not re-investigated this pass)
- **Component**: `backtesting/universe.py`, `backtesting/runner.py`, `backtesting/walk_forward.py`,
  `quant_research/universe_expansion.py`
- **Status**: `RESEARCH_DECISION_REQUIRED` (carried over from `docs/FULL_SYSTEM_RED_TEAM_2026-09-22.md`
  §R1, not touched in the 2026-09-23 pass)
- **Evidence**: full detail in the earlier report. Summary: real point-in-time universe correction
  exists (`quant_research/security_identity_map.py` + `point_in_time_fno_universe.py`) but only one
  standalone script pipeline uses it; every other backtest caller (including
  `quant_research/universe_expansion.py`, used by 5+ hypotheses) applies TODAY's current
  eligibility snapshot uniformly across the historical window.
- **Recommended action**: unchanged from the earlier report — a human decides whether to retrofit
  point-in-time correction into the shared engine before any future hypothesis.

### R2 — `H_MEANREV_013` is executed, published, and concluded, but its registry status is ambiguous by original design, not by omission

- **Severity**: Low (bookkeeping, reinforced not resolved by R5's reconciliation)
- **Component**: `strategy/hypothesis_registry.py`, `audit/edge_feasibility/`
- **Status**: `RESEARCH_DECISION_REQUIRED` (carried over from `docs/FULL_SYSTEM_RED_TEAM_2026-09-22.md`
  §R2; R5's 2026-09-23 registry accounting table below reconciles the COUNT but does not resolve
  whether `H_MEANREV_013` should ever gain a registry entry — that remains the human decision)
- **Evidence**: full detail in the earlier report. `H_MEANREV_013`'s own preregistration explicitly
  scoped it as "audit-only... written up there only if/when it graduates" — it did not graduate
  (concluded NOT SUPPORTED). Its absence from the registry is most plausibly the original,
  deliberate scoping decision, not an oversight.
- **Recommended action**: unchanged — a human decides whether to add a registry entry anyway (for
  completeness) or leave it as an audit-only document, consistent with its own preregistration.

### R3 — No purging/embargo in the backtest split logic

- **Severity**: Medium (methodology gap, confirmed not verdict-threatening)
- **Component**: `quant_research/market_behavior.py` (NOT `backtesting/walk_forward.py` — see below)
- **Status**: `CLASSIFIED — NO EFFECT` (investigated 2026-09-23, closed; not a code defect)
- **Evidence**: confirmed real — `build_symbol_dataset` (`quant_research/market_behavior.py:176-193`)
  computes forward-return labels (`close.shift(-h)`) over the full per-symbol series BEFORE
  `split_periods` divides it into dev/val/oos — a development row within `h<=20` bars of a
  boundary has its label computed partly from validation-window prices. Scope is narrower than
  originally stated: this mechanism affects only hypotheses built on `market_behavior.py`'s
  `SymbolDataset` — the F_CONTEXT family (12 entries), F_XSECT (6 entries), and `H_BREADTH_001`
  (~19 of 59 total). The other ~40 hypotheses run through `backtesting.engine.run_backtest`
  (causal trade simulation, no `shift(-h)` labels) — a structurally different mechanism this
  finding does not reach. `backtesting/walk_forward.py` also does not compute forward-return
  labels at all and has its own leakage test — its earlier inclusion as an affected component was
  imprecise.
- **Investigation**: max leak window (20 bars) is small relative to the smallest affected split
  (e.g. `H_CONTEXT_MARKET_006` development n=1068, <=2% boundary contamination); every affected
  verdict is REJECTED on large-magnitude, qualitative grounds (e.g. wrong-signed or
  structurally-empty condition buckets), not a borderline call this contamination could plausibly
  flip. `ml_research/walk_forward.py` (a separate, unused sibling module) already implements
  purge/embargo correctly and remains available as a template if this mechanism is ever extended.
- **Decision**: no rerun required for any hypothesis; no code change made (would be a speculative
  rewrite into a path confirmed to have no effect on any real conclusion). If `market_behavior.py`
  is ever extended to new hypotheses with thinner splits, backport `ml_research/walk_forward.py`'s
  embargo logic at that time.

### R4 — No dependence correction in confidence-interval machinery

- **Severity**: Medium (methodology gap, confirmed not verdict-threatening)
- **Component**: `learning/profitability.py`
- **Status**: `CLASSIFIED — NO EFFECT` (investigated 2026-09-23, closed; not a code defect)
- **Evidence**: confirmed real — `_mean_confidence_interval()` (`learning/profitability.py:158-165`)
  uses a plain i.i.d. normal approximation (`z * stdev / sqrt(n)`), no block-bootstrap/HAC/
  clustering by date or symbol. This machinery underlies most CI-decisive verdict language
  registry-wide, so its reach is broad, not narrow.
- **Investigation**: the defect is asymmetric — an understated (too-narrow) CI can only make an
  already-decisive result (positive or negative) look LESS decisive once corrected; a CI that
  already includes zero cannot become MORE zero-excluding by widening. Checked whether any
  verdict's classification depends on this: the one SUPPORTED entry (`H_ENTRY_001`) rests on a
  Monte Carlo percentile test, not this CI machinery; the one borderline CI-decisive-positive
  thread (`H_MEANREV_010`, already INCONCLUSIVE) was independently killed by portfolio-realism and
  point-in-time-universe reruns (`H_MEANREV_011`/`H_MEANREV_014`), unrelated to CI width.
- **Decision**: no rerun required; no code change made. A correct dependence-aware correction
  would, if anything, further reinforce the "NO DEMONSTRATED EDGE" verdict — implementing one now
  would be speculative work against a confirmed-non-verdict-threatening gap. Revisit if the
  H_MEANREV chain is ever reconsidered for promotion (the one place this could matter).

### R5 — Multiple-testing family-size accounting is stale/incomplete

- **Severity**: Medium (bookkeeping, confirmed not verdict-threatening)
- **Component**: `strategy/multiple_testing.py`, `audit/edge_feasibility/PHASE8_MULTIPLE_TESTING_AUDIT.md`
- **Status**: `CLASSIFIED — MINOR DISCLOSURE ISSUE` (investigated 2026-09-23; registry accounting
  table below is the fix — no code/verdict change)
- **Evidence**: confirmed — registry grew 56→59 entries since Phase 8's one-time manual analysis;
  `H_MEANREV_013` confirmed absent from the registry (id sequence jumps `H_MEANREV_012` ->
  `H_MEANREV_014`), deliberately (its own preregistration scopes it audit-only); the 4 derivatives
  hypotheses (`DERIV_001-004`, `audit/derivatives_research/PHASE6_DECISION_GATE_AND_TERMINAL_REPORT.md`)
  are tracked with their own honestly-disclosed, separate `family_size=4` Bonferroni correction —
  a disclosed parallel ledger, not a hidden omission. The 3 entries added since Phase 8
  (`H_CONTEXT_MARKET_006/007`, `H_MEANREV_014`) both extend EXISTING families and each already
  self-applies a correction that survives (`H_CONTEXT_MARKET_006` explicitly states its finding
  "remains CI-decisive under an additional family_size=3 Bonferroni correction").
- **Registry accounting table** (true honest count across the whole program, stated in no single
  document before this entry):

  | Ledger | Count | Where tracked |
  |---|---:|---|
  | `strategy/hypothesis_registry.py` entries | 59 | this file |
  | `H_MEANREV_013` (audit-only, tested, deliberately unregistered) | 1 | `audit/edge_feasibility/PHASE8_MULTIPLE_TESTING_AUDIT.md` |
  | Derivatives family (`DERIV_001-004`) | 4 | `audit/derivatives_research/PHASE6_DECISION_GATE_AND_TERMINAL_REPORT.md`, own `family_size=4` correction |
  | **True total distinct tested hypotheses** | **64** | reconciled here |

- **Decision**: a stricter (larger-family) correction can only push already-REJECTED/INCONCLUSIVE
  results deeper into null, never elevate one into a demonstrated edge — confirmed against the
  actual entries added since Phase 8, each of which already survives its own applicable
  correction. No hypothesis requires a rerun. Recommended future action (not done here, genuinely
  optional): fold this table into a refreshed Phase 8 document the next time the registry grows
  again, rather than re-deriving it by hand each time.

### R6 — `H_MEANREV_001`'s own entry doesn't disclose its cost model

- **Severity**: Low (confirmed not verdict-threatening)
- **Component**: `strategy/hypothesis_registry.py`
- **Status**: `FIXED` (documentation correction, no rerun — see below)
- **Evidence**: confirmed — `H_MEANREV_001` used the generic, non-NSE-specific default
  `CostModel()`; `H_MEANREV_003`'s entry discloses this retroactively, but `H_MEANREV_001`'s own
  entry did not.
- **Investigation**: `backtesting/costs.py`'s `india_nse_intraday_2026()` preset is strictly more
  expensive than the default (~0.11% extra round-trip: added fees_pct/taxes_pct, doubled exit
  slippage). `H_MEANREV_001`'s REJECTED point estimates (+0.09%/+0.13%/-0.26% across
  dev/val/oos for its lead candidate) would only move further negative under the realistic preset
  — cannot un-reject the verdict.
  - **Fix**: this pass — added the cost-model disclosure directly to `H_MEANREV_001`'s own
    `evidence` field in `strategy/hypothesis_registry.py`, stating the exact model used, the
    direction and rough magnitude of the more-realistic alternative, and that no rerun is planned
    because it cannot threaten the verdict. No number, threshold, or verdict was changed —
    additive disclosure text only.
  - **Test**: `tests/test_hypothesis_registry.py` (19 tests, re-verified green; none asserts on
    this entry's exact prose, so no test needed updating).

---

## Summary counts

| Status | Count |
|---|---:|
| FIXED (with regression test) | 18 (F1–F6, G1–G6, G9, G10, G11, G12, G14) |
| `ACCEPTED_RISK` (investigated, confirmed not a reachable defect) | 1 (G9-B) |
| OPEN — disclosed, deliberately not fixed, low residual risk | 1 (G13) |
| `CLASSIFIED — NO EFFECT` (investigated, closed, no code change) | 2 (R3, R4) |
| `CLASSIFIED — MINOR DISCLOSURE ISSUE` | 1 (R5, reconciliation table added) |
| `FIXED` (research, documentation-only) | 1 (R6) |
| `RESEARCH_DECISION_REQUIRED` | 2 (R1, R2 — carried over, not re-investigated this pass) |

No entry in this file is a critical or unresolved safety-invariant violation. As of the
2026-09-23 remediation pass, no open item is High severity — G9 (the prior single highest-severity
open item) is now FIXED. G13 is the only remaining OPEN code-level item, and it is Low severity
and narrow-trigger. R1/R2 are the only remaining `RESEARCH_DECISION_REQUIRED` items, both
Medium/Low severity and both explicitly judged non-verdict-threatening in their own earlier
investigations.
