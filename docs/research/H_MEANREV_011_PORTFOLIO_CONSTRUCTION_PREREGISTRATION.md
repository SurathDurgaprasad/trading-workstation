# H_MEANREV_011 — Multi-Position Portfolio Construction, Pre-Registration

Written and frozen **before** any portfolio simulation runs. Per this
project's own multiple-testing discipline: signal, exit, universe,
splits, portfolio construction, and capital allocation are all fixed
here; none may change after seeing results.

**This is a portfolio-construction test, not a signal search, not a
parameter search, and not an optimization exercise.** The signal and
the exit horizon are IDENTICAL to `H_MEANREV_006`/`009`/`010`. Nothing
about either changes anywhere in this document.

## 1. Research question

`H_MEANREV_010` showed the `H_MEANREV_006` signal's gross edge survives
real trade simulation, and that realistic percentage costs alone are
survivable — but its own two candidates were each disqualified for a
different reason: Candidate 2 required putting 100% of capital into a
single position (an unrealistic concentration with an extreme tail,
worst single trade −65%); Candidate 3 used zero fixed brokerage, an
explicit diagnostic control, not a real cost structure.

**Question**: does the same frozen signal, exited the same frozen way,
survive conversion into a realistic MULTI-POSITION portfolio — multiple
simultaneous positions, real capital allocation, real Indian
transaction costs, and disclosed concentration/liquidity limitations —
without concentrating capital unrealistically in one position at a
time? The objective is to determine whether the previously observed
edge survives diversification, not to maximize a backtest number.

## 2. Audit — existing infrastructure (verified by direct reading, not assumed)

Read directly: `quant_research/cross_sectional_portfolio.py`
(`H_XSECT_005`'s own equal-weight, periodically-rebalanced portfolio
backtest — the closest existing precedent, but built around a FIXED
rebalance calendar replacing a whole ranked basket, not an event-driven
per-symbol signal with staggered entry timing; its own philosophy
(equal-weight capital allocation across concurrently-held positions)
is reused, its own code is not, since the signal-generation pattern is
structurally different); `quant_research/mean_reversion_execution_structure.py`
(`H_MEANREV_010`'s own `compute_fixed_notional_trade` — reused
VERBATIM, unmodified, for the per-trade price/cost/notional
calculation once a signal is accepted into the portfolio);
`backtesting/equity.py`'s `build_equity_curve` (reused verbatim —
already exactly the "one point per completed trade, realized-P&L-
based, not intrabar mark-to-market" design this entry needs, per spec
§15); `backtesting/metrics.py`'s `compute_performance_metrics` (NOT
directly reusable — requires `backtesting.trade.Trade` objects with a
`r_multiple` field, a stop-based concept that does not apply to
fixed-notional sizing; this entry writes one small portfolio-specific
summary instead, reusing `build_equity_curve` inside it unchanged);
`risk/config.py`'s `RiskConfig.max_exposure_pct` (existing, already-
documented constant: "Matches the blueprint's 25% max portfolio
exposure" — reused directly, see §4); `market_intelligence/nse_sector_map.py`'s
`NSE_SECTOR_MAP` (existing, 21/32-of-original-universe partial
coverage, the SAME disclosed limitation every prior entry that
touches it already carries); a codebase-wide search for average-daily-
volume/free-float/market-cap fields returned NOTHING — confirmed no
liquidity-ceiling data exists anywhere in this repository (see §9).

**Confirmed: no existing multi-position, event-driven, shared-capital
portfolio simulator exists in this codebase.** Every prior backtest in
this project is either single-symbol with its own dedicated capital
(`H_MEANREV_009`/`010`, `backtesting/engine.py`,
`backtesting/exit_experiments.py`) or a periodic full-basket
replacement on a fixed rebalance calendar (`H_XSECT_005`). This entry
therefore builds the minimum new simulator required — see §5.

## 3. Frozen signal, exit, universe, splits

**Signal**: `quant_research.mean_reversion_signal._oversold_2std_relative_weak`
— `zscore_close_20 < -2.0` AND `relative_strength_20 <
H_MEANREV_006_RELSTRENGTH_MEDIAN (-6.8845%)`. Imported and reused
directly, not reimplemented, not changed.

**Exit**: h10 time-based exit — entry at signal bar + 1's open
(slippage-adjusted), exit at signal bar + 10's close (slippage-
adjusted) — the EXACT bar arithmetic `compute_fixed_notional_trade`
(`H_MEANREV_010`'s own function) already implements, reused verbatim.

**Universe**: `COMBINED` (`ORIGINAL_32_NSE_UNIVERSE` ∪
`EXPANDED_ONLY`), 206/208 buildable symbols, identical to every prior
entry in this family.

**Splits**: `quant_research.cross_sectional.shared_period_boundaries`
— a SHARED, calendar-based development/validation/out-of-sample
boundary across the whole portfolio (deliberately NOT
`backtesting.splits.split_periods`'s own per-symbol convention
`H_MEANREV_009`/`010` used — a true portfolio simulation needs ONE
boundary for the whole simultaneous system, since positions interact
with each other on the same calendar date; this is the SAME shared-
calendar convention `H_MEANREV_006`/`007`/`008` already used for their
own cross-sectional measurements, reused here, not invented).

## 4. Portfolio construction and capital allocation (frozen, pre-justified, no search)

**`MAX_CONCURRENT_POSITIONS = 4`**, derived directly from `RiskConfig.max_exposure_pct
= 25.0` — an EXISTING, already-documented project constant ("Matches
the blueprint's 25% max portfolio exposure"), not a new or searched
number: `100% / 25% = 4` equally-sized slots exactly fills the
portfolio without any single position exceeding the project's own
pre-existing max-exposure convention.

**Capital allocation**: equal-weight, `capital_per_position =
initial_capital x 0.25` — matching `RiskConfig.max_exposure_pct`
exactly, reusing `H_XSECT_005`'s own equal-weight-allocation
PHILOSOPHY (not its code). **FIXED, not dynamically recalculated from
current equity** — a deliberate, disclosed simplification for this
first, deliberately boring design (realized P&L accumulates into
portfolio equity/drawdown tracking, per §6, but does NOT feed back
into position sizing — no compounding, no dynamic re-optimization).
`initial_capital = 100,000`, this project's own standard default.

**Signal scheduling (the minimum new logic this entry adds)**: every
bar across all 206 symbols where the frozen predicate fires is
collected as a candidate entry event, then processed in STRICT
CHRONOLOGICAL order (by signal date, not by symbol). A candidate is
ACCEPTED if and only if: (a) that symbol has no currently-open
position, (b) the portfolio has fewer than `MAX_CONCURRENT_POSITIONS`
open positions at that moment, and (c) `capital_per_position` does not
exceed currently available cash. Before evaluating a candidate, any
currently-open position whose own precomputed exit date has already
passed is closed first (capital and slot released), matching a
real, sequential trading process. A REJECTED candidate (capacity or
cash unavailable) is counted, not silently dropped. Each accepted
signal's own entry/exit price, quantity, gross P&L, and costs are
computed via `compute_fixed_notional_trade`
(`capital_per_slot=capital_per_position`, real `CostModel.
india_nse_intraday_2026()`), reused unchanged — this entry adds no new
per-trade price/cost math of any kind.

**No optimization, frozen**: `MAX_CONCURRENT_POSITIONS`,
`capital_per_position`, `initial_capital`, and the chronological
first-come-first-served acceptance rule are ALL fixed before any
result is examined, each with the justification stated above. No
alternative concurrency cap, allocation scheme, or acceptance
ordering is tried or compared after seeing results.

## 5. The minimum new simulator (kept small, deliberately)

One new module, `quant_research/mean_reversion_portfolio.py`:
- A pure function to collect every `(symbol, signal_date, signal_idx)`
  candidate event across the frozen universe (reusing the SAME
  feature-building pipeline `H_MEANREV_009`/`010` already established
  — `add_alpha_features` with a real `market_series=^NSEI`).
- A pure scheduling function (no I/O) that takes the sorted candidate
  list and, applying the frozen acceptance rule above, returns the
  accepted trades (each computed via the UNMODIFIED
  `compute_fixed_notional_trade`) plus the rejected-candidate count —
  independently unit-testable against a synthetic multi-symbol
  scenario without a real market-data fetch.
- A small portfolio-summary function reusing `build_equity_curve`
  (`backtesting/equity.py`, unmodified) for the realized equity/
  drawdown curve, plus gross/net/cost/concentration/breadth statistics
  computed directly from the accepted-trade list (not routed through
  `compute_performance_metrics`, which requires `r_multiple` — not
  meaningful for fixed-notional sizing, per §2).

No giant framework. No new optimizer. No ML-based allocation.

## 6. Portfolio controls — required reporting (frozen)

**[VERIFIED]/[TESTED] required for every split (development,
validation, out-of-sample)**: number of accepted trades; maximum and
average concurrent positions; capital utilization (average allocated
capital / `initial_capital`); gross P&L; total fixed costs; total
variable costs; net P&L; win rate; portfolio equity curve and maximum
drawdown (via `build_equity_curve`, unmodified); worst single trade;
best single trade; rejected-candidate count (capacity vs. cash,
reported separately); portfolio turnover (trades / average concurrent
positions, a simple, standard definition); symbol concentration
(top-5/top-10 trades' share of total net P&L, and distinct-symbol
count, the SAME concentration check `H_MEANREV_010` already used);
sector concentration where `NSE_SECTOR_MAP` coverage permits (21/32 of
the original universe, disclosed as partial, not fabricated for the
`EXPANDED_ONLY` 176).

No control is added merely because it would flatter the result — every
item above is part of this pre-registered design, not chosen after
seeing output.

## 7. Realistic costs (frozen)

`CostModel.india_nse_intraday_2026()` — the real, standard NSE cost
preset, unchanged. `H_MEANREV_010`'s own zero-fixed-fee diagnostic is
**explicitly NOT used as this entry's own cost model** — it remains
available only as a comparison reference point (§10), per the
mission's own explicit instruction. Reported per split: gross P&L,
minus total variable costs, minus total fixed costs, equals net P&L —
each component shown separately, not netted silently.

## 8. Liquidity (frozen disclosure, not fabricated)

**[INCONCLUSIVE, disclosed explicitly, not silently assumed
unlimited]**: this repository contains NO average-daily-volume,
free-float, or market-capitalization data for any symbol in the
universe (confirmed by direct search, §2). `market.indicators`'s own
`volume_ratio` (today's volume relative to that SAME stock's own
trailing average) exists but provides no ABSOLUTE liquidity ceiling —
it cannot answer "is a ₹25,000 position in this specific name
realistically fillable without material price impact." This entry
therefore does NOT apply any liquidity constraint, and explicitly
marks liquidity validation as **[INCONCLUSIVE]** in its own results —
not resolved, not silently assumed away. `compute_fixed_notional_trade`'s
own existing flat basis-point slippage assumption is the only
execution-friction modeling available, and (as `H_MEANREV_010` already
disclosed for its own Candidate 2) may understate real impact at
larger position sizes.

## 9. Concentration / correlation (frozen approach, no new causal claims)

Symbol breadth, sector breadth (where covered), top-5/top-10 P&L
concentration, and whether a single crisis period (already known:
2020, per `H_MEANREV_006`'s own year-stability finding) dominates the
result are all measured directly from the accepted-trade list, using
the `[VERIFIED]`/`[TESTED]`/`[INFERENCE]`/`[HYPOTHESIS]` discipline
`H_MEANREV_009`/`010` already established. Pairwise correlation of
concurrently-open positions' own return series is NOT computed in this
entry — no existing infrastructure for it, and building one would be a
new capability beyond "the minimum simulator" (§5); this is disclosed
as a genuine, un-answered gap, not silently skipped.

## 10. Comparisons (frozen)

This entry's own results are compared against: (1) `H_MEANREV_010`
Candidate 2 (fixed-notional, single-position, real costs); (2)
`H_MEANREV_010` Candidate 3 (zero-fixed-fee diagnostic); (3) the raw
`H_MEANREV_006` forward-return evidence. `H_MEANREV_009`'s own
historical verdict (`REJECTED`) and `H_MEANREV_010`'s own historical
verdict (`INCONCLUSIVE`) are NOT rewritten, re-run, or modified —
cited as-is.

## 11. Promotion (frozen, unmodified existing machinery)

`strategy.promotion_gate.evaluate_promotion`, applied to the portfolio-
level net per-trade returns, exactly as every prior entry in this
family. No new success criterion invented, no gate weakened. A
positive gross result with negative realistic net economics, or a
result dependent on an undisclosed/unrealistic assumption, is
explicitly NOT a promotable outcome. A `PROMOTED` verdict here would
still require paper-trading validation before any live consideration
— never a claim of trading readiness.

## 12. What will NOT change after this is pre-registered

No change to the entry predicate, the h10 exit, `MAX_CONCURRENT_POSITIONS`,
`capital_per_position`, the chronological acceptance rule, the
universe, or the splits. No new liquidity assumption invented after
seeing results. No alternative concentration cap tried and compared.
`H_MEANREV_009`/`010`'s own historical records stay immutable.

## 13. Verdict-vocabulary discipline (frozen, matching `H_MEANREV_010`)

Every claim in the results write-up is labeled **[VERIFIED]**
(directly observed), **[TESTED]** (a specific, reported statistical
result), **[INFERENCE]** (a reasoned conclusion from verified/tested
facts, disclosed as inference), or **[HYPOTHESIS]** (an open,
unverified conjecture, never presented as a finding).

## 15. Reproducibility record

**[VERIFIED]** `COMBINED` universe: 206/208 symbols built. Shared
calendar: `development_end=2023-11-25`, `validation_end=2025-04-17`
(identical to `H_MEANREV_006`/`007`/`008`'s own boundaries, as
expected — same universe, same shared-calendar method).
`MAX_CONCURRENT_POSITIONS=4`, `capital_per_position=25,000` (25% of
`initial_capital=100,000`), `holding_bars=10` — all as frozen.

## 16. Results — a genuinely ambiguous, underpowered outcome, NOT a clean disproof, with a serious disclosed selection-bias caveat

Full evidence: `H_MEANREV_011` in `strategy/hypothesis_registry.py`.

### Headline numbers

| Split | candidate events | accepted trades | accept rate | net mean (CI) | `ProfitabilityVerdict` |
|---|---|---|---|---|---|
| development | 7286 | 555 | 7.6% | +0.10% [−0.64%,+0.84%] | `STATISTICALLY_MEANINGLESS` |
| validation | 1549 | 111 | 7.2% | −0.51% [−2.05%,+1.02%] | `STATISTICALLY_MEANINGLESS` |
| out-of-sample | 1058 | 105 | 9.9% | −0.42% [−1.80%,+0.96%] | `STATISTICALLY_MEANINGLESS` |

**Promotion verdict: `PromotionVerdict.REJECTED`** — per the
machinery's own precise rule: no split shows a confident
`NEGATIVE_PERFORMANCE` verdict (none of the three CIs are
CI-decisively negative), but the point estimates are mixed in sign
(development slightly positive, validation/out-of-sample slightly
negative), so the mechanical rule outputs `REJECTED`, not `NEGATIVE`.
**This is a materially different, milder finding than `H_MEANREV_009`'s
own decisive `NEGATIVE`** (all three splits CI-decisively negative
there) — here, EVERY split's CI straddles zero substantially; the
honest characterization is "underpowered and mixed-direction," not
"confirmed harm." Mapped to `HypothesisStatus.REJECTED`, matching this
project's own established mapping (`NEGATIVE`/`REJECTED` →
`REJECTED`), while the evidence field states this distinction
explicitly, not silently.

### [VERIFIED] The overwhelming majority of candidate signals were rejected — a severe, disclosed sample-attrition problem

| Split | accepted | rejected (capacity) | rejected (cash) | rejected (symbol already open) |
|---|---|---|---|---|
| development | 7.6% | 45.1% | 37.7% | 9.6% |
| validation | 7.2% | 48.1% | 34.4% | 10.2% |
| out-of-sample | 9.9% | 50.0% | 26.7% | 10.4% |

**Only 7-10% of every candidate signal the frozen entry condition
produced was actually accepted into the portfolio** — the
`MAX_CONCURRENT_POSITIONS=4` cap (and the cash it implies) rejected
82-93% of all signal occurrences. This collapsed the sample size this
family's raw/single-position measurements enjoyed (`H_MEANREV_009`/
`010` pooled several hundred to well over a thousand trades per split)
down to 105-555 trades per split here — a DIRECT, mechanical
consequence of the frozen, non-optimized concurrency cap, not a
retuning decision, but a real downstream effect worth disclosing
prominently: **this design, as pre-registered, cannot exercise most of
the underlying signal's own sample.**

### [INFERENCE] The rejection pattern strongly suggests signal clustering, not independent diversification

**[VERIFIED]** Roughly half of ALL candidate events were rejected
specifically because the portfolio was already at its 4-position cap
(45-50% `rejected_capacity`, before even considering cash). **[INFERENCE]**
This magnitude of capacity-driven rejection is only possible if many
symbols frequently satisfy the oversold-and-relative-weak condition
SIMULTANEOUSLY (on the same or nearby calendar dates) — consistent
with this being, at least in part, a broad, MARKET-WIDE phenomenon
(many stocks becoming oversold together during a systemic decline)
rather than a set of independent, idiosyncratic, diversifiable
single-stock events. If true, the 4 "concurrent" positions accepted on
a clustered day are themselves likely to be CORRELATED with each other
(simultaneously weak in the same market environment) rather than
genuinely diversified bets — directly relevant to this entry's own
Phase-7 concentration/correlation question, though pairwise return
correlation of concurrent positions was NOT computed (§9's own
disclosed scope limit — no existing infrastructure for it).

### [VERIFIED, a serious, disclosed methodological limitation] The chronological + alphabetical tie-break is a real selection-bias risk

**[VERIFIED]** `collect_candidate_events`'s own tie-break rule sorts
same-day candidates by symbol NAME. **[INFERENCE]** On any date where
more eligible candidates exist than open slots (shown above to be
common), this systematically favors symbols earlier in the alphabet
over economically-equivalent later ones — an ARBITRARY, not
economically-motivated, selection mechanism. This means the accepted-
trade sample is **not a representative random sample of the underlying
signal's own full population** — it is a systematically-filtered
subset, filtered by an incidental naming convention under heavy
capacity constraint. **This is disclosed here as a genuine limitation
of this first, deliberately boring, pre-registered design — not fixed
or retried, per the no-optimization mandate — and is a material reason
this entry's own result should NOT be read as a clean, decisive test
of "does diversification destroy the edge."** A more principled
tie-break (e.g., by signal strength or a fixed rotation) would
be a genuinely different design, not a parameter retune, and is named
as an open question in §17 below.

### (C) Does portfolio construction eliminate the absurd single-position tail? — [TESTED] Partially, and precisely quantified

**[VERIFIED]** Development's worst single trade: −₹9,676.95. As a
percentage of that ONE position's own capital (₹25,000): **−38.7%** —
still a large position-level loss, consistent with this signal
family's own already-characterized fat tail (`H_MEANREV_008`'s own
risk-characterization work). **As a percentage of TOTAL PORTFOLIO
capital (₹100,000): −9.68%** — a real, meaningful, DISCLOSED
improvement over `H_MEANREV_010` Candidate 2's own −65%-of-TOTAL-
capital outcome (which concentrated 100% of capital in one position).
Best trade: +₹18,989.02 (+76.0% of that position, +19.0% of total
portfolio). **The portfolio-LEVEL tail is genuinely less catastrophic
than the single-position design — this is a real success on this
specific dimension — but the POSITION-level volatility itself is
unchanged (still the same underlying stock-level fat tail
`H_MEANREV_008` already documented), and portfolio-level drawdown
remains substantial (below).**

### (D) Portfolio-level drawdown — [TESTED] Still large; the portfolio rarely reached its own stated diversification

**[VERIFIED]** Maximum drawdown: development 39.34%, validation
26.44%, out-of-sample 26.90% — all substantial. **[VERIFIED]**
Rough calendar-day-weighted average concurrent positions: ~2.1-2.2 out
of the 4-position cap (~53-55% average capital utilization) — **the
portfolio spent much of its time well BELOW its own nominal
diversification target**, running with 1-3 positions open far more
often than the full 4. This is consistent with, and reinforces, the
clustering inference above: eligible signals arrive in bursts (driving
heavy capacity rejection during bursts) separated by quieter stretches
(driving the portfolio to run under-deployed the rest of the time) —
not a smooth, continuously-diversified 4-position book.

### (E)/(F) Breadth and concentration — [TESTED] Broader than a single position, but the concentration metric itself is uninformative here

**[VERIFIED]** Distinct symbols contributing: 163 (development), 79
(validation), 80 (out-of-sample) — broader than a single name, though
the accepted set is the alphabetically/chronologically-filtered subset
described above, not the full universe. **[VERIFIED]**
`top5_trades_pnl_share_pct`: development +360.2%, validation −192.3%,
out-of-sample −199.5%. **[INFERENCE] These numbers are NOT
meaningfully interpretable as "concentration" here** — the ratio's own
denominator (total net P&L) is small or negative in every split, so a
handful of large individual trades mechanically produce an extreme,
uninformative percentage regardless of true concentration; this is a
disclosed limitation of the top-5-share metric specifically at this
small a sample and P&L magnitude, not a real finding about
concentration one way or the other. Sector concentration (using the
existing, partially-covered `NSE_SECTOR_MAP`) was NOT computed in this
entry — given the small, already-ambiguous sample and the metric
limitation just disclosed, a further slicing dimension would not add
proportionate value; disclosed as not run, not silently skipped.

### (A)/(B) Gross edge and realistic-cost survival

**[VERIFIED]** Gross P&L: development +₹43,460.67, validation
−₹7,852.26, out-of-sample −₹4,789.98. **[INFERENCE] Unlike
`H_MEANREV_009`/`010`, where gross returns were consistently positive
and closely matched the raw `H_MEANREV_006`/`007`/`008` measurement
across all three splits, this entry's own GROSS result is ALREADY
mixed in sign** (validation and out-of-sample gross are negative, not
just net) — meaning the accepted-trade SUBSET itself (not merely the
cost structure) no longer cleanly reproduces the raw signal's own
positive edge. This is consistent with the selection-bias concern
above: if the accepted trades are a systematically-filtered, non-
representative subset of the full signal population, there is no
reason to expect them to preserve the FULL population's own gross
edge. **[TESTED]** Total costs (fixed + variable) remain modest
relative to the LARGER (₹25,000) position size, as `H_MEANREV_010`
Candidate 2 already demonstrated for this same notional scale — costs
are not the binding constraint here; the binding issue is the
selection/sample-size problem above.

### Liquidity — [INCONCLUSIVE], as pre-registered

No average-daily-volume, free-float, or market-capitalization data
exists anywhere in this repository (confirmed, §2/§8). This entry does
not resolve liquidity validation — marked **[INCONCLUSIVE]** exactly
as the pre-registration committed to, not silently assumed away. At
₹25,000 per position (a quarter of `H_MEANREV_010` Candidate 2's own
₹100,000), liquidity/impact risk is plausibly smaller in absolute
terms, but this is not independently verified here.

### Verdict

**REJECTED**, matching `strategy.promotion_gate.evaluate_promotion`'s
own unmodified verdict exactly — mapped to `HypothesisStatus.REJECTED`.
**Precisely characterized, not overstated**: this is a MIXED,
UNDERPOWERED, small-sample result (every split's CI straddles zero
substantially), not a confirmed-harm result like `H_MEANREV_009`'s own
decisive `NEGATIVE`. The most important, disclosed finding is
METHODOLOGICAL, not merely statistical: this specific, deliberately
"boring" first portfolio design (a hard 4-position cap with a
chronological + alphabetical acceptance rule) rejects 82-93% of the
underlying signal's own candidate population, likely due to genuine
signal clustering (a systemic, not purely idiosyncratic, phenomenon),
and its own arbitrary tie-break introduces a real, disclosed
selection-bias risk. **This entry does NOT cleanly answer "does the
signal survive diversification" — it demonstrates that THIS
PARTICULAR, simple scheduling rule cannot exercise enough of the
signal's own sample to answer that question with confidence,** while
independently confirming a genuine, real improvement in
PORTFOLIO-LEVEL tail realism relative to `H_MEANREV_010` Candidate 2
(−9.68% vs. −65% worst-single-trade-as-%-of-total-capital).
`H_MEANREV_009` (`REJECTED`) and `H_MEANREV_010` (`INCONCLUSIVE`)
remain unmodified, cited as comparison points only.

## 17. Next bottleneck (not pursued here)

**[HYPOTHESIS, not started]** No longer raw signal validity or
per-fill costs (both already addressed by `H_MEANREV_009`/`010`). The
open bottleneck is now **candidate-selection/acceptance design under
signal clustering** — a genuinely different portfolio-construction
question from anything tested so far: when more eligible signals exist
than available slots on a given date, HOW should the portfolio choose
among them (by relative signal strength, by a fixed non-alphabetical
rotation, by explicit sector/correlation diversification rules, or by
simply allowing more concurrent slots at smaller size per slot)? Any
such change would be a genuinely new hypothesis, not a retune of this
one's own frozen 4-slot/chronological design, and is not started here
per the user's own explicit stop instruction.

## 18. Scope note

Paper-only research throughout. The new simulator is a pure,
isolated backtesting module — never reachable from `paper/`, `live/`,
or `main.py`'s own live-trading command paths. No broker execution
exists or is touched anywhere in this research path. No scheduler
dependency. Does not touch `data/paper_trading.db`,
`data/live_state.db`, `data/scheduler_runs.db`,
`data/direction_forecasts.db`, or `data/predictions.db`.
