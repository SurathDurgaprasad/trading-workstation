# H_MOMENTUM_001 — Multi-Horizon Momentum Interaction, Pre-Registration

Written and frozen **before** any experiment code runs. Per this
project's own multiple-testing discipline: the metric, thresholds,
universe, splits, and success/failure criteria are fixed here; none
may change after seeing results.

## 1. Research direction and question

Per the user's own explicit next-direction guidance, priority #2:
"Multi-horizon momentum interaction — short-term weakness combined
with medium/long-term strength. Conceptually different from pure mean
reversion: buy temporary weakness inside persistent structural
strength." `H_EXTREME_001` (priority #1) is complete and closed.

**Question**: does a single stock's own SHORT-TERM weakness
(`trailing_return_5` in the lower tail of its own distribution),
measured **while** that same stock's own MEDIUM/LONG-TERM momentum
(`trailing_return_60`) is in the upper tail (structurally strong),
predict a better forward return than either condition alone? The
critical scientific question (not merely "is the combined condition's
average positive") is whether long-horizon strength adds **incremental
predictive information** beyond simply buying short-term weakness — an
interaction effect, not just another mean-reversion variant.

## 2. Registry audit — what already exists (verified against the registry, not assumed)

`grep` across `strategy/hypothesis_registry.py` for
`trailing_return_5`/`trailing_return_20`/`trailing_return_60`/momentum-
interaction/pullback/multi-horizon terminology, followed by reading the
three real candidates it surfaced in full:

- **`H_ENTRY_003`** ("Pullback entries... buying a temporary dip within
  an established uptrend") is the closest conceptual precedent, but a
  genuinely different formulation: uptrend condition via SMA-based
  trend filter + RSI14 dropping from >=55 two bars ago into [40,55] +
  a same-day resumption close (a 5-way AND, RSI-shape metric family),
  tested immediately as an EXECUTABLE strategy (with stop/target
  attached) on the 41-symbol (32 NSE + 9 US) universe. Result:
  INCONCLUSIVE / INSUFFICIENT_DATA — only 29 trades pooled across all
  three splits, below this project's own 30-trade floor. This entry
  uses a completely different metric family (raw-magnitude percentile
  returns, not RSI level/shape), a completely different universe (NSE
  standard 32), and tests RAW MEASUREMENT first, not an executable
  strategy — a genuinely independent way of asking a related economic
  question, not a repeat of the same test.
- **`H_MEANREV_003`** (TRENDING_UP-conditioned mean reversion) is the
  other close precedent: short-term weakness via `zscore_close_20`
  (standardized deviation from a 20-bar mean) AND a MARKET-WIDE regime
  flag (`market_trend_regime == TRENDING_UP` on `^NSEI`, the SAME value
  shared by every symbol on a given date). This entry's own "structural
  strength" condition is instead a per-STOCK, continuous, idiosyncratic
  measure (`trailing_return_60`) — an individual stock's own momentum,
  not the broader index's regime. This is a materially different
  question: "is THIS stock strong" vs. "is the MARKET strong."
- **`H_RELSTRENGTH_001`** ("relative strength alone predicts
  continuation") is directly relevant supporting context, not a
  precedent for this formulation: buying medium-term strength ALONE
  (no weakness condition) was REJECTED (CI-decisive NEGATIVE on the
  largest-sample candidate). This strengthens the economic case for
  testing the INTERACTION specifically — the project's own evidence
  says "buy strength alone" fails, so if there is an edge here, it must
  come from the combination, not from the strength condition by itself.
- **`H_EXTREME_001`** (just completed) tested `trailing_return_5` tail
  extremes ALONE (no long-horizon condition), at the 5th/95th
  percentile, single-horizon. Genuinely different question (no
  interaction, more extreme tails, no 60-bar dimension at all).

No hypothesis in this registry has tested a per-stock, continuous,
multi-horizon AND-interaction between short-term `trailing_return_5`
weakness and long-term `trailing_return_60` strength. Confirmed
genuinely novel.

## 3. Infrastructure audit — reuse, no new calculations

- `quant_research.cross_sectional.add_lookback_return_columns` already
  computes `trailing_return_5`, `trailing_return_20`, AND
  `trailing_return_60` in one call (`DEFAULT_LOOKBACKS = (5, 20, 60)`)
  — zero new production code for the metric itself.
- `quant_research.market_behavior.measure_condition` already accepts
  an arbitrary `condition_fn(row) -> bool` — a combined AND predicate
  (`trailing_return_5 <= WEAKNESS_THRESHOLD and trailing_return_60 >=
  STRENGTH_THRESHOLD`) needs no new machinery, matching the exact
  reuse pattern `H_EXTREME_001`/`H_MEANREV_003`/`H_XSECT_003` already
  established.
- `quant_research.cross_sectional.shared_period_boundaries` (dev/val/
  oos calendar split) and `quant_research.universe_expansion.
  ORIGINAL_32_NSE_UNIVERSE` (standard 32-symbol universe) reused
  unchanged.
- No duplicate trailing-return calculation is created — the existing
  `add_lookback_return_columns` is the single source of truth for this
  metric family across the registry (`H_XSECT_001`-`006`,
  `H_EXTREME_001`, and now this entry).

**This phase requires zero new production code.** A scratch measurement
script only, matching `H_EXTREME_001`'s own precedent exactly.

## 4. Metric and thresholds (frozen)

- **SHORT_WEAKNESS**: `trailing_return_5 <= WEAKNESS_THRESHOLD`, where
  `WEAKNESS_THRESHOLD` is the **20th percentile** (lower tail, a
  moderate pullback — deliberately NOT the 5th percentile used by
  `H_EXTREME_001`'s `EXTREME_WEAKNESS`, both to test a genuinely
  different, milder "ordinary pullback" concept per `H_ENTRY_003`'s own
  framing, and because ANDing two 5th/95th-percentile extreme filters
  would produce a sample size far too small to evaluate at all) of the
  **NSE-pooled, development-period-only** `trailing_return_5`
  distribution.
- **STRUCTURAL_STRENGTH**: `trailing_return_60 >= STRENGTH_THRESHOLD`,
  where `STRENGTH_THRESHOLD` is the **80th percentile** (upper tail) of
  the **NSE-pooled, development-period-only** `trailing_return_60`
  distribution. Same reasoning: a top-quintile "clearly outperforming"
  reading, not an extreme, rare 95th-percentile rally.
- Both thresholds computed ONCE, from real development-period data,
  before any validation/out-of-sample bar is examined, and frozen from
  that point forward — matching `H_EXTREME_001`'s own precedent
  methodology exactly (same freeze discipline, different percentiles,
  justified above, not tuned after seeing any result).
- `trailing_return_20` is explicitly NOT used as an additional
  structural-confirmation filter, to keep this a single, simple
  two-condition interaction (fewer researcher degrees of freedom) —
  disclosed here as a deliberate design choice, not an oversight.

## 5. Universe and data (frozen)

Full original 32-symbol NSE universe
(`quant_research.universe_expansion.ORIGINAL_32_NSE_UNIVERSE`) — this
project's own established default. 10 years daily, matching every
`H_XSECT_00x`/`H_MEANREV_00x`/`H_EXTREME_001` entry.

## 6. Splits and horizons (frozen)

`shared_period_boundaries` derived 60/20/20 development/validation/
out-of-sample split, matching every prior cross-sectional/multi-symbol
entry. Horizons: `FORWARD_HORIZONS = (1, 2, 3, 5, 10, 20)` bars, all
six reported. **Primary horizon: h5** (matching `H_EXTREME_001`'s own
choice, for direct comparability, and because the short-term-weakness
condition itself is a 5-bar measure — the horizon over which that
specific pullback would be expected to resolve). h10/h20 are named
secondary horizons of particular interest (a "structural strength
reasserting itself" story plausibly takes longer than 5 bars to show
fully) but are not cherry-picked after the fact — all six are always
reported together.

## 7. Experiment design (frozen)

Pure measurement first, per this project's own established two-phase
workflow. Four conditions measured independently, each via
`measure_condition(..., market_filter="NSE")`, across development,
validation, and out-of-sample, for all six horizons:

1. **UNCONDITIONAL** — no filter (`condition_fn` always `True`) — the
   baseline every other condition is compared against.
2. **SHORT_WEAKNESS_ALONE** — `trailing_return_5 <= WEAKNESS_THRESHOLD`.
3. **STRUCTURAL_STRENGTH_ALONE** — `trailing_return_60 >=
   STRENGTH_THRESHOLD`.
4. **COMBINED** — both conditions true simultaneously (the AND
   interaction — the entry's actual hypothesis).

Minimum sample-size requirement: **>=30 pooled observations per split**
for the COMBINED condition specifically (this project's own standard
floor, matching `H_ENTRY_003`'s own INSUFFICIENT_DATA precedent) — if
not met in any split, the verdict is INSUFFICIENT_DATA/INCONCLUSIVE,
not a forced positive/negative read.

## 8. The critical scientific question (frozen operationalization)

Per the mission's own explicit framing: "does long-horizon strength
provide incremental predictive information about short-term weakness,"
NOT merely "does the combined condition have a positive average."
Operationalized precisely, at the primary horizon (h5), BEFORE any
result is seen:

**The COMBINED condition's point-estimate mean return must exceed
BOTH the SHORT_WEAKNESS_ALONE and STRUCTURAL_STRENGTH_ALONE point
estimates, in the same period, for the out-of-sample split** — this is
the specific, falsifiable claim that an "interaction," not just "another
mean-reversion flavor," exists. If COMBINED is no better than either
single condition alone out-of-sample, incremental information is NOT
supported, regardless of whether COMBINED's own raw average is
positive.

## 9. Success / failure / inconclusive criteria (frozen)

**Success (promising — justifies an adversarial-checks pass, NOT yet
promotion or executable conversion)**:
(a) COMBINED shows a CI-decisive positive mean forward return at h5 in
ALL THREE splits, no sign reversal, AND
(b) COMBINED's out-of-sample point estimate at h5 exceeds BOTH
SHORT_WEAKNESS_ALONE's and STRUCTURAL_STRENGTH_ALONE's own
out-of-sample point estimates (the incremental-information test, §8),
AND
(c) >=30 pooled observations in every split for COMBINED.

**Failure (REJECTED)**:
- A sign reversal in COMBINED's mean return between any two splits, OR
- COMBINED's out-of-sample point estimate at h5 is NOT better than
  both alone-conditions' own out-of-sample point estimates (no
  incremental information — the interaction claim itself is false even
  if some positive return exists), OR
- The effect is too small to plausibly clear realistic costs
  (`CostModel.india_nse_intraday_2026()`, ~0.21% round-trip) even
  before considering execution mechanics.

**Inconclusive**:
- Below the 30-observation floor in any split for COMBINED
  (INSUFFICIENT_DATA), OR
- Directionally favorable and passing the incremental-information test,
  but out-of-sample CI straddles zero (underpowered, not reversed —
  matching the "dev/val decisive, oos underpowered" shape this registry
  has repeatedly and honestly recorded, e.g. `H_CONTEXT_MARKET_002`,
  `H_EXTREME_001`'s own WEAKNESS side).

## 10. What will NOT change after this is pre-registered

No threshold re-derivation after seeing any split's result (20th/80th
percentiles are fixed, not searched). No switching lookback windows (5
and 60 bars are fixed, matching the user's own "short-term" /
"medium/long-term" framing). No addition of `trailing_return_20` as a
third filter after the fact. No universe change. No jump to an
executable-strategy design without its own, separately pre-registered
follow-up hypothesis, mirroring `H_XSECT_001`->`H_XSECT_002` and
`H_MEANREV_003`->`H_MEANREV_004`'s own established two-step discipline
— and explicitly informed by this project's own repeated lesson that a
trend-continuation-calibrated STOP/TARGET exit has damaged every
reversal/mean-reversion-type signal converted so far
(`H_XSECT_002`, `H_MEANREV_004`, `H_EXIT_005`) — any executable
follow-up must account for this explicitly, not reuse the frozen
exit architecture blindly.

## 11. Adversarial checks (run ONLY if the raw COMBINED measurement passes §9's success criteria)

- Sign stability across dev/val/oos (already part of §9's own success
  gate, re-verified here across all six horizons, not just h5).
- Per-symbol breadth: no single symbol dominating the COMBINED
  condition's pooled sample (matching `H_MEANREV_003`'s own
  adversarial-check precedent — e.g. hits on a wide majority of the 32
  symbols, not a handful).
- Sector concentration: best-effort only, given
  `market_intelligence.nse_sector_map.NSE_SECTOR_MAP` covers just
  21/32 symbols (the same disclosed, honest partial-coverage caveat
  `H_XSECT_003` already carries) — not a blocking requirement.
- Year-by-year stability (matching `H_MEANREV_003`'s own era-stability
  check, directly answering BIGGEST RISKS item #2's standing concern
  about 5-year-window era-dependence, since this entry uses the full
  10-year history).
- Realistic transaction-cost deduction on the COMBINED condition's own
  raw out-of-sample mean at h5 (`CostModel.india_nse_intraday_2026()`,
  ~0.21% round-trip) — the raw-measurement check only, explicitly NOT
  assumed to guarantee an executable, stop/target-managed strategy
  survives (the `H_XSECT_002`/`004` lesson).
- Threshold sensitivity ONLY within this pre-registered formulation
  (i.e., disclosing how far the result would need to move to flip, not
  re-deriving new thresholds).
- Overlap/non-independence disclosure: forward-return observations
  pooled by `measure_condition` are overlapping (day T's and day T+1's
  5-bar/60-bar windows share almost all underlying bars) — the SAME
  accepted, shared methodological limitation every other
  `measure_condition`-based hypothesis in this registry already
  carries (`H_MEANREV_003`, `H_EXTREME_001`, `H_XSECT_003`, etc.), not
  a new problem introduced here, disclosed rather than silently
  ignored.

## 12. Data integrity

Reuses `build_universe_datasets(..., use_cache=True)` against the
existing 10-year NSE cache (the same cache every prior hypothesis this
segment has used) — cache freshness/depth already verified repeatedly
this session; no new data source, no risk of contaminating any
production/live-trading state (this is a read-only research script
against cached historical data only).

## 13. Scope note — paper-trading/live-system boundary

This entry is pure historical-data research. It does not touch
`data/paper_trading.db`, `data/live_state.db`, `data/scheduler_runs.db`,
or any live/paper-execution code path. No broker execution changes. No
scheduler changes (see separate operational note in this segment's
final report regarding a scheduler restart credential issue, unrelated
to this hypothesis).

## 14. Reproducibility record

- Universe: `ORIGINAL_32_NSE_UNIVERSE`, all 32 built successfully. 10y daily.
- `development_end=2022-09-08`, `validation_end=2024-09-07` (shared calendar boundaries).
- Frozen thresholds, computed from pooled NSE development-period data: `WEAKNESS_THRESHOLD` (20th percentile of n=47,296 `trailing_return_5` observations) = **-2.5630%**; `STRENGTH_THRESHOLD` (80th percentile of n=45,536 `trailing_return_60` observations) = **+15.1840%**.

## 15. Results — INCONCLUSIVE: real incremental information at h5 OOS, but underpowered to a decisive verdict

Full evidence: `H_MOMENTUM_001` in `strategy/hypothesis_registry.py`.

**Primary horizon (h5), all four conditions:**

| Condition | Split | n | Mean | 95% CI |
|---|---|---|---|---|
| UNCONDITIONAL | development | 47456 | +0.36% | [+0.32%,+0.40%] |
| UNCONDITIONAL | validation | 15712 | +0.45% | [+0.40%,+0.50%] |
| UNCONDITIONAL | out-of-sample | 15832 | +0.00% | [-0.05%,+0.06%] |
| SHORT_WEAKNESS_ALONE | development | 9460 | +0.33% | [+0.22%,+0.43%] |
| SHORT_WEAKNESS_ALONE | validation | 2286 | +0.83% | [+0.69%,+0.98%] |
| SHORT_WEAKNESS_ALONE | out-of-sample | 2990 | +0.07% | [-0.06%,+0.20%] |
| STRUCTURAL_STRENGTH_ALONE | development | 9108 | +0.48% | [+0.39%,+0.56%] |
| STRUCTURAL_STRENGTH_ALONE | validation | 2908 | +0.14% | [+0.01%,+0.27%] |
| STRUCTURAL_STRENGTH_ALONE | out-of-sample | 1400 | **-0.22%** | **[-0.37%,-0.06%]** |
| COMBINED | development | 963 | **+1.01%** | **[+0.71%,+1.32%]** |
| COMBINED | validation | 276 | **+0.68%** | **[+0.23%,+1.13%]** |
| COMBINED | out-of-sample | 114 | +0.49% | [-0.13%,+1.11%] |

**§8's incremental-information test (frozen, out-of-sample, h5)**:
COMBINED's out-of-sample point estimate (+0.4895%) exceeds BOTH
SHORT_WEAKNESS_ALONE's (+0.0668%) and STRUCTURAL_STRENGTH_ALONE's
(-0.2162%) own out-of-sample point estimates — the test **passes**.
Long-horizon strength does appear to add real incremental information
beyond short-term weakness alone: on this same sample, buying
structural strength ALONE reverses to a decisive loss out-of-sample,
while requiring the short-term-weakness pullback alongside it
produces a positive (though not itself decisive) out-of-sample point
estimate.

**§9's success gate (frozen, CI-decisive positive in ALL THREE
splits) does NOT pass**: development and validation are both
CI-decisive positive, but out-of-sample's CI (`[-0.13%,+1.11%]`,
n=114) straddles zero. No sign reversal occurred (all three means are
positive), and the effect is not small relative to the ~0.21%
round-trip cost estimate on its point estimate — but with only 114
pooled out-of-sample observations the interval is too wide to call
decisive either way.

**Verdict: INCONCLUSIVE**, matching the pre-registration's own frozen
bucket exactly ("directionally favorable and passing the incremental-
information test, but out-of-sample CI straddles zero — underpowered,
not reversed"). Per §11, the adversarial-checks phase (year-by-year
stability, symbol concentration, cost deduction) is explicitly NOT run
— its own frozen gate (passing §9's success criteria) was not met, and
running it anyway would be exactly the kind of "keep testing until
something looks promising enough" pattern this project's discipline
forbids.

**A genuinely useful secondary finding, disclosed regardless of the
primary verdict**: `STRUCTURAL_STRENGTH_ALONE`'s own out-of-sample
result is CI-decisive NEGATIVE — a clean reversal from development's
CI-decisive positive result. This is now the THIRD independent
replication, via a THIRD distinct metric family, of this project's
long-standing finding that buying medium/long-term strength alone
fails out-of-sample on NSE (`H_RELSTRENGTH_001`'s `relative_strength_20`
vs. benchmark, `H_EXTREME_001`'s `trailing_return_5` 95th-percentile
tail, and now this entry's `trailing_return_60` 80th-percentile tail).
`SHORT_WEAKNESS_ALONE`'s own out-of-sample result, by contrast, is
underpowered-not-reversed — the same shape seen repeatedly elsewhere
in this registry for weakness-only conditions
(`H_EXTREME_001`'s own `EXTREME_WEAKNESS` side).

**What remains open**: whether COMBINED would clear the CI-decisive
bar with more out-of-sample data (n=114 is the binding constraint, not
a reversed sign) is a genuine, real question — not pursued further in
this run. If revisited, it would need its own justification (e.g. more
elapsed calendar time widening the out-of-sample window under the same
frozen thresholds) rather than a retry on the same data with adjusted
percentiles.
