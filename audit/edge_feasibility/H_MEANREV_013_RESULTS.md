# H_MEANREV_013 — Results

Executed exactly per `H_MEANREV_013_CLUSTERING_PREREGISTRATION.md`, script at
`audit/edge_feasibility/scripts/h_meanrev_013_clustering.py`, full per-event output at
`audit/edge_feasibility/H_MEANREV_013_RESULTS.csv` (9,811 priceable candidate events). No
production file modified; fleet untouched throughout.

## Correctness checks (pass before interpreting results)

- **Cross-check against the real, unmodified `schedule_portfolio()`**: this script's own
  independently-replicated accept/reject labeling produced 791 accepted trades; the real,
  imported (not reimplemented) `schedule_portfolio()` call produced 791. **MATCH.**
- **Cross-split count vs. the registry's own cited H_MEANREV_011/012 numbers**: development
  accepted count matches exactly (555 vs. 555 cited). Validation (120 vs. 111 cited) and
  out-of-sample (116 vs. 105 cited) are each ~9-11 higher. **Explained, not a bug**: `period="10y"`
  is a rolling window ending "now" (2026-09-21), later than whenever H_MEANREV_011/012 were
  originally run — the window has shifted forward, picking up genuinely newer calendar data in
  the tail (validation/OOS) while development's own count is unaffected. Disclosed, not hidden.

## PRIMARY RESULT — the clustering hypothesis is NOT cleanly confirmed; the honest read is Outcome C (unstable)

| Split | bin=1 | bin=2 | bin=3-4 | bin=5-9 | bin=10+ |
|---|---:|---:|---:|---:|---:|
| development | **+1.25%** (POSITIVE, n=336) | +0.77% (POSITIVE, n=512) | +0.30% (meaningless, n=923) | +0.08% (meaningless, n=1673) | **-0.23%** (meaningless, n=3830) |
| validation | **-3.59%** (NEGATIVE, n=63) | -0.05% (meaningless, n=98) | +0.91% (meaningless, n=182) | +0.57% (meaningless, n=385) | **+2.60%** (POSITIVE, n=805) |
| out_of_sample | +0.09% (meaningless, n=66) | -0.77% (meaningless, n=90) | **-1.00%** (NEGATIVE, n=186) | +0.22% (meaningless, n=375) | **+2.63%** (POSITIVE, n=287) |

**Development, taken alone, shows exactly the pre-registered "Outcome A" pattern**: a
statistically clean, monotonic decline from low-clustering (+1.25% CI-decisively positive) to
high-clustering (-0.23%, though not itself CI-decisive). Read in isolation, this would look like
a clean confirmation of the clustering/correlation mechanism.

**Validation and out-of-sample do not reproduce this pattern — in their most statistically
decisive bins, they show the OPPOSITE direction**: validation's bin=1 (the LOWEST-clustering,
most "isolated-signal" bin) is the single worst result anywhere in the table
(-3.59%, CI-decisively NEGATIVE), while validation's bin=10+ (the HIGHEST-clustering bin) is
CI-decisively POSITIVE (+2.60%). Out-of-sample's bin=10+ is also CI-decisively positive (+2.63%),
while its bin=3-4 is CI-decisively negative (-1.00%) — no monotonic structure at all.

**Per the pre-registered decision rule (§6 of the preregistration, written before this analysis
ran)**: this is not "few positive, many negative" (Outcome A) and not "flat-or-positive
throughout" (Outcome B). It is **Outcome C: random/unstable/no consistent pattern across
splits.** Per that same pre-registered rule: **the clustering hypothesis is not supported by
this evidence.** The apparent clean pattern in development alone is exactly the kind of
in-sample-only structure the project's own dev/val/oos discipline exists to catch before it is
mistaken for a real, generalizable mechanism.

## ACCEPTED vs. REJECTED (capacity) — also unstable, does not independently rescue the finding

| Split | ACCEPTED mean (n) | REJECTED-capacity mean (n) |
|---|---|---|
| development | +0.10% meaningless (555) | **-1.01% NEGATIVE** (3279) |
| validation | -0.17% meaningless (120) | **+1.77% POSITIVE** (1253) |
| out_of_sample | -0.13% meaningless (116) | **+0.57%** (750) |

Development alone would suggest the portfolio scheduler is discarding the *better* candidates
(rejected underperforms accepted) — but validation and out-of-sample show rejected candidates
*outperforming* accepted ones, the opposite direction. This is the same instability as the
primary cluster-bin table, viewed from the accept/reject angle rather than the cluster-size
angle, and does not change the Outcome-C conclusion above.

## Survivorship-exposure quantification (measured, not fixed, per preregistration §7)

Accepted trades drawn from the ORIGINAL-32 (point-in-time-plausible, not current-F&O-eligibility-
dependent) universe: **14.7% of accepted trade count, but 140.8% of the summed net return** —
meaning the EXPANDED-ONLY 176-symbol group (the portion most directly exposed to the
current-membership survivorship concern) contributes a *net negative* share overall, and whatever
positive signal exists in the accepted-trade population is disproportionately carried by the
smaller, more defensible original universe. This is, if anything, mildly reassuring for the
survivorship question specifically (the positive contribution is not concentrated in the
more-exposed subset) — but it does not change the Outcome-C verdict above, since the primary
result is already "no consistent pattern," not "a positive pattern that might be survivorship-
inflated."

## Verdict, per the pre-registered rule

**H_MEANREV's clustering explanation for why the portfolio-constrained result diverges from the
single-position result is NOT SUPPORTED by this evidence.** Combined with `H_MEANREV_012`'s own
earlier finding (signal-strength ranking does not explain it either), **neither of the two most
plausible mechanisms for H_MEANREV_011's portfolio-level disappointment has survived direct
testing.** Per the user's own pre-specified Outcome-C guidance: *"H_MEANREV remains unresolved.
At that point, the right move may be dataset improvement, not another strategy variation."*

This does not reopen or rescue `H_MEANREV_010`'s single-position positive result (still real,
still cost-inclusive, still CI-decisive in 2 of 3 splits, still discounted by the already-disclosed
survivorship exposure) — it specifically closes off "the portfolio-construction problem has an
identifiable, fixable cause" as a productive next research direction using the CURRENT dataset.
Per the user's own explicit sequencing, the next defensible step is constructing a genuine
point-in-time-correct universe (removing the current-F&O-eligibility survivorship dependency)
before any further portfolio-construction experiment on this signal family — not a new
H_MEANREV_014 clustering variant, and not H57.
