# Open-Issues Remediation — Final Report (2026-09-23)

This is the final report for the 2026-09-23 remediation pass: a follow-on mission whose explicit
job was to resolve the remaining actionable issues left open by the 2026-09-22 continuous
red-team pass (`docs/CONTINUOUS_FULL_SYSTEM_RED_TEAM_FINAL_2026-09-22.md`,
`docs/MASTER_KNOWN_ISSUES.md`), then independently re-audit the fixes. Priority order followed the
mission's own list: (1) the dashboard dual-writer risk, (2) remaining operational/code-quality
issues, (3) documentation, (4) database/schema hardening, (5) cross-thread/concurrency issues,
(6) research-methodology classification, (7) a fresh second-order/final red-team pass, (8) full
regression and final verification.

**Evidence labels used throughout**: PROVEN (a passing, real test demonstrates the claim), TESTED
(exercised directly), INFERRED (a reasoned conclusion, explicitly labeled), CLASSIFIED (a research
finding investigated to a specific, evidenced conclusion), UNRESOLVED (a real, open question).

## 1. Executive summary

Starting baseline: branch `final-product-hardening`, HEAD `a4cfaa4`, clean tree, all refs synced,
Python 3.14.4, Windows 11 Pro, 2765 tests collected, `docs/MASTER_KNOWN_ISSUES.md` showing 12 FIXED
(F1-F6, G1-G6), 6 OPEN (G9-G14, G9 the single highest-severity item), 6 `RESEARCH_DECISION_REQUIRED`
(R1-R6).

**Resolved this pass**: G9 (the headline finding — dashboard/CLI dual-writer risk, real
architectural fix with concurrency tests), G10, G11, G12, G14 (all FIXED with regression tests).
G13 was re-investigated and confirmed to genuinely have no safe cheap fix — left open, disclosed.
All four research-methodology questions (R3-R6) were investigated and classified: R3 and R4
CLASSIFIED — NO EFFECT (no hypothesis verdict threatened), R5 CLASSIFIED — MINOR DISCLOSURE ISSUE
(a registry accounting table was added to reconcile the true 64-hypothesis count), R6 FIXED
(a documentation-only cost-model disclosure added to `H_MEANREV_001`'s own registry entry, no
number or verdict changed). R1/R2 were carried over from the earlier pass, not re-investigated,
and remain `RESEARCH_DECISION_REQUIRED`.

**New findings from the fresh final red-team pass (Part 19)**: a second, independent instance of
the G9 defect class in `mcp_server/server.py`'s own separate `_paper_engine` singleton (fixed, same
mechanism); a real YAML schema bug in `tests/failure_injection/failure_matrix.yaml` — a duplicate
`note:` key silently overwrote the evidence text for the `FI-ENV-GUARD-CORRUPTED-VENV-INTERPRETER`
row with an unrelated note from an earlier entry (fixed — the orphaned duplicate removed); a stale
"Read-only" claim about the dashboard in `ARCHITECTURE.md`'s own component table (the dashboard has
4 mutating POST routes — fixed).

**Second-order effects found and fixed within this same pass** (see §14): three existing tests
(`test_paper_advance.py`, `test_live_workstation.py`, and — caught only by the full regression run,
not targeted testing — `test_fail_closed_workflow.py`) mutated `engine.account` in memory without
persisting, a state the engine can never legitimately be in after the G9 fix — all three corrected
to persist their injected state, matching what real code always does. The G10 exception handler's
first version reused `_page()` for styling, which itself makes live DB reads that could be the very
thing failing — caught by this fix's own regression test before being committed, rewritten to be
fully self-contained.

**Full regression**: see §13 for the exact final run (executed after every change in this pass).
Real-order execution remains structurally impossible, independently re-verified (26/26 dedicated
safety tests passing) after every change tonight.

## 2. Issues found (this pass)

| ID | Severity | Component | Status |
|---|---|---|---|
| G9 | High → FIXED | `paper/engine.py`, `paper/store.py`, `live/workstation.py`, `mcp_server/server.py` | FIXED |
| G9-B | Low | `paper/engine.py` | investigated, `ACCEPTED_RISK` (not a reachable defect) |
| G10 | Low → FIXED | `dashboard/app.py` | FIXED |
| G11 | Low → FIXED | `dashboard/app.py` | FIXED (doc correction) |
| G12 | Low → FIXED | `live/dhan/candle_builder.py`, `live/dhan/market_data_source.py` | FIXED (dormant, defensive) |
| G13 | Low | `live/dhan/candle_builder.py` | re-investigated, still OPEN (genuinely no safe cheap fix) |
| G14 | Low → FIXED | `paper/store.py`, `paper/errors.py` | FIXED |
| R3 | Medium | `quant_research/market_behavior.py` | CLASSIFIED — NO EFFECT |
| R4 | Medium | `learning/profitability.py` | CLASSIFIED — NO EFFECT |
| R5 | Medium | `strategy/multiple_testing.py` | CLASSIFIED — MINOR DISCLOSURE ISSUE |
| R6 | Low → FIXED | `strategy/hypothesis_registry.py` | FIXED (doc correction) |
| (new) | Low | `tests/failure_injection/failure_matrix.yaml` | FIXED (duplicate YAML key silently overwrote real evidence text) |
| (new) | Low | `ARCHITECTURE.md` | FIXED (stale "read-only" claim about the dashboard) |

Full detail for every entry lives in `docs/MASTER_KNOWN_ISSUES.md`, which this report does not
duplicate.

## 3. Dashboard concurrency architecture (G9)

**Investigation, before any fix**: mapped every writer and reader of `data/live_sim_trading.db`'s
`account` row. Writers: `PaperTradingEngine.submit_signal` (evaluates risk against `self.account`,
does not mutate it), `process_bar`/`close_at_end_of_data` (mutate `self.account` in place, then
`store.save_account`). Readers: the same three methods, plus every `live/workstation.py` display
function. Confirmed `PaperStore`'s connection is `isolation_level=None` (autocommit) + WAL, so a
fresh `SELECT` outside a transaction always sees the latest committed state from another
process — the gap was purely that nothing ever issued that fresh read. Confirmed
`store.transaction()` used plain `BEGIN` (SQLite DEFERRED), so two processes could both pass a
check-then-act read before either's write landed — a genuine cross-process TOCTOU independent of
the caching issue. Confirmed the account model is single-position-only, naturally limiting (not
eliminating) one class of dual-writer scenario.

**Chosen architecture**: option (b) from the earlier report — always re-fetch fresh state
immediately before any write-path decision AND before any display read — rather than making the
dashboard read-only or routing through a supervisor. Reasoning: dashboard approve/reject is a
required, already-documented control (not optional convenience), and the fleet workflow already
has full process-level isolation as its own single-writer guarantee, so no new execution authority
was invented — the fix closes the staleness at its exact source (the cached `PaperTradingEngine`
instance) rather than adding a new coordination layer.

**Mechanism**:
1. `PaperTradingEngine.refresh_account()` — a fresh `store.get_account()` read, called at the top
   of every transactional method AND every read-only display function across
   `live/workstation.py` and `mcp_server/server.py`.
2. `PaperStore.transaction()` now issues `BEGIN IMMEDIATE` — SQLite's own RESERVED lock, acquired
   atomically at the start of the transaction (a native OS-level file lock: cannot be left stale
   by a crashed holder, since the OS releases it when the process's file descriptor closes).

**Concurrency red-team of the fix** (Part 2): tested two dashboard-shaped engine instances racing
on `submit_signal` for both the SAME signal (pre-existing coverage, cycle 15) and DIFFERENT
signals for the SAME symbol (new coverage, proves the `BEGIN IMMEDIATE` fix specifically) — real
threads, real file-backed SQLite, `threading.Barrier`-synchronized. Proved: exactly one side ever
wins the symbol's single PENDING-order slot; a stale cached account never causes a wrong risk
decision; no deadlock (`BEGIN IMMEDIATE` is a single, non-nested lock acquisition per transaction,
released automatically at commit/rollback/process-exit).

## 4. Database changes

- `PaperStore.transaction()`: `BEGIN` → `BEGIN IMMEDIATE` (G9).
- `PaperStore._migrate_trades_unique_position_id_index()`: new `UNIQUE(position_id)` index on
  `trades`, mirroring `predictions/store.py`'s established migration pattern exactly — additive
  index only (no column backfill needed), soft-fails (constraint reported inactive, not a crash)
  against a pre-existing database with real historical duplicates (G14).
- `paper.errors.DuplicateTradeForPositionError`: new typed error, mirroring
  `DuplicatePredictionError`'s pattern, raised by `save_trade()` when the new constraint rejects a
  duplicate.

Migration tests: `tests/test_paper_store.py::test_migration_disables_the_unique_index_gracefully_when_preexisting_duplicate_trades_exist`
(raw-sqlite3-seeded pre-existing-duplicate scenario, proves graceful degradation, no data loss).
Concurrent-write test: `::test_two_connections_racing_to_save_a_trade_for_the_same_position_never_both_succeed`.

## 5. Frontend/backend changes

`dashboard/app.py`:
- Registered `exception_handlers={Exception: _handle_uncaught_exception}` on the Starlette `app`
  (G10) — a clean 500 page instead of a raw traceback, with the real exception logged
  server-side. The handler is deliberately self-contained (no live DB/workstation reads of its
  own), a lesson learned from this fix's own second-order bug (see §14).
- Corrected two docstrings (`api_state`, `_page`) that falsely claimed a client-side polling
  script exists (G11) — none does; the real, sole refresh mechanism is the existing 15s full-page
  meta-refresh.
- `ARCHITECTURE.md`'s component table corrected: the dashboard is not read-only (4 POST routes
  mutate state via the same `live/workstation.py` functions the CLI's own approval prompt calls).

No separate JS/TS frontend exists in this repository (confirmed again this pass: no
`package.json`, no `.tsx`/`.jsx` files) — "frontend" is the server-rendered dashboard covered
above, plus the MCP tool surface (`mcp_server/server.py`), where the second G9-DISPLAY instance was
found and fixed (§3, §9).

## 6. Backend changes

`live/dhan/candle_builder.py`, `live/dhan/market_data_source.py` (G12): added a `threading.Lock`
around `CandleBuilder`'s mutating (`on_tick`, split into a thin locked wrapper plus its unchanged
original body) and read-only (`last_known_price`, `last_known_timestamp`, `flush()`) paths.
Confirmed still genuinely dormant (no production caller today) but relying on GIL atomicity for a
COMPOUND read (price paired with its own timestamp) was never actually correct even under a GIL
build — confirmed via `sys._is_gil_enabled()` that a free-threaded build is a real, selectable
option for this exact Python 3.14 install. Added `last_known_price_and_timestamp()` (a true atomic
pair read) and `rejected_tick_counts_snapshot()` (a lock-protected copy); updated
`market_data_source.py`'s own wrappers to use them instead of two separate, non-atomically-paired
reads. Deadlock analysis: a single, non-reentrant lock on a documented-pure (no I/O) class where no
locked method calls another — cannot deadlock by construction.

## 7. Research methodology review

A dedicated investigation (read-only, no strategy/registry code changes beyond the one disclosed
R6 fix) verified each of R3-R6's original claims against the current code and classified each:

- **R3** (no purging/embargo in backtest splits): claim verified true but narrower in scope than
  originally stated — affects only ~19 of 59 hypotheses (those built on
  `quant_research/market_behavior.py`'s `SymbolDataset`, not the ~40 that run through
  `backtesting.engine.run_backtest`, a structurally different mechanism). Max leak window (20 bars)
  is small relative to the smallest affected split; every affected verdict is REJECTED on
  large-magnitude, qualitative grounds, not a borderline call this could plausibly flip.
  **CLASSIFIED — NO EFFECT.**
- **R4** (no dependence correction in CIs): claim verified true and broad in reach, but the defect
  is asymmetric — an understated CI can only make an already-decisive result look LESS decisive,
  never manufacture a hidden positive edge from an already-null result. The one SUPPORTED entry
  rests on a different statistical test entirely; the one borderline thread was independently
  killed by unrelated findings. **CLASSIFIED — NO EFFECT.**
- **R5** (stale multiple-testing accounting): claim verified true. True honest count reconciled:
  59 registry entries + 1 (`H_MEANREV_013`, deliberately unregistered per its own preregistration)
  + 4 (derivatives family, its own separately-disclosed correction) = **64**. A stricter
  (larger-family) correction can only push already-null results deeper into null.
  **CLASSIFIED — MINOR DISCLOSURE ISSUE** — a registry accounting table was added to
  `docs/MASTER_KNOWN_ISSUES.md` reconciling this; no hypothesis requires a rerun.
- **R6** (undisclosed cost model): claim verified exactly as described. The more realistic NSE
  cost preset is strictly more expensive; applying it to `H_MEANREV_001`'s already-negative point
  estimates would only push them further negative. **FIXED** — added the disclosure directly to
  `H_MEANREV_001`'s own registry entry (additive text only, no number/verdict changed).

No hypothesis was reopened, reversed, or reinterpreted. No new backtest was run.

## 8. Multiple-testing registry reconciliation (R5)

| Ledger | Count | Where tracked |
|---|---:|---|
| `strategy/hypothesis_registry.py` entries | 59 | that file |
| `H_MEANREV_013` (audit-only, tested, deliberately unregistered) | 1 | `audit/edge_feasibility/PHASE8_MULTIPLE_TESTING_AUDIT.md` |
| Derivatives family (`DERIV_001-004`) | 4 | `audit/derivatives_research/PHASE6_DECISION_GATE_AND_TERMINAL_REPORT.md`, own `family_size=4` correction |
| **True total distinct tested hypotheses** | **64** | reconciled in `docs/MASTER_KNOWN_ISSUES.md` R5 |

The 3 entries added since Phase 8's own one-time manual correction (`H_CONTEXT_MARKET_006/007`,
`H_MEANREV_014`) each already self-apply a correction that survives — verified against the actual
registry text, not assumed.

## 9. Cost model review (R6)

`backtesting/costs.py`'s `india_nse_intraday_2026()` preset (used by every hypothesis except
`H_MEANREV_001`'s original run) models: ₹20 flat brokerage, entry/exit slippage (5bps/10bps),
`fees_pct` (0.00375%), and `taxes_pct` (0.025%) per fill — roughly 0.11% more expensive round-trip
than the generic default `CostModel()`. `H_MEANREV_001` used the cheaper default; disclosed this
pass (§7). A full per-hypothesis cost-assumption audit (brokerage/GST/stamp-duty/slippage/spread/
liquidity/minimum-brokerage/turnover for all 59+ entries) was judged out of scope for this pass —
the one concrete, disclosed gap (H_MEANREV_001) was fixed; a blanket audit of an already-frozen,
NO-DEMONSTRATED-EDGE research program would be exactly the kind of unbounded, low-value work this
mission's own "do not spend unlimited compute" instruction warns against, absent a specific,
evidenced reason to suspect another entry's cost model is both wrong AND verdict-threatening.

## 10. Security review

No new finding. Re-confirmed alongside the rest of this pass: no `shell=True`, no unsafe
deserialization, no secret committed, dashboard still binds 127.0.0.1 by default, MCP server still
stdio-only. `BEGIN IMMEDIATE` and the new lock in `CandleBuilder` are both native
SQLite/stdlib-threading mechanisms — no new dependency, no new attack surface.

## 11. Real-order safety verification

Re-verified after every change in this pass: `tests/test_dhan_no_real_orders.py` +
`tests/test_approval_security.py` + `tests/test_mcp_live_workstation.py`, **26/26 passing**. Every
mutating endpoint touched this pass (dashboard POST routes, MCP `paper_trade_signal_tool`,
`submit_paper_market_bar_tool`) still terminates only in `PaperTradingEngine`/`LiveStateStore`
operations — none reaches `live/dhan/broker_adapter.py::DisabledDhanOrderExecutor` (still zero call
sites outside its own file and tests). `BEGIN IMMEDIATE` and `refresh_account()` do not alter
`RiskEngine.evaluate`'s own logic — they change WHEN/HOW its input (`account`) is fetched, never
what it does with that input. No supported production path can submit a real order.

## 12. Tests

New/changed test files: `tests/test_paper_engine.py` (+2 concurrency tests), `tests/test_paper_store.py`
(+4 migration/concurrency tests), `tests/test_paper_advance.py` (1 second-order fix),
`tests/test_live_workstation.py` (1 second-order fix), `tests/test_dashboard.py` (+2 tests),
`tests/test_dhan_candle_builder.py` (+2 concurrency tests), `tests/failure_injection/failure_matrix.yaml`
(+2 new rows, 1 duplicate-key bug fixed), `tests/test_hypothesis_registry.py` (unchanged, re-verified).

Every new concurrency claim in this report is backed by a REAL multi-threaded/multi-connection test
against a real file-backed SQLite database — not reasoning alone, matching this project's own
established convention (cycle 15's precedent).

## 13. Full regression results

Final run, executed against the exact state committed in this pass, after every fix and every
second-order correction: **2779 passed, 0 failed, 1 pre-existing unrelated warning (chromadb's own
dependency deprecation, unchanged all night), 3577.94s.** Up from 2765 at this pass's own starting
baseline (14 new tests added this pass: G9 ×2, G10 ×2, G12 ×2, G14 ×4, plus 4 new
failure-injection-matrix rows the matrix's own integrity test expands into additional collected
items). This run caught a THIRD second-order test regression from the G9 fix beyond the two found
during targeted testing — `tests/test_fail_closed_workflow.py::test_account_state_changes_after_approval_triggers_second_risk_rejection`,
the same "mutated `engine.account` in memory without persisting" pattern, fixed the same way — a
direct demonstration of why this mission's own "run the full suite, not just targeted tests,
before declaring done" discipline matters.

## 14. Second-order review

Performed for every fix in this pass, per the mission's own "what did this change make possible
that was impossible before?" instruction:

- **G9's `refresh_account()`** made three EXISTING tests fail (two found via targeted testing,
  a third only surfaced by the full regression run): all three had mutated `engine.account`
  directly in memory as a test-isolation shortcut, without persisting — a state the engine can
  never legitimately be in during real operation (every real mutation persists before any other
  call could observe it). All three were real regressions from the fix correctly rejecting
  artificial, unpersisted state — not from the fix being wrong. All three tests corrected to
  persist their injected state, matching what real code always does — and matching an existing,
  already-correct sibling test (`test_live_pipeline.py`'s drawdown test) that already did this
  before tonight, confirming this is the established norm, not a new invention.
- **G10's exception handler** (first version) reused `_page()` for visual consistency. `_page()`
  itself renders live banners that read the same workstation/DB state that could be the very thing
  failing — a genuinely corrupted DB would make the error page ITSELF raise a second, unhandled
  exception, defeating the fix. Caught by this fix's OWN regression test (which forces
  `get_feed_status` to always raise) before the flawed version was ever committed. Rewritten to be
  fully self-contained.
- **G12's lock**: measured for deadlock risk specifically (a single, non-reentrant lock; no locked
  method calls another; class is documented I/O-free) — none found, confirmed by a real 2000-tick,
  two-thread concurrency test completing well within its timeout.
- **G14's typed error**: checked for any OTHER caller of `save_trade` that might have depended on
  the OLD silent-duplicate-insert behavior — confirmed exactly one production call site
  (`paper/engine.py::_close_position`, already inside a transaction, already the sole writer by
  design), no behavior change for the only real caller.
- **BEGIN IMMEDIATE**: checked whether it could starve dashboard reads during a writer transaction
  — confirmed no: WAL mode allows concurrent readers regardless of an in-flight writer transaction;
  `BEGIN IMMEDIATE` only affects OTHER transactions that ALSO intend to write.

## 15. Remaining risks

- **G9-B**: investigated, confirmed not a reachable defect (see `docs/MASTER_KNOWN_ISSUES.md`) —
  `ACCEPTED_RISK`, not a gap.
- **G13**: re-investigated this pass, confirmed no safe cheap fix exists — the only correct fix
  requires a two-tick-agreement mechanism analogous to the one already in `CandleBuilder`, which
  itself took two real production incidents to get right; building an analogous one now under
  time pressure risks repeating that history in one pass instead of two incidents' worth of
  evidence. Low severity, narrow trigger, disclosed.
- **R1, R2**: carried over from the 2026-09-22 pass, not re-investigated this pass, both already
  judged non-verdict-threatening in their own earlier investigations.

## 16. REQUIRES_LIVE_VALIDATION

Everything in this report was verified offline (unit/integration/concurrency tests, static code
reading, migration simulation). The market was closed for the entirety of this pass. The next real
trading-hours session is the only way to observe: whether the G9 fix behaves correctly under a
genuine simultaneous dashboard+CLI session against real market data (today proven only against
synthetic, deterministic concurrency tests); whether `refresh_account()`'s extra `SELECT` per
display call has any observable latency impact on the dashboard under real, repeated 15s-refresh
load over a multi-hour session (not measured this pass — reasoned to be negligible, a single
indexed-by-primary-key SELECT, but not empirically profiled against a real long session).

## 17. RESEARCH_DECISION_REQUIRED

R1 (point-in-time universe correction not wired into the shared backtest engine) and R2
(`H_MEANREV_013`'s registry status) remain open human decisions, unchanged from the 2026-09-22
report. Neither was found, this pass or the last, to threaten any settled verdict.

## 18. Final Git state

See the commit log for this pass's exact commits (grouped: paper-store/dashboard-state-ownership
hardening, dashboard frontend fixes, candle-builder concurrency, research-methodology disclosure,
documentation). Full regression run, clean tree, and synchronized refs confirmed before this report
was finalized — see §13.

## Convergence assessment

No known critical or unaddressed High-severity safety/reliability defect remains open: G9 (the
prior single highest-severity open item) is now FIXED with real concurrency-test evidence. Every
fixed defect has regression coverage, including new real multi-threaded/multi-connection tests
where the finding was concurrency-shaped. The fresh, independent final red-team pass (Part 19)
found and closed 3 additional real, if low-severity, defects (a second G9-class instance in the MCP
server, a duplicate-key data-loss bug in the failure-injection registry itself, a stale
architecture-doc claim) rather than declaring completion once the planned list was exhausted.
Research-methodology findings are explicitly classified with evidence, not silently resolved or
left vague. Documentation was corrected where it drifted from implementation. Real-order execution
remains structurally impossible, re-verified. **Convergence reached for what is checkable
offline.** Live-market validation of this pass's fixes (§16) remains outstanding by necessity
(market closed), not by omission.
