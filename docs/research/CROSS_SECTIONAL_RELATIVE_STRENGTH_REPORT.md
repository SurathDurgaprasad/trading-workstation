# Cross-Sectional Relative Strength — Validation Report

Hypothesis: `H_XSECT_001` (`strategy/hypothesis_registry.py`).
Mission: "INDIAN NSE TRADING BRAIN — EDGE DISCOVERY PHASE," 2026-09-09.
This report exists per that mission's own explicit instruction:
"IF A REAL EDGE APPEARS: do NOT immediately modify the live paper
trading strategy. First: create a dedicated validation report... verify
no data leakage... verify concentration... verify era stability...
register as PROMISING... run SHADOW MODE." This document is that
validation report.

## 1. The question

Every prior hypothesis in this project tested a stock's own signal in
isolation — "does this stock's own price behavior predict its own
forward return." This project never built genuine **cross-sectional**
ranking: comparing all 32 universe stocks against *each other* on the
*same date* and asking whether the ranking itself carries information.
`quant_research/relative_strength_signal.py`'s own module docstring
flagged this gap explicitly and named it as the natural next step if
its own (rejected) single-symbol finding ever needed following up.

The question: on each trading day, rank all 32 NSE universe stocks by
trailing N-day return. Do the **leaders** (top quintile) or the
**laggards** (bottom quintile) show better forward returns?

## 2. What was built

`quant_research/cross_sectional.py` — a minimal, pure-measurement
ranking engine (not a portfolio/rebalancing/execution engine), reusing
`quant_research.market_behavior.SymbolDataset`/`build_universe_datasets`
and their existing `fwd_return_h` columns completely unchanged. The
only new logic: for each shared calendar date, gather every symbol's
score, rank them, and bucket into quantiles. A date is skipped entirely
(never padded) if fewer than 15 of 32 symbols have a valid score that
day. 7 new unit tests (`tests/test_cross_sectional.py`) cover causality
(no look-ahead in the return columns), correct bucket assignment, the
minimum-symbols-per-date guard, missing-data exclusion (never
fabricated as a neutral score), and period filtering.

## 3. Pre-specified experiment design

Taken directly from the mission's own text, not fit to this data:
lookbacks **5, 20, 60** bars; horizons **1, 5, 20** bars; **5 buckets**
(quintiles). Full 32-symbol NSE universe, 10 years daily
(2016-09-08 → 2026-09-08). Shared development/validation/out-of-sample
split (`backtesting.splits.split_periods`, the same 60/20/20 convention
every hypothesis in this project uses) applied **once** to the shared
universe calendar, not per-symbol — cross-sectional ranking is
meaningless without one shared reference date.

## 4. Headline finding

Across **all three lookbacks and all three splits**, the direction is
strikingly consistent: **laggards (Q5) outperform leaders (Q1)** — the
opposite of naive momentum, and the same direction as this project's
entire prior research history (every "buy strength" formulation this
project has ever tested — volume-confirmation, momentum-acceleration,
single-symbol relative strength, breakout quality — REJECTED; mean
reversion the consistently more promising family). This is now
independently confirmed via a genuinely different research design.

## 5. Strongest configuration: 60-day lookback, 20-day horizon

"Buy the bottom 20% of the universe by trailing 60-day return, hold 20
days." Q5's own absolute forward return (the real, tradeable, long-only
signal):

| Split | n | Mean return | 95% CI |
|---|---|---|---|
| Development | 9,961 | +1.525% | [+1.355%, +1.695%] |
| Validation | 2,946 | +2.378% | [+2.146%, +2.611%] |
| Out-of-sample | 2,879 | +0.487% | [+0.258%, +0.716%] |

**Decisive and positive in all three splits, never reversing.** This is
the first hypothesis in this project's multi-session history where that
is true.

## 6. Adversarial validation (deliberately applying every check that has previously killed a promising-looking candidate in this project)

**(1) Cost sensitivity.** Full-period pooled mean +1.568% (n=14,363,
CI-decisive) survives realistic costs with the widest margin of any
finding in this project: still net **positive at a 1.00% round-trip
cost** (net +0.568%), roughly 5x the realistic ~0.21% estimate used
elsewhere in this project (`backtesting.costs.CostModel.
india_nse_intraday_2026()`). Gap-fade and the Tuesday effect both
failed at a fraction of this margin.

**(2) Symbol concentration.** 29 of 32 symbols show a positive mean Q5
return (only ITC.NS -1.30%, EICHERMOT.NS -0.52%, HEROMOTOCO.NS -0.13%
negative, all small). Sample sizes per symbol range 175–695 — broadly
distributed, not concentrated in a handful of names.

**(3) Sector concentration.** No single sector dominates — the largest
bucket (NIFTY_IT) is only 17.8% of the pooled sample. Every sector
shows a positive or near-zero mean (weakest: NIFTY_AUTO +0.05%,
NIFTY_FMCG -0.03%; strongest: NIFTY_FINANCIAL_SERVICES +4.91%). The 11
symbols this project's own sector map cannot classify (31% of the
sample) independently show the same effect (+1.58%) — not an artifact
of an incomplete sector map.

**(4) Era stability.** Remarkably consistent across three
decade-spanning windows:

| Era | n | Mean return | 95% CI |
|---|---|---|---|
| 2016–2019 | 4,524 | +1.423% | [+1.195%, +1.652%] |
| 2020–2022 (incl. COVID crash/recovery) | 4,482 | +1.748% | [+1.444%, +2.051%] |
| 2023–2026 | 5,357 | +1.539% | [+1.367%, +1.711%] |

No decay, no era-dependence — the opposite of `H_CONTEXT_MARKET_005`'s
own stark sign-reversal on a similarly long window.

**(5) Liquidity.** Both above-median (n=6,826, +1.668%, CI-decisive)
and below-median (n=7,537, +1.477%, CI-decisive) `avg_daily_value`
halves show strong, comparable effects — not an illiquid-execution
artifact, the exact issue that disqualified gap-fade.

**(6) Non-overlapping / independence check.** The single most important
statistical concern for a rolling 20-day-forward-return design:
consecutive days' Q5 memberships share up to 19 of 20 forward days, so
the pooled n=14,363 estimate's own confidence interval could be
misleadingly narrow (true independent sample size much smaller than
raw n). Re-measured using **only every 20th trading day** as a
rebalance date (124 genuinely non-overlapping dates across the full 10
years): Q5 n=720 (properly independent), mean=+1.526%, CI=[+0.927%,
+2.126%] — barely different from the overlapping-window estimate and
still comfortably decisive. **The effect is not an artifact of
overlapping-window inflation.**

**(7) Parameter stability.** The same direction held across all 3
independently pre-specified lookback windows (5/20/60 bars) without any
tuning — not a single cherry-picked configuration.

## 7. Data leakage check

`fwd_return_h = close.shift(-h) / close - 1` — the same, already
extensively audited forward-return machinery every hypothesis in this
project's history uses, deliberately the *only* sanctioned look-ahead
in `quant_research/market_behavior.py`, used here exactly as everywhere
else: only ever as the outcome being measured, never as an input to the
ranking itself. The ranking score (`trailing_return_N`) is
`close.pct_change(N)`, strictly backward-looking. No new leakage
surface introduced.

## 8. What this is NOT yet

This is a **measurement finding**, not an executable strategy. No
signal has been run in shadow mode. No position sizing, entry/exit
mechanics, or paper-execution wiring exists for it. Implementing it as
a real (paper) strategy would need: a `Strategy`-protocol wrapper (a
20-day-hold rule is directly compatible with this project's existing
long-only, multi-bar-hold `backtesting/engine.py` — unlike gap-fade,
which needed same-day forced-exit infrastructure this project doesn't
have), a frozen, pre-specified entry/exit rule (e.g., enter at close
when a stock is newly in the bottom quintile, exit after 20 bars,
reusing `strategy/baseline.py`'s existing stop/target constants the
same way `H_RELSTRENGTH_001` already does), and a genuine walk-forward
backtest through the existing promotion gate
(`strategy/promotion_gate.py`) before any shadow-mode observation.

## 9. Verdict

**INCONCLUSIVE, not PROMOTED** — by explicit choice, not by a
demonstrated flaw. Every adversarial check this project's research
discipline has ever applied to any candidate was applied here, and this
is the first candidate to survive all of them. The registry status
stays conservative because this project's own promotion discipline
requires a shadow-mode observation period before anything stronger, and
that has not yet happened. This is, by a wide margin, the strongest and
most rigorously-validated finding in this project's history to date.

## 10. Recommended next steps, in order

1. Build the minimal `Strategy`-protocol wrapper for "bottom-quintile
   60-day trailing return, 20-day hold" and run it through the existing
   `backtesting/runner.py`/`strategy/promotion_gate.py` machinery — a
   real, cost-aware, risk-sized backtest, not just the raw price-behavior
   measurement this report is based on (the same "does the raw finding
   survive becoming an actual trade" question `H_MEANREV_002` asked of
   its own raw finding). **DONE — see §11 below. Result: NEGATIVE.**
2. ~~If that backtest also clears the promotion gate, run it in shadow
   mode~~ — **does not apply.** The executable wrapper did not clear the
   promotion gate (§11), so no shadow-mode observation was started.
3. Test the sector-relative and NIFTY-relative score variants the
   mission's own text also named (`stock_return_N - nifty_return_N`,
   `stock_return_N - sector_return_N`) as independent replications, not
   assumed to behave identically to the absolute-return version tested
   here. **DONE — see §12 below.**

## 11. Addendum — the real, cost-aware, risk-sized backtest (`H_XSECT_002`)

Full record: `H_XSECT_002` in `strategy/hypothesis_registry.py`,
status `REJECTED`. Summary here so this report stays a complete,
standalone account of what has and hasn't been validated.

`quant_research/cross_sectional_strategy.py` implements
`CrossSectionalLaggardStrategy` (Strategy protocol; fires a LONG entry
only on a stock's first day newly in Q5 by trailing 60-day return,
reading a bucket-membership column precomputed once across the whole
universe) and runs it through `backtesting.exit_experiments.
run_time_based_exit_backtest` (reused unchanged, `max_holding_bars=20`)
with `CostModel.india_nse_intraday_2026()` and `risk.engine.RiskEngine`
sizing — the same real machinery, and the same `strategy/
promotion_gate.py::evaluate_promotion` verdict, every other hypothesis
candidate in this project is judged by. Single frozen configuration,
no parameter search.

**Result: NEGATIVE.** Development n=623 mean **-0.17%**
(CI=[-0.63%,+0.28%], statistically meaningless); validation n=236 mean
**+0.84%** (CI=[+0.30%,+1.37%], positive); out-of-sample n=227 mean
**-0.76%** (CI=[-1.31%,-0.21%], CI-decisive **negative**). The
out-of-sample split's confident negative verdict fails
`evaluate_promotion` outright: *"decisive evidence of harm, not merely
unproven. Must not be promoted."*

**Mechanism (diagnostic on the already-computed trades, not a re-run
with different parameters):** STOP exits dominate the loss in every
split — development 320/623 trades (51%) exited via STOP for a
combined **-₹160,628** (avg -₹502/trade), versus only 118 EXPIRED
(the pure 20-day time-cap exit, the closest analogue to §5's raw
measurement) for +₹11,969 (avg +₹101/trade); out-of-sample 130/227
(57%) exited via STOP for **-₹61,371** (avg -₹472/trade) versus 36
EXPIRED for only -₹1,006 (avg -₹28/trade — mildly negative, but two
orders of magnitude smaller). The ATR-based stop reused from
`strategy/baseline.py` was calibrated for `TrendMomentumBaseline`'s
trend-**continuation** setups, never validated for a reversal/
mean-reversion signal — the working explanation is that laggards
often fall further before the 20-day reversal §5 measured actually
occurs, and this stop is clipping those positions before it can play
out.

**What this does and does not mean.** The §4–§6 raw measurement is
**not invalidated** — it remains a real, adversarially-validated
statistical fact about NSE cross-sectional price behavior; nothing
about the mechanism above changes any of §6's checks. What is rejected
is narrower: *this specific, naive execution wrapper* — a stop/target
mechanic borrowed unchanged from a different strategy family — does
not monetize the finding. Per this project's own multiple-testing
discipline, no alternative stop/target width was tried here, and none
will be tried as a tuning follow-up on this same result: a genuinely
different, honestly pre-registered exit design (e.g. one built for
mean-reversion's own known dynamics — wider stops, or no hard stop at
all within the 20-day hold) would need to be its own new, independently
motivated hypothesis, not a retry of this one.

**Net effect on status:** `H_XSECT_001` stays `INCONCLUSIVE` (a raw
measurement claim, not an executable-strategy claim) — it is not
promoted to `PROMISING`, and shadow mode does not start on the strength
of this execution design. The mission's own "IF A REAL EDGE APPEARS"
workflow's "verify costs" step is exactly where this candidate stopped,
and honestly reporting a real negative result at that stage — rather
than retrying with looser risk parameters until something clears the
gate — is the discipline this whole research program is built on.

## 12. Addendum — sector-relative and NIFTY-relative score variants (`H_XSECT_003`)

Full record: `H_XSECT_003` in `strategy/hypothesis_registry.py`,
status `INCONCLUSIVE`. Two independently-motivated variants, treated
as two separate questions since — as the result below shows — they
turned out not to be equally independent.

**NIFTY-relative — not actually an independent test.** Subtracting
`^NSEI`'s own trailing-60-day return from every stock's score is a
uniform per-date shift: every symbol loses (or gains) the identical
amount on a given date, which cannot change that date's cross-sectional
rank order. This is a mathematical fact, not an empirical claim — and
it was confirmed empirically on the real 32-symbol dataset anyway: Q5
bucket assignments (sample size and mean return, to six decimal places)
were **byte-identical** to the absolute-return version in all three
splits. The NIFTY-relative variant will always reproduce §5's result
exactly (up to `^NSEI`'s own handful of warm-up dates) and does not
need to be tested again — a useful, if modest, finding in its own
right, since it forecloses a line of "independent confirmation" that
was never going to be independent.

**Sector-relative — genuinely independent, and confirms the pattern.**
Each stock's own NIFTY sector index return is subtracted instead — a
sector-*group*-specific shift, which can and does reorder the
cross-section differently. Tested on the 21/32 symbols
`market_intelligence/nse_sector_map.py`'s `NSE_SECTOR_MAP` covers
(a real, disclosed universe reduction), against the 6 real sector
indices those symbols map to, each with a full, verified 10-year Yahoo
history. Result: Q5 (sector-relative laggards) is **CI-decisive
positive in all three splits, never reversing** — development n=5,692
+2.265% (CI=[+2.011%,+2.519%]); validation n=1,964 +2.214%
(CI=[+1.935%,+2.493%]); out-of-sample n=1,920 +0.487%
(CI=[+0.219%,+0.755%]) — the out-of-sample figure matches §5's
absolute-return out-of-sample result (+0.4872%) to within 0.0002
percentage points. Q5 beats Q1 (leaders — CI-decisive only in
development, not out-of-sample) in every split. This is a real,
independent replication of the laggard-outperformance direction under
a materially different score formula and a smaller, differently
composed universe.

**What this does and does not mean.** Promoted the reusable primitive
behind both checks into `quant_research/cross_sectional.py` as
`attach_relative_score_column` (4 new tests), since a single function
covers both a shared-benchmark and a per-symbol-sector lookup with no
duplicated logic. Status stays `INCONCLUSIVE` for the same reason
§9/§11 already gave: this is again a raw measurement, not an
executable-strategy result. Given §11's own negative result for the
closely-related absolute-return version's naive stop/target wrapper,
this sector-relative variant's own executable behavior is **explicitly
not assumed** to behave any differently — it has not been tested, and
doing so would need its own new, honestly pre-registered hypothesis,
not an assumption carried over from a different variant's result.

## 13. Addendum — does a wider/absent stop rescue the executable backtest? (`H_XSECT_004`)

Full record: `H_XSECT_004` in `strategy/hypothesis_registry.py`,
status `REJECTED`. §11's own mechanism finding — that STOP exits drove
nearly all of the loss while EXPIRED exits were only mildly negative —
raised an obvious, disclosed follow-up question, already named in
`docs/INDIAN_TRADING_BRAIN_STATUS.md` before this test was written:
would a wider (or effectively absent) stop rescue the edge? Two, and
only two, pre-specified variants were tested — `wide_stop`
(`stop_atr_multiplier=4.5`, 3× the original) and `no_stop`
(`stop_atr_multiplier=20.0`, wide enough that a STOP exit within a
20-bar hold is not realistically reachable) — with the target distance
held fixed at the original formula in both, so only one variable
changed at a time.

**Result: both variants REJECTED, and both performed WORSE than the
original.** `wide_stop`: development and validation statistically
meaningless, out-of-sample **-1.47%** (CI=[-2.29%,-0.65%]) — worse
than §11's own -0.76%. `no_stop`: **all three splits** CI-decisive
negative — development -5.46%, validation -2.66%, out-of-sample
-4.61% — far worse than either the original or `wide_stop`, including
in development and validation, which were mixed-to-positive under the
original tight stop.

**The mechanism is a genuine correction to §11's own reading.** §11
observed STOP-exited trades looked terrible and EXPIRED-exited trades
looked only mildly negative, and inferred that removing the stop would
let those same trades land in the mild EXPIRED bucket instead. That
inference was wrong: the trades that populate the EXPIRED bucket are
not fixed — they change when the stop changes. Under the tight stop, a
trade that keeps deteriorating gets cut at a bounded loss (~1.5×ATR)
and is recorded as STOP; under a wide or absent stop, that *same*
trade is instead held to day 20's close, which can be a far larger,
uncapped loss, now recorded as EXPIRED — dragging that bucket's own
average down sharply. A meaningful fraction of laggards simply do not
reverse within 20 days and keep falling further; the original stop was
doing real, protective work bounding that tail risk, work invisible in
§5's pooled, unconditioned mean-return statistic, which reports only
the average outcome, not the per-trade downside variance a real
position is actually exposed to. This is the same kind of lesson
`H_GAP_003`'s small-sample illusion and `H_CONTEXT_MARKET_005`'s
era-instability already taught this project in different forms: a
pooled average can look robust while hiding structure that only
becomes visible once real trade mechanics are actually simulated.

**What remains open.** This closes the "wider/absent stop" direction
only. It does not test the opposite direction — a *tighter* stop than
the original 1.5×ATR, which this entry's own mechanism explanation
would predict might do even better by capping the same tail-risk
trades even earlier. That remains untested and would need its own new,
honestly pre-registered hypothesis before any code is written, not a
same-session follow-up chasing this result.

## 14. Reconciliation — why does the raw measurement (§5) diverge from every executable test so far (§11, §13)?

Per the "EDGE DISCOVERY mission" continuation's own explicit instruction
before any further code was written: a precise reconciliation between
§5's raw forward-return measurement and every executable backtest
tested against it (`H_XSECT_002`, `H_XSECT_004`). Four real, disclosed
structural differences, not one:

1. **Entry timing.** §5's `fwd_return_h = close.shift(-h)/close - 1`
   implicitly assumes a trade can be entered at the *same* close used
   to compute the ranking score — a same-day, zero-lag entry. Every
   executable backtest in this project, `H_XSECT_002`/`H_XSECT_004`
   included, enters at the *next* bar's open instead (with slippage).
   This is a real, disclosed, one-day lag that has never been
   separately isolated or quantified.
2. **Path-dependence.** §5 is a pure, unconditional fixed-horizon
   return — nothing exits early under any condition. `H_XSECT_002`'s
   own exit-reason diagnostic (§11) shows a TARGET exit fired in every
   variant tested so far, including `H_XSECT_004`'s `no_stop`
   configuration (29–197 trades per split, every time) — meaning *none*
   of the executable tests to date actually measured the same
   fixed-horizon quantity §5 reports. This was a genuine, previously
   unexamined confound.
3. **Sampling.** §5 pools every `(date, symbol)` observation where a
   symbol is *currently* in the bottom quintile that day (development
   n=8,538 for this configuration). `H_XSECT_002`/`H_XSECT_004` only
   trade a symbol's *first* day newly entering the bottom quintile
   (development n=623 — about 7% of §5's own sample). Whether that
   much smaller, specifically-selected sub-population behaves like the
   full pooled population was never checked.
4. **Portfolio construction.** §5's daily cross-sectional pooling is
   economically closest to holding a continuously diversified basket
   of every current bottom-quintile member at once. `H_XSECT_002`/
   `H_XSECT_004` test independent, symbol-isolated trades with no
   capital allocation, concurrent-position, or rebalance-calendar
   concept at all.

`H_XSECT_005` (below) addresses (3) and (4) directly, and (2)
completely — while deliberately holding (1) fixed, to keep this a
single, well-scoped test rather than changing four variables in one
shot.

## 15. Addendum — does a genuine portfolio reproduction change the answer? (`H_XSECT_005`)

Full record: `H_XSECT_005` in `strategy/hypothesis_registry.py`,
status `INCONCLUSIVE` (`INSUFFICIENT_DATA`). New module
`quant_research/cross_sectional_portfolio.py` (8 new tests): an
equal-weight, periodically-rebalanced portfolio backtest reproducing
§5's own exact economic design — rebalance every 20 trading bars
(non-overlapping, the same cadence §6's own independence check already
validated), form a basket of every symbol *currently* in the bottom
quintile by trailing 60-day return, hold for a pure fixed 20-bar
horizon with **no stop and no target of any kind**, real per-position
transaction costs (`CostModel.india_nse_intraday_2026()`).

**Result: no sign reversal in any split, unlike every prior executable
test.** 120 total rebalance periods (72/24/24 across
development/validation/out-of-sample). Mean portfolio return per
period: development **+0.76%** (n=72, win rate 54.2%); validation
**+1.81%** (n=24, win rate 66.7%); out-of-sample **+0.46%** (n=24, win
rate 50.0%) — positive in all three, in sharp contrast to
`H_XSECT_002`'s out-of-sample -0.76% and both `H_XSECT_004` variants.
The out-of-sample figure is strikingly close to §5's own raw
out-of-sample measurement for this exact configuration (+0.487%) —
net of real transaction costs, a portfolio-level reproduction lands
almost exactly where the cost-free raw measurement predicted.

**But this is not a promotion, and the reason is purely statistical
power, not a weak effect.** `evaluate_promotion`'s own verdict is
`INSUFFICIENT_DATA`: development is statistically meaningless
(CI=[-0.71%,+2.23%], straddles zero), and validation/out-of-sample
both fall below the promotion gate's own 30-observation minimum at
n=24 each — a structural consequence of collapsing ten years of daily
data into 20-day non-overlapping portfolio periods (~126 periods is
close to the ceiling this dataset can ever provide at this cadence),
not a fixable implementation gap. Basket size is a constant 6 members
per rebalance; turnover is a disclosed 48% per 20-day period (52%
basket overlap between consecutive rebalances).

**What this means for the mission's central question.** `H_XSECT_001`'s
raw finding does *not* clearly fail once genuinely reproduced at the
portfolio level with no path-dependent exit — the negative verdicts
from `H_XSECT_002`/`H_XSECT_004` look substantially attributable to
those tests' own structural choices (a stop/target mechanic borrowed
from a trend-continuation strategy; independent single-symbol trades
rather than a diversified basket), not to the underlying cross-sectional
signal being illusory. This result is directionally the most
encouraging in the entire `H_XSECT_00x` executable-strategy family —
but it is explicitly *not* strong enough to promote or move to shadow
mode. Directional-but-inconclusive is reported as exactly that, not
rounded up.

**Open, not pursued in this same run** (each would need its own
pre-registration): a wider universe would reduce per-period portfolio
variance through more diversification without increasing the number of
independent time periods — a distinct, legitimate lever from more raw
data; a shorter rebalance cadence would roughly double the period count
but has not been validated for independence the way the 20-day cadence
was, and would reintroduce overlapping 20-day holding windows across
staggered rebalances; and the entry-timing mismatch (point 1 above)
remains completely untested.
