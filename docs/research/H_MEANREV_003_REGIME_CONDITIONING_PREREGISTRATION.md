# H_MEANREV_003 — Regime-Conditioned Mean Reversion, Pre-Registration

Written and frozen **before** any experiment code runs. Per this
project's own multiple-testing discipline: the signal definition,
regime dimensions, universe, splits, and success/failure criteria are
fixed here; none may change after seeing results. Any deviation found
necessary during implementation must be classified (BUG FIX /
MECHANICAL CORRECTION / NEW HYPOTHESIS) and disclosed here before
results are examined.

## 1. Research question

Does `H_MEANREV_001`'s oversold mean-reversion entry (`zscore_close_20`
below a frozen threshold) behave differently depending on the broader
NIFTY market's own trend regime and volatility regime — tested
NSE-only for the first time (the original `H_MEANREV_001` pooled NSE
and US together and found a directionless null result)?

Framed as: **"When does mean reversion work, and when does it fail?"**
— not "does another indicator predict returns," per the mission's own
explicit reframing of this research family.

## 2. Audit — what already exists (verified against the actual repository, not assumed)

Full comparison matrix, built from `strategy/hypothesis_registry.py`'s
own actual entries:

| Existing Signal | Market Trend Regime | Volatility Regime | Sector Regime | Interaction Tested? |
|---|---|---|---|---|
| Baseline BUY (`TrendMomentumBaseline`) | `H_CONTEXT_MARKET_001` (UP, REJECTED) / `H_CONTEXT_MARKET_002`+`005` (DOWN, INCONCLUSIVE, **era-unstable**: sign flips 2016-2022 vs. 2022-2026) | `H_CONTEXT_MARKET_003` (REJECTED — clean development→validation sign reversal) | `H_CONTEXT_SECTOR_001`/`002` | Market×Sector: `H_CONTEXT_ALIGN_001` (INCONCLUSIVE, OOS n=10, later found era-unstable). Market×Volatility: **never tested** |
| Overnight gap fade (`H_GAP_001-003`) | Tested (`H_GAP_003`) | Tested via VIX (`H_GAP_003`) | Tested (`H_GAP_003`) | Already REJECTED overall, regardless of regime |
| India VIX regime (on baseline BUY) | — | `H_CONTEXT_VIX_001`/`002` (both REJECTED — sign reversal) | — | — |
| `H_MEANREV_001` (zscore oversold) | **never tested** | **never tested** | **never tested** | Never regime-conditioned at all; only ever tested pooled NSE+US (41 symbols), REJECTED as directionless (point estimates near zero, wide CIs, no clear sign) |
| `H_XSECT_001`/`005` (cross-sectional laggard) | **never tested** | **never tested** (`H_VOL_001` tested volatility regime on the *baseline* signal, not this one) | **never tested** | Already severely underpowered (n=24/split at 10y); further slicing would fragment an already-thin sample |

**Selection reasoning**: interacting market-trend×volatility on the
baseline BUY signal is *technically* untested as a 2-D combination, but
both marginal dimensions on that specific signal already show real
instability there (clean sign reversals, era-dependence) — this family
has 14 prior hypotheses, and `H_CONTEXT_ALIGN_001` already demonstrated
how fast cells fragment (n=10 OOS from combining just two conditions).
Regime-slicing `H_XSECT_001`/`005` would compound an already
underpowered base. `H_MEANREV_001`×regime is genuinely novel
(Signal×Regime pairing never tried), economically well-motivated
(mean-reversion is classically regime-dependent in traditional
TA/quant literature — expected to work in range-bound markets, fail in
persistent trends), ties to this session's own recurring finding that
mean-reversion is the more promising NSE family, was never isolated to
NSE-only before, and reuses 100% existing infrastructure.

## 3. Signal (frozen, unchanged from `H_MEANREV_001`)

`zscore_close_20 < -2.0` (Candidate A) and `zscore_close_20 < -1.5`
(Candidate B) — `H_MEANREV_001`'s own exact, already-frozen a priori
thresholds (`quant_research/mean_reversion_signal.py`'s
`_oversold_2std`/`_oversold_1_5std`), reused verbatim, not retuned.
Candidate C (`_oversold_within_uptrend`, an SMA-200 trend filter) is
**excluded** here — it already bakes in a trend condition, which would
confound this experiment's own regime-conditioning question.
`zscore_close_20` requires no new computation: `quant_research.
market_behavior.build_symbol_dataset` already computes it via
`add_alpha_features` as part of every `SymbolDataset`'s own pipeline.

## 4. Regime dimensions (frozen, existing definitions only, no new thresholds)

**Market trend regime**: `backtesting.regime.classify_trend_at`'s
existing `TrendRegime` enum (`TRENDING_UP` / `TRENDING_DOWN` /
`SIDEWAYS` / `UNKNOWN`), applied to `^NSEI`'s own OHLCV via
`quant_research.context_experiments.build_benchmark_regime_series` +
`attach_external_regime` — the exact machinery `H_CONTEXT_MARKET_001`/
`002` already used, unchanged (same `DEFAULT_REGIME_SLOPE_LOOKBACK`).

**Market volatility regime**: `backtesting.regime.
classify_volatility_at`'s existing `VolatilityRegime` enum (`LOW` /
`NORMAL` / `HIGH` / `UNKNOWN`), applied to `^NSEI`'s own OHLCV via
`build_benchmark_volatility_series` + `attach_external_regime` — the
exact machinery `H_CONTEXT_MARKET_003` already used, unchanged (same
`DEFAULT_REGIME_VOLATILITY_LOOKBACK=60`).

This is the **broader market's** own regime (external NIFTY overlay),
matching `H_CONTEXT_MARKET_*`'s own established convention for what
"market regime" means in this registry — deliberately **not**
`SymbolDataset`'s own built-in `trend_regime`/`volatility_regime`
columns (the stock's *own* price behavior), which would be a
economically confounded gate for a mean-reversion entry (a stock
already deviating from its own trend, by construction, makes "is this
stock trending" a less clean external condition than "what is the
whole market doing").

**Sample-size hierarchy (frozen, per the mission's own explicit
instruction)**: marginal effects first.
1. Market trend regime alone (3 buckets: UP/DOWN/SIDEWAYS).
2. Volatility regime alone (3 buckets: LOW/NORMAL/HIGH).
3. The 2-D interaction (9 cells) is attempted **only if** step 1 and
   step 2 each show at least one bucket with an adequate,
   pre-specified minimum sample (≥30 observations per split, matching
   this project's own standard promotion-gate floor) — expected sample
   counts are checked before running the interaction, not after seeing
   whether it looks promising.

## 5. Universe and data

Full 32-symbol original NSE universe (`quant_research.
universe_expansion.ORIGINAL_32_NSE_UNIVERSE`) — NSE-only, a deliberate,
disclosed change from `H_MEANREV_001`'s own pooled NSE+US design,
motivated by wanting a market-homogeneous conditioning test (this
project's own `quant_research/market_behavior.py` module docstring
already states its own default policy: "NEVER pool NSE and US unless
the caller asks for it"). 10 years daily (2016–2026), the deepest
verified NSE depth already established by the `H_XSECT`/
`H_CONTEXT_MARKET_005` threads.

## 6. Splits

The project's own established `backtesting.splits.split_periods`
60/20/20 development/validation/out-of-sample convention, applied to
the shared universe calendar exactly as every prior `H_XSECT_00x`/
`H_CONTEXT_MARKET_00x` entry already does.

## 7. Success criteria (frozen)

For a regime bucket (marginal or, if reached, interaction cell) to be
considered a real signal:
- Same directional sign (positive) across development, validation,
  AND out-of-sample — no reversal in any split.
- At least 30 observations in every split that contributes to the
  verdict (this project's own standard floor; a split below this is
  reported as insufficient data, not folded into a weaker bar).
- A 95% confidence interval excluding zero in at least development and
  out-of-sample (validation may be directional-but-not-decisive and
  still be reported as encouraging, matching `H_CONTEXT_MARKET_002`'s
  own precedent for how this project reads a real-but-underpowered
  middle split).
- No single-symbol concentration (checked the same way `H_XSECT_006`
  checked it: remove the largest contributor, confirm the result
  survives).
- Where realistic costs are relevant (i.e., if this ever proceeds past
  the raw-measurement stage), the effect must clear `CostModel.
  india_nse_intraday_2026()`'s ~0.21% round-trip estimate.

## 8. Failure criteria (frozen)

Any of:
- The regime-conditioned effect's sign reverses between any two
  splits with an adequate sample.
- No regime bucket shows an improvement over the unconditioned
  `H_MEANREV_001` control (i.e., regime information adds nothing).
- An apparently promising cell is revealed to be driven by a single
  symbol or a narrow time window once checked.
- Every cell is underpowered (< 30 observations) even at the marginal
  (non-interaction) level — reported honestly as INSUFFICIENT_DATA,
  not stretched into a claim.

## 9. Anti-p-hacking discipline (explicit, per mission instruction)

Forbidden after this document is committed: changing the -2.0/-1.5
thresholds, dropping a losing regime bucket, redefining the dev/val/
oos splits, excluding symbols that hurt the result, or repeatedly
testing adjacent regime-lookback values. Allowed: a documented
mechanical correction to a genuine bug found before results are
examined (classified explicitly, as `H_XSECT_006`'s own reference-
dataset fix was). If the marginal tests are inconclusive or rejected,
the natural interaction test (step 3 above) is only pursued if its own
pre-specified sample-size gate is cleared — not chased regardless.

## 10. Adversarial checks (mandatory if any cell looks promising)

Unconditioned-baseline comparison (does the regime cell beat
`H_MEANREV_001`'s own unconditioned NSE-only result, not just show a
positive absolute number — the same lesson `H_VOL_001` already
demonstrated is necessary given this universe's general positive
drift); era stability (first half vs. second half of the 10-year
window); symbol concentration; sector concentration (via the existing,
disclosed-as-partial `NSE_SECTOR_MAP`); liquidity split; non-overlapping
sample check if overlapping windows are used; realistic cost margin.

## 11. Reproducibility record (filled in at execution time)

To be completed after the experiment runs: exact bucket sample counts
per split, `^NSEI` data window used, any symbol exclusion, and the
`H_MEANREV_001`-derived control numbers this experiment compares
against.
