# Monday Live Validation Plan

Strategy science mission, Phase 14. Written on Saturday, 2026-09-05, with
markets closed — nothing in this document may be described as "LIVE MARKET
VERIFIED" (that label requires it to actually happen during a real market
session). This is a concrete, checkable plan for the next trading day, not
a claim that live validation has already occurred.

**Verify before relying on this**: no exchange holiday calendar is
integrated anywhere in this project (`live/dhan/market_session.py`'s own
documented limitation). Confirm Monday 2026-09-07 is a genuine NSE/BSE
trading day against the exchange's own published holiday calendar before
following this plan — this document does not and cannot verify that itself.

## Step 0 — structural pre-flight (can be run any time before Monday)

Run:

```bash
python main.py readiness-check --symbols RELIANCE.NS,TCS.NS,INFY.NS
```

Added this phase (`main.py`'s `readiness-check` command,
`live/workstation.py`'s new `get_kill_switch_status()`). Checks, in order:

1. **Dhan credentials configured** (`DHAN_CLIENT_ID`/`DHAN_ACCESS_TOKEN` env
   vars present) — `[FAIL]` and exit code 1 if missing. Never prints the
   actual values.
2. **Current market session state** (informational only — will correctly
   show CLOSED right now on a Saturday).
3. **Kill switch state** — `[WARN]` if currently active (decide whether
   that's intentional before starting).
4. **Leftover pending approvals** from a prior session — `[WARN]` if any
   exist; review them (approve/reject/let them expire) before starting
   fresh, so Monday's session isn't confused by stale state.
5. **Historical cache freshness** for the given symbols (informational —
   irrelevant to the live feed itself, relevant only if also comparing
   against a same-day backtest).

This is a **structural** check only. It cannot and does not verify the
live WebSocket feed, order routing, or fill behavior — those genuinely
require a real market session.

## Step 1 — start a short, supervised session at market open

09:15 IST is the start of continuous trading (`PRE_OPEN` runs 09:00–09:15,
worth watching too if validating pre-open behavior specifically).
Recommended first run:

```bash
python main.py paper-live --source dhan --symbol RELIANCE.NS --interval 1m --period 1d
```

Watch, in the terminal and the dashboard (`python main.py dashboard`) in a
second window:

- **Feed status table**: does `source` show `DHAN` and `status` show
  `LIVE`, with `connection_state` reaching `CONNECTED`? (See
  `docs/NEWS_MARKET_INTELLIGENCE_AUDIT.md` — the dashboard banner now
  correctly reflects this instead of a stale hardcoded claim.)
- **Bar cadence**: for `--interval 1m`, a new bar roughly once a minute
  during active trading, not immediately (the first bar only completes once
  a tick from the *next* minute bucket arrives — see
  `live/dhan/candle_builder.py`'s documented "no synthetic bar" policy).
- **No crash, no unhandled exception**, across at least 30–60 minutes of
  continuous operation.
- **CandleBuilder rejection warnings** (Phase 13's new tick-plausibility
  check) — check the log for `"rejecting a non-positive-price tick"` /
  `"rejecting an implausible tick"` messages. Zero is expected for a real
  feed; if any appear, note the symbol/price/timestamp and investigate
  whether it's a genuine feed anomaly or a false positive from the 20%
  threshold (adjust `max_tick_deviation_pct` if a legitimately volatile
  instrument trips it).

## Step 2 — deliberately exercise the approval workflow

With `--no-human-approval` **not** set (the default), let at least one real
signal reach `PENDING_HUMAN_APPROVAL` and manually APPROVE or REJECT it via
the dashboard. Confirms the human-in-the-loop gate genuinely blocks
auto-execution end-to-end during a live session, not just in tests.

## Step 3 — deliberately test the kill switch mid-session

```bash
python main.py paper-live --kill-switch --kill-switch-reason "Monday validation drill"
```

While the feed is live, confirm: no new signal reaches
`PENDING_HUMAN_APPROVAL` while active; the dashboard's kill-switch banner
shows active immediately. Then:

```bash
python main.py paper-live --reset-kill-switch
```

Confirm normal operation resumes.

## Step 4 — deliberately test a disconnect (if feasible)

Briefly disable network access (or use a firewall rule to block
`api-feed.dhan.co`) for under a minute, then restore it. Confirm the
reconnect logic (`DhanMarketDataSource`, bounded exponential backoff,
tested extensively per `docs/LIVE_DATA_STRESS_TESTING.md`) actually
recovers in a real environment, not just in the mocked unit tests. Note
whether any bars were skipped across the gap, and whether that matches
Phase 13's documented (not yet fixed) concern about a stop/target
potentially not triggering across a data gap — if a position happens to be
open when this test runs, watch this specifically.

## What would make this session "LIVE MARKET VERIFIED"

Only claim this label, and only for the specific things actually observed:
a genuinely `CONNECTED`/`LIVE` feed status sustained for a meaningful
duration, at least one real bar built from real ticks, at least one signal
correctly reaching human approval, and (if exercised) a kill-switch
activation/reset and a reconnect both behaving correctly. Do not
generalize "the feed connected once" into "the live pipeline is fully
validated" — note explicitly which of the above steps were actually run
and which were skipped, honestly, in whatever record of the session is
kept afterward (following this project's own established evidence-grading
convention — see `docs/MARKET_DATA_SOURCES.md` for the style).
