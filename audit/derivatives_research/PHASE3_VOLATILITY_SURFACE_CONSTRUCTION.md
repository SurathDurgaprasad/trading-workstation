# Phase 3 — Volatility-Surface Construction

`quant_research/iv_surface.py` built (22 tests, all passing, `tests/test_iv_surface.py`) —
`compute_atm_iv_level` and `compute_put_call_iv_skew`, both with the exact temporal/contract
-selection rules documented in the module's own docstrings (timestamp, expiry/strike selection,
no-interpolation guarantee, missing-strike handling, zero-volume/stale-observation handling, units,
normalization — each specified per-function, matching the mission's own required list item-by-item).

## Scoping decision: two features, not three

Per the mission's own "do not combine into a complex model initially" and (from the prior pass's own
established discipline) "do not test all possible combinations":

- **Primary: ATM implied-volatility level.** The simplest, most directly liquid (0% zero-volume in
  Phase 1's own real sample), single-strike, single-expiry-leg feature — lowest data-quality risk of
  the three candidates named in the mission's own list.
- **One pre-declared backup: put/call IV asymmetry** (ATM PUT IV − ATM CALL IV). Chosen over
  strike-based skew (ATM+1 vs. ATM−1) because it requires only ONE strike (both option types at the
  SAME strike, already confirmed in Phase 1 to return matching strikes), not two — marginally
  simpler and lower-risk than a genuine cross-strike skew, while still directly answering the
  mission's own explicitly-named "call/put IV asymmetry" family. This mirrors the prior derivatives
  pass's own precedent exactly (DERIV_001 primary, DERIV_002 the one pre-declared, explicitly-named
  backup, then stop).
- **Explicitly NOT built**: strike-based skew (ATM+1/ATM−1) and expiry term structure (next vs. far).
  Both are real, data-available (Phase 1 confirmed the raw strikes/expiries resolve correctly), but
  adding a third and fourth feature immediately would be exactly the "test dozens of variants"
  pattern this mission's own instructions repeatedly prohibit. If the two features actually built
  here both fail Phase 6's own decision gate, per the mission's own explicit instruction ("do not
  test another IV threshold, another strike, another expiry... the point of this mission is to
  determine whether the information source is useful, not to optimize it indefinitely"), these two
  deferred candidates are NOT tested as a fallback — the research program closes instead.

## No future information (verified by construction, not merely asserted)

Both functions operate on an already-ordered `list[OptionRollingBar]` and compute each output value
using ONLY that bar's own reading (`compute_atm_iv_level`) or a same-timestamp pair
(`compute_put_call_iv_skew`) — never a later bar. `flag_volume_artifacts`'s own trailing-median
window uses strictly `bars[i - WINDOW : i]` (bars strictly BEFORE `i`), never bars at or after `i` —
directly tested (`test_flag_only_uses_prior_bars_never_future_ones`): appending a future artifact
bar to a series does not change an earlier bar's own flag.

## Real, quantitative guard against Phase 1's own found defect

`flag_volume_artifacts` directly operationalizes the exact anomaly Phase 1 found empirically (two
near-expiry bars with volume ~1,000x every other bar in the same series): any bar whose own volume
exceeds 20x the trailing 10-bar median is excluded. `is_plausible_iv` directly operationalizes the
other half of the same finding (IV readings of 0.0 and 0.4 co-occurring with the volume anomaly): any
IV below 3.0 (percent) is excluded. Neither threshold was tuned against a predictive-return result —
both were fixed from the RAW DATA'S OWN observed defect pattern, before any prediction target was
touched (Phase 2's own frozen rule, implemented unchanged here).
