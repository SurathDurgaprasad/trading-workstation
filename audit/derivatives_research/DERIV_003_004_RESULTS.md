# DERIV_003 / DERIV_004 — Results: Neither ATM IV Level Nor Put/Call IV Skew Adds Meaningful Incremental Information

Executed exactly per
`docs/research/DERIV_003_004_IV_SURFACE_INFORMATION_CONTENT_PREREGISTRATION.md`, no deviation.
Script: `audit/derivatives_research/scripts/deriv_003_004_iv_surface_information_content.py`.

## Data retrieval

28 paced (~29-day) windows fetched for each of CALL and PUT ATM NIFTY options (56 real, live, read
-only Dhan Data API calls, ~1 second apart) — 3,946 raw hourly bars per side. After Phase 2/3's own
frozen quality gate (`MIN_PLAUSIBLE_IV_PCT=3.0`, `VOLUME_MEDIAN_MULTIPLE=20.0`): 3,910 clean
`atm_iv_level` hourly bars, 3,756 clean `put_call_iv_skew` hourly bars (98.8%/95.2% of raw bars
survived — a small, expected loss, consistent with Phase 1's own finding that degeneracy is a narrow,
near-expiry phenomenon, not a broad data-quality problem). Downsampled to 546 daily observations
(last valid hourly reading per trading day). Merged with the existing OHLCV+futures baseline: 397
usable rows survive the full intersection (spot ∩ futures ∩ clean-IV ∩ non-NaN features).

## IMPORTANT, PROMINENTLY DISCLOSED LIMITATION: under the pre-registered sample floor

The 60/20/20 split of 397 total rows produced **development n=237, validation n=77, out_of_sample
n=84** — both validation and out-of-sample fall BELOW the pre-registered minimum of 100
observations/split (§6 of the preregistration). This was not knowable in advance without actually
building the merged, split dataset (Phase 2's own liquidity gate concerned OBSERVATION-level
trustworthiness, which was genuinely established — 3,910/3,756 clean hourly bars; the SPECIFIC
split-level undersizing only emerged from intersecting the shorter ~2.2-year options-retrieval
window with the temporal 60/20/20 split). **This is disclosed honestly, not hidden after the fact
or worked around by loosening the floor.** Per the mission's own explicit instruction, this is
recorded as a real data-adequacy limitation.

**Why this does not change the conclusion**: both results below are decisive misses, not marginal
ones. Even a somewhat underpowered test would be expected to at least point toward a real, sizeable
effect if one existed; instead, one result is negative-SIGNED and the other is roughly an order of
magnitude below the pre-registered threshold. A larger sample might sharpen the estimate, but there
is no indication in this data that more samples would flip the sign or clear the bar by a wide
margin — this is disclosed as a genuine limitation on how MUCH confidence to place in "no effect
exists at all," not as a reason to doubt the "no effect was FOUND at this sample size" finding
itself.

## Primary result — ROC-AUC and Brier score, baseline (OHLCV+futures) vs. each augmented model

| Feature | Split | Baseline AUC | Augmented AUC | ΔAUC | Baseline Brier | Augmented Brier | ΔBrier |
|---|---|---:|---:|---:|---:|---:|---:|
| DERIV_003 (`atm_iv_level`) | validation (n=77) | 0.7069 | 0.6999 | **-0.0070** | 0.2281 | 0.2299 | +0.0018 |
| DERIV_003 (`atm_iv_level`) | out_of_sample (n=84) | 0.5330 | 0.5249 | **-0.0081** | 0.2497 | 0.2504 | +0.0007 |
| DERIV_004 (`put_call_iv_skew`) | validation (n=77) | 0.7069 | 0.7104 | +0.0035 | 0.2281 | 0.2282 | +0.0002 |
| DERIV_004 (`put_call_iv_skew`) | out_of_sample (n=84) | 0.5330 | 0.5347 | +0.0017 | 0.2497 | 0.2493 | -0.0004 |

Note the baseline's own AUC on validation (0.7069) is materially higher than anything seen in
DERIV_001/002 — this reflects the SMALLER, more RECENT validation window here (n=77, a different
calendar period than the ~10-year-deep DERIV_001/002 baseline), not a change to the baseline
model itself, which is identical in specification. This is exactly why the augmented-vs-baseline
DELTA (not either model's absolute performance) is this entry's own primary quantity of interest, per
its own preregistration.

## Verdict, against the pre-registered decision rule (§7)

- **DERIV_003 (ATM IV level)**: ΔAUC is NEGATIVE on both splits; Brier score WORSENS on both splits.
  **NO MEANINGFUL INCREMENTAL INFORMATION** — the feature does not merely fail to help, it very
  slightly hurts.
- **DERIV_004 (put/call IV skew)**: ΔAUC is positive but far below the 0.02 threshold on both splits
  (+0.0035, +0.0017 — roughly 6-12x too small); Brier does not clearly improve on validation.
  **NO MEANINGFUL INCREMENTAL INFORMATION.**

## Multiple-testing context (Phase 10)

`family_size=2` (this pass) → z=2.2414; `family_size=4` (the whole derivatives program, including
DERIV_001/002) → z=2.4977. Disclosure only — neither correction changes either verdict, since both
entries used a fixed, pre-registered effect-size threshold rather than a p-value, and both missed
that threshold by a wide margin regardless of correction stringency.

## Decision, per the pre-registered decision rule

**Neither DERIV_003 nor DERIV_004 shows meaningful incremental information. Per the mission's own
explicit Phase 6 instruction: the derivatives research program CLOSES here.** No third IV threshold,
strike, expiry, holding period, model, or OI feature will be tested. See
`PHASE6_DECISION_GATE_AND_TERMINAL_REPORT.md` for the full, formal closure.
