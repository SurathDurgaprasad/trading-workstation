# DERIV_002 — Results: NIFTY Futures OI Change Adds No Meaningful Incremental Information

Executed exactly per
`docs/research/DERIV_002_FUTURES_OI_CHANGE_INFORMATION_CONTENT_PREREGISTRATION.md`, no deviation.
Script: `audit/derivatives_research/scripts/deriv_002_futures_oi_change_information_content.py`.

## Data

Same NIFTY futures series and same spot/OHLCV baseline as DERIV_001 (2,554 futures bars, 1,792
usable merged rows, development n=1,069 / validation n=363 / out_of_sample n=360 — identical splits,
only the augmented feature differs).

## Primary result

| Split | Baseline AUC | Augmented AUC | ΔAUC | Baseline Brier | Augmented Brier | ΔBrier |
|---|---:|---:|---:|---:|---:|---:|
| validation | 0.4910 | 0.4919 | +0.0009 | 0.2269 | 0.2269 | 0.0000 |
| out_of_sample | 0.5299 | 0.5282 | **-0.0016** | 0.2747 | 0.2747 | 0.0000 |

**A weaker, and on out-of-sample actually NEGATIVE, result than DERIV_001.** Adding
`futures_oi_change_pct` does not merely fail to help — on out-of-sample it very slightly hurts
(ΔAUC = -0.0016), and Brier score does not improve on either split (both effectively unchanged, 0.0000
at 4 decimal places). This is a cleaner, more unambiguous rejection than DERIV_001's own
near-zero-but-technically-positive result.

## Verdict, against the pre-registered decision rule (§5, identical structure to DERIV_001 §9)

- Validation ΔAUC ≥ 0.02: **False** (+0.0009).
- Out-of-sample ΔAUC ≥ 0.02: **False** (-0.0016).
- Brier does not worsen on either split: **False** (flat, not improved — the rule's own "does not
  worsen" bar is technically met since neither split's Brier score gets WORSE either, but there is
  no genuine improvement to report, unlike DERIV_001's own trivial-but-real improvement).

**VERDICT: NO MEANINGFUL INCREMENTAL INFORMATION.**

## Family-size context (Phase 10)

This is entry #2 of the newly-tracked derivatives research family. A `family_size=2` Bonferroni
correction (z=2.2414 vs. uncorrected 1.96) is disclosed for context — not a re-decision, since this
entry's own decision rule used a fixed, pre-registered effect-size threshold (ΔAUC ≥ 0.02), not a
p-value subject to correction. Both entries fail even the UNCORRECTED threshold by a wide margin, so
the correction does not change either verdict.

## Decision, per this entry's own preregistration

Per `DERIV_002`'s own explicit preregistration: **"This is the last derivatives-information-content
test in this initial pass... no third variant... will be tested automatically regardless of this
entry's own outcome."** Two of two pre-registered, economically-motivated, genuinely distinct
derivatives information families (futures basis, futures OI change) have now been tested and both
decisively rejected. Per the mission's own explicit Phase 12 stop-condition #3 ("derivatives
variables provide no meaningful incremental information") and its own explicit "do not automatically
test dozens of alternatives" instruction, **this triggers a stop of the information-content testing
phase.** Phase 7 (preregistered trading test) does not apply — it was explicitly gated behind Phase 6
finding meaningful incremental information, which did not occur. See
`PHASE10_12_DERIVATIVES_FAMILY_AND_STOP_CONDITIONS.md` for the full, formal accounting.
