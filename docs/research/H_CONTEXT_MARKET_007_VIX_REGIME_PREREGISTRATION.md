# H_CONTEXT_MARKET_007 — Does India VIX Regime Explain the Market-Divergence Era Sign Reversal?, Pre-Registration

Written and frozen **before** any interaction result is computed. Path 2 of the user's own
capital-allocation mission (2026-09-21), executed only after Path 1 reached its own terminal
conclusion (`audit/edge_feasibility/PATH1_MEAN_REVERSION_POINT_IN_TIME_CLOSURE.md`). Per the user's
own explicit framing: **not** "try different regimes until something works" — this is the single,
final, pre-declared follow-up named explicitly in `H_CONTEXT_MARKET_006`'s own preregistration as
the one reserved alternative, tested once, with the answer accepted either way.

## 1. Research question (frozen)

"Does India VIX regime (an implied-volatility, forward-looking fear-gauge proxy) explain the
historical sign reversal of F_CONTEXT (the market/sector-divergence effect), given that NIFTY's own
REALIZED-volatility regime already failed to explain it (`H_CONTEXT_MARKET_006`, REJECTED)?"

This is explicitly the LAST pre-declared regime candidate in this line of investigation. Per the
user's own instruction, if this fails, F_CONTEXT is closed — no third regime variable will be
sought.

## 2. Audit — what already exists (verified by direct reading, not assumed)

Read directly: `quant_research/context_experiments.py::build_india_vix_regime_series` — already
-committed, already-tested (`tests/test_context_experiments.py`), reused verbatim. Wraps
`market_intelligence.regime`'s own `DEFAULT_VIX_LOOKBACK`/`DEFAULT_VIX_ELEVATED_MULTIPLIER`/
`DEFAULT_VIX_DEPRESSED_MULTIPLIER` (the SAME thresholds `compute_india_vix_context`'s own live,
latest-bar classifier already uses — made causal-historical by applying them at every bar instead of
just the last one, not a new definition). Directly verified this session: `^INDIAVIX` has full
10-year Yahoo depth (2451 bars, 2016-09-21 to 2026-09-21) via this project's own market data
provider — the data dependency is real and already satisfied, no new fetch capability needed.

## 3. Frozen regime variable

**India VIX regime** (`ELEVATED` / `DEPRESSED` / `NORMAL` / `UNKNOWN`), via
`build_india_vix_regime_series(period="10y")`, unmodified default thresholds. Chosen because it was
the ONE alternative explicitly named and reserved in `H_CONTEXT_MARKET_006`'s own preregistration —
not selected after seeing that entry's own result, decided in advance as the single designated
follow-up.

**No further regime variable will be considered after this entry**, regardless of outcome — matching
the user's own explicit "not: try different regimes until something works" instruction.

## 4. Frozen signal, universe, and splits (identical to `H_CONTEXT_MARKET_002`/`006`)

- **Condition**: `baseline_buy_condition(row)` AND external `market_trend_regime == "TRENDING_DOWN"`
  (`H_CONTEXT_MARKET_002`'s own exact condition, unchanged).
- **Universe**: `ORIGINAL_32_NSE_UNIVERSE`, unchanged.
- **Splits**: `period="10y"` via `build_symbol_dataset`'s own internal `split_periods` call — the
  same development(2016-2022)/validation(2022-2024)/out_of_sample(2024-2026) boundaries every prior
  entry in this family used.
- **Horizons**: h5 and h10, h10 primary.

## 5. What is genuinely new

Bucketing `H_CONTEXT_MARKET_002`'s own already-measured population by India VIX regime AT THE SAME
BAR (via `attach_external_regime` with `column_name="india_vix_regime"`), then measuring the
condition's forward-return effect separately within each VIX bucket, in each split. Nothing about
entry, exit convention, or universe changes.

## 6. Statistical discipline and multiple-testing correction (frozen, reported at several levels)

Same `>=30`-observation floor. Reported at: (a) the conventional uncorrected 95% CI (z=1.96), for
direct comparability with `H_CONTEXT_MARKET_002`/`006`; (b) a `family_size=2` Bonferroni correction
(this entry is the SECOND pre-declared regime-variable test in this specific investigation line,
following `H_CONTEXT_MARKET_006`); (c) the registry-wide `family_size=17` (Phase 8's own
family-search correction, now covering F_CONTEXT's 12th member after this entry). The widest
applicable correction is the binding one for any promotion-relevant claim, matching Phase 8's own
established practice.

## 7. Decision rule (frozen, identical structure to `H_CONTEXT_MARKET_006`'s own four outcomes)

1. **Genuine stable conditional effect**: one VIX bucket shows a CONSISTENT-DIRECTION h10 effect
   across all three splits (at least validation and out-of-sample CI-decisive in that direction),
   with a DIFFERENT bucket showing a materially different pattern.
2. **Unstable effect with no explanatory regime**: no bucket shows a consistent cross-split
   direction, or the dominant bucket simply reproduces the unconditioned control's own already
   -known instability.
3. **Apparent regime effect from data mining**: a pattern is decisive in development/validation but
   fails out-of-sample.
4. **Insufficient sample**: any decision-relevant cell has <30 observations; if every relevant cell
   is underpowered, the whole entry is `INSUFFICIENT_DATA`, not forced into 1/2/3.

**Per the user's own explicit instruction: if this test fails (Outcome 2, 3, or 4 without a credible
path forward), F_CONTEXT is CLOSED — this research tree ends, not continues to a third variable.**

## 8. What will NOT change after this is pre-registered

No new entry condition, universe, or horizon. No re-deriving VIX thresholds after seeing results. No
third regime variable added if this one is inconclusive. No retroactive change to
`H_CONTEXT_MARKET_002`/`004`/`005`/`006`'s own historical verdicts, regardless of outcome.

## 9. Scope note

Offline, isolated audit script (mirrors `H_CONTEXT_MARKET_006`'s own established pattern exactly).
Reuses `quant_research/context_experiments.py` and `quant_research/market_behavior.py` completely
unmodified. No production code touched, no live-fleet dependency.
