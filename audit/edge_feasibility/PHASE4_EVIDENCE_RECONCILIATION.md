# Phase 4 — Full Mean-Reversion Evidence Reconciliation (H_MEANREV_009 through 013)

No experiments were rerun to reproduce known numbers (reproducibility was already independently
tested this session via H_MEANREV_012's own control and H_MEANREV_013's own cross-check — both
confirmed reproducible in substance, per Phase 3's W/X finding on `period=10y` drift). This table
consolidates already-verified evidence, citing sources, not re-deriving them.

## Consolidated evidence table

| Hyp | Signal | Universe | Split | n | Gross mean | Net mean (CI) | Win rate | Sizing | Portfolio | Survivorship | MT status | Verdict |
|---|---|---|---|---:|---:|---|---:|---|---|---|---|---|
| H_MEANREV_009 | `_oversold_2std_relative_weak`, h10 exit, wide stop (20xATR) | COMBINED 206 | dev | 1118 | +0.56% | -8.81% [-9.41,-8.21] | 14.1% | fixed-fractional (0.5% risk), fixed brokerage | single-position | current-F&O, undisclosed at the time | local only | REJECTED (NEGATIVE) |
| | | | val | 382 | +1.97% | -5.29% [-6.01,-4.57] | 21.2% | " | " | " | " | " |
| | | | oos | 370 | +1.42% | -5.81% [-6.49,-5.12] | 18.1% | " | " | " | " | " |
| H_MEANREV_010 Cand.2 | same signal/exit | COMBINED | dev | 2897 | +0.18% | +0.08% [-0.27,+0.44] | n/a | fixed-notional, 100% capital/position | single-position, unrealistic concentration | undisclosed at the time | local only | INCONCLUSIVE (STATISTICALLY_MEANINGLESS dev) |
| | | | val | 688 | +1.61% | **+1.51% [+0.94,+2.08]** | n/a | " | " | " | " | POSITIVE_PERFORMANCE, CI-decisive |
| | | | oos | 840 | +1.08% | **+0.98% [+0.52,+1.44]** | n/a | " | " | " | " | POSITIVE_PERFORMANCE, CI-decisive |
| H_MEANREV_011 | same | COMBINED | dev | 555 | +43460.67(₹) | +0.10% [-0.64,+0.84] | ~50.1% | fixed-notional, 4-slot/25%-cap portfolio | realistic, 82-93% capacity-rejected | undisclosed at the time | local only | REJECTED (mixed sign, not CI-decisive) |
| | | | val | 111 | -7852.26(₹) | -0.51% [-2.05,+1.02] | ~42.3% | " | " | " | " | " |
| | | | oos | 105 | -4789.98(₹) | -0.42% [-1.80,+0.96] | ~48.6% | " | " | " | " | " |
| H_MEANREV_012 (ranked ctrl) | same, zscore-ranked tie-break | COMBINED | dev | 567 | +66732.34(₹) | +0.26% | 49.0% | same portfolio | same, tie-break replaced | undisclosed at the time | local only | REJECTED, ranking made val WORSE |
| | | | val | 101 | -22473.73(₹) | -1.13% | 34.6% | " | " | " | " | " |
| | | | oos | 104 | -5349.05(₹) | -0.46% | 40.4% | " | " | " | " | " |
| H_MEANREV_013 (all candidates, cluster=10+) | same, ALL priced independently regardless of acceptance | COMBINED (this run: 206/208, minor rolling-window count drift vs. above, see Phase 3 W/X) | dev | 3830 | n/a | -0.23% [-0.57,+0.12] | n/a | fixed-notional, independent pricing | n/a (measurement, not a portfolio) | **quantified this session**: accepted trades 14.7%/count, 140.8%/net-return-share from ORIGINAL-32 | local only | STATISTICALLY_MEANINGLESS |
| | | | val | 805 | n/a | **+2.60% [+2.00,+3.19]** | n/a | " | " | " | " | POSITIVE_PERFORMANCE |
| | | | oos | 287 | n/a | **+2.63% [+1.88,+3.37]** | n/a | " | " | " | " | POSITIVE_PERFORMANCE |
| H_MEANREV_013 (cluster=1, lowest) | same | COMBINED | val | 63 | n/a | **-3.59% [-5.69,-1.48]** | n/a | " | " | " | " | NEGATIVE_PERFORMANCE |

Full per-split, per-bin detail: `H_MEANREV_013_RESULTS.md`/`.csv` (this session).

## Answers to Phase 4's six required questions

**1. Is H_MEANREV_010's positive validation/OOS result still statistically interesting after
correcting for known research limitations?**
Yes, as a raw statistical fact it remains real: CI-decisive positive net returns after realistic
percentage costs, in 2 of 3 splits, at fixed-notional single-position sizing. It is NOT, on its own,
evidence of a deployable edge — see Q2-Q5.

**2. How much of the result depends on the historical universe?**
Materially, but not entirely. The survivorship-exposure measurement this session (H_MEANREV_013)
found accepted-trade net return is disproportionately carried by the ORIGINAL-32 (more
point-in-time-defensible) subset (140.8% of summed net return from only 14.7% of trade count) —
meaning the EXPANDED-ONLY 176-symbol group, the portion most exposed to current-F&O-eligibility
survivorship bias, is a net DRAG on the portfolio-level result, not its source. This is a mixed
signal: it means the CORE positive effect is not manufactured purely by survivorship-biased names,
but the true magnitude on a genuine point-in-time universe cannot be stated with confidence without
implementing Phase 2's deferred universe-reconstruction work.

**3. How much depends on single-position concentration?**
Substantially. H_MEANREV_010 Candidate 2's own single-position, 100%-capital design carried a
-65%-of-total-capital worst trade (H_MEANREV_011's own already-recorded comparison). The realistic
4-position portfolio (H_MEANREV_011) reduced that tail to -9.68% of total capital but also
collapsed the statistically-decisive positive result into a statistically-meaningless mixed one.
**The positive validation/OOS finding does NOT survive the transition to realistic concentration
limits as a clean, confident result** — it becomes ambiguous, not simply "smaller but still
positive."

**4. How much depends on fixed-notional sizing?**
This is the ONE dimension directly, controlled-experiment-tested this session (H_MEANREV_010
Candidate 3, the zero-fixed-fee diagnostic): sizing itself (fixed-notional vs. the original
fixed-fractional) is not the source of the original H_MEANREV_009 failure — the FIXED BROKERAGE
component specifically was (₹20/fill on tiny fractional-sized positions). Once sizing was
corrected to fixed-notional at a meaningful capital scale, the underlying gross signal reasserted
itself cleanly. Fixed-notional sizing is therefore a NECESSARY correction (H_MEANREV_009's own
sizing was a genuine methodological defect), not an artificial inflation.

**5. Does realistic portfolio construction destroy the effect?**
Based on THIS specific, pre-registered, non-retuned 4-slot design: **yes, in the sense that it
destroys the STATISTICAL CONFIDENCE of the result**, though it does not prove the underlying
signal is fake — H_MEANREV_011's own point estimates remain mixed-sign, not confidently negative.
Neither of the two most plausible explanations for why (signal-strength selection, H_MEANREV_012;
candidate clustering, H_MEANREV_013) was confirmed as the mechanism. The honest answer is: **this
specific portfolio-construction approach cannot currently demonstrate that the effect survives
realistic implementation, and cannot demonstrate that it doesn't** — underpowered, not
disconfirming.

**6. Is there any defensible path from the observed effect to a tradable portfolio?**
Not through further portfolio-construction retuning on the CURRENT dataset — per the user's own
explicit instruction, two mechanisms have already been ruled out (selection rule, clustering), and
retuning the concurrency cap or capital allocation without a new, economically-motivated hypothesis
would be exactly the curve-fitting risk repeatedly flagged. **The one still-open, defensible path
is resolving the survivorship dependency (Phase 2's PARTIALLY_AVAILABLE finding) before any further
portfolio experiment** — since the current universe's own composition is a real, unresolved
confound on top of an already-ambiguous portfolio result, testing further portfolio variants on
this same data would not meaningfully advance the question.

## FACT / INFERENCE / ASSUMPTION / LIMITATION / DECISION

- **FACT**: H_MEANREV_010 Candidate 2 showed CI-decisive positive net returns in validation and OOS.
- **FACT**: H_MEANREV_011's realistic portfolio construction produced a mixed-sign, statistically
  meaningless result in all three splits.
- **FACT**: Neither signal-strength ranking (H_MEANREV_012) nor candidate clustering
  (H_MEANREV_013) explains the divergence between single-position and portfolio-level results.
- **FACT**: accepted-trade net return is disproportionately carried by the ORIGINAL-32 subset, not
  the EXPANDED-ONLY (more survivorship-exposed) subset.
- **INFERENCE**: the mean-reversion signal family (`_oversold_2std_relative_weak`) likely reflects
  a real, if modest, gross statistical regularity in NSE price behavior — the magnitude and
  tradability of that regularity as an actual portfolio strategy remain unresolved.
- **ASSUMPTION**: `period="10y"` rolling-window experiments are treated as approximately, not
  exactly, reproducible across different run dates (Phase 3 finding).
- **LIMITATION**: point-in-time universe membership is unresolved; multiple-testing correction is
  local-only, not registry-wide (addressed further in Phase 8).
- **DECISION**: per Phase 2's PARTIALLY_AVAILABLE outcome and this phase's own Q6 answer, no
  further H_MEANREV portfolio-construction variant will be tested this session. Proceeding to
  Phase 8 (registry-level multiple-testing/research-bias audit) before any new hypothesis family
  is considered, per the mission's own stated sequencing and the "no further shotgun testing"
  instruction.
