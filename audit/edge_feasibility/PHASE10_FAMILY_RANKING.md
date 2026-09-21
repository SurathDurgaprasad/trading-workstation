# Phase 10 — Ranking Remaining Hypothesis Families by Existing Evidence

Per the mission's own scope for this phase: use ONLY evidence already recorded in the registry.
No new experiments, no new data pulls, no parameter retuning. This ranks every family from
`PHASE8_MULTIPLE_TESTING_AUDIT.md`'s §1 grouping (excluding F_MEANREV, already fully covered in
Phase 4/8) by the strength and survivability of its own existing evidence, to answer: if F_MEANREV
does not ultimately clear the bar, is there a materially stronger alternative already sitting in the
registry, or not?

## Rank 1 — F_CONTEXT (market/sector-divergence): richest evidence base, disqualified by temporal instability

Full evidence read directly from the registry (`H_CONTEXT_MARKET_002/SECTOR_002/ALIGN_001/MARKET_004/MARKET_005`,
all INCONCLUSIVE). This is, by evidence volume and robustness-check coverage, the single
best-supported family in the entire registry:

- **Core finding** (H_CONTEXT_MARKET_002, 5-year data): the frozen baseline BUY condition performs
  BETTER when the broader NIFTY is in a DOWNTREND (divergence) than when it confirms — CI-decisive
  positive in development (+0.573%/+1.040%) and validation (+0.760%/+1.536%, a striking reversal
  from the unconditioned control's decisive NEGATIVE in the same period). Out-of-sample: positive
  point estimate, not CI-decisive (n=261, underpowered, not reversing).
- **Independently replicated at the sector level** (H_CONTEXT_SECTOR_002): the same divergence
  -beats-confirmation shape, an independent context layer.
- **Compounds** (H_CONTEXT_ALIGN_001, both market+sector diverging at once): dev/val larger than
  either layer alone (validation +0.958%/+1.389%), consistent with a genuine, not double-counted,
  mechanism — but OOS collapses to n=10, unusable.
- **Deep validation** (H_CONTEXT_MARKET_004): survives cost sensitivity up to 0.30% round-trip
  (wider margin than the already-rejected gap-fade family), broad-based across sectors and BOTH
  liquidity halves (unlike gap-fade, which was concentrated in one sector/illiquid names) — this is
  a materially more robust profile than any other INCONCLUSIVE entry in the registry.
- **The disqualifying finding** (H_CONTEXT_MARKET_005, 10-year extension): the market-level
  condition's SIGN IS NOT STABLE across the full available history — **CI-decisively NEGATIVE in
  2016–2022** (the opposite of the original 5-year study's own development-period finding),
  **CI-decisively POSITIVE in 2022–2026**. The 5-year study that produced the "core finding" above
  only ever covered the post-2021 era, so it could not have detected this. This is a genuine,
  previously-undetected regime-dependence, not merely a power problem. The one partial improvement:
  the compound BOTH_DIVERGE condition's out-of-sample sample is now properly powered (n=236, up from
  the original n=10) and CI-decisive positive — but development/validation do not confirm it under
  this same partition, so it is not a clean three-split confirmation either.

**Verdict for ranking purposes**: this family has the deepest, most robustness-tested positive
evidence in the registry, but its own most recent, most rigorous test (the 10-year extension)
found the core condition's sign flips between eras. That is a disqualifying finding of a
fundamentally different KIND than F_MEANREV's (temporal/regime instability, not multiple-testing
fragility or portfolio-construction collapse) — and arguably more serious, since a sign reversal
across eras cannot be fixed by better sizing or a larger sample the way F_MEANREV's problems
potentially could be. **Not currently promotable. Not clearly worth a dedicated new research cycle
either**, unless a principled, pre-registered regime-conditioning variable (not merely "add more
years") is proposed first — repeating the same unconditioned test on yet more data would not resolve
an already-observed era-dependent sign flip.

## Rank 2 — F_MEANREV: covered fully in Phase 4/8; not repeated here

See `PHASE4_EVIDENCE_RECONCILIATION.md` and `PHASE8_MULTIPLE_TESTING_AUDIT.md`. Summary for ranking
purposes only: validation-split positive result survives multiple-testing correction at every level
tested; OOS-split does not survive family-search-level correction; both splits remain unresolved
against portfolio-construction collapse (H_MEANREV_011) and universe-membership survivorship
(Phase 2, PARTIALLY_AVAILABLE). A different failure mode than F_CONTEXT's temporal instability, but
equally disqualifying for promotion today.

## Rank 3 — Families already closed by their own downstream work (not live candidates)

- **F_GAP**: H_GAP_002 (gap-down recovery) shows dev/val CI-decisive positive but OOS flat/not
  decisive; H_GAP_003, this family's own pre-registered "deep validation" adversarial pass, reached
  REJECTED. The family has already been chased to a negative conclusion by its own prior work — not
  an open candidate.
- **F_XSECT**: H_XSECT_001 alone looks "strikingly consistent" (laggard-outperformance across every
  lookback/split tested), but the family's own downstream deep-dive (H_XSECT_002/004 REJECTED,
  H_XSECT_006 REJECTED — objective universe-widening produced a sign reversal, per
  `H_XSECT_006_UNIVERSE_WIDENING_PREREGISTRATION.md`) has already disqualified it. Citing H_XSECT_001
  alone without its own family's later verdicts would be exactly the selective-citation error this
  audit exists to prevent.

## Rank 4 — Remaining single-entry / thin-evidence families: none stand out

Reviewed (description + evidence excerpt) but not deep-dived further, since none show F_CONTEXT or
F_MEANREV's combination of magnitude, cross-split consistency, AND multi-dimensional robustness
checks already on file: H_MOMENTUM_001 (dev CI-decisive positive at h5, but weaker/unconfirmed at OOS per the
length-limited excerpt reviewed — worth a closer look only if this family is ever revisited, not
ranked above F_CONTEXT/F_MEANREV on current evidence), H_TRANSMISSION_001 (decisive but NEGATIVE direction — a real,
confirmed-negative predictive relationship, not a positive edge candidate), H_ENTRY_003/005,
H_EXIT_002, H_CALENDAR_001, H_OPENRANGE_001, H_MEANREV_002/003/006/008 (already subsumed under
F_MEANREV's own closed evaluation). None of these carry evidence remotely close to F_CONTEXT's five
-entry, multi-robustness-check body of work.

## Phase 10 conclusion

**No hypothesis family currently in the registry clears a defensible bar for promotion**, and the
two strongest candidates (F_CONTEXT, F_MEANREV) fail for two independent, non-overlapping reasons —
temporal/regime sign-instability for one, multiple-testing/portfolio-construction fragility for the
other. This is not a case of "we haven't looked hard enough" (56 entries, 17 independent research
avenues, several with deep multi-stage validation already completed) — it is closer to consistent,
convergent evidence that the currently available signal set, dataset, and research framework have
not yet produced a demonstrably stable, tradable edge. This directly feeds Phase 11.

## FACT / INFERENCE / ASSUMPTION / LIMITATION / DECISION

- **FACT**: F_CONTEXT's market-divergence condition is CI-decisively NEGATIVE in 2016–2022 and
  CI-decisively POSITIVE in 2022–2026, per H_CONTEXT_MARKET_005's own direct measurement.
- **FACT**: F_GAP and F_XSECT have already been pursued to REJECTED verdicts by their own downstream
  family members.
- **INFERENCE**: the registry's own accumulated evidence, taken as a whole rather than any single
  entry, is more consistent with "no currently demonstrable edge in this dataset/framework" than
  with "an edge exists but hasn't been found yet."
- **LIMITATION**: this ranking used only already-recorded evidence; several entries (H_MOMENTUM_001,
  H_MEANREV_006/008) were reviewed from a length-limited excerpt, not their full evidence field —
  sufficient for ranking purposes (none approached F_CONTEXT/F_MEANREV's evidence density even in
  excerpt form) but not exhaustive.
- **DECISION**: proceeding to Phase 11 (Stop Conditions) next, not to a new hypothesis cycle.
