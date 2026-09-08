# Indian Trading Brain — Current Status

Last updated: 2026-09-08, end of the "BUILD A REAL PROFIT-SEEKING
INDIAN NSE TRADING BRAIN" mission segment. This is a living status
snapshot, not a narrative report — see `docs/
INDIAN_NSE_PREDICTION_ENGINE_REPORT.md` and `docs/
INDIAN_TRADING_DECISION_BRAIN_REPORT.md` for the fuller writeups this
distills.

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
answer, not a gap to be embarrassed about. The closest candidates:

- Market/sector-divergence conditioning on the baseline BUY signal
  (H_CONTEXT_MARKET_002/SECTOR_002/ALIGN_001): real, broad-based,
  cost-surviving, replicated at two independent context layers and
  appears to compound — but out-of-sample power is too thin (as low as
  n=10 for the combined condition) to promote.
- Overnight gap-fade (H_GAP_001/002): the single most statistically
  consistent raw price-behavior finding in this project's history
  (broad-based across 26+ of 32 symbols, never reverses sign across any
  split) — but the effect size is comparable to or smaller than
  realistic NSE intraday round-trip costs in most splits, and this
  project's execution engine is structurally long-only with no same-day
  forced-exit mechanism, so it isn't even implementable as a strategy
  yet regardless of the cost question.

Neither is promoted. Neither should be traded.

## PROMOTED HYPOTHESES

**None.** Zero, across the entire history of this project's research
(27 hypotheses tested to date).

## PROMISING HYPOTHESES

None currently meet the bar for "promising" (decisive across all three
splits with adequate OOS power) — the two INCONCLUSIVE candidates above
are the closest, but are explicitly not there yet.

## INCONCLUSIVE HYPOTHESES (10)

H_ENTRY_003, H_ENTRY_005, H_EXIT_002, H_MEANREV_002, H_CONTEXT_MARKET_002,
H_CONTEXT_SECTOR_002, H_CONTEXT_ALIGN_001, H_GAP_001, H_GAP_002, and
H_TRANSMISSION_001 (Nasdaq → NIFTY IT, honest decline/advance
asymmetry). Full evidence for each in `strategy/hypothesis_registry.py`.

## REJECTED HYPOTHESES (16)

H_ENTRY_002, H_ENTRY_004, H_EXIT_001, H_EXIT_003, H_EXIT_004,
H_MEANREV_001, H_RELSTRENGTH_001, H_BREAKOUT_001, H_CONTEXT_MARKET_001,
H_CONTEXT_MARKET_003, H_CONTEXT_SECTOR_001, H_CONTEXT_VIX_001,
H_CONTEXT_VIX_002, H_TRANSMISSION_002, H_TRANSMISSION_003,
H_TRANSMISSION_004. Full evidence for each in `strategy/
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
2. **Temptation to lower the promotion bar.** Two INCONCLUSIVE
   candidates (context-divergence, gap-fade) are genuinely the most
   interesting results this project has produced. Promoting either
   before out-of-sample power or cost-survival is actually demonstrated
   would be exactly the "manufactured profitability" this mission
   explicitly forbids.
3. **Execution-infrastructure gap for gap-fade.** If that line of
   research is ever pursued further, this project has no same-day
   intraday exit mechanism and no short-selling capability — pursuing
   it without building (and re-auditing for safety) that infrastructure
   first would be premature.

## NEXT HIGHEST-VALUE RESEARCH QUESTION

Given the evidence-starvation finding above, the single highest-EV
action is **not another new hypothesis** — it is time: let the 15 real
directional forecasts recorded this segment (and the 10 existing BUY
predictions) resolve, then re-run `evaluate-forecasts`/`evaluate`/
`learn` for the first real calibration read this project has ever had.

If a genuinely new research question is wanted before then: **does the
gap-fade effect (H_GAP_001) hold when conditioned on market regime**
(does it strengthen in a NIFTY downtrend, where broad selling pressure
might mechanically produce more gap-ups-to-fade, or is it regime-
independent)? This is a natural, narrow, evidence-informed follow-up —
not a new family, a refinement of the strongest raw finding this
project has, using infrastructure that already exists.
