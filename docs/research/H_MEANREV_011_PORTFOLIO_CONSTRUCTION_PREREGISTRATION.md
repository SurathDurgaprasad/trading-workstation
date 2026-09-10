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

## 14. Scope note

Paper-only research throughout. The new simulator is a pure,
isolated backtesting module — never reachable from `paper/`, `live/`,
or `main.py`'s own live-trading command paths. No broker execution
exists or is touched anywhere in this research path. No scheduler
dependency. Does not touch `data/paper_trading.db`,
`data/live_state.db`, `data/scheduler_runs.db`,
`data/direction_forecasts.db`, or `data/predictions.db`.
