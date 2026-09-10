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

**New mission ("CONTINUE BUILDING THE REAL PROFIT-SEEKING INDIAN NSE
TRADING BRAIN"): is there a structurally different exit architecture —
not a stop-width retune — that rescues the signal? No — `H_EXIT_005`,
REJECTED, and more decisively than the stop-based design it replaced.**
An architecture audit (reading `backtesting/execution.py`,
`risk/engine.py`, `backtesting/exit_experiments.py` directly, not
inferring from filenames) confirmed the project's only exit mechanisms
are price-stop/price-target and a time-cap fallback, all built for
trend-continuation and reused unchanged by every reversal candidate so
far. A registry search confirmed mean-reversion-completion,
regime-invalidation, signal-decay, and opposite-signal exits were all
genuinely untested. Selected mean-reversion-completion (exit when
`zscore_close_20` recovers to ≥0.0 — price back at its own trailing
mean, the literal completion of the entry's own thesis — or a 20-bar
safety cap) as the more fundamental question, pre-registered before any
code ran. **Result: `evaluate_promotion` returns NEGATIVE for both
candidates — every one of six splits is individually CI-decisive
negative** (win rates as low as 3.9%, mean returns -3.5% to -6.1% per
trade) — a *stronger* rejection than `H_MEANREV_004`'s own
`STATISTICALLY_MEANINGLESS` result. The mechanism is genuinely new, not
a repeat of the STOP-domination story: `MEAN_REVERSION_COMPLETE` is the
*majority* exit reason (77% of trades in one split) — most trades DO
see the zscore recover — yet win rates stay catastrophically low,
because **the moving average itself declines during a genuine
downtrend**, so "price returned to its own trailing mean" is satisfied
long before "price returned to (or above) entry" whenever the entry
caught a real, sustained decline rather than a temporary dip. This
directly falsifies the working hypothesis (carried over from
`H_MEANREV_004`) that the stop itself was the primary obstacle —
removing it made things worse, not better. Full writeup in
`docs/research/H_EXIT_005_MEAN_REVERSION_COMPLETION_PREREGISTRATION.md`.

**Per the user's own explicit next-direction guidance after three
consecutive exit-design rejections: return to hypothesis discovery,
priority 1 = extreme-move/post-shock behavior. Tested — `H_EXTREME_001`,
REJECTED overall, but the asymmetry it surfaces is itself the real
finding.** Does NSE show a forward-return asymmetry following an
extreme 5-day cumulative move (`trailing_return_5`, a raw-magnitude
percentile metric — genuinely distinct from `zscore_close_20`'s
standardized-deviation family every `H_MEANREV_00x` entry used),
tested for both weakness and strength, thresholds frozen from
NSE-pooled development-period data only (5th/95th percentile: -6.14%/
+7.15%)? **Result: a real, disclosed asymmetry.** EXTREME_WEAKNESS
(bottom 5%): development/validation both CI-decisive positive
(strengthening at longer horizons), out-of-sample never reaches
decisiveness at any of six horizons but never reverses either — real,
just underpowered. EXTREME_STRENGTH (top 95%): development CI-decisive
positive at *every* horizon (real momentum), but out-of-sample
CI-decisive **negative** at the pre-declared primary horizon (h5:
-0.32%) and at h3 — a genuine sign reversal, this entry's own explicit
failure condition. **This is the same pattern this project's entire
research history has independently converged on** through completely
different methodologies (`H_XSECT_001`'s cross-sectional laggards,
`H_ENTRY_002`/`004`'s rejected strength-buying, `H_RELSTRENGTH_001`,
`H_BREAKOUT_001`) — a genuinely new metric family reproducing the same
asymmetry is real corroborating evidence, not a coincidence. Rejected
overall (the strength side's reversal triggers the frozen failure
criterion), with the two sides' honestly different verdicts kept
distinct — strength cleanly disqualified, weakness merely underpowered
and open. Full writeup in `docs/research/
H_EXTREME_001_POST_SHOCK_ASYMMETRY_PREREGISTRATION.md`.

**Priority 2, multi-horizon momentum interaction — tested —
`H_MOMENTUM_001`, INCONCLUSIVE, with a real incremental-information
signal that is not yet statistically decisive.** Does a single stock's
own short-term weakness (`trailing_return_5`, bottom 20th percentile)
combined with that SAME stock's own medium/long-term structural
strength (`trailing_return_60`, top 80th percentile) predict a better
forward return than either condition alone — the critical test being
whether long-horizon strength adds *incremental* predictive
information, not merely whether the combined average is positive?
Thresholds frozen from NSE-pooled development-period data only. At h5
(primary horizon): COMBINED is CI-decisive positive in development
(+1.01%, n=963) and validation (+0.68%, n=276); out-of-sample is
directionally positive (+0.49%, n=114) and **passes the frozen
incremental-information test** (beats both `SHORT_WEAKNESS_ALONE`'s
+0.07% and `STRUCTURAL_STRENGTH_ALONE`'s own out-of-sample point
estimate), but its own CI (`[-0.13%,+1.11%]`) straddles zero — a small
out-of-sample sample (n=114), not a reversed sign, is the binding
constraint. A genuinely interesting secondary finding surfaced in the
same run: `STRUCTURAL_STRENGTH_ALONE` (buying medium/long-term
strength with no weakness condition) reverses to CI-decisive
**negative** out-of-sample (-0.22%, CI=[-0.37%,-0.06%]) — the THIRD
independent replication, via a THIRD distinct metric family, of this
project's long-standing "buying strength alone fails" finding
(`H_RELSTRENGTH_001`, `H_EXTREME_001`). Per the pre-registration's own
frozen gate, adversarial checks were explicitly NOT run since the
success gate (CI-decisiveness in all three splits) was not met — no
promotion, no executable-strategy pre-registration follows from this
result. Full writeup in `docs/research/
H_MOMENTUM_001_MULTI_HORIZON_INTERACTION_PREREGISTRATION.md`.

**A genuinely new mechanism — market breadth, not tested before —
`H_BREADTH_001`, REJECTED via a clean sign-order reversal.** Does the
FRACTION of the 32-symbol universe individually trending up (a
cross-sectional PARTICIPATION measure, mechanistically distinct from
NIFTY's own index-level trend already tested in
`H_CONTEXT_MARKET_001`-`005`) predict NIFTY's own forward return — the
classic "narrow rally is fragile" divergence thesis? Thresholds frozen
from NSE-pooled development-period-only daily breadth (20th/80th
percentile). At h10 (primary horizon): development showed the
predicted direction (`NARROW_BREADTH` +0.36% < `BROAD_BREADTH`
+0.91%), but validation reversed (+1.03% vs +0.95%) and out-of-sample
reversed more sharply — `NARROW_BREADTH` positive (+0.48%),
`BROAD_BREADTH` negative (-0.21%) — the opposite of the thesis
out-of-sample. A clean, disclosed sign-order reversal, this entry's
own explicit failure condition. A genuine methodological finding
surfaced alongside it: restricting to NIFTY's own `TRENDING_UP` dates,
`NARROW_BREADTH` never co-occurs at all (n=0 in every split) — narrow
participation and NIFTY's own uptrend classification are close to
mutually exclusive on this data, not independent dimensions, meaning
the "index looks fine while breadth deteriorates" scenario this
hypothesis depends on essentially never occurs at this threshold. Full
writeup in `docs/research/H_BREADTH_001_MARKET_BREADTH_PREREGISTRATION.md`.

Nothing is promoted. Nothing should be traded.

## PROMOTED HYPOTHESES

**None.** Zero, across the entire history of this project's research
(47 hypotheses tested to date).

## PROMISING HYPOTHESES

None FORMALLY carry that status in the registry yet (this project's own
`HypothesisStatus` enum doesn't have a PROMISING tier), and **there is
currently no standing "closest candidate"** — the underlying question
has moved from "which signal is closest to tradeable" to "does this
project's own exit-mechanics research have a viable direction left at
all," and the honest current answer is: not yet a validated one.
`H_XSECT_002`/`H_MEANREV_004` failed via STOP-domination (a trend-
continuation-calibrated ATR stop clipping a reversal signal); `H_EXIT_
005` then tested a genuinely different, thesis-based exit (mean-
reversion-completion) and failed **more decisively**, revealing a
deeper mechanistic problem — a moving-average-based exit condition can
be satisfied by the *average declining to meet the price*, not just by
the price genuinely recovering, so it does not imply profitability the
way it appears to. `H_MEANREV_003` remains, by a real margin, the
cleanest RAW finding in this registry (CI-decisive positive in all
three splits, both candidates, every horizon, no sign reversal, broad,
cost-margin-surviving, non-decaying — see CURRENT ACTIVE EDGE STATUS
above) — but three consecutive executable-conversion attempts
(`H_XSECT_002`, `H_MEANREV_004`, `H_EXIT_005`) have now failed for two
genuinely different reasons, and "cleanest raw measurement" is
increasingly distant from "closest to a tradeable strategy" in this
project's own history. See CURRENT ACTIVE EDGE STATUS above for the
full story on `H_XSECT_001`/`002`/`005`/`006`, `H_MEANREV_003`/`004`,
and `H_EXIT_005`. `H_EXTREME_001` (a genuinely new metric family —
raw-magnitude `trailing_return_5` percentile extremes, not
`zscore_close_20`) does not change this picture: STRENGTH cleanly
reversed sign out-of-sample (REJECTED, not promising), and WEAKNESS
was underpowered rather than reversed (INCONCLUSIVE, not promising
either) — see CURRENT ACTIVE EDGE STATUS and REJECTED HYPOTHESES
above. Per the user's own explicit next-direction guidance, the
project is now moving to a genuinely different hypothesis family
(multi-horizon momentum interaction — short-term weakness inside
persistent medium/long-term strength) rather than a fourth
exit-architecture or extreme-move variant. Tested — `H_MOMENTUM_001`
is now the closest thing to a live open thread: it passed the frozen
incremental-information test out-of-sample and showed no sign
reversal, but its own out-of-sample sample (n=114) was too small for
CI-decisiveness — genuinely promising-shaped, but INCONCLUSIVE, not
promoted, and its own adversarial-checks phase was correctly never
triggered since the success gate was not met. See CURRENT ACTIVE EDGE
STATUS and INCONCLUSIVE HYPOTHESES below for the full breakdown.

## INCONCLUSIVE HYPOTHESES (19)

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
HYPOTHESES and REJECTED HYPOTHESES above)**, and **H_MOMENTUM_001
(multi-horizon momentum interaction — short-term `trailing_return_5`
weakness AND per-stock `trailing_return_60` structural strength;
passed the frozen incremental-information test out-of-sample, no sign
reversal, but the out-of-sample sample (n=114) was too small for
CI-decisiveness; a real, disclosed secondary finding — buying
structural strength ALONE reversed to CI-decisive negative
out-of-sample, a third independent replication of this project's own
"strength alone fails" pattern — see CURRENT ACTIVE EDGE STATUS
above)**. Full evidence for each in `strategy/hypothesis_registry.py`.

## REJECTED HYPOTHESES (27)

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
entirely existing infrastructure, no new module needed), H_MEANREV_004
(the real, cost-aware, risk-sized backtest of H_MEANREV_003's own
TRENDING_UP-gated finding — every split for both candidates shows a CI
straddling zero, driven by the SAME STOP-exit mechanism H_XSECT_002
already found for an unrelated signal; per the pre-registration's own
frozen discipline, no stop retuning follows — see PROMISING HYPOTHESES
above), and **H_EXIT_005 (mean-reversion-completion exit — a
structurally different, thesis-based exit design, not a stop retune —
failed MORE decisively than H_MEANREV_004: every one of six splits is
CI-decisive negative, because a moving-average-based exit condition
can be satisfied by the average declining to meet the price rather
than genuine recovery; see PROMISING HYPOTHESES above)**, and
**H_EXTREME_001 (post-shock move asymmetry — a genuinely new metric
family, `trailing_return_5` percentile extremes rather than
`zscore_close_20` — measured both EXTREME_WEAKNESS and
EXTREME_STRENGTH on NSE; overall REJECTED because STRENGTH shows a
clean sign reversal, development CI-decisive positive at every horizon
but out-of-sample CI-decisive NEGATIVE at h3/h5, the same
buying-strength-fails pattern this registry has independently found
via H_XSECT_001/H_ENTRY_002/H_ENTRY_004/H_RELSTRENGTH_001/
H_BREAKOUT_001; WEAKNESS is separately, more mildly, inconclusive —
development/validation CI-decisive positive but out-of-sample
underpowered rather than reversed, a real open question not pursued
further in this run)**, and **H_BREADTH_001 (market breadth —
cross-sectional participation, a genuinely new mechanism distinct from
NIFTY's own index-level trend already tested in
H_CONTEXT_MARKET_001-005; the "narrow rally is fragile" divergence
thesis tested against NIFTY's own forward returns, thresholds frozen
from development-period-only daily breadth; development showed the
predicted direction but validation and out-of-sample both reversed,
out-of-sample most sharply — a clean sign-order reversal, this entry's
own explicit failure condition; a genuine methodological finding
surfaced alongside it — narrow breadth and NIFTY's own uptrend
classification are close to mutually exclusive on this data, so the
divergence scenario the thesis depends on essentially never occurs at
this threshold)**. Full evidence for each in
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

**Update 2026-09-10**: counts unchanged since 2026-09-08/09 above (15
total directional forecasts, still the same 4 resolved/11 active; no
new resolutions) — passive accumulation has not progressed, because
the live scheduler was found STOPPED again this morning (see below),
so no new `pre_market`/`market_open` ticks ran to add predictions or
forecasts today.

**Scheduler operational note, 2026-09-10**: found completely stopped
at session start (zero python.exe processes; no `scheduler_runs.db`
rows at all for 2026-09-10; today's `pre_market` slot already missed
by the time this was discovered, ~09:17 IST, market already open).
Restarted using the exact established command line, but the restart
is NON-FUNCTIONAL: every `market_open` attempt fails with
`DhanCredentialsMissingError` (`DHAN_CLIENT_ID`/`DHAN_ACCESS_TOKEN` not
set in this session's shell, not in User/Machine Windows environment
variables, and the codebase has no `.env` auto-loading anywhere —
confirmed via `grep` for `dotenv`). Whatever shell originally launched
the prior scheduler instance (PIDs 24472/24464) must have had these
exported directly; per the credential-masking policy this session has
never had access to their actual values and cannot restore them. The
broken restart attempt was stopped cleanly rather than left spamming
failed runs. **This requires the user's own action**: restart the
scheduler from a shell where the Dhan credentials are set, using the
exact established command line (`main.py schedule loop --watchlist-file
market_data/watchlists/starter_nse.yaml --paper-execute
--initial-capital 100000 --paper-db data/paper_trading.db --state-db
data/live_state.db --live-source dhan --resilient
--staleness-seconds 120`). No scheduler architecture change was made;
this is a credential-provisioning gap, not a code defect.

**Forecast-journal infrastructure audit, 2026-09-10 (read-only, no
historical record modified)**: ran `main.py evaluate-forecasts
--resilient` for real against the live `data/direction_forecasts.db`
(no credentials needed — uses the standard cached/Yahoo provider, not
the live Dhan feed) and read `predictions/direction_forecast.py`'s
resolution logic directly. **Verdict: the resolution mechanism itself
has no bug.** 15 total forecasts, 4 resolved (unchanged — the same
known stale-reference-price batch already excluded from calibration
above: RELIANCE/TCS/INFY/HDFCBANK, 1 correct/3 incorrect — this is
NOT a new accuracy read, just a re-confirmation of an already-disclosed
data-integrity issue), 11 legitimately still ACTIVE. The 11 ACTIVE
ones are correctly unresolved, not stuck: `as_of=2026-09-08`,
`horizon_bars=5`, and only ONE trading day (2026-09-09) has closed
since — `evaluate_forecast` correctly reports `bars_observed=0` because
the underlying market-data cache for these 11 symbols has not been
refreshed since 2026-09-08T14:34 UTC (confirmed via `cache-status`),
itself a downstream consequence of the scheduler being down (the
scheduler's own ticks are what normally trigger fresh fetches). No
retained-ACTIVE anomaly found (checked: no forecast's evaluation
history ever showed `resolved=True` followed by a later `resolved=
False`). **A real operational guardrail identified, NOT acted on**:
all 11 of these symbols are also part of the 32-symbol research
universe (`ORIGINAL_32_NSE_UNIVERSE`) with 10-year cached depth;
`CachedMarketDataProvider` has no automatic invalidation and serves
a cache hit as-is regardless of the caller's requested period, so a
naive refresh (deleting the cache file and letting `evaluate-forecasts`
refetch at its own default `--period=1y`) would silently downgrade
these 11 symbols' research-grade 10-year depth to 1 year, corrupting
every other hypothesis in this registry that touches them (the exact
class of risk this project has hit before). Not done: even a
depth-safe refresh today would only advance `bars_observed` from 0 to
1 (one new trading day), nowhere near the 5-bar resolution threshold —
no forecast would actually resolve, so the risk is not justified by
the reward right now. This will resolve naturally once the scheduler
is restored and its normal ticks resume advancing the cache correctly.
**No code was changed** — per this audit's own finding, there is no
bug to fix, matching the "if no bug exists and the scheduler is simply
stopped: do NOT create unnecessary code" discipline.

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
    Partially answered, and the answer is more sobering than hoped:
    `H_EXIT_005` tried a genuinely different, thesis-based exit design
    (not a stop retune) and it failed *more* decisively than the
    stop-based one it replaced. Removing the stop is not the fix — see
    item 11 below for why.
11. **A moving-average-based exit condition does not imply
    profitability, even when it fires as intended.** `H_EXIT_005`'s
    own key lesson, worth carrying into any future exit-design
    hypothesis on a reversal signal: `zscore_close_20 >= 0.0` was the
    *majority* exit reason (most trades DID see the zscore recover) yet
    win rates were catastrophically low (3.9%-24.1%), because the
    trailing mean used as the reversion target is itself declining
    during a genuine downtrend — "price returned to its own mean" can
    be satisfied by the mean falling to meet a still-falling price, not
    by genuine recovery. Any future exit condition tested on this
    signal family should be checked for whether it can fire on a
    trade that is still net-unprofitable, not just for whether it
    eventually fires at all.

## NEXT HIGHEST-VALUE RESEARCH QUESTION

**Per the user's own explicit next-direction guidance** (priority
order: extreme-move/post-shock behavior, then multi-horizon momentum
interaction, then passive evidence accumulation, then microstructure
only if data supports it — and explicitly: do not start another
`H_EXIT_*` hypothesis without genuinely new evidence), the
exit-architecture thread (three consecutive rejections — `H_XSECT_002`,
`H_MEANREV_004`, `H_EXIT_005`) has been set aside, not resumed.

**Priority #1, extreme-move/post-shock behavior — DONE, `H_EXTREME_001`,
REJECTED with a real, disclosed asymmetry.** Measured both
`EXTREME_WEAKNESS` and `EXTREME_STRENGTH` (`trailing_return_5`
percentile extremes, a genuinely new metric family distinct from
`zscore_close_20`) on the standard 32-symbol NSE universe. STRENGTH
reversed sign cleanly out-of-sample (development CI-decisive positive
at every horizon, out-of-sample CI-decisive negative at h3/h5) —
reproducing this project's own long-standing "buying strength fails"
finding (`H_XSECT_001`, `H_ENTRY_002`/`004`, `H_RELSTRENGTH_001`,
`H_BREAKOUT_001`) via an independent methodology, which strengthens
confidence it is a real NSE phenomenon rather than a `zscore_close_20`
artifact. WEAKNESS was separately, more mildly, inconclusive
(development/validation CI-decisive positive, out-of-sample
underpowered but not reversed) — a real open question, not pursued
further in this run. See CURRENT ACTIVE EDGE STATUS and REJECTED
HYPOTHESES above for the full breakdown.

**Priority #2, multi-horizon momentum interaction — DONE,
`H_MOMENTUM_001`, INCONCLUSIVE with a real, not-yet-decisive
incremental-information signal.** Per the user's own framing:
short-term weakness (`trailing_return_5`, bottom 20th percentile)
combined with that SAME stock's own medium/long-term structural
strength (`trailing_return_60`, top 80th percentile) — conceptually
distinct from pure mean reversion, and confirmed genuinely novel
against the registry (`H_ENTRY_003` used a different RSI-shape metric
family and was INSUFFICIENT_DATA at n=29; `H_MEANREV_003` gated on a
market-wide `TRENDING_UP` regime flag, not per-stock long-horizon
momentum). At h5 (primary horizon), COMBINED was CI-decisive positive
in development (+1.01%) and validation (+0.68%), and its
out-of-sample point estimate (+0.49%, n=114) **passed the frozen
incremental-information test** — beating both `SHORT_WEAKNESS_ALONE`
(+0.07%) and `STRUCTURAL_STRENGTH_ALONE` (-0.22%, itself CI-decisive
negative out-of-sample — a third independent replication of "buying
strength alone fails") — but COMBINED's own out-of-sample CI
(`[-0.13%,+1.11%]`) straddled zero due to a small sample (n=114), not
a reversed sign. Per the pre-registration's own frozen gate, no
adversarial checks or executable-strategy pre-registration followed,
since the all-three-splits-decisive success bar was not met. See
CURRENT ACTIVE EDGE STATUS and INCONCLUSIVE HYPOTHESES above, and
`docs/research/H_MOMENTUM_001_MULTI_HORIZON_INTERACTION_PREREGISTRATION.md`
for the full breakdown. If ever revisited, it would need more elapsed
calendar time to widen the out-of-sample window under the SAME frozen
thresholds, not a retry with adjusted percentiles.

**Priority #3, accumulating live forecast evidence — audited
2026-09-10, infrastructure confirmed healthy, progress currently
stalled on the scheduler.** Read `predictions/direction_forecast.py`'s
resolution logic directly and ran `main.py evaluate-forecasts
--resilient` for real (read-only, no credentials needed, no historical
record modified). **No bug found.** 15 total forecasts, 4 resolved
(unchanged — the same known stale-reference-price batch already
excluded from calibration), 11 legitimately ACTIVE (too young — only
one trading day has elapsed against a 5-bar horizon — and the
underlying market-data cache for those 11 symbols hasn't advanced
since 2026-09-08, itself downstream of the scheduler being down). A
real operational guardrail was identified and deliberately NOT acted
on: all 11 pending symbols are also part of the 32-symbol research
universe with 10-year cached depth, and a naive refresh via
`evaluate-forecasts`'s own default `--period=1y` would silently
downgrade that depth — not worth the risk today regardless, since even
a safe refresh would only advance one trading day, resolving nothing.
This clears naturally once the scheduler is restored. No new
hypothesis or pre-registration needed — just elapsed time (and the
scheduler).

**Priority #4, microstructure — explicitly gated, likely blocked.**
Only pursue if existing data depth is sufficient; the session's own
prior finding (`H_OPENRANGE_001`, INSUFFICIENT_DATA) showed only ~60
trading days of intraday history, making every split fundamentally
underpowered. Do not revisit without either more elapsed calendar time
or a longer-history intraday data source.

**New this segment, outside the user's own 4-item priority list but
selected via a bounded registry audit per this segment's own mission
instructions (avoid renaming/re-parameterizing already-weak families;
prioritize genuinely untested Indian-market-specific mechanisms):
`H_BREADTH_001` (market breadth), REJECTED via a clean sign-order
reversal — see CURRENT ACTIVE EDGE STATUS and REJECTED HYPOTHESES
above for the full breakdown, including the genuine methodological
finding that narrow breadth and NIFTY's own uptrend classification are
close to mutually exclusive on this data.**

**Already tried, do not retest**: volatility contraction (`H_VOL_001`,
REJECTED), the market-trend/volatility-regime sweep (`H_MEANREV_003`),
two independent exit-architecture executable-conversion designs
(`H_MEANREV_004`, `H_EXIT_005`), extreme-move/post-shock asymmetry
(`H_EXTREME_001`, REJECTED), the short-weakness/long-strength
interaction at 20th/80th percentile thresholds specifically
(`H_MOMENTUM_001`, INCONCLUSIVE — see above; do not silently re-run
with different percentiles chasing a decisive result, that would be
the prohibited post-hoc threshold search), and market breadth at the
20th/80th percentile threshold and h10 horizon specifically
(`H_BREADTH_001`, REJECTED — see above; do not silently re-run with
looser/tighter breadth thresholds chasing a decisive result). Universe-
generalization for `H_MEANREV_003` (per the `H_XSECT_006` precedent)
remains a legitimate, cheap, not-yet-run check, but is lower priority
than a genuinely new hypothesis family.

**Next candidate families not yet tested, for the next segment's own
bounded registry audit (not pre-committed, subject to that audit's own
findings)**: turn-of-month/institutional-flow calendar effects
(mechanistically distinct from the already-tested day-of-week Tuesday
effect, though likely to face the same cost/no-index-execution-vehicle
wall `H_CALENDAR_001`/`002` already hit); volume-price divergence (a
stock rising on declining volume, distinct from the already-tested
volume-CONFIRMATION formulation in `H_ENTRY_002`); a looser breadth
threshold or a different target (e.g., forward UNIVERSE-pooled returns
instead of `^NSEI` alone) if market breadth is ever revisited — not
planned without new justification, per the no-parameter-mining
discipline.

**If the exit-architecture thread is ever resumed (not currently
planned)**: regime-invalidation exit (exit when `TRENDING_UP` ends),
named in `H_EXIT_005`'s own pre-registration as the next candidate —
but per the user's explicit instruction, this must not be started
without genuinely new evidence, and any future attempt must first be
checked for whether its own condition can fire on a still-net-
unprofitable trade (see BIGGEST RISKS item 11 above), not just for
whether it fires at all.

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
