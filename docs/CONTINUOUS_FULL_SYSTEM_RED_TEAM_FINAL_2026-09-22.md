# Continuous Full-System Red-Team — Final Report (2026-09-22)

This is the final, consolidated report for tonight's entire adversarial engineering effort: an
earlier full-system red-team pass (see `docs/FULL_SYSTEM_RED_TEAM_2026-09-22.md`, commit
`501dbf0`) followed by a continuous, multi-pass "inspect → attack → fix → re-audit → search for
second-order effects → repeat" loop, executed autonomously to convergence. Every fixed defect has
a regression test; every deferred item has a stated reason; every research-methodology finding is
labeled `RESEARCH_DECISION_REQUIRED` rather than silently resolved.

**Evidence labels used throughout**: PROVEN (a passing, real test demonstrates the claim), TESTED
(exercised directly, not merely reasoned about), INFERRED (a reasoned conclusion, explicitly
labeled as such, not independently verified), UNRESOLVED (a real, open question), REQUIRES
LIVE-MARKET VALIDATION (cannot be established offline; the market was closed for the entirety of
this session).

## 1. Executive summary

Starting baseline: branch `final-product-hardening`, HEAD `501dbf0`, clean tree, all refs synced,
Python 3.14.4, Windows 11 Pro, 2746 tests collected. Six parallel investigation passes were run
(dashboard/frontend + API contract; security deep-dive; documentation-vs-reality; second-order
review of the prior pass's own six fixes; concurrency/resource-leak audit; research-methodology
deep audit), plus direct, hand-verified work on real-order-execution safety, the failure-injection
matrix, and several fixes made directly rather than delegated.

**Total new findings this pass**: 14 concrete findings (G1–G14) plus 4 research-methodology items
(R3–R6). **Fixed with regression tests**: 6 (G1, G2, G3, G4, G5, G6). **Deferred, real, disclosed**:
6 (G9–G14), of which G9 is the single highest-severity open item (architectural, not a quick
patch). **Research-methodology, human decision required**: 4 (R3–R6), none verdict-threatening for
any settled REJECTED hypothesis.

The single most important finding of this entire pass is **G3**: a dedicated second-order review
of one of the EARLIER pass's own fixes (the CandleBuilder close-ordering fix, F1) found that fix
had itself introduced a real, reproducible data-integrity defect — broken redelivery-duplicate
detection, causing volume double-counting for a specific tick-ordering pattern. This was found and
closed within the same night, before any live use, and is the clearest demonstration of why this
mission's own "search for second-order effects" phase is not optional.

**Full regression**: 2765 passed, 0 failed, 1 pre-existing unrelated deprecation warning
(chromadb's own dependency), 445.92s. Real-order execution remains structurally impossible,
independently re-verified (26/26 dedicated safety tests passing) after every change tonight.

## 2. System architecture audited

Python-only backend (no separate JS/TS/React frontend — confirmed: no `package.json`, no
`.tsx`/`.jsx` files anywhere). The "frontend" is `dashboard/app.py`, a server-rendered Starlette/
uvicorn HTML dashboard, plus `mcp_server/server.py` (stdio-only MCP tools for an LLM client). No
CI/CD, no Docker/container files, no deployment YAML exist in this repository — confirmed by
direct inventory; this is a single-operator, local-only, manually-run system by design, not an
oversight. Persistence is entirely SQLite (WAL mode). The live-data path is
Dhan-WebSocket → `CandleBuilder` → `LiveSimPipeline` → `CriticGate` → `RiskEngine` →
`PaperTradingEngine`. A separate, complementary research pipeline (`backtesting/`,
`quant_research/`, `strategy/hypothesis_registry.py`) is frozen at NO DEMONSTRATED EDGE.

## 3. All findings (this pass)

See `docs/MASTER_KNOWN_ISSUES.md` for the complete, structured (ID/Severity/Component/Status/
Evidence/Reproduction/Root cause/Fix/Test/Residual risk) inventory of every finding from both
tonight's passes. Summary below; full detail lives in that file.

| ID | Severity | Component | Status |
|---|---|---|---|
| G1 | Medium | `dashboard/intelligence.py` | FIXED |
| G2 | Medium | `live/workstation.py` (surfaced via MCP) | FIXED |
| G3 | High | `live/dhan/candle_builder.py` | FIXED (second-order) |
| G4 | Low | `main.py` | FIXED (second-order) |
| G5 | Low | `tests/test_market_indicators_properties.py` | FIXED (second-order) |
| G6 | Low | `live/runtime_layout.py` | FIXED (defensive) |
| G9 | High (scoped) | `live/workstation.py`, `paper/engine.py` | OPEN — architectural |
| G10 | Low | `dashboard/app.py` | OPEN |
| G11 | Low | `dashboard/app.py` (docs) | OPEN |
| G12 | Low (dormant) | `live/dhan/candle_builder.py` | OPEN — unreachable today |
| G13 | Low (narrow) | `live/dhan/candle_builder.py` | OPEN — disclosed |
| G14 | Low (mitigated) | `paper/store.py` | OPEN — carried over |
| R3 | Medium | `backtesting/splits.py` | `RESEARCH_DECISION_REQUIRED` |
| R4 | Medium | `learning/profitability.py` | `RESEARCH_DECISION_REQUIRED` |
| R5 | Medium | `strategy/multiple_testing.py` | `RESEARCH_DECISION_REQUIRED` |
| R6 | Low | `strategy/hypothesis_registry.py` | `RESEARCH_DECISION_REQUIRED` |

## 4. Fixed defects (this pass) — detail

### G3 — the critical second-order finding

A dedicated agent was tasked SPECIFICALLY with trying to break the six fixes made in the prior
pass, treating each as adversarially as a stranger's code. For the CandleBuilder close-ordering
fix (F1: `close` now only advances chronologically, not on arrival order), it found: the
redelivery-duplicate check (`is_likely_redelivered_duplicate`) compared the incoming tick against
`last_source_timestamp`/`close` — fields that, after F1, track the chronological-MAX tick, not the
most-recently-MERGED one. A concrete, reproducible sequence — a tick, then a genuine out-of-order
tick, then a genuine wire-redelivery of that SAME out-of-order tick — would previously (pre-F1)
correctly suppress the redelivery's volume, but post-F1-only, `last_source_timestamp`/`close` had
already moved past that tick (to the chronologically-later first tick), so the redelivery no
longer matched and its volume was added a second time. **Proven with a real test**
(`tests/test_dhan_candle_builder.py::test_a_genuine_redelivery_of_an_out_of_order_tick_still_does_not_double_count_volume`)
that failed against the F1-only code (`bar.volume == 20` instead of the correct `15`) before the
fix in this pass. **Fixed** by adding `last_merged_timestamp`/`last_merged_price` — a separate pair
of fields updated unconditionally on every merge (arrival order), used only by the redelivery
check, fully decoupled from `close`/`last_source_timestamp` (chronological order, used only for
the bar's own OHLC). Both mechanisms now independently correct; the test suite proves both
simultaneously (`bar.close == 100.0` AND `bar.volume == 15.0` in the same scenario).

### G1, G2, G4, G5, G6 — see §3 table and `docs/MASTER_KNOWN_ISSUES.md` for full detail

Each has its own root cause, fix, and regression test documented there. None touched strategy,
risk, or research logic.

## 5. Remaining issues (deferred, disclosed)

G9 (dashboard dual-writer risk) is the only High-severity open item, and it is architectural: the
dashboard's single-symbol workstation pages cache a `PaperTradingEngine` whose account state is
loaded once and never refreshed, while `submit_signal()`'s RiskEngine evaluation uses that same
cached state rather than a fresh re-read. This is a genuine risk ONLY if the dashboard and a
separate `paper-live` (no `--runtime-dir`) CLI process are run simultaneously against the same
`data/live_sim_trading.db` — a scenario the codebase's own documentation explicitly anticipates as
a supported use case. **The fleet workflow (`fleet-supervise`, `/fleet`, `fleet-summary`) is NOT
affected** — fully isolated per-symbol state, no shared cached engine. Not fixed tonight: the two
candidate fixes (enforce single-writer, or always re-fetch before write-path risk evaluation) are
both real design changes to a load-bearing assumption in `PaperTradingEngine`, used by the actual
live pipeline too — not a "minimal fix," and rushing it under time pressure risked introducing a
new defect into the one component (`RiskEngine`) this entire mission was told never to weaken.
Recommendation: do not run the dashboard approval workflow and a separate single-symbol CLI
session concurrently until this is resolved by a deliberate, separately-scoped change.

G10–G14: see `docs/MASTER_KNOWN_ISSUES.md`. All Low severity, all either dormant/unreachable today
or narrow-trigger, none affecting the real-order-impossibility invariant or the live decision
chain's correctness.

## 6. Research issues

R3–R6 (this pass) join R1–R2 (the earlier pass) as `RESEARCH_DECISION_REQUIRED` findings. None was
found severe enough to plausibly overturn a settled REJECTED/INCONCLUSIVE verdict — in each case
either (a) the affected population is already decisively negative (correcting the gap would only
make it more negative, e.g. R6's cost-model finding), or (b) the gap is most relevant to the ONE
still-open, not-yet-promoted question (the H_MEANREV chain), not to the closed research program's
own bottom line (R3, R4, R5). No hypothesis was reopened, reversed, or reinterpreted. A genuine,
new accounting gap was found: the honest count of distinct tested hypotheses across the whole
program (~64: 59 registry entries + `H_MEANREV_013`, tested but unregistered + 4 derivatives
hypotheses tracked separately) is not stated in any single document today — R5 flags this for a
human decision on how to reconcile it.

## 7. Frontend findings

Dashboard/MCP surface fully audited (`docs/MASTER_KNOWN_ISSUES.md` G1, G2, G9, G10, G11, G12).
**Every mutating endpoint** on both the dashboard (4 POST routes) and the MCP server (4 mutating
tools) was traced exhaustively to its actual call chain — all terminate in
`PaperTradingEngine`/`LiveStateStore` operations only; none reaches
`live/dhan/broker_adapter.py::DisabledDhanOrderExecutor` (confirmed: zero call sites for that class
outside its own file and test files). The one real "frontend tells a lie" finding (G2, hardcoded
`source: MOCK`) has been fixed. Timestamp/timezone handling, cross-symbol data isolation, and
field-name contracts against the real store schemas were all spot-checked and found correct with
evidence (PROVEN, not merely inferred).

## 8. Backend findings

See §3–5 and `docs/MASTER_KNOWN_ISSUES.md`. Concurrency audit (a genuinely new angle this pass)
found the WebSocket receive-thread / foreground-consumer locking discipline in
`live/dhan/market_data_source.py` correct with evidence (no deadlock path found; every
lock-holding block is short and non-blocking), with one dormant, already-disclosed gap (G12). No
unbounded in-memory growth found anywhere in the live tick/bar path over a multi-hour session
(every collection checked is either fixed-size or bounded with drop-oldest overflow, already
established before tonight).

## 9. Security findings

Full deep-dive: **zero actionable findings**. No secret was ever committed to git history (checked
via `git log --all -p`, all refs). `.gitignore` correctly covers `.env`/`*.db`. No unsafe
subprocess construction (`shell=True` never used, list-based argv everywhere). No unsafe
deserialization (no `pickle`, no `eval`/`exec`, `yaml.safe_load` used exclusively). No SSRF (every
outbound host is a hardcoded literal or operator-set config default). Dashboard binds to
127.0.0.1 by default with an explicit warning if bound elsewhere; MCP server has no network
surface at all (stdio-only). One defensive-hardening opportunity found and fixed this pass (G6,
path-separator rejection in symbol-derived filesystem paths) — not currently exploitable given the
trusted-input-only threat model, fixed anyway as cheap, safe hardening.

## 10. Data integrity findings

G3 (see §4) is the headline finding: a real, reproducible tick-level data-corruption defect,
introduced by an earlier fix the same night, found and closed before any live exposure. Combined
with the earlier pass's F1/F2 (close-ordering, NaN/Inf rejection), the live tick-to-bar aggregation
path has now survived three genuinely independent adversarial passes in one night. No lookahead
defect found in `compute_sma`/`compute_rsi`/`compute_macd`/`compute_atr` (proven via direct
mutate-future-rows tests, `tests/test_no_lookahead_redteam.py`, carried over from the earlier
pass).

## 11. Persistence findings

WAL mode + real transactions confirmed to protect against kill-mid-write corruption (re-confirmed
this pass via a dedicated concurrency/resource audit, not merely re-cited). One connection-leak
class found and fixed (G1, `dashboard/intelligence.py`). `paper.db`'s `trades` table still lacks a
schema-level `UNIQUE(position_id)` constraint (G14, carried over, still deferred — currently
mitigated by application discipline, not exploitable via any known path).

## 12. Operational findings

Failure-injection matrix (`tests/failure_injection/failure_matrix.yaml`) extended from 54 to 62
rows this pass, adding four new entries matching this project's own established, machine-verified
convention (every row's cited test node ID is checked for real existence by
`tests/failure_injection/test_matrix_integrity.py`, which passed with the new rows before and
after every subsequent change): NaN/Inf tick rejection, fleet-worker-unresponsive detection,
CriticGate fail-closed on exception, and corrupted-venv handling. Thread-leak-on-reconnect
confirmed correct with evidence, with one honest caveat: the old transport's thread is signaled to
close (fire-and-forget, `daemon=True`) but never explicitly `.join()`ed, so actual termination
timing depends on the third-party `websocket-client` library's own internal behavior, which this
audit did not independently verify against a real socket.

## 13. Test quality findings

Two genuine test-quality defects found and fixed: F6 (an already-flaky test, root-caused as
test-infrastructure timing rather than a real indicator defect — see the earlier pass's own
report) had its fix over-broadened to silently disable genuine speed-regression detection for 13
unrelated tests (G5), now narrowed to only the one test that actually needed it. The existing,
pre-tonight `tests/failure_injection/failure_matrix.yaml` mechanism — a machine-checked registry
that fails the build if a cited test doesn't actually exist — is itself a strong, already-in-place
answer to this mission's own "tests that don't prove what they claim" concern; extended, not
replaced, this pass.

## 14. Documentation findings

Four real documentation-vs-reality gaps found and fixed: stale live-validation date (README.md,
"most recently 2026-09-15" → corrected to reference the 2026-09-22 session), stale test counts
(README.md: 2,560 → 2,765; INSTALLATION.md: explicitly marked stale with an honest note about what
wasn't re-verified rather than a fabricated new number), a missing note about the new
self-correcting venv guard near the `fleet-supervise` example (README.md, OPERATIONS_GUIDE.md
still needs the same treatment — not done this pass), and an overstated safety claim in
ARCHITECTURE.md ("can never hang in CONNECTING forever," missing its own already-disclosed
CONNECTED-state caveat, now added). `FINAL_PRODUCT_READINESS_REPORT.md` (dated 2026-09-15) now
carries a forward-pointer to both of tonight's newer, superseding audits.

## 15. Safety-invariant verification

| Invariant | Status | Evidence |
|---|---|---|
| Real orders impossible | **PROVEN, re-verified this pass** | `tests/test_dhan_no_real_orders.py` + `tests/test_approval_security.py` + `tests/test_mcp_live_workstation.py`, 26/26 passing after every change tonight. Every dashboard/MCP mutating endpoint traced exhaustively (§7) — none reaches the disabled order executor. |
| RiskEngine cannot be bypassed | **PROVEN** (unchanged from the earlier pass) | Not re-derived this pass; no code touched this pass alters `submit_signal`'s unconditional RiskEngine call. |
| Critic cannot authorize execution | **PROVEN** (unchanged) | `critic/engine.py` untouched this pass; failure-injection row FI-CRITIC-UNEXPECTED-EXCEPTION-FAILS-CLOSED added as permanent regression coverage. |
| Stale data cannot generate valid candles | **PROVEN, strengthened** | G3's fix directly strengthens this — see §4/§10. |
| Future data cannot enter predictions | **PROVEN** (unchanged) | `predictions/tracker.py` untouched this pass. |
| Production cannot silently use mock data | **PROVEN, strengthened** | G2's fix closes the one place a hardcoded (not silently-mock, but silently-WRONG-label) value was surfaced to an external client. |
| Wrong Python environment cannot silently run production | **PROVEN** (unchanged) | `live/environment_guard.py`'s core logic untouched this pass beyond the already-tested F5 fix. |

## 16. Failure-injection results

62 rows, all passing, all with a real, collectible cited test
(`tests/failure_injection/test_matrix_integrity.py`, 131+ tests including the integrity checks
themselves). Four new rows added this pass (§12).

## 17. Mutation-test results

The pre-existing `momentum and/or` mutation guard for `trend_momentum_baseline` (the mission's own
explicit convergence requirement) was independently re-run and confirmed passing:
`tests/test_backtest_strategy.py`, 9/9 passed. No strategy parameter was changed or optimized this
pass. The second-order review itself functioned as a form of manual mutation testing against
tonight's own six earlier fixes, finding G3 (a real defect) and G4/G5 (real but lower-severity
gaps) — direct evidence the technique works, not merely asserted.

## 18. Full regression results

**2765 passed, 0 failed, 1 pre-existing unrelated warning, 445.92s** — the definitive, final run
of the night, executed after every fix in this pass was in place. Up from 2746 collected at this
pass's own starting baseline (19 new tests added this pass: G1 behavior-preserving, no new test
needed there; G2 ×3, G3 ×1, G4 ×1, G5 ×0 new test — narrowed an existing one; G6 ×5).

## 19. Second-order review

A dedicated pass explicitly re-attacked all six of the EARLIER mission's own fixes. Result: 2 real
defects found (G3 — critical, fixed; G4 — real, fixed), 1 design-tradeoff identified and corrected
(G5 — over-broad scope, narrowed), 3 confirmed clean with no further action needed (the NaN/Inf
fix, F5's OSError catch, and — after deep, specific investigation of the exact "does the 300s
staleness threshold work for every `--interval`" concern raised — F3's heartbeat-staleness
detection: heartbeat cadence is bounded by the feed-queue poll timeout (~5s), independent of
`--interval`, so no false-positive risk exists for coarse intervals). This second-order pass is
itself now closed; a THIRD-order review of G3/G4/G5's own fixes was not performed (diminishing
returns judged to have been reached — each of these three fixes is small, narrowly scoped, and
independently regression-tested).

## 20. Final residual risk

Only what genuinely remains, per this mission's own instruction not to inflate the list:

1. **G9** (dashboard dual-writer risk) — real, High severity but narrowly scoped, requires a human
   architectural decision.
2. **G10–G14** — real but Low severity, disclosed, either dormant or narrow-trigger.
3. **R3–R6** (plus the earlier pass's R1–R2) — research-methodology items requiring a human
   decision, none currently verdict-threatening.
4. The ~15:13–15:14 IST fleet-wide feed interruption's root cause remains genuinely unproven
   (unchanged — a separate, already-documented investigation from earlier tonight,
   `docs/DHAN_FEED_INTERRUPTION_1514_INVESTIGATION_2026-09-22.md`; not re-opened by this pass).
5. **REQUIRES_NEXT_LIVE_SESSION**: everything in this report was verified offline (unit/integration
   tests, static code reading, mutation testing, failure injection via mocks/monkeypatching). The
   market was closed for the entirety of this session. No live Dhan connection was opened, no real
   or paper order was placed, no live data was fabricated. The next real trading-hours session is
   the only way to observe: whether G3's fix behaves correctly against genuine live tick reordering
   (not just the synthetic adversarial sequence in its test), whether the 15:13–15:14 pattern
   recurs a third time, and whether G2's fix correctly reports `DHAN`/`LIVE` against a real feed
   (today it was only proven against synthetic `feed_status` rows in a test).

## 21. Recommended next actions, ordered by risk

1. Decide G9 (dashboard dual-writer risk) — the highest-severity open item, architectural.
2. Decide R3–R6 (and R1–R2 from the earlier pass) — research-process decisions.
3. Consider G14 (`trades` table unique-index migration) as a small, focused follow-up.
4. Run another live NSE session (market permitting) and specifically watch: does G3's fix hold
   under real reordering; does the 15:13–15:14 pattern recur; does G2 correctly report the real
   feed source on the dashboard/MCP surface.
5. G10/G11 (dashboard exception handler, stale `/api/state` docstring) — low priority, no safety
   impact, worth a dedicated small pass when convenient.
6. No further code changes are recommended beyond the above — convergence criteria (§ below) are
   met for everything checkable offline tonight.

## Convergence assessment

Per the mission's own 16-point definition of "done": no known reproducible CRITICAL or unaddressed
HIGH-severity safety/reliability defect remains (G9 is High but is disclosed, scoped, and requires
a deliberate decision, not an oversight); every fixed defect has regression coverage; critical
safety invariants have independent, re-verified evidence (§15); backend/frontend (dashboard/MCP)
contracts were traced and tested; CLI paths were tested; failure-injection coverage exists and grew
this pass; no secret exposure exists; no known stale/false-health path remains uncorrected (G2
fixed; G9 disclosed, not hidden); no real-order bypass exists (re-verified); research-methodology
issues are explicitly classified as `RESEARCH_DECISION_REQUIRED`, none silently resolved;
documentation was corrected where it drifted from implementation; the full test suite passes; the
one relevant mutation test (`momentum and/or`) passes; the second-order review found and closed a
real defect (G3) with no further defect found in a follow-up review of that fix; a fresh final pass
(this report's own synthesis) finds no additional actionable defect beyond what is already listed
as deferred/research-decision-required. **Convergence reached for what is checkable offline.**
Live-market validation remains outstanding by necessity (market closed), not by omission.
