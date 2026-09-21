# H_CONTEXT_MARKET_006 — Does NIFTY's Own Volatility Regime Explain the Market-Divergence Era Sign Reversal?, Pre-Registration

Written and frozen **before** any interaction result is computed. Phase B of the current mission
(`audit/edge_feasibility/PHASE_A_POINT_IN_TIME_UNIVERSE.md`'s companion phase). Per this project's
own multiple-testing discipline: the regime variable, threshold methodology, universe, splits, and
primary metric are fixed here; none may change after seeing results.

## 1. Research question (frozen, per the user's own B1 instruction)

"Does a pre-specified market-regime variable explain the historical sign reversal of F_CONTEXT
(the market/sector-divergence effect), or is the effect simply nonstationary?"

`H_CONTEXT_MARKET_005` (`audit/edge_feasibility/PHASE10_FAMILY_RANKING.md`) found the frozen
baseline BUY condition, conditioned on NIFTY TRENDING_DOWN, is CI-decisively **NEGATIVE** in
2016-2022 development and CI-decisively **POSITIVE** in 2022-2026 validation/out-of-sample — a
genuine sign reversal the original 5-year study (which only covered the post-2021 era) could not
have detected. This entry asks: is that reversal explained by a specific, pre-declared, economically
motivated regime variable, or does the effect remain unstable even after conditioning on it?

## 2. Audit — what already exists (verified by direct reading, not assumed)

Read directly: `quant_research/context_experiments.py` (`baseline_buy_condition`,
`build_benchmark_regime_series`, `build_benchmark_volatility_series`,
`build_india_vix_regime_series`, `attach_external_regime` — all already-committed, already-tested,
reused verbatim, zero new regime-computation code required); `quant_research/market_behavior.py`
(`build_symbol_dataset`, `measure_condition`, `ForwardReturnSummary`, `_period_mask`);
`backtesting/regime.py` (`classify_trend_at`, `classify_volatility_at` — the actual classifiers
`build_benchmark_regime_series`/`build_benchmark_volatility_series` wrap); `tests/
test_context_experiments.py` (confirms this machinery is already unit-tested, not merely asserted
to work).

**Confirmed**: `build_benchmark_volatility_series("^NSEI", period="10y")` applies the SAME
already-tested `classify_volatility_at` classifier (ATR14-as-%-of-close vs. its own trailing
60-bar average, `HIGH >= 1.5x`, `LOW <= 0.67x`, `NORMAL` otherwise — unmodified defaults, never
tuned against any historical performance) to NIFTY's own indicator series, one label per bar,
causally (no look-ahead — verified directly in `backtesting/regime.py`'s own docstring and
`classify_volatility_at`'s implementation, which only reads `iloc[index-lookback:index]`, strictly
before the current bar).

## 3. Frozen regime variable (a SMALL, pre-justified set of ONE — per the user's own B2 instruction)

**NIFTY's own realized-volatility regime** (`HIGH_VOLATILITY` / `NORMAL_VOLATILITY` /
`LOW_VOLATILITY` / `UNKNOWN`), via `build_benchmark_volatility_series("^NSEI", period="10y")`,
unmodified defaults (`lookback=60`, `high_multiplier=1.5`, `low_multiplier=0.67`).

**Why this variable, and why chosen before running anything**: (a) it is the ONLY volatility
-regime classifier already built, tested, and used elsewhere in this exact research family
(zero new code, zero new-threshold risk); (b) it is economically distinct from the base condition
under test (NIFTY's own TREND direction) — trend direction and volatility level are different
dimensions, so conditioning on one is not circular with the other; (c) it has a clear, standard,
pre-existing economic rationale: mean-reversion/counter-trend effects (buying a stock that
diverges bullishly from a falling market) are conventionally understood to behave differently in
choppy/high-volatility regimes than in calm, persistently-trending ones — a genuine, falsifiable
prior, not chosen because it looked promising in a first peek at the data (no peek occurred before
this document was written).

**Other candidates considered and explicitly NOT selected** (documented per B2's own "if an
appropriate variable is unavailable... document that" instruction — these were available, but a
SMALL set was required, and this is the single strongest prior candidate): India VIX regime
(`build_india_vix_regime_series`, also already-existing/tested, implied rather than realized
volatility — held in reserve as a natural follow-up only if this primary test is inconclusive, NOT
tested in this entry); NIFTY breadth (`quant_research/market_breadth.py` — introduces additional
scope/verification burden without a comparably direct a-priori link to a DIVERGENCE effect's
expected mechanism). Testing both now, then reporting only the "better" one, is exactly the kind
of after-the-fact selection this document exists to prevent — so only the volatility regime is
tested in this entry.

## 4. Frozen signal, universe, and splits (reused verbatim from `H_CONTEXT_MARKET_002`/`005`)

- **Condition**: `baseline_buy_condition(row)` (uptrend structure `close > sma_20 > sma_50` AND
  `rsi_14 > 50`) AND external `market_trend_regime == "TRENDING_DOWN"` (NIFTY's own trend, via
  `build_benchmark_regime_series("^NSEI")`) — i.e., `H_CONTEXT_MARKET_002`'s own exact condition,
  byte-for-byte unchanged. No new entry logic.
- **Universe**: `ORIGINAL_32_NSE_UNIVERSE` (`quant_research/universe_expansion.py`) — the SAME
  32-symbol universe every prior `H_CONTEXT_MARKET`/`SECTOR`/`ALIGN` entry used. NOT the
  206-symbol `COMBINED` universe (that is `H_MEANREV`'s own universe, a different research
  question; switching universes here would itself be an undisclosed methodology change).
- **Splits**: `period="10y"` via `build_symbol_dataset`'s own internal `backtesting.splits.
  split_periods` call — the SAME mechanism `H_CONTEXT_MARKET_005`'s own 10-year extension used,
  reproducing its development(2016-2022)/validation(2022-2024)/out_of_sample(2024-2026) boundaries
  without hardcoding dates.
- **Horizons**: h5 and h10 (matching every prior `H_CONTEXT` entry). **h10 is primary** for the
  decision rule below, per this family's own established convention (h5 reported as corroborating,
  not decision-determining on its own).

## 5. What is genuinely new in this entry (the ONLY change from `H_CONTEXT_MARKET_002`)

Bucketing `H_CONTEXT_MARKET_002`'s own already-measured population by NIFTY's own volatility
regime AT THE SAME BAR (via `attach_external_regime` with a second external series, `column_name=
"nifty_volatility_regime"`), then measuring `H_CONTEXT_MARKET_002`'s own forward-return effect
separately within each of the three volatility buckets, in each of the three splits. Nothing about
the entry condition, the exit/holding convention (raw h5/h10 forward close-to-close return, matching
this family's own pre-execution-structure "prove the market behavior" stage — no cost model applied
here, consistent with every prior `H_CONTEXT` entry), or the universe changes.

## 6. Statistical discipline

Same `>=30`-observation floor this family has used throughout (a cell below 30 is reported as
`INSUFFICIENT_DATA` for that cell specifically, not silently omitted or treated as zero evidence).
**Multiple-testing correction**: this entry adds ONE new regime variable tested via 3 buckets
(`HIGH`/`NORMAL`/`LOW`) — reported at both the conventional uncorrected 95% CI (z=1.96, for direct
comparability with every prior entry in this family) AND a Bonferroni-corrected CI at
`family_size=3` (via `strategy.multiple_testing.bonferroni_corrected_z`, the same primitive used in
Phase 8), reflecting the 3 buckets as the immediate comparison family for THIS entry. This is
reported ALONGSIDE, not instead of, the `family_size=17`/`family_size=56` registry-level corrections
Phase 8 already established for the whole project — the widest applicable correction is the binding
one for any promotion-relevant claim.

## 7. Decision rule (frozen, matching the four outcomes the user's own B4 specified)

1. **Genuine stable conditional effect**: the SAME volatility bucket (e.g. `HIGH_VOLATILITY`) shows
   a CONSISTENT-DIRECTION h10 effect across all three splits (dev/val/oos), with at least
   validation AND out-of-sample CI-decisive in that same direction, AND a DIFFERENT bucket (e.g.
   `LOW_VOLATILITY`) shows a genuinely different (weaker, flat, or reversed) pattern — i.e., the
   regime actually discriminates, not merely "some bucket somewhere looked positive."
2. **Unstable effect with no explanatory regime**: no bucket shows a consistent cross-split
   direction, OR the same instability (positive here, negative there, no coherent story) that
   `H_CONTEXT_MARKET_005` already found in the unconditioned data reappears inside every bucket.
3. **Apparent regime effect caused by data mining**: a pattern is CI-decisive in development or
   validation but does not hold in out-of-sample, OR is only visible in one bucket by chance with no
   plausible mechanism (guarded against here primarily by testing only ONE pre-declared variable,
   not several).
4. **Insufficient sample**: any decision-relevant cell (bucket × split) has <30 observations — that
   specific cell is reported as inconclusive, and if EVERY cell relevant to the primary claim is
   underpowered, the whole entry is classified `INSUFFICIENT_DATA`, not forced into 1, 2, or 3.

**A single positive-looking bucket in a single split does NOT, by itself, satisfy Outcome 1.** The
regime must explain the ALREADY-OBSERVED instability (dev-negative, val/oos-positive) and survive
out-of-sample under the SAME bucket assignment that looked correct in development/validation — not
be re-selected after seeing which bucket "worked" in each split independently.

## 8. What will NOT change after this is pre-registered

No new entry condition. No new universe. No new horizon. No re-deriving the volatility-regime
thresholds after seeing results. No second regime variable added if this one is inconclusive (a
follow-up entry, separately preregistered, would be required — not a same-entry pivot). No
retroactive change to `H_CONTEXT_MARKET_002`/`004`/`005`'s own historical registry verdicts,
regardless of this entry's own outcome.

## 9. Scope note

Offline, isolated audit script only (mirrors `H_MEANREV_013`'s own established pattern): reuses
`quant_research/context_experiments.py` and `quant_research/market_behavior.py` completely
unmodified. No production code touched. No live-fleet dependency. No broker/order-execution path
reachable from this analysis, matching every prior entry's own disclosed scope.
