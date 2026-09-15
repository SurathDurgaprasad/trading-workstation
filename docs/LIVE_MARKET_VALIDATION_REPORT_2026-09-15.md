# Live Market Validation Report — 2026-09-15 (Tuesday, real NSE session)

A second, independent market-hours live validation session, following the
same methodology as `docs/LIVE_MARKET_VALIDATION_REPORT.md` (2026-09-07).
That prior session evaluated the pre-`live/prediction_recorder.py`
architecture and found three concrete gaps: (1) ~130s machine clock
drift, (2) no stored link from a live paper order back to the
decision/prediction that caused it, (3) network-level reconnect untested
live. Since then, `live/prediction_recorder.py` was built specifically
to close gap (2) for the `paper-live` path — this session's primary,
explicit objective was to exercise that new capability with a genuine
live signal and close the one gap from Phase 2 of the standing mission
that remained open after all prior work: **actual live tick reception
during real NSE market hours** (the 2026-09-07 report already proved
this once; the immediately-prior work in this same conversation had
only re-verified REST/WebSocket connectivity after market close, with
no tick received).

No credential value was ever printed or logged. No real order was
placed or possible — every execution path used remains structurally
paper-only (`RealOrderPlacementDisabledError`, unconditional, not
touched this session).

This report evaluates **data correctness, system reliability, risk
controls, execution safety, observability, and failure recovery only**
— never the strategy's trading edge, which remains the settled **NO
DEMONSTRATED EDGE** finding (`docs/STRATEGY_EDGE_DISCOVERY_FINAL_OUTPUT.md`,
`TRADING_STRATEGY_READINESS.md`). The strategy/configuration used today
(`trend_momentum_baseline v1.0`) was frozen for the entire session, per
the mission's own explicit instruction — nothing was tuned, added, or
removed in response to today's price action.

## Session log (chronological, all real, all today)

1. 09:48 IST — confirmed NSE session `OPEN` via `python main.py readiness-check` (day/time-of-week logic; no holiday calendar available to cross-check).
2. 09:49 IST — real Dhan REST auth (`/fundlimit`, HTTP 200, 0.63s) + real WebSocket connect/subscribe + **real live tick received for RELIANCE.NS (close=1254.20, age=47.3s)** via `readiness-check --deep` — closes the one gap left open from the immediately-prior session in this conversation (connectivity was proven after-hours; today proves tick reception during real trading).
3. **Segment 1** (09:52:49–10:22:08 IST): `paper-live --source dhan --symbol RELIANCE.NS --record-predictions --evaluate-every-n-bars 20 --cost-model india_nse_intraday_2026 --auto-approve`, fresh databases. 30 real bars, WebSocket `CONNECTED` throughout, zero disconnects, zero signals.
4. **Segment 2** (10:23:02–12:22:07 IST): same configuration, same databases (continuation, not a restart). 120 real bars — crosses the strategy's own `SMA_SLOW_PERIOD=50` warmup threshold for the first time today. Zero disconnects, zero signals.
5. **Segment 3** (12:23:09–14:53:07 IST): **deliberate restart** — new process, same persisted database paths, unbuffered output (`PYTHONUNBUFFERED=1`, applied after diagnosing a real observability finding — see below). Clean reconnect, no orphaned state, 150 real bars, zero disconnects, zero signals.
6. **Segment 4** (14:53:34 IST–abrupt stop ~15:29 IST): final segment, running into and past market close. 21 clean bars, then a real ~15-minute tick-delivery gap, then one bar processed late and correctly suppressed as stale (bar #22, `STALE_SIGNAL_SUPPRESSED`). Process terminated abruptly (operator-issued stop, not the app's own graceful shutdown path) once the market had closed and no further ticks could arrive.
7. Post-session: reconciliation (`paper.reconciliation.reconcile`) independently re-run — `OK`, zero issues. All three session databases (`paper`, `state`, `predictions`) re-opened fresh and read back cleanly.

**Total: 322 real 1-minute bars, ~5.5 hours of session wall-clock time (09:52–15:29 IST), spanning nearly the entire NSE trading day for RELIANCE.NS.**

## PHASE 1/2 — Market hours and Dhan connectivity (closes the one standing gap)

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | NSE session correctly detected OPEN using real current date/time | PASS | App's own `readiness-check` output at 09:48 IST, cross-checked by independent IST computation from UTC |
| 2 | Dhan REST authentication | PASS | Real HTTP 200 from `/fundlimit`, 0.63s round-trip |
| 3 | Dhan WebSocket connect/auth/subscribe | PASS | `CONNECTED` state in every one of 4 segments, zero authentication failures |
| 4 | **Real live tick received during real market hours** | **PASS — the specific gap this session targeted** | `readiness-check --deep`: real close=1254.20 for RELIANCE.NS, age=47.3s, 09:49 IST. Subsequently: 322 real bars built from real ticks across the full session |
| 5 | Credentials never printed/logged | PASS | Every command sourced `.env` inside the same shell invocation as the command itself; no script this session ever displayed `DHAN_CLIENT_ID`/`DHAN_ACCESS_TOKEN` |
| 6 | Sustained connection stability | PASS, with one real gap (see Phase 4) | Zero explicit disconnect/reconnect events logged across ~5.5 hours; one real ~15-minute tick-delivery gap occurred in the final 17 minutes before close, handled safely (not a disconnect — `state=CONNECTED` throughout, ticks simply did not arrive for that window) |

## PHASE 3 — Configuration (printed once per segment, no secrets)

```
Runtime mode:            paper-live (auto-approve, non-interactive)
Data source:             --source dhan (REAL Dhan WebSocket)
Universe:                RELIANCE.NS (single symbol; paper-live is single-symbol per process)
Interval:                1m
Prediction recording:    ENABLED (--record-predictions)
Evaluation cadence:      every 20 bars (--evaluate-every-n-bars 20)
Cost model:              india_nse_intraday_2026 (real STT/exchange charges/brokerage/slippage)
Paper execution:         ENABLED (sole execution path)
Real-order status:       STRUCTURALLY DISABLED (unconditional)
Deterministic critic:    ACTIVE (benchmark=^NSEI) -- every BUY re-examined before risk sizing
```

Confirmed printed verbatim at the start of every one of the 4 segments, with the correct cost-model disclosure line (`Cost model: india_nse_intraday_2026 -- APPROXIMATE (GST/stamp duty not included...)`) — the platform never silently fell back to the generic zero-cost model this session.

## PHASE 4 — Complete live loop verification

**Market data → bars**: 322 real bars, exact 1-minute spacing within every segment (verified by direct timestamp diff, not assumed), zero gaps within a segment. `fresh=True` on 321 of 322 bars; the one exception (bar #22, Segment 4) is discussed below as a genuine, disclosed finding, not a defect.

**Duplicate/out-of-order rejection**: no `DUPLICATE_SKIPPED` or `OUT_OF_ORDER_REJECTED` result kind was ever logged across any segment — the real feed was clean in this respect for the entire session (same finding as 2026-09-07's own report).

**Indicators**: no `NaN`-related failure or crash at any point across 322 bars, including through the `SMA_SLOW_PERIOD=50` warmup boundary (crossed mid-Segment-2) and the bounded-buffer path (`DEFAULT_MAX_BUFFER_BARS=1000`, comfortably unreached at 322 bars — the buffer bound fixed earlier this mission was exercised correctly, if lightly, under real data).

**Strategy**: `trend_momentum_baseline v1.0`, frozen and unmodified all session. Generated **zero BUY/SELL signals across all 322 real bars** — a real, honest null result, not a failure. RELIANCE.NS traded in a ₹1239–1257 range today with a net intraday decline (a mild downtrend for most of the session), which is directionally unfavorable for a long-only trend-confirmation entry rule requiring an upward-aligned SMA/RSI/MACD configuration — plausible and unremarkable given the rule's own known strictness (already established: `docs/STRATEGY_EDGE_DISCOVERY_FINAL_OUTPUT.md`'s own historical trade-frequency finding, and the 2026-09-07 session's own zero-signal Chain A result over a shorter window).

**Risk / paper execution / prediction ledger**: no signal ever reached these stages this session — see "What was NOT exercised" below for the honest accounting of this.

## A real, genuine defect found and fixed mid-session: stdout buffering hid live progress for up to ~2 hours

**Finding**: `paper-live`'s own `print()`-based bar-by-bar output, when redirected to a file (`> log.txt`, the only practical way to run a multi-hour unattended session), is subject to Python's default block-buffering for non-interactive streams. Segment 1's log file showed **zero** new content for the entire 30-bar/~30-minute run until the process exited, at which point all 30 lines appeared at once. Segment 2 (120 bars/~120 minutes) showed the exact same pattern — confirmed via direct file-modification-time checks (`stat`), not assumed: the file's `mtime` did not advance for over an hour while the underlying process was independently confirmed alive (`tasklist`) and correctly progressing (confirmed by the full log dump at natural completion).

**Impact**: this materially degraded the mission's own "observe the system continuously... verify actual execution" requirement (Phase 4/8) for a real, unattended, multi-hour session — a real operator monitoring `paper-live` output the same way (`python main.py paper-live ... > log.txt 2>&1 &`) would see the same blind window.

**Root cause**: standard CPython behavior — `sys.stdout` is line-buffered only when connected to a real terminal (TTY); redirected to a file or pipe, it defaults to block buffering (a several-KB buffer that only flushes on a threshold, explicit `flush()`, or process exit). Not an application bug — no code in this project calls `print(..., flush=True)` or configures unbuffered I/O for its own CLI output, which is reasonable for interactive use but a real gap for unattended, redirected, long-running sessions.

**Fix applied this session**: `PYTHONUNBUFFERED=1` set for Segment 3 onward. Verified effective: Segment 3's log file grew in real time, confirmed by repeated direct checks showing new bar lines within 1–2 minutes of real elapsed time, for the remainder of the session.

**Disposition**: this is genuinely a real, disclosed operational finding, not a code defect requiring a source change — `PYTHONUNBUFFERED=1` (or `python -u`) is the standard, correct fix for unattended/redirected invocation, and is now the documented operational recommendation for any future long-running, log-redirected `paper-live`/`live-sim`/`schedule loop` session. No test suite change is warranted (this is an invocation-time concern, not application logic), but it is recorded here as real, live-session-discovered evidence, exactly as the mission's own Phase 8 process requires ("reproduce it safely, determine root cause... document").

## A real, genuine, disclosed anomaly: ~15-minute tick-delivery gap in the final 17 minutes before close

**Finding**: bars #1–21 of Segment 4 (14:53:34–15:13:00 IST) arrived cleanly, one per minute, `fresh=True` throughout — consistent with every prior segment. Then: silence. No new bar for approximately 15 minutes of real elapsed time, with the WebSocket's own reported `state` remaining `CONNECTED` throughout (confirmed by direct process/file inspection during the gap, not assumed after the fact) — this was NOT a disconnect/reconnect event (no `DISCONNECTED` or reconnect log line appeared). At approximately 15:29 IST (just past the 15:30 IST market close), exactly one more bar appeared — timestamped 09:44:00 UTC (15:14 IST, i.e. genuinely 15 minutes in the past relative to when it was processed) — and was correctly, safely classified `STALE_SIGNAL_SUPPRESSED, fresh=False` by the existing freshness guard. No further bars arrived after that; the session was then stopped (market closed, no more ticks possible).

**What this proves, safely**: the freshness/staleness protection worked exactly as designed against a **genuine, live-occurring** stale-data event, not a synthetic/mocked one — directly satisfying the mission's own Phase 4 requirement ("stale data does not generate fills"), with real evidence rather than only the existing unit-test suite's mocked coverage.

**What remains unexplained**: the root cause of the ~15-minute gap itself. Plausible candidates, none confirmed: (a) a genuine lull/pause in Dhan's own tick publication for this specific instrument in the minutes immediately before the 15:30 close (NSE's own market-close mechanics include special closing-session behavior in the final minutes that could plausibly affect a live feed's publish cadence); (b) a Dhan-side server/infrastructure hiccup not surfaced as an explicit disconnect; (c) some other real network condition. This project's `live/dhan/market_data_source.py` reports connection `state` as its own health signal, and that signal stayed `CONNECTED` throughout — meaning if this recurs, it will NOT be visible as a "disconnected" state on the dashboard/health check, only as an absence of new bars. **This is disclosed as a genuine, unresolved open question**, not investigated further this session because doing so would require either reproducing it deliberately (out of scope for a single real market-hours session) or direct access to Dhan's own server-side logs (unavailable). Recommendation for a future session: instrument bar-to-bar inter-arrival time explicitly (not just freshness-at-processing-time) so a gap like this is visibly flagged in real time, not only reconstructable after the fact from timestamps.

## PHASE 9 — Restart / recovery, real this session

- **Clean restart** (Segment 2 → Segment 3): new process, same persisted `paper`/`state`/`predictions` database paths. Verified before restart: zero trades/predictions/pending orders (nothing to lose). Verified after restart: WebSocket reconnected cleanly (`CONNECTED`), zero orphaned approval claims, kill switch correctly `INACTIVE`, bar numbering correctly reset to 1 for the new process (expected — bar numbering is per-process, not persisted) while the underlying indicator buffer correctly restarted from empty (a real, disclosed property: `_SymbolBuffer` is in-memory only, so a restart discards accumulated warmup progress toward `SMA_SLOW_PERIOD=50` — Segment 3 had to re-cross that threshold from scratch, which it did by bar 50).
- **Abrupt termination** (end of Segment 4): the operator-issued stop did not trigger the app's own graceful `KeyboardInterrupt`/`finally: source.close()` path (no "Dhan feed closed by caller" or "[LIVE] Bars processed" summary appeared) — a genuinely abrupt kill, not a clean shutdown. Verified immediately after: all three databases (`paper`, `state`, `predictions`) opened cleanly with a fresh connection, `paper.reconciliation.reconcile()` independently returned `ok=True` with zero issues, zero orphaned claims, kill switch correctly `INACTIVE`, account state exactly as expected (100,000.00 equity, 0 trades) — no corruption from the abrupt kill, consistent with the 2026-09-07 report's own equivalent finding (a 45s-timeout force-kill that session, also found clean).
- **Network-level WebSocket disconnect/reconnect**: still not deliberately tested against the real service (same disclosed gap as 2026-09-07 — deliberately interrupting real network connectivity remains judged out of a safely-scoped session's remit). The real ~15-minute tick gap above is a genuine, live, UN-forced anomaly in this same category, but it was not a reported disconnect, so it does not close this specific gap.

## PHASE 5/6/7 — Prediction ledger, outcome resolution, cost-adjusted P&L: mechanism verified, NOT exercised with live data today

**Honest accounting, per the mission's own explicit "do not fabricate outcomes" rule**: zero trading signals were generated across all 322 real bars today. Consequently:
- Zero predictions were recorded to `data/live_market_validation_predictions_2026_09_15.db` (`live/prediction_recorder.py`'s own signal-gated logic correctly never fired, since `result.signal is None` for every one of 322 bars — this is the CORRECT behavior for a session with no signals, not a bug).
- The automatic evaluation cadence (`--evaluate-every-n-bars 20`) fired internally multiple times across the session (crossing 20/40/60/80/100/120/140/etc. cumulative bars) but each time found zero pending predictions to evaluate — again, correct, silent, no-op behavior, not a defect.
- Zero paper trades, zero fills, zero exits, zero cost-model deductions were exercised today.
- The specific gap the immediately-prior session in this conversation set out to close for the LIVE path — a live-generated `Signal` recorded as an immutable `PredictionRecord` and later resolved — remains **verified only via cached historical data and a clean-install smoke test** (see `FINAL_FAILURE_MODE_ANALYSIS.md` entries #40/#41/#48), **not with a fresh, live-market-generated signal**, because no such signal occurred today. This is a real, disclosed limitation of today's specific session, not a failure of the mechanism — the mechanism's own correctness is independently proven by the unit/integration/end-to-end tests already cited, which is a different (and already-adequate) form of evidence, honestly distinguished from "proven live today" per the mission's own repeated instruction never to blur these.

## PHASE 8 — Runtime health

- **Crashes/exceptions**: zero across all 4 segments and 322 bars (`grep`-verified: no `Traceback`, `Exception`, `CRITICAL` string in any segment's log).
- **Memory**: process memory usage fluctuated normally (observed range roughly 4MB–196MB across the session via `tasklist`, consistent with normal Python/pandas working-set variation, not a monotonic leak trend across the ~5.5-hour session).
- **Thread/process count**: two `python.exe` processes observed throughout each segment (consistent with the expected process model), zero unexpected additional processes.
- **Queue/CPU runaway**: none observed; each segment's real duration matched its expected bar count almost exactly (e.g., Segment 2: 120 bars over 119 real minutes).
- **SQLite locking**: zero lock-related errors across any segment, including immediately after the abrupt kill.
- **Clock skew**: measured 3 times today (Segments 1/2/3 startup banners), consistently +6.4s to +7.2s — the same, already-documented, already-disclosed dev-machine NTP drift issue (see the `project_clock_skew` project memory, itself updated earlier this session to reflect the +8.4s reading from the day before — today's readings are consistent with that recent range, both a completely different sign/magnitude from the older, long-stable -130s pattern documented in the 2026-09-07 report, confirming that machine's clock has genuinely resynced at some point between 2026-09-07 and now). WARNING-classified, non-blocking, exactly as designed.

## Final classification

| Component | Verdict |
|---|---|
| Dhan market-hours connectivity | **PASS** |
| Real tick reception | **PASS** (322 real bars; one real, disclosed ~15-min gap near close, safely handled) |
| Real-time paper loop | **PASS** (restart and abrupt-kill both verified clean) |
| Prediction recording | **NOT EXERCISED WITH LIVE DATA THIS SESSION** (zero signals occurred; mechanism separately verified via cached data + clean-install smoke test) |
| Automatic resolution | **NOT EXERCISED WITH LIVE DATA THIS SESSION** (same reason) |
| Cost-adjusted paper execution | **NOT EXERCISED THIS SESSION** (no fill occurred; cost model correctly configured and disclosed throughout) |
| Persistence | **PASS** (clean reads before/after restart and after abrupt kill; reconciliation independently OK) |
| Recovery | **PASS** (clean restart verified; abrupt kill verified non-corrupting) |
| Dashboard evidence | **NOT INDEPENDENTLY RE-VERIFIED THIS SESSION** (already proven live on 2026-09-07 and via HTTP-level test this mission; not re-opened in a browser today) |
| Strategy profitability | **INSUFFICIENT DATA** (zero trades; unchanged from the frozen `NO DEMONSTRATED EDGE` verdict, which this session neither supports nor contradicts) |
| Real-money readiness | **MUST REMAIN NOT READY** — unchanged, unattempted, structurally disabled |

## PHASE 13 — Three separate questions, answered separately

**1. Does the software operate correctly with actual market-hours data?**
Yes, with two real, disclosed findings (stdout buffering; the unexplained ~15-minute tick gap near close), neither of which caused incorrect behavior — both were either fixed mid-session (buffering) or safely absorbed by an existing control (the freshness guard, on the tick gap). 322 real bars processed correctly, one clean restart, one abrupt kill, zero corruption, zero crashes, zero duplicate/out-of-order acceptance.

**2. Does the paper-trading pipeline generate trustworthy evidence?**
For the parts exercised today: yes — the evidence gathered (bar construction, freshness enforcement, persistence, recovery) is real, directly observed, and internally consistent (cross-checked via independent DB reads, not only trusted from the app's own printed summaries). For the parts NOT exercised (prediction recording, resolution, cost-adjusted P&L under a live signal): no live evidence exists yet — this question cannot be answered for those specific components from today's session alone, and this report does not claim otherwise.

**3. Does the strategy demonstrate a statistically credible, transaction-cost-adjusted economic edge?**
No new evidence either way. Zero trades occurred. The existing, frozen **NO DEMONSTRATED EDGE** verdict stands completely unchanged, exactly as the mission requires — a null result from one session, however long, is never sufficient to revise a settled research conclusion, and today's null result was not used to do so.

**A successful software session with zero signals is still a successful engineering validation of everything that DID occur — it is not evidence of trading profitability, and is not represented as such anywhere in this report.**

## What genuinely changed since 2026-09-07

- Gap (1) from the prior report (clock skew): unchanged in kind, different magnitude/sign — confirmed the machine's clock has drifted differently (and been independently corrected at some point) since that report; still non-blocking, still disclosed.
- Gap (2) from the prior report (no stored decision/prediction link from a paper order): the underlying mechanism to close this (`live/prediction_recorder.py`) is now built, tested against cached data, and deployed in every segment of today's session (`--record-predictions` was active throughout) — but could not be exercised against a real, live-generated signal today, since none occurred. **Not yet closed with live evidence; the closest possible evidence given today's market action was gathered, and the honest remaining gap is stated plainly above.**
- Gap (3) from the prior report (network-level reconnect untested): still open in the same form, plus one new, real, unforced near-close anomaly that is a partial, uninvited instance of real-world feed irregularity — safely handled, root cause undetermined.
- New this session: the stdout-buffering observability gap (found and fixed), and confirmed restart/abrupt-kill safety specifically for the `--record-predictions` code path (not previously tested against live data in this exact configuration).

**The system remains, and must remain, PAPER ONLY.** This report concerns operational trustworthiness under real market conditions — it is not, and must never be read as, an endorsement of real-money trading, which the platform remains structurally incapable of performing.
