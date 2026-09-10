# H_MEANREV_006 — Mechanism Decomposition of the Generalized NSE Oversold Effect, Pre-Registration

Written and frozen **before** any experiment code runs. Per this
project's own multiple-testing discipline: the entry condition,
universe, bucket definitions, splits, and success/failure criteria are
fixed here; none may change after seeing results.

**This is a mechanism-decomposition phase, not strategy optimization.**
No stops, targets, or executable design are touched here. No new
entry threshold is introduced. The FROZEN `zscore_close_20 < -2.0`
oversold condition (Candidate A, `H_MEANREV_001`'s own original a
priori threshold) is used exactly as-is throughout.

## 1. Research question

`H_MEANREV_005` established that the RAW, unconditioned oversold
signal generalizes strongly to a 174-symbol expanded NSE universe (in
fact more decisively out-of-sample there than `H_MEANREV_003`'s own
regime-gated version). The central question this entry asks:

**What type of oversold event produces the generalized NSE
mean-reversion effect, and when does the reversal actually occur?**
Four genuinely distinct, pre-registered sub-questions, each comparing
the SAME frozen entry condition's forward-return response across a
different decomposition axis — not four different entry signals, and
not a search for a better entry signal.

## 2. Audit — what already exists (read directly, not assumed)

Read in full: `H_MEANREV_003`, `H_MEANREV_004`, `H_MEANREV_005`,
`H_EXIT_005` (registry entries and pre-registrations), plus
`quant_research/mean_reversion_signal.py`,
`quant_research/alpha_features.py`, `quant_research/cross_sectional.py`,
`quant_research/context_experiments.py`.

- **Oversold definition (frozen, reused verbatim)**: `zscore_close_20
  < -2.0` (`_oversold_2std`, Candidate A) from
  `quant_research/mean_reversion_signal.py`. Candidate B (`< -1.5`) is
  NOT used in this entry — using a single candidate keeps this
  four-question mechanism study from multiplying into eight result
  sets; Candidate B remains available as a future robustness check,
  not run by default here.
- **Forward horizons (existing)**: `FORWARD_HORIZONS = (1, 2, 3, 5, 10,
  20)`, already computed by every `SymbolDataset`.
- **Existing lookbacks**: `quant_research.cross_sectional.
  add_lookback_return_columns` already generalizes to an arbitrary
  lookback tuple (`DEFAULT_LOOKBACKS = (5, 20, 60)`); adding
  `lookback=1` is a one-line extension of an already-generalized
  function, not new logic.
- **Existing volatility measure**: `atr_pct_of_price` (ATR14 /
  close), already computed by `add_alpha_features`, already causal,
  already used across this registry.
- **Existing relative-strength measure**: `relative_strength_20`
  (`trailing_return_20` minus the market's own trailing 20-bar
  return), already implemented in `add_alpha_features` — but **left
  all-NaN by default** in the standard `build_symbol_dataset`/
  `add_mean_reversion_columns` pipeline, because `market_series=None`
  is passed there (confirmed by direct inspection: `ds.frame
  ['relative_strength_20'].isna().all()` is `True` for the default
  pipeline). `H_RELSTRENGTH_001`'s own module
  (`quant_research/relative_strength_signal.py`) shows the correct
  pattern: pass the symbol's own benchmark OHLCV (`^NSEI` for every
  `.NS` symbol in this project) as `market_series`. This entry reuses
  that exact pattern — fetch `^NSEI` ONCE, pass it as `market_series`
  for every symbol (simpler than `H_RELSTRENGTH_001`'s own per-symbol
  benchmark lookup, since this entry's universe is 100% NSE).
- **Existing splits**: standard 60/20/20 development/validation/
  out-of-sample via `shared_period_boundaries`.
- **Existing costs**: `CostModel.india_nse_intraday_2026()`, ~0.21%
  round-trip — used here only as a raw-measurement sanity reference on
  the primary temporal-decay curve, not a strategy backtest.
- **Existing universe definitions**: `ORIGINAL_32_NSE_UNIVERSE` (32)
  and `EXPANDED_ONLY` (176, `H_XSECT_006`/`H_MEANREV_005`'s own frozen
  set). This entry uses **COMBINED** (`build_universe_groups()`'s own
  `combined` key — the union, ~206 buildable symbols after the 2
  path-excluded tickers), since generalization across both halves is
  already independently established (`H_MEANREV_005`) and this phase's
  own goal is maximum statistical power to characterize the mechanism,
  not to re-test whether it generalizes.
- **Known failure mechanism (not re-tested here)**: `H_XSECT_002`/
  `H_MEANREV_004`/`H_EXIT_005` all independently found the project's
  frozen trend-continuation-calibrated stop/target architecture is
  mismatched to a reversal-type entry (STOP-domination). This entry
  does not touch exit/execution logic at all — it studies the FORWARD
  RETURN RESPONSE only, exactly the layer mission guidance places
  BEFORE any exit/risk/execution design.

**No existing entry in this registry has measured the full six-horizon
response shape of the unconditioned oversold signal on the COMBINED
universe, decomposed by shock-vs-orderly decline, volatility bucket,
or relative-vs-absolute weakness. Confirmed genuinely novel.**

## 3. Infrastructure audit — new code required, kept minimal

- Fetch `^NSEI` once, pass as `market_series` to `add_alpha_features`
  for every symbol — populates `relative_strength_20` for real (a
  parameter change to an existing call, not new logic).
- `add_lookback_return_columns(dataset, lookbacks=(1, 5))` — reuses
  the existing generalized function, no new computation logic.
- Three new **bucket-assignment** functions (pure, small, each
  independently unit-tested): shock-vs-orderly concentration ratio,
  volatility tercile lookup, relative-strength median split. These are
  the only genuinely new code this entry requires — a scratch
  measurement script otherwise, matching every prior precedent in this
  segment.

## 4. Universe (frozen)

`COMBINED` = `ORIGINAL_32_NSE_UNIVERSE` ∪ `EXPANDED_ONLY` (176), from
`build_universe_groups()` against the already-cached Dhan public
instrument master (no credentials). ~206 of 208 nominal symbols
buildable (`M&M.NS`/`GVT&D.NS` excluded by the path-safety allowlist,
the same disclosed-in-advance exclusion `H_MEANREV_005` already
carried). 10 years daily. `^NSEI` fetched once as the benchmark for
`relative_strength_20`.

## 5. Entry condition, splits, horizons (frozen)

- Entry: `zscore_close_20 < -2.0` (Candidate A), unchanged, unconditioned (no regime gate — this is deliberately the RAW signal `H_MEANREV_005` validated generalizes).
- Splits: `shared_period_boundaries`-derived 60/20/20 on `COMBINED`'s own shared calendar, computed fresh (not assumed identical to any prior universe's dates).
- Horizons: `FORWARD_HORIZONS` (1,2,3,5,10,20), all six reported for every sub-question. **Primary horizon for the bucket-comparison sub-questions (Q2/Q3/Q4): h10** — a mid-range holding horizon, chosen a priori for consistency across sub-questions, not selected after seeing any result. Q1 (temporal decay) has no single primary horizon by design — its own object of study IS the shape across all six.

## 6. Q1 (PRIMARY) — Temporal decay / response shape

**Question**: is the reversal immediate, delayed, persistent, or
short-lived? Measure the SAME frozen entry condition's forward-return
response at all six horizons, three splits, on `COMBINED`. No new
entry condition, no bucketing — a direct redescription of the
already-frozen signal's own response curve, using
`measure_condition`/`summarize_forward_returns` unchanged.

**Success/failure is descriptive, not pass/fail**: report the full
mean/median/win-rate/CI/p5/p95 curve at every horizon, every split.
The finding is the SHAPE itself (e.g., "the effect is already fully
present by h3 and plateaus" vs. "the effect builds gradually through
h20") — disclosed as observed, not judged against a frozen numeric
target. A secondary, disclosed cost-margin check compares the primary
observed effect size at each horizon against `CostModel.
india_nse_intraday_2026()`'s ~0.21% round-trip reference (raw
measurement only, not a strategy claim).

## 7. Q2 (PRIMARY) — Shock vs. orderly decline

**Question**: does an abrupt single-day decline (temporary
overshoot/liquidity-pressure thesis) behave differently from a
gradual multi-day decline (genuine-deterioration thesis) reaching the
SAME oversold state?

**Frozen operationalization**: at each oversold-triggering bar,
`concentration = abs(trailing_return_1) / abs(trailing_return_5)`
(both already-causal lookback returns). A value near 1 means nearly
the entire 5-day move happened on the trigger day itself (SHOCK); a
low value means the decline was spread across the window (ORDERLY).
**Threshold**: the MEDIAN of `concentration` among development-period
oversold-triggering observations only (not the whole universe) —
`SHOCK` = at or above the median, `ORDERLY` = below. A simple,
symmetric, non-arbitrary median split, frozen from development-period
data only, never re-derived.

## 8. Q3 (PRIMARY) — Volatility normalization

**Question**: is the effect primarily a raw price-return phenomenon,
or does it depend on how unusual the move was relative to the stock's
own recent volatility?

**Frozen operationalization**: bucket oversold-triggering observations
into volatility TERCILES by `atr_pct_of_price` AT THE TRIGGER BAR.
**Thresholds**: the 33rd/67th percentile of `atr_pct_of_price` among
ALL `COMBINED`-universe development-period observations (not just
triggering ones — the volatility-regime definition is independent of
which days happen to trigger oversold, avoiding a circular definition)
— `LOW_VOL`/`MID_VOL`/`HIGH_VOL`. Compares each bucket's own forward-
return response; `zscore_close_20` is already volatility-normalized by
construction (a standardized deviation), so a SIMILAR response across
volatility terciles would indicate the zscore normalization is already
doing its job; a MATERIALLY DIFFERENT response would indicate
volatility context still matters beyond what the zscore alone
captures.

## 9. Q4 (PRIMARY) — Relative vs. absolute weakness

**Question**: does the effect depend on the stock being weak in
absolute terms, or does it require/intensify with weakness RELATIVE to
the broader market (i.e., does it survive after controlling for
common, broad-market-wide moves)?

**Frozen operationalization**: `relative_strength_20` (`trailing_
return_20` minus `^NSEI`'s own trailing 20-bar return over the same
window — real market_series, not the default NaN), computed AT THE
TRIGGER BAR. **Threshold**: the MEDIAN of `relative_strength_20` among
development-period oversold-triggering observations only —
`RELATIVE_WEAKNESS` (below median — the stock underperformed the
market specifically) vs. `MARKET_DRIVEN` (at or above median — the
stock's own oversold reading is closer to a broad-market-wide move,
not stock-specific underperformance).

## 10. Minimum sample size, statistical reporting (frozen)

**>=30 observations per split per bucket** for every sub-question — a
bucket below this floor is reported as INSUFFICIENT_DATA for that
specific cell, never folded into a weaker claim. Every reported cell
carries: n, mean, median, win rate, 95% CI, p5, p95 (via
`summarize_forward_returns`, unchanged).

## 11. Multiple-testing discipline (frozen, per mission instruction)

Four PRIMARY pre-registered sub-questions (Q1-Q4 above), each with its
own frozen bucket definition/threshold, computed ONCE from
development-period data, never re-derived after seeing validation/OOS.
No threshold search across sub-questions. Any unexpected pattern that
suggests a genuinely different mechanism (e.g., an interaction between
two bucket dimensions) is recorded as a candidate FUTURE hypothesis in
the results write-up, never folded back into this entry's own frozen
tests retroactively. Secondary descriptive observations (e.g.,
symbol/year breakdowns noticed while producing the primary tables) are
explicitly labeled SECONDARY DESCRIPTIVE, not treated as additional
pass/fail tests.

## 12. What will NOT change after this is pre-registered

No retuning the -2.0σ entry threshold. No new entry conditions. No
stop/target/exit design of any kind. No universe change after seeing
results. No re-deriving the SHOCK/ORDERLY, volatility-tercile, or
RELATIVE/MARKET_DRIVEN thresholds after seeing validation/OOS. No
selecting a "best" horizon for Q1 after observing the curve — the full
curve is reported regardless of shape.

## 13. Adversarial checks (mandatory ONLY if a specific sub-question's result is strong enough to warrant it — assessed per sub-question, not globally)

Year stability, symbol/sector concentration, cost sensitivity — run
selectively, only for a sub-question whose primary result is both
decisive and substantively interesting enough to justify the
additional testing surface, disclosed explicitly which sub-questions
received this treatment and why.

## 15. Reproducibility record

- `COMBINED` universe: 208 nominal symbols, 206 built (`M&M.NS`/`GVT&D.NS` excluded, disclosed in advance).
- Shared calendar: `development_end=2023-11-25`, `validation_end=2025-04-17` — identical to `H_MEANREV_005`'s own `EXPANDED_ONLY` calendar (expected, since `COMBINED` ⊇ `EXPANDED_ONLY` and NSE symbols largely share a calendar).
- `relative_strength_20` sanity check passed: non-NaN after passing `^NSEI` as a real `market_series` (was all-NaN under the default pipeline).
- Frozen thresholds (development-period only): `CONCENTRATION_MEDIAN` (Q2) = 0.3701 (n=14,578 triggering observations); `ATR_PCT_33`/`ATR_PCT_67` (Q3, universe-wide) = 2.6583% / 3.6352% (n=317,090); `RELSTRENGTH_MEDIAN` (Q4) = −6.8845% (n=14,571 triggering observations).

## 16. Results

Full evidence: `H_MEANREV_006` in `strategy/hypothesis_registry.py`.

### Q1 — Temporal decay (descriptive, all six horizons, no bucketing)

| Split | h1 | h2 | h3 | h5 | h10 | h20 |
|---|---|---|---|---|---|---|
| development | −0.00% | −0.05% | −0.06% | **−0.19%** (decisive neg.) | −0.14% | **+1.00%** (decisive) |
| validation | **+0.25%** | **+0.40%** | **+0.65%** | **+1.17%** | **+1.92%** | **+2.95%** |
| out-of-sample | **+0.24%** | **+0.38%** | **+0.44%** | **+0.61%** | **+0.59%** | **+1.13%** |

(**bold** = CI-decisive)

**Validation and out-of-sample both show a clean, monotonically
increasing, never-reversing positive response from h1 through h20** —
the reversal is present almost immediately (h1 already CI-decisive
positive in both splits) and continues accumulating all the way to
h20, with no sign of an early peak-then-fade shape. This argues against
a "quick 1-2 day overshoot correction, then flat" story and for a
persistent drift that keeps building through at least a 20-bar window
— informative for any future exit-horizon design (a short holding
period would capture only a fraction of the measured cumulative
effect).

**Development is a genuine anomaly, disclosed honestly, not
smoothed over**: mean returns are flat-to-CI-decisive-NEGATIVE at
h1-h10, only turning CI-decisive positive at h20. This is a real
divergence from validation/out-of-sample's own consistent shape, not a
sampling artifact (n=12,854, large). The development window
(2016–2023-11-25) contains the COVID crash/recovery (Feb–Apr 2020), a
plausible but NOT YET VERIFIED explanation — flagged as an open
question for a future, narrowly-scoped year-stability check (§17
below), not resolved here.

### Q2 — Shock vs. orderly decline (primary horizon h10)

| Bucket | Split | n | Mean (h10) | 95% CI |
|---|---|---|---|---|
| SHOCK | development | 6439 | −0.23% | [−0.489%,+0.024%] (not decisive) |
| SHOCK | validation | 1690 | **+2.10%** | [+1.754%,+2.445%] |
| SHOCK | out-of-sample | 2200 | **+0.83%** | [+0.549%,+1.117%] |
| ORDERLY | development | 6415 | −0.05% | [−0.293%,+0.190%] (not decisive) |
| ORDERLY | validation | 1672 | **+1.74%** | [+1.395%,+2.078%] |
| ORDERLY | out-of-sample | 2190 | **+0.34%** | [+0.064%,+0.622%] |

**A modest, consistent — but not dramatic — SHOCK > ORDERLY pattern**:
SHOCK's point estimate exceeds ORDERLY's in both validation
(+2.10% vs. +1.74%) and out-of-sample (+0.83% vs. +0.34%, more than
double), and again at h20 (SHOCK dev +1.01%/val +3.07%/oos +1.36% vs.
ORDERLY dev +0.98%/val +2.82%/oos +0.90%) — directionally consistent
across both reported horizons and both out-of-sample-relevant splits.
Development does not distinguish the two buckets (neither decisive).
This lends modest, disclosed support to the overshoot/liquidity-
pressure thesis over the pure-information-deterioration thesis, but
the gap is not large and is not confirmed in development — reported as
a real but modest directional finding, not a decisive mechanistic
split.

### Q3 — Volatility terciles (primary horizon h10)

| Bucket | Split | n | Mean (h10) | 95% CI |
|---|---|---|---|---|
| LOW_VOL | development | 2894 | +0.14% | [−0.078%,+0.353%] (not decisive) |
| LOW_VOL | validation | 1483 | **+1.11%** | [+0.856%,+1.356%] |
| LOW_VOL | out-of-sample | 2005 | +0.04% | [−0.170%,+0.250%] (not decisive) |
| MID_VOL | development | 4283 | +0.15% | [−0.089%,+0.379%] (not decisive) |
| MID_VOL | validation | 1087 | **+2.00%** | [+1.605%,+2.401%] |
| MID_VOL | out-of-sample | 1472 | **+0.40%** | [+0.045%,+0.745%] |
| HIGH_VOL | development | 5677 | **−0.50%** | [−0.842%,−0.162%] (decisive NEGATIVE) |
| HIGH_VOL | validation | 792 | **+3.33%** | [+2.598%,+4.054%] |
| HIGH_VOL | out-of-sample | 913 | **+2.11%** | [+1.493%,+2.717%] |

**A clean, monotonic dose-response by volatility tercile in
validation AND out-of-sample**: LOW < MID < HIGH in both splits (val:
+1.11% < +2.00% < +3.33%; oos: +0.04% < +0.40% < +2.11%) — the
reversal is materially STRONGER in high-volatility stocks. This means
`zscore_close_20`'s own volatility normalization does NOT fully
neutralize volatility's influence on the response — raw ATR% context
adds real information beyond the zscore threshold alone, directly
relevant to any future risk-sizing or exit design (a HIGH_VOL oversold
event is evidently a materially different animal than a LOW_VOL one).

**Development shows the SAME kind of anomaly as Q1**: HIGH_VOL is
CI-decisive NEGATIVE in development (−0.50%), the opposite direction
from validation/out-of-sample's own strongly positive result — the
identical pattern (development diverges, val/oos agree) seen in Q1,
strengthening the hypothesis that a specific development-period era
(plausibly COVID) is responsible, not yet verified (§17).

### Q4 — Relative vs. market-driven weakness (primary horizon h10)

| Bucket | Split | n | Mean (h10) | 95% CI |
|---|---|---|---|---|
| RELATIVE_WEAKNESS | development | 6744 | **+0.50%** | [+0.251%,+0.759%] |
| RELATIVE_WEAKNESS | validation | 1491 | **+1.58%** | [+1.157%,+1.994%] |
| RELATIVE_WEAKNESS | out-of-sample | 1629 | **+1.35%** | [+0.997%,+1.693%] |
| MARKET_DRIVEN | development | 6103 | **−0.86%** | [−1.100%,−0.617%] (decisive NEGATIVE) |
| MARKET_DRIVEN | validation | 1871 | **+2.19%** | [+1.912%,+2.473%] |
| MARKET_DRIVEN | out-of-sample | 2761 | +0.14% | [−0.097%,+0.382%] (not decisive) |

**The cleanest finding of the four sub-questions.**
`RELATIVE_WEAKNESS` (the stock underperformed `^NSEI` specifically
during its own decline, not just falling with a broad-market move) is
**CI-decisive positive in ALL THREE splits, no sign reversal** — the
same bar this registry has used elsewhere to call a raw finding
"real." `MARKET_DRIVEN` (the oversold reading is closer to a
broad-market-wide move) is, by contrast, genuinely unstable: CI-
decisive NEGATIVE in development, CI-decisive POSITIVE (even larger
than `RELATIVE_WEAKNESS`) in validation, and not decisive at all in
out-of-sample. This suggests the generalized reversal effect is
meaningfully tied to genuine, stock-specific relative underperformance
— not simply "the whole market fell and reverted together" — though
`MARKET_DRIVEN`'s own validation-split reversal means this is not a
clean, unqualified story either; disclosed precisely, not rounded up.

### Verdict

**INCONCLUSIVE overall** — this is a mechanism-decomposition/
descriptive study by design (§6-9), not a single pass/fail test, and
no registry status besides `INCONCLUSIVE` honestly captures "real,
mixed, partially-anomalous findings across four sub-questions, none
rising to a full dev/val/oos-consistent promotion-relevant claim."
Q4 (relative weakness) is the strongest, cleanest individual finding
(CI-decisive, all three splits, no reversal). Q3 (volatility) shows a
striking dose-response in validation/out-of-sample but an unexplained
development-period reversal. Q2 (shock vs. orderly) shows a real but
modest directional lean toward shock. Q1 establishes the temporal
shape is a gradual, persistent build (not an immediate snap-back) in
validation/out-of-sample, with an unexplained development-period
anomaly shared with Q3. No executable-strategy design follows from
this entry — per §6/§11 of the mission's own guidance, this is
strictly the forward-return-response layer, prior to any exit/risk/
execution design.

## 17. Open question, explicitly flagged for a future, narrowly-scoped follow-up (NOT run here)

Both Q1 and Q3 show the SAME shape: development-period results that
are flat-to-negative and materially weaker/opposite-signed from
validation/out-of-sample's own consistent, positive, often-decisive
results. A plausible but unverified explanation is that the COVID
crash/recovery (Feb–Apr 2020), which sits inside the development
window (2016–2023-11-25) but not inside validation/out-of-sample, is
disproportionately responsible — this is a genuine, well-motivated,
narrowly-scoped candidate for a future year-by-year stability check
(a SECONDARY DESCRIPTIVE follow-up, not a new pass/fail hypothesis),
not run in this entry per its own effort-scoping, and explicitly NOT
assumed to be the explanation without verification.

## 18. Scope note

Pure historical-data research, read-only. Does not touch
`data/paper_trading.db`, `data/live_state.db`, `data/scheduler_runs.db`,
`data/direction_forecasts.db`, or `data/predictions.db`. No broker
execution changes, no exit/stop/target design, no scheduler dependency.
The one Dhan-sourced input (`combined` universe membership) reuses the
already-cached, public, unauthenticated instrument master — no
credentials involved.
