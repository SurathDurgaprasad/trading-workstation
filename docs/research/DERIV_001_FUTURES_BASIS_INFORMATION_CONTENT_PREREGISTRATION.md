# DERIV_001 — Futures Basis Information-Content Test, Pre-Registration

Written and frozen **before** any model is fit or any result is inspected. Phase 6 of the
derivatives research mission (2026-09-21). Per the mission's own instruction: "Do NOT immediately
search for profitable strategies. First determine whether derivatives variables contain incremental
information relative to the existing OHLCV features."

## 1. Research question (frozen)

"Does NIFTY futures basis improve out-of-sample prediction of NIFTY's own forward return direction,
relative to a baseline using only the existing, already-established OHLCV feature set?"

This is a statistical-information question, not a trading-strategy question. Per the mission's own
explicit caution, a positive result here does **not**, by itself, constitute a claim of trading edge
— it would only justify proceeding to Phase 7 (a genuinely preregistered trading test).

## 2. Why futures basis, and why NIFTY (not stock-level)

Per `audit/derivatives_research/PHASE3_DATA_FEASIBILITY_GATE.md`'s own classification, futures
basis is Classification A (historically usable, all nine minimum requirements met) — the strongest,
cleanest candidate, and the one requiring the least additional engineering (a single already
-continuous data source, confirmed below). NIFTY (not individual stocks) is chosen for this FIRST
information-content test because:
- A genuine, already-continuous, multi-year daily futures series was found and verified this session
  for NIFTY specifically (Dhan `/charts/historical`, `instrument=FUTIDX`, a RELATIVE `expiryCode`
  selector rather than a specific contract ID — 1,623 real daily bars, 2019-12-31 to 2026-09-17,
  confirmed economically sensible: the largest single-day moves cluster exactly around the real,
  well-documented March 2020 COVID crash, not artificial roll-splice points).
- This avoids Phase 5's own disclosed, unresolved risk (item 6, futures-roll price discontinuity)
  entirely for this specific test — Dhan's own backend appears to already handle rollover
  internally for this relative-`expiryCode` query pattern, a materially simpler starting point than
  building and trusting a brand-new manual rollover-stitching implementation (Phase 4's own
  bhavcopy-based `build_continuous_futures_series`) for the FIRST information-content test.
- It sidesteps the corporate-action/stock-identity complications (Phase 5 item 11) that any
  individual-stock derivatives test would immediately inherit.
- It is the smallest, single-underlying scope consistent with "choose the smallest economically
  motivated set" — a multi-stock cross-sectional version is explicitly deferred, not attempted here.

**Not yet verified**: whether the same internal-continuity behavior extends to `FUTSTK` (individual
stock futures) — an open item for a possible future, separately-scoped stock-level extension, not
assumed true here.

## 3. Frozen baseline feature set (the EXISTING OHLCV feature set, not invented)

Every feature below is an already-established, already-used-elsewhere-in-this-project column from
`market.indicators.compute_indicator_series` / `quant_research.alpha_features.add_alpha_features` —
none are new:
- `trend_ratio = sma_20 / sma_50 - 1` (scale-invariant trend measure, needed because NIFTY's own
  price level moved from ~8,000 to ~25,000+ across the available window — a raw `sma_20`/`sma_50`
  level would not be comparable across eras).
- `rsi_14` (momentum, already-established).
- `atr_pct = atr_14 / close` (scale-invariant volatility, same normalization reasoning as above).
- `zscore_close_20` (mean-reversion, already-established, the same field the entire closed
  `H_MEANREV` chain was built on).

## 4. Frozen augmented feature (the ONE derivatives family under test)

`futures_basis = (futures_close - spot_close) / spot_close`, computed at the SAME bar date from the
two independently-sourced series (NIFTY futures: Dhan `/charts/historical`, `FUTIDX`,
`expiryCode=0`; NIFTY spot: the existing, already-used `market.data_provider`/`^NSEI` pipeline).
**No other derivatives family is computed or tested in this entry** — OI-change was considered and
explicitly deferred (not tested), per the mission's own "do not test all seven indiscriminately"
instruction.

## 5. Frozen target

`y = 1 if fwd_return_10 > 0 else 0` — binarized sign of the h10 (10-trading-day) forward
close-to-close return, via the already-established `quant_research.alpha_features.
add_forward_return_targets`. h10 is primary, matching this project's own convention throughout the
closed OHLCV research (H_MEANREV, F_CONTEXT). h5 is reported as a secondary, corroborating horizon,
not decision-determining on its own.

## 6. Frozen model

**Logistic regression** (scikit-learn `LogisticRegression`, default L2 regularization, no
hyperparameter search) — chosen for interpretability and low overfitting risk on a modest sample,
matching the mission's own explicit "prefer DATA VALIDITY over MODEL COMPLEXITY" instruction. Not a
gradient-boosted tree, not a neural network — those would be disproportionate complexity for a
single-underlying, single-feature-family information-content check.

Two models are fit, both trained ONLY on the development split, both evaluated (never re-fit) on
validation and out-of-sample:
- **Baseline**: `trend_ratio`, `rsi_14`, `atr_pct`, `zscore_close_20`.
- **Augmented**: baseline features + `futures_basis`.

## 7. Frozen splits

`backtesting.splits.split_periods` (60/20/20), applied to the merged spot+futures dataset's own date
range (bounded by whichever series is SHORTER — the futures series, 2019-12-31 onward, since NIFTY
spot has much deeper history but the futures series is the binding constraint).

## 8. Statistical discipline

- **Primary metrics**: ROC-AUC and Brier score, on validation and out-of-sample, for both models —
  the augmented model's OWN improvement over the baseline (ΔAUC, ΔBrier) is the primary
  quantity of interest, not either model's absolute performance.
- **Calibration**: reported via a reliability comparison (predicted-probability deciles vs. realized
  frequency) for the augmented model on out-of-sample.
- **Minimum sample**: at least 100 observations per split (a lighter floor than the `MIN_SAMPLE_
  SIZE_FOR_A_VERDICT=30` trade-level floor used elsewhere, chosen because this is a per-bar
  classification task, not a per-trade economic one — every trading day in a split is one
  observation, not a rare triggered-signal event).
- **Multiple-testing family**: this is entry #1 of a NEW, explicitly-tracked "derivatives research
  family" (Phase 10 of this mission) — NOT folded into the existing 59-hypothesis OHLCV registry.
  Reported at the conventional level for THIS single, first, pre-registered test; a family-size
  correction will be applied once a second derivatives entry exists (matching how the OHLCV
  research's own Phase 8 correction was applied once the family was established, not before a
  second data point existed to correct across).

## 9. Decision rule (frozen)

- **Meaningful incremental information**: augmented ROC-AUC exceeds baseline ROC-AUC by a
  economically-non-trivial margin (≥0.02, a conventional, modest, pre-declared threshold — not
  tuned after seeing the result) on BOTH validation and out-of-sample, AND the augmented model's
  Brier score does not worsen on either split.
- **No meaningful incremental information**: any other outcome — close ROC-AUC, an improvement that
  reverses sign between validation and out-of-sample, or a worsened Brier score.
- **Per the mission's own explicit instruction**: "Do not claim trading edge from statistical
  prediction improvement alone" — even if this entry finds meaningful incremental information, the
  ONLY consequence is proceeding to Phase 7 (a fully preregistered trading test with its own
  separate decision gate), never a direct promotion claim from this entry alone.

## 10. What will NOT change after this is pre-registered

No new baseline feature added after seeing results. No second derivatives feature (e.g. OI change)
substituted in if basis disappoints. No threshold in §9 adjusted after seeing the ROC-AUC numbers.
No re-derivation of the target horizon. No retroactive change to any existing OHLCV-registry verdict
— this is a new, separately-tracked family from the start.

## 11. Scope note

Offline, isolated audit script. Reuses `market.indicators`, `quant_research.alpha_features`,
`backtesting.splits`, and this session's own new `quant_research/derivatives_data.py` /
Dhan-API-verified futures series. No production strategy/RiskEngine/order-execution code touched. No
live-fleet dependency.
