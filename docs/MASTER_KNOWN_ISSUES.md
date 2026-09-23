# Master Known-Issues List

Consolidated, evidence-labeled inventory as of 2026-09-22, covering both tonight's earlier
full-system red-team pass (commit `501dbf0`, see `docs/FULL_SYSTEM_RED_TEAM_2026-09-22.md`) and
the continuous-loop follow-on pass documented in
`docs/CONTINUOUS_FULL_SYSTEM_RED_TEAM_FINAL_2026-09-22.md`. Every entry below has a real
`Status`; nothing is listed without one. IDs prefixed `F` are from the first pass, `G` from the
continuous-loop pass, `R` are research-methodology items requiring a human decision (not code
defects). This file supersedes ad hoc "known issue" mentions scattered across older reports for
anything it lists — where this file and an older report disagree, this file is the newer,
independently re-verified state.

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

### G9 — Dashboard/single-workstation dual-writer risk (NOT FIXED — real, architectural)

- **Severity**: High (scoped narrowly — does not affect the fleet workflow)
- **Component**: `live/workstation.py::get_live_engine`, `paper/engine.py::submit_signal`
- **Status**: OPEN — requires an architectural decision, not attempted under time pressure
- **Evidence**: `get_live_engine()` caches a `PaperTradingEngine` singleton for the dashboard
  process's entire lifetime; `self.account` is loaded once (`PaperTradingEngine.__init__`) and
  never refreshed. `submit_signal()`'s RiskEngine evaluation (`paper/engine.py:191`) uses this
  same cached `self.account`, not a fresh re-read from the store.
- **Reproduction**: not executed as a live test (would require two real, concurrently-running
  processes against the same `data/live_sim_trading.db`); reasoned from direct code reading,
  confirmed via `dashboard/app.py`'s own comment that the dashboard and the CLI are genuinely
  separate OS processes sharing this file by design (`live/workstation.py`'s own module docstring:
  "so an operator can observe or decide from either the CLI or an MCP-connected client and see the
  same state").
- **Root cause**: a single-writer-per-process design (correct in isolation) combined with a
  documented, intended use case (dashboard + CLI simultaneously) that violates that assumption —
  not a coding mistake so much as an unexamined interaction between two individually-correct
  designs.
- **Scope**: affects ONLY the single-symbol workstation pages (`/`, `/signals`, `/portfolio`) that
  use `get_live_engine()`/`data/live_sim_trading.db`. The fleet workflow (`/fleet`,
  `fleet-supervise`, `fleet-summary`) is NOT affected — each symbol's runtime directory is fully
  isolated, and `/fleet` reads via fresh, short-lived store connections per request, never a
  cached engine.
- **Fix**: none applied. Two candidate directions for a human decision: (a) enforce single-writer
  (the dashboard becomes read-only for account state whenever a CLI process might also be active),
  or (b) always re-fetch `store.get_account()` fresh immediately before any write-path RiskEngine
  evaluation, never trusting a cached in-memory copy for that specific purpose. Either is a real
  design change to a currently load-bearing assumption in `PaperTradingEngine`, not a "minimal
  fix," and both need to be checked against every OTHER caller of `PaperTradingEngine` (the real
  live pipeline included) before being made.
- **Test**: none — no fix was made to test.
- **Residual risk**: real, until decided. Recommend: do not run the dashboard's approve/reject
  workflow and a separate `paper-live` (no `--runtime-dir`) CLI session against the same account
  simultaneously until this is resolved.

### G10 — No Starlette exception handler on the dashboard

- **Severity**: Low
- **Component**: `dashboard/app.py`
- **Status**: OPEN — not fixed
- **Evidence**: a corrupted DB file (`DatabaseCorruptedError`) or any other uncaught exception in a
  route handler produces a raw 500/traceback rather than a clean error page.
- **Reproduction**: code inspection only (`app = Starlette(routes=[...])` registers no
  `exception_handlers`); not exercised against a real corrupted file in this pass.
- **Root cause**: never implemented.
- **Fix**: not made — a single generic handler risks masking genuinely-different failure classes
  under one message; deferred to a dedicated pass that can design the right granularity.
- **Residual risk**: low — this is a single-operator, local-only dashboard (per its own documented
  threat model); the failure mode is an ugly error page, not a safety or data-integrity issue.

### G11 — `/api/state`'s docstring claims a polling script that doesn't exist

- **Severity**: Low (documentation-only)
- **Component**: `dashboard/app.py`
- **Status**: OPEN — not fixed
- **Evidence**: the route's own docstring says a "small vanilla-JS snippet... polls it to update
  DOM nodes in place"; no `<script>`/`fetch`/`setInterval` exists anywhere in the file. The only
  real refresh mechanism is a 15s `<meta http-equiv="refresh">` full page reload.
- **Root cause**: stale documentation — the described behavior was apparently never implemented,
  or was removed without updating the docstring.
- **Fix**: not made — either implement the described polling or correct the docstring; left for a
  deliberate frontend decision, not touched under this pass's own scope.
- **Residual risk**: none functionally (the endpoint itself is safe, read-only, and correct) —
  purely a documentation-accuracy gap.

### G12 — `CandleBuilder` cross-thread reads have no lock (currently dormant)

- **Severity**: Low (not reachable in production today)
- **Component**: `live/dhan/candle_builder.py`, `live/dhan/market_data_source.py`
- **Status**: OPEN — not fixed, by design deferral
- **Evidence**: `last_known_price()`, `partial_candle()`, `rejected_tick_counts_by_symbol()` read
  `CandleBuilder` instance state with no synchronization, while `on_tick()` mutates the same state
  from the WebSocket receive thread. `CandleBuilder`'s own docstrings already anticipate this
  ("e.g. for a dashboard/monitoring poll"), but a repo-wide search found no current caller of any
  of these three methods outside tests.
- **Root cause**: forward-looking API surface, never wired up, never synchronized.
- **Fix**: not made — dormant/unreachable; would need a real caller and a real threading test to
  justify the added locking complexity now.
- **Residual risk**: none today. Flagged as a landmine for whoever eventually wires these into the
  dashboard.

### G13 — Second-order: a poisoned first tick can freeze `close` for a whole bucket

- **Severity**: Low (requires an already-anomalous upstream tick)
- **Component**: `live/dhan/candle_builder.py`
- **Status**: OPEN — disclosed, not further hardened
- **Evidence**: found by the second-order review of F1. If a bucket's first-arriving tick carries
  an anomalously large (but not rejected) timestamp, `close` freezes at that tick's value for the
  rest of the bucket instead of self-correcting on the next in-order tick (the pre-F1 behavior).
- **Root cause**: an interaction between F1's own chronological-ordering fix and an already-narrow
  external corruption class (a tick that passes existing timestamp-skew/plausibility gates but is
  still anomalous).
- **Fix**: not made — the trigger condition requires an upstream tick that already evaded existing
  safeguards; adding a third layer of ordering logic to handle this under time pressure risked
  introducing a further defect, per this mission's own "no speculative rewrites" instruction.
- **Residual risk**: low, narrow. Revisit if a real incident is ever traced to this pattern.

### G14 — `trades` table still lacks schema-level `UNIQUE(position_id)`

- **Severity**: Low (currently mitigated)
- **Component**: `paper/store.py`
- **Status**: OPEN — carried over from the earlier pass's D1 finding, still deferred
- **Evidence**: durability that a position closes at most once relies on application discipline
  (single call site + transactional atomicity), not a schema constraint.
- **Fix**: not made. Recommended: `try_create_unique_index(conn, "trades", ["position_id"], ...)`,
  mirroring the existing `predictions` migration.
- **Residual risk**: low — not exploitable via any known code path today.

### R3 — No purging/embargo in the backtest split logic

- **Severity**: Medium (methodology gap, not verdict-threatening for settled entries)
- **Component**: `backtesting/splits.py`, `backtesting/walk_forward.py`, `quant_research/market_behavior.py`
- **Status**: `RESEARCH_DECISION_REQUIRED`
- **Evidence**: forward-return labels (`close.shift(-h)`) are computed over the full continuous
  series BEFORE the dev/val/oos date-range filter is applied — a development-period row within `h`
  bars of the boundary has its label computed from prices inside the validation window.
- **Why not fixed**: changing split/label methodology is a research-methodology decision, out of
  scope for an infrastructure audit, and risks exactly the "reopen a rejected hypothesis" pattern
  this mission was told not to do.
- **Judgment (inference, not proof)**: most credible for already-thin splits (n<40); unlikely to
  flip a verdict for well-powered ones.
- **Recommended action**: a human decides whether to backport purging/embargo (an unused sibling
  module, `ml_research/walk_forward.py`, already implements it for a different research track) into
  the shared engine before any future hypothesis, or to disclose this exposure per-hypothesis.

### R4 — No dependence correction in confidence-interval machinery

- **Severity**: Medium (methodology gap, most relevant to one still-open question)
- **Component**: `learning/profitability.py`
- **Status**: `RESEARCH_DECISION_REQUIRED`
- **Evidence**: `_mean_confidence_interval()` uses a plain i.i.d. normal approximation — no
  block-bootstrap/HAC/clustering by date or symbol.
- **Judgment (inference)**: overstates precision (narrower-than-true CIs), most relevant to the one
  still-open H_MEANREV promotion question and to measurement-only conditioning hypotheses with
  persistent boolean conditions; unlikely to rescue any settled REJECTED verdict.
- **Recommended action**: a human decides whether to add a dependence-aware correction before the
  H_MEANREV chain is ever reconsidered for promotion.

### R5 — Multiple-testing family-size accounting is stale/incomplete

- **Severity**: Medium (bookkeeping, not verdict-threatening for settled entries)
- **Component**: `strategy/multiple_testing.py`, `audit/edge_feasibility/PHASE8_MULTIPLE_TESTING_AUDIT.md`
- **Status**: `RESEARCH_DECISION_REQUIRED`
- **Evidence**: registry grew 56→59 entries since Phase 8's own one-time manual analysis;
  `H_MEANREV_013` is counted in that analysis's family total but has no registry entry (reinforces
  finding R2 from `docs/FULL_SYSTEM_RED_TEAM_2026-09-22.md`); the 4 derivatives hypotheses are
  tracked in an entirely separate, never-reconciled family total. Honest count across the whole
  program: ~64 distinct tested hypotheses (59 registry + 1 unregistered + 4 derivatives), stated in
  no single document.
- **Recommended action**: a human decides whether to re-run Phase 8's accounting against the
  current, full 64-hypothesis count, and whether/how to reconcile `H_MEANREV_013`'s registry status
  (see R2).

### R6 — `H_MEANREV_001`'s own entry doesn't disclose its cost model

- **Severity**: Low (not verdict-threatening — a cheaper assumption on an already-rejected result)
- **Component**: `strategy/hypothesis_registry.py`
- **Status**: `RESEARCH_DECISION_REQUIRED` (documentation correction, not a rerun)
- **Evidence**: used the generic, non-NSE-specific default `CostModel()` (cheaper than every other
  hypothesis's `india_nse_intraday_2026()`), disclosed only retroactively in a later entry's aside.
- **Judgment (inference)**: real costs would only push this already-REJECTED result further
  negative — does not threaten the verdict.
- **Recommended action**: a human (or a documentation-only follow-up) adds an explicit cost-model
  disclosure to `H_MEANREV_001`'s own registry text.

---

## Summary counts

| Status | Count |
|---|---:|
| FIXED (with regression test) | 12 (F1–F6, G1–G6) |
| OPEN — deferred, real, low/medium residual risk | 6 (G9–G14) |
| `RESEARCH_DECISION_REQUIRED` | 4 (R3–R6, plus R1/R2 already tracked in the earlier report) |

No entry in this file is a critical or unresolved safety-invariant violation. G9 is the single
highest-severity open item and is architectural, not a quick patch.
