# Phase C — Final Research Decision

Per the user's own mission: "Determine whether any currently identified trading effect can survive
historically correct data, multiple-testing scrutiny, regime instability, realistic costs, and
realistic portfolio implementation. If neither survives, produce a defensible terminal research
conclusion."

## Classification: **3 — NO DEMONSTRATED EDGE WITH CURRENT DATA**

Not category 4 (research data insufficient) — this project used substantial, real, high-quality
data (10 years, 206-230+ symbols, multiple independently-verified NSE archive sources, ~2,500
trading days) and a genuinely rigorous statistical/engineering infrastructure (57 registry entries,
17 independent research families, real cost models, real portfolio-construction simulation, real
multiple-testing correction). The verdict below is a substantive negative finding, not a "we
couldn't get enough data to know" finding — though one narrower, specific sub-question (exact
point-in-time F&O universe membership) does remain data-constrained, disclosed precisely in Phase A
rather than blurring the whole project's classification.

Not category 1 (demonstrated candidate edge) or category 2 (interesting effect but not tradable) —
reasoning for each candidate below.

## What was tested (full accounting)

**57 hypotheses** across **17 materially-independent research families** (`PHASE8_MULTIPLE_TESTING_
AUDIT.md` §1): 34 REJECTED, 22 INCONCLUSIVE, 1 SUPPORTED (a confirmed NON-edge: "trend confirmation
entry timing carries no meaningful directional edge"). The two candidates carried furthest —
`F_MEANREV` (14 sequential entries) and `F_CONTEXT` (now 11, after this session's `H_CONTEXT_
MARKET_006`) — are examined in full below. No other family approaches their evidence density
(`PHASE10_FAMILY_RANKING.md`).

## F_MEANREV — what survived, what failed

| Test applied | Result |
|---|---|
| Gross signal (H_MEANREV_006-008) | Survives — a real, repeatable statistical regularity in NSE price behavior |
| Realistic costs, corrected sizing (H_MEANREV_010) | Survives in validation (+1.51% CI-decisive) and out-of-sample (+0.98% CI-decisive), at an explicitly-disclosed unrealistic 100%-capital-concentration sizing |
| Realistic portfolio construction, 4-position cap (H_MEANREV_011) | **FAILS** — collapses to statistically-meaningless, mixed-sign result in all three splits |
| Signal-strength-selection mechanism test (H_MEANREV_012) | Ruled out as the cause of the portfolio-level disappointment |
| Clustering/correlation mechanism test (H_MEANREV_013) | Also ruled out (Outcome C, unstable) |
| Registry-level multiple-testing correction (Phase 8, this session) | Validation survives every correction level tested (up to family=56); **out-of-sample does NOT survive** family-search (17) or full-registry (56) correction |
| Point-in-time universe reconstruction (Phase A, this session) | **Practically buildable in principle, but 20.6% of a sampled "eligibility-changed" population is unfetchable under its historical ticker (corporate actions/renames), concentrated in exactly the sub-population the correction needs to fix — classified material, replay not executed** |

**Conclusion**: the underlying gross signal is real. The path from that signal to a demonstrated,
tradable edge fails at realistic portfolio construction (a result already obtained before this
session) and the specific remaining path to rescue it (a corrected, point-in-time-accurate universe)
is blocked by a genuine, disclosed data-identity problem, not merely unbuilt convenience
infrastructure. **Does not survive.**

## F_CONTEXT — what survived, what failed

| Test applied | Result |
|---|---|
| Original 5-year study (H_CONTEXT_MARKET_002/SECTOR_002/ALIGN_001) | CI-decisive positive in development/validation, broad-based, cost-surviving |
| Deep robustness pass (H_CONTEXT_MARKET_004) | Survives cost sensitivity to 0.30% round-trip, both liquidity halves, no single-sector dominance |
| 10-year extension (H_CONTEXT_MARKET_005) | **FAILS** — the core condition's sign flips between eras: CI-decisively NEGATIVE 2016-2022, CI-decisively POSITIVE 2022-2026 |
| Regime-instability explanation test (H_CONTEXT_MARKET_006, this session) | **FAILS to explain it** — NIFTY's own volatility regime does not discriminate a stable sub-effect; the dominant, best-powered bucket reproduces the same unexplained instability |

**Conclusion**: the richest, most extensively robustness-tested evidence base in the entire
registry, but the core phenomenon itself is not stable across the full available history, and the
one economically-motivated regime explanation tested this session does not account for the
instability. **Does not survive.**

## What was contaminated by survivorship

Quantified, not merely asserted: accepted `H_MEANREV` trades from the point-in-time-plausible
`ORIGINAL_32_NSE_UNIVERSE` subset are 14.7% of trade count but 140.8% of summed net return —
`EXPANDED_ONLY` (the current-F&O-eligibility, survivorship-exposed group) is a net DRAG, not the
source of the positive result. This is a mixed signal (the core effect is not manufactured purely by
survivorship-biased names) but the true magnitude on a genuine point-in-time universe remains
unquantifiable given Phase A's own material gap.

## What failed multiple-testing scrutiny

`H_MEANREV`'s out-of-sample split (Phase 8, this session). No other individually-promoted claim was
close enough to a promotion threshold for multiple-testing correction to be the deciding factor —
`F_CONTEXT` failed on regime instability before multiple-testing correction was even the binding
constraint.

## What failed regime-stability testing

`F_CONTEXT`'s entire remaining case (this session, Phase B) — the one candidate whose central
problem WAS regime/era instability, and whose one tested explanatory regime variable did not resolve
it.

## What data limitations remain

1. **Point-in-time NSE F&O universe membership**: practically reconstructable in principle (two
   real, verified archive formats span the required window), but a corporate-action-aware
   ticker-identity-resolution layer is required for full correctness and was not built this session
   (Phase A, Classification B, material gaps).
2. **NSE's own bulk-retrieval terms of use**: unread/unverified — any future bulk reconstruction
   attempt should read these first.
3. **Regime variables beyond NIFTY volatility**: India VIX regime and market breadth remain
   available, untested alternatives for explaining `F_CONTEXT`'s instability — not tested this
   session, by design (small pre-declared set), not because they were found wanting.

## What additional data/work would be required to continue scientifically

- A corporate-action/ticker-rename resolution layer (companies merged/renamed/demerged over the
  research window), built on top of the now-existing `quant_research/point_in_time_fno_universe.py`
  prototype, before any further point-in-time `H_MEANREV` replay is attempted.
- A separately-preregistered follow-up testing India VIX regime (or another single, pre-declared
  variable) against `F_CONTEXT`'s instability, if that avenue is judged worth continuing.
- Neither is undertaken automatically by this session — both require the human resource-allocation
  decision already flagged in the prior mission's own Phase 11 conclusion, now sharpened with this
  session's concrete findings about exactly what each would require.

## Terminal conclusion

**No hypothesis tested in this project — including the two most extensively investigated,
highest-evidence candidates — currently constitutes a statistically and economically defensible,
tradable intraday edge in the Indian equity market.** This is not a failure of engineering rigor or
data access (Phase 3 found zero infrastructure defects across a full audit; this session
independently verified two real historical data archives and built working retrieval/parsing
infrastructure for one of them) — it is a substantive, multiply-corroborated research result,
reached by testing 57 hypotheses across 17 independent avenues, with the two strongest candidates
each failing for different, non-overlapping, honestly-earned reasons rather than a single fragile
p-value. Per the project's own established terminology discipline, this is **NO DEMONSTRATED
ECONOMIC EDGE**, not a claim that no edge could ever exist. **The project remains paper-only.**
