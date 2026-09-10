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

## 10. Reproducibility record

- Universe/calendar identical to `H_MEANREV_006`: `COMBINED`, 206/208 symbols, `development_end=2023-11-25`, `validation_end=2025-04-17`.
- Frozen thresholds reused verbatim: `RELSTRENGTH_MEDIAN=-6.8845%`, `ATR_PCT_33/67=2.6583%/3.6352%`.
- Bucket-overlap contingency (development-period triggering observations, n=14,578): `RELWEAK_LOW`=1270 (8.7%), `RELWEAK_MID`=2346 (16.1%), `RELWEAK_HIGH`=3670 (25.2%), `MARKET_LOW`=2621 (18.0%), `MARKET_MID`=2488 (17.1%), `MARKET_HIGH`=2176 (14.9%). HIGH_VOL rate among `RELATIVE_WEAKNESS` observations = 50.4%, vs. 40.1% overall — a real but moderate (~10pp) overrepresentation, confirming genuine but not extreme confounding overlap between the two dimensions.

## 11. Results

Full evidence: `H_MEANREV_007` in `strategy/hypothesis_registry.py`.

### Primary comparison (h10)

| Bucket | Split | n | Mean | 95% CI |
|---|---|---|---|---|
| A (oversold alone) | development | 12854 | −0.14% | not decisive |
| A | validation | 3362 | **+1.92%** | [+1.676%,+2.162%] |
| A | out-of-sample | 4390 | **+0.59%** | [+0.389%,+0.788%] |
| B (+relative weakness) | development | 6745 | **+0.51%** | [+0.254%,+0.761%] |
| B | validation | 1491 | **+1.58%** | [+1.157%,+1.994%] |
| B | out-of-sample | 1629 | **+1.35%** | [+0.997%,+1.693%] |
| C (+high volatility) | development | 5677 | **−0.50%** | [−0.842%,−0.162%] (decisive NEGATIVE) |
| C | validation | 792 | **+3.33%** | [+2.598%,+4.054%] |
| C | out-of-sample | 914 | **+2.10%** | [+1.492%,+2.716%] |
| D (joint) | development | 3575 | +0.40% | not decisive |
| D | validation | 542 | **+3.07%** | [+2.115%,+4.034%] |
| D | out-of-sample | 590 | **+2.08%** | [+1.331%,+2.833%] |

**The frozen incremental-information test (h10, out-of-sample): D beats
BOTH B and C? FALSE.** D (+2.08%) essentially TIES C (+2.10%, well
within overlapping CIs) and both clearly exceed B (+1.35%) and A
(+0.59%). Per this entry's own frozen reading (§4): D is not worse
than both B and C (it clearly beats B), but it does NOT beat C — **the
joint condition adds no incremental information beyond volatility
alone.** This pattern (C ≈ D >> B > A) holds consistently in BOTH
validation and out-of-sample.

**A real, disclosed ASYMMETRY, not a symmetric null result**: comparing
D against EACH component separately tells two different stories.
D vs. C (does adding relative weakness on top of high volatility help)
→ NO, negligible difference. D vs. B (does adding high volatility on
top of relative weakness help) → YES, substantially (D +2.08% vs. B
+1.35% at OOS, D +3.07% vs. B +1.58% at validation) — **volatility adds
real information on top of relative weakness, but relative weakness
adds essentially nothing on top of volatility.** Volatility is the
more dominant, magnitude-driving dimension between the two.

**But dominance in magnitude is not the same as robustness.** B
(relative weakness alone) is the ONLY one of A/B/C/D that is CI-decisive
POSITIVE in ALL THREE splits, including development (+0.51%) — no sign
reversal anywhere. C and D are BOTH vulnerable to the SAME
development-period anomaly `H_MEANREV_006` already flagged: C is
CI-decisive NEGATIVE in development (−0.50%), and D is not decisive
there either (+0.40%, CI touches zero) — both inherit the instability
that comes with conditioning on high volatility.

### WITH-2020 vs. WITHOUT-2020 robustness (development period, h10)

| Bucket | WITH 2020 | WITHOUT 2020 |
|---|---|---|
| A | +0.06% (not decisive) | **+0.98%** (decisive) |
| B | **+0.52%** (decisive) | **+1.04%** (decisive) |
| C | **−0.45%** (decisive NEGATIVE) | **+1.48%** (decisive POSITIVE) |
| D | +0.36% (not decisive) | **+1.43%** (decisive) |

**2020 is confirmed to be the entire source of C's and D's own
development-period sign reversal — a complete flip, not a partial
dampening.** Without 2020, C's own development result matches
validation/OOS's own strongly positive shape almost perfectly (+1.48%
vs. +3.33%/+2.10%). B, by contrast, is CI-decisive positive WITH 2020
included, and only strengthens moderately when 2020 is excluded
(+0.52% → +1.04%) — **2020 dampens B but never reverses it.** This
confirms the mechanistic picture: 2020's systemic, broad-market crash
disproportionately contaminates the volatility-conditioned buckets (C,
D) — mechanically unsurprising, since a market-wide panic concentrates
extreme-volatility observations — while the relative-weakness
dimension, which does not condition on volatility at all, is far less
exposed to that single year's own anomalous behavior.

### Secondary descriptive: relative-weakness × volatility tercile (E)

The full 6-cell breakdown (h10, all three splits) shows the same
qualitative pattern within EVERY volatility tercile: `HIGH_VOL` cells
(both `RELWEAK_HIGHVOL` and `MARKETDRIVEN_HIGHVOL`) show the largest
magnitude effects in validation/out-of-sample (e.g. validation h10:
`RELWEAK_HIGHVOL` +3.07%, `MARKETDRIVEN_HIGHVOL` +3.87%) but the
worst development-period instability (`MARKETDRIVEN_HIGHVOL`
development h10 = **−2.03%**, CI-decisive negative, the single most
extreme cell in the whole table) — reinforcing that volatility, not
relative weakness, is the dimension most entangled with the 2020
anomaly.

### Verdict

**REJECTED** for this entry's own primary frozen claim — the joint
condition (D) does NOT contain information beyond the stronger of its
two components (C, high volatility) alone; the "genuinely different,
more informative population" reading is not supported by the data.

**Important, precisely disclosed secondary findings, not diminished by
the REJECTED verdict**: (1) volatility is the more dominant driver of
raw reversal MAGNITUDE between the two dimensions tested; (2) relative
weakness is the more ROBUST dimension, uniquely surviving all three
splits including the 2020-contaminated development period without a
sign reversal; (3) the 2020 anomaly is now fully explained as a
volatility-conditioning artifact, not a property of relative weakness
or of the raw oversold signal's own robustness in general. Together
these suggest the generalized oversold effect is a MIXTURE of (at
least) two only-partially-overlapping populations — a
large-magnitude-but-fragile volatility/overshoot component, and a
smaller-magnitude-but-robust genuine relative-weakness component — not
a single unified mechanism.

Per §8's own frozen gate, the full adversarial-checks battery (symbol
breadth, sector concentration, liquidity) was NOT run, since the
primary D-vs-B/C comparison did not produce a decisive, novel
interaction result warranting it.

## 12. Scope note

Pure historical-data research, read-only, reusing the already-built
`COMBINED` universe datasets and features. Does not touch
`data/paper_trading.db`, `data/live_state.db`, `data/scheduler_runs.db`,
`data/direction_forecasts.db`, or `data/predictions.db`. No broker
execution changes, no exit/stop/target design, no scheduler
dependency.
