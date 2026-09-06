# Monday Live Validation Plan

Originally written Strategy science Phase 14 (Saturday, 2026-09-05).
**Updated** by the LIVE MARKET READINESS audit (2026-09-06) with:
corrected holiday-calendar guidance (a real fix now exists — see Step 0),
the corrected two-pipeline architecture (Step 1 below explains which
command actually exercises which chain — this was previously ambiguous),
the new `implausible_timestamp` rejection category, and full
COMMAND/EXPECTED RESULT/FAILURE CONDITION/RECOVERY ACTION structure per
that mission's own Phase 13 requirement. Nothing in this document may be
described as "LIVE MARKET VERIFIED" until it actually happens during a
real market session — this is a concrete, checkable plan, not a claim
that live validation has already occurred.

**This platform has NO DEMONSTRATED TRADING EDGE** (see
`docs/STRATEGY_EDGE_DISCOVERY_FINAL_OUTPUT.md`). Every step below
validates PLATFORM OBSERVATION and PAPER-ONLY mechanics — never treat a
successful run as evidence the strategy is profitable.

## Architecture note — READ THIS FIRST

This codebase has **two separate pipelines** that are never wired
together:

1. **`shadow-run`** (optionally `--paper-execute`, or via `schedule
   tick`/`loop`): Yahoo-scanned candidates → `decision_engine` →
   `critic` → `risk` → paper execution. `--live-source dhan` only
   overlays a live Dhan PRICE onto Yahoo-scanned candidates — it does
   **not** drive the scan itself with live ticks.
2. **`paper-live`/`live-sim`** (`--source dhan`): a genuine live Dhan
   WebSocket feed → `TrendMomentumBaseline` (or another registered
   `Strategy`, NOT `decision_engine`) → `risk` → paper execution.

**There is no single command that validates "real Dhan ticks feeding
the full decision_engine/critic/scanner chain"** — that integration
does not exist in the codebase today (see the readiness report's
Section 2 for detail). Decide which pipeline you are validating before
you start, and do not conflate a `paper-live --source dhan` session
(proves the live feed) with a `shadow-run` session (proves the decision
chain) — Monday's validation needs both, run separately.

## Before market

| # | Command | Expected result | Failure condition | Recovery action |
|---|---|---|---|---|
| B1 | `git status && git log --oneline -1` | Clean tree, HEAD is the commit you intend to run | Uncommitted changes, unexpected HEAD | Stash/commit or `git checkout` to the intended commit before proceeding |
| B2 | `python -m pytest tests/ -q` | All tests pass | Any failure | Do not proceed to a live session on a red test suite — fix or revert first |
| B3 | Copy `config/schedule.yaml.example` to `config/schedule.yaml` and fill in the real NSE holiday dates for the current year from [NSE's own published circular](https://www.nseindia.com/resources/exchange-communication-holidays) | File exists with real dates, `holidays:` populated | File missing or still has only commented-out example dates | Populate it now — every command below auto-detects this path; skipping it means every session runs holiday-blind |
| B4 | `python main.py readiness-check --symbols RELIANCE.NS,TCS.NS,INFY.NS` | `[PASS]` credentials, `[INFO]` session state cross-checked against N configured holiday dates, `[PASS]` kill switch inactive, `[PASS]` no leftover pending approvals | `[FAIL]` credentials (env vars not set in THIS shell), `[INFO]` says "No holiday calendar was supplied" (B3 skipped or path wrong), `[WARN]` kill switch active, `[WARN]` leftover pending approvals | Set `DHAN_CLIENT_ID`/`DHAN_ACCESS_TOKEN` in your shell (never in source); fix B3; review/clear leftover state via the dashboard before starting fresh |
| B5 | `python main.py dashboard` in its own terminal, then open `http://127.0.0.1:8765` | Page loads, shows the amber "SCIENTIFIC STRATEGY VERDICT: NO DEMONSTRATED EDGE" banner, market status CLOSED (pre-market) or correct PRE_OPEN/OPEN, kill switch INACTIVE | Page fails to load, banner missing, wrong market status | Check the dashboard process's own stderr; if the verdict banner or holiday cross-check is missing, confirm you're running the commit with this audit's fixes (`git log` should show `965e51c` or later) |
| B6 | `python main.py cache-status --symbols RELIANCE.NS` | Reports cache age (informational — irrelevant to the live feed itself) | N/A — informational only | N/A |

## Market open (09:15 IST)

PRE_OPEN runs 09:00–09:15 IST, worth watching too if validating that
window specifically.

| # | Command | Expected result | Failure condition | Recovery action |
|---|---|---|---|---|
| M1 | `python main.py paper-live --source dhan --symbol RELIANCE.NS --interval 1m --period 1d --schedule-config config/schedule.yaml` | Startup banner shows `MARKET SESSION: PRE_OPEN` or `OPEN`, cross-checked against your configured holidays; "This process places NO real orders" line present | Session shows CLOSED at 09:15+ on a real trading day, or the holiday cross-check line is missing | If CLOSED when it should be OPEN: check system clock/timezone. If the holiday line is missing: confirm `--schedule-config` path is correct |
| M2 | Watch the dashboard's MARKET FEED table | `source=DHAN`, `status=LIVE`, `connection`→`CONNECTED` within a few seconds | Stuck at `CONNECTING`/`RECONNECTING`, or `status` never reaches `LIVE` | Check `DHAN_CLIENT_ID`/`DHAN_ACCESS_TOKEN` are valid (not just present); check Dhan's own service status; check firewall/network egress to `api-feed.dhan.co` |
| M3 | Watch for the first completed bar (`--interval 1m`: roughly once a minute) | A new `Last Bar` timestamp appears in the feed table, `Data Age` stays low | No bar after 2-3 minutes of a connected feed during active trading | Check terminal for `CandleBuilder` rejection warnings (see M4); a genuinely silent bucket produces no bar by design (not a bug) — confirm via a broker terminal that the symbol is actually trading |
| M4 | Check terminal/log output for `CandleBuilder(...): rejecting a ...` warnings | Zero rejections for a healthy feed | Any `non_positive_price`, `negative_volume`, `implausible_deviation`, `implausible_timestamp`, or `late_out_of_order` warning | Note the exact symbol/price/timestamp/skew. `implausible_timestamp` (new this audit — a tick whose timestamp differs from the last real one by more than `max_timestamp_skew_seconds`, default 1 hour) firing on a healthy connection would indicate a genuine Dhan data-quality issue worth escalating, not adjusting the threshold reflexively |

## During market

| # | Command | Expected result | Failure condition | Recovery action |
|---|---|---|---|---|
| D1 | Let at least one real signal reach `PENDING_HUMAN_APPROVAL` (default: human approval required); APPROVE or REJECT via the dashboard | Approval/rejection recorded, dashboard updates, journal entry created | Signal auto-executes without stopping for approval | Confirm `--no-human-approval` was not accidentally passed |
| D2 | `python main.py paper-live --kill-switch --kill-switch-reason "Monday validation drill"` while the feed is live | No new signal reaches `PENDING_HUMAN_APPROVAL` while active; dashboard kill-switch banner shows active immediately | A signal is approved/executed while the kill switch is active | This would be a serious safety-control regression — stop the session and investigate before any further live use |
| D3 | `python main.py paper-live --reset-kill-switch` | Normal operation resumes; new signals can reach approval again | Kill switch stays active after reset | Check `live_state.db` directly via `python main.py paper-live --state-db ...` or the dashboard for a stuck lock |
| D4 | Restart the `paper-live` process mid-session (Ctrl+C, then re-run the same command) | Pending approvals, positions, and kill-switch state are recovered exactly as they were (proven by `tests/test_paper_restart.py`'s Level-3 restart tests) — no duplicate execution, no lost state | A signal executes twice after restart, a pending approval silently disappears, or account P&L differs from before the restart | This would contradict already-passing regression tests — capture the exact DB state (`paper.db`, `live_state.db`) before investigating further, do not overwrite it |
| D5 | (If feasible) Briefly block network access to `api-feed.dhan.co` for under a minute, then restore it | Bounded exponential-backoff reconnect logic recovers automatically (see `docs/LIVE_DATA_STRESS_TESTING.md`); dashboard feed status reflects the disconnect/reconnect in real time | Feed never reconnects, or reconnects but silently drops/duplicates bars across the gap | Known, documented, NOT YET FIXED concern: a stop/target crossed entirely within a disconnect gap may not trigger correctly (see the readiness report's Remaining Risks). If a position was open during this drill, check its outcome carefully |

## Failure testing (deliberate, only where safe per D2-D5 above)

Covered inline in the During Market table (D2/D3 kill switch, D4
restart, D5 disconnect) — run these deliberately, do not skip them as
"probably fine."

## After market (15:30 IST close, or session end)

| # | Command | Expected result | Failure condition | Recovery action |
|---|---|---|---|---|
| A1 | Stop `paper-live` cleanly (Ctrl+C) | Process exits without an unhandled exception | Traceback on shutdown | Note the traceback; check whether it happened during an in-flight order (a real gap worth fixing if so) |
| A2 | `python main.py paper live journal --db <path>` (or the dashboard's JOURNAL section) | Every signal generated today has a journal entry with a terminal or explicable non-terminal outcome | A signal with no journal entry, or stuck at a non-terminal state with no clear reason | Cross-reference against terminal output/logs from the session; this is exactly the observability gap flagged in the readiness report (no single correlation ID ties a decision to its paper execution outcome today) — manual cross-referencing by symbol/timestamp is the only current option |
| A3 | If `shadow-run --paper-execute` or `schedule tick/loop` also ran today: `python main.py evaluate --predictions-db ...` then check `predictions.db` vs `paper.db` agree on outcome for the same symbol/day | Consistent outcomes | A prediction shows `TARGET_HIT` while its paper order was REJECTED/never filled (a known, documented architecture gap — predictions are recorded before the execution/critic gate runs) | Not a bug to "fix" on the spot — note it, matches the readiness report's own documented finding |
| A4 | Check `data/*.db` files exist and are non-empty; back them up if this was a meaningful session | Files present, sizes reasonable | Empty/missing DB file despite a session that should have written to it | Check the `--*-db` paths actually used matched what you expected; SQLite files are gitignored, so nothing here was ever meant to be committed |
| A5 | Review the full terminal/log output for this session for any `CandleBuilder` rejection counts, reconnect events, or unexpected warnings not already investigated above | A clear, written account of what happened (see "What would make this session LIVE MARKET VERIFIED" below) | N/A | N/A |

## What would make this session "LIVE MARKET VERIFIED"

Only claim this label, and only for the specific things actually
observed: a genuinely `CONNECTED`/`LIVE` feed status sustained for a
meaningful duration, at least one real bar built from real ticks, at
least one signal correctly reaching human approval, and (if exercised)
a kill-switch activation/reset, a restart, and a reconnect all behaving
correctly. Do not generalize "the feed connected once" into "the live
pipeline is fully validated" — note explicitly which of the steps above
were actually run and which were skipped, honestly, in whatever record
of the session is kept afterward (following this project's own
established evidence-grading convention — see
`docs/MARKET_DATA_SOURCES.md` for the style). And regardless of how
well this session goes: **it validates platform observation and
paper-only mechanics, never trading profitability.**
