# Indian Trading Brain — Current Status

Last updated: 2026-09-09, mid-session of the "BUILD THE REAL
PROFIT-SEEKING INDIAN NSE TRADING BRAIN" autonomous loop. This is a
living status snapshot, not a narrative report — see `docs/
INDIAN_NSE_PREDICTION_ENGINE_REPORT.md` and `docs/
INDIAN_TRADING_DECISION_BRAIN_REPORT.md` for the fuller writeups this
distills.

## CURRENT SYSTEM STATE

Paper-trading only, structurally incapable of a real order (no
order-placement code path exists anywhere in this project). **The live
scheduler was found STOPPED at the start of this session** (last real
run was yesterday's `post_market` slot at 15:30 IST 2026-09-08; no
process was running this morning, confirmed via `Get-CimInstance
Win32_Process` — a clean stop with no crash/error in its own log, most
likely a machine restart or closed terminal overnight, not a software
defect). Restarted with the exact same established command line
(`schedule loop --watchlist-file market_data/watchlists/starter_nse.yaml
--paper-execute --initial-capital 100000 --paper-db data/paper_trading.db
--state-db data/live_state.db --live-source dhan --resilient
--staleness-seconds 120`) right at today's market open; confirmed
healthy — its `pre_market` slot completed cleanly (15 candidates
scanned, 1 BUY, 1 prediction recorded) within minutes of restart. Full
pipeline (scan → decision → critic → risk → paper) real and tested; a
`MarketRegimeReport` snapshot is persisted per shadow-run and every
`Decision` carries a `scan_id` back to it; a `daily-report` command
produces a real, ranked, evidence-labeled NSE view (now with a
cache-staleness pre-flight check); UP/DOWN/NO_EDGE directional
forecasts have their own outcome-tracking loop, independent of the
BUY-only trade-prediction journal.

## CURRENT ACTIVE EDGE STATUS

**No validated, tradeable edge exists.** This is the honest, current
answer, not a gap to be embarrassed about.

Overnight gap-fade was this project's most promising raw finding
(H_GAP_001/002) and was put through a deep, deliberately adversarial
validation this segment (H_GAP_003) — cost sensitivity, pre-specified
magnitude buckets, market-regime/VIX-regime/sector splits, a liquidity
check, and year-by-year concentration. It did not survive: the effect
is concentrated in below-median-liquidity names (nearly 6x stronger
there than in the more-liquid half of this large-cap universe), is
inert specifically when NIFTY itself is trending up, is disproportion-
ately driven by NIFTY_PHARMA on the recovery side, shows a real decay
trend (decisive 2021-2024, flat 2025-2026), and sits right at or past
the realistic cost break-even point. A superficially striking
extreme-gap (3%+) sub-finding turned out to be a small-sample illusion
that failed its own development-period check. **REJECTED as a
currently tradeable edge** — see H_GAP_003 for the full evidence.

The remaining candidate — genuinely the most-tested lead this project
has, and the honest picture is now more complicated than it looked one
research pass ago:

- Market/sector-divergence conditioning on the baseline BUY signal
  (H_CONTEXT_MARKET_002/SECTOR_002/ALIGN_001) survived an adversarial
  deep-validation pass (H_CONTEXT_MARKET_004: costs, liquidity, sector,
  time) that killed gap-fade. Following that entry's own recommended
  next step — grow the out-of-sample sample rather than slice further
  — the universe was extended from 5 to a genuine, verified 10 years of
  NSE history (H_CONTEXT_MARKET_005). The result was NOT a clean
  confirmation: the market-level condition's own sign **reverses**
  between 2016-2022 (decisively negative) and 2022-2026 (decisively
  positive) — a real, previously-undetectable time-instability the
  shorter window could never have surfaced, meaning the original
  finding may be specific to the post-2021 market era rather than a
  stable mechanism. The one genuine gain: the compound "both market and
  sector diverge" condition's out-of-sample sample grew from an
  unusable n=10 to a properly-powered, CI-decisive n=236 — solving the
  exact limitation H_CONTEXT_MARKET_004 flagged — though development
  and validation do not confirm it under the new, longer partition.
  Both facts (the instability AND the improved power) must be read
  together, not selectively.

Nothing is promoted. Nothing should be traded.

## PROMOTED HYPOTHESES

**None.** Zero, across the entire history of this project's research
(32 hypotheses tested to date).

## PROMISING HYPOTHESES

None meet the bar (decisive across all three splits with adequate OOS
power). The market/sector-divergence family survived the same
adversarial deep-validation pass that killed gap-fade — but the 10-year
re-run (H_CONTEXT_MARKET_005) then found the market-level condition's
own sign is unstable across the full available history, which is a
step BACKWARD from "promising," not forward, even though the compound
condition's OOS sample is now properly powered for the first time.

## INCONCLUSIVE HYPOTHESES (13)

H_ENTRY_003, H_ENTRY_005, H_EXIT_002, H_MEANREV_002, H_CONTEXT_MARKET_002,
H_CONTEXT_SECTOR_002, H_CONTEXT_ALIGN_001, H_CONTEXT_MARKET_004,
H_CONTEXT_MARKET_005 (the 10-year re-run — found real sign-instability
pre-2022 alongside improved OOS power for the compound condition — see
above), H_GAP_001, H_GAP_002 (the original gap-fade discovery record —
kept as history; see H_GAP_003 for why the underlying idea did not
ultimately survive), H_TRANSMISSION_001 (Nasdaq → NIFTY IT, honest
decline/advance asymmetry), and two new entries from today's session —
H_OPENRANGE_001 (real intraday opening-range research, genuinely tested
with real 15-minute Yahoo data, but the ~60-day intraday history limit
made every split fundamentally underpowered; a mild fade direction
echoed gap-fade's own finding but never reached decisive significance)
and see REJECTED below for H_SECTOR_ROTATION_001. Full evidence for
each in `strategy/hypothesis_registry.py`.

## REJECTED HYPOTHESES (18)

H_ENTRY_002, H_ENTRY_004, H_EXIT_001, H_EXIT_003, H_EXIT_004,
H_MEANREV_001, H_RELSTRENGTH_001, H_BREAKOUT_001, H_CONTEXT_MARKET_001,
H_CONTEXT_MARKET_003, H_CONTEXT_SECTOR_001, H_CONTEXT_VIX_001,
H_CONTEXT_VIX_002, H_TRANSMISSION_002, H_TRANSMISSION_003,
H_TRANSMISSION_004, H_GAP_003 (the deep-validation follow-up to
H_GAP_001/002 — see above), and H_SECTOR_ROTATION_001 (new today: a
stock's own sector's cross-sectional momentum RANK among the 9 NIFTY
sector indices, a genuinely different formulation from the earlier
binary sector-regime tests — found a real, sensible, monotonic ordinal
pattern, leading sectors beat lagging ones, but the magnitude was too
small and the "best" bucket still went decisively negative
out-of-sample). Full evidence for each in `strategy/
hypothesis_registry.py`.

(1 SUPPORTED entry, H_ENTRY_001, is itself a negative finding —
"entry timing underperforms random" — confirmatory, not an edge.)

## CURRENT PREDICTION SAMPLE SIZE

- **BUY-shaped trade predictions** (`data/predictions.db`): 10 total as
  of this writing, **all still ACTIVE, zero resolved.** The live
  scheduler's `pre_market` slot today (2026-09-09) added 1 more real
  prediction after its restart (see below) — still effectively zero
  resolved history.
- **Directional (UP/DOWN/NO_EDGE) forecasts** (`data/
  direction_forecasts.db`): 15 recorded 2026-09-08 against the live
  15-symbol watchlist (13 DOWN, 2 UP — market was in a real NIFTY
  downtrend at recording time), plus 4 OLDER real forecasts
  (RELIANCE.NS/TCS.NS/INFY.NS/HDFCBANK.NS, as_of 2026-08-25/26)
  discovered already resolved in the same database from an earlier
  debugging session — 1 correct, 3 incorrect, but **known to be built
  on a stale reference price** (see the data-integrity finding below)
  and should be excluded from any calibration read, not treated as
  real evidence either way.

Both sample sizes are far too small for any statistical conclusion.
This is the actual current bottleneck — not a missing capability.

**The live scheduler was found stopped at the start of today's
session** (2026-09-09) — last real activity was yesterday's
`post_market` slot; nothing had run overnight or this morning despite
market open approaching. Confirmed via `Get-CimInstance Win32_Process`
(authoritative, not just the tailed log) that no scheduler process was
running at all — a clean stop (no error in its own log), most likely an
overnight machine restart or closed terminal, not a bug. Restarted with
the identical established command line right at market open; confirmed
healthy within minutes (a real `pre_market` tick completed, 1 new
prediction recorded). This is disclosed here because it is exactly the
kind of "assume nothing, verify with the authoritative source" finding
this project's own research discipline keeps demonstrating the value
of — the tailed log file alone would NOT have revealed this (its last
line was a normal, non-alarming `[SKIPPED]`).

**Real data-integrity finding this segment, now fixed**: `daily-report`
had no cache-freshness check at all — `CachedMarketDataProvider` never
auto-refreshes, so a symbol whose cache silently went stale (weeks since
last refresh) still returns a normal cache HIT, meaning a forecast could
be recorded against a stale `reference_price` with zero warning. Found
by investigating exactly this happening to 4 real forecasts (see above).
Fixed: `daily-report` now runs `backtesting.cache.report_cache_staleness`
before recording anything, prints an explicit warning naming any stale
symbol (same 5-day/432000s threshold `critic/config.py`'s own
DATA_FRESHNESS check already uses), and **skips forecast recording**
for any stale candidate rather than silently recording a bad one.

## CURRENT CALIBRATION STATUS

**INSUFFICIENT_DATA**, honestly reported by the existing `learn`
command against the real production database — not a fabricated
number. Zero resolved BUY predictions means confidence calibration
cannot be evaluated yet. All 10 existing predictions happen to fall in
the MEDIUM (50–80%) confidence band; none LOW or HIGH.

## CURRENT PAPER TRADING STATUS

Structurally safe (paper-only, verified). Real trade/prediction volume
remains small. `main.py paper status` / `learn` / `evaluate` are the
existing, correct tools to track this going forward — reused, not
rebuilt, this segment.

## KNOWN DATA LIMITATIONS

- NSE circuit limits (price bands) are not modeled anywhere in this
  codebase — investigated and deliberately not built (rare on the
  large/mega-cap universe this project trades, and circuit-band data
  isn't available through the existing free Yahoo-backed path).
- No stock-split/dividend adjustment source is integrated — both
  prediction-tracking modules share a disclosed anomaly guard that
  refuses to score an affected bar rather than adjusting for it.
- `CachedMarketDataProvider`'s path-safety validator rejects any Yahoo
  ticker containing `=` (e.g. `INR=X`) — real signals on such tickers
  need an uncached fetch, a real (if minor) friction point for macro
  research.
- The NSE sector map (`market_intelligence/nse_sector_map.py`) covers
  only 20 of the 32-symbol universe, hand-built and disclosed as such.
- The live scheduler runs with no holiday-calendar configuration; real,
  sourced 2026 NSE holiday dates are documented in `docs/
  INDIAN_NSE_PREDICTION_ENGINE_REPORT.md` §13 for the operator to apply
  deliberately (a config file was tried and reverted this segment after
  it was found to have an unintended side effect on dashboard
  behavior — see that report for the full story).

## BIGGEST RISKS

1. **Evidence starvation, not architecture gaps.** The system can now
   express and track everything the mission asks for; what it lacks is
   elapsed time and resolved outcomes. No amount of further engineering
   fixes this — only continued, undisturbed live observation does.
2. **Regime/era-dependence hiding behind a 5-year window.** The single
   most important lesson from H_CONTEXT_MARKET_005: a finding that
   looked stable across a 5-year sample reversed sign entirely in the
   6 years before that window. Every remaining INCONCLUSIVE hypothesis
   in this registry was ALSO only ever tested on 5 years of data
   (or less) — this specific risk has not been checked for any of them
   yet, and should be treated as a standing methodological gap, not a
   one-off finding specific to the divergence family.
3. **Small-sample illusions hiding inside a real-looking pooled
   result.** H_GAP_003's own extreme-gap sub-finding (a huge, exciting-
   looking +0.745% pooled effect that turned out to have zero support
   in its own development period once split by percentile/threshold)
   is a concrete, freshly-demonstrated example of why every promising
   number from this point forward must be re-split into dev/val/oos and
   checked for per-symbol sample size before being trusted, even when
   it emerges from an otherwise-legitimate pre-specified bucket scheme.
4. **The temptation to cite only the favorable half of a mixed
   result.** H_CONTEXT_MARKET_005 found genuine improvement (the
   compound condition's OOS sample is now properly powered) AND a
   genuine complication (sign instability pre-2022) in the SAME run.
   Both must be carried forward together in any future summary of this
   line of research.

## NEXT HIGHEST-VALUE RESEARCH QUESTION

Given the evidence-starvation finding above, the single highest-EV
action is **not another new hypothesis** — it is time: let the 15 real
directional forecasts recorded 2026-09-08 (and the 10-11 existing BUY
predictions) resolve, then re-run `evaluate-forecasts`/`evaluate`/
`learn` for the first real calibration read this project has ever had.

If a genuinely new research question is wanted before then: **the
10-year NSE cache is now available for every symbol in this universe —
re-run the era-stability check H_CONTEXT_MARKET_005 just did on the
divergence family against every other still-INCONCLUSIVE hypothesis**
(gap-fade already REJECTED, so lower priority; H_MEANREV_002 and
H_TRANSMISSION_001 were both 5-year-or-shorter US/global-linked studies
worth the same scrutiny). A finding that only ever survived a 5-year
window has not yet earned the same confidence as one checked against
the decade this project's own data now makes available for free.

Two new negative-knowledge findings from 2026-09-09, worth remembering
so they aren't re-investigated blindly: (1) sector momentum RANK
(leading vs. lagging among the 9 NIFTY sector indices, distinct from
the already-tested binary sector-regime conditioning) shows a real but
too-small, too-unstable effect (H_SECTOR_ROTATION_001, REJECTED) — the
next genuinely different sector-related question, if pursued, should
probably look at something other than momentum ranking specifically.
(2) Real intraday opening-range research is now possible via this
project's existing Yahoo-backed data path (confirmed: real 5m/15m/30m/
60m bars, ~60 trading days of history) — but that ~60-day window is
fundamentally too short for this project's own dev/val/oos rigor
(H_OPENRANGE_001, INSUFFICIENT_DATA/INCONCLUSIVE) and should not be
revisited on the same window; either wait for more calendar time to
accumulate or source a longer-history intraday provider before trying
Family A again.
