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
