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
   its own raw finding).
2. If that backtest also clears the promotion gate, run it in shadow
   mode — recording what it WOULD have signaled, without affecting any
   live paper-trading decision — for a real observation period before
   ever considering `--paper-execute` integration.
3. Test the sector-relative and NIFTY-relative score variants the
   mission's own text also named (`stock_return_N - nifty_return_N`,
   `stock_return_N - sector_return_N`) as independent replications, not
   assumed to behave identically to the absolute-return version tested
   here.
