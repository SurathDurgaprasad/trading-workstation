# Phase B — F_CONTEXT Regime Investigation: Summary and Decision

Executed per the user's own detailed B1-B5 mission structure (2026-09-21), immediately following
Phase A's own documented stop (`PHASE_A_POINT_IN_TIME_UNIVERSE.md`).

## What was done

- **B1**: froze the research question in writing, before any result was computed —
  `docs/research/H_CONTEXT_MARKET_006_VOLATILITY_REGIME_PREREGISTRATION.md`.
- **B2**: selected a SMALL, single, pre-justified regime variable — NIFTY's own realized-volatility
  regime, via already-existing, already-tested project infrastructure
  (`quant_research/context_experiments.py::build_benchmark_volatility_series`, wrapping
  `backtesting/regime.py::classify_volatility_at`, unmodified defaults). India VIX regime was
  identified as an available, reasonable alternative and explicitly NOT tested, to keep the set
  small and avoid after-the-fact "test several, report the best one" selection.
- **B3**: the preregistration fixed the exact condition (`H_CONTEXT_MARKET_002`'s own, byte-for-byte
  unchanged), universe (`ORIGINAL_32_NSE_UNIVERSE`, unchanged), splits (the same 10-year
  development/validation/out-of-sample partition `H_CONTEXT_MARKET_005` used), horizons (h5/h10,
  h10 primary), minimum sample floor (30), and a four-outcome decision rule — all before running
  anything.
- **B4**: executed `audit/edge_feasibility/scripts/h_context_market_006_volatility_regime.py`. The
  unconditioned control cross-checked EXACTLY against `H_CONTEXT_MARKET_005`'s own already-recorded
  numbers (validity confirmed). The bucketed result: `LOW_VOLATILITY` is structurally empty in
  every split (a real, disclosed, mechanical near-exclusivity between "NIFTY trending down" and
  "NIFTY in a low-volatility regime," not a gap); the dominant, best-powered `NORMAL_VOLATILITY`
  bucket reproduces the control's own exact era-instability pattern (negative development, positive
  validation/out-of-sample) essentially unchanged; `HIGH_VOLATILITY`, where powered, points AWAY
  from a stabilizing explanation (more negative in development, flat/non-decisive in out-of-sample).
- **B5**: out-of-sample was already one of the three tested splits (not a separate held-out step) —
  it did not show a stabilizing pattern in either powered bucket, so per the user's own "if OOS
  fails, close the hypothesis" instruction, this specific explanatory hypothesis is closed.

## Result

**NIFTY's own realized-volatility regime does NOT explain F_CONTEXT's era sign reversal.**
`H_CONTEXT_MARKET_006` added to the registry as `REJECTED` (the explanatory mechanism, not the
underlying `H_CONTEXT_MARKET_002/004/005` findings themselves, which are left unmodified per the
project's own no-retroactive-rewrite rule). Full results: `H_CONTEXT_MARKET_006_RESULTS.md`.

## Decision: no further regime variable tested this session

India VIX regime remains a real, available, already-built candidate for a future, separately
-preregistered follow-up — a human resourcing/priority decision, not something this session pivots
to automatically. Per the mission's own Phase B scope (test a SMALL, pre-declared set, not
"iterate through regime variables until one works") and per Phase C's own explicit "do not produce
a new hypothesis merely to avoid a null result" instruction, Phase B concludes here with one clean,
negative, well-evidenced result rather than continuing to search for a regime variable that
"rescues" F_CONTEXT.

## FACT / INFERENCE / ASSUMPTION / LIMITATION / DECISION

- **FACT**: the dominant NIFTY-volatility bucket (NORMAL_VOLATILITY, ~90% of observations in every
  split) reproduces H_CONTEXT_MARKET_005's own exact era-instability pattern unchanged.
- **FACT**: the LOW_VOLATILITY bucket is empty (n=0) in all three splits, a structural consequence
  of testing this variable inside an already-trend-conditioned population.
- **INFERENCE**: F_CONTEXT's era instability is more consistent with genuine nonstationarity than
  with a volatility-regime-dependent mechanism.
- **LIMITATION**: only one of several plausible regime variables was tested (by design, per B2's own
  small-set constraint) — a different, untested variable (e.g. India VIX, breadth) could in
  principle still explain the instability; this entry does not rule that out, only this one
  variable.
- **DECISION**: proceeding to Phase C (final research classification) with both Phase A (point-in
  -time universe: material gaps, replay not executed) and Phase B (volatility-regime explanation:
  rejected) now complete.
