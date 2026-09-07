# Live System Hardening — Final Report

**Update (same day, continuation session): EXECUTION SAFETY + REAL MARKET
INTELLIGENCE HARDENING mission.** Sections 1–13 below are the original
report, unchanged. This update adds Part II, covering five further
commits landed the same day after market close: wiring the deterministic
critic into `paper-live`, threading real benchmark context into
`shadow-run`'s critic call, dashboard visibility for connection/
staleness health, a real corporate-actions provider, and a deterministic
event-risk assessment module. See Part II's own executive verdict for
the updated picture — it does not repeat Part I's findings, only what
changed.


Continuous, adversarial audit-and-fix session against the live Dhan
paper-trading pipeline, conducted with real credentials during a real
NSE session (2026-09-07, Monday). Every claim below is labeled by its
actual evidence category — REAL LIVE DATA, REAL API TEST, INTEGRATION
TEST, UNIT TEST, or CODE INSPECTION — never blended. This report
supersedes nothing in `docs/LIVE_MARKET_READINESS_REPORT.md` or
`docs/LIVE_MARKET_VALIDATION_REPORT.md`; it extends them with what this
session found, fixed, and proved.

**Absolute constraint restated**: paper trading only. No code path in
this repository can place a real order — verified again this session via
`tests/test_dhan_no_real_orders.py`/`tests/test_broker.py`, run clean
before every commit below. No credential value was ever printed or
logged.

## 1. Executive Verdict

Three separate trust scores — never combined into one misleading grade,
per this mission's own instruction.

- **PLATFORM TRUST: B — MOSTLY RELIABLE, KNOWN LIMITATIONS.** The core
  pipeline (live data → strategy → risk → human/auto approval → paper
  execution → reconciliation) is solid, real, and now meaningfully
  better-instrumented than at session start. What keeps this from an A:
  the deterministic critic never runs in the interactive `paper-live`
  path at all, market-regime context is computed but wired into nothing,
  no automatic data-source fallback exists, and Dhan reconnect logic —
  while thoroughly unit-tested — was not observed against a genuine live
  disconnect this session.
- **DATA TRUST: C — WORKING BUT SIGNIFICANT GAPS.** Live Dhan price data
  is real and, as of this session, properly layered (raw tick →
  last-known-price → partial candle → completed candle, each honestly
  labeled). Clock skew is real, measured, persisted, and now visible —
  but still uncorrected (an environment issue this session deliberately
  did not fix itself). Corporate-action and regulatory data do not exist
  in this codebase at all; market context (news, sector, regime) is real
  but narrow (Yahoo-only) and largely disconnected from any live
  decision.
- **STRATEGY TRUST: F by design — NO DEMONSTRATED EDGE.** This is the
  settled, correct scientific answer from the prior research mission
  (`docs/STRATEGY_EDGE_DISCOVERY_FINAL_OUTPUT.md`), reaffirmed, never
  revisited or gamed this session. An F here is success, not failure —
  it is what an honest audit is supposed to produce when no edge exists.

## 2. Before vs. After (this session)

| Area | Before | After | Evidence |
|---|---|---|---|
| Clock skew visibility | CLI-only (`readiness-check --deep`); dashboard had zero awareness | Measured, persisted (`live/state_store.py`'s new `clock_skew` table), rendered on the dashboard with staleness-awareness | REAL LIVE DATA: `-129.8s`, `FAIL`, rendered end-to-end through the real dashboard function against a real persisted row |
| Sub-candle live price | `CandleBuilder._last_known_price` existed internally, unreachable from outside the class | `DhanMarketDataSource.last_known_price(symbol)` — a real, public, tested accessor | REAL LIVE DATA: returned a genuine live tick (1310.90) with its real exchange timestamp |
| Partial (in-progress) candle | `CandleBuilder.flush()` existed but was unused in production and mislabeled identically to a completed candle | `OHLCVBar.is_partial` field (additive); `flush()` now correctly marks `is_partial=True`; exposed via `DhanMarketDataSource.partial_candle(symbol)` | REAL LIVE DATA: real OHLC-so-far, correctly labeled; a repeated peek proved zero side effects on the real candle-building pipeline |
| Risk-halt visibility | Raw numbers shown with limits, no explicit "halted now" signal separate from the kill switch | New dashboard banner reusing `risk.engine.RiskEngine.account_level_halt_reasons()` (pre-existing, already-tested logic) | INTEGRATION TEST (HTTP-level) + UNIT TEST (direct call) |
| Traceability consistency | `/intelligence`'s journal showed `decision_id`; the main `/` page's journal did not | Both pages now show it, via one de-duplicated helper | UNIT TEST |

Test count: **1531 → 1561** (last full regression at 1560 passed, 0
failed; one further test added in the final, small, targeted-only commit
below — see that commit's own reasoning for why a full regression wasn't
re-run for it), across the 4 commits
listed in the table above (`01078be`, `4700105`, `b21c286`, `a20b0b1`),
each preceded by either full regression (for changes touching
persistence/live-data internals) or targeted+affected-subsystem tests
(for small, purely-additive dashboard changes) — the calibration this
mission's own Part 12 asked for. Safety suite green at every commit.

## 3. Real Market Evidence (today, 2026-09-07, all REAL LIVE DATA / REAL API TEST unless noted)

- Dhan REST connectivity: `[PASS]`, real HTTP 200 from `/fundlimit`, ~0.28s round-trip, measured independently 3 times across the session (each also doubling as a clock-skew measurement, below).
- Clock skew: **-130.0s, -129.8s, -130.3s** across 3 independent real measurements today (readiness-check --deep; a bounded live-price verification run; the extended paper-live session's own startup measurement, confirmed via its persisted `measured_at` timestamp matching that session's real start time) — consistent with the -129.5s/-130.3s/-130.6s range a prior session on this same machine also observed. Stable and reproducible, not noise. Root cause (confirmed via `w32tm /query /status`, already documented): Windows Time service has never synced to NTP on this machine. Remediation is the user's own action, never executed by this session: `w32tm /resync` as Administrator, or enable "Set time automatically" in Windows Settings.
- WebSocket: `[PASS]`, real `CONNECTED` state, sustained across every session run today with zero unexpected drops observed.
- `last_known_price("RELIANCE.NS")`: real tick, `1310.9000244140625` at `2026-09-07T07:56:45Z`.
- `partial_candle("RELIANCE.NS")`: real OHLC-so-far, `is_partial=True`, `source=DHAN`, `status=LIVE` — correctly distinguishing settlement state from provenance.
- Extended `paper-live --source dhan --auto-approve` session: 13:33:21–15:27:47 IST, 100 real bars processed, clean shutdown, zero anomalies beyond one correctly-triggered freshness suppression — full tally in §12.

## 4. Data Reliability — the six-category truth audit

See the full table produced mid-session (reproduced here for the
permanent record):

| Category | Have it? | Source | Live in decisions? | Fallback? |
|---|---|---|---|---|
| A. Live price | Yes | Dhan WebSocket (real-time); Yahoo (labeled `HISTORICAL`, never claimed live) | Yes (Dhan, for `paper-live`) | None exists |
| B. Market structure | OHLC only, honestly | Dhan Ticker packets — no volume field in Ticker mode, reported as real `0.0`, never fabricated | Yes (OHLC) | — |
| C. Corporate actions | **No** | — | No | — |
| D. Regulatory | **No** | — | No | — |
| E. News/events | Company-level only | `yfinance`'s `Ticker.news`, verified against a real call | Only via manual `research summarize`, not wired into trading | None |
| F. Market context | Partial | `market_intelligence/regime.py`, real Yahoo-sourced computation | **No** — confirmed by reading the call sites: `shadow-run`'s critic call never passes `benchmark_context`; `paper-live` has no critic at all | — |

No exchange-grade NSE/BSE claim is made anywhere in this codebase or
this report. Dhan is a real broker's own feed, not the exchange
directly; `.NS`/`.BO` symbol suffixes are Yahoo's routing convention,
not evidence of exchange-grade data — this was true before this session
and remains true now.

## 5. Pipeline Reliability

Tick → `CandleBuilder` → completed candle → `StreamingSnapshotAdapter` →
strategy → risk → (critic, `shadow-run` only) → approval → paper
execution → reconciliation: every stage in this chain has real test
coverage and, for the Dhan-sourced half, real live evidence gathered
either this session or the immediately preceding one. The tick-rejection
defenses (`non_positive_price`, `negative_volume`,
`implausible_deviation`, `late_out_of_order`, `implausible_timestamp`)
have real live-wire test coverage; on real market data specifically,
zero rejections have been observed across every live session run to
date — the real feed has been clean, so these five tick-level defenses
remain unit-proven against adversarial input, not live-proven, honestly
stated. The separate freshness/staleness gate (`FreshnessPolicy`, a
different defense from the five tick-rejection reasons above) *was*
observed firing live this session — see §12's `STALE_SIGNAL_SUPPRESSED`
event — genuinely PROVEN, not just unit-tested, for that specific gate.

Reconnect-on-disconnect: extensive, real unit coverage (bounded retry,
flapping-connection handling, stale-generation-race prevention, all
against a fake transport reproducing real Dhan wire behavior) — but no
genuine live disconnect occurred naturally this session or the prior
one, and this session did not attempt to force one against the real
broker feed (unsafe/unreliable to script). **PARTIALLY PROVEN**, stated
as such, not overstated.

Automatic fallback (Dhan → Yahoo or any other source): **does not
exist** anywhere in `live/` (confirmed by an exhaustive grep, zero
matches). This is the safer default — disconnection is reported as
`DISCONNECTED`/stale, never silently masked by a provenance swap — but
it is an absence, not a hidden capability, and is stated as such.

## 6. Safety Validation

- Kill switch: real activate/persist/reset drill proven in the prior
  session; confirmed `INACTIVE` at every readiness check this session.
- Risk engine circuit breakers (`max_daily_loss`, `max_drawdown`,
  `consecutive_loss_hard_limit`): pre-existing, well-tested logic, now
  also surfaced on the dashboard as a dedicated RISK HALT banner
  (this session's own addition) distinct from the kill switch.
- Deterministic critic: real, deterministic, no I/O, no LLM — verified
  by reading its own module docstring and implementation, not assumed
  from its name. **Confirmed absent from the entire `live/` directory**
  — it protects `shadow-run` only, by default, and is never consulted by
  `paper-live`, including under `--auto-approve` (unattended operation
  with neither a human nor the critic in the loop — flagged, not fixed,
  since deciding whether/how to add it changes what can gate a trade).
- No real-order code path exists anywhere in this codebase — reconfirmed
  by the safety test suite passing at every commit this session.

## 7. Observability

`decision_id` is reused (not reinvented) as the single correlation key
across `Decision → Signal → JournalEntry → PredictionRecord`, proven
with a real live 3-way join in the prior session and now visible on
*both* dashboard journal views (this session closed the inconsistency
between them). `rejected_tick_counts_by_symbol()` gives real, queryable,
per-reason bad-tick counts. Clock skew now carries its own
"measured at" timestamp, so staleness of the measurement itself is
honest, not just staleness of the underlying data.

No latency instrumentation exists anywhere in the pipeline (tick-received
→ candle-completed → signal-generated → risk-evaluated timing is not
measured at any stage — confirmed by search). Noted rather than built:
this strategy trades 1-minute candles, not sub-second moves, so latency
in the hundreds-of-milliseconds-to-seconds range this pipeline actually
operates in has no material bearing on correctness or safety for this
specific system — building instrumentation for it now would be effort
disproportionate to its value here, not an oversight.

Gap found this session: when the critic *does* run (`shadow-run` only),
its per-check HARD/SOFT breakdown is tallied into an in-memory
run-level summary but never persisted per-decision alongside the
journal entry — an operator can see "3 REJECTED today" in aggregate but
not, for one specific trade, exactly which check failed.

## 8. Silent Failure Audit

Every "do not fabricate" boundary checked this session held under
inspection: Yahoo bars are labeled `HISTORICAL`, never `LIVE`; a tick
with no volume field reports real `0.0`, never an estimate; an absent
`feed_status`/`clock_skew` row renders as an explicit "never
measured"/"no data" state on the dashboard, never a fabricated default;
a partial candle is now impossible to mistake for a completed one
(`is_partial`); the AI explanation layer is structurally incapable of
altering a trade parameter and is labeled, verbatim, "LLM narration —
not the decision basis" wherever it appears. No new silent-failure mode
was introduced by this session's changes — each new capability
(`last_known_price`, `partial_candle`, risk-halt reasons, clock skew)
returns an explicit `None`/empty state rather than a fabricated value
when nothing real is available, matching the codebase's own established
discipline.

## 9. News / Market-Intelligence Capability Matrix

See §4 above (categories C–F) — this *is* the matrix the mission asked
for, and duplicating it here would only invite drift between two
copies.

## 10. Remaining Risks

**P0** — none newly found this session that touch real-money risk (there
is no real-money path to touch). The highest-severity *architectural*
item is the critic/regime disconnection from live decision paths (§4,
§6) — real, but bounded by the fact that paper trading has no financial
consequence.

**P1**:
1. Decide, deliberately, whether `paper-live` should gain a critic
   check (at minimum under `--auto-approve`, where neither a human nor
   the critic currently reviews a signal).
2. Wire `benchmark_context` into `shadow-run`'s existing critic call —
   mechanically small (the check is `WARNING` severity, cannot newly
   reject a trade), but requires a real decision about how `shadow-run`
   should economically source a benchmark's data on every invocation.
3. Persist per-decision critic detail, not just the run-level tally.
4. Confirm Dhan reconnect behavior against a genuine live disconnect
   when one naturally occurs (do not force one artificially).

**P2**:
1. REST-connectivity status on the dashboard, alongside the
   already-shown WebSocket state (same persistence pattern as clock
   skew would work here).
2. A distinct "RISK HALT" banner exists now; consider whether the same
   treatment belongs on `decision_detail_page`, not just the index page.
3. **Real operational trap found this session**: `paper-live`'s stdout is
   block-buffered (Python's default when output is redirected to a file
   rather than a TTY) — running it as `paper-live ... > session.log 2>&1`
   for background monitoring can leave the log file looking frozen for
   many minutes while the process is genuinely healthy and actively
   processing real bars (verified: the log file showed only the startup
   banner for over 15 real minutes while `feed_status`, queried
   independently from the real SQLite state, was advancing normally the
   whole time; the underlying process's CPU time was also visibly
   incrementing). An operator relying on a tailed log file alone, without
   also checking the persisted state, could mistake a healthy session
   for a hang. `python -u` (or `PYTHONUNBUFFERED=1`) fixes this for
   anyone redirecting output for monitoring; not changed in the codebase
   itself this session since it's an invocation-time concern, not a bug.
4. The `analyze` command's "RISK ANALYSIS"/"CRITIC" section headers
   share names with the real deterministic `risk.engine`/`critic.engine`
   modules — a cosmetic clarity gap, not a safety issue (confirmed via
   import-graph analysis: `analyze` is completely isolated from the real
   trading path).

## 11. Honest Trust Score

Restated from §1 for completeness — PLATFORM: B, DATA: C, STRATEGY: F
by design. None of these three numbers should ever be averaged into a
single figure; they answer different questions for different audiences
(an engineer asking "is the code reliable," a researcher asking "is the
data trustworthy," and a trader asking "does this make money" each need
a different one of these three answers, not a blend).

## 12. Live Session Final Tally (REAL LIVE DATA)

The extended `paper-live --source dhan --auto-approve` session ran
13:33:21–15:27:47 IST (~114 real minutes, essentially the rest of
today's NSE session) against real production state
(`data/live_sim_trading.db`, `data/live_state.db`), RELIANCE.NS, 1m
interval, bounded to 100 bars.

- **100 bars processed**, real prices throughout: opened around
  ₹1310, ranged roughly ₹1303.60–1310.90 across the session, closed
  around ₹1308.
- **Zero signals generated.** Not forced, not manipulated — the
  strategy's own deterministic entry conditions simply never qualified
  during this real window. This is itself honest evidence, directly
  consistent with the settled NO DEMONSTRATED EDGE finding: a real
  ~114-minute live session produced no trade, and that is reported
  plainly rather than treated as a shortfall to explain away.
- **One real, live-observed `STALE_SIGNAL_SUPPRESSED` event** on the
  final bar (`fresh=False`) — confirmed by reading `live/pipeline.py`'s
  own logic: this means the freshness gate rejected the bar *before*
  `strategy.generate_signal()` was ever called, exactly the
  "never trade on stale data" behavior this gate exists for, firing
  correctly under real, naturally-occurring conditions (most likely a
  genuine quiet stretch in tick arrival near the end of the session,
  not a bug — the ~13-minute gap between this bar's own timestamp and
  the process's eventual clean shutdown is consistent with that).
- **Account**: cash and equity both closed at ₹100,000.00 (unchanged —
  no trade occurred), zero drawdown, zero consecutive losses.
- **Reconciliation: OK.** No corruption, no drift between the store and
  the in-memory account.
- **Kill switch**: confirmed `INACTIVE` throughout and after.
- The process shut down cleanly via its own `finally: source.close()`
  path — no crash, no hang, no manual intervention needed.

This is the single longest continuous real live-Dhan paper-trading
session run in this project to date, and it completed with zero
anomalies beyond the one freshness-gate event described above, which is
itself a positive proof point, not a defect.

## 13. Final Answer

The platform is genuinely more trustworthy today than it was at this
session's start — not because problems were hidden, but because more of
them are now visible where an operator will actually see them (the
dashboard) rather than only in a CLI flag an operator has to remember to
pass. Today's real, ~114-minute live paper-trading session ran end to
end with zero anomalies, produced zero trades because none were
genuinely warranted (not because anything was forced or suppressed
incorrectly), and its one notable event — a real freshness gate firing
on real data — is a demonstration of the platform doing exactly what it
should, not a defect. The strategy remains unproven and is not claimed
otherwise; today added a real data point of "ran cleanly, found nothing
to trade," which is consistent with, not contradictory to, the settled
NO DEMONSTRATED EDGE finding. The gaps that remain (critic/regime
disconnection from live paths, unproven live reconnect, no automatic
fallback) are named, evidenced, and scoped — not fixed today, because
fixing some of them (the critic wiring in particular) changes what can
gate a real decision, and that is a choice for the user to make
deliberately, not one to make unilaterally under time pressure. If the
system cannot yet be fully trusted in those specific, named ways, this
report says so plainly rather than implying otherwise.

---

# Part II — Execution Safety + Real Market Intelligence Hardening

Continuation, same day, after market close (NSE closed 15:30 IST; this
work is entirely offline — no live Dhan session was open while it was
built). Verified against actual repository state before touching
anything, per this mission's own explicit instruction, not against
memory of the prior session.

## 14. Executive Verdict (Part II)

- **PLATFORM TRUST: B+ — MOSTLY RELIABLE, ONE NAMED GAP CLOSED.** The
  single most consequential finding from Part I — `paper-live
  --auto-approve` could execute unattended with risk.engine as the only
  gate — is now closed. The critic runs by default for `--source dhan`
  and independently re-examines every live-generated BUY signal against
  real scanner and market-context evidence before risk sizing even runs.
  Not a full letter grade jump to A: the critic's rule set is exactly
  what Part I already knew (kill switch, duplicate exposure, structure,
  evidence completeness, regime conflict, ...), and event risk — a real,
  tested, new capability — is deliberately not yet wired into anything
  that can block a trade.
- **DATA TRUST: C — unchanged from Part I.** Nothing about live price
  data changed this session; the connection-state richness fix and
  dashboard health composite are visibility improvements over the same
  underlying data, not new data.
- **STRATEGY TRUST: F by design — unchanged, untouched.**
- **MARKET INTELLIGENCE TRUST: C — WORKING BUT SIGNIFICANT GAPS (new
  grade, per this mission's own instruction to report it separately).**
  Real progress from a standing start: corporate actions (dividends,
  splits, forward earnings estimate) and India VIX are now confirmed,
  live-verified, available through the same `yfinance` dependency this
  project already trusts — zero new external risk. But NSE/BSE bulk &
  block deals, ASM/GSM surveillance status, and SEBI regulatory
  circulars remain entirely unavailable (no fabricated substitute was
  built for any of them), and none of what IS now available — corporate
  actions, event risk, benchmark regime — reaches a real paper-trading
  decision yet except benchmark regime via the critic's own
  `REGIME_CONFLICT` check.

These four scores are reported separately, as before, and must never be
averaged into one number.

## 15. What Was Found

1. **`LiveSimPipeline` never constructed a `decision_engine.models.
   Decision` at all** — confirmed by reading `live/pipeline.py` before
   changing it, not assumed from Part I's own summary. It calls
   `strategy.generate_signal()` directly; no scanner evidence, no
   `decision_engine`-shaped market context, nothing `critic.engine.
   evaluate()` requires ever existed on that path.
2. **`decision_engine.rules.classify()`'s label is independent of any
   live strategy's own signal** — it derives BUY/WATCH/AVOID/NO_ACTION
   purely from scanner `candidate`/`risk_context`. Calling
   `decision_engine.engine.make_decision()` from inside the live
   pipeline could have silently produced a DIFFERENT label than the BUY
   the live strategy already, separately decided — and
   `critic.engine.evaluate()` raises if `label != BUY`. This is why
   `live/critic_gate.py` builds its `Decision` directly instead.
3. **Scanner evidence requires its own historical fetch**, incompatible
   with per-live-tick computation (confirmed by reading `market_intelligence.
   scanner._screen_symbol`, which calls `provider.fetch_ohlcv` itself,
   ignoring whatever indicator series the caller already has) — this is
   why `CriticGate` refreshes evidence on a bounded 15-minute timer
   rather than every bar.
4. **`shadow-run`'s own critic call never passed `benchmark_context`**,
   despite the parameter existing since the critic was first built —
   confirmed by reading the exact call site, not inferred.
5. **`LiveSimPipeline` only ever asked `is_connected()` (a bool)**,
   collapsing a richer connection state some sources track internally
   down to CONNECTED/DISCONNECTED before it ever reached `feed_status`
   or the dashboard.
6. **NSE, BSE, and SEBI have no officially-documented, self-service
   developer API** for corporate announcements, bulk/block deals,
   ASM/GSM surveillance status, or regulatory circulars — real web
   research (not assumption), confirmed the same conclusion from three
   independent searches: official access, where it exists at all, runs
   through licensed data vendors, not a public endpoint. NSE/BSE do
   publish some of this on their own public web pages, which is a
   different, higher-risk category (no documented terms for
   programmatic access) this project has consistently declined to
   scrape, and continues to decline.
7. **`yfinance` — already a direct dependency this project trusts for
   price history, news, and sector data — exposes real dividend
   history, split history, a forward earnings-date estimate, AND India
   VIX (`^INDIAVIX`)**, all confirmed via real, live calls against this
   project's own existing `YahooFinanceProvider`/`yf.Ticker`, not
   assumed from documentation.
8. **The critic's assessment is persisted for rejected signals but not
   for approved ones** passing through `paper-live` — the trade itself
   stays fully traceable via existing `decision_id`/`signal_id`
   machinery; the critic's own specific verdict for that one trade
   simply isn't additionally persisted. A real, minor, honestly-named
   gap, not a broken chain.
9. **The learning/promotion pipeline is genuinely human-gated** —
   verified by reading `learning/adaptation.py` and its one real caller
   in `main.py` directly: `compare_and_recommend` never touches any
   config file, is reachable only through a manual CLI command
   (`experiment recommend`) requiring explicit human-supplied experiment
   IDs, and prints "ADVISORY ONLY, NO CONFIGURATION IS CHANGED". The
   scheduler never calls it (confirmed: zero references in
   `scheduler/runner.py`).
10. **Clock-skew consequences separate cleanly into two categories**:
    comparisons entirely within the local clock (age calculations,
    internal lifecycle durations, dashboard "Data Age") are self-
    consistent and immune to skew, since both sides of the comparison
    share the same bias. Skew only matters where a local timestamp is
    compared against something external — confirmed one concrete,
    previously-undocumented instance: `scheduler/runner.py`'s `run_tick`
    uses real local wall-clock time (`datetime.now(IST)`) against a
    configured schedule, so a scheduled run fires ~130s late relative to
    the operator's real-world intent. Candle boundaries are provably
    unaffected (bucketing uses the tick's own exchange timestamp, never
    local receipt time — unchanged from Part I's own finding).

## 16. What Was Actually Broken

- The core gap this mission was created to close: `paper-live
  --auto-approve` could run fully unattended with `risk.engine` as the
  only gate between a live-generated signal and a real (paper) order —
  confirmed, then fixed (§17).
- A real bug in the new event-risk module, caught by its own test suite
  before commit, never shipped: the `UPCOMING_EARNINGS` check hardcoded
  `UNKNOWN` when corporate-actions evidence was unavailable, ignoring
  the caller's own configured `treat_missing_corporate_actions_as`
  policy — inconsistent with the sibling `CORPORATE_ACTIONS_AVAILABILITY`
  check, which respected it correctly. Fixed same-session; both checks
  now honor the same policy.

## 17. What Was Fixed (5 commits, `74b1846` → `d34c3e0`)

| # | Commit | What | Evidence |
|---|---|---|---|
| 1 | `74b1846` | `shadow-run` now computes real `benchmark_context` once per run and passes it into the existing critic call | INTEGRATION TEST: a new test forces a real (fake-provider) benchmark fetch and confirms `REGIME_CONFLICT` flips from "not evaluated" to evaluated |
| 2 | `498e18f` | `live/critic_gate.py` (new) bridges `LiveSimPipeline`'s live signals to `critic.engine.evaluate()` with real, independently-fetched scanner/market-context evidence; wired into `paper-live` by default for `--source dhan` (`--skip-critic` opts out); a blocking verdict (REJECT/INSUFFICIENT_EVIDENCE) prevents any paper order and is persisted (new `critic_rejections` table) and shown on the dashboard | UNIT TEST (9 tests against real `run_scan`/`compute_benchmark_context` with a fake provider) + INTEGRATION TEST (5 tests proving the pipeline wiring blocks/passes correctly) + full regression (1589 passed) |
| 3 | `f119a65` | `LiveSimPipeline._connection_state_label()` surfaces a richer connection state when a source exposes one (soft capability check, zero effect on sources that don't); dashboard's new `_data_health_label()` composes CONNECTED/DEGRADED/STALE/RECONNECTING/DISCONNECTED/SOURCE_UNAVAILABLE from existing `feed_status` fields, display-only, honestly documented as an approximation | UNIT TEST (7 tests covering every state + boundary conditions) + full regression (1596 passed) |
| 4 | `100e3d7` | `market_intelligence/corporate_actions.py` (new): real dividend/split/earnings-estimate data via `yfinance` | UNIT TEST (6 tests, fake `yf.Ticker`) + REAL LIVE DATA (verified against RELIANCE.NS: real 2024/2025/2026 dividends, real splits, real 2026-10-16 earnings estimate) |
| 5 | `d34c3e0` | `market_intelligence/event_risk.py` (new): deterministic ALLOW/CAUTION/BLOCK/UNKNOWN assessment from corporate-actions evidence, policy-configurable, never silently treats missing evidence as safe | UNIT TEST (13 tests, one real bug found and fixed before commit) |

## 18. What Was Deliberately Not Fixed

- **Event risk is not wired into `live/critic_gate.py` or `paper-live`'s
  blocking path.** `paper-live` already gained one new blocking layer
  (the critic) this session, with its own dedicated regression cycle.
  Adding event risk as a *second* new blocking layer to live execution
  in the same pass — on a still-narrow rule set, since Part 4's own
  audit found only earnings-date proximity as a real, reliable,
  forward-looking signal — was deferred rather than rushed. The module
  is complete, real, and tested; wiring it in is a small, well-defined
  follow-up, not a redesign.
- **India VIX is not wired into `market_intelligence/regime.py`'s
  volatility read.** Confirmed real and fetchable; `compute_benchmark_context`
  still derives `volatility_regime` from the trend-benchmark's own ATR,
  not a direct VIX read. A genuine design choice (which volatility
  measure to trust more, and how to combine them) deserves more
  consideration than this session had budget for — documented, not
  hidden.
- **Bulk/block deals, ASM/GSM surveillance, SEBI circulars, and official
  NSE/BSE announcements remain entirely unbuilt.** No real,
  officially-sanctioned, low-risk source was found for any of them this
  session. `market_intelligence/event_risk.py`'s own docstring states
  this explicitly: a future check for any of these categories should
  raise the same honest "not evaluated" this module already uses for
  corporate actions, never invent a verdict from nothing.
- **The critic's assessment is not persisted for approved signals**,
  only rejected ones (§15, item 8) — the safety-critical case is fully
  covered; extending persistence to the approved case is a nice-to-have,
  not a blocking traceability failure, and was not built to keep this
  session's scope from creeping into a fourth new table.
- **`FreshnessPolicy`'s own enforcement threshold was not changed.** The
  dashboard's new DEGRADED/STALE distinction is display-only, explicitly
  documented as an approximation (feed_status does not record which
  interval a symbol runs at) — it does not become a second, competing
  gate against the one that already exists and is already proven live
  (§12's own `STALE_SIGNAL_SUPPRESSED` event, Part I).

## 19. What Remains Unproven

- **The critic in `paper-live` has not yet been exercised against a real
  live Dhan session.** Built, unit-tested, integration-tested, and
  regression-clean — but the market was closed (15:30 IST) before this
  work landed. Genuinely PARTIALLY PROVEN, not PROVEN, stated as such.
- **The richer connection-state surfacing has only been proven with a
  simulated `RECONNECTING` value** (a real capability the mock source
  does not naturally have, set directly on the test double) — not yet
  observed from an actual Dhan reconnect event, for the same reason (no
  live session ran after this landed).
- **The corporate-actions provider and event-risk module have real live
  verification for their own data fetch** (§17, row 4) but have never
  been exercised end-to-end inside an actual live paper-trading loop,
  since neither is wired into one yet.

## 20. Test Results

1561 → **1615 passed, 0 failed** across the 5 commits in §17, full
regression clean at the two commits that touched the live execution
path (critic gate: 1589 passed; connection-state/dashboard: 1596
passed) and a final milestone full regression after all five landed
(1615 passed, exactly matching total test collection — nothing skipped,
nothing uncounted). Safety suite (`test_dhan_no_real_orders.py`,
`test_broker.py`) green at every commit.

## 21. For the Next Live Market Session

Per this mission's own instruction: do not force trades, do not loosen
thresholds to generate activity. A successful validation can legitimately
produce zero signals and zero trades — that remains valid evidence.
Specifically capture, with real evidence:

- Does `paper-live --source dhan` print `DETERMINISTIC CRITIC: ACTIVE`
  at startup, and does a real critic evaluation actually occur for any
  signal the live strategy generates?
- If a signal is critic-rejected, does it appear correctly in the
  dashboard's CRITIC REJECTIONS table with a real, accurate reason?
- If a signal passes the critic and proceeds, does the rest of the
  chain (risk → approval → paper execution) work exactly as it did
  before this session, unaffected?
- Does `feed_status.connection_state` show a real, richer value (not
  just CONNECTED/DISCONNECTED) if any connection hiccup occurs, and does
  the dashboard's Data Health column reflect it correctly?
- Does the deep readiness check / session startup still correctly
  measure and report clock skew, unaffected by any of this session's
  changes?

## 22. Final Answer — the Mission's Own Nine Questions

1. **Can the platform safely operate as an autonomous PAPER trading
   system?** More safely than at the start of this mission: unattended
   `paper-live` now has a real, independent, deterministic check before
   risk sizing, not just risk.engine alone. Not fully proven yet — the
   critic has no live-session evidence behind it.
2. **Can it receive and correctly distinguish real-time market data,
   live price, partial candles, and completed candles?** Yes — proven in
   Part I, unchanged this session.
3. **Can it safely degrade when live data fails?** The real enforcement
   (no new signals on stale data, bounded reconnect) was already real
   and proven in Part I. This session added honest, better-labeled
   operator visibility into that same degradation — not new enforcement.
4. **Does every unattended paper trade pass deterministic critic +
   market context + risk controls?** For `--source dhan` without
   `--skip-critic` (the default): yes, structurally, as of this session
   — pending live confirmation. Market context reaches the critic via
   `REGIME_CONFLICT`; event risk does not yet reach any decision.
5. **Does the system understand relevant market context rather than
   only symbol-level candles?** More than at the start: benchmark regime
   now reaches the critic in both `shadow-run` and `paper-live`. Still
   narrow: no sector, breadth, or India-VIX-derived signal reaches a
   real decision yet.
6. **Does it have a reliable architecture for NSE/BSE/SEBI/corporate/
   event intelligence?** Partially, and honestly scoped: corporate
   actions and India VIX, yes, via a source this project already trusts.
   Regulatory/surveillance/bulk-deal intelligence: no real source
   exists, and none was fabricated.
7. **Can every paper trade be traced from market data to final
   evaluation?** Yes, for the core chain (decision_id/signal_id through
   to JournalEntry/PredictionRecord, proven in Part I). One honest gap:
   critic assessments for approved (non-rejected) live-pipeline signals
   aren't additionally persisted.
8. **Is learning measurement-driven rather than uncontrolled self-
   modification?** Yes, verified directly in this session's own code
   reading, not just trusted from a docstring — promotion is manual,
   advisory, and never touches configuration.
9. **What remains unsafe, unproven, or incomplete?** Named precisely in
   §18 and §19 above, not summarized away: event risk unwired, India VIX
   unwired, three whole intelligence categories genuinely unavailable,
   and the critic/connection-state work awaiting its first real live
   session.
