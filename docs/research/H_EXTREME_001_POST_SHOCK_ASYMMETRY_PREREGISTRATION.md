# H_EXTREME_001 — Post-Shock Move Asymmetry, Pre-Registration

Written and frozen **before** any experiment code runs. Per this
project's own multiple-testing discipline: the metric, thresholds,
universe, splits, and success/failure criteria are fixed here; none
may change after seeing results.

## 1. Research direction and question

Per the user's own explicit next-direction guidance (priority order:
extreme-move/post-shock behavior, then multi-horizon momentum
interaction, then passive evidence accumulation, then microstructure
only if data supports it) and this project's own conclusion that the
exit-architecture thread has reached three consecutive rejections and
should be set aside for a genuinely new hypothesis family.

**Question**: does NSE show a real, forward-return asymmetry following
an EXTREME single-window price move (5-day cumulative return in the
tails of its own distribution) — and is that asymmetry the same shape
(bounce after weakness) the project's own 68-condition sweep already
found on **US** data (`H_MEANREV_002`), or does NSE behave differently?
Tested for **both** extreme weakness and extreme strength, to directly
answer the "asymmetric situations" framing the user named — not
assumed one-sided.

**Explicitly distinct from prior mean-reversion work in this
registry**: `H_MEANREV_001`/`003`/`004` all condition on
`zscore_close_20`, a *standardized* deviation from a 20-bar rolling
mean. This entry conditions on `trailing_return_5`, a *raw magnitude*
cumulative return — a genuinely different metric family (percentile-
of-distribution, not standard-deviations-from-mean), matching
`H_MEANREV_002`'s own already-validated (on US data) approach rather
than reusing the zscore family the exit-architecture thread already
exhausted three times.

## 2. Audit — what already exists (verified against the registry, not assumed)

`grep` across `strategy/hypothesis_registry.py` for
extreme-move/post-shock/shock/large-move terminology surfaces only
`H_GAP_001`-`003` (overnight gap fade, a **different** mechanism —
the gap between previous close and today's open, already REJECTED —
not a multi-day cumulative extreme move) and `H_MEANREV_002` itself
(US-only, weakness-only). No hypothesis has tested `trailing_return_5`
percentile extremes on NSE, and none has tested the strength side at
all. `quant_research/us_weakness_reversal_signal.py`'s own module
docstring is the direct precedent and methodology template: a
threshold **frozen from development-period data only**, never
refit — reused here, computed fresh for NSE (not reusing the
US-specific `-0.053477` value, which has no reason to apply to a
different market).

## 3. Metric and thresholds (frozen)

`trailing_return_5 = close.pct_change(5)` — already computed, zero new
code, via `quant_research.cross_sectional.add_lookback_return_columns`
(the identical formula `H_MEANREV_002`'s own inline calculation uses).

Thresholds: the 5th percentile (extreme **weakness**) and 95th
percentile (extreme **strength**) of the **NSE-pooled, development-
period-only** `trailing_return_5` distribution — computed once, from
real data, before any validation/out-of-sample bar is examined, and
frozen from that point forward. Not the US-specific value. Not
re-derived after seeing any split's own result.

## 4. Universe and data (frozen)

Full original 32-symbol NSE universe
(`quant_research.universe_expansion.ORIGINAL_32_NSE_UNIVERSE`) — this
project's own established default, not the 208-symbol expansion. 10
years daily, matching every `H_XSECT_00x`/`H_MEANREV_00x` entry.

## 5. Splits and horizons (frozen)

`backtesting.splits.split_periods` 60/20/20, matching every prior
entry. Horizons: `quant_research.market_behavior.FORWARD_HORIZONS`
= (1, 2, 3, 5, 10, 20) bars, the project's own standard set — h=5 is
named as the *primary* horizon of interest (the one horizon that
survived Bonferroni correction in the original US sweep this
methodology is modeled on), but all six are reported, not
cherry-picked after the fact.

## 6. Experiment design

Pure measurement first — matching this project's own established,
hard-won two-phase workflow (raw measurement, then only if promising,
an executable-strategy conversion as its own separately pre-registered
hypothesis; never build the strategy first). Reuses `quant_research.
market_behavior.build_universe_datasets`/`measure_condition` (via
`market_filter="NSE"`) completely unchanged — the same machinery every
`H_CONTEXT_*`/`H_VOL_001`/`H_MEANREV_003` measurement step already
used. Two condition_fns: `EXTREME_WEAKNESS` (`trailing_return_5` below
the frozen 5th percentile) and `EXTREME_STRENGTH` (above the frozen
95th percentile), each measured independently across development,
validation, and out-of-sample.

## 7. Success / failure criteria (frozen)

**Success (for either side)**: a CI-decisive forward return, same sign
across development, validation, AND out-of-sample — no reversal in any
split — matching the exact bar every hypothesis in this registry is
held to.

**Failure**: sign reversal between any two splits, no split reaching
decisiveness, or an effect too small to plausibly clear realistic
costs (`CostModel.india_nse_intraday_2026()`, ~0.21% round-trip) even
before considering execution mechanics.

**Asymmetry read (the user's own explicit interest, reported
regardless of whether either side individually succeeds)**: do
weakness and strength show materially different magnitude/
decisiveness/direction? A real asymmetry is itself informative evidence
even if neither side alone clears the promotion-relevant bar.

## 8. What will NOT change after this is pre-registered

No threshold re-derivation after seeing any split's result. No
switching to a different lookback window (5 days is fixed, matching
`H_MEANREV_002`'s own already-validated choice, not searched). No
universe change. No jump to an executable-strategy design without its
own, separately pre-registered follow-up hypothesis — mirroring
`H_XSECT_001`→`H_XSECT_002` and `H_MEANREV_003`→`H_MEANREV_004`'s own
established two-step discipline.

## 9. Adversarial checks (if either side looks promising)

Symbol concentration (no single name dominating the pooled sample),
cost-sensitivity margin on the raw-measurement mean, and — given this
project's own repeated `H_CONTEXT_MARKET_005`/`H_XSECT_006` lesson
about era- and universe-dependence — an explicit note that neither
check is performed here by default; both remain open, disclosed
follow-ups if this entry's own raw measurement is promising enough to
warrant them.

## 10. Reproducibility record (filled in at execution time)

To be completed after the experiment runs: the exact frozen threshold
values (5th/95th percentile, computed from real NSE development data),
sample counts per split, and the full six-horizon result matrix for
both sides.
