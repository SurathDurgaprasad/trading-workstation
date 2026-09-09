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

## 11. Reproducibility record

- Universe: `quant_research.universe_expansion.ORIGINAL_32_NSE_UNIVERSE`, all 32 built successfully, 10y daily via `CachedMarketDataProvider`.
- `^NSEI` trend + volatility regime series: `build_benchmark_regime_series`/`build_benchmark_volatility_series`, `period="10y"`, cached.
- No symbol exclusions.
- `H_MEANREV_001`-derived NSE-only control (Step 0, never measured before): h20, Candidate A dev n=2195 +0.92%, val n=523 +1.79%, oos n=785 +0.47%; Candidate B dev n=5568 +0.97%, val n=1541 +1.79%, oos n=2080 +0.73%. All positive at h20 (unlike H_MEANREV_001's own original pooled NSE+US result, which was flat/mixed) — a genuinely new observation in its own right, though not decisive at every horizon.

## 12. Results — market TREND regime alone: `TRENDING_UP` is a real, broad, non-decaying finding; `TRENDING_DOWN`/`SIDEWAYS` unstable; volatility regime rejected; interaction not pursued

Full evidence: `H_MEANREV_003` in `strategy/hypothesis_registry.py`.

**Step 1 — market trend regime, marginal.** At h5/h10/h20,
`market_trend_regime == TRENDING_UP` is **CI-decisive positive in
development, validation, AND out-of-sample, for BOTH candidates, at
every one of those three horizons — no sign reversal anywhere**:

| Candidate | Split | h5 | h10 | h20 |
|---|---|---|---|---|
| A (−2.0σ) | dev (n=775) | +0.77% | +1.47% | +1.75% |
| A | val (n=225) | +0.44% | +0.78% | +1.31% |
| A | oos (n=250/238) | +0.65% | +1.31% | +1.47% |
| B (−1.5σ) | dev (n=2053) | +0.73% | +1.25% | +1.72% |
| B | val (n=617) | +0.60% | +1.07% | +1.73% |
| B | oos (n=616/583) | +0.57% | +0.99% | +1.37% |

`TRENDING_DOWN` and `SIDEWAYS` both show the familiar "development/
validation decisive, out-of-sample reverses toward zero or negative"
shape this registry has repeatedly flagged as disqualifying (e.g.
`SIDEWAYS` h20: dev/val decisive positive for both candidates,
out-of-sample -0.77%/-0.47%, CI touching zero) — neither clears the
frozen success criteria.

**Step 2 — market volatility regime, marginal.** Both `LOW_VOLATILITY`
and `HIGH_VOLATILITY` show clear sign reversals between splits for
both candidates (e.g. `LOW_VOLATILITY` h20 Candidate A: dev +6.23%,
validation **-2.00%**, out-of-sample **-2.22%**), and the validation
split for these extreme buckets is severely underpowered (n=8-36 across
both candidates) — consistent with this project's own repeated finding
(`H_CONTEXT_VIX_001`, `H_VOL_001`) that volatility regimes are rare and
temporally clustered, not a stable conditioning dimension at this
universe size. **REJECTED as a marginal conditioner.**

**Step 3 — interaction, not pursued.** Per the pre-registration's own
frozen sample-size gate: volatility regime's own informative buckets
(LOW/HIGH) are far too small even at the marginal level (validation
n=8-36) to support a further 2-D split with trend regime — proceeding
would only produce smaller, less meaningful cells. Correctly not
attempted, per §4's own pre-specified rule.

### Adversarial checks on the `TRENDING_UP` finding

**Symbol concentration** (full period, h20): both candidates fire on
all 32 symbols at least once. Candidate A: 24/32 symbols show a
positive mean; top-5 contributors (`DIVISLAB.NS`, `BAJAJFINSV.NS`,
`EICHERMOT.NS`, `SBIN.NS`, `NTPC.NS`) are large but not implausible per
trade, and losses are modest and spread across the bottom-5. Candidate
B: 29/32 positive — broader still. **Not concentrated in a handful of
names.**

**Cost sensitivity** (full-period pooled, h20): mean +1.62%/+1.66%
(A/B). Survives a **0.30% round-trip cost** with a wide margin (net
+1.32%/+1.36%) — comparable margin to this project's strongest prior
findings. This is the raw-measurement cost check only; this project's
own `H_XSECT_002`/`004` already demonstrated a wide raw-measurement
cost margin does *not* guarantee an executable, stop/target-managed
strategy survives — that remains untested here.

**Era stability — year-by-year** (Candidate B, h20, the check that
resolved an initial ambiguity from a simple 50/50 split): 2017 +2.80%
(decisive), 2018 -0.02% (flat, not decisive), 2019 +3.07% (decisive),
2020 +4.98% (decisive, the COVID crash/recovery year), 2021 +1.98%
(decisive), **2022 -3.36% (decisive NEGATIVE — the one real
exception)**, 2023 +1.57% (decisive), 2024 +1.36% (decisive), 2025
+3.25% (decisive, one of the strongest years on record), 2026 -0.26%
(partial year, not decisive). **7 of 9 complete years are CI-decisive
positive; only 2022 is decisively negative; the most recent complete
year (2025) is among the strongest.** This is normal year-to-year
variation around a real, non-decaying effect, not a clean decay
pattern — a materially different, more reassuring shape than gap-fade's
own (`H_GAP_003`) "decisive 2021-2024, flat 2025-2026" decay signature.
The initial 50/50 era-split (`docs/research/...` §10 diagnostic run)
showed "early half strong (+2.61%), late half weak (+0.58%)" purely
because 2022's single bad year sits at the start of that split's late
half and drags its average down — resolved, not a genuine finding of
its own once the year-by-year breakdown is examined.

### Verdict

**INCONCLUSIVE — a genuine, well-validated raw price-behavior finding,
not yet an executable-strategy claim**, following this project's own
established `H_XSECT_001` precedent exactly: `market_trend_regime ==
TRENDING_UP` conditions `H_MEANREV_001`'s oversold entry into a
CI-decisive-positive, broad-based, cost-margin-surviving, non-decaying
signal across all three splits and both frozen candidates — the
cleanest, most complete NSE-only regime-conditioning result this
registry has produced (in contrast to every one of the 14 prior
baseline-signal regime hypotheses, all of which showed at least one
sign reversal or a severe sample-size limitation). It is **not**
promoted to SUPPORTED because — exactly as this project's own
`H_XSECT_002`/`004`/`005` sequence already demonstrated for a different
signal — a raw, cost-free measurement is not the same claim as a real,
risk-sized, stop/target-managed trade, and that conversion has not yet
been attempted here. The next well-motivated step, if pursued, is
building the equivalent of `H_MEANREV_001`'s own executable wrapper
(`quant_research/mean_reversion_signal.py`'s `MeanReversionSignalStrategy`,
already exists) gated additionally on `market_trend_regime ==
TRENDING_UP`, run through `strategy/promotion_gate.py`'s real dev/val/
oos verdict — its own new, honestly pre-registered hypothesis, not
folded into this one after the fact.
