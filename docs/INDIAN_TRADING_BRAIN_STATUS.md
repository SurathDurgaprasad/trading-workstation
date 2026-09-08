# Indian Trading Brain — Current Status

Last updated: 2026-09-08, end of the "INDIAN NSE EDGE VALIDATION AND
LEARNING LOOP" mission segment. This is a living status snapshot, not a
narrative report — see `docs/INDIAN_NSE_PREDICTION_ENGINE_REPORT.md`
and `docs/INDIAN_TRADING_DECISION_BRAIN_REPORT.md` for the fuller
writeups this distills.

## CURRENT SYSTEM STATE

Paper-trading only, structurally incapable of a real order (no
order-placement code path exists anywhere in this project). Live
scheduler (`schedule loop --paper-execute --live-source dhan`) has run
continuously and untouched throughout this segment; last real tick
completed its `post_market` slot at 15:30 IST 2026-09-08 and has been
correctly idling since (`[SKIPPED] No configured slot is due at this
time.`) — market closed, nothing due until tomorrow. Full pipeline
(scan → decision → critic → risk → paper) real and tested; a
`MarketRegimeReport` snapshot is now persisted per shadow-run and every
`Decision` carries a `scan_id` back to it; a `daily-report` command
produces a real, ranked, evidence-labeled NSE view; UP/DOWN/NO_EDGE
directional forecasts now have their own outcome-tracking loop,
independent of the BUY-only trade-prediction journal.

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

The remaining candidate — and now this project's single most credible
lead:

- Market/sector-divergence conditioning on the baseline BUY signal
  (H_CONTEXT_MARKET_002/SECTOR_002/ALIGN_001) has now ALSO been through
  the same adversarial deep-validation gap-fade received (H_CONTEXT_
  MARKET_004) and, unlike gap-fade, **substantially strengthened**: it
  clears realistic costs with wide margin (still solidly positive even
  at a 0.30% round-trip cost, well past the ~0.21% realistic estimate),
  is CI-decisive in BOTH the above- and below-median liquidity halves
  of the universe (not confined to illiquid names, the exact check that
  killed gap-fade), is not dominated by a single sector, and shows no
  clean year-over-year decay pattern. It is directly implementable with
  the EXISTING long-only, multi-bar-hold backtesting engine — no new
  execution infrastructure needed, unlike gap-fade. What it still lacks
  is out-of-sample statistical POWER (as low as n=10 for the compound
  market+sector condition) — a sample-size problem, not a robustness
  problem, and the correct next step is growing that sample, not more
  adversarial slicing of what already exists.

Nothing is promoted. Nothing should be traded.

## PROMOTED HYPOTHESES

**None.** Zero, across the entire history of this project's research
(29 hypotheses tested to date).

## PROMISING HYPOTHESES

None formally meet the bar yet (decisive across all three splits with
adequate OOS power) — but the market/sector-divergence family is now
the closest this project has come: it has survived the same adversarial
deep-validation pass that killed gap-fade, and its only remaining gap is
out-of-sample sample size, not a demonstrated flaw.

## INCONCLUSIVE HYPOTHESES (11)

H_ENTRY_003, H_ENTRY_005, H_EXIT_002, H_MEANREV_002, H_CONTEXT_MARKET_002,
H_CONTEXT_SECTOR_002, H_CONTEXT_ALIGN_001, H_CONTEXT_MARKET_004 (the deep-
validation follow-up — see above), H_GAP_001, H_GAP_002 (the original
gap-fade discovery record — kept as history; see H_GAP_003 for why the
underlying idea did not ultimately survive), and H_TRANSMISSION_001
(Nasdaq → NIFTY IT, honest decline/advance asymmetry). Full evidence for
each in `strategy/hypothesis_registry.py`.

## REJECTED HYPOTHESES (17)

H_ENTRY_002, H_ENTRY_004, H_EXIT_001, H_EXIT_003, H_EXIT_004,
H_MEANREV_001, H_RELSTRENGTH_001, H_BREAKOUT_001, H_CONTEXT_MARKET_001,
H_CONTEXT_MARKET_003, H_CONTEXT_SECTOR_001, H_CONTEXT_VIX_001,
H_CONTEXT_VIX_002, H_TRANSMISSION_002, H_TRANSMISSION_003,
H_TRANSMISSION_004, H_GAP_003 (the deep-validation follow-up to
H_GAP_001/002 — see above). Full evidence for each in `strategy/
hypothesis_registry.py`.

(1 SUPPORTED entry, H_ENTRY_001, is itself a negative finding —
"entry timing underperforms random" — confirmatory, not an edge.)

## CURRENT PREDICTION SAMPLE SIZE

- **BUY-shaped trade predictions** (`data/predictions.db`): 10 total,
  **all still ACTIVE, zero resolved.**
- **Directional (UP/DOWN/NO_EDGE) forecasts** (`data/
  direction_forecasts.db`): 15, recorded this segment against the live
  15-symbol watchlist (13 DOWN, 2 UP — market was in a real NIFTY
  downtrend at recording time) — the first real forecast history this
  project has ever had. All unresolved as of this writing (recorded
  same-day, horizon not yet elapsed).

Both sample sizes are far too small for any statistical conclusion.
This is the actual current bottleneck — not a missing capability.

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
2. **Out-of-sample power, specifically for the now-strengthened
   market/sector-divergence family.** It has survived every robustness
   check thrown at it (cost, liquidity, sector, time) — but robustness
   on the full-period sample is not the same claim as decisive
   out-of-sample performance, and the OOS sample for the compound
   condition is as thin as n=10. Promoting on robustness alone, without
   growing that sample first, would still be premature.
3. **Small-sample illusions hiding inside a real-looking pooled
   result.** H_GAP_003's own extreme-gap sub-finding (a huge, exciting-
   looking +0.745% pooled effect that turned out to have zero support
   in its own development period once split by percentile/threshold)
   is a concrete, freshly-demonstrated example of why every promising
   number from this point forward must be re-split into dev/val/oos and
   checked for per-symbol sample size before being trusted, even when
   it emerges from an otherwise-legitimate pre-specified bucket scheme.

## NEXT HIGHEST-VALUE RESEARCH QUESTION

Given the evidence-starvation finding above, the single highest-EV
action is **not another new hypothesis** — it is time: let the 15 real
directional forecasts recorded 2026-09-08 (and the 10 existing BUY
predictions) resolve, then re-run `evaluate-forecasts`/`evaluate`/
`learn` for the first real calibration read this project has ever had.

If a genuinely new research question is wanted before then: **grow the
out-of-sample sample for the market/sector-divergence family**
(H_CONTEXT_MARKET_004's own stated correct next step) — a longer
history and/or a larger, better-sourced NSE sector map (currently only
20 of 32 universe symbols are sector-tagged) would directly attack the
one remaining, demonstrated gap in this project's strongest current
candidate, rather than another new hypothesis family.
