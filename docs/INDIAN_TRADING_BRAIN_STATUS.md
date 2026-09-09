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
scheduler stopped TWICE this same session** — once overnight (found
stopped at session start, restarted at market open) and once again
mid-session (confirmed alive at ~10:07 IST, gone by ~10:48 IST — no
error anywhere in its own log both times, just a clean stop right after
a normal, successful tick). Restarted both times with the identical
established command line; confirmed healthy each time via
`Get-CimInstance Win32_Process` (never trust the tailed log file's own
apparent freshness alone — it looked perfectly normal both times right
up to the silent stop) and `scheduler_runs.db`. **This recurring pattern
(clean, errorless, mid-session stops) is now itself worth flagging as
an operational risk** — see Known Data Limitations / Biggest Risks
below; the root cause (machine sleep/terminal closure vs. something
else) has not been identified and is outside what this session can
diagnose from inside the process itself. Full pipeline (scan → decision
→ critic → risk → paper) real and tested; a `MarketRegimeReport`
snapshot is persisted per shadow-run and every `Decision` carries a
`scan_id` back to it; a `daily-report` command produces a real, ranked,
evidence-labeled NSE view (now with a cache-staleness pre-flight
check); UP/DOWN/NO_EDGE directional forecasts have their own
outcome-tracking loop, independent of the BUY-only trade-prediction
journal.

## CURRENT ACTIVE EDGE STATUS

**No validated, tradeable edge exists.** This is the honest, current
answer, not a gap to be embarrassed about — but the gap has narrowed
significantly today.

**New today, and by a wide margin the strongest, most rigorously-
validated finding in this project's history**: `H_XSECT_001`, a genuine
CROSS-SECTIONAL momentum ranking (rank all 32 universe stocks by
trailing 60-day return, buy the bottom quintile "laggards," hold 20
days) — a capability this project never had before today
(`quant_research/cross_sectional.py`, new). Decisive and POSITIVE in
ALL THREE splits, never reversing (development +1.53%, validation
+2.38%, out-of-sample +0.49%, all CI-decisive). Survived every
adversarial check that has ever killed a promising candidate in this
project: clears realistic costs with a 5x margin (still net positive
at a 1.00% round-trip cost); broad across 29 of 32 symbols; no sector
concentration (largest sector bucket only 17.8%); remarkably stable
across three decade-spanning eras including COVID (no decay, unlike
gap-fade or the divergence family); strong in BOTH liquidity halves
(unlike gap-fade); and — the check specifically designed to catch an
inflated-looking rolling-window result — still decisive under a
genuinely non-overlapping, independent re-sampling. Full validation in
`docs/research/CROSS_SECTIONAL_RELATIVE_STRENGTH_REPORT.md`. **Still
INCONCLUSIVE, not PROMOTED, by explicit choice**: this project's own
promotion discipline requires a real backtest through the existing
cost-aware/risk-sized engine and a shadow-mode observation period
before anything stronger — not yet done, deliberately, per the
mission's own "do not immediately modify live trading" instruction.

Overnight gap-fade was this project's second-most promising raw finding
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

**New today, and arguably the most statistically robust single finding
this project has ever produced**: H_CALENDAR_001 found NSE Tuesday
returns are positive and CI-decisive in ALL THREE splits (never
reversing), even after a conservative Bonferroni correction for testing
all 5 weekdays, broad-based across 31 of 32 symbols, and positive in 9
of 11 individual years with no decay trend — genuinely the strongest
replication in this project's history by every measure that has
disqualified other candidates. **Still not a tradeable edge, for two independent reasons**: the effect
size (~0.08-0.12% per week) does not clear a realistic weekly
round-trip cost (~0.21%) if traded stock-by-stock; and a same-day
follow-up (H_CALENDAR_002) found the effect does NOT hold on NIFTY 50
itself with any statistical decisiveness — the pooled-stock
significance came specifically from combining 32 correlated-but-
distinct series, so a cheap single-index-instrument trade (which would
sidestep the cost problem) isn't statistically supported either. Real
evidence of a genuine market phenomenon; not yet evidence of an
exploitable one, and now closed off from two different directions.

Nothing is promoted. Nothing should be traded.

## PROMOTED HYPOTHESES

**None.** Zero, across the entire history of this project's research
(35 hypotheses tested to date).

## PROMISING HYPOTHESES

None FORMALLY carry that status in the registry yet (this project's own
`HypothesisStatus` enum doesn't have a PROMISING tier — see the note in
`H_XSECT_001`'s own entry), but **H_XSECT_001 (cross-sectional
mean-reversion) is now, by a clear margin, the closest this project has
ever come**: decisive across all three splits (not just robust on the
pooled sample, unlike Tuesday), survives costs with the widest margin
of any finding here, and passed every adversarial check applied. It is
recorded as INCONCLUSIVE only because the mission's own required
workflow (validation report → PROMISING → shadow mode) hasn't completed
the shadow-mode step yet — see `docs/research/
CROSS_SECTIONAL_RELATIVE_STRENGTH_REPORT.md`. H_CALENDAR_001 (Tuesday
effect) remains the strongest PURELY STATISTICAL replication (broad,
Bonferroni-surviving, no decay) but fails economically (doesn't clear
costs, no execution vehicle) — a different way of falling short than
H_XSECT_001's own remaining gap (evidence exists, shadow-mode
observation does not yet).

## INCONCLUSIVE HYPOTHESES (15)

H_ENTRY_003, H_ENTRY_005, H_EXIT_002, H_MEANREV_002, H_CONTEXT_MARKET_002,
H_CONTEXT_SECTOR_002, H_CONTEXT_ALIGN_001, H_CONTEXT_MARKET_004,
H_CONTEXT_MARKET_005 (the 10-year re-run — found real sign-instability
pre-2022 alongside improved OOS power for the compound condition — see
above), H_GAP_001, H_GAP_002 (the original gap-fade discovery record —
kept as history; see H_GAP_003 for why the underlying idea did not
ultimately survive), H_TRANSMISSION_001 (Nasdaq → NIFTY IT, honest
decline/advance asymmetry), H_OPENRANGE_001 (real intraday opening-
range research, genuinely tested with real 15-minute Yahoo data, but
the ~60-day intraday history limit made every split fundamentally
underpowered; a mild fade direction echoed gap-fade's own finding but
never reached decisive significance), H_CALENDAR_001 (the Tuesday
effect — this project's most statistically robust PURE finding, real
but not tradeable — see above), and **H_XSECT_001 (cross-sectional
mean-reversion — this project's strongest finding overall, awaiting
shadow-mode validation — see PROMISING HYPOTHESES above)**. Full
evidence for each in `strategy/hypothesis_registry.py`.

## REJECTED HYPOTHESES (19)

H_ENTRY_002, H_ENTRY_004, H_EXIT_001, H_EXIT_003, H_EXIT_004,
H_MEANREV_001, H_RELSTRENGTH_001, H_BREAKOUT_001, H_CONTEXT_MARKET_001,
H_CONTEXT_MARKET_003, H_CONTEXT_SECTOR_001, H_CONTEXT_VIX_001,
H_CONTEXT_VIX_002, H_TRANSMISSION_002, H_TRANSMISSION_003,
H_TRANSMISSION_004, H_GAP_003 (the deep-validation follow-up to
H_GAP_001/002 — see above), H_SECTOR_ROTATION_001 (a stock's own
sector's cross-sectional momentum RANK among the 9 NIFTY sector
indices, a genuinely different formulation from the earlier binary
sector-regime tests — found a real, sensible, monotonic ordinal
pattern, leading sectors beat lagging ones, but the magnitude was too
small and the "best" bucket still went decisively negative
out-of-sample), and H_CALENDAR_002 (the Tuesday effect does not hold on
NIFTY 50 itself — see above). Full evidence for each in `strategy/
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

**The live scheduler stopped TWICE today** (2026-09-09): once overnight
(found stopped at session start, restarted at market open, a real
`pre_market` tick completed, 1 new prediction recorded) and once again
mid-session (confirmed alive ~10:07 IST, gone ~10:48 IST, right after a
normal `intraday` tick completed cleanly at 10:31 IST — no error either
time). Both times confirmed via `Get-CimInstance Win32_Process`
(authoritative — the tailed log's own last line looked perfectly
healthy both times and would NOT have revealed the stop on its own).
Both restarted with the identical established command line; both
confirmed healthy afterward. This is exactly the kind of "assume
nothing, verify with the authoritative source" finding this project's
own research discipline keeps demonstrating the value of.

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
5. **The temptation to rush H_XSECT_001 straight to paper execution.**
   It is this project's strongest finding by every measure applied —
   which is exactly why the mission's own explicit workflow (real
   cost-aware backtest → shadow mode → only then consider execution)
   matters most here, not least. A measurement finding, however
   well-validated, is not yet a strategy.
6. **Recurring, unexplained live-scheduler stops.** Twice in one
   session, with no error either time. The cause has not been
   identified from inside this session (no OS-level kill log visible to
   this process) — worth the user's own attention if it keeps
   recurring, since undisturbed live observation (risk #1 above) is
   only possible if the scheduler actually stays running.

## NEXT HIGHEST-VALUE RESEARCH QUESTION

The single highest-EV action is now **not another new hypothesis** — it
is completing H_XSECT_001's own validation pipeline per the mission's
explicit required order: (1) build the minimal `Strategy`-protocol
wrapper for "bottom-quintile 60-day trailing return, 20-day hold" and
run it through the EXISTING cost-aware, risk-sized backtesting/
promotion-gate machinery (not yet done — this report is the raw
price-behavior validation stage only); (2) if that clears the promotion
gate, shadow-mode observation before any execution consideration. See
`docs/research/CROSS_SECTIONAL_RELATIVE_STRENGTH_REPORT.md` §10 for the
full ordered next-steps list, including testing the sector-relative and
NIFTY-relative score variants as independent replications.

Separately, and lower priority: let the 15 real directional forecasts
recorded 2026-09-08 (and the 10-11 existing BUY predictions) resolve,
then re-run `evaluate-forecasts`/`evaluate`/`learn` for the first real
calibration read this project has ever had.

**Already answered, same session**: does the Tuesday effect hold on
NIFTY 50 itself (`^NSEI`), not just the 32-stock universe? No
(H_CALENDAR_002, REJECTED) — none of the three splits are individually
decisive on the index alone (n=97-295 vs. the pooled version's
n=3000-9000+). The pooled-stock result's own statistical power came
specifically from combining 32 correlated-but-distinct series, exactly
how a real single-instrument trade would NOT be implemented. This
closes off the "trade it via one cheap index instrument" idea
completely — the Tuesday effect is now disqualified from practical
tradeability by two independent reasons (cost margin at the pooled
level, no statistical power at the single-instrument level), not just
one.

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
