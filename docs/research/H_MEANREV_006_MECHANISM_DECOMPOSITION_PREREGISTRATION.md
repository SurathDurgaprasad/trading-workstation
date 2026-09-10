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

## 14. Scope note

Pure historical-data research, read-only. Does not touch
`data/paper_trading.db`, `data/live_state.db`, `data/scheduler_runs.db`,
`data/direction_forecasts.db`, or `data/predictions.db`. No broker
execution changes, no exit/stop/target design, no scheduler dependency.
The one Dhan-sourced input (`combined` universe membership) reuses the
already-cached, public, unauthenticated instrument master — no
credentials involved.
