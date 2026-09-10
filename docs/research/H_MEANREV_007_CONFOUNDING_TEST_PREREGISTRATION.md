# H_MEANREV_007 — Confounding Test: Relative Weakness vs. Volatility, Pre-Registration

Written and frozen **before** any experiment code runs. Per this
project's own multiple-testing discipline: the entry condition,
universe, bucket definitions (reused verbatim from `H_MEANREV_006`,
not re-derived), splits, and comparison framework are fixed here; none
may change after seeing results.

**This is a confounding/mechanism test, not an optimization exercise.**
No new threshold is introduced anywhere in this entry. No exits,
stops, targets, or execution design are touched.

## 1. Research question

`H_MEANREV_006` found two real, independently disclosed conditioning
dimensions on the SAME frozen oversold entry: (Q3) volatility —
high-ATR% stocks show a materially stronger reversal; (Q4) relative
weakness — a stock underperforming NIFTY specifically during its own
decline shows a cleaner, more stable reversal than a stock whose
decline is closer to a broad market-wide move. These were measured
**independently** (marginal, one dimension at a time). The question
this entry asks:

**Does the strongest part of the oversold effect remain after
simultaneously accounting for BOTH relative weakness AND volatility?**
Specifically: distinguish (A) a genuine stock-specific oversold/
reversal mechanism, from (B) an effect largely explained by
volatility, from (C) an effect largely explained by market-relative
weakness, from (D) an interaction where relative weakness + elevated
volatility together identify a genuinely different, more informative
population than either alone.

## 2. Audit — infrastructure and prior results (verified, not assumed)

Read directly: `H_MEANREV_005`, `H_MEANREV_006`'s own registry entry
and pre-registration (including its year-stability addendum),
`H_RELSTRENGTH_001`, `quant_research/alpha_features.py`,
`quant_research/mean_reversion_signal.py`.

- **Entry (frozen, unchanged)**: `zscore_close_20 < -2.0`
  (`_oversold_2std`), `H_MEANREV_001`'s own original a priori
  threshold, reused verbatim throughout this whole family.
- **`zscore_close_20`**: causal rolling 20-bar z-score
  (`(close - rolling_mean_20) / rolling_std_20`, `min_periods=20`) —
  verified by direct reading of `add_alpha_features`; no look-ahead
  (row i uses only rows <= i).
- **`atr_pct_of_price`**: `atr_14 / close`, already causal (ATR14
  itself computed upstream, causal). Verified correct by direct
  reading.
- **`relative_strength_20`**: `trailing_return_20` (stock) minus
  `^NSEI`'s own trailing 20-bar return over the SAME window,
  `market_series["close"]` reindexed onto the stock's own calendar
  with a forward-fill that only ever uses a PAST index value (never
  future) — verified causal by direct reading of `add_alpha_features`.
  **Confirmed correctly populated** in `H_MEANREV_006`'s own
  reproducibility record: all-NaN under the DEFAULT pipeline
  (`market_series=None`), populated for real only when `^NSEI`'s own
  frame is passed as `market_series` — the exact same call this entry
  reuses unchanged.
- **Frozen partitions, reused VERBATIM from `H_MEANREV_006`, not
  re-derived**:
  - `RELSTRENGTH_MEDIAN = -6.8845%` (median of development-period
    OVERSOLD-TRIGGERING `relative_strength_20` observations, n=14,571).
  - `ATR_PCT_33 = 2.6583%`, `ATR_PCT_67 = 3.6352%` (33rd/67th
    percentile of development-period UNIVERSE-WIDE `atr_pct_of_price`,
    n=317,090 — deliberately universe-wide, not triggering-only, to
    avoid circularity with the entry condition itself, exactly as
    `H_MEANREV_006` originally froze them).
- **No new indicator, no new lookback, no new universe** — this entry
  reuses `H_MEANREV_006`'s own `COMBINED` universe (206/208 symbols)
  and identical feature-building steps (`add_alpha_features` with a
  real `market_series=^NSEI`, `add_regime_columns`,
  `add_lookback_return_columns`) verbatim.

**Confirmed genuinely novel**: no prior entry has measured the JOINT
condition (oversold AND relative-weak AND high-volatility)
simultaneously, nor formally tested whether the combined condition
adds information beyond either single-dimension bucket alone.

## 3. Universe, splits, horizons (frozen, identical to `H_MEANREV_006`)

`COMBINED` (206/208 symbols), 10 years daily. `shared_period_boundaries`
60/20/20 split (`development_end=2023-11-25`,
`validation_end=2025-04-17`, identical to `H_MEANREV_006`'s own
calendar, since the universe is unchanged). `FORWARD_HORIZONS`
(1,2,3,5,10,20), all six reported descriptively for every bucket
(temporal-response requirement); **primary horizon for the core
comparison: h10**, matching `H_MEANREV_006`'s own established
convention, chosen for direct comparability, not selected after seeing
results.

## 4. Required comparisons (frozen)

Four conditions, all built from the SAME frozen entry and the SAME
frozen `H_MEANREV_006` partitions:

- **A. OVERSOLD_ALONE** — `zscore_close_20 < -2.0`, unconditioned.
  (Identical by construction to `H_MEANREV_006`'s own Q1 measurement —
  recomputed here for a clean, self-contained side-by-side table, not
  a new result.)
- **B. OVERSOLD_AND_RELATIVE_WEAKNESS** — A AND `relative_strength_20
  < RELSTRENGTH_MEDIAN`. (Identical by construction to `H_MEANREV_006`'s
  own Q4 `RELATIVE_WEAKNESS` bucket.)
- **C. OVERSOLD_AND_HIGH_VOL** — A AND `atr_pct_of_price > ATR_PCT_67`.
  (Identical by construction to `H_MEANREV_006`'s own Q3 `HIGH_VOL`
  bucket.)
- **D. OVERSOLD_AND_RELATIVE_WEAKNESS_AND_HIGH_VOL** — A AND B's own
  relative-weakness condition AND C's own high-volatility condition,
  simultaneously. **The genuinely new measurement this entry
  contributes.**

**The incremental-information test (frozen, the entry's own central
question, at h10, out-of-sample)**: D's point-estimate mean forward
return must exceed BOTH B's and C's own out-of-sample point estimates
for D to be read as containing information beyond either single
dimension alone — the identical operationalization `H_MOMENTUM_001`
already used for its own two-dimension interaction test, applied here.
If D is no better than the stronger of B/C, the interaction adds
nothing; if D is worse than both, the "genuinely different population"
reading (D) is not supported and B or C alone is the more informative
lens.

**Secondary, descriptive-only (frozen thresholds, no new degrees of
freedom)**: E. the full `RELATIVE_WEAKNESS` × {`LOW_VOL`, `MID_VOL`,
`HIGH_VOL`} breakdown (6 cells: relative-weak/market-driven crossed
with all three, already-frozen, volatility terciles) — reported as
additional disclosure, not part of the core A/B/C/D comparison, using
only thresholds `H_MEANREV_006` already froze.

## 5. Confounding checks (frozen, mandatory)

- **Population overlap**: report the joint contingency of bucket
  membership among ALL oversold-triggering observations (development
  period) — how many fall into each of the 4
  `RELATIVE_WEAKNESS`/`MARKET_DRIVEN` × `LOW`/`MID`/`HIGH_VOL`
  combinations — to determine whether high-volatility stocks are
  disproportionately represented among relative-weakness observations
  (or vice versa), rather than assuming independence.
- **2020 robustness (frozen, pre-specified, NOT a way to discard an
  inconvenient observation)**: report the COMPLETE development-period
  result for A/B/C/D first, THEN a WITH-2020 vs. WITHOUT-2020
  comparison for the SAME four buckets, restricted to the development
  period (validation/out-of-sample never contained 2020 to begin with,
  per `H_MEANREV_006`'s own calendar). If excluding 2020 materially
  changes any conclusion, this is documented prominently, not
  smoothed over.

## 6. Minimum sample size, statistical reporting (frozen)

**>=30 observations per split per bucket**, matching every prior entry
in this family — a cell below this floor is reported as
INSUFFICIENT_DATA, never folded into a weaker claim. Every reported
cell carries n, mean, median, win rate, 95% CI, p5, p95 (via
`summarize_forward_returns`, unchanged).

## 7. What will NOT change after this is pre-registered

No new entry threshold. No re-deriving `RELSTRENGTH_MEDIAN` or
`ATR_PCT_33`/`67` — both reused verbatim from `H_MEANREV_006`. No new
volatility or relative-strength lookback windows. No new universe. No
horizon selected after seeing results (h10 primary, fixed above, all
six reported regardless). No exit/stop/target/execution design of any
kind. If an unexpected pattern (e.g., a genuinely different
interaction shape) emerges, it is recorded as a candidate FUTURE
hypothesis, never folded back into this entry's own frozen comparison
retroactively.

## 8. Adversarial checks (mandatory ONLY if the primary D-vs-B/C comparison is decisive enough to warrant it)

Symbol breadth, sector concentration (where `NSE_SECTOR_MAP` coverage
permits, a disclosed partial-coverage caveat carried by every prior
entry that touches it), liquidity — assessed selectively, not as an
unlimited slicing exercise, and only for whichever bucket(s) the
primary comparison identifies as most informative.

## 9. Scope note

Pure historical-data research, read-only, reusing the already-built
`COMBINED` universe datasets and features. Does not touch
`data/paper_trading.db`, `data/live_state.db`, `data/scheduler_runs.db`,
`data/direction_forecasts.db`, or `data/predictions.db`. No broker
execution changes, no exit/stop/target design, no scheduler
dependency.
