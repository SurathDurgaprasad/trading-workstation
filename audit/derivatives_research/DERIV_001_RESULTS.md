# DERIV_001 — Results: NIFTY Futures Basis Adds No Meaningful Incremental Information

Executed exactly per
`docs/research/DERIV_001_FUTURES_BASIS_INFORMATION_CONTENT_PREREGISTRATION.md`, no deviation.
Script: `audit/derivatives_research/scripts/deriv_001_futures_basis_information_content.py`.

## Data

NIFTY futures: 2,554 real daily bars (2015-12-31 to 2026-09-17) via Dhan's `/charts/historical`
(`FUTIDX`, relative `expiryCode=0`, already-continuous across rolls — see Phase 1's addendum
finding). NIFTY spot: 2,466 bars via the existing `^NSEI` pipeline. Merged (inner join, both series
required): 1,815 bars, 2016-09-08 to 2026-09-08; 1,792 usable after dropping rows with any NaN
feature/target (indicator warm-up). Split: development n=1,069, validation n=363, out_of_sample
n=360 — all three comfortably exceed the pre-registered minimum (100/split).

## Primary result — ROC-AUC and Brier score, baseline vs. augmented

| Split | Baseline AUC | Augmented AUC | ΔAUC | Baseline Brier | Augmented Brier | ΔBrier |
|---|---:|---:|---:|---:|---:|---:|
| validation | 0.4910 | 0.4934 | **+0.0024** | 0.2269 | 0.2267 | -0.0003 |
| out_of_sample | 0.5299 | 0.5325 | **+0.0026** | 0.2747 | 0.2744 | -0.0002 |

Both ΔAUC values are roughly **8x smaller** than the pre-registered 0.02 threshold for "meaningful
incremental information." The Brier-score improvements are negligible (both ~0.0003, effectively
noise-level on this sample size). Genuinely note-worthy on its own: even the BASELINE (OHLCV-only)
model's AUC is barely above 0.50 (random) in both splits — consistent with everything already
established by the closed OHLCV research (NO DEMONSTRATED EDGE) — futures basis was tested as an
addition to an already-weak baseline, not a strong one.

## Calibration (augmented model, out-of-sample, predicted-probability deciles)

| Decile | Mean predicted | Realized frequency | n |
|---:|---:|---:|---:|
| 0 (lowest) | 0.537 | 0.389 | 36 |
| 1 | 0.567 | 0.417 | 36 |
| 2 | 0.579 | 0.417 | 36 |
| 3 | 0.588 | 0.389 | 36 |
| 4 | 0.597 | 0.528 | 36 |
| 5 | 0.606 | 0.472 | 36 |
| 6 | 0.618 | **0.222** | 36 |
| 7 | 0.628 | 0.500 | 36 |
| 8 | 0.641 | 0.389 | 36 |
| 9 (highest) | 0.670 | 0.583 | 36 |

The model's own predicted probabilities are poorly calibrated and not cleanly monotonic against
realized frequency — decile 6 (a middling predicted probability) has the LOWEST realized frequency
of any decile, and the gap between the lowest and highest deciles' realized frequencies (0.389 to
0.583) is modest and noisy relative to what a genuinely informative model would show. This further
corroborates the AUC finding: whatever signal exists is very weak.

## Verdict, against the pre-registered decision rule (§9)

- Validation ΔAUC ≥ 0.02: **False** (+0.0024).
- Out-of-sample ΔAUC ≥ 0.02: **False** (+0.0026).
- Brier does not worsen on either split: True (both improve trivially).

**VERDICT: NO MEANINGFUL INCREMENTAL INFORMATION.** Per the mission's own explicit instruction, this
does not itself prove futures basis contains zero information whatsoever — it means the pre
-registered, economically-motivated threshold for a decision-relevant improvement was not met on
either split. Per the mission's own explicit stop-condition discipline ("if one avenue fails, do not
automatically test dozens of alternatives... record the failure"), **futures basis is closed as an
information family for NIFTY-level, h10, logistic-regression-based prediction.** This does not
retroactively affect Phase 3's own classification (futures basis remains genuinely Classification A
— historically usable, well-formed data — the DATA was real and clean; the INFORMATION CONTENT
question, a separate matter, is answered negative).

## FACT / INFERENCE / ASSUMPTION / LIMITATION / DECISION

- **FACT**: augmented-model ΔAUC is +0.0024 (validation) and +0.0026 (out-of-sample), both below the
  pre-registered 0.02 threshold.
- **FACT**: the baseline OHLCV model itself has AUC barely above 0.50 in both splits.
- **INFERENCE**: futures basis, at NIFTY-index level, h10 horizon, via a linear (logistic-regression)
  combination with the existing OHLCV feature set, does not provide economically meaningful
  incremental predictive information beyond what OHLCV technicals already capture (which is itself
  very little, consistent with the closed OHLCV research's own terminal conclusion).
- **ASSUMPTION**: a linear/logistic combination is an appropriate test of "incremental information" —
  a genuinely non-linear interaction (e.g., basis matters only in specific regimes) would not be
  detected by this design; not tested here, per the mission's own "prefer data validity over model
  complexity" instruction (a non-linear model was deliberately not used for a first information
  -content check).
- **LIMITATION**: single-underlying (NIFTY only), single-horizon-primary (h10), single-model-class
  (logistic regression) — a materially different design (individual stocks, other horizons, other
  model classes) was not tested and might behave differently; not pursued here, matching the
  mission's own "do not automatically test dozens of alternatives" instruction.
- **DECISION**: futures basis closed as an information family. Per the preregistration's own
  disclosed next candidate (OI change, explicitly named and deferred, not a new ad hoc choice),
  proceeding to consider ONE further, separately-preregistered entry (DERIV_002) for futures OI
  change — the last candidate before this specific research avenue would need to stop per the
  mission's own "do not test dozens" discipline.
