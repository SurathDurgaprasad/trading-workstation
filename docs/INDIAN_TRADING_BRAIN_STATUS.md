# Indian Trading Brain — Current Status

Last updated: 2026-09-09, mid-session of the "INDIAN NSE TRADING BRAIN
— AUTONOMOUS CONTINUATION LOOP — EDGE DISCOVERY PHASE" mission
(cross-sectional research thread). This is a
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
validated RAW MEASUREMENT this project's history has produced**:
`H_XSECT_001`, a genuine CROSS-SECTIONAL momentum ranking (rank all 32
universe stocks by trailing 60-day return, buy the bottom quintile
"laggards," hold 20 days) — a capability this project never had before
today (`quant_research/cross_sectional.py`, new). Decisive and
POSITIVE in ALL THREE splits, never reversing (development +1.53%,
validation +2.38%, out-of-sample +0.49%, all CI-decisive). Survived
every adversarial check that has ever killed a promising candidate in
this project: clears realistic costs with a 5x margin (still net
positive at a 1.00% round-trip cost, as an unconditioned pooled-return
subtraction — see below for why that estimate did not hold up once
converted to a real trade); broad across 29 of 32 symbols; no sector
concentration (largest sector bucket only 17.8%); remarkably stable
across three decade-spanning eras including COVID (no decay, unlike
gap-fade or the divergence family); strong in BOTH liquidity halves
(unlike gap-fade); and — the check specifically designed to catch an
inflated-looking rolling-window result — still decisive under a
genuinely non-overlapping, independent re-sampling. Full validation in
`docs/research/CROSS_SECTIONAL_RELATIVE_STRENGTH_REPORT.md` §1-9.

**Same day, the follow-through: the real, cost-aware, risk-sized
backtest FAILED (`H_XSECT_002`, REJECTED).** Per the mission's own "IF
A REAL EDGE APPEARS" workflow, the next required step was building the
executable wrapper and running it through the real promotion-gate
machinery — done this session (`quant_research/
cross_sectional_strategy.py`, new). Result: out-of-sample shows a
CI-decisive **NEGATIVE** mean per-trade return (-0.76%,
CI=[-1.31%,-0.21%]) against a realistic `CostModel.
india_nse_intraday_2026()`; `strategy/promotion_gate.py` verdict:
NEGATIVE, "decisive evidence of harm... must not be promoted." Root
cause, confirmed via an exit-reason diagnostic (not a re-run with
different parameters): the ATR-based stop reused from
`strategy/baseline.py` — calibrated for trend-CONTINUATION setups, not
a reversal signal — clips the majority of positions (51-57% of trades
each split) before the 20-day mean-reversion the raw measurement
captured can play out; the pure time-cap EXIT (`EXPIRED`, the closest
analogue to the raw measurement) stayed only mildly negative in
out-of-sample by comparison. **This is the same "does the raw finding
survive becoming a real trade" test H_MEANREV_002 already applied to
its own finding, applied here for the first time to a decisively-
positive-in-all-splits raw measurement — and it did not survive.**
Full addendum in `docs/research/
CROSS_SECTIONAL_RELATIVE_STRENGTH_REPORT.md` §11. **`H_XSECT_001`
itself stays INCONCLUSIVE, not downgraded** — the raw measurement claim
and the executable-strategy claim are honestly kept distinct; no
alternative stop/target width was or will be tried as a tuning
follow-up on this result (that would violate this project's own
multiple-testing discipline) — a genuinely different, independently
motivated exit design would need its own new hypothesis. Shadow mode
does not start on the strength of this execution design.

**Same day, one more closed loop: the sector-relative and NIFTY-
relative score variants (`H_XSECT_003`, INCONCLUSIVE).** Report §10
step 3's two remaining open items, now both resolved.
NIFTY-relative turned out **not to be an independent test at all** —
subtracting the same benchmark value from every symbol on a given date
cannot change that date's rank order (confirmed both mathematically
and empirically: byte-identical bucket assignments to the absolute
version in all three splits) — a useful negative-knowledge finding
that forecloses re-testing it. Sector-relative (21/32 sector-mapped
symbols, 6 real NIFTY sector indices) **is** genuinely independent and
**confirms the pattern**: Q5 sector-relative laggards CI-decisive
positive in all three splits (dev +2.27%, val +2.21%, oos +0.49% —
matching the absolute-return oos figure almost exactly). Its own
executable behavior has explicitly not been tested and is not assumed
to mirror `H_XSECT_002`'s negative result either way. Full addendum in
`docs/research/CROSS_SECTIONAL_RELATIVE_STRENGTH_REPORT.md` §12.

**Same day, one more test, and a genuinely humbling correction:
does a wider or absent stop rescue H_XSECT_002's result
(`H_XSECT_004`, REJECTED)?** H_XSECT_002's own diagnostic showed STOP
exits driving nearly all the loss while EXPIRED exits were only mildly
negative — the obvious next question, already named in this document
before it was tested. **Both pre-specified variants performed WORSE,
not better.** `wide_stop` (3× the original ATR multiplier):
out-of-sample -1.47%, worse than the original -0.76%. `no_stop`
(effectively unbounded): CI-decisive negative in **all three splits**
(-5.46%/-2.66%/-4.61%), far worse than either configuration. The
mechanism corrects the earlier diagnostic's own naive reading: the
trades landing in the EXPIRED bucket are not fixed — widening the stop
lets the *same* deteriorating trades that used to get cut at a bounded
loss instead run to a far larger, uncapped one by day 20, dragging the
EXPIRED bucket's own average down. A real, meaningful fraction of
laggards simply keep falling and never reverse within the 20-day
window; the original tight stop was doing real protective work
invisible in the pooled mean-return statistic. This closes the
"wider/absent stop" direction only — a *tighter* stop remains
untested and would need its own new, honestly pre-registered
hypothesis. Full addendum in `docs/research/
CROSS_SECTIONAL_RELATIVE_STRENGTH_REPORT.md` §13.

**New mission, new segment (2026-09-09, "EXECUTION-MECHANICS
INVESTIGATION"): a precise reconciliation between the raw H_XSECT_001
measurement and every executable test against it identified FOUR real
structural mismatches, not one** — entry timing (raw assumes a
same-close entry; every executable backtest uses next-bar-open),
path-dependence (the raw measurement is a pure fixed-horizon return;
H_XSECT_002's own diagnostic shows a TARGET exit fired in EVERY
variant tested so far, including H_XSECT_004's `no_stop`, meaning
none of them actually measured the same quantity H_XSECT_001 reports),
sampling ("newly entered" trades are ~7% of the raw measurement's own
pooled sample, never checked for representativeness), and portfolio
construction (the raw measurement's daily pooling is economically a
diversified basket; H_XSECT_002/004 test independent, undiversified
single-symbol trades). Full reconciliation in `docs/research/
CROSS_SECTIONAL_RELATIVE_STRENGTH_REPORT.md` §14.

**The resulting test (`H_XSECT_005`, INCONCLUSIVE/INSUFFICIENT_DATA)
is the most encouraging result in the entire executable-strategy
family so far.** A genuine equal-weight, periodically-rebalanced
(every 20 bars, non-overlapping) portfolio backtest — current
bottom-quintile membership, a PURE fixed 20-bar hold with NO stop and
NO target at all (the first test in this family with no path-dependent
exit whatsoever) — shows **no sign reversal in any split**: development
+0.76% (n=72), validation +1.81% (n=24), out-of-sample +0.46% (n=24),
all positive, in sharp contrast to H_XSECT_002/004's negative
out-of-sample results. The out-of-sample figure is strikingly close to
H_XSECT_001's own raw out-of-sample measurement for this exact
configuration (+0.487%) — net of real costs, the portfolio reproduction
lands almost exactly where the cost-free raw measurement predicted.
**But this does not clear the promotion gate — purely on sample size,
not a weak effect**: `evaluate_promotion` returns INSUFFICIENT_DATA
because validation and out-of-sample (n=24 each) fall below its own
30-observation minimum, a structural consequence of only ~126 periods
existing at a 20-day non-overlapping cadence across 10 years of data,
not a fixable bug. This strongly suggests H_XSECT_002/004's own
negative verdicts were substantially attributable to THEIR OWN
structural choices (a trend-continuation stop mechanic; no
diversification), not to the underlying signal being illusory — but
directional-but-inconclusive is reported as exactly that, never
rounded up to a positive claim. Full addendum in `docs/research/
CROSS_SECTIONAL_RELATIVE_STRENGTH_REPORT.md` §15.

**Same day, next mission continuation: does H_XSECT_005's effect
survive on a wider, objectively-selected NSE universe? No —
`H_XSECT_006`, REJECTED.** Pre-registered *before* any code ran
(`docs/research/H_XSECT_006_UNIVERSE_WIDENING_PREREGISTRATION.md`,
committed as its own commit ahead of the experiment): an objective,
exchange-vetted expansion using the already-integrated Dhan instrument
master — every NSE equity symbol with an active NSE single-stock
futures contract (a real, regulator-vetted liquidity/market-cap gate,
deliberately NOT a NIFTY-100/200 claim, since `market_data/
universe.py` already declined to make that claim for lack of a
verifiable source). 208 symbols total, the original 32 a strict
subset, leaving 176 genuinely new symbols with zero overlap. Same
frozen `H_XSECT_005` methodology run independently on ORIGINAL (32),
EXPANDED-ONLY (176), and COMBINED (208). **Result: EXPANDED-ONLY
reverses sign relative to ORIGINAL in two of three splits**
(development +0.76%→-0.29%, out-of-sample +0.46%→-0.58%; only
validation stays positive, and more weakly). COMBINED shows the same
pattern, more pronounced out-of-sample (-1.26%). This is exactly the
pre-registration's own frozen failure condition. Adversarial checks
ruled out a single-outlier artifact (removing the largest contributor,
`YESBANK.NS`, barely moves the result) and illiquid-name concentration
(both liquidity halves show a similar pattern, if anything the
below-median-liquidity half performs slightly *better*) — the reversal
is broad, not a fragile artifact of one name or one liquidity segment.
Survivorship bias (current F&O eligibility, not point-in-time) was
disclosed up front as a limitation that would be expected to *inflate*
a positive result, making the REJECTED verdict more credible, not
less. **`H_XSECT_001`'s raw measurement and `H_XSECT_005`'s portfolio
result on the original 32 symbols are not invalidated** — both remain
real findings on that specific, now-explicitly-disclosed universe.
What is rejected is the broader claim that this is a universe-agnostic
NSE phenomenon; it looks specific to large-cap "quality" names, a
plausible but untested mechanism. Full results in `docs/research/
H_XSECT_006_UNIVERSE_WIDENING_PREREGISTRATION.md` §9.

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

**Same session, first venture outside the cross-sectional thread since
it hit two consecutive rejections: volatility contraction
(`H_VOL_001`, REJECTED).** Does a LOW volatility regime (existing,
unmodified `backtesting.regime.classify_volatility_at` thresholds)
show a forward-return advantage over the baseline? A genuinely
untested, economically-motivated question, answerable with zero new
production code (the `volatility_regime` column and measurement
function already existed, built for the H_CONTEXT family). Result:
LOW_VOL's raw absolute return is positive in every split, but that
merely reflects this large-cap universe's own general 10-year positive
drift — the meaningful comparison (LOW_VOL vs. the NORMAL_VOL
baseline, ~90% of all bars) reverses direction in validation
(LOW_VOL underperforms baseline there) after favoring LOW_VOL in
development, and even where favorable the margin decays sharply
(development +1.2 points over baseline → out-of-sample +0.54 points)
— too small and inconsistent to survive realistic costs. Rejected at
the pure-measurement stage, before any executable-strategy work.

**New mission continuation ("REGIME-DEPENDENT SIGNAL VALIDATION"):
the cleanest, most complete NSE-only regime-conditioning finding this
registry has produced (`H_MEANREV_003`, INCONCLUSIVE — a genuine raw
finding, not yet an executable-strategy claim).** An audit of all 14
prior regime hypotheses found market-trend×volatility interaction on
the *baseline* signal technically untested but both dimensions already
unstable there — high risk of just fragmenting known noise. Chose
instead a genuinely novel pairing: does `H_MEANREV_001`'s oversold
entry (`zscore_close_20`, frozen thresholds) behave differently by
NIFTY's own market regime, tested NSE-only for the first time (the
original pooled NSE+US and found nothing). Pre-registered before any
code ran. **Result: `market_trend_regime == TRENDING_UP` is CI-decisive
positive in development, validation, AND out-of-sample, for both
frozen candidates, at h5/h10/h20 — no sign reversal anywhere** (h20:
+1.75%/+1.31%/+1.47% and +1.72%/+1.73%/+1.37%). `TRENDING_DOWN` and
`SIDEWAYS` both show the familiar "dev/val decisive, oos reverses"
shape already disqualifying elsewhere in this registry; volatility
regime alone is REJECTED (clear sign reversals, severely underpowered
extreme buckets, n=8-36 in validation) — matching this project's
repeated finding that volatility regimes are too rare/clustered to
condition on at this universe size, and correctly blocking the planned
2-D interaction per the pre-registration's own sample-size gate.
Adversarial checks on `TRENDING_UP`: broad across 24-29 of 32 symbols
(not concentrated); survives a 0.30% round-trip cost with a wide
margin; year-by-year shows **7 of 9 complete years CI-decisive
positive, only 2022 decisively negative (a single real exception, not
a decay trend), and 2025 — the most recent complete year — among the
strongest** (an initial 50/50 era-split had looked like "early strong,
late weak" purely because 2022's bad year sits at the start of that
split's late half — resolved once examined year-by-year). Not promoted
to SUPPORTED for the same reason `H_XSECT_001` wasn't: a raw, cost-free
measurement is not the same claim as a real, stop/target-managed
trade — that conversion is the natural next step, as its own new
pre-registered hypothesis. Full writeup in `docs/research/
H_MEANREV_003_REGIME_CONDITIONING_PREREGISTRATION.md`.

**Same segment, the natural next step, done immediately: does
H_MEANREV_003's clean raw finding survive becoming a real trade? No —
`H_MEANREV_004`, REJECTED, and instructively so.** Built the
executable wrapper (new `REGIME_GATED_CANDIDATES` in `quant_research/
mean_reversion_signal.py`, `H_MEANREV_001`'s own frozen thresholds
gated on `TRENDING_UP`, exit mechanic completely unchanged — tests
entry-timing in isolation), ran it cost-aware and risk-sized through
`strategy/promotion_gate.py`. **Neither candidate reaches a confident
positive verdict in any split** — every one of six splits (2
candidates × 3 splits) has a mean-return CI straddling zero
(`STATISTICALLY_MEANINGLESS`), despite the underlying raw measurement
being CI-decisively positive in every one of those same splits. The
exit-reason diagnostic shows why: STOP exits dominate 57-66% of trades
in every split, the **same mechanism `H_XSECT_002`'s own diagnostic
already found** for a completely different signal — `strategy.
baseline`'s frozen ATR stop, built for trend-*continuation*, plausibly
clips this reversal-type entry before the recovery can complete. Per
the pre-registration's own frozen discipline, **no stop retuning
follows** — `H_XSECT_004` already tested exactly that idea for an
analogous signal and found it made things *worse*, not better.
`H_MEANREV_003`'s own raw finding is not invalidated by this result;
what fails is this specific executable design. **This is the second
time in this project's history a cleanly-validated raw NSE measurement
has failed the exact same conversion** (`H_XSECT_001`→`H_XSECT_002`
being the first) — a genuinely notable, recurring pattern about this
project's own frozen stop/target design, worth carrying forward as a
standing observation rather than re-litigating per-signal. Full
writeup in `docs/research/
H_MEANREV_004_EXECUTABLE_REGIME_GATED_PREREGISTRATION.md`.

Nothing is promoted. Nothing should be traded.

## PROMOTED HYPOTHESES

**None.** Zero, across the entire history of this project's research
(43 hypotheses tested to date).

## PROMISING HYPOTHESES

None FORMALLY carry that status in the registry yet (this project's own
`HypothesisStatus` enum doesn't have a PROMISING tier), and **there is
currently no standing "closest candidate"** — the two leading raw
findings this project has produced (`H_XSECT_001`'s cross-sectional
laggard effect and `H_MEANREV_003`'s regime-conditioned mean reversion)
have BOTH now independently hit the same wall when converted into a
real trade: `H_XSECT_002` and `H_MEANREV_004` each failed for the same
mechanistic reason (STOP exits dominating 55-65%+ of trades, this
project's frozen ATR stop — calibrated for trend-*continuation* — very
plausibly clipping a reversal-type entry before it can complete).
**This is now the single most important standing finding about this
project's own architecture**: two structurally unrelated signals,
tested months apart with completely independent methodology, failed
their executable conversion via the identical mechanism. `H_MEANREV_003`
remains, by a real margin, the cleanest RAW finding in this registry
(CI-decisive positive in all three splits, both candidates, every
horizon, no sign reversal, broad, cost-margin-surviving, non-decaying —
see CURRENT ACTIVE EDGE STATUS above) — but "cleanest raw measurement"
and "closest to a tradeable strategy" are no longer the same claim in
this project's own history. See CURRENT ACTIVE EDGE STATUS above for
the full story on `H_XSECT_001`/`002`/`005`/`006` and `H_MEANREV_003`/
`004`.

## INCONCLUSIVE HYPOTHESES (18)

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
but not tradeable — see above), H_XSECT_001 (cross-sectional laggard
raw measurement, on the original 32-symbol universe specifically — see
H_XSECT_006 below for why this can no longer be described as a broad,
universe-agnostic finding), H_XSECT_003 (sector-relative score variant
— genuinely replicates H_XSECT_001's pattern on the original universe,
its own broader generalizability now also an open question), H_XSECT_005
(the genuine portfolio reproduction — positive in all three splits on
the original 32 symbols, but INSUFFICIENT_DATA at n=24 per validation/
out-of-sample split — see above), and **H_MEANREV_003 (regime-
conditioned mean reversion — the cleanest RAW finding in this registry,
CI-decisive positive across all splits/candidates/horizons, but its own
executable conversion failed as H_MEANREV_004 — see PROMISING
HYPOTHESES and REJECTED HYPOTHESES above)**. Full evidence for each in
`strategy/hypothesis_registry.py`.

## REJECTED HYPOTHESES (24)

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
out-of-sample), H_CALENDAR_002 (the Tuesday effect does not hold on
NIFTY 50 itself — see above), H_XSECT_002 (the real, cost-aware,
risk-sized backtest of H_XSECT_001's own finding — out-of-sample shows
CI-decisive harm, driven mechanistically by an ATR stop mis-calibrated
for a reversal signal — see above), H_XSECT_004 (does a wider/absent
stop rescue H_XSECT_002's result? Both pre-specified variants performed
WORSE, not better — a genuine correction to H_XSECT_002's own
diagnostic reading; see above for the full mechanism), H_XSECT_006
(universe widening — the laggard effect reverses sign on 176 genuinely
new NSE symbols not in the original universe; a selection-bias warning
escalating to falsification per the pre-registration's own frozen
criteria — see above), H_VOL_001 (volatility contraction — does a LOW
volatility regime beat the baseline forward return? Reverses direction
in validation versus development/out-of-sample, and the effect where
favorable is small and decaying — a real, pure-measurement test reusing
entirely existing infrastructure, no new module needed), and
**H_MEANREV_004 (the real, cost-aware, risk-sized backtest of
H_MEANREV_003's own TRENDING_UP-gated finding — every split for both
candidates shows a CI straddling zero, driven by the SAME STOP-exit
mechanism H_XSECT_002 already found for an unrelated signal; per the
pre-registration's own frozen discipline, no stop retuning follows —
see PROMISING HYPOTHESES above)**. Full evidence for each in
`strategy/hypothesis_registry.py`.

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
5. **The temptation to tune the stop/target until H_XSECT_002 "works."**
   Now realized, not just hypothetical: the real backtest failed
   out-of-sample, and the honest, disclosed mechanism (an ATR stop
   mis-calibrated for a reversal signal) makes it obvious a wider stop
   or no stop at all might behave very differently. That is exactly the
   trap — retrying with looser parameters until one clears the
   promotion gate would be undisclosed multiple testing on the same
   result. Any different exit design must be its own new, independently
   pre-registered hypothesis, not a quiet retry of this one. This risk
   item stays open as a standing reminder for whoever picks that up
   next.
6. **Recurring, unexplained live-scheduler stops.** Twice in one
   session, with no error either time. The cause has not been
   identified from inside this session (no OS-level kill log visible to
   this process) — worth the user's own attention if it keeps
   recurring, since undisturbed live observation (risk #1 above) is
   only possible if the scheduler actually stays running.
7. **The temptation to round H_XSECT_005's INSUFFICIENT_DATA up to a
   positive claim.** Now more clearly resolved than hypothetical: the
   principled variance-reduction lever this risk named (a wider
   universe) WAS tested, pre-registered, and found a sign reversal
   (H_XSECT_006) — a direct, healthy correction of the temptation this
   item warned about. Kept as a standing reminder of the discipline
   that produced that correction, not because the specific worry is
   still live.
8. **Universe-selection risk is real, not hypothetical, for every
   remaining INCONCLUSIVE cross-sectional finding.** H_XSECT_006 proved
   it concretely for the laggard effect: a result that looked robust
   across 5 separate tests on the original 32 symbols reversed sign on
   176 different, objectively-selected NSE symbols. H_XSECT_003's own
   sector-relative replication was ALSO only ever tested on the
   original 32/21-symbol universe — its own broader generalizability is
   now an open question by the same logic, not yet checked.
9. **The temptation to round H_MEANREV_003's INCONCLUSIVE up to a
   positive claim.** Now realized rather than hypothetical: the
   conversion to a real trade (`H_MEANREV_004`) was attempted
   immediately and failed, via the identical STOP-domination mechanism
   `H_XSECT_002` already demonstrated for a completely different
   signal — the exact trap this item warned about, now the strongest
   evidence yet that "clean raw measurement" and "close to promotable"
   are not the same claim in this project. Universe-selection risk
   (item 8 above) still applies to `H_MEANREV_003`'s own raw finding
   and has not yet been checked — it has only ever been tested on the
   original 32 symbols — but is now a lower-priority question than it
   was, since the executable conversion already failed independently
   of universe size.
10. **This project's frozen stop/target design (`strategy.baseline`'s
    `STOP_ATR_MULTIPLIER`/`TARGET_RISK_REWARD`, built for
    trend-*continuation*) may be structurally unsuited to every
    reversal-type signal this project discovers, not just one.**
    `H_XSECT_002` and `H_MEANREV_004` — two structurally unrelated
    signals — both failed their executable conversion via the same
    STOP-exit-domination mechanism. This is now the single most
    important standing architectural question for this research
    program: is there a genuinely different, honestly pre-registered
    exit design (not a retuning of the same stop) that could let a real
    reversal signal survive execution at all? `H_XSECT_004` already
    showed a naive wider/absent stop makes things worse, not better —
    the answer, if one exists, is not a simple parameter change.

## NEXT HIGHEST-VALUE RESEARCH QUESTION

**Current answer**: does `H_MEANREV_003`'s raw finding survive becoming
a real, cost-aware trade? **No — `H_MEANREV_004`, REJECTED, via the
same STOP-exit mechanism `H_XSECT_002` already found for an unrelated
signal.** Both leading research threads this project has produced
(`H_XSECT_001`→`H_XSECT_002`, `H_MEANREV_003`→`H_MEANREV_004`) have now
independently failed the identical conversion step. See CURRENT ACTIVE
EDGE STATUS and BIGGEST RISKS item 10 above for the full story — this
is now a standing architectural question, not a per-signal one.

**The single highest-EV question this project now has** is item 10
above: is there a genuinely different, honestly pre-registered exit
design that would let ANY reversal-type signal survive execution in
this project's own backtesting engine, or is the frozen ATR-stop/
fixed-R:R-target mechanic structurally incompatible with reversal
signals as a category (as opposed to the trend-continuation signals
`strategy.baseline` was actually designed for)? This is explicitly
**not** a stop-width retuning exercise — `H_XSECT_004` already showed
that direction (wider/absent stop) makes things worse, not better, for
one signal. A genuinely different design (e.g., an exit rule with no
hard stop-loss at all within a short, fixed holding period but a
different risk-control mechanism, or a stop sized from the SIGNAL's own
economics rather than borrowed from `TrendMomentumBaseline`) would need
its own careful, honestly pre-registered hypothesis — not assumed to
work, and not chased reflexively after two rejections in a row.

**Two closed-out threads, both at genuine natural stopping points**:
the cross-sectional (`H_XSECT`) thread (two REJECTED in a row, one
closed variant, one underpowered-but-real result) and now the
regime-conditioned mean-reversion thread as well (`H_MEANREV_003`
INCONCLUSIVE raw finding, `H_MEANREV_004` REJECTED executable
conversion). Universe-generalization for `H_MEANREV_003` (per the
`H_XSECT_006` precedent) is now lower priority than it was, since the
executable conversion already failed independently of universe size —
still a legitimate, cheap check if pursued, but not the most valuable
next question.

**Already tried this session, do not retest**: volatility contraction
(`H_VOL_001`, REJECTED), the market-trend/volatility-regime marginal+
interaction sweep (`H_MEANREV_003`), and the executable conversion
itself (`H_MEANREV_004`). Untested candidates from the mission's own
lower-priority family list remain, though the exit-design question
above is now higher priority than any of them: extreme-move research,
multi-horizon single-stock momentum (distinct from the already-tested
cross-sectional and relative-strength formulations, both REJECTED), and
market microstructure (likely blocked by the same ~60-day intraday-
history ceiling that constrained `H_OPENRANGE_001`).

Separately, and lower priority: let the 15 real directional forecasts
recorded 2026-09-08 (and the 10-11 existing BUY predictions) resolve,
then re-run `evaluate-forecasts`/`evaluate`/`learn` for the first real
calibration read this project has ever had.

**Prior segments' answered questions, kept brief so this section stays
focused on what's actually next:**
- Does the Tuesday effect hold on NIFTY 50 itself, not just the pooled
  32-stock universe? No (`H_CALENDAR_002`, REJECTED) — no statistical
  power at the single-instrument level, closing off a cheap index-only
  trade vehicle for that effect entirely.
- Sector momentum RANK among the 9 NIFTY sector indices: real but
  too-small, too-unstable (`H_SECTOR_ROTATION_001`, REJECTED) — the
  next sector-related question, if pursued, should look at something
  other than momentum ranking specifically.
- Real intraday opening-range research is possible (confirmed 5m/15m/
  30m/60m Yahoo bars) but the ~60-trading-day history ceiling makes
  every split fundamentally underpowered (`H_OPENRANGE_001`,
  INSUFFICIENT_DATA) — do not revisit on the same window; either wait
  for more calendar time or source a longer-history intraday provider.
- The 10-year NSE cache is available for every symbol in this
  universe — an era-stability re-check (matching H_CONTEXT_MARKET_005's
  own 5-year-to-10-year re-run) remains a well-motivated, not-yet-done
  standing option for H_MEANREV_002/H_TRANSMISSION_001, both originally
  tested on 5 years or less.
