# Phase 8 — Registry-Level Multiple-Testing / Research-Selection Audit

Per the mission's own instruction: not a blind `family_size=56` Bonferroni application. This phase
first establishes a defensible dependency structure across all 56 registry entries, then applies
graduated corrections to the one result currently under consideration for promotion
(H_MEANREV_010/013's positive validation/OOS net returns), and finally states the research-selection
caveat explicitly.

## 1. Dependency structure: grouping 56 entries into materially-independent families

Source: direct `build_hypothesis_registry()` dump (`_all_56_full.tsv`, this session). Grouping
criterion: entries share the same underlying signal/predicate, the same base dataset population, or
are an explicit sequential follow-up/decomposition of an earlier entry in the same list (per the
mission's own definition of non-independence — shared data OR selected-after-seeing-earlier-results).

| Family | Members | n | Basis for grouping |
|---|---|---:|---|
| F_ENTRY | H_ENTRY_001–005 | 5 | All modify entry timing on the same frozen baseline signal/population |
| F_EXIT | H_EXIT_001–004 | 4 | All modify exit rules on the same frozen baseline signal/population |
| F_MEANREV | H_MEANREV_001–012, H_EXIT_005, H_MEANREV_013 (this session, not yet a registry entry) | 14 | One continuous, explicitly sequential research chain — each entry is a follow-up decomposition/correction of the previous (verified directly: 006 decomposes 005, 007/008 decompose 006, 009 is the first executable form of 006, 010 corrects 009's sizing defect, 011 adds portfolio construction to 010, 012 tests 011's tie-break, 013 tests 011/012's clustering explanation, H_EXIT_005 is explicitly an exit-architecture variant for this same signal) |
| F_CONTEXT | CONTEXT_MARKET_001–005, CONTEXT_SECTOR_001–002, CONTEXT_VIX_001–002, CONTEXT_ALIGN_001 | 10 | All test regime/context filters conditioning the same frozen baseline signal on the same population |
| F_TRANSMISSION_NASDAQ | H_TRANSMISSION_001 | 1 | Nasdaq→NSE-IT predictor; distinct predictor variable from the USD/INR group below |
| F_TRANSMISSION_USDINR | H_TRANSMISSION_002–004 | 3 | 003/004 are explicit, disclosed decompositions of 002 (IT vs. Pharma tested separately) |
| F_GAP | H_GAP_001–003 | 3 | 003 is an explicit "deep validation" follow-up of 001/002 |
| F_XSECT | H_XSECT_001–006 | 6 | Sequential deep-dive on the same cross-sectional laggard-portfolio effect |
| F_SECTOR_ROTATION | H_SECTOR_ROTATION_001 | 1 | Sector-level (not stock-level) cross-sectional rank; related methodology to F_XSECT but a distinct target variable — kept separate given genuine uncertainty about shared-data overlap |
| F_CALENDAR | H_CALENDAR_001–002 | 2 | 002 explicitly re-tests 001's Tuesday effect on a different instrument |
| F_OPENRANGE | H_OPENRANGE_001 | 1 | Standalone |
| F_VOL | H_VOL_001 | 1 | Standalone |
| F_EXTREME | H_EXTREME_001 | 1 | Standalone (distinct predicate/outcome from F_MEANREV — asymmetry test, not the oversold+relative-weakness signal) |
| F_MOMENTUM | H_MOMENTUM_001 | 1 | Standalone (continuation test; conceptually adjacent to F_MEANREV but untested lineage — kept separate, not merged, absent direct evidence of shared derivation) |
| F_BREADTH | H_BREADTH_001 | 1 | Standalone |
| F_BREAKOUT | H_BREAKOUT_001 | 1 | Standalone |
| F_RELSTRENGTH | H_RELSTRENGTH_001 | 1 | Standalone (possible conceptual ancestor of F_MEANREV's relative-strength component, but not confirmed by direct code/doc citation this session — kept separate rather than assumed) |
| *(excluded)* | H_BASELINE_001 | 1 | **Not an independent test.** It is a same-session consolidation/synthesis of H_ENTRY_001's own prior evidence, the pre-existing 5-year backtest, and the pre-existing promotion-gate verdict — no new data was tested. Excluded from the family count on that basis, not folded into F_ENTRY. |

**Totals**: 56 registry entries = 55 independently-tested entries (1 excluded as a non-independent
synthesis) + 17 materially-independent research families.

This grouping is itself a judgment call in a few places (F_SECTOR_ROTATION vs. F_XSECT,
F_MOMENTUM/F_RELSTRENGTH vs. F_MEANREV) — flagged explicitly above rather than silently resolved
either direction, since collapsing them would only ever make the correction MORE conservative, never
less.

## 2. Applying graduated corrections to the one result under live consideration

The only registry result currently CI-decisive and positive after realistic costs is
H_MEANREV_010's fixed-notional single-position finding (validation +1.51% CI[+0.94,+2.08], OOS
+0.98% CI[+0.52,+1.44], per `PHASE4_EVIDENCE_RECONCILIATION.md`). H_MEANREV_010's own exact per-trade
return series was not persisted outside its summary statistics, so it cannot be re-corrected byte
-for-byte. As the closest available proxy, this phase recomputes the confidence interval on
H_MEANREV_013's own "all priced candidates" population (same signal, same universe, same h10 exit,
same cost model — but a LARGER, unfiltered set, since H_MEANREV_013 independently prices every
raw candidate regardless of same-symbol overlap, whereas H_MEANREV_010 enforced one position per
symbol at a time). **This is a directionally-informative proxy, not a re-verification of
H_MEANREV_010's own reported figure** — the two populations differ in size (val n=1533 vs. n=688;
OOS n=1004 vs. n=840) though they draw from the same underlying signal and market data.

| Split (H_MEANREV_013 population) | n | mean | uncorrected z=1.96 | within-chain z=2.91 (family=14) | family-search z=2.97 (family=17) | full-registry z=3.32 (family=56) |
|---|---:|---:|---|---|---|---|
| validation | 1533 | +1.464% | [+1.05%,+1.88%] POSITIVE | [+0.84%,+2.08%] POSITIVE | [+0.83%,+2.10%] POSITIVE | [+0.76%,+2.17%] POSITIVE |
| out_of_sample | 1004 | +0.585% | [+0.19%,+0.98%] POSITIVE | [+0.00%,+1.17%] POSITIVE (touches zero) | **[-0.01%,+1.18%] MEANINGLESS** | **[-0.08%,+1.25%] MEANINGLESS** |

Three correction levels are reported, not one, because they answer different questions:
- **Within-chain (family=14)**: "does this result survive correcting for the fact that 14 sequential
  tests were run on this one signal before reporting it?" — validation and OOS both survive
  (OOS only barely; the lower bound is exactly 0.00%).
- **Family-search (family=17)**: "does this result survive correcting for the fact that 17
  materially independent research avenues were searched across the whole registry, of which this
  is the one being highlighted?" — validation survives; **OOS does not** (flips to
  STATISTICALLY_MEANINGLESS).
- **Full-registry (family=56)**: the most conservative, treating every individual test as if fully
  independent (known to be wrong, per §1's dependency analysis, but included as an upper bound) —
  same conclusion as family-search: validation survives, OOS does not.

## 3. Required three-part deliverable

**1. Unadjusted evidence**: H_MEANREV_010's own reported validation (+1.51% CI[+0.94,+2.08]) and OOS
(+0.98% CI[+0.52,+1.44]) results are both CI-decisive positive at the conventional, uncorrected 95%
level. This is a true, verified statement about the raw statistical output.

**2. Adjusted interpretation**: Once the registry's own research-selection structure is accounted
for, the picture is weaker than the unadjusted numbers suggest. The proxy recomputation above shows
the validation-split finding is robust to every correction level tested here, including the most
conservative (family=56, z=3.32) — it does not appear to be an artifact of having searched 17
avenues. The OOS-split finding, however, is NOT robust once the correction reflects the true search
space (family-search, family=17) rather than only the within-chain sequential count (family=14) —
its lower confidence bound crosses zero. **Combined with the already-documented, unresolved
confounds on this same result** (survivorship exposure quantified at 140.8% of net return from 14.7%
of trade count in ORIGINAL-32 names, per Phase 4; and the fact that H_MEANREV_011's realistic
4-position portfolio construction already collapsed this same signal into a statistically
meaningless, mixed-sign result), the honest combined position is: **one of the two previously
CI-decisive splits (OOS) does not survive a defensible multiple-testing correction, and the other
(validation) survives multiple-testing correction alone but has NOT yet survived either
portfolio-construction realism (H_MEANREV_011) or universe-membership scrutiny (Phase 2,
unresolved). No individual correction below is sufficient on its own to call this a demonstrated
edge, and none has been treated that way.**

**3. Research-selection caveat**: This entire audit is itself a form of selection. The
H_MEANREV chain was elevated to "Priority 1" specifically BECAUSE it was the one positive-looking
result among 56 tested hypotheses — that is exactly the scenario multiple-testing correction exists
to guard against, and it is also why the user's own instruction to resolve survivorship,
portfolio-construction, and clustering explanations BEFORE treating it as a finding was correct
methodology, independently arriving at the same caution this section's numbers now confirm
quantitatively. No further hypothesis in this registry should be presumed to have a better chance of
being real merely because it hasn't been tested yet — 33/56 rejected and 22/56 inconclusive is the
realistic prior for any new, untested predicate drawn from the same general search process.

## 4. Registry-level accounting mechanism for future research — decision

**Decision: not implemented this session.** Reasoning: `strategy/multiple_testing.py` already
provides a correct, reusable `bonferroni_corrected_z(family_size)` primitive; what was missing was
not code but the dependency-structure judgment applied above, which requires human-legible
reasoning about which hypotheses are "genuinely related" — the kind of judgment call flagged
explicitly in §1 (F_SECTOR_ROTATION, F_MOMENTUM, F_RELSTRENGTH). Hard-coding a family-assignment
field onto `HypothesisRecord` now, based on a single session's grouping judgment, risks freezing a
debatable taxonomy into the data model and would not itself prevent the underlying mistake (treating
an uncorrected CI as sufficient). The lower-cost, lower-risk action taken instead: this document
itself, as a standing, citable reference for family-size assumptions, to be manually re-applied and
updated whenever a new hypothesis is added to a family or a new family is opened. Per the mission's
explicit rule, no historical hypothesis-registry verdict (REJECTED/INCONCLUSIVE/SUPPORTED) was
altered by this analysis — this phase only adds a correction lens on top of the existing,
unmodified H_MEANREV_010 verdict (INCONCLUSIVE, unchanged).

## FACT / INFERENCE / ASSUMPTION / LIMITATION / DECISION

- **FACT**: 56 registry entries group into 17 materially-independent research families (1 entry,
  H_BASELINE_001, excluded as a non-independent synthesis).
- **FACT**: the proxy recomputation's validation-split result remains CI-decisive positive at every
  correction level tested, up to and including family=56.
- **FACT**: the proxy recomputation's OOS-split result is CI-decisive positive only under the
  within-chain correction (family=14); it becomes statistically meaningless under the family-search
  (17) and full-registry (56) corrections.
- **ASSUMPTION**: the proxy population (H_MEANREV_013's independently-priced "all candidates" set)
  is a reasonable stand-in for H_MEANREV_010's own exact population for the purpose of a
  multiple-testing sensitivity check, given neither the signal, universe, exit rule, nor cost model
  differs between them — only the position-concurrency filter does.
- **LIMITATION**: H_MEANREV_010's own exact per-trade return series was not persisted this session,
  so this is a sensitivity analysis on a closely related population, not a byte-for-byte correction
  of the originally reported numbers.
- **DECISION**: no registry-level code/schema change implemented (§4). Proceeding next to Phase 10's
  ranking step (using only existing evidence, no new experiments) to determine which OTHER
  hypothesis family, if any, has the next-strongest surviving evidence, since F_MEANREV's own
  strongest surviving claim (validation-only, portfolio-construction-unresolved,
  universe-membership-unresolved) is not sufficient by itself to justify further dedicated research
  budget without first checking whether a stronger alternative avenue already exists in the
  registry.
