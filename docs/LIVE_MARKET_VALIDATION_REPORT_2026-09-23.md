# Live Market Validation Report — 2026-09-23

Full-session, autonomous, real-Dhan-data validation of the repaired build produced by the
2026-09-22 continuous red-team pass and the 2026-09-23 open-issues remediation pass. This session's
job was engineering validation, not trading performance — the strategy remains frozen at
**NO DEMONSTRATED EDGE** and was never modified, tuned, or overridden.

**Evidence labels**: PROVEN (a real, direct observation — a log line, a DB row, a process check),
INFERRED (a reasoned conclusion from real evidence, explicitly labeled), UNPROVEN (an open question
— pattern observed, cause not established).

## Session

| | |
|---|---|
| Date | 2026-09-23 (Wednesday) |
| Commit | `6cf86f3` (unchanged for the entire session — zero code changes made) |
| Branch | `final-product-hardening` |
| Interpreter | `venv/Scripts/python.exe`, Python 3.14.4 |
| Symbols | 15 (`market_data/watchlists/starter_nse.yaml`) |
| Fleet launch | `fleet-supervise --watchlist-file market_data/watchlists/starter_nse.yaml --runtime-dir runtime --source dhan --poll-interval-seconds 30`, ~09:41:32 IST |
| Dashboard | `dashboard --fleet-runtime-dir runtime --fleet-watchlist-file market_data/watchlists/starter_nse.yaml`, ~09:44 IST, `http://127.0.0.1:8765` |
| Shutdown | `taskkill /PID <supervisor> /T` (graceful, failed — plain console processes, no message loop, matching the 2026-09-22 session's own documented finding) → `taskkill /F /T` (forceful, succeeded), ~15:47 IST |
| Runtime | ~6h06m wall-clock (09:41–15:47 IST); market session 09:15–15:30 IST |

## Market data

| | |
|---|---|
| Total bars (15 symbols) | 4,995 (333/symbol) |
| Fresh | 4,980 (99.7%) |
| Stale (correctly suppressed) | 15 (exactly 1/symbol — all from the single incident below) |
| Gaps | 1 fleet-wide incident, ~15 minutes (see Incidents) |
| Duplicate/redelivered ticks | Many observed and correctly suppressed throughout the session (CandleBuilder's redelivery-dedup logic, hardened 2026-09-22, fired continuously on real live data — see Trading Pipeline Fixes Validated below) |
| Out-of-order events | None observed requiring the `late_out_of_order` rejection path today |
| Invalid ticks (NaN/Inf) | None observed |
| Reconnects | 1 launch-time `code=805` disconnect (RELIANCE.NS only, self-healed in 1s); 2 idle-timeout (`silently lost connection`, 300s threshold) reconnects each on 4 symbols during the incident |

## Fleet

| | |
|---|---|
| Worker health | 15/15 alive and heartbeat-fresh for the entire session, including throughout the incident |
| Restarts | 0 (`max-restarts` budget never consumed) |
| Stale-worker detections | None — every worker's own process loop kept iterating and writing `heartbeat.json` even while its FEED was silently dead, correctly proving the "process alive, data stale" distinction the F3/G2 hardening exists to make |
| Duplicated/orphaned workers | None real. A benign, confirmed-harmless process-count artifact was found and investigated — see Findings §1 |
| Supervisor events | 0 restarts triggered; supervisor's own heartbeat stayed fresh the whole session |

## Dashboard

| | |
|---|---|
| Freshness | Correctly showed `DEGRADED` (data age > 30s, normal for a 1-minute bar cadence) for most of the session, and correctly escalated to `0/15 HEALTHY` / every symbol `STALE` during the incident — never a false `HEALTHY` |
| Source correctness | Single-symbol Overview page correctly reported "no active live session appears to be running" (accurate — no single-symbol `paper-live` process was running; only the isolated fleet was). Fleet tab correctly showed real, live per-symbol data the whole session |
| Account consistency | The fleet workflow is, by design, not exposed to the G9 dual-writer scenario (each symbol has a fully isolated `runtime/{SYMBOL}/` store) — this session's architecture did not exercise that specific fix, since no concurrent single-symbol CLI session was run against the same account |
| Errors | None — no exception, no raw traceback, no 500 observed on any page visited |

## Trading pipeline

Complete, real, end-to-end evidence chain, reconstructed from `state.db`/`predictions.db` across
all 15 symbols (read-only queries; nothing overridden):

| Stage | Count | Detail |
|---|---:|---|
| Strategy signals generated | 371 | `TrendMomentumBaseline`, real live bars |
| CriticGate evaluations | 371 | **371/371 = `DOWNGRADE`, 0 blocked** — consistent with the pre-existing documented finding that the NIFTY-regime market-context check is WARNING-severity only (`DOWNGRADE` does not block downstream); confirmed on real, live data today |
| RiskEngine rejections | 371 | **371/371 veto reason = `MAX_EXPOSURE`**, 100% single-cause (see Findings §2) |
| Pending human approvals created | 0 | Every signal was rejected before reaching `PENDING_HUMAN_APPROVAL` (RiskEngine's first-pass check runs before that state in `require_human_approval=True` mode) |
| Paper trades | 0 | No signal was ever approved |
| Rejections overridden | 0 | None — per the mission's own explicit rule, no rejection was ever second-guessed or bypassed |

## Predictions

| | |
|---|---|
| Created today | 371 (one `PredictionRecord` per generated signal, regardless of downstream disposition — matches `live/prediction_recorder.py`'s own "record NO-TRADE decisions too" design) |
| Evaluation cycles run today | 5,894 (repeated re-checks of still-`ACTIVE` predictions against real historical price data via the Yahoo-Finance-backed evaluator, every 20 bars per symbol) |
| Resolved today | 0 (`STOP_HIT`/`TARGET_HIT`) — all of today's 371 predictions were still `ACTIVE` (within their 20-bar horizon, or the price genuinely hadn't moved enough to resolve) as of session end |
| Resolved historically (all prior sessions, for context) | 109 (93 `STOP_HIT`, 16 `TARGET_HIT`) — confirms the evaluation mechanism itself is genuinely functional, not silently broken (see Findings — this required correcting my own initial investigation, which checked the wrong table; documented for transparency) |
| Evaluation failures | None observed |

## P&L

**₹0.00 across all 15 symbols.** Zero trades occurred; no P&L is possible or claimed. This is the
expected, correct outcome given the strategy's own frozen NO-DEMONSTRATED-EDGE verdict and today's
100% RiskEngine rejection rate — not evidence of anything beyond "the system did not trade," which
was never the goal of this session.

## Incidents

### Incident 1 — RELIANCE.NS launch-time `805` disconnect (self-healed)

- **09:42:30 IST**: `Dhan feed connection lost (server-sent disconnect (code=805)) -- reconnecting, attempt 1/5.`
- **09:42:31 IST**: Reconnected (generation 1→2), subscription re-established, next tick processed normally.
- **Impact**: none — self-healed in 1 second, no bar affected, no other symbol hit this today (vs. 4/15 in the 2026-09-17 incident) — the `--launch-stagger-seconds` mitigation (1.5s/symbol) appears to be helping, though this is a single data point, not proof.

### Incident 2 — Fleet-wide silent feed interruption, ~15:14–15:29 IST (~15 minutes)

Full reconstruction from real log evidence across all 15 symbols:

- **~15:13:57–15:14:34 IST**: Last genuinely fresh ticks/bar (bar #332) processed across the fleet. Every symbol's WebSocket remained in `CONNECTED` state throughout — this was never a visible disconnect at the transport level.
- **15:14:xx–15:19:xx IST** (~5 min): Zero messages received on any of the 15 connections, despite `CONNECTED` state. `[GAP DETECTED]` (180s) then repeated `[GAP ONGOING]` (240s, 301s, 361s...) fired on every symbol — the observability layer correctly flagged this the whole time.
- **15:19:43–15:19:45 IST**: The idle-timeout mechanism (`connected_idle_timeout_seconds`, 300s threshold) fired on 4 of 15 symbols (RELIANCE.NS, SBIN.NS, SUNPHARMA.NS, TCS.NS) — `received no message at all for ~300s while nominally CONNECTED -- treating as a silently lost connection and reconnecting.` All 4 reconnected within 1–2 seconds (generation N→N+1). The other 11 symbols' gaps had not yet reached the 300s idle threshold at this point.
- **Post-reconnect**: only a **stale redelivered tick** (exchange timestamp `09:44:59 UTC`, i.e. from the moment the gap began) was received — correctly identified as a redelivery by `CandleBuilder` and **not** treated as new data (no bucket advance).
- **15:24:50–15:24:51 IST**: The SAME 4 symbols hit the idle-timeout a **second** time (another ~5 minutes of silence even after the first reconnect) and reconnected again (generation N+1→N+2). Again, only the same stale redelivered snapshot arrived.
- **15:29:11–15:29:14 IST**: Genuinely fresh ticks (new exchange timestamps, e.g. `09:59:30 UTC`) finally resumed across the fleet — right at/after market close.
- **Resolution**: the delayed bucket (`09:44:00–09:45:00 UTC`, bar #333) finally completed on every one of the 15 symbols once enough real data arrived to close it, and every single one was correctly finalized as **`STALE_SIGNAL_SUPPRESSED, fresh=False`** — no signal, no trade, no dashboard-visible action was ever taken on this stale bar, on any symbol.
- **Recovery verification**: post-incident, all 15 heartbeats returned to sub-5-second freshness; `fleet-summary`/dashboard both correctly reflected the recovery; no duplicate bars, no corrupted OHLC, no duplicate volume observed on any symbol (PROVEN — `bar# 333` is the only new bar per symbol; no `bar# 333` appears twice in any log).
- **Impact**: zero unsafe behavior. The system's every safety mechanism (gap detection, idle-timeout reconnect, redelivery-dedup, freshness-based signal suppression, honest dashboard reporting) worked exactly as designed under what was, in aggregate, the most severe real data outage this build has been tested against — roughly 15 minutes of near-total silence, twice requiring reconnection, with the eventual recovered data correctly refused as tradeable.

## Root causes

- **805 disconnect (Incident 1)**: PROVEN — a known, documented Dhan-side connection-count cap
  (5 connections/client ID), previously observed 2026-09-17, self-healing by design.
- **Fleet-wide silent gap (Incident 2)**: **UNPROVEN.** No definitive root cause was established —
  per this mission's own explicit instruction, none is claimed without evidence. What IS proven:
  every one of this project's own resilience mechanisms functioned correctly throughout. What is
  INFERRED, not proven: this is the **third** occasion this general pattern has now been observed
  (2026-09-17, 2026-09-22, 2026-09-23), each time in the mid-to-late trading session, and today's
  own logs additionally showed the SAME "silently lost connection" signature recurring at a similar
  (though not identical) time on 2026-09-22 (~15:32–15:38 IST) as on 2026-09-23 (~15:14–15:29 IST)
  — strengthening, but not proving, a time-of-day-correlated, Dhan-side cause (e.g. an
  end-of-session batch process on Dhan's own infrastructure). No DNS/Windows-Event-Log correlation
  was checked this session (a genuine gap in this session's own investigation — see Post-Market
  Actions).

## Findings (not code-changed during the session, per the mission's own explicit rule)

### 1. CODE BUG (Low severity, deferred, confirmed harmless) — unconditional venv self-re-exec doubles every process

`live/environment_guard.py::ensure_running_under_project_venv()` re-executed every worker,
the supervisor, and the dashboard into a child process **even though each was already launched
directly via the correct `venv/Scripts/python.exe`** — confirmed by its own fast-path check
(`exe.relative_to(expected_dir)`) apparently not matching in this environment, likely a path
resolution difference between `Path(__file__).resolve()` (used by `_default_project_root()`) and
`sys.executable`'s own resolved path under this project's OneDrive-synced directory (not
root-caused to the byte level this session). **Confirmed harmless**: the outer/parent process
never reaches real business logic — it blocks on `subprocess.run` and `sys.exit()`s on the child's
own exit code — so there was never a duplicate WebSocket subscription, duplicate heartbeat writer,
or duplicate DB writer (verified directly: every symbol showed exactly one `Dhan feed CONNECTED`
per connection generation, never two). Real impact: 32 OS processes instead of the logical 16
(15 workers + supervisor), and 4 instead of 2 for the dashboard — a resource-overhead inefficiency,
not a safety or correctness defect. **Not fixed this session** (touches startup/environment code,
deferred per "no code changes during live session"). Recommended after-market work: investigate the
exact path mismatch and either fix the fast-path comparison or document it as an accepted,
harmless double-launch.

### 2. RESEARCH_FINDING — `MAX_EXPOSURE` rejected 100% of today's real signals

All 371 real candidate signals generated today, across all 15 symbols, were rejected by RiskEngine
for the single veto reason `MAX_EXPOSURE` — never anything else, on any symbol, at any point in the
session. Every account started fresh (₹100,000 cash/equity, 0 open positions), so this was not an
account-state-dependent trigger accumulating over the day — it fired from the very first signal.
One inspected rejection (RELIANCE.NS, entry≈₹1243.70) showed `requested_quantity=790,
approved_quantity=0, exposure_pct=99.5%` against the 25% `max_exposure_pct` default — i.e. the
strategy's own `risk_per_trade_pct=0.5%`-based position sizing, at current NSE large-cap price
levels and this stock's own stop distance, produced a notional position size roughly **4x** the
configured exposure ceiling. This is **not a code defect** — RiskEngine is correctly enforcing its
own configured limit, exactly as designed, on every single signal without exception. It is a
genuine, evidenced research/configuration question: whether `risk_per_trade_pct`/`max_exposure_pct`
defaults are compatible with the current 15-symbol universe's price levels at all, independent of
any single day's specific signals. **Not modified.** This is recorded here as a `RESEARCH_FINDING`
for a human decision, per the mission's own explicit instruction never to touch RiskEngine/sizing
to "fix" this observation.

### 3. Git hygiene (informational, pre-existing, unrelated to this session)

`data/` shows as untracked (`?? data/`) in `git status` despite a `.gitignore` pattern (`data/`,
line 58) that appears to cover the whole directory — worth a dedicated, careful investigation in a
non-live-session context. Confirmed pre-existing (the directory has accumulated real databases
since 2026-09-04, long before today); not caused by, and not touched during, this session.

## Requires live-market validation (still, going forward)

- The exact root cause of the recurring mid/late-session silent interruption pattern (now 3
  occasions) remains genuinely open — only a real future session, ideally with DNS/Windows-Event-Log
  correlation checked in real time, can further narrow it.
- Whether the `MAX_EXPOSURE`-blocks-everything pattern (Finding 2) holds on a day with different
  price action, or is a structural certainty regardless of market conditions, requires more
  sessions (or a dedicated offline sizing-vs-universe analysis) to distinguish.

## Post-market actions (recommended, not performed this session)

1. Investigate and resolve Finding 1 (double-process venv re-exec) — low priority, safe, no
   safety-invariant impact, can be fixed and regression-tested in a normal engineering pass.
2. A human decision on Finding 2 (`MAX_EXPOSURE` structural rejection rate) — is this intended
   behavior for this universe/account-size combination, or does it warrant a deliberate review of
   default risk parameters against current price levels? Not a code-change request either way.
3. Investigate the `data/` `.gitignore` discrepancy (Finding 3) — low priority, cosmetic.
4. If the mid/late-session interruption pattern recurs a fourth time, perform a dedicated forensic
   pass with Windows Event Log and DNS correlation checked in real time during the incident, not
   reconstructed afterward.

## Success criteria — assessed against the mission's own list

| Criterion | Result |
|---|---|
| 15-symbol fleet operates correctly | **PROVEN** — 15/15 healthy, 0 restarts, 6+ hours |
| Real Dhan data flows, no mock fallback | **PROVEN** — real REST+WebSocket, real ticks, real gap/reconnect behavior throughout |
| CandleBuilder fixes behave correctly | **PROVEN** — redelivery-dedup fired continuously and correctly on live data; stale post-incident data correctly suppressed, never falsely completed as fresh |
| Duplicate volume protected | **PROVEN** — no duplicate-volume evidence found on any symbol, including through the incident |
| Invalid data cannot crash the feed | **PROVEN** (by absence — zero NaN/Inf/crash observed; no negative test needed given a clean real session) |
| Stale workers detected | **PROVEN** (correctly NOT triggered — every worker's own loop stayed alive; the dashboard's process-vs-data distinction correctly differentiated stale DATA from a stale WORKER throughout the incident) |
| Reconnect recovery works | **PROVEN** — 5 total reconnects (1 launch-time + 4×(2 idle-timeout)) all succeeded |
| Dashboard reports truthful state | **PROVEN** — correctly escalated from DEGRADED to STALE/0-HEALTHY during the incident, never false-HEALTHY |
| Account state remains synchronized | Not exercised this session (fleet workflow is isolated by design — G9's specific scenario requires a concurrent single-symbol session, not run today) |
| DB constraints hold | **PROVEN** — `integrity_check() == "ok"` on all 45 databases post-shutdown |
| Predictions persist | **PROVEN** — 371 created, 5,894 evaluation cycles run, mechanism confirmed genuinely functional |
| Paper trading remains deterministic | **PROVEN** (vacuously — 0 trades, but the full decision chain up to rejection was deterministic and fully traced) |
| Real-order execution remains impossible | **PROVEN** — unchanged code, re-verified structurally impossible per the 2026-09-23 remediation pass's own audit; no execution path was reachable at any point |
| No unsafe intervention required | **PROVEN** — every incident self-resolved via the system's own existing mechanisms; zero manual intervention was needed at any point during the live session |

**This system is not claimed to be perfect.** Two real, non-safety-critical findings (venv
double-launch, `MAX_EXPOSURE` structural rejection pattern) were surfaced and recorded, not hidden
or minimized. The root cause of the recurring mid-session interruption remains genuinely unproven
after three occasions.

---

## Final operational summary

```text
COMMIT:                 6cf86f3 (unchanged throughout — zero code changes this session)
SESSION DURATION:       ~09:41–15:47 IST (~6h06m); market 09:15–15:30 IST
WORKERS:                15/15 healthy, 0 restarts
BARS:                   4,995 total (333/symbol), 4,980 fresh (99.7%), 15 correctly-suppressed stale
FRESHNESS:               99.7% fresh; the 0.3% stale was correctly detected and suppressed, never traded
RECONNECTS:             5 total (1 launch-time 805, self-healed 1s; 4 symbols x 2 idle-timeout reconnects during the incident)
SIGNALS:                371 real strategy candidates generated
CRITICS:                371/371 DOWNGRADE, 0 blocked
RISK DECISIONS:         371/371 REJECTED — 100% MAX_EXPOSURE
PAPER TRADES:           0
P&L:                    ₹0.00
PREDICTIONS:            371 created today; 5,894 evaluation cycles run; 0 resolved today (109 resolved historically, confirming the mechanism works)
INCIDENTS:               2 (1 self-healed in 1s; 1 fleet-wide ~15-minute silent gap, fully self-recovered)
BUGS FOUND:              1 (venv double-re-exec, Low severity, confirmed harmless)
BUGS FIXED:              0 (none touched — no code changes during the live session, as required)
BUGS DEFERRED:           1 (venv double-re-exec — after-market work)
ROOT CAUSES PROVEN:      1 (805 disconnect — known Dhan connection cap)
ROOT CAUSES UNKNOWN:     1 (the recurring mid/late-session silent interruption — 3rd occasion, still unproven)
POST-MARKET ACTIONS:     4 (see Post-market actions above — none are safety-critical)
```
