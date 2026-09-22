# Live Market Validation Report — 2026-09-22

Fresh real-market NSE/Dhan paper-trading session. Purpose was strictly operational validation — the
research program is closed (59 OHLCV hypotheses + 4 derivatives hypotheses, all REJECTED / NO
DEMONSTRATED EDGE, commit `a8a2f9d`) and this session was not permitted to reopen it. No strategy,
risk, or configuration change was made at any point.

**Evidence labels used throughout**: REAL (observed directly from a live/real system), MECHANISM-
VERIFIED (proven correct by running the project's own code, not exercised live today), INFERENCE (a
reasoned conclusion from real evidence, not itself directly observed).

## 1. Session summary

| | |
|---|---|
| Date | 2026-09-22 (Tuesday, fresh NSE trading day) |
| Commit at start | `a8a2f9d`, `final-product-hardening` == `origin/final-product-hardening` == `main`, working tree clean |
| Universe | 15 symbols, `market_data/watchlists/starter_nse.yaml` |
| Fleet launch | `fleet-supervise --watchlist-file market_data/watchlists/starter_nse.yaml --runtime-dir runtime --source dhan --poll-interval-seconds 30`, **09:18:22 IST** |
| Data source | REAL Dhan WebSocket (`--source dhan`), 1-minute bars |
| Execution | Paper only — structurally guaranteed (`live/dhan/broker_adapter.py`'s `DisabledDhanOrderExecutor` unconditionally raises on every order-mutating call; never wired into any live pipeline). Confirmed unchanged today. |
| Strategy | `trend_momentum_baseline` v1.0, frozen, unmodified — SCIENTIFIC VERDICT: NO DEMONSTRATED EDGE (unchanged from readiness-check banner) |
| Supervisor PID | 16232, heartbeating fresh at every checkpoint from launch to shutdown |
| Worker PIDs | RELIANCE 21808, TCS 16992, HDFCBANK 11816, ICICIBANK 10516, INFY 8712, HINDUNILVR 22676, ITC 22780, SBIN 22900, BHARTIARTL 23068, KOTAKBANK 23428, LT 23536, AXISBANK 22596, ASIANPAINT 8460, MARUTI 2500, SUNPHARMA 23340 — **same PIDs from 09:18:22 launch through shutdown at ~15:40 IST; zero restarts, zero crashes over the whole session** |
| Monitoring | Continuous checkpoints roughly every 8–20 minutes from before open through the 15:30 close and ~10 minutes past it |
| Shutdown | Clean `taskkill /F /T` on the supervisor PID at ~15:40 IST after confirming no post-close phantom bars; all 16 processes terminated successfully |

## 2. Pre-flight and safety (REAL, verified before launch)

- Git: commit `a8a2f9d`, all three refs in sync, working tree clean.
- Dhan credentials (`DHAN_CLIENT_ID`, `DHAN_ACCESS_TOKEN`) present, never printed.
- `readiness-check --deep`: real REST call to `/fundlimit` succeeded (HTTP 200, 0.78s round-trip); real WebSocket connect/subscribe/live-quote cycle succeeded end-to-end (RELIANCE.NS, age=35.4s, HEALTHY).
- Kill switch: INACTIVE at start, confirmed INACTIVE again at close (0 kill-switch-related log lines in the supervisor console all day).
- No unresolved pending approvals left over from a prior session.
- Clock skew: −14.3s at pre-open deep-check, later observed in the −10s to +5s range across individual workers over the day (known, non-blocking dev-machine NTP drift, per prior sessions — not corrected, per standing instruction not to touch the system clock).
- Real order execution: unconditionally disabled at the code level (`RealOrderPlacementDisabledError`, raised by every method of `DisabledDhanOrderExecutor`, never imported by any live pipeline). Verified unchanged; never enabled.

## 3. Data table (per symbol, REAL, final)

| Symbol | Bars today | Fresh | Stale | Signals (cumulative, all-time) | Trades | Net P&L | Last bar (UTC) |
|---|---:|---:|---:|---:|---:|---:|---|
| RELIANCE.NS | 357 | 356 | 1 | 36 | 0 | 0.00 | 2026-09-22 09:44:00 |
| TCS.NS | 357 | 356 | 1 | 18 | 0 | 0.00 | 2026-09-22 09:44:00 |
| HDFCBANK.NS | 357 | 356 | 1 | 11 | 0 | 0.00 | 2026-09-22 09:44:00 |
| ICICIBANK.NS | 357 | 356 | 1 | 18 | 0 | 0.00 | 2026-09-22 09:44:00 |
| INFY.NS | 357 | 356 | 1 | 29 | 0 | 0.00 | 2026-09-22 09:44:00 |
| HINDUNILVR.NS | 357 | 356 | 1 | 29 | 0 | 0.00 | 2026-09-22 09:44:00 |
| ITC.NS | 357 | 356 | 1 | 10 | 0 | 0.00 | 2026-09-22 09:44:00 |
| SBIN.NS | 357 | 356 | 1 | 13 | 0 | 0.00 | 2026-09-22 09:44:00 |
| BHARTIARTL.NS | 357 | 356 | 1 | 18 | 0 | 0.00 | 2026-09-22 09:44:00 |
| KOTAKBANK.NS | 357 | 356 | 1 | 15 | 0 | 0.00 | 2026-09-22 09:44:00 |
| LT.NS | 357 | 356 | 1 | 14 | 0 | 0.00 | 2026-09-22 09:44:00 |
| AXISBANK.NS | 357 | 356 | 1 | 22 | 0 | 0.00 | 2026-09-22 09:44:00 |
| ASIANPAINT.NS | 357 | 356 | 1 | 21 | 0 | 0.00 | 2026-09-22 09:44:00 |
| MARUTI.NS | 357 | 356 | 1 | 22 | 0 | 0.00 | 2026-09-22 09:44:00 |
| SUNPHARMA.NS | 357 | 356 | 1 | 19 | 0 | 0.00 | 2026-09-22 09:44:00 |
| **TOTAL** | **5,355** | **5,340** | **15** | **295** | **0** | **0.00** | |

"Signals" is `predictions.db`'s all-time cumulative `PredictionRecord` count (persists across sessions
by design, per `live/fleet_summary.py`'s own docstring) — not a today-only figure. "Bars" and "Fresh"
are today-only, correctly reset at each fresh `RUNTIME DIR:` launch marker.

## 4. Opening window (09:15–09:30 IST)

- All 15 workers launched within a ~1-second window (heartbeats 03:49:06.5–03:49:07.5 UTC), matching
  the 1.5s stagger setting.
- Two of fifteen symbols (HDFCBANK.NS, ITC.NS) hit a real, server-sent Dhan disconnect (`code=805`,
  "too many WebSocket connections for this client ID") within seconds of connecting — the exact,
  previously-documented startup-churn pattern the launch-stagger mechanism reduces but does not
  eliminate. **Both self-healed on the very first reconnect attempt, within 1 second, with zero missed
  bars and zero data loss** (verified: HDFCBANK's bar#1 and ITC's bar#2 both landed correctly
  immediately after reconnect).
- Duplicate-tick redelivery correctly deduplicated throughout (`CandleBuilder... exactly repeats the
  most recently merged tick... not re-adding its volume a second time`) — observed on essentially
  every symbol, working as designed.

## 5. Mid-session (09:30–15:14 IST)

- Bars accumulated at the expected ~1/minute pace across all 15 symbols continuously, 100% freshness,
  zero stale bars, zero gaps, zero anomalous reconnects for this entire ~5h45m stretch.
- Kill switch remained inactive throughout; no pending-approval backlog ever accumulated
  (`--auto-approve` correctly answers every `PENDING_HUMAN_APPROVAL` signal without bypassing
  CriticGate or RiskEngine — see §6 for a full traced example).

## 6. One signal traced end-to-end (REAL, full decision chain)

INFY.NS, 2026-09-22 06:31:00 UTC (12:01 IST):

1. **Strategy**: BUY signal, entry=1025.00, stop=1024.1964, target=1026.6072, horizon=20 bars (1m).
2. **CriticGate**: verdict = `DOWNGRADE`. Zero HARD-severity failures. Three WARNING-severity flags:
   no research evidence recorded, MACD histogram (+0.0809) disagreeing with the scanner's own momentum
   score (−0.22), and the NIFTY benchmark (`^NSEI`) in a DOWNTREND regime ("hostile for a fresh LONG").
   This is exactly the previously-audited, documented behavior that market-context/regime checks are
   WARNING-only and therefore have zero live blocking effect by themselves — confirmed live, not just
   in prior static audits.
3. **RiskEngine**: `approved=False`, `veto_reasons=[MAX_EXPOSURE]`. Requested quantity 622 shares
   (≈₹99,425 notional, 99.4% of the ₹100,000 paper account) was reduced to an approved quantity of 0.
   RiskEngine correctly rejected an oversized position on its own, independent of the critic's verdict.
4. **Outcome**: no paper trade placed. Full chain — tick → candle → indicators → strategy → signal →
   CriticGate → RiskEngine → prediction record → (no trade, correctly) — worked exactly as designed.

This pattern (signal generated, CriticGate downgrades on WARNING-only grounds, RiskEngine vetoes on
MAX_EXPOSURE) is consistent with the 0-trades-all-session result and with prior sessions' documented
behavior. It is **not interpreted as evidence about the strategy**, per standing instruction.

## 7. Real infrastructure finding — yfinance ModuleNotFoundError (found, scoped, remediated)

**What happened**: starting at 10:17:46 IST, `live.prediction_recorder`'s periodic prediction-outcome
auto-evaluation (runs every 20 bars) began failing every ~20 minutes with
`ModuleNotFoundError: No module named 'yfinance'`, isolated entirely to BHARTIARTL.NS (the only symbol
with pending predictions reaching their evaluation-due horizon during today's session — confirmed by
grepping `ModuleNotFoundError` across all 15 symbols' full session logs, only BHARTIARTL.NS matched).

**Root cause** (fully traced): today's `fleet-supervise` was launched using the system Python
(`C:\...\Python314\python.exe`, on PATH) rather than this project's `venv\Scripts\python.exe`. Only
the venv has `yfinance` installed. The traceback confirms the exact call site:
`market/data_provider.py:196`'s lazy `import yfinance as yf` inside `fetch_ohlcv`, reached only via
`predictions/tracker.py::evaluate_prediction`'s periodic auto-evaluation path.

**Classification**: DATA/INFRASTRUCTURE ISSUE — specifically, a launch-environment mistake this
session, not a code defect. Nothing in the core tick→candle→indicator→strategy→signal→CriticGate→
RiskEngine→paper-trade chain imports yfinance; it was completely unaffected (confirmed: 100% bar
freshness, correct signal/critic/risk behavior throughout, as documented above).

**Remediation**: fleet was deliberately **not restarted mid-session** — that would have discarded
~3+ hours of continuous in-memory indicator-buffer state across all 15 workers and directly conflicted
with the mission's own instruction against interfering or restarting unless the supervisor itself
fails. Instead, after clean shutdown, the full prediction backlog was resolved post-hoc for all 15
symbols using the correct `venv/Scripts/python.exe main.py evaluate --db runtime/<symbol>/predictions.db`
(see §11). **No source code change was required or made; nothing was committed.**

**For future sessions**: always launch via `venv\Scripts\python.exe main.py fleet-supervise ...` (or
activate the venv first), never the bare system `python`.

## 8. Real infrastructure finding — fleet-wide feed disruption near close (~15:14–15:33 IST)

**What happened**: all 15 workers' last real bar landed at the identical timestamp,
**2026-09-22 09:44:00 UTC (15:14:00 IST)**, immediately followed by a universal `[GAP DETECTED]`
warning and a `STALE_SIGNAL_SUPPRESSED` bar #357 on every single symbol. Starting at 15:19:46 IST,
every symbol's feed independently crossed the 300-second silent-connection threshold
(`received no message at all for 30Xs... treating as a silently lost connection and reconnecting`) and
reconnected — **every one succeeded on its first or second attempt**. Most symbols hit this cycle 2–3
times between 15:19 and 15:33 IST (full counts: 2–3 silent-loss events per symbol; 0–3 additional
`code=805` disconnects per symbol, heaviest on ITC.NS at 3). **All 15 workers recovered fully every
time; zero manual intervention; zero invalid candles created (the staleness gate correctly suppressed
signal generation on every affected bar); zero data corruption.**

**Cross-session corroboration**: the prior 2026-09-17 validated session report
(`docs/LIVE_MARKET_VALIDATION_REPORT_2026-09-17.md`, §9) independently documents an almost identical
event — all unaffected symbols "stopped producing new bars simultaneously at 09:43:00 UTC (15:13 IST)"
— **within one minute of today's clock time**, five calendar days apart. That prior session treated it
as an unexplained anomaly and explicitly flagged it as "the natural starting point for the next
engineering session," since on 2026-09-17 the workers never triggered their own reconnect logic during
that gap and simply sat idle, believing themselves connected, for 600s+ without recovering (observation
ended at close before it could self-heal).

**What today adds**: this session shows the SAME near-close clock-time pattern, but today the
300-second silent-loss detector correctly triggered and every worker successfully reconnected multiple
times, unlike the 2026-09-17 observation. This is reported as new evidence, not a diagnosis or a claim
that anything was fixed between sessions (no code changed this session) — the reproducible ~15:13–15:14
IST clock-time correlation across two independent sessions is itself the noteworthy, disclosed fact,
and remains a real, open question about Dhan's own end-of-day feed behavior worth investigating in a
future engineering session, exactly as the prior report already flagged.

## 9. End-of-day verification

- **Market session transition**: `readiness-check` reported `Market session right now: CLOSED` at
  15:30:31 IST — correct, on time.
- **Final bar timestamp**: 2026-09-22 09:44:00 UTC (15:14:00 IST) for all 15 symbols, identically.
- **No post-close phantom bars**: verified directly — three separate checks at 15:33:35, 15:36:06, and
  15:38:36 IST all showed bar #357 as the last processed bar for every symbol checked, with no new bar
  appearing after the 15:30 close.
- **Worker termination**: no auto-stop-at-close logic exists in `live/pipeline.py` (workers run "until
  fed exhaustion / stopped" by design). A graceful `taskkill /PID <supervisor> /T` (no `/F`) was
  attempted first and refused by Windows ("can only be terminated forcefully"), consistent with these
  being ordinary console processes with no message loop; `taskkill /F /T` on the supervisor PID then
  cleanly terminated the supervisor and all 15 workers in one pass — confirmed via `tasklist`, zero
  processes remaining. Safe under the circumstances: no open positions, no pending approvals, real
  order execution structurally disabled throughout, and every prior bar/signal/prediction write was
  already committed to its SQLite store incrementally (not buffered pending a graceful exit).
- **Kill switch**: confirmed INACTIVE at final check.

## 10. Database consistency (REAL, cross-checked against `fleet-summary`)

`paper.store.PaperStore` and `predictions.store.PredictionStore`, queried directly per symbol, agree
exactly with `fleet-summary`'s own read of the same stores: **0 trades, ₹0.00 net P&L, every symbol**,
295 total cumulative predictions across the fleet. No discrepancy found.

## 11. Prediction outcome resolution (post-hoc, all 15 symbols, correct venv interpreter)

Run via `venv/Scripts/python.exe main.py evaluate --db runtime/<symbol>/predictions.db --period 3mo`
after shutdown, resolving the backlog left incomplete by §7's issue plus every symbol's own natural
backlog of predictions whose horizon has since elapsed:

| Symbol | Total | Active | Target hit | Stop hit | Win rate | Avg return |
|---|---:|---:|---:|---:|---:|---:|
| RELIANCE.NS | 36 | 23 | 0 | 13 | 0.0% | −0.05% |
| TCS.NS | 18 | 12 | 0 | 6 | 0.0% | −0.11% |
| HDFCBANK.NS | 11 | 5 | 0 | 6 | 0.0% | −0.08% |
| ICICIBANK.NS | 18 | 15 | 2 | 1 | 66.7% | +0.05% |
| INFY.NS | 29 | 19 | 0 | 10 | 0.0% | −0.10% |
| HINDUNILVR.NS | 29 | 21 | 0 | 8 | 0.0% | −0.09% |
| ITC.NS | 10 | 5 | 0 | 5 | 0.0% | −0.09% |
| SBIN.NS | 13 | 7 | 0 | 6 | 0.0% | −0.07% |
| BHARTIARTL.NS | 18 | 0 | 7 | 11 | 38.9% | +0.02% |
| KOTAKBANK.NS | 15 | 9 | 0 | 6 | 0.0% | −0.14% |
| LT.NS | 14 | 12 | 0 | 2 | 0.0% | −0.05% |
| AXISBANK.NS | 22 | 14 | 0 | 8 | 0.0% | −0.11% |
| ASIANPAINT.NS | 21 | 19 | 0 | 2 | 0.0% | −0.05% |
| MARUTI.NS | 22 | 13 | 0 | 9 | 0.0% | −0.09% |
| SUNPHARMA.NS | 19 | 12 | 7 | 0 | 100.0% | +0.26% |

**These figures are explicitly NOT interpreted as evidence about strategy profitability**, per the
mission's standing instruction. Most predictions remain ACTIVE because `evaluate`'s `--period 3mo`
resolves against **daily** bars while these predictions were made against a **1-minute, 20-bar**
horizon — a known, pre-existing resolution mismatch in this command, not something introduced or
fixed today. The small resolved samples per symbol (0–18) are far too small, and the
resolution-methodology mismatch too coarse, to say anything about the frozen strategy — consistent
with, and reinforcing, the existing NO DEMONSTRATED EDGE verdict rather than contradicting it.

## 12. What was NOT done (per mission's explicit prohibitions)

No parameters changed. No thresholds loosened. `MAX_EXPOSURE` untouched. No ATR multiplier changed.
No signal or trade forced. CriticGate and RiskEngine never disabled. Real orders never enabled. No new
hypothesis created from today's observations. The two real findings above (§7, §8) were classified
precisely (DATA/INFRASTRUCTURE) and neither required or received a source code change — both were
launch-environment/external-feed observations, disclosed and remediated without touching the frozen
strategy, risk configuration, or research registry.

## 13. Tests / commits

No code was changed today, so no new tests were written and nothing was committed. Git remains at
`a8a2f9d`, `final-product-hardening` == `origin/final-product-hardening` == `main`, working tree clean
— identical to the start of this session.

## 14. Final verdict

**System operated correctly; no research conclusion changed.**

Operationally: 15/15 workers launched cleanly (staggered), ran ~6h22m without a single restart or
crash, self-healed from every one of ~40 total transient Dhan-side disconnects across the day (two at
launch, a fleet-wide cluster near close), produced zero invalid candles, zero duplicate-tick
overcounts, zero premature or phantom bars, and shut down cleanly with a fully consistent, cross-
checked audit trail (295 predictions, 0 trades, every rejection traceable to a specific RiskEngine
veto or CriticGate downgrade). One real, fully-traced, non-fatal infrastructure issue was found
(§7, launch-environment yfinance gap) and fully remediated without touching any source file. One real,
cross-session-corroborated open question about Dhan's own near-close feed behavior was reinforced with
new evidence (§8) and left for a future, separately-scoped engineering session, exactly as the prior
session's report already recommended. The research program remains closed exactly as it was at the
start of the day.
