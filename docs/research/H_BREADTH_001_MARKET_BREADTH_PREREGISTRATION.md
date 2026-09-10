# H_BREADTH_001 — Market Breadth (Cross-Sectional Participation), Pre-Registration

Written and frozen **before** any experiment code runs. Per this
project's own multiple-testing discipline: the metric, thresholds,
universe, splits, and success/failure criteria are fixed here; none
may change after seeing results.

## 1. Research direction and question

Per the mission's own explicit instruction to return to the hypothesis
registry, avoid renaming/re-parameterizing already-weak families
(buying strength alone, naive cross-sectional laggards, sector
rotation, calendar effects, executable mean-reversion variants,
global-to-India transmission, volatility contraction, stop-based exit
variants — all already tested), and prioritize Indian-market-specific
mechanisms not yet tested.

**Question**: does NSE market BREADTH — the fraction of the 32-symbol
universe individually classified `TRENDING_UP` on a given date, a
cross-sectional PARTICIPATION measure — predict NIFTY's (`^NSEI`) own
forward returns? And does breadth add INCREMENTAL information beyond
NIFTY's own index-level price-trend regime (already tested as a
context filter in `H_CONTEXT_MARKET_001`-`005`, but never as a
breadth/participation measure)?

**Economic thesis**: a market advance backed by broad participation
(many individual stocks independently trending up) is more durable
than one where the index rises while few constituents actually
participate (narrow breadth) — the classic technical-analysis
"divergence" thesis: a cap-weighted index can be propped up by a
handful of large names while breadth quietly deteriorates, a
historically-cited warning sign of fragility. This is mechanistically
DISTINCT from "is the index itself in an uptrend" (a single
index-level price/MA relationship) — breadth and index trend CAN
diverge, and that divergence is the entire object of this test.

## 2. Registry audit — what already exists (verified against the registry, not assumed)

`grep` for "breadth" across `strategy/hypothesis_registry.py` surfaces
exactly one hit (`H_CALENDAR_001`'s own use of the word to mean
"how many of the 32 symbols replicate a finding" — an unrelated sense
of the word, not market breadth/participation). No hypothesis has ever
tested cross-sectional participation breadth. The closest precedents,
read in full, are genuinely distinct:

- **`H_CONTEXT_MARKET_001`-`005`** condition a STOCK-level baseline BUY
  signal on NIFTY's own INDEX-level `trend_regime`/`volatility_regime`
  (a single classification of the index's own price history) — a
  different target variable (a stock's forward return conditional on
  market regime) and a different metric (index price trend, not
  universe participation).
- **`H_MEANREV_003`** gates a STOCK-level `zscore_close_20` weakness
  signal on the SAME NIFTY index-level `TRENDING_UP` regime — again
  index-level, not breadth.
- **`H_SECTOR_ROTATION_001`** ranks sectors' own cross-sectional
  momentum against each other — a relative-ranking mechanism among
  sectors, not a participation-count/breadth measure of the whole
  market.

None of these test whether the FRACTION of the universe independently
trending up predicts the INDEX's own forward return, or whether that
fraction diverges informatively from the index's own trend
classification. Confirmed genuinely novel.

## 3. Infrastructure audit — what is reused, what is new

- `backtesting.regime.classify_trend_at` (via
  `quant_research.market_behavior.build_symbol_dataset`) already
  computes a causal, per-bar `trend_regime`
  (TRENDING_UP/TRENDING_DOWN/SIDEWAYS/UNKNOWN) for every symbol in the
  32-symbol universe — confirmed present in `SymbolDataset.frame` for
  every symbol without any extra step. Zero new indicator/regime-
  classification code.
- `quant_research.context_experiments.build_benchmark_regime_series`
  already computes the SAME causal `trend_regime` for `^NSEI` itself —
  reused unchanged as the "simpler formulation" comparator (§7 below),
  the exact machinery `H_CONTEXT_MARKET_00x`/`H_MEANREV_003` already
  used for NIFTY's own regime.
- **New, small, genuinely needed**: a cross-sectional aggregation
  function (`quant_research/market_breadth.py`,
  `compute_universe_breadth_series`) that, for each date on the shared
  32-symbol calendar, computes `breadth_pct = (# symbols with
  trend_regime == TRENDING_UP) / (# symbols with a non-UNKNOWN
  trend_regime)` that date — a pure aggregation over ALREADY-COMPUTED
  per-symbol columns, inventing no new per-symbol indicator. This is
  the one piece of new production code this hypothesis needs, with its
  own targeted unit tests.
- `^NSEI`'s own 10-year cache confirmed present (2466 bars, verified
  via `cache-status` immediately before writing this pre-registration).

## 4. Metric and thresholds (frozen)

`BREADTH_PCT(date)` as defined in §3, computed across the full
`ORIGINAL_32_NSE_UNIVERSE`. Two conditions, thresholds frozen from the
**development-period-only** pooled `BREADTH_PCT` distribution (the
daily series itself, not per-symbol observations):

- **NARROW_BREADTH**: `BREADTH_PCT <= WEAKNESS_THRESHOLD` (20th
  percentile of development-period daily breadth values).
- **BROAD_BREADTH**: `BREADTH_PCT >= STRENGTH_THRESHOLD` (80th
  percentile of development-period daily breadth values).

20th/80th percentiles chosen (not 5th/95th) for the same reason as
`H_MOMENTUM_001`: this is a single DAILY series (not pooled across 32
symbols), so extreme-tail percentiles would leave very few dates per
split; a moderate quintile-style split preserves usable sample size
while still being economically meaningful ("bottom/top fifth of days
by participation," not an ultra-rare extreme).

## 5. Universe and data (frozen)

`ORIGINAL_32_NSE_UNIVERSE` for breadth computation. `^NSEI` (NIFTY 50)
as the sole forward-return TARGET — this is a market-level, not a
stock-level, hypothesis. 10 years daily for both.

## 6. Splits and horizons (frozen)

`shared_period_boundaries`-derived 60/20/20 development/validation/
out-of-sample split on the shared calendar (same convention as every
cross-sectional/multi-symbol entry this registry uses).
`FORWARD_HORIZONS = (1, 2, 3, 5, 10, 20)`, all six reported. **Primary
horizon: h10** — breadth/participation divergence is a market-
structure signal, plausibly slower-resolving than a single stock's
short-term mean-reversion signal; h10 is chosen a priori as a
reasonable middle horizon for this class of signal, not selected after
seeing any result. h5/h20 are named secondary horizons of particular
interest.

## 7. Experiment design and controls (frozen)

Three conditions measured against `^NSEI`'s own forward returns, per
split, per horizon, via `summarize_forward_returns` (reused unchanged
— pure statistics, no new code):

1. **UNCONDITIONAL** — `^NSEI`'s own full-period forward returns, no
   filter (the baseline).
2. **NARROW_BREADTH** — `^NSEI`'s forward returns on dates where
   `BREADTH_PCT <= WEAKNESS_THRESHOLD`.
3. **BROAD_BREADTH** — `^NSEI`'s forward returns on dates where
   `BREADTH_PCT >= STRENGTH_THRESHOLD`.

**Control / simpler-formulation comparison (Phase F, frozen)**: NIFTY's
own index-level `trend_regime` (via `build_benchmark_regime_series`,
unchanged) is the "relevant simpler formulation" this entry must beat.
If breadth's own effect (§8) is found, the entry is NOT successful
unless it also shows incremental value beyond NIFTY's own regime — see
§9 for the precise adversarial test, gated behind §8's own success
criterion.

Minimum sample size: **>=30 dates per split** for both NARROW_BREADTH
and BROAD_BREADTH — below this, INSUFFICIENT_DATA/INCONCLUSIVE, not a
forced verdict.

## 8. Success / failure / inconclusive criteria (frozen)

**Success (promising — justifies the adversarial/incremental-
information phase in §9, NOT promotion)**: at h10 (primary horizon),
NARROW_BREADTH's mean forward `^NSEI` return is LOWER than
BROAD_BREADTH's in ALL THREE splits (the "narrow rally is fragile"
direction), with no sign-order reversal (i.e., NARROW never exceeds
BROAD in mean return in any split), AND at least the out-of-sample
comparison is not attributable to pure noise (BROAD's OOS CI and
NARROW's OOS CI do not both sit on the same side of, and overlap
entirely with, each other in a way that makes the ordering
indistinguishable from chance — assessed qualitatively alongside the
numbers, not a single hard statistical test, disclosed either way).

**Failure (REJECTED)**: the NARROW < BROAD ordering reverses in any
split, OR neither condition's effect is distinguishable from the
UNCONDITIONAL baseline in any economically meaningful way, OR the
effect is too small to be of any plausible practical relevance even
before costs (this is an index-level, non-tradeable-as-is measurement,
so "costs" here means: is the gap large enough to matter at all,
tested loosely against `CostModel.india_nse_intraday_2026()`'s ~0.21%
round-trip as an order-of-magnitude reference, not because this raw
measurement is itself a trade).

**Inconclusive**: below the 30-date floor in any split for either
condition, or a directionally-favorable but not clearly distinguishable
result (the "underpowered, not reversed" shape this registry has
repeatedly and honestly recorded elsewhere).

## 9. Adversarial / incremental-information checks (run ONLY if §8's success criteria are met)

- **Incremental information beyond NIFTY's own trend regime (the
  central test)**: restrict to dates where NIFTY's OWN `trend_regime
  == TRENDING_UP` (i.e., the index itself already "looks fine"), and
  re-run the NARROW_BREADTH vs BROAD_BREADTH comparison WITHIN that
  subset only. If breadth no longer differentiates forward returns
  once NIFTY's own regime is already known, breadth adds nothing
  beyond the existing, already-tested index-trend signal, and this
  entry should be classified accordingly (a real but redundant
  finding, not a genuinely new source of information) — mirroring
  `H_MOMENTUM_001`'s own incremental-information framing.
- Year-by-year stability (does the effect hold across the full 10-year
  window, not concentrated in one regime/crisis period).
- Sign stability across all six horizons, not just h10.
- Whether the effect is concentrated around known market-stress
  episodes (a large fraction of NARROW_BREADTH days clustering in one
  or two calendar windows would undercut a "general phenomenon" claim)
  — the closest available proxy check to genuine regime-stability
  given this is a single-series (index-level) measurement.
- Overlap/non-independence disclosure: forward-return observations at
  different horizons for nearby dates are overlapping and
  autocorrelated (the SAME accepted, shared limitation already
  disclosed for every `measure_condition`-based entry in this
  registry), compounded here by `BREADTH_PCT` itself changing slowly
  day-to-day (persistent runs of NARROW or BROAD days are expected,
  not evidence of a stronger effect than the true sample size
  supports) — disclosed explicitly, not silently ignored.

## 10. What will NOT change after this is pre-registered

No threshold re-derivation after seeing any split's result (20th/80th
percentiles fixed). No switching the underlying trend classification
(reuses `backtesting.regime.classify_trend_at` exactly as every other
hypothesis in this registry already does — not re-tuned). No universe
change. No jump to an executable-strategy design (this is explicitly a
market-level raw measurement, not a stock-level trade signal — even a
positive raw result here would need a completely separate, newly
pre-registered design to become tradeable, since NIFTY itself is not
directly tradeable in this project's current execution infrastructure,
the same disclosed gap `H_CALENDAR_001`/`002` already found).

## 11. Data integrity and scope

Reuses `build_universe_datasets`/`build_symbol_dataset` against the
existing 10-year NSE cache (already verified fresh/deep for all 32
universe symbols and `^NSEI` earlier this session). Pure historical-
data research — does not touch `data/paper_trading.db`,
`data/live_state.db`, `data/scheduler_runs.db`, `data/predictions.db`,
or `data/direction_forecasts.db`. No broker execution changes. No
scheduler dependency (uses only cached historical data, not the live
Dhan feed).
