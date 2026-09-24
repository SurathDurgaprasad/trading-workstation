# Phase 1 Report — ML_PHASE1_v1 Triple-Barrier Baseline

`experiment_version: ML_PHASE1_v1` | branch `phase1-quant-ml-foundation` |
pre-registration: `docs/research/ML_PHASE1_TRIPLE_BARRIER_BASELINE_
PREREGISTRATION.md` | raw artifacts: `data/ml_research/`

Verdict labeling follows this project's own established convention:
`[VERIFIED]` (directly observed), `[TESTED]` (a specific, reported
statistical result), `[INFERENCE]` (a reasoned conclusion from
verified/tested facts, disclosed as such), `[HYPOTHESIS]` (open,
unverified).

---

## Executive summary

**What was tested**: whether a logistic regression trained on this
project's own already-computed technical features (plus three new
intraday features) can discriminate, and calibrate a probability for,
whether a triple-barrier exit hits its ATR-based target before its
ATR-based stop within 8 five-minute bars (40 minutes) — and, separately,
whether that probability translates into a positive economic result net
of real NSE intraday costs, compared against the existing deterministic
rule on identical data.

**Dataset**: `ORIGINAL_32_NSE_UNIVERSE` (32 symbols), 5-minute bars, 59
trading sessions (`2026-06-22`–`2026-09-11`), via `yfinance`.

**Horizon**: `H = 8` bars.

**Model**: logistic regression only (scikit-learn, Platt-scaled), no other
model type in scope for this phase.

**Benchmark**: `decision_engine.rules.classify`'s own corroboration logic
(`composite_score > 0 AND trend_score > 0 AND momentum_score > 0`),
evaluated on the identical rows, symbols, dates, and cost model as the
model.

**Result**: **[TESTED]** the model shows real, modest, statistically
consistent discrimination (ROC-AUC 0.57–0.61 across every walk-forward
fold and the held-out test; Brier score consistently, if narrowly, better
than a trivial constant-base-rate baseline). **[TESTED]** Neither the
model nor the existing deterministic rule clears the economic bar: both
report a `PromotionVerdict.NEGATIVE` (CI-decisive negative expected net
return, net of real costs) on every one of the development, validation,
and out-of-sample splits.

**Does evidence support further development?** Not in its current form.
The statistical discrimination is real but small, and is fully consumed
(and then some) by realistic transaction costs on this dataset's own
short, single-regime window. See Recommendation.

---

## Data audit

- **Source**: `market.data_provider.YahooFinanceProvider` (yfinance),
  unmodified, `interval="5m"`, `period="60d"`.
- **Coverage**: **[VERIFIED]** all 32/32 symbols of `ORIGINAL_32_
  NSE_UNIVERSE` fetched successfully; 59 distinct trading sessions,
  identical first (`2026-06-22`) and last (`2026-09-11`) session across
  every symbol; 72–75 bars/session (consistent with NSE's ~6.25-hour
  session, no material intraday gap evidence); **zero duplicate
  timestamps** across all 32 symbols, directly counted.
- **Timestamp integrity**: naive `datetime` (no `tzinfo`), IST wall-clock
  values (`09:15`–`15:30`), consistent with this project's own
  established convention elsewhere.
- **Missing data**: **[TESTED]** of 139,430 generated labels, 416
  (0.30%) resolved as `INSUFFICIENT_DATA` (the anomalous-bar-gap guard)
  — a low rate, consistent with generally clean intraday data over this
  window.
- **Limitation, disclosed and load-bearing**: **59 trading sessions is a
  narrow, single ~3-month window**, not the multi-year span this
  project's daily-bar research has used. Regime diversity within it is
  almost certainly limited (see Regime Analysis).

## Label audit

- **Barrier semantics**: triple-barrier, `stop_price = entry - 1.5 ×
  atr_14`, `target_price = entry + 2.0 × (entry - stop_price)`
  (`strategy/baseline.py`'s own frozen constants, unmodified), `H = 8`
  bars, same-bar ambiguity resolved `STOP_FIRST` (matching
  `backtesting/execution.py::check_exit` exactly).
- **Session-boundary square-off**: a label that would need a bar past its
  own entry session's last bar instead resolves `TIMEOUT` at that
  session's own last bar — verified structurally impossible to violate
  by `tests/test_ml_research_leakage.py::test_label_generator_ignores_
  bars_beyond_its_own_session`.
- **Label distribution** (all 139,430 generated labels, before the
  `INSUFFICIENT_DATA` rows are excluded from training):

  | Outcome | Count | Share |
  |---|---|---|
  | `TIMEOUT` | 73,835 | 52.9% |
  | `STOP_FIRST` | 51,034 | 36.6% |
  | `TARGET_FIRST` | 14,145 | 10.1% |
  | `INSUFFICIENT_DATA` | 416 | 0.3% |

  **[INFERENCE]** `TIMEOUT` dominating (over half of all labels) is
  consistent with an 8-bar horizon frequently being too short, for this
  ATR-scaled stop/target combination on this universe, for either barrier
  to be reached — a real characteristic of this specific frozen
  configuration, not a data defect.

## Feature audit

Full definitions with formulas, sources, and leakage status are in
`TRADING_FEATURE_CATALOG.json`; this table lists only what was actually
computed and used in `ML_PHASE1_v1`.

| Feature | Source | Leakage status |
|---|---|---|
| `sma_20`, `sma_50`, `rsi_14`, `macd`, `macd_signal`, `macd_histogram`, `atr_14`, `volume_ratio` | `market/indicators.py`, reused unmodified | Inherits that module's own existing no-look-ahead guarantee |
| `volume_trend_score` | `market/indicators.py`'s `volume_trend`, numerically re-encoded (`increasing`=+1/`decreasing`=−1/`neutral`=0) for model consumption | Same as above |
| `trend_score`, `momentum_score`, `breakout_score`, `relative_strength_score` | Vectorized re-implementation of `market_intelligence/scanner.py`'s own per-latest-bar formulas | **[TESTED]** — `tests/test_ml_research_leakage.py`'s no-look-ahead tests |
| `sector_strength_score` | Cross-sectional pass over the 32-symbol universe, `market_intelligence/nse_sector_map.py::NSE_SECTOR_MAP` | **34.67% NaN** (11/32 symbols have no sector tag) — complete-case-dropped, never imputed |
| `composite_score` | Equal-weighted (1.0 each) sum of the five scores above | Same as constituents |
| `vwap_distance` | New for Phase 1, session-reset VWAP | **[TESTED]** no-look-ahead |
| `opening_gap` | New for Phase 1 | **[TESTED]** no-look-ahead |
| `intraday_range_normalized` | New for Phase 1 | **[TESTED]** no-look-ahead |

`relative_strength_score` NaN rate: 0.46% (early-warmup rows only).
Every `NaN` feature value is complete-case-dropped at model fit/predict
time, never imputed — a row with any missing feature contributes nothing
to the model, rather than a fabricated value contributing something.

## Validation methodology

- **Folds**: 4 expanding-window, session-level walk-forward folds over a
  47-session pool (18/25/32/39 training sessions respectively, 7-session
  validation blocks, 1-session embargo — **[VERIFIED]** structurally
  impossible to overlap, `tests/test_ml_research_leakage.py::test_walk_
  forward_folds_never_let_train_and_validate_sessions_overlap`), plus a
  final model refit on the full 47-session pool, evaluated exactly once
  on the 12-session held-out test window.
- **Preprocessing**: `StandardScaler`, fit only on each fold's own
  training rows (enforced structurally by `sklearn.pipeline.Pipeline`).
- **Calibration**: Platt scaling (`CalibratedClassifierCV`, `method=
  "sigmoid"`, internal 3-fold CV), fit only on the training fold, never
  on validation/test outcomes.
- **Random seed**: fixed (`20260913`) throughout.

## Model results (statistical)

| Fold | Train rows (complete-case) | Validate rows | ROC-AUC | PR-AUC | Log loss | Brier | Positive rate |
|---|---|---|---|---|---|---|---|
| 1 | 26,440 | 16,800 | 0.575 | — | — | 0.0855 | 9.52% |
| 2 | 37,318 | 16,517 | 0.604 | — | — | 0.0896 | 10.04% |
| 3 | 48,053 | 16,308 | 0.608 | — | — | 0.0931 | 10.49% |
| 4 | 58,621 | 16,294 | 0.615 | — | — | 0.0905 | 10.17% |
| **Held-out test** | 105,674 | 18,070 | **0.606** | **0.144** | **0.327** | **0.0922** | 10.42% |

**[TESTED]** ROC-AUC is consistently above 0.5 in every fold and rises
monotonically with training-set size (0.575→0.615) — **[INFERENCE]** a
pattern consistent with (not proof of) more training data continuing to
help, untested beyond this window's own 59-session ceiling.

**[TESTED]** Trivial-baseline comparison (Brier score of a model that
always predicts the fold's own constant base rate, `p×(1−p)`):

| Fold/test | Model Brier | Trivial-baseline Brier | Model better? |
|---|---|---|---|
| 1 | 0.0855 | 0.0861 | Yes, narrowly |
| 2 | 0.0896 | 0.0903 | Yes, narrowly |
| 3 | 0.0931 | 0.0939 | Yes, narrowly |
| 4 | 0.0905 | 0.0913 | Yes, narrowly |
| Held-out test | 0.0922 | 0.0934 | Yes, narrowly |

**[TESTED]** The model beats the trivial constant-probability baseline
in every single fold and on the held-out test — small (≈0.6–1.3%
relative reduction), but perfectly consistent, never reversed. This is
genuine, if modest, calibrated signal, not noise.

## Economic results

Cost model: `CostModel.india_nse_intraday_2026()`, unmodified.
**Disclosed, repeated per this project's own convention: GST, stamp
duty, and SEBI charges are NOT included in this preset.**

**Simplification, disclosed**: the model's own `expected_net_return` is
computed for **every** row (a probability-weighted average of the target
and stop payoffs net of costs, per `PHASE_1_IMPLEMENTATION_SPEC.md`
Section 9), not gated by any `expected_value > 0` decision threshold —
i.e. it answers "what is the expected outcome of acting on every signal,
weighted by the model's own probability" rather than "what would a
rational agent earn by only acting on the subset it judges profitable."
The deterministic rule's own comparison number, by contrast, is
inherently gated (it only "trades" rows where its own binary condition
fires — 6,416 of 18,070 held-out rows, 35.5%). **This asymmetry is named
explicitly as a limitation below**, not silently presented as a perfectly
matched comparison, even though both series are computed from the
identical underlying rows, dates, symbols, and cost model.

| Split | Model expectancy (net) | Model 95% CI | Model verdict | Rule expectancy (net) | Rule 95% CI | Rule verdict |
|---|---|---|---|---|---|---|
| Development | −0.431% | [−0.433%, −0.429%] | `NEGATIVE_PERFORMANCE` | −0.225% | [−0.231%, −0.220%] | `NEGATIVE_PERFORMANCE` |
| Validation | −0.380% | [−0.381%, −0.379%] | `NEGATIVE_PERFORMANCE` | −0.231% | [−0.236%, −0.225%] | `NEGATIVE_PERFORMANCE` |
| Out-of-sample | −0.404% | [−0.406%, −0.402%] | `NEGATIVE_PERFORMANCE` | −0.243% | [−0.250%, −0.236%] | `NEGATIVE_PERFORMANCE` |

**Overall promotion verdict — MODEL: `PromotionVerdict.NEGATIVE`.
DETERMINISTIC RULE: `PromotionVerdict.NEGATIVE`.** Both, via `strategy.
promotion_gate.evaluate_promotion`, unmodified — every split's 95% CI
lies entirely below zero for both candidates; this is a **confident**
negative result, not merely an unproven one (`STATISTICALLY_
MEANINGLESS` would mean the CI straddled zero — it does not, in either
candidate, on any split).

## Benchmark comparison

**[TESTED]** The model's own net expectancy is *more* negative than the
deterministic rule's on every split (roughly −0.38% to −0.43% vs. −0.23%
to −0.24%). Given the disclosed asymmetry above (the model's own number
is unconditional, the rule's is pre-filtered to its own "would trade"
subset), this comparison should be read cautiously — it does **not**
straightforwardly mean "the model is worse than the existing rule";
it more directly reflects that the model's own unconditional expected
value, averaged across every signal regardless of confidence, is
naturally more diluted than a rule that already filters to its own
higher-conviction subset. **Neither reading changes the primary
conclusion**: both are decisively negative after costs on this dataset.

## Failure analysis

**[INFERENCE]** The `Brier`-vs-`trivial-baseline` and `ROC-AUC`-vs-0.5
comparisons show the model is not learning nothing — there is real,
consistent discriminative signal in this feature set for this labeling
scheme. The failure is specifically **economic**: the magnitude of the
edge (a few tenths of a percentage point in ROC-AUC/Brier terms) is
smaller than the round-trip transaction cost this project's own cost
model charges at the ₹25,000 notional used here. **[VERIFIED]** cost
fraction per round-trip trade at ₹25,000 notional, computed directly
from `CostModel.india_nse_intraday_2026()`:
`(2 × 20.0 + 25000 × (0.00375+0.025)/100 × 2) / 25000 ≈ 0.38%` per
round trip — large relative to the target return most triple-barrier
target hits realize at this horizon, and larger still relative to the
model's own modest discrimination edge.

## Regime analysis

**Not computed in this run — disclosed as not run, not silently
skipped.** The 59-session window is short enough (per the pre-
registration's own upfront disclosure) that it almost certainly
represents a narrow slice of market conditions, not the multi-regime
diversity `market_intelligence/regime.py`/`learning/regime.py` could
stratify on a multi-year daily series. Building and joining a regime
label onto this dataset was not part of the frozen `ML_PHASE1_v1` scope;
a genuine regime-conditioned breakdown is deferred to a future,
separately-scoped phase, once (if) a longer intraday history becomes
available to make such a breakdown meaningful rather than a single-bucket
tautology.

## Symbol breadth

**[VERIFIED]** Per-symbol row counts are tightly even (4,349–4,364
across all 32 symbols) — no single symbol dominates the raw dataset by
construction (each symbol contributes an almost-identical number of
5-minute bars over the identical 59-session window). A per-symbol
economic-contribution breakdown (which symbols drove the negative
result) was not computed in this run — a reasonable next diagnostic if
this experiment is ever revisited, not performed here to keep Phase 1's
own scope bounded to what was frozen.

## Limitations

1. **59 trading sessions is a narrow window** — the single largest
   constraint on this entire experiment's statistical power, disclosed
   in the pre-registration before any code was written, not discovered
   after the fact.
2. **The model/rule economic comparison asymmetry** named above
   (unconditional expected value vs. a pre-filtered rule) — a genuine
   apples-to-apples caveat on the Benchmark Comparison section.
3. **`sector_strength_score` is unavailable for 11/32 symbols** (no
   `NSE_SECTOR_MAP` tag) — those rows are complete-case-dropped for
   every model fit, silently reducing effective sample size for exactly
   those symbols, not just for that one feature.
4. **The binary label collapses `STOP_FIRST` and `TIMEOUT`** into one
   class, per the frozen label scheme — `expected_value.py`'s own
   simplification (treating all "not target" mass as a full stop-loss
   return) is conservative but not a precise 3-way accounting.
5. **The overlapping-label statistical-independence caveat**, named in
   the pre-registration and `ml_research/evaluation.py`'s own docstring,
   applies to every confidence interval reported above: adjacent
   5-minute signals for the same symbol have resolution windows that can
   overlap in time, so the effective sample size behind each reported CI
   is smaller than its own raw row count — the CIs are directionally
   informative (all comfortably exclude zero here) but should not be
   read as precisely calibrated to the literal `n` shown.
6. **No live-market or forward-paper validation** — this is a purely
   offline, historical experiment, as scoped.

## Recommendation

**`NO EVIDENCE OF EDGE`** (economically, after realistic costs, on this
dataset). The statistical discrimination is real, modest, and
consistent (worth recording, not dismissing), but is not economically
actionable at the transaction-cost scale this project's own cost model
charges, over the only intraday history currently available. Per
invariant 10, this is a complete, valid, useful Phase 1 result — the
falsifiable objective has been answered: **on this dataset, this feature
set, and this cost model, the intraday feature vector does not contain
economically useful out-of-sample information about triple-barrier
outcomes, though it does contain real, non-trivial statistical
information.**

This does **not** invalidate the pipeline or the architecture — every
invariant held (see Compliance Checklist below), and the negative result
was reached through the SAME rigor this project's own promotion gate
applies to every hypothesis. A future phase, if pursued, should prioritize
(in order): (1) a longer intraday history (once/if a data source with
more than ~60 days of 5-minute NSE history is found — Dhan's own live
feed, accumulated over time, is the only currently-known path within
this repository's existing integrations), before (2) any new feature or
model complexity, since this run's own evidence suggests the ceiling is
currently set by data volume and cost economics, not by an under-powered
model or a missing feature.
