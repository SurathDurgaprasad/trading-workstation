# Live Market Validation Report — 2026-09-17

Second real market-hours execution of the hardened 15-symbol multi-symbol fleet on a fresh NSE session, real Dhan data, paper trading only, the frozen `TrendMomentumBaseline v1.0` strategy, prediction recording, and full observability. This session also produced, diagnosed, reproduced, and fixed a real production defect in `CandleBuilder`'s cold-start timestamp handling.

**Evidence labels used throughout**: REAL (observed directly from a live/real system), MECHANISM-VERIFIED (proven correct by running the project's own code against real data, but not exercised by today's live path), DIAGNOSTIC (a real reconstruction from real Dhan-fed log data, run outside the live process, used only to explain — never to substitute for — the live path's own behavior).

## 1. Session summary

| | |
|---|---|
| Date | 2026-09-17 (Thursday, fresh NSE trading day) |
| Universe | 15 symbols, `market_data/watchlists/starter_nse.yaml` |
| Fleet launch | `fleet-supervise --watchlist-file market_data/watchlists/starter_nse.yaml --runtime-dir runtime --source dhan --poll-interval-seconds 30`, 09:12:15 IST |
| Data source | REAL Dhan WebSocket (`--source dhan`), 1-minute bars |
| Execution | Paper only — structurally guaranteed (see §6) |
| Strategy | `TrendMomentumBaseline` v1.0, frozen, unmodified all session (confirmed via `Get-CimInstance Win32_Process` — zero of 15 worker command lines carry a `--strategy` override) |
| Supervisor | Alive and heartbeating fresh throughout, confirmed at every checkpoint including the final one (15:21:53 IST) |
| Monitoring | Continuous observation-only checkpoints roughly every ~28 minutes from fleet launch through NSE close, per the mission's standing instruction |

## 2. Pre-flight and safety (REAL, verified before any launch)

- Branch `final-product-hardening`, `main` in sync at launch time.
- Credentials (`DHAN_CLIENT_ID`, `DHAN_ACCESS_TOKEN`) confirmed present without ever printing values.
- Fleet launched successfully at 09:12:15 IST, all 15 workers alive within seconds, confirmed via heartbeats.
- No strategy, threshold, or configuration change made at any point today — strictly observe/validate/document per the mission's absolute rule.

## 3. Data table (per symbol, REAL)

| Symbol | Bars produced today | `implausible_timestamp` rejections | Last real bar (UTC) | Status at final checkpoint |
|---|---|---|---|---|
| RELIANCE.NS | 360 | 0 | 2026-09-17 09:43:00 | Alive, feed gap since last bar (see §9) |
| TCS.NS | 360 | 0 | 2026-09-17 09:43:00 | Alive, feed gap since last bar (see §9) |
| HDFCBANK.NS | 360 | 0 | 2026-09-17 09:43:00 | Alive, feed gap since last bar (see §9) |
| ICICIBANK.NS | 360 | 0 | 2026-09-17 09:43:00 | Alive, feed gap since last bar (see §9) |
| INFY.NS | 360 | 0 | 2026-09-17 09:43:00 | Alive, feed gap since last bar (see §9) |
| HINDUNILVR.NS | 282 (bars 1-282 span 2026-09-16→17, cold-start defect — see §8) | 9,881 | n/a (blocked by defect, see §8) | Alive; will self-heal on next process restart with the fix |
| ITC.NS | 360 | 0 | 2026-09-17 09:43:00 | Alive, feed gap since last bar (see §9) |
| SBIN.NS | 360 | 0 | 2026-09-17 09:43:00 | Alive, feed gap since last bar (see §9) |
| BHARTIARTL.NS | 360 | 0 | 2026-09-17 09:43:00 | Alive, feed gap since last bar (see §9) |
| KOTAKBANK.NS | 360 | 0 | 2026-09-17 09:43:00 | Alive, feed gap since last bar (see §9) |
| LT.NS | 360 | 0 | 2026-09-17 09:43:00 | Alive, feed gap since last bar (see §9) |
| AXISBANK.NS | 360 | 0 | 2026-09-17 09:43:00 | Alive, feed gap since last bar (see §9) |
| ASIANPAINT.NS | 360 | 0 | 2026-09-17 09:43:00 | Alive, feed gap since last bar (see §9) |
| MARUTI.NS | 360 | 0 | 2026-09-17 09:43:00 | Alive, feed gap since last bar (see §9) |
| SUNPHARMA.NS | 279 (2026-09-16→17, cold-start defect — see §8) | 16,623 | n/a (blocked by defect, see §8) | Alive; will self-heal on next process restart with the fix |

13/15 symbols processed 360 real bars normally all session. 2/15 (HINDUNILVR.NS, SUNPHARMA.NS) were affected by the cold-start defect described in §8, confirmed and fixed today (fix applies to future process starts only — the currently-running instances were left untouched per the standing instruction not to restart the live fleet).

## 4. Trading table (per symbol, REAL)

| Symbol | Candidates (live path) | Critic evals | Risk evals | Signals | Predictions | Trades |
|---|---|---|---|---|---|---|
| *(all 15 symbols)* | 0 | 0 | 0 | 0 | 0 | 0 |

Zero across the board, every symbol, all day — confirmed by direct read-only SQLite queries against every symbol's `predictions.db` and `paper.db` (all `PRAGMA integrity_check = ok`). This is consistent with, and does **not** change, the frozen `NO DEMONSTRATED EDGE` verdict — see §11.

**Diagnostic root-cause (not a wiring defect):** at a 12:43 IST mid-session diagnostic cross-check, indicator series were reconstructed directly from each symbol's own REAL Dhan close-price ticks (never Yahoo) and run through the project's own `market.indicators.compute_indicator_series()` and `TrendMomentumBaseline`'s real entry conditions. `volume_trend` was the dominant, near-universal blocker across the session — several symbols independently satisfied trend AND momentum simultaneously, blocked only by `volume_trend` reading "decreasing"/"neutral". This has a plausible, non-bug, code-level explanation: `market/indicators.py::_volume_trend()` computes a 5-bar trailing linear-regression slope of raw per-minute volume; NSE intraday volume is well-known to be U-shaped (highest at the 09:15-09:30 open, decaying through the morning) — a continuously-computed 5-bar trailing slope through a normal morning session will systematically read "decreasing" for this reason alone, independent of any genuine bullish setup. This is a DIAGNOSTIC finding about the shape of the blocker, not proof the strategy has or lacks edge — see §11's valid/invalid-statement distinction.

`live/pipeline.py::LiveSimPipeline.process_next()` (the authoritative live signal-generation path) was read and confirmed correct: the current candle is included in signal generation, no hidden filter exists between `generate_signal()`'s return and the `BAR_PROCESSED`/signal-handling branch, and stale bars are still appended to the indicator buffer (barred only from generating a NEW signal on that specific bar). Zero signals today is genuinely explained by the frozen strategy's actual entry conditions interacting with real market seasonality, not a pipeline wiring defect.

## 5. Fleet supervision and observability

- Supervisor (PID 7268) alive and heartbeating fresh at every checkpoint throughout the session, confirmed via `runtime/_supervisor/heartbeat.json` freshness (the authoritative liveness signal — RSS-based process filtering was found earlier in the session to give false negatives for this lightweight process and was abandoned as the primary check).
- All 15 workers alive and heartbeating fresh (~3-4s age) at the final checkpoint (15:21-15:22 IST).
- Independent RSS-based corroboration of the CandleBuilder defect: healthy workers ~25-26MB RSS (proportional to accumulated bar/indicator history) vs HINDUNILVR.NS/SUNPHARMA.NS at only ~6MB (near-zero accumulated history) — a completely separate signal from the log evidence, both pointing to the same root cause.

## 6. Safety verification (structural, REAL)

The 8 live-execution-safety files remained **zero-diff against `main` for the entire session**, re-confirmed at the final checkpoint (15:23 IST): `live/dhan/broker_adapter.py`, `live/broker.py`, `live/pipeline.py`, `decision_engine/rules.py`, `decision_engine/engine.py`, `risk/engine.py`, `risk/sizing.py`, `main.py`. `DisabledDhanOrderExecutor.place_order()` re-verified structurally disabled (raises `RealOrderPlacementDisabledError` unconditionally) multiple times throughout the day. 0 rows in every `paper.db`'s trades table and every `predictions.db`'s predictions table across all 15 symbols, queried read-only, `PRAGMA integrity_check = ok` on every database, every checkpoint, all day.

## 7. Prediction tracking

Mechanism exists and is code-path-reachable (`--record-predictions`, `--evaluate-every-n-bars 20`), but **NOT EXERCISED today** — zero signals means zero predictions were ever recorded. Honest, required statement: **PREDICTION PATH NOT EXERCISED BY LIVE SIGNAL today** — mechanism remains MECHANISM-VERIFIED only, by historical/integration tests and prior sessions, never by a live invocation on 2026-09-17.

## 8. Confirmed defect: `CandleBuilder` cold-start timestamp poisoning — found, reproduced, fixed today

**Discovery.** During a mid-session read-only audit, HINDUNILVR.NS and SUNPHARMA.NS showed near-zero bar counts and RSS while the other 13 symbols processed normally. `implausible_timestamp` rejection counts were growing unbounded (203/235 at first observation, reaching 9,881/16,623 by end of session).

**Root cause.** `live/dhan/candle_builder.py::CandleBuilder.on_tick()` trusted the very first tick a fresh instance ever receives unconditionally as its timestamp baseline (`_last_known_timestamp`), since there was nothing yet to compare it against. HINDUNILVR.NS and SUNPHARMA.NS each received a stale first tick today carrying the **previous** trading day's timestamp (2026-09-16 10:26:09 UTC and 10:22:06 UTC respectively — almost certainly a Dhan overnight LTP-snapshot artifact delivered immediately on WebSocket subscribe). This silently seeded the baseline with a stale value, and every genuinely-current tick thereafter was rejected forever by the (correct, and unchanged) `_max_timestamp_skew_seconds` plausibility check, since it would always appear ~1 day "in the future" relative to the poisoned baseline.

**Reproduction.** Reproduced exactly in isolation using the real seed timestamps from today's incident (see the commit for the exact repro), confirming the permanent-rejection behavior pre-fix and the self-healing behavior post-fix.

**Fix (commit `4a26221` on `final-product-hardening`, fast-forward-merged to `main`).** Added a two-tick confirmation window: while the baseline is unconfirmed, a disagreeing tick is rejected (exactly like the pre-existing behavior) and remembered as a `_pending_candidate_timestamp`, rather than immediately overwriting the trusted baseline. Only when a **second, independent** tick agrees with that pending candidate does the baseline switch, discarding any bucket state built from the now-abandoned baseline. Once two ticks agree (either reconfirming the original baseline, or establishing a new one), behavior becomes permanently identical to the pre-existing, already-tested mid-session rejection logic — the defense that protects a single stray bad tick mid-session from ever displacing a good baseline is untouched.

An earlier, simpler "re-seed on any single disagreement" design was tried first and **rejected** — it broke the existing `test_a_wildly_future_timestamp_does_not_permanently_kill_candle_production` test by letting one stray mid-session bad tick permanently displace an already-good baseline. The two-tick confirmation requirement is what correctly distinguishes "the original baseline was the bad one" (today's real incident) from "one stray bad tick occurred mid-stream" (the scenario the existing test already protects against).

**Verification.**
- 3 new regression tests added to `tests/test_dhan_candle_builder.py`: self-healing from a poisoned first tick, repeated disagreeing startup ticks until two finally agree, and an explicit named regression guard that the fix does not weaken the existing mid-session single-bad-tick protection.
- All 37 tests in `tests/test_dhan_candle_builder.py` pass (34 pre-existing + 3 new).
- Mutation-tested: the new confirmation branch was disabled and re-run — exactly the 2 new self-recovery tests failed (the mid-session regression guard correctly still passed, since it exercises unrelated code), confirming the new tests genuinely exercise the fix.
- Re-reproduced against today's exact real HINDUNILVR.NS seed values with the fix applied: self-heals after one extra tick instead of rejecting forever.
- Full regression suite: **2,565 passed, 0 failures** (up from the prior 2,562 baseline by exactly the 3 net new tests).
- `git diff` confirmed scoped to exactly `live/dhan/candle_builder.py` and `tests/test_dhan_candle_builder.py`.

**Scope note, stated explicitly per the standing instruction:** the fix applies to future `CandleBuilder` process starts only. The currently-running HINDUNILVR.NS and SUNPHARMA.NS workers were **not** restarted today and remain in their pre-fix, poisoned-but-alive state through the rest of this session — implementing, testing, and committing the fix did not require touching the running fleet at all.

## 9. New anomaly found during final checkpoint: fleet-wide bar gap since 09:43 UTC (15:13 IST)

All 13 symbols unaffected by the CandleBuilder defect stopped producing **new** bars simultaneously at 09:43:00 UTC (15:13 IST) — each one's `session.log` shows an identical, growing `[GAP ONGOING] connected, no new bar for Ns` sequence with no corresponding reconnect or error event logged after fleet startup (the only reconnect event across the whole session was a single server-sent disconnect, code 805, at 09:12:21 IST — recovered automatically, unrelated to this gap). Worker heartbeats remained fresh throughout this gap (the process is alive and believes itself connected), but no new tick data has been observed for ~600s+ as of the final checkpoint (15:23 IST), roughly 7 minutes before NSE close. This is reported as an observed, unexplained anomaly at the day's final checkpoint, not diagnosed further today (diagnosis would require either restarting a worker or waiting past close, both out of scope for an observation-only session) — flagged here as the natural starting point for the next engineering session, alongside applying the CandleBuilder fix on the next fleet restart.

## 10. Dashboard

Not exercised or re-audited today — no live signal, prediction, or trade occurred to observe rendering of, and no dashboard-affecting code changed this session.

## 11. Frozen strategy verdict — explicitly unchanged

**`trend_momentum_baseline v1.0` remains `NO DEMONSTRATED EDGE`, exactly as before this session.** Today's zero natural live signals is additional supporting evidence consistent with that verdict, not new proof of its absence or presence — per the mission's own valid/invalid-statement distinction:
- VALID: "Today's live session produced zero natural candidates across all 15 symbols, with `volume_trend` as the dominant observed blocker."
- INVALID: "The strategy has no edge because of zero signals today" (one session's zero-signal outcome does not itself prove or disprove edge) — not asserted here.

No threshold, parameter, or strategy code was tuned, loosened, or otherwise modified today. No synthetic data was injected. No trade was manually created. No source was substituted for Dhan and called live.

## 12. Final Deliverable

1. All 15 symbols individually reported (§3, §4) — bars, rejections, candidates, predictions, trades.
2. Honest natural-candidate count: **0** on the live path, with the `volume_trend`/intraday-seasonality diagnostic explanation for the near-misses clearly labeled DIAGNOSTIC, never conflated with the live path's own result (§4).
3. **0 predictions, 0 trades**, all 15 symbols, all day (§4, §6, §7).
4. All data-quality/infrastructure anomalies disclosed: the CandleBuilder cold-start defect — found, root-caused, reproduced, fixed, regression-tested, mutation-tested, committed (§8) — and the new fleet-wide bar-gap anomaly discovered at the final checkpoint (§9).
5. Safety status: 8 sacred files zero-diff against `main` all session; real-order path structurally disabled; all databases integrity-checked `ok` with 0 rows (§6).
6. Frozen `NO DEMONSTRATED EDGE` verdict explicitly **not** upgraded or downgraded (§11).
7. The `CandleBuilder` fix is committed (`4a26221`), pushed to `final-product-hardening`, fast-forward-merged and pushed to `main`, both verified in sync with origin.
8. Full regression suite: 2,565 passed, 0 failures, after the fix.
9. The live fleet was left running, untouched (no restarts, no code/config changes to the running processes), through this entire fix-implementation-and-report workflow, per the standing instruction.
10. This report consolidates the day's evidence per the mission's required format; no new markdown files were created beyond this dated report, following the existing `docs/LIVE_MARKET_VALIDATION_REPORT_YYYY-MM-DD.md` convention already established by the 2026-09-15 and 2026-09-16 reports.
