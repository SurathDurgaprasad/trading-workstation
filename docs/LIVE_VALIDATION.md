# Live validation — index

This project ran six real market-hours sessions against the live Dhan NSE feed between
2026-09-07 and 2026-09-23. This page summarizes why, what was and wasn't validated, and
points to the full dated reports. **None of these sessions validated trading
profitability** — the strategy has no demonstrated edge (see
[`RESEARCH_RESULTS.md`](RESEARCH_RESULTS.md)), and no session placed a real order (see
[`SAFETY.md`](SAFETY.md)). What they validated was operational: does the live-data
pipeline, candle construction, fleet supervision, and dashboard behave correctly against
a real, adversarial, unpredictable market-data feed.

## Why Dhan, and why paper-only

Dhan was chosen as the one real broker/market-data integration this project built
(`live/dhan/`) — a real DhanHQ v2 REST + WebSocket client. It is used **exclusively for
market data and read-only account state**; every order-mutating method is structurally
disabled (`DisabledDhanOrderExecutor`, see [`SAFETY.md`](SAFETY.md)). Real market data
was worth validating against because simulated/replayed data cannot exercise real
connection drops, real out-of-order or duplicate ticks, real exchange-side rate limits,
or real multi-hour operational drift — all things a paper-trading engine still needs to
handle correctly even though it will never place a real order.

## Session history

| Date | Scope | Key findings |
|---|---|---|
| 2026-09-07 | First live session — single symbol, real REST/WS, kill-switch drill | Found ~130s clock drift (later resynced), no prediction↔order link yet, reconnect untested live — all disclosed as gaps, not failures |
| 2026-09-15 | Second session — real prediction recording during real market hours | 322 real bars, one real ~15-minute feed gap correctly detected and suppressed rather than traded on |
| 2026-09-16 | First 15-symbol fleet session | 4,185 real bars, 100% fresh; an unplanned simultaneous stop of all 15 workers (later traced to a host machine reboot, not a code defect) |
| 2026-09-17 | Second fleet session | Found and fixed a real `CandleBuilder` cold-start timestamp defect (one symbol's bar corruption, ~9,881 tick rejections) |
| 2026-09-22 | Fresh fleet session, post-hardening | Zero worker crashes across the full session; strategy explicitly frozen and unmodified |
| 2026-09-23 | Final validation of the remediated build | 4,995 bars, 99.7% fresh; one ~15-minute fleet-wide feed gap self-healed correctly; one low-severity engineering finding (harmless double process re-exec) |

Full reports: `docs/LIVE_MARKET_VALIDATION_REPORT*.md` (one per dated session).

## What was validated

- **Real connectivity**: real REST account calls, a real WebSocket handshake, real
  market packets and OHLCV bars reaching the unmodified strategy/risk/paper pipeline.
- **`CandleBuilder` correctness under real data**: tick ordering, deduplication
  (`is_likely_redelivered_duplicate`), and invalid-tick rejection, including a real
  defect found and fixed (2026-09-17 cold-start timestamp corruption) and one disclosed,
  deliberately-not-fixed low-severity issue (`G13` — a poisoned first tick in a bucket
  can freeze that bucket's `close`; no cheap safe fix exists, risk judged narrow).
- **Reconnect behavior**: idle-timeout reconnects (`connected_idle_timeout_seconds`,
  300s), a Dhan-side 5-connections-per-client-ID cap (`code=805`), and multiple
  occurrences of an unexplained, unresolved ~15-minute fleet-wide interruption pattern —
  the resilience mechanisms handled all of these correctly, but this specific recurring
  pattern's root cause remains genuinely unproven despite investigation (see
  `docs/DHAN_FEED_INTERRUPTION_1514_INVESTIGATION_2026-09-22.md`).
- **Stale-data handling**: `FreshnessPolicy` suppression of late-arriving bars
  (`STALE_SIGNAL_SUPPRESSED`), verified to correctly prevent a stale bar from either
  generating a new signal or filling/closing an existing position.
- **Dashboard honesty**: the dashboard correctly distinguishes live vs. stale state and
  was found (and fixed) to have a real dual-writer race — the dashboard and a CLI
  session could evaluate a decision against a stale, process-cached account snapshot —
  closed via `PaperTradingEngine.refresh_account()` plus `PaperStore.transaction()`
  switching to SQLite's `BEGIN IMMEDIATE`, both proven with real multi-connection
  concurrency tests.
- **Fleet health semantics**: a worker being alive (process exists) is not the same as
  healthy — health requires a fresh heartbeat *and* fresh data *and* internal
  coherence, checked explicitly rather than inferred from process existence alone.

## What was explicitly NOT observed

- **A naturally-occurring trading signal reaching the risk engine, human approval, and
  paper execution, end to end, on a live session.** Every live session run so far has
  honestly produced zero or very few natural signals (the frozen strategy rarely fires,
  and per the research verdict, would not be worth trading if it did) — never a
  fabricated or forced one. The full mechanism has been proven correct against real
  *historical* data replay, which is a real but weaker form of verification than an
  observed live signal.
- **BSE live connectivity** — code-complete and unit-tested via the same Dhan
  integration, but never exercised against a real live BSE feed. Do not treat it as
  equivalent to the NSE evidence above.
- **Multi-day or multi-week continuous operation** — sessions ran for single trading
  days (up to ~6h22m), not sustained unattended weeks.

## Why live validation stopped

Live validation stopped when the research program itself closed (§18,
[`EDGE_DISCOVERY_FINAL_REPORT.md`](EDGE_DISCOVERY_FINAL_REPORT.md)): with no
demonstrated trading edge, there is nothing further that spending Dhan API quota on live
data can validate about *trading performance* — only about engineering behavior that
offline testing and replay can also exercise, at zero cost. Further live sessions were
therefore not authorized as part of ordinary engineering work; live-data usage is
economically justified only if an offline hypothesis first clears the promotion gate
(`docs/RESEARCH_METHODOLOGY.md`), which none has.
