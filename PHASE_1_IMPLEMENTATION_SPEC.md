# Phase 1 Implementation Specification — Quantitative Prediction Foundation

**Status**: Specification. No code has been written against this document. Nothing in this repository has been modified to produce it. This is the handoff artifact between Phase 0.5 (research/gap analysis) and Phase 1 (implementation) — matching this project's own established Phase Execution Rules (`PROJECT_GOAL_AND_ROADMAP.md` §24: understand → define scope → branch → baseline → implement incrementally → test → audit → commit → push → reconcile → merge decision). Whoever implements Phase 1 should read this document as the scope definition Step 2 requires, not as a suggestion to improvise around.

**Predecessor documents**: `TRADING_INTELLIGENCE_GAP_ANALYSIS.md` (the research), `TRADING_FEATURE_CATALOG.json` (the candidate-signal inventory), the architecture diagram published alongside them.

## The falsifiable objective

> Determine whether an intraday feature vector contains economically useful, out-of-sample information about triple-barrier trade outcomes after costs.

Everything below exists to answer this one question honestly. A `REJECTED` or `INCONCLUSIVE` answer is a complete, successful Phase 1 — see Acceptance Gates.

---

## 1. Locked invariants (frozen at handoff, version `invariants_v1`)

These do not change during Phase 1 implementation. If an implementer believes one must change, that is itself a scope-change requiring a new pre-registration, not a silent edit here.

| # | Invariant |
|---|---|
| 1 | A feature snapshot is strictly `as-of t` — computed only from bars with timestamp `<= t`. |
| 2 | Labels may use `t, t+1, ..., t+H` (future bars). Features may never use anything past `t`. |
| 3 | A model probability never directly becomes `BUY`. |
| 4 | Expected value is a distinct computation from probability — probability is an input to it, not a synonym for it. |
| 5 | Risk evaluation remains fully deterministic (`risk/engine.py`, unmodified) and independent of any model output beyond the expected-value number it is handed. |
| 6 | The existing deterministic strategy (`decision_engine/rules.py::classify`, unmodified) remains the benchmark every model result is compared against — never a strawman, never retired quietly. |
| 7 | Evaluation criteria (Section 8, below) are fixed **before** any model is fit to any data. |
| 8 | No live execution capability is introduced during this phase. The structurally-disabled Dhan order path (`live/dhan/broker_adapter.py`) is not touched. |
| 9 | No LLM integration is added to this pipeline during this phase — see `TRADING_INTELLIGENCE_GAP_ANALYSIS.md`'s P3, unchanged. |
| 10 | A demonstrated absence of edge is a valid, useful, complete result — not a failure requiring escalation to a more complex model within this phase. |

### The model is a forecasting component, not a replacement trading strategy

This must be impossible to lose during implementation. Logistic regression's output is one measurement feeding a comparison — never a strategy standing on its own, never a second decision engine running in parallel with authority to act. The evaluation hierarchy is:

```text
Historical 5m bars → as-of-t feature set → Logistic regression → P(target first)
                                                                        │
                                                          Expected value + costs
                                                                        │
                                              ┌─────────────────────────┴─────────────────────────┐
                                              │                                                     │
                                      Deterministic rule                                       New model
                                    (existing, unmodified)                                  (this phase's output)
                                              │                                                     │
                                              └─────────────────────────┬─────────────────────────┘
                                                                        │
                                                       identical OOS observations
                                                          (same symbols, dates, costs)
                                                                        │
                                                             Economic comparison
```

`P(target first) != BUY`, at every point in this pipeline, without exception. The probability is an economic input to the deterministic decision/risk layer (Section 9) — it is evaluated on whether it makes that layer's output better, never asked to act by itself. The deterministic rule and the new model are measured as two candidate inputs to the *same* downstream comparison, not as two competing trading systems.

### The one architectural boundary that matters most

```text
TRAINING DATA
     │
     ├── feature snapshot @ t              (Section 4 schema, Section 5 timestamp contract)
     │
     └── label resolved using (t, t+1 ... t+H)   (Section 6 label semantics)

MODEL
     │
     └── probability estimate               (Section 9, logistic regression only in Phase 1)

DECISION
     │
     ├── probability
     ├── payoff (target_return, stop_return — Section 6)
     ├── costs (Section 7, existing CostModel, unchanged)
     ├── liquidity (existing scanner gates, unchanged)
     └── deterministic risk constraints (risk/engine.py, unmodified)
     ↓
TRADE / NO TRADE
```

The label generator, future bars, realized outcomes, or any post-entry information must never reach the feature-generation code path. This is enforced structurally in Section 3 (feature and label data live in physically separate datasets, joined only at training time by a single, tested join function) and verified by the leakage test suite in Section 10 — not left as a discipline to remember.

---

## 2. Scope

**In scope for Phase 1**: an offline, research-only feature engine; an offline triple-barrier label generator; one logistic regression baseline; a walk-forward evaluation harness with purge/embargo; a promotion-gate-style acceptance verdict. All of it lives outside the live/paper/decision pipeline, reachable by nothing in `main.py`'s live commands, exactly as `quant_research/` is architecturally isolated today.

**Out of scope for Phase 1** (deferred per `TRADING_INTELLIGENCE_GAP_ANALYSIS.md`'s P2/P3, restated here as a hard boundary, not a suggestion):
- Any model beyond logistic regression (no random forest, gradient boosting, neural network — those are a *later* phase's own pre-registered hypothesis, only if logistic regression shows signal).
- Any feature not explicitly listed in Section 4 as Phase 1 scope (VWAP distance, opening gap, normalized intraday range are the only *new* features in scope; everything else stays at "candidate" per `TRADING_FEATURE_CATALOG.json`).
- Wiring the model's output into `decision_engine/`, `paper/`, or any live command.
- Any LLM/RAG integration.
- Options/derivatives/microstructure features (confirmed unreliable or absent per the gap analysis).
- Modifying `strategy/baseline.py`, `risk/engine.py`, `decision_engine/rules.py`, `backtesting/`, or any other existing production module. Phase 1 reads their constants and reuses their pure functions; it does not edit them.

---

## 3. Module and data layout (proposed, not mandated — confirm before coding)

**New top-level package: `ml_research/`** — parallel to, never imported by, `quant_research/`, `strategy/`, `risk/`, `paper/`, `decision_engine/`, matching the exact isolation posture `quant_research/alpha_features.py`'s own module docstring already establishes for that package. A sibling package rather than a subpackage of `quant_research/` because Phase 1 introduces a genuinely new capability class (fitted models, calibration, a feature/label data pipeline) rather than another alpha-signal hypothesis in the existing research family's own shape.

Proposed contents (naming indicative, not final):
```
ml_research/
    __init__.py
    features.py          # FeatureSnapshot construction, as-of enforcement
    labels.py             # triple-barrier label generation (offline adaptation
                           # of predictions/tracker.py::evaluate_prediction)
    dataset.py             # joins features + labels, enforces the join-safety
                           # invariant, produces the training-ready table
    baseline_model.py     # logistic regression wrapper: fit, calibrate, predict
    walk_forward.py       # NEW retrain-per-fold harness (distinct from, and
                           # not a modification of, backtesting/walk_forward.py)
    evaluation.py         # metrics from Section 8, reusing learning/profitability.py
                           # and strategy/promotion_gate.py wherever the shape matches
    expected_value.py      # the decision-layer calculation (Section 9's boundary)
```

**Data storage**: Parquet files (not SQLite), partitioned by `symbol` and `year_month`, under `data/ml_research/features/` and `data/ml_research/labels/` (kept physically separate directories, not merged tables, per the architectural boundary in Section 1). Rationale: this project's existing SQLite stores hold prediction/decision/scan records at one-row-per-decision granularity; an intraday feature store at one-row-per-bar-per-symbol granularity, across 200+ symbols and multiple years, is a different scale and access pattern, and columnar storage avoids straining the existing SQLite convention it would be inconsistent to force this into. This is a new data-storage decision requiring explicit confirmation before implementation, not an automatic extension of the existing `*_store.py` pattern.

**Pre-registration**: before any code in `ml_research/` is written, produce `docs/research/ML_PHASE1_TRIPLE_BARRIER_BASELINE_PREREGISTRATION.md`, following this project's own established convention (see any `H_MEANREV_0XX_..._PREREGISTRATION.md` for the shape) — this specification is the source material for that document, not a replacement for it. The pre-registration must restate Sections 4–9 below verbatim as the frozen design, committed before any experiment code produces a result.

---

## 4. Dataset schema

Two physically separate datasets, joined only inside `ml_research/dataset.py`'s own tested join function.

### 4a. Feature dataset (`data/ml_research/features/symbol=<SYM>/year_month=<YYYY-MM>/*.parquet`)

| Column | Type | Notes |
|---|---|---|
| `symbol` | string | |
| `timestamp` | datetime, UTC, tz-aware | the signal bar's own close time — the `t` every invariant refers to |
| `interval` | string | e.g. `"5m"` — pinned per dataset generation run, never mixed intervals in one file |
| `feature_version` | string | sha256 of `ml_research/features.py`'s own source, mirroring `DecisionConfig.version_id()`'s existing convention — any formula change produces a new version, old datasets stay attributable |
| `data_version` | string | identifies the underlying OHLCV retrieval (cache timestamp or content hash) — distinguishes a re-fetch/backfill from the original data a given row was computed against |
| `close`, `open`, `high`, `low`, `volume` | float | raw, as-of `t` only |
| `sma_20`, `sma_50`, `rsi_14`, `macd`, `macd_signal`, `macd_histogram`, `atr_14`, `volume_ratio`, `volume_trend` | float / categorical | reused verbatim from `market/indicators.py`, unmodified |
| `trend_score`, `momentum_score`, `breakout_score`, `relative_strength_score`, `sector_strength_score`, `composite_score` | float | reused verbatim from `market_intelligence/scanner.py`, unmodified |
| `vwap_distance` | float | **new for Phase 1** — `(close - session_vwap) / session_vwap`; `session_vwap` must reset at session open, never roll across days — see Open Questions, item 3 |
| `opening_gap` | float | **new for Phase 1** — `(session_open - prior_session_close) / prior_session_close`, computed once per session, forward-filled within the session, `null` for a symbol's first observed session |
| `intraday_range_normalized` | float | **new for Phase 1** — `(high - low) / close` for the current bar |
| `market_regime` | categorical | `UPTREND` / `DOWNTREND` / `UNKNOWN`, from `learning/regime.py::classify_regime_at`, reused unmodified, joined as a stratification feature |
| `entry_reference_price` | float | the price the label generator will use for entry — the next bar's slippage-adjusted open, computed and stored here (not re-derived inside the label generator) so features and the label's own entry price are guaranteed to agree |

**Explicitly excluded from this dataset, by the invariant in Section 1**: anything from `predictions/`, `paper/`, `risk/`, any realized return, any outcome label, any bar timestamped after `t`.

### 4b. Label dataset (`data/ml_research/labels/symbol=<SYM>/year_month=<YYYY-MM>/*.parquet`)

| Column | Type | Notes |
|---|---|---|
| `symbol` | string | joins to the feature dataset on `(symbol, timestamp)` |
| `timestamp` | datetime, UTC, tz-aware | must exactly match a feature-dataset `timestamp` — the label generator never invents its own timestamps |
| `label_generator_version` | string | sha256 of `ml_research/labels.py`'s own source |
| `horizon_bars` | int | `H`, frozen per Section 6 |
| `stop_price`, `target_price` | float | derived from `entry_reference_price` and `atr_14` per Section 6's exact formula |
| `outcome` | enum | `TARGET_FIRST` / `STOP_FIRST` / `TIMEOUT` / `INSUFFICIENT_DATA` |
| `realized_return` | float, nullable | `exit_price / entry_reference_price - 1`; `null` when `outcome == INSUFFICIENT_DATA` |
| `bars_to_resolution` | int, nullable | |
| `resolved_at` | datetime | the timestamp of the resolving bar |

`INSUFFICIENT_DATA` rows (the anomalous-gap guard, Section 6) are **excluded from training**, never imputed, never silently converted to `TIMEOUT` — matching `predictions/tracker.py`'s own existing convention exactly.

---

## 5. Feature timestamp contract (the "as-of" enforcement)

1. A row's `timestamp` is bar `t`'s own close time. All feature values in that row are computed using **only** bars with index `<= t` — this is the exact no-look-ahead guarantee `market/indicators.py::compute_indicator_series` already provides for the reused indicators (SMA/RSI/MACD/ATR/volume), and must be independently true for the three new features (`vwap_distance`, `opening_gap`, `intraday_range_normalized`) by construction, not by inheritance.
2. `entry_reference_price` stored on the feature row is the **next** bar's (`t+1`) slippage-adjusted open — matching `backtesting/execution.py` and `compute_fixed_notional_trade`'s existing entry convention exactly. Storing it on the `t`-row (rather than computing it inside the label generator) is deliberate: it guarantees the feature snapshot and the label generator agree on entry price without a second, potentially-diverging computation.
3. `feature_version` and `data_version` are mandatory, non-null, on every row. A training run that cannot resolve both for a row must exclude that row rather than proceed with unknown provenance.
4. Regeneration policy: features are **never edited in place**. A feature-formula change produces a new `feature_version` and a new dataset generation run; old runs remain on disk, addressable, and never silently overwritten — matching this project's own append-only-store convention (`docs/SECURITY_REVIEW.md`'s confirmed "append-only invariant holds on every historical store").

---

## 6. Label semantics (triple-barrier, exact)

Adapts `predictions/tracker.py::evaluate_prediction` and `backtesting/execution.py::check_exit` for offline, historical, batch use — the resolution mechanics are not reinvented, only re-targeted at historical bars instead of live-forward ones.

**Entry**: `entry_reference_price` = slippage-adjusted open of bar `t+1` (from the feature row, Section 5 item 2).

**Stop and target**: reuse `strategy/baseline.py`'s existing frozen constants unchanged —
```text
STOP_ATR_MULTIPLIER = 1.5      # strategy/baseline.py:8
TARGET_RISK_REWARD  = 2.0      # strategy/baseline.py:9

stop_price   = entry_reference_price - STOP_ATR_MULTIPLIER * atr_14_at_t
target_price = entry_reference_price + TARGET_RISK_REWARD * (entry_reference_price - stop_price)
```
Not re-derived, not re-tuned for this phase — using the project's own existing risk/reward convention keeps the ML label comparable to what a real trade using this system's own sizing would attempt, and avoids quietly inventing a second stop/target methodology alongside the one already in production.

**Horizon**: `H` bars, a single frozen integer, **fixed only after Open Questions item 1 (intraday data depth) is resolved** — not chosen in this document. Candidate starting range: 6–12 bars on 5-minute data (≈30–60 minutes), per the gap analysis's own reasoning; the exact value must be pre-registered in `docs/research/ML_PHASE1_TRIPLE_BARRIER_BASELINE_PREREGISTRATION.md` before any label is generated, and never changed after seeing results.

**Resolution loop**, for each bar from `t+1` to `t+H`:
```text
if low <= stop_price and high >= target_price:   # same-bar ambiguity
    outcome = STOP_FIRST        # conservative rule, see Ambiguous-Bar Handling below
elif low <= stop_price:
    outcome = STOP_FIRST
elif high >= target_price:
    outcome = TARGET_FIRST
elif bars_observed >= H:
    outcome = TIMEOUT
else:
    continue to next bar
```

**Anomaly guard**: reuse `predictions/tracker.py`'s existing `ANOMALOUS_BAR_GAP_THRESHOLD = 0.5` unchanged — any bar whose `low`/`high` implies a >50% move from the previous close (the unadjusted-corporate-action signature this guard already exists to catch) resolves the label to `INSUFFICIENT_DATA` immediately, not `STOP_FIRST`/`TARGET_FIRST`/`TIMEOUT`.

---

## 7. Ambiguous-bar handling

**Same-bar stop-and-target ambiguity**: resolved as `STOP_FIRST`, reusing `backtesting/execution.py::check_exit`'s exact conservative "assume the stop was hit first" rule, **unchanged, not reconsidered for this phase**. This is a deliberate choice for apples-to-apples comparability: the deterministic-rule benchmark (invariant 6) uses this exact rule, and any divergence here would confound "the model found a real edge" with "the model benefited from a more favorable ambiguity rule than its own benchmark."

**Gap-through-stop**: as the gap analysis already disclosed, this codebase's execution model fills exactly at `stop_price`, never at a worse gapped price, in both the existing backtester and this label generator (by reuse). This is a shared, disclosed limitation of the THEORETICAL result on both sides of the comparison — not corrected here, since correcting it only for the new model would bias the comparison, not fix realism symmetrically.

**Missing/duplicate bars within the resolution window**: a gap in the bar sequence between `t+1` and the resolving bar does not, by itself, trigger `INSUFFICIENT_DATA` (only the anomalous-price-gap guard does) — but the label generator must log a `bars_observed` count distinct from `bars_to_resolution` to make any data-completeness issue auditable after the fact, matching `docs/OBSERVABILITY.md`'s own established "make it queryable, not just logged" convention.

---

## 8. Walk-forward validation design

Distinct from, and not a modification of, `backtesting/walk_forward.py` — that module explicitly has no retraining mechanism (correct for a parameter-free frozen rule, insufficient for a fitted model). This is new, additive code.

**Structure**: expanding-window walk-forward, not a single random train/test split.

```text
Fold 1: [train: start..T1]  [purge]  [validate: T1+purge..T2]
Fold 2: [train: start..T2]  [purge]  [validate: T2+purge..T3]
Fold 3: [train: start..T3]  [purge]  [validate: T3+purge..T4]
...
Final:  [train: start..Tn-1] [purge] [TEST (held out, evaluated once): Tn-1+purge..end]
```

**Purge/embargo rule (the overlapping-label safeguard, made concrete)**: any training row whose label-resolution window `[t, t+H]` overlaps the validation/test window's own start must be excluded from that fold's training set. Purge length = `H` bars minimum, plus a small fixed embargo buffer (propose 1 additional bar) to avoid boundary edge cases. This directly implements the overlapping-label risk `TRADING_INTELLIGENCE_GAP_ANALYSIS.md` names as the single largest statistical risk in the plan — it must be tested (Section 10), not merely stated.

**Number of folds**: not fixed here — determined by the actual data volume from Open Questions item 1. Propose reusing `backtesting/walk_forward.py::split_into_n_folds`'s own equal-length-window logic as a starting point for computing fold boundaries, adapted for expanding (not equal-length) training windows.

**Final test window**: held out and evaluated **exactly once**, after every other decision (feature set, horizon, hyperparameters) is frozen — matching this project's own `development`/`validation`/`out_of_sample` discipline (`shared_period_boundaries`'s existing convention) applied to a model-fitting context for the first time.

**Retrain cadence**: refit the logistic regression at each fold boundary (a cheap operation for this model class) — not once for the whole walk-forward run.

---

## 9. Cost assumptions and the expected-value / decision boundary

**Cost model**: `backtesting/costs.py::CostModel.india_nse_intraday_2026()`, reused unmodified. Every report this pipeline produces must repeat, verbatim, the existing disclosed limitation: GST, stamp duty, and SEBI charges are **not** included — this is not a one-time footnote, it must appear on every acceptance-gate report (Section 11), matching this project's own convention of repeating caveats rather than assuming a reader recalls an earlier one.

**The two-layer boundary (invariants 3 and 4, made computational)**:

```text
MODEL LAYER (ml_research/baseline_model.py)
    p_target, p_stop, p_timeout = model.predict_proba(feature_row)

DECISION LAYER (ml_research/expected_value.py)
    target_return = (target_price - entry_reference_price) / entry_reference_price
    stop_return   = (stop_price   - entry_reference_price) / entry_reference_price   # negative
    expected_gross_return = p_target * target_return + p_stop * stop_return
                             # p_timeout contributes 0 by convention in Phase 1 --
                             # a real timeout return distribution is a later refinement,
                             # not assumed here
    expected_net_return = expected_gross_return - cost_model.cost_for_fill(...)/notional * 2
                             # entry AND exit cost, matching CostModel's own
                             # brokerage_per_fill convention (charged both sides)

    # THIS NUMBER, not p_target alone, is what the decision layer produces.
    # It is handed to risk/engine.py exactly as a deterministic signal's own
    # composite_score sign is handed to classify() today -- as an input,
    # never as a self-executing decision.
```

`risk/engine.py` is not modified to consume this — Phase 1 does not wire this into the live risk engine at all (out of scope, Section 2). This computation exists so that Phase 1's own evaluation (Section 8) measures the thing that would actually matter if this were ever wired in, rather than measuring raw classification accuracy and hoping it translates.

---

## 10. Testing requirements (must pass before any result is trusted)

Extends `tests/test_backtest_lookahead.py`'s existing pattern (mutate a future row, confirm an earlier value is unchanged) — not a new testing philosophy, the same one this project already applies elsewhere.

1. **Feature no-look-ahead**: for each new feature (`vwap_distance`, `opening_gap`, `intraday_range_normalized`), construct a synthetic bar series, mutate every bar strictly after `t`, and confirm the feature value at `t` is unchanged. (The reused indicators already have this coverage in `market/indicators.py`'s own test suite — do not re-test what is already tested, cite it instead.)
2. **Label uses only `t+1..t+H`**: confirm the label generator never reads a bar timestamped before `t+1` for entry pricing, and never reads a bar beyond `t+H` for resolution.
3. **Join safety**: confirm the feature/label join function (`ml_research/dataset.py`) never produces a training row where the feature's own `timestamp` is later than or equal to the label's `resolved_at` minus the horizon — i.e., a structural assertion that the join cannot silently smuggle a resolved outcome back into a feature row.
4. **Purge/embargo correctness**: confirm, for a synthetic walk-forward fold boundary, that every training row surviving the purge has a label-resolution window entirely before the validation window's start, with zero exceptions — not a statistical check, an exact structural one.
5. **Anomaly guard passthrough**: confirm a bar sequence containing a >50%-gap synthetic event produces `INSUFFICIENT_DATA`, not `STOP_FIRST`/`TARGET_FIRST`, and confirm such rows are excluded from the training dataset produced by `dataset.py`.
6. **Reproducibility**: confirm two runs of the full feature+label generation pipeline over identical input data produce byte-identical output (matching this project's own established determinism-testing convention, e.g. `test_schedule_portfolio_deterministic_replay`'s pattern from this session's own earlier work).

No acceptance-gate number (Section 11) may be reported until all six pass.

---

## 11. Acceptance gates

Computed on the held-out final test window only, after every design choice above is frozen. Every report states all of the following together — a partial report (e.g., accuracy alone) is not acceptable.

**Leakage gate (binary, must pass first)**: the full Section 10 test suite passes with zero failures. If this gate fails, no other number in this section may be reported or acted on.

**Discrimination**: ROC-AUC, PR-AUC, log loss, Brier score — reported, not gated on a specific number for this first baseline (no prior baseline exists to set a threshold against).

**Calibration**: a reliability table (predicted-probability decile vs. realized outcome frequency) — reported; a systematically miscalibrated model (e.g., predicted 0.7 realizing at 0.4) is a disqualifying finding regardless of other metrics, since invariant 4's expected-value calculation depends on the probability being roughly honest.

**Statistical significance**: `strategy/promotion_gate.py::evaluate_promotion`, applied to the expected-net-return series (Section 9) from the held-out window, reused unmodified. **Open question**: whether `MIN_SAMPLE_SIZE_FOR_A_VERDICT = 30` (the existing constant) remains appropriate at intraday sample sizes, which will likely be far larger than any prior hypothesis in this project's history — raising it is a legitimate consideration, but must be decided and pre-registered before results are seen, not adjusted afterward to reach a verdict.

**Economic significance (the real bar, per the review that produced this document)**: the model's expected-net-return series must beat the existing deterministic rule's own net performance (invariant 6) on the **identical** held-out window, symbols, and cost model — not merely beat zero. Report both series' `PromotionVerdict` side by side, exactly as `H_MEANREV_012`'s own control-vs-ranked comparison in this project's research history already did.

**Overall verdict**: `PROMOTED` / `REJECTED` / `INCONCLUSIVE` / `INSUFFICIENT_DATA`, using the existing `evaluate_promotion` vocabulary unmodified. Per invariant 10: `REJECTED` or `INCONCLUSIVE` is a complete, honestly-reported Phase 1 outcome. A `PROMOTED` verdict here means "worth a Phase 2 pre-registration to consider wiring in," never "ready for live use" — the same distinction this project's own promotion gate has always drawn between statistical promotion and live-trading readiness.

---

## 12. Open questions to resolve before coding starts

These are prerequisites, not implementation details to sort out along the way.

1. **Intraday data depth and reliability** — verified empirically (fetch and inspect, do not assume) for the intended universe at the candidate interval(s) before `H` (Section 6) is fixed. This project's own code (`main.py:1872-1884`) already confirms no workflow has ever exercised an intraday interval — this is a real unknown, not a formality.
2. **Universe for Phase 1** — the full ~206-symbol combined universe, or a smaller, deliberately chosen subset for the first run? A smaller, liquid subset reduces confounding from thin/unreliable intraday data on illiquid names and is the more defensible first choice, but must be stated and frozen in the pre-registration, not left implicit.
3. **VWAP session-reset convention** — confirm exactly how a "trading session" boundary is determined from the data source in use (Yahoo intraday bars do not self-annotate session boundaries the way a broker feed might) before implementing `vwap_distance`; an incorrect session boundary silently corrupts this feature without raising an error.
4. **`MIN_SAMPLE_SIZE_FOR_A_VERDICT`** — see Section 11; decide and pre-register before results are seen.
5. **Purge/embargo buffer size** — Section 8 proposes `H + 1` bars as a starting point; confirm this is sufficient given the actual autocorrelation structure of the chosen universe/interval once real data is in hand, rather than treating the proposed number as final.

---

## 13. Frozen implementation sequence

This order is itself an invariant, not a suggestion — its purpose is to prevent implementation results from ever influencing experimental design, the same discipline `strategy/hypothesis_registry.py`'s own pre-registration convention already enforces everywhere else in this project. Steps 1–6 must all complete, and their results committed to the pre-registration document (Section 3), before step 7 writes a single line of code.

```text
 1. Resolve data availability/depth           (Open Questions §12 item 1)
 2. Freeze H                                  (Section 6, pending step 1)
 3. Freeze the dataset date range/universe    (Open Questions §12 item 2)
 4. Freeze label semantics                    (Section 6, fully specified above)
 5. Freeze walk-forward geometry              (Section 8, pending steps 1-2)
 6. Freeze the cost model                     (Section 9 -- already frozen: CostModel.india_nse_intraday_2026(), unmodified)
──────────────────────────────────────────── nothing above this line may change after step 7 ────
 7. Implement dataset construction            (ml_research/features.py, labels.py, dataset.py)
 8. Run leakage tests                         (Section 10 -- must pass with zero failures)
 9. Implement the logistic regression baseline (ml_research/baseline_model.py)
10. Run out-of-sample evaluation              (Section 8's held-out test window, evaluated once)
11. Compare against the deterministic benchmark (Section 11's economic-significance gate)
12. Only then consider promotion/integration  (a PROMOTED verdict here starts a NEW, separate
                                                Phase 2 pre-registration -- it does not itself
                                                authorize wiring anything into decision_engine/)
```

A result discovered during steps 7–12 is never grounds for revisiting steps 1–6 within this same pre-registered run — that would be exactly the "look at results, then decide the design" failure mode this project's own multiple-testing discipline exists to prevent. If steps 1–6's frozen choices turn out to be wrong in hindsight, that is itself a finding to report honestly (per invariant 10), and grounds for a *new*, separately pre-registered Phase 1b — not a silent do-over of this one.

## 14. Handoff checklist

- [ ] This specification reviewed and any open questions in Section 12 answered.
- [ ] `docs/research/ML_PHASE1_TRIPLE_BARRIER_BASELINE_PREREGISTRATION.md` written and committed, restating Sections 4–9 as the frozen design, **before** any `ml_research/` code is written.
- [ ] Module layout (Section 3) confirmed or revised.
- [ ] A new branch created (matching this project's own branching convention observed throughout its git history) — not committed directly to `main` for exploratory Phase 1 work, given its scope and the number of new modules involved.
- [ ] Baseline `pytest` run and recorded before any change, per this project's own established discipline.
- [ ] Section 10's test suite implemented and passing **before** Section 11's acceptance gates are computed on real data.
- [ ] Full regression run and observed (not assumed) before any Phase 1 branch is proposed for merge.
- [ ] Final report follows this project's own `[VERIFIED]`/`[TESTED]`/`[INFERENCE]`/`[HYPOTHESIS]` labeling discipline, exactly as every prior hypothesis in `strategy/hypothesis_registry.py` has.
