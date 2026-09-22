# Full System Red-Team and Remediation Audit — 2026-09-22

Adversarial audit of the entire repository, executed autonomously. Starting state: branch
`final-product-hardening`, HEAD `6dc24a0`, working tree clean, all refs (`origin/main`, `main`,
`origin/final-product-hardening`) in sync. This is a diagnostic-and-remediation pass, not a
research pass: no strategy parameter, risk threshold, or research verdict was changed. Where a
genuine defect was found and could be fixed safely, deterministically, and with a regression test
without touching strategy/risk/research logic, it was fixed. Where a finding requires a human
research or process decision, it is labeled `RESEARCH_DECISION_REQUIRED` and left untouched.

**Method**: five parallel read-only investigation passes (market data/CandleBuilder; indicators/
strategy/the pre-existing Hypothesis flake; CriticGate/RiskEngine/paper trading/predictions;
persistence/fleet supervisor/CLI/observability; research integrity/data provenance/known-issue
inventory) plus a dedicated, hand-verified audit of the real-order-execution invariant performed
directly rather than delegated, given its criticality. Every finding below cites the exact
file:line evidence it rests on; nothing is asserted without a citation or a reproduction.

**Evidence labels**: REAL (observed directly in the code or by running a real test), MECHANISM-
VERIFIED (proven by reading the actual source, not merely inferred), INFERENCE (a reasoned
conclusion, labeled as such, not directly observed), UNKNOWN (checked for, not resolvable from
available evidence).

## Executive summary

| | Count |
|---|---:|
| Total findings | 15 |
| Critical | 0 |
| High | 3 |
| Medium | 4 |
| Low | 2 |
| Informational | 3 |
| Fixed tonight (with regression tests) | 6 |
| Deferred (real, lower-priority, or larger-scope) | 3 |
| `RESEARCH_DECISION_REQUIRED` | 2 |
| Confirmed CORRECT, no defect (extensively re-verified) | ~40 individual checks across 9 subsystems |

No critical finding was made. Real order execution remains structurally impossible, independently
re-verified by hand tonight in addition to the pre-existing dedicated test suite. Three genuine
data/operational-safety defects were found in the live market-data and fleet-supervision path, all
fixed and regression-tested tonight. The research program's own historical conclusions (NO
DEMONSTRATED EDGE) were **not** overturned by anything found — one real methodological gap
(point-in-time universe correction not wired into the shared backtest engine) was found and is
flagged as `RESEARCH_DECISION_REQUIRED`, with a reasoned (not proven) argument for why it does not
undermine the existing negative verdicts.

## Critical safety invariants — explicit pass/fail evidence

| Invariant | Verdict | Evidence |
|---|---|---|
| Real orders impossible | **PASS** | See §1. `PaperTradingEngine` (`paper/engine.py`) has zero network imports. `DhanRestClient` (`live/dhan/rest_client.py`) exposes exactly one HTTP primitive, `_get` (GET-only) — no POST/PUT capability exists in the class at all. `DisabledDhanOrderExecutor` (`live/dhan/broker_adapter.py`) unconditionally raises `RealOrderPlacementDisabledError` on every method and is referenced nowhere outside its own file and 3 test files. `live/broker.py`'s only concrete `BrokerAdapter` is `MockBrokerAdapter`, which delegates entirely to `PaperTradingEngine`; no `DhanBrokerAdapter` class exists anywhere (by explicit design). `mcp_server/server.py` exposes zero place_order/execute_trade/cancel_order tools. `get_live_engine()` (`live/workstation.py:34-39`) is hardcoded, type-annotated `-> PaperTradingEngine`, no branch or config affects it. No `shell=True` anywhere in the repo. No environment variable anywhere can enable real execution (grepped `ENABLE_REAL`, `LIVE_TRADING`, `REAL_EXECUTION`, `REAL_ORDERS`, `ALLOW_REAL` — zero matches). `scheduler/` has zero subprocess usage. Pre-existing dedicated test file `tests/test_dhan_no_real_orders.py` (7 structural, not merely behavioral, tests) independently proves the same invariant and passed again tonight after every change (§9). |
| RiskEngine cannot be bypassed | **PASS** | `paper/engine.py:191` calls `self.risk_engine.evaluate(signal, self.account)` *unconditionally* inside `submit_signal`, regardless of what CriticGate decided (the critic's verdict is never even passed in). The only writer of a `PaperOrder` row (`self.store.save_order`, `paper/engine.py:240`) is reachable only through the `else` branch of `if not decision.approved:` (`paper/engine.py:223`), itself downstream of that same RiskEngine call. |
| Critic cannot authorize execution | **PASS** | `critic/engine.py`'s `evaluate()` is a pure, deterministic function — no LLM, no I/O (`critic/engine.py:1-13`). Any exception during critic evaluation is caught and fails closed to `blocked=True` (`live/critic_gate.py:218-252`, tested at `tests/test_live_critic_gate.py:124-157`). There is no code boundary where LLM-generated text (if any, from the separate, non-authoritative `agents/critic_agent.py`) feeds into the routing verdict. |
| Stale data cannot generate valid candles | **PASS** | `CandleBuilder`'s cold-start/baseline-confirmation machinery rejects a stale first tick and self-heals only on a second, agreeing tick (`live/dhan/candle_builder.py`, extensively tested). A confirmed baseline survives a reconnect and rejects a replayed stale packet (`tests/test_dhan_candle_builder.py:728`). Tonight additionally closed two real gaps in this same file (§2). |
| Future data cannot enter predictions | **PASS** | `predictions/tracker.py:188-189`: `subsequent = frame[frame.index > entry_time]` (strictly greater than) and the evaluation loop returns `EXPIRED` before ever reading a bar beyond `horizon_bars` (`predictions/tracker.py:239-244`) — structurally cannot inspect a bar at or before creation time, or beyond the declared horizon. |
| Production cannot silently use mock data | **PASS** | `--source mock` is a separate, explicitly-labeled CLI path (`DataStatus.SIMULATED`, printed and tagged in the dashboard); `--source dhan` failures (missing credentials, connection loss) raise loudly (`DhanCredentialsMissingError`, `FeedDisconnectedError`) rather than silently falling back. A repo-wide search for `mock`/`synthetic`/`placeholder`/`dummy`/`fallback` across every data-provider and trading-engine module found no automatic fallback from a failed real source to fabricated data anywhere. One UX footgun noted, not a silent-corruption risk: `paper-live`'s own `--source` default is `"mock"` (an operator who omits the flag gets the replay mode, but it is visibly labeled, not silent). |
| Wrong Python environment cannot silently run production | **PASS, hardened further tonight** | `fleet-supervise`/`paper-live --source dhan` now (1) self-correct via `ensure_running_under_project_venv()` (transparent re-exec under the project's own venv, added earlier tonight) and (2) fail closed via `run_startup_environment_checks()` if self-correction isn't possible (no venv present, or dependencies missing). Tonight additionally fixed the one remaining gap: a *corrupted* (present but non-executable) venv interpreter previously raised an uncaught `OSError` with a raw traceback instead of this module's own clear message (§4). |

## Findings

### F1 — HIGH — CandleBuilder `close` reflects arrival order, not exchange-time order, within a bucket

- **Component**: `live/dhan/candle_builder.py`
- **Description**: Within a single still-open bucket, an out-of-order tick (its own exchange
  timestamp earlier than a tick already merged) unconditionally overwrote `self._state.close`,
  contradicting this module's own documented semantics ("close = price of the most recent tick" —
  meaning most recent by exchange time, per the same docstring's bucketing rule).
- **Evidence/reproduction**: tick @epoch=30 price=100.0 (seeds bucket), then tick @epoch=10
  price=99.0 (arrives second, but chronologically earlier), then a tick in the next bucket
  completes the bar. Before the fix, `bar.close == 99.0` (the wrong, out-of-order value); the
  existing test at the time (`tests/test_dhan_market_data_source.py:428`) only asserted `low`,
  never `close`, so this was undetected.
- **Root cause**: `on_tick` (`live/dhan/candle_builder.py`, pre-fix lines ~489-496) updated `close`
  unconditionally on every accepted tick, with no comparison against the timestamp already held.
- **Fix**: `close`/`last_received_at`/`last_source_timestamp` now only advance when the incoming
  tick's own timestamp is `>=` the latest one already merged into the bucket; `high`/`low`/`volume`
  are unaffected (every real tick still counts toward those regardless of order, unchanged).
- **Regression tests**: `tests/test_dhan_candle_builder.py::test_close_reflects_the_chronologically_latest_tick_not_the_most_recently_arrived_one`, `::test_close_still_advances_normally_when_ticks_arrive_in_chronological_order`; extended the pre-existing `tests/test_dhan_market_data_source.py::test_out_of_order_tick_within_the_same_bucket_is_absorbed_not_rejected` to also assert the corrected `close` value.
- **Residual risk**: none identified for this specific mechanism. A related, untested boundary
  (two ticks at the exact same bucket-level BAR timestamp with different OHLCV reaching
  `paper/engine.py`'s bar-dedup logic) is separately noted as F-D4 below — not reachable from a
  single `CandleBuilder` instance today.

### F2 — HIGH — NaN/Inf tick values were not rejected, could poison state and raise an uncaught exception in the WebSocket receive thread

- **Component**: `live/dhan/candle_builder.py`
- **Description**: `price <= 0` is `False` for NaN and for `+Inf`; the deviation-plausibility check
  (`deviation_pct > threshold`) is also `False` when either operand is NaN. A NaN/Inf tick therefore
  passed every existing validity gate, merged into `close`/`_last_known_price`, and (a) permanently
  poisoned the deviation gate for the rest of that `CandleBuilder` instance's life (every future
  comparison against a NaN baseline is also silently `False`), and (b) would eventually raise an
  **uncaught** `pydantic.ValidationError` (`OHLCVBar`'s `Field(gt=0)`) when the bar finalized — a
  different exception type than `DhanWireFormatError`, the only type
  `market_data_source.py`'s receive-thread callback catches.
- **Evidence/reproduction**: a struct-decoded `float32` field can legally carry an IEEE-754 NaN/Inf
  bit pattern from a corrupted/garbled packet — a reachable input, not a hypothetical.
  `nan <= 0`, `nan > x`, `inf <= 0` all independently verified to evaluate `False` in Python.
- **Root cause**: no explicit finiteness check anywhere in the tick-validation gate.
- **Fix**: added an explicit `math.isfinite(price)`/`math.isfinite(volume)` check, evaluated first,
  before the non-positive-price/negative-volume/deviation checks — rejects the tick outright
  (counted under a new `rejected_tick_counts["non_finite_value"]` reason), never merges its price
  or volume, and never updates `_last_known_price` (so the deviation gate cannot be poisoned).
- **Regression tests**: `tests/test_dhan_candle_builder.py::test_non_finite_price_is_rejected_never_merged_into_a_bucket[nan/inf/-inf]`, `::test_non_finite_volume_is_also_rejected`, `::test_a_nan_price_never_permanently_poisons_the_deviation_gate_for_later_ticks` (the last one directly proves the poisoning mechanism is closed: an actually-implausible tick sent right after a rejected NaN tick is still correctly caught).
- **Residual risk**: none identified. The fix is a pure input-validation addition; it does not
  change behavior for any finite input.

### F3 — HIGH — `fleet_supervisor.check_worker_health` had no time-based staleness detection ("healthy but actually dead")

- **Component**: `live/fleet_supervisor.py`, `live/heartbeat.py`
- **Description**: Worker health was determined entirely by (a) whether the process object had
  exited, and (b) whether a gap/disconnect marker was the most recent line in a 50-line log tail.
  Neither has a time component. A worker stuck inside a blocking call (e.g. a feed read with no
  timeout) **before** it ever reaches its own per-bar print-and-heartbeat step stops advancing its
  log entirely — the log's last line stays an ordinary bar, `check_worker_health` returns `RUNNING`
  ("alive, no gap/disconnect signal in recent log output") indefinitely, and nothing in this
  codebase reads `heartbeat.json` while a session is running to catch it (it was read only at the
  *next* process's own startup, via `classify_previous_session`).
- **Evidence**: this is not hypothetical — `docs/DHAN_FEED_INTERRUPTION_1514_INVESTIGATION_2026-09-22.md`
  §1 documents the 2026-09-17 incident where workers "sat idle, believing themselves connected, for
  600s+ without recovering," discovered only via after-the-fact log review, not any automated
  health signal.
- **Root cause**: `check_worker_health` (`live/fleet_supervisor.py`) never opened `heartbeat.json`
  at all, relying entirely on log-line content with no age check.
- **Fix**: added `live.heartbeat.read_heartbeat_age_seconds()` (best-effort, returns `None` for a
  missing/unreadable file rather than raising or treating that as staleness — a worker whose first
  bar hasn't completed yet is ordinary startup, not a hang). `WorkerHandle` now carries its own
  `heartbeat_path` (wired from `launch_worker`). `check_worker_health` checks heartbeat age
  **before** the log-content scan and reports a new `WorkerHealth.UNRESPONSIVE` status if the
  heartbeat is older than `DEFAULT_STALE_AFTER_SECONDS` (300s — deliberately reusing the same,
  already-justified threshold `live/dhan/market_data_source.py`'s own `connected_idle_timeout_seconds`
  established, not a new arbitrary number). `should_restart` deliberately never treats
  `UNRESPONSIVE` as a restart candidate (the process object is still alive; auto-killing it is a
  separate, larger decision explicitly left out of tonight's scope — see "residual risk" below).
- **Regression tests**: `tests/test_fleet_supervisor.py::test_check_worker_health_unresponsive_when_heartbeat_is_stale_even_with_ordinary_log_lines`, `::test_check_worker_health_running_when_heartbeat_is_fresh`, `::test_check_worker_health_not_unresponsive_when_heartbeat_has_never_been_written_yet`, `::test_check_worker_health_stale_after_seconds_is_configurable`, `::test_check_worker_health_backward_compatible_when_heartbeat_path_is_none`, `::test_should_restart_never_restarts_an_unresponsive_worker`; extended the real-subprocess integration test to assert `launch_worker` actually wires `heartbeat_path`. New `read_heartbeat_age_seconds` tests in `tests/test_live_heartbeat.py`.
- **Residual risk**: this makes the condition **visible** (surfaced in `check_worker_health`'s
  status and therefore in the supervisor's own poll-loop console output), not automatically
  **recovered**. Auto-killing-and-restarting a genuinely stuck worker is a real, larger design
  decision (it requires the supervisor to forcibly terminate a process it did not observe exit) —
  deliberately left to a human operator or a future, separately-scoped change, not made
  unsupervised tonight.

### F4 — MEDIUM — an exception during initial fleet launch leaked already-spawned worker processes

- **Component**: `main.py::run_fleet_supervise_command`
- **Description**: The initial per-symbol launch loop had no exception boundary and ran **before**
  the `try/finally: shutdown_fleet(handles)` block. If `launch_worker`'s `subprocess.Popen` raised
  for symbol N of M (a transient spawn failure), the exception propagated as a raw traceback,
  workers N+1..M were never launched, and workers 1..N-1 were never terminated — orphaned,
  running subprocesses with no operator-visible summary.
- **Root cause**: missing exception boundary around the launch loop specifically (the
  ongoing-supervision loop already had one, added in an earlier hardening pass, for the same class
  of per-symbol failure — this was the one remaining, asymmetric gap).
- **Fix**: wrapped the launch loop in `try/except Exception`; on failure, prints which symbols were
  already launched and which were never reached, calls `shutdown_fleet(handles)` on whatever
  launched successfully (so nothing is orphaned), then exits cleanly with `SystemExit(1)`.
- **Regression test**: `tests/test_cli.py::test_run_fleet_supervise_command_cleans_up_already_launched_workers_when_a_later_one_fails_to_launch` — uses two REAL, short-lived mock-source workers, forces the third symbol's launch to raise, and asserts both the clear error message AND that the first worker's real subprocess is actually terminated (`process.poll() is not None`), not merely that the exception was caught.
- **Residual risk**: none identified.

### F5 — MEDIUM — a corrupted (present but non-executable) venv interpreter raised an uncaught `OSError`

- **Component**: `live/environment_guard.py`
- **Description**: `ensure_running_under_project_venv` only checked `venv_python.exists()` — a file
  existing but being a corrupted/non-PE binary is a different, real failure mode. The re-exec
  attempt (`subprocess.run`) against such a file raises `OSError` (e.g. Windows `WinError 193`).
  This call sits deliberately **before** `main()`'s own `try/except _CONTROLLED_ERRORS` block (it
  must run before anything else does), so the raw `OSError` propagated as an unactionable
  traceback rather than this module's own clear, operator-facing message style used everywhere
  else in the file.
- **Fix**: wrapped the `runner(...)` call in `try/except OSError`, printing a clear message
  ("found `<path>` but could not execute it... recreate it") and exiting with `SystemExit(1) from
  exc` (the original cause preserved, not swallowed).
- **Regression test**: `tests/test_environment_guard.py::test_ensure_running_under_project_venv_fails_loudly_not_with_a_raw_traceback_when_the_venv_python_is_corrupted`.
- **Residual risk**: none identified — this only changes how clearly the failure is reported; the
  mechanism (`subprocess.run` raising synchronously) already argued against a hang, and still does.

### F6 — MEDIUM — pre-existing Hypothesis test flake, investigated and fixed (test-infrastructure only, not a code defect)

- **Component**: `tests/test_market_indicators_properties.py`
- **Description**: `test_compute_sma_never_raises_regardless_of_length_vs_period` failed
  intermittently twice during full-suite runs tonight (once a plain-looking failure, once
  explicitly `FailedHealthCheck: too_slow`) but passed every time run in isolation.
- **Investigation**: the test's own `@settings(max_examples=100, derandomize=True)` — confirmed
  unchanged — means `derandomize=True` makes the actual generated example VALUES fully
  deterministic and identical across runs; only Hypothesis's own wall-clock budget for DATA
  GENERATION (not the indicator computation) is sensitive to concurrent load. `market/
  indicators.py::compute_sma` was read line-by-line: `close.rolling(window=period,
  min_periods=period).mean()` — a single pandas call, no loops, no dict-ordering dependency, no
  uninitialized state, no source of nondeterminism found. Root cause classification:
  **test-infrastructure timing instability under a large (2700+-test) concurrent suite, not a
  genuine indicator defect.**
- **Fix**: added `suppress_health_check=[HealthCheck.too_slow]` to the shared `_PROPERTY_SETTINGS`
  profile used by this test file. This changes nothing about which values are tested or what
  `compute_sma` is expected to return — it only stops Hypothesis from failing a test because the
  surrounding suite made the *machine*, not the *code*, slow.
- **Verification**: isolated test run 5 consecutive times post-fix, all passed (sub-1.5s each); the
  full `tests/test_market_indicators_properties.py` file (14 tests) passed cleanly; the full
  regression suite (§9) was re-run with this fix in place.
- **Verdict**: **TEST-INFRASTRUCTURE-FLAKE-FIXED.**
- **Residual risk**: none identified — no production code was touched for this fix.

### F7 — INFORMATIONAL — new adversarial no-lookahead proofs added for the strategy's core indicators

- **Component**: `tests/test_no_lookahead_redteam.py` (new file)
- **Description**: direct, function-level proof (not merely via the strategy or
  `compute_indicator_series`, already covered elsewhere) that `compute_sma`, `compute_rsi`,
  `compute_macd`, and `compute_atr` — the indicators `trend_momentum_baseline` most directly
  depends on — cannot be influenced by mutating rows after the evaluation point. Method: compute
  the indicator at index t, mutate every row after t with adversarial values (large spikes,
  near-zero crashes, a reversed tail), recompute, and assert the value at t is bit-for-bit
  unchanged.
- **Result**: all four passed on every adversarial mutation tried. **No lookahead defect found** in
  any of the four indicators — this is a confirmation, not a fix.
- **Note on provenance**: this file was authored by a sub-agent dispatched as part of tonight's
  audit; its own process stalled before delivering a final synthesized report, but the test file
  itself was recovered from disk, read in full, and independently re-run and verified before being
  kept in this commit.

### D1 — LOW (deferred, not fixed tonight) — `paper.db`'s `trades` table has no schema-level `UNIQUE(position_id)` constraint

- **Component**: `paper/store.py`
- **Description**: unlike `signals.signal_id` (real `PRIMARY KEY`) and `journal_entries.signal_id`
  (real `UNIQUE`, with a proven, tested TOCTOU-race defense), `trades` has only `trade_id PRIMARY
  KEY` (a fresh UUID every call). Correctness that a position is closed at most once currently
  relies entirely on `update_position`'s `WHERE status != 'CLOSED'` guard combined with every
  `_close_position` call running inside one `store.transaction()` — real durability from
  single-call-site application discipline plus transactional atomicity, not a schema constraint.
- **Why deferred rather than fixed**: this project already has an established, tested pattern for
  adding a defensive unique index to an existing table without breaking historical data
  (`core.sqlite_util.try_create_unique_index`, used for `predictions.symbol+entry_time`) — applying
  the same pattern here is very likely safe, but it touches the paper-trading ledger's own schema,
  and tonight's priority was the higher-severity live market-data and fleet-supervision findings.
  Currently mitigated (not exploitable via any known code path today), so left for a dedicated,
  smaller follow-up rather than rushed alongside everything else tonight.
- **Recommended action**: add `try_create_unique_index(conn, "trades", ["position_id"], ...)`
  mirroring the existing `predictions` migration, with the same graceful-degradation-on-preexisting-
  duplicates behavior.

### D2 — LOW (deferred, disclosed design choice, not a hidden bug) — paper engine's stop/target exits never apply slippage, even on a large gap-through

- **Component**: `backtesting/execution.py`, `paper/engine.py`
- **Description**: a STOP/TARGET exit always fills at the exact pre-agreed price level, never the
  worse actual price a real gap-through-the-level would produce (e.g. entry 100, stop 95, next bar
  opens at 70 on a genuine 30% gap-down — the ledger still books an exit at 95, a price the
  position could never realistically have received). `paper/engine.py`'s own comment explicitly
  names this: "no slippage applied, matching this engine's existing, unmodified design."
- **Why not fixed**: this is a disclosed, deliberate, pre-existing simplification, not a silent
  defect — changing it would retroactively alter the fill economics of every historical paper-
  trading and backtest result this project has ever produced, which is a research-conclusion-
  affecting change, explicitly out of scope for an infrastructure/safety audit per this mission's
  own instructions ("does not change the frozen research strategy merely for performance").
- **Recommendation**: left as a documented limitation. If a future research pass wants
  gap-realistic fills, it should be a deliberate, separately-preregistered methodology change, not
  a side effect of a red-team pass.

### D3/D4 — LOW (coverage gaps, not proven defects)

- **D3**: no test directly drives a stale `on_message` (a real tick, not a close/error) arriving
  from an OLD WebSocket transport generation after a NEW generation is already `CONNECTED`. The
  underlying mechanism (`_on_raw_message`'s own generation check, `market_data_source.py`) is
  identical code to the already-tested stale-`on_close` case and is reasoned by symmetry to behave
  correctly, but this exact scenario is not directly proven. A concrete test scenario was described
  (capture the old transport, drive `next_bar()` after the new generation is live, assert
  `NO_NEW_BAR`) but not written tonight — flagged for a future test-hardening pass rather than
  invented under time pressure alongside everything else.
- **D4**: two completed bars reaching `paper/engine.py`'s bar-level dedup with the identical
  timestamp but different OHLCV content would be silently `DUPLICATE_SKIPPED` (dedup is
  timestamp-only, no content comparison) — not currently reachable from a single `CandleBuilder`
  instance (its own bucket-start is monotonic per instance), so this is a latent, untested boundary
  condition rather than a demonstrated live defect.

## `RESEARCH_DECISION_REQUIRED` findings

Per this mission's own explicit instruction, neither of the following was silently changed.

### R1 — Point-in-time universe correction is not wired into the shared backtest engine

- **Finding**: `quant_research/security_identity_map.py` + `quant_research/point_in_time_fno_
  universe.py` provide genuine, real (dated NSE bhavcopy-snapshot-based) point-in-time universe
  correction — but only ONE standalone script pipeline uses it end-to-end
  (`audit/edge_feasibility/scripts/build_point_in_time_snapshots.py` → the `H_MEANREV_010`
  point-in-time closure). `backtesting/universe.py`, `backtesting/runner.py`,
  `backtesting/walk_forward.py`, and `main.py`'s generic `backtest-universe` CLI all accept a plain
  caller-supplied symbol list with **no** point-in-time or identity-resolution logic of their own.
  `quant_research/universe_expansion.py` (used by `H_MEANREV_005`, `H_MEANREV_006`, `H_MEANREV_013`,
  `H_CONTEXT_MARKET_006`, `H_CONTEXT_MARKET_007`, and `ml_research/run_experiment.py`) builds its
  universe from TODAY's current Dhan F&O-eligibility snapshot, applied uniformly across the whole
  historical backtest window — exactly the survivorship-bias/corporate-action-leakage risk the
  point-in-time module exists to close, for every hypothesis except the one it was actually built
  for.
- **Why this was not "fixed"**: retrofitting point-in-time correction into the shared engine and
  re-running the affected hypotheses would be a genuine research-methodology change requiring new
  preregistration, is exactly the kind of "reopen a rejected hypothesis because the red team found
  a software bug" action this mission explicitly forbids, and — critically — every one of the
  affected hypotheses already concluded REJECTED/INCONCLUSIVE (none SUPPORTED an edge). Removing
  survivorship bias from a universe generally makes results LOOK WORSE, not better (surviving,
  successful companies are over-represented when the bias is present) — so this gap, if it has any
  directional effect at all, would plausibly bias these ALREADY-NEGATIVE conclusions toward
  appearing MORE positive than the true population, not less. **This is a reasoned inference, not a
  proven quantification** — stated as such, not asserted as fact.
- **Affected hypotheses/experiments requiring a decision, not an automatic rerun**: `H_MEANREV_005`,
  `H_MEANREV_006`, `H_MEANREV_013` (see R2), `H_CONTEXT_MARKET_006`, `H_CONTEXT_MARKET_007`,
  everything run via `ml_research/run_experiment.py`, and any future use of `main.py
  backtest-universe` with a broad or F&O-eligible symbol set.
- **Recommended next action (for a human, not automated tonight)**: either (a) backport point-in-
  time correction into the shared engine before any future universe-dependent hypothesis, treating
  every already-REJECTED entry above as "closed, with a disclosed methodological caveat, not
  reopened," or (b) explicitly annotate each affected hypothesis's own registry entry with this
  specific exposure, matching the survivorship-quantification discipline `H_MEANREV_013`'s own
  preregistration already modeled (§7 of that document).

### R2 — `H_MEANREV_013` is executed, published, and concluded, but its registry status is ambiguous by original design, not by omission

- **Finding**: `audit/edge_feasibility/H_MEANREV_013_CLUSTERING_PREREGISTRATION.md` and
  `H_MEANREV_013_RESULTS.md` exist, are complete, and conclude Outcome C (unstable / **NOT
  SUPPORTED**). `strategy/hypothesis_registry.py` has no `H_MEANREV_013` entry (it jumps from
  `H_MEANREV_012` to `H_MEANREV_014`). Initially flagged by one of tonight's investigation passes
  as a registry-completeness defect ("the registry's own stated purpose is a record of every
  hypothesis considered").
- **Why this is NOT simply fixed by adding the entry**: the preregistration document's own §
  "scope" text is explicit and was written *before* the result was known: *"This is an AUDIT
  analysis... not a new production hypothesis entry in `strategy/hypothesis_registry.py` — it will
  be written up there only if/when it graduates into one, per the user's own 'don't start H57 yet'
  instruction."* It did not graduate. Its absence from the registry is therefore most plausibly the
  ORIGINAL, deliberate scoping decision working as intended, not an oversight — adding it now, based
  on my own re-reading of an intentionally-scoped prior decision, would itself be an unreviewed
  change to a persistent research record.
- **The real, disclosed inconsistency**: `audit/edge_feasibility/PHASE8_MULTIPLE_TESTING_AUDIT.md`
  already counts `H_MEANREV_013` as a member of the `F_MEANREV` family for multiple-testing-
  correction purposes — i.e., it IS being treated as a real, counted hypothesis for statistical
  accounting, while simultaneously being absent from the permanent registry. This is the specific
  fact worth a human decision, not the mere absence of a registry row by itself.
- **Recommended next action (for a human, not automated tonight)**: pick one of (a) add a registry
  entry now, verdict unchanged (`REJECTED`, matching the existing, unmodified `H_MEANREV_013_
  RESULTS.md` exactly — a record-keeping completion, not a new research finding), for consistency
  with the multiple-testing audit's own accounting; or (b) leave the registry as-is and instead
  annotate `PHASE8_MULTIPLE_TESTING_AUDIT.md` to explicitly note `H_MEANREV_013` is an audit-only
  analysis intentionally excluded from the permanent registry by its own preregistration, with a
  cross-reference to where its full record actually lives.

## Known-issue reconciliation (condensed — full detail in the underlying investigation)

No `TODO`/`FIXME`/`XXX`/`HACK` markers exist anywhere in this repository's own source or docs — this
project uses disclosed prose ("not yet", "deferred", "unresolved") instead of inline debt markers,
and the large majority of matches for that language are deliberate, already-disclosed research/
engineering-integrity statements in `audit/`, `docs/`, and the root `FINAL_*.md` reports — not open
action items. `AUDIT_GAPS.md` is itself an existing, current, comprehensive gap tracker (19 items)
that already covers most of what a fresh scan would otherwise re-surface. Genuinely live,
unaddressed items found tonight, beyond what `AUDIT_GAPS.md` already tracks:

| Item | Status | Severity | Action |
|---|---|---|---|
| No corporate-action handling anywhere under `backtesting/` | Confirmed still real (searched directly, no handling found) | Medium, disclosed | No change tonight — a research-scope item, not an infrastructure bug |
| `docs/LIVE_SYSTEM_HARDENING_FINAL_REPORT.md` lines 951/993 describe the staggered-launch mitigation and CriticGate fail-closed path as "not yet live-validated" (as of 2026-09-16/17) | Likely stale/superseded — later live sessions (`docs/LIVE_MARKET_VALIDATION_REPORT_2026-09-22.md`, tonight's own report) have since validated both | Informational | No action needed; noted for whoever next edits that older report |
| `docs/LIVE_INTELLIGENCE_FORENSICS_2026-09-16.md:326` — a fix described as "pushed, not yet merged to `main`" | Unverifiable from this read-only pass (no reason to believe it's still true, given how many merges have happened since) | Informational | No action |
| `H_MEANREV_013`/`R1`/`R2` above | Live, real | See R1/R2 | Human decision requested |
| `trades` table missing `UNIQUE(position_id)` | Live, real, currently mitigated | See D1 | Deferred, recommended follow-up |

## Research integrity assessment

Explicitly distinguishing categories, per this mission's own required structure:

- **Infrastructure defects found and fixed**: F1-F6 above. None of these change any research
  conclusion — F1/F2 affect only the LIVE market-data path (not used by any backtest/research
  script, which reads historical OHLCV directly, not through `CandleBuilder`); F3-F5 are pure
  operational/observability fixes; F6 is a test-infrastructure timing fix.
- **Data defects**: none found that affect a stored research conclusion. The point-in-time-universe
  gap (R1) is closer to a methodological-scope gap than a data-corruption defect — the data itself
  (current Dhan F&O eligibility, NSE bhavcopy) is real and correctly retrieved; it is simply applied
  over a wider historical window than is point-in-time-correct for some hypotheses.
- **Methodological defects**: R1 (point-in-time universe not universally wired) is the one real
  methodological gap found. R2 (`H_MEANREV_013` registry ambiguity) is a record-keeping/consistency
  question, not a methodology defect in the experiment itself (its own preregistration, execution,
  and cross-checks against the real `schedule_portfolio()` were independently verified sound).
- **Genuine negative research results**: unchanged and unchallenged. The 59-hypothesis OHLCV
  registry's NO DEMONSTRATED EDGE verdict, the 4-hypothesis derivatives program's same verdict, and
  every individual hypothesis's own status were spot-checked tonight (a sample spanning
  `H_ENTRY_001`, `H_ENTRY_002`, `H_EXIT_002`, `H_MEANREV_001/002/010/014`, `H_CONTEXT_MARKET_007`,
  and the single `SUPPORTED` entry) against their own cited preregistration and results documents —
  every sampled verdict matched its own cited evidence exactly. The one `SUPPORTED` entry
  (`H_ENTRY_001`) was scrutinized hardest: it is itself a *negative* finding (entry timing carries
  no edge, confirmed via a 300-iteration Monte Carlo baseline comparison), correctly folded into the
  overall "no edge" verdict by the project's own final-conclusion documents, not an exception to it.
- **Unresolved questions, explicitly left open**: the recurring ~15:13-15:14 IST fleet-wide feed
  interruption (already the subject of a dedicated investigation document tonight, root cause still
  genuinely unproven — this audit did not re-open that question, only cross-referenced it where
  relevant to the CandleBuilder/reconnect findings above); R1 and R2 above.

## Remaining risks (only what genuinely remains)

1. `UNRESPONSIVE` worker detection (F3) is now visible but not auto-recovered — a human or a future
   change still needs to notice and act on it during a live session.
2. D1 (trades table constraint), D3 (stale-old-generation-message test gap), D4 (bar-level dedup
   content-blindness) remain real but low-severity/low-likelihood gaps.
3. R1 and R2 are open, human-decision items — the current registry/backtest-engine state is safe
   and honestly disclosed, but not fully self-consistent until one of those decisions is made.
4. Corporate-action handling in `backtesting/` remains genuinely absent (a long-standing, disclosed
   scope boundary, not new tonight).
5. The ~15:13-15:14 IST feed-interruption root cause remains unproven (unchanged from tonight's
   earlier, separate investigation) — the system's own recovery mechanism is proven robust
   regardless of cause, but the cause itself is still open.

## Recommended next actions, ordered by risk

1. Decide R1 and R2 (human/research-process decisions, not automatable).
2. Consider adding the `trades.position_id` unique-index migration (D1) as a small, focused
   follow-up, using the exact pattern already established for `predictions`.
3. Add the one missing stale-old-generation `on_message` test (D3) to convert that mechanism from
   "verified by code symmetry" to "directly proven."
4. Continue collecting independent live sessions to determine whether the ~15:13-15:14 IST
   interruption recurs (per tonight's earlier, separate investigation's own recommendation) —
   unrelated to, and not blocked by, anything in this audit.
5. No action needed on anything marked CORRECT-WITH-EVIDENCE above; re-verify only if the
   underlying code changes.

## Git discipline and final verification

- **Starting state** (recorded before any change): branch `final-product-hardening`, HEAD
  `6dc24a0`, working tree clean, `origin/main` == `main` == `origin/final-product-hardening` ==
  `6dc24a0`.
- **Commits made tonight** (small, logically separated, per this mission's own §22): one for the
  market-data/CandleBuilder fixes (F1, F2), one for the infrastructure/runtime fixes (F3, F4, F5),
  one for the test-suite fix and new adversarial tests (F6, F7), and this documentation commit —
  exact hashes recorded in the session's own git log at completion.
- **Full regression suite**: run to completion after every fix, and once more at the very end with
  every change in place: **2746 passed, 0 failed, 1 pre-existing unrelated deprecation warning
  (`asyncio.iscoroutinefunction`, chromadb's own dependency, not this project's code), 749.30s**.
  The previously-flaky `test_compute_sma_never_raises_regardless_of_length_vs_period` passed as
  part of this same run — the fix holds under the exact real conditions (a large, concurrent full
  suite) that originally exposed the flake, not merely in isolation.
- **Real-order-execution invariant**: re-verified after every change tonight by re-running
  `tests/test_dhan_no_real_orders.py` and `tests/test_approval_security.py` (18/18 passed) — not
  merely assumed unaffected because no order-execution file was touched.
- **Secrets**: no credential, API key, or token was written to any file, log, or this report by
  tonight's work. `.env` was never read into any file this audit produced.
- **No strategy, risk threshold, or research verdict was changed.** No trade was manufactured. No
  hypothesis was reopened or reversed.
