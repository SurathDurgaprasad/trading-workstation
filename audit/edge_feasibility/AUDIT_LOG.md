# Edge Feasibility Audit — Log

## 2026-09-21T09:23:00Z — Loop start
State files created. Live fleet running unaffected on commit e0350fc (15/15 healthy, 645 bars, 73 signals, 0 trades at last check before this audit began). This audit performs no production code changes, no strategy/RiskEngine/dashboard/architecture work, and does not touch the live fleet. Beginning Phase 0 (Inventory).

## 2026-09-21T09:24-09:29Z — Phase 0 complete, Phase 2 partial
Ran `build_hypothesis_registry()` directly (not CLI grep) to get an authoritative count: **56 entries**,
not the 44 the audit brief assumed (33 REJECTED / 22 INCONCLUSIVE / 1 SUPPORTED; 32/22/1 pre-existing +
this session's own H_BASELINE_001). Corrected in INVENTORY.md immediately, before the wrong number could
propagate into later phases.

Identified H_MEANREV_006->012 as the single most important thread in the registry: a real gross positive
effect was found, destroyed by a diagnosed fixed-brokerage/undersized-position interaction
(H_MEANREV_009), partially recovered under corrected sizing with two CI-decisive POSITIVE_PERFORMANCE
splits (H_MEANREV_010 Candidate 2), and left unresolved (not disproven) at the realistic-portfolio-
construction stage (H_MEANREV_011/012, capacity-driven sample attrition). Flagged as the central case
study for Phase 4 Synthesis question C.

Verified three pieces of shared evaluation infrastructure directly against source (not registry prose):
CostModel.india_nse_intraday_2026() (backtesting/costs.py), the 30-trade MIN_SAMPLE_SIZE_FOR_A_VERDICT
floor (strategy/promotion_gate.py), and strategy/multiple_testing.py's Bonferroni correction. All three
are real, not fabricated or ad hoc. Found one genuine, disclosed-but-unaddressed gap: Bonferroni
correction is scoped per-experiment (caller-defined family_size), never applied registry-wide across all
55-56 hypotheses sharing overlapping datasets -- flagged as open work for Phase 2/3.

Live fleet checked twice during this work (09:24:45Z: 680 bars/73 signals; 09:28:50Z: 750 bars/75
signals -- 2 new natural signals, both DOWNGRADE verdict / MAX_EXPOSURE rejection, consistent with all
73 prior). Fleet untouched, no code changes made to production paths. Pausing deep audit work as NSE
close (15:30 IST, ~09:29Z + ~31min) approaches to prioritize end-of-day capture; will resume Phase 1/2/3
afterward.

## 2026-09-21T09:34-09:36Z — Priority-1 substantive progress: MEANREV_CHAIN_AUDIT.md

Read `quant_research/mean_reversion_portfolio.py` directly: `_run_schedule`'s accept/reject decision
uses only signal-date-available information (open count, cash); trade outcome computed only after
acceptance. No-look-ahead confirmed structurally, not just by docstring claim.

Found H_MEANREV_012's own Candidate A independently re-derived H_MEANREV_011's exact cited numbers
(555/111/105 trades, same gross P&L, same verdict) -- a genuine independent reproduction via a
different code path, partially resolving (not eliminating) the "no committed runner script" gap.

Answered the user's central question ("are rejected candidates systematically different from
accepted ones") INDIRECTLY: H_MEANREV_012's own pre-registered ablation (zscore-strength ranking
replacing the arbitrary alphabetical tie-break) made validation MATERIALLY WORSE (net -0.51%->-1.13%,
gross ~3x more negative), ruling out "the accepted subset is just the weaker signals" as the dominant
mechanism. The clustering/correlation hypothesis (stated as [INFERENCE], never [TESTED], in the
H_MEANREV_011 preregistration itself) remains the live, unresolved explanation.

Resolved both flagged data-audit open items by reading `docs/research/
H_XSECT_006_UNIVERSE_WIDENING_PREREGISTRATION.md` S7-S8 directly: 206/208 is a mechanical filesystem-
path-safety exclusion (GVT&D.NS, M&M.NS -- tickers contain '&'), unrelated to survivorship.
Survivorship bias itself is real, already disclosed by the project's own prior research (not a fresh
discovery), and correctly identified there as biasing toward INFLATING a positive finding -- directly
discounting confidence in H_MEANREV_010's positive point estimates specifically.

## 2026-09-21T09:48-09:49Z — Pre-registration for the clustering analysis (Priority 1 continuation)

Per explicit user instruction, wrote `H_MEANREV_013_CLUSTERING_PREREGISTRATION.md` BEFORE running any
analysis or looking at data -- frozen bins (1/2/3-4/5-9/10+ candidates), frozen decision rule (monotonic
decline vs. flat-positive vs. random/unstable, exactly as the user specified), frozen scope
(measures survivorship exposure via ORIGINAL/EXPANDED-ONLY split, does not attempt to fix it; explicitly
does not authorize any portfolio-construction retune regardless of outcome). Analysis itself deferred
to after today's NSE close, per explicit instruction not to run new analysis work while the live fleet
is active -- this offline preregistration work itself never touches the fleet.

Fleet checked repeatedly through this window (09:34Z 825/83 -> 09:49Z 975/90 bars/signals), consistently
healthy, 0 trades, same DOWNGRADE/MAX_EXPOSURE pattern throughout. ~11 minutes to 15:30 IST close as of
this entry.

## 2026-09-21T10:16-10:20Z — H_MEANREV_013 executed, after NSE close, fleet untouched throughout

Wrote `audit/edge_feasibility/scripts/h_meanrev_013_clustering.py`, an isolated offline script:
independently replicates (never modifies) `_run_schedule`'s own accept/reject decision rule from
`quant_research/mean_reversion_portfolio.py` so individual candidate events can be labeled, then
prices EVERY candidate (accepted and rejected) via the existing, unmodified
`compute_fixed_notional_trade`. Cross-checked correct: replicated labeling produced 791 accepted
trades, matching the real, imported `schedule_portfolio()` call exactly.

**Result: the clustering hypothesis is NOT SUPPORTED.** Development alone shows a clean, CI-decisive
monotonic decline from low-clustering (+1.25%) to high-clustering (-0.23%) bins -- exactly the
pre-registered Outcome A pattern in isolation. Validation and out-of-sample do not reproduce it:
validation's bin=1 (lowest clustering) is the single worst result in the whole table (-3.59%,
CI-decisively NEGATIVE), while validation's and out-of-sample's bin=10+ (highest clustering) are
BOTH CI-decisively POSITIVE (+2.60%/+2.63%). Per the pre-registered decision rule this is Outcome C
(random/unstable across splits) -- clustering does not explain the portfolio-level result, joining
H_MEANREV_012's own earlier finding that signal-strength selection doesn't either. Neither of the
two most plausible mechanisms for H_MEANREV_011's disappointment has survived direct testing.

Survivorship-exposure quantification (measured, not fixed): accepted trades from the ORIGINAL-32
universe are only 14.7% of trade count but 140.8% of summed net return -- the EXPANDED-ONLY
(current-F&O-eligibility, more survivorship-exposed) group is a net drag, not the source of
whatever positive signal exists. Mildly reassuring for the survivorship concern specifically, does
not change the Outcome-C verdict.

Full writeup: `H_MEANREV_013_RESULTS.md`. Full per-event data: `H_MEANREV_013_RESULTS.csv` (9,811
rows). Zero production files modified. Live fleet checked before and confirmed unchanged/idle
throughout (post-close, no new bars, healthy).

---

## 2026-09-21 (later) — New 12-phase autonomous mission: Phases 1, 2, 3, 4, 8, 10, 11 executed

User formally appointed this session as the autonomous research/engineering agent with a sweeping
new objective: find a defensible edge, or produce strong evidence the current framework cannot
demonstrate one, operating through a 12-phase sequence without stopping to ask between subtasks.

**Phase 1** (repo/registry state audit): branch `final-product-hardening`, HEAD `9131389`, clean
tree, 56 registry entries confirmed (33 REJECTED/22 INCONCLUSIVE/1 SUPPORTED), universe/dataset/test
inventory taken. **Phase 2** (point-in-time universe): confirmed the cached Dhan scrip-master holds
zero historical F&O contracts (all FUTSTK rows expire 2026-09-24 or later); browser-investigated
NSE's own public archives and found a genuine, authoritative F&O daily bhavcopy archive exists, but
full multi-year reconstruction is a separate, unscoped engineering effort -- status
`PARTIALLY_AVAILABLE`, deferred, not built this session. **Phase 3** (infrastructure audit, A-X
checklist against splits/labels/entry-exit timing/costs/sizing/universe timing/corporate
actions/missing bars/timezone/tie-break/CI methodology/multiple-testing scope/reproducibility):
zero genuine defects found; one new caveat recorded (`period="10y"` rolling-window results are not
byte-for-byte reproducible across different run dates). **Phase 4** (full H_MEANREV_009-013 evidence
table, 6 required questions answered): confirms the validation/OOS positive result is real as a raw
statistic but does not survive realistic portfolio concentration (H_MEANREV_011) with confidence,
and the universe dependency remains open; decision to skip Phases 5-7 (gated behind the unresolved
universe question) and proceed to Phase 8.

**Phase 8** (registry-level multiple-testing / research-selection audit): grouped the 56 entries
into 17 materially-independent research families (excluding H_BASELINE_001 as a non-independent
synthesis of prior evidence, not a new test). Computed graduated Bonferroni corrections
(within-chain family=14, z=2.91; family-search family=17, z=2.97; full-registry family=56, z=3.32)
and applied them to a same-signal/universe/exit proxy of H_MEANREV_010's own population (exact
original per-trade series not persisted, so this is a sensitivity check, not a byte-for-byte
recorrection). Result: the validation-split positive finding survives every correction level
tested; the out-of-sample-split finding does NOT survive family-search or full-registry correction
(CI crosses zero). Decision: no registry-schema/code change implemented -- the judgment calls
involved (which entries share a family) are better served by a standing, human-legible reference
document than a frozen data-model field.

**Phase 10** (rank remaining hypothesis families using ONLY existing evidence, no new experiments):
read the full evidence field for all 22 INCONCLUSIVE registry entries directly. Found that
F_CONTEXT (the market/sector-divergence family, H_CONTEXT_MARKET_002/SECTOR_002/ALIGN_001/MARKET_004/
MARKET_005) is the single richest, most robustness-tested body of evidence in the entire registry --
broad-based across symbols, survives cost sensitivity to 0.30% round-trip, decisive in both
liquidity halves, replicated independently at the sector level and in compound form. But its own
most recent, most rigorous test (H_CONTEXT_MARKET_005, a 10-year extension) found the core
condition's SIGN IS NOT STABLE across eras: CI-decisively NEGATIVE 2016-2022, CI-decisively POSITIVE
2022-2026 -- a genuine disqualifying finding the original 5-year study (which only covered the
post-2021 era) could not have detected. F_GAP and F_XSECT were found already closed by their own
downstream family work (H_GAP_003 and H_XSECT_002/004/006 all REJECTED). No remaining family
approaches F_CONTEXT or F_MEANREV's evidence density. Conclusion: no hypothesis family in the
registry currently clears a defensible promotion bar.

**Phase 11** (stop-condition assessment): both Condition 1 (genuine external-data dependency: a
real point-in-time universe reconstruction for F_MEANREV; a fresh regime-conditioned pre-registration
for F_CONTEXT) and Condition 3 (avenue exhausted: both top candidates' own next reasonable
robustness checks have already been run) are independently satisfied. Condition 2's negative-finding
counterpart is satisfied -- the mission's own explicitly stated alternative objective ("strong
evidence the current framework cannot demonstrate one") has been reached, via 56 hypotheses / 17
independent families / two independently-disqualified top candidates / zero infrastructure defects
found. Determination: stop autonomous hypothesis-generation here rather than starting an ungrounded
new hypothesis, and report to the user for a human resource-allocation decision on the two deferred
engineering/research tasks. Phase 12 (live pilot) does not apply -- no promotable candidate exists.

Live fleet checked non-disruptively post-close (16:18 IST): 15/15 symbols healthy, 91 signals total
(unchanged since 15:30 IST close, as expected), 0 trades, no action taken. Zero production files
modified across Phases 1-11 of this mission (Phase 3's own audit found no defect requiring a code
change). Full regression run before committing (see commit message for pass/fail counts).

Deliverables this session: `PHASE1_PHASE2_REPORT.md`, `PHASE3_INFRASTRUCTURE_AUDIT.md`,
`PHASE4_EVIDENCE_RECONCILIATION.md`, `PHASE8_MULTIPLE_TESTING_AUDIT.md`,
`PHASE10_FAMILY_RANKING.md`, `PHASE11_STOP_CONDITIONS.md`, `STATE.json` (updated).

---

## 2026-09-21 (continuing from 58dd8b8) — Phase A (point-in-time universe) and Phase B (F_CONTEXT regime) executed sequentially; Phase C terminal conclusion reached

User instruction: resolve the two deferred research dependencies sequentially without intermediate
approval, then produce a defensible terminal conclusion if neither survives. No new hypothesis (no
"H57") to be manufactured merely to continue.

Phase A1 (read directly, not assumed): confirmed H_MEANREV_010's own eligibility definition is
single-stock-FUTURES availability specifically (Dhan's FUTSTK instrument type), a static
current-snapshot applied uniformly across the whole 10-year backtest. Ban-list/zero-volume-contract
treatment judged out of scope (the research trades the underlying equity, not the derivative
contract itself).

Phase A2: investigated NSE's own archive structure live. Found and directly verified (real HTTP
status codes, not assumed) two distinct bhavcopy generations spanning the required window: a
classic archive (archives.nseindia.com, confirmed 200 for 2016-01, 2019-01, 2022-06, 2024-01,
2024-06; confirmed 404 for 2024-07 and later) and a UDiFF archive (nsearchives.nseindia.com,
confirmed 200 for 2026-09; confirmed 404 for 2022-06). Downloaded one real file from each format
(766KB and 1.1MB) via a plain scripted HTTPS GET and inspected the actual schema: classic uses an
INSTRUMENT=="FUTSTK" column (198 underlyings in the 2022-06 sample); UDiFF uses FinInstrmTp==
"STF" (210 underlyings in the 2026-09 sample) -- both directly analogous to Dhan's own FUTSTK
definition, confirming the archive is usable for this exact research question. A real rate-limiting/
bot-protection signal was encountered from NSE's own infrastructure after roughly a dozen rapid
requests (subsequent same-session requests failed before even reaching the network) -- investigation
stopped there rather than retried aggressively, consistent with "do not download years of files
blindly."

Phase A3: built quant_research/point_in_time_fno_universe.py (dated bhavcopy retrieval with
format-aware fallback, FUTSTK/STF parsing, full provenance, never-fabricate guarantee) and
tests/test_point_in_time_fno_universe.py (14 tests, all passing, using small real-row fixtures
excerpted from the two downloaded files -- matching this project's own established fixture
convention, not the full proprietary archive files, which were not committed).

Phase A4: sampled-date completeness table produced (representative, not exhaustive, per the
mission's own instruction). The materially more important finding: diffing the verified 2022-06
FUTSTK set against today's Dhan-derived set found 68 lost-eligibility candidates and 78 gained
candidates across just one 4-year gap. Directly tested (via this project's own market data provider)
whether all 68 lost symbols are fetchable under their historical ticker: 54/68 (79.4%) fetch
cleanly; 14/68 (20.6%) do NOT -- Yahoo Finance itself reports "possibly delisted" for the exact
historical ticker, including large, currently very actively-traded names undergoing a corporate
action (HDFC/HDFCBANK merger, MINDTREE+LTI/LTIMINDTREE merger, SRTRANSFIN/SHRIRAMFIN rename,
MCDOWELL-N/UNITDSPR rename, IDFC demerger, PVR/PVRINOX merger, and TATAMOTORS itself following its
2024 demerger).

Phase A5 decision: Classification B (reconstructable with explicit gaps), and the gaps are
MATERIAL, not immaterial -- reasoning: the whole point of a point-in-time correction is to determine
how much of H_MEANREV_010's result depends on the survivorship-exposed EXPANDED_ONLY population
(already quantified at 140.8% of net return from only 14.7% of trade count in Phase 4), and that is
EXACTLY where corporate-action/rename noise concentrates. A naive "exclude unfetchable symbols"
implementation would introduce a NEW, different, undisclosed selection bias (favoring corporately
quiet stocks), not a genuine fix. Per the mission's own explicit branching for this outcome,
Phase A7 (the point-in-time H_MEANREV replay) was NOT executed this session. Phases A8-A10
consequently do not apply.

Phase B1-B3: preregistered docs/research/H_CONTEXT_MARKET_006_VOLATILITY_REGIME_
PREREGISTRATION.md BEFORE running anything. Selected ONE small, pre-justified regime variable --
NIFTY's own realized-volatility regime, via already-existing, already-tested infrastructure
(quant_research/context_experiments.py::build_benchmark_volatility_series, wrapping
backtesting/regime.py::classify_volatility_at, unmodified defaults) -- economically motivated
(mean-reversion/divergence effects are conventionally understood to behave differently across
volatility regimes) and explicitly distinct from the base condition (trend direction) under test.
India VIX regime was named as an available alternative and explicitly deferred, not tested, to keep
the set small.

Phase B4: executed audit/edge_feasibility/scripts/h_context_market_006_volatility_regime.py.
The unconditioned control cross-checked EXACTLY against H_CONTEXT_MARKET_005's own already-recorded
numbers (validity confirmed). Bucketed result: LOW_VOLATILITY structurally empty (n=0) in all three
splits (NIFTY trending-down and NIFTY low-volatility are close to mutually exclusive); the dominant,
best-powered NORMAL_VOLATILITY bucket (~90% of observations in every split) reproduces the control's
own exact era-instability pattern unchanged (negative development, positive validation/out-of
-sample); HIGH_VOLATILITY, where powered, points AWAY from a stabilizing explanation (more negative
in development, flat/non-decisive out-of-sample).

Phase B5: per the user's own "if OOS fails, close the hypothesis" instruction, this explanatory
hypothesis is closed. Added to the registry as H_CONTEXT_MARKET_006, status REJECTED (the
explanatory mechanism specifically -- H_CONTEXT_MARKET_002/004/005's own historical verdicts left
unmodified, per the no-retroactive-rewrite rule). Registry now 57 entries: 34 REJECTED / 22
INCONCLUSIVE / 1 SUPPORTED.

Phase C: final classification produced in PHASE_C_FINAL_RESEARCH_DECISION.md: 3 -- NO
DEMONSTRATED EDGE WITH CURRENT DATA. Both leading candidates fail for independent, non-overlapping
reasons (F_MEANREV: portfolio-construction collapse plus a now-confirmed-material universe
-correction blocker; F_CONTEXT: era instability unexplained by the one regime variable tested). Not
classified as data-insufficient -- substantial real data and rigorous infrastructure were used
throughout. No new hypothesis manufactured to continue, per the mission's own explicit instruction.
Two deferred follow-on tasks (a corporate-action-resolution layer; a VIX-regime follow-up) are named
precisely and left for a human resource-allocation decision, not started automatically.

Live fleet checked non-disruptively multiple times: unchanged, healthy, no action taken. Full
regression run before committing (see commit message for pass/fail counts). Zero production
strategy/RiskEngine/order-execution code modified.

Deliverables this session: quant_research/point_in_time_fno_universe.py,
tests/test_point_in_time_fno_universe.py,
docs/research/H_CONTEXT_MARKET_006_VOLATILITY_REGIME_PREREGISTRATION.md,
audit/edge_feasibility/scripts/h_context_market_006_volatility_regime.py,
PHASE_A_POINT_IN_TIME_UNIVERSE.md, H_CONTEXT_MARKET_006_RESULTS.md,
PHASE_B_CONTEXT_REGIME_INVESTIGATION.md, PHASE_C_FINAL_RESEARCH_DECISION.md,
strategy/hypothesis_registry.py (H_CONTEXT_MARKET_006 added), STATE.json (updated).
