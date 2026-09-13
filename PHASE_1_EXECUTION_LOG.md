# Phase 1 Execution Log — ML_PHASE1_v1

Chronological record of the autonomous Phase 1 execution, per the user's
own "Document every important discovery" instruction. Timestamps are
session-local (IST); dates use the environment's own current date.

## Start

- Branch: `phase1-quant-ml-foundation`, created off `main` at `a7961dd`
  (Phase 0.5 baseline commit, pushed to `origin/main` before branching).
- Baseline `git status`: clean before any Phase 1 code was written.
- Read `AUDIT_BASELINE.json`, `AUDIT_GAPS.md`, `TRADING_INTELLIGENCE_GAP_
  ANALYSIS.md`, `TRADING_FEATURE_CATALOG.json`, `PHASE_1_IMPLEMENTATION_
  SPEC.md` — all five authored earlier in this same session, held in full
  in context; re-verified no drift via `git log`/`git status` before
  proceeding (no edits occurred between authoring and this phase).

## Step 1 — Data availability (frozen sequence item 1)

- Probed `market.data_provider.YahooFinanceProvider.fetch_ohlcv` directly
  (uncached, real network calls) for `RELIANCE.NS`, `TCS.NS`, `^NSEI` at
  multiple interval/period combinations.
- **Finding**: `interval="5m", period="60d"` is the correct request —
  `period="max"` at intraday intervals returns *less* data than
  `period="60d"` (yfinance appears to clamp intraday `"max"` to an
  internal default shorter than 60 days).
- Extended the probe to the full `ORIGINAL_32_NSE_UNIVERSE` (32 symbols):
  **32/32 succeeded**, zero fetch errors, all sharing an identical
  **59-trading-session** window (`2026-06-22` to `2026-09-11`), zero
  duplicate timestamps, naive-datetime (IST wall-clock) representation.
- **Not a blocker.** Real, disclosed constraint: only ~3 calendar months
  of 5-minute history exists via this project's sole real data provider —
  materially shorter than the 10-year daily history this project's other
  research has used. Recorded in the pre-registration, not hidden.

## Step 2 — Pre-registration committed

- Wrote and committed `docs/research/ML_PHASE1_TRIPLE_BARRIER_BASELINE_
  PREREGISTRATION.md` (commit `1ef52a9`) freezing all six required
  inputs, **before** any `ml_research/` code was written:
  - `H = 8` bars (40 minutes) — inside the pre-specified 6–12 bar range,
    chosen as a direct intraday analogue of this project's own existing
    `h10` daily-bar holding convention, not tuned to any result.
  - Universe = `ORIGINAL_32_NSE_UNIVERSE` (32 symbols), not the full
    206-symbol `COMBINED` universe — the most-vetted, most conservative
    choice, and the one directly verified clean in step 1.
  - Triple-barrier label semantics reusing `predictions/tracker.py`/
    `backtesting/execution.py::check_exit` verbatim, plus one new
    refinement decided from the data's own shape (not from any result):
    labels never cross a trading-session boundary — a resolution window
    that would need a bar from the next session instead resolves as
    `TIMEOUT` at the current session's own last bar. This has the useful,
    disclosed side effect of making cross-session label leakage
    structurally impossible, since no label's resolution window can ever
    span two sessions.
  - Walk-forward: 4 expanding-window, session-level folds over 47 pool
    sessions (7-session validation blocks, 1-session embargo), 12
    sessions held out as a single final test window.
  - Cost model: `CostModel.india_nse_intraday_2026()`, unmodified.

## Step 3 — Environment

- Confirmed `pandas`, `numpy`, `yfinance` already installed; `scikit-
  learn==1.9.0` already present (transitive); `pyarrow` was **not**
  installed — installed it (`pip install pyarrow`, resolved to
  `25.0.1`) for Parquet I/O.
- Documented both in `requirements.txt`, matching the file's own
  established "direct dependency, pinned to the version in venv/"
  convention, with a comment explaining why each was added.

## Step 4 — `ml_research/` package implementation

Wrote, in order: `__init__.py`, `features.py`, `labels.py`, `dataset.py`,
`walk_forward.py`, `baseline_model.py`, `expected_value.py`,
`evaluation.py`.

Design decisions made during implementation (disclosed, not silent):

- `market_intelligence/scanner.py`'s own `trend_score`/`momentum_score`/
  `breakout_score`/`relative_strength_score`/`sector_strength_score`/
  `composite_score` functions operate only on a series' own LATEST bar
  (a live "scan now" operation) — they cannot be called directly to
  produce a per-bar value across full history. `ml_research/features.py`
  contains vectorized re-implementations of the *identical* formulas
  (cited by `scanner.py` line number at each point), not a re-derivation.
- `sector_strength_score` requires the whole 32-symbol universe
  simultaneously (a cross-sectional pass) — implemented as
  `add_sector_strength_score`, a second pass over all 32 symbols' already-
  built frames, exploiting the fact (confirmed in step 1) that every
  symbol shares an identical timestamp index. Sector-tag coverage via
  `market_intelligence/nse_sector_map.py::NSE_SECTOR_MAP` is 21/32 for
  this universe (previously known, re-confirmed this session) — the
  other 11 symbols get `sector_strength_score = NaN`, matching
  `scanner.py`'s own None-when-untagged behavior exactly, and are
  complete-case-dropped by the model fit (never imputed).
- `expected_value.py`'s formula is a disclosed simplification versus
  `PHASE_1_IMPLEMENTATION_SPEC.md` Section 9's own three-outcome sketch:
  the frozen label scheme (Section 5's own binary `TARGET_FIRST=1` /
  `STOP_OR_TIMEOUT=0` convention, matching the user's Phase 1 mission
  message Section 8) means the model produces only `P(target)`, not
  separate `P(stop)`/`P(timeout)`. `(1 - P(target))` is treated as if it
  always realized the full stop-loss return — a conservative
  approximation, not an attempt to recover a 3-way split the binary
  model was never trained to produce. Named explicitly in the module's
  own docstring and repeated in the final report's Limitations section.

## Step 5 — Leakage test suite (release gate)

- Wrote `tests/test_ml_research_leakage.py`: 15 tests covering feature
  no-look-ahead (3 new features + 1 reused-indicator sanity check), label
  session-boundary enforcement, label resolved-at-strictly-after-
  timestamp, label horizon respected, join-safety acceptance and
  rejection, join correctly excludes `INSUFFICIENT_DATA` rows, walk-
  forward fold non-overlap and strict-precedence, walk-forward fold
  expansion, walk-forward duplicate-session rejection, feature/label
  reproducibility, and the anomaly guard.
- **First run: 2 of 15 failed.** Both were test-fixture bugs, not
  leakage bugs, root-caused and fixed:
  1. `test_reused_indicators_still_no_lookahead_through_this_wrapper`
     compared an index before either indicator's own warmup period had
     completed (both sides legitimately `NaN`, and the `pytest.approx`
     comparison doesn't handle `NaN == NaN`). Fixed: compare at an index
     past both warmup periods, with an explicit `NaN`-safe branch.
  2. Same test, second bug: the mutation start index (11) was *before*
     the comparison index (15), so the comparison index's own bar value
     had itself legitimately changed — not a leakage question at all.
     Fixed: mutate strictly after the comparison index.
  3. `test_join_excludes_insufficient_data_labels` exposed a **real
     design bug in `dataset.py` itself** (not the test): the join-safety
     "reject if empty" check ran *after* filtering out
     `INSUFFICIENT_DATA` rows, so a dataset where the only overlapping
     row was legitimately `INSUFFICIENT_DATA` was incorrectly treated as
     a construction error. Fixed by moving the emptiness check to before
     the quality filter, checking raw `(symbol, timestamp)` overlap
     separately from whether anything survives quality filtering.
- **Second run: all 15 passed.**

## Step 6 — Full experiment execution

Ran `ml_research/run_experiment.py` against real market data via
`CachedMarketDataProvider`. **Four attempts, three real bugs found and
fixed, root-caused each time before rerunning** (per the "autonomous
recovery" discipline — no symptom-patching, no silent workaround):

1. **Attempt 1** (`ml_phase1_run.log`) — feature/label generation for all
   32 symbols succeeded (139,462 feature rows, 139,430 label rows,
   persisted to Parquet), but `dataset.join_features_and_labels` raised
   `JoinSafetyError: features frame is missing required columns:
   ['timestamp']`. **Root cause**: the feature DataFrame's index carried
   the name `"Date"` (inherited from `OHLCV.to_dataframe()`'s own
   convention through `compute_indicator_series`), so
   `frame.reset_index().rename(columns={"index": "timestamp"})` silently
   renamed nothing (there was no column literally named `"index"`).
   **Fix**: `frame.rename_axis("timestamp").reset_index()`, which renames
   the axis itself regardless of its prior name.
2. **Attempt 2** (`ml_phase1_run2.log`) — join succeeded (139,014 rows,
   join-safety assertion passed); failed inside `baseline_model.fit_fold`
   with `ValueError: could not convert string to float: 'decreasing'`.
   **Root cause**: `volume_trend` (from `market/indicators.py`) is a
   categorical string (`"increasing"`/`"decreasing"`/`"neutral"`),
   included directly in `dataset.FEATURE_COLUMNS` as if numeric. **Fix**:
   added `volume_trend_score` (a numeric {-1,0,+1} encoding of the same
   already-computed value, mirroring `trend_score`'s own convention) in
   `features.py`, and swapped it into `FEATURE_COLUMNS` in place of the
   raw string column. Updated the corresponding test fixture in
   `tests/test_ml_research_leakage.py` (`_minimal_feature_row`) to match,
   reran the full leakage suite (15/15 passed) before rerunning the
   experiment.
3. **Attempt 3** (`ml_phase1_run3.log`) — feature/label/join stages
   succeeded again; failed inside `expected_value.compute_expected_value`
   with `TypeError: CostModel.cost_for_fill() takes 1 positional argument
   but 2 were given`. **Root cause**: `cost_for_fill`'s own signature
   (`backtesting/costs.py:43`) takes `notional` as a **keyword-only**
   argument (`def cost_for_fill(self, *, notional: float)`); called
   positionally. **Fix**: `cost_model.cost_for_fill(notional=notional)`
   at both call sites.
4. **Attempt 4** (`ml_phase1_run4.log`) — **completed successfully end to
   end.** Feature/label build reused the on-disk `CachedMarketDataProvider`
   cache from attempt 1 (no repeated network calls), so the full run
   (feature build through final promotion-gate verdicts) completed in
   under 2 minutes.

## Step 7 — Post-run diagnostics

- Queried the persisted Parquet artifacts directly to confirm: label
  outcome distribution (`TIMEOUT` 52.9%, `STOP_FIRST` 36.6%,
  `TARGET_FIRST` 10.1%, `INSUFFICIENT_DATA` 0.3%); per-symbol row-count
  evenness (4,349–4,364, no single-symbol dominance); `sector_strength_
  score` NaN rate (34.67%, consistent with 11/32 symbols untagged in
  `NSE_SECTOR_MAP`); `relative_strength_score` NaN rate (0.46%, warmup
  only).
- Computed a trivial-baseline (constant base-rate) Brier score for each
  fold/the held-out test as an explicit "does this beat doing nothing
  clever" check — the model beat the trivial baseline in every single
  fold and the held-out test, narrowly but with zero reversals.

## Step 8 — Regression and reporting

- Full `pytest` regression: **1960 passed, 3 failed, 1963 collected**
  (baseline before this phase: 1948 collected). The 3 failures are the
  **same pre-existing, unrelated** `tests/test_daily_report.py`
  data-staleness failures already diagnosed earlier in this session
  (local market-data cache aged past its 5-day freshness threshold) —
  confirmed unrelated by scope: `ml_research/` and
  `tests/test_ml_research_leakage.py` do not touch `main.py`'s
  `daily-report` command or its cache-staleness logic at all. 1963 − 1948
  = 15, exactly matching the 15 new leakage tests added — no other test
  count changed, confirming nothing else in the existing suite was
  touched or broken.
- Final report: `PHASE_1_REPORT.md`.

---

## Final Results

See `PHASE_1_REPORT.md` for the full, formatted results. Headline:
**[TESTED]** real, modest, consistent statistical discrimination
(ROC-AUC 0.575–0.615 across every fold and the held-out test; Brier
score beats a trivial constant-base-rate baseline in every fold, never
reversed) — but **[TESTED]** decisively negative economic performance
net of real costs for BOTH the new model and the existing deterministic
rule benchmark, on every one of the development/validation/out-of-sample
splits (`PromotionVerdict.NEGATIVE` for both, via the unmodified
`strategy.promotion_gate.evaluate_promotion`). Recommendation:
`NO EVIDENCE OF EDGE` (economic), a complete and valid Phase 1 outcome
per invariant 10.
