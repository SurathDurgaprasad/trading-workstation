# H_MEANREV_013 — Candidate Clustering, Pre-Registration

Written and frozen **before** the analysis runs, per this project's own established discipline
(every `H_MEANREV_*` entry preregisters this way). This is an AUDIT analysis (part of the
edge-feasibility audit, `audit/edge_feasibility/`), not a new production hypothesis entry in
`strategy/hypothesis_registry.py` — it will be written up there only if/when it graduates into one,
per the user's own "don't start H57 yet" instruction. Executed strictly offline, after today's live
NSE session closes; the live fleet is never touched by this work.

## 1. Research question

`H_MEANREV_011` found that `MAX_CONCURRENT_POSITIONS=4` rejects 82-93% of candidate signals,
predominantly by capacity (45-50% of all candidates, before cash). `H_MEANREV_012` ruled out
"the accepted subset is just the weaker signals" as the mechanism (strength-based ranking made
validation materially worse, not better). The preregistration's own stated [INFERENCE], never
[TESTED]: heavy capacity-driven rejection implies many symbols become oversold simultaneously,
consistent with a market-wide phenomenon, not independent idiosyncratic dips.

**Question, exactly as specified**: when many symbols become oversold simultaneously, is the
apparent mean-reversion edge concentrated in isolated (low-clustering) signals, while clustered
signals occur during broad market stress and behave differently?

## 2. What will NOT change

The frozen `H_MEANREV_006` entry predicate (`_oversold_2std_relative_weak`,
`quant_research/mean_reversion_signal.py`, unmodified), the frozen h10 time-based exit
(`compute_fixed_notional_trade`, unmodified), the COMBINED 206-symbol universe, and the existing
development/validation/out-of-sample calendar boundaries (`shared_period_boundaries`) are all
reused exactly as-is. No parameter is retuned to make this analysis or its outcome more favorable.
No universe change (the survivorship-bias question, §7, is measured, not fixed, here).

## 3. What is genuinely new

This analysis operates on `collect_candidate_events`'s own output (every candidate event, not just
accepted ones) plus each event's own forward h10 return computed directly and independently of
capacity/cash acceptance — i.e., every candidate is priced through `compute_fixed_notional_trade`'s
own entry/exit/cost math AS IF it had been accepted alone with its own dedicated capital slot
(matching `H_MEANREV_010`'s own already-validated fixed-notional, single-position costing — reused,
not reinvented), regardless of whether the real portfolio scheduler (`H_MEANREV_011`) actually
accepted it. This is what makes it possible to measure the REJECTED candidates' own subsequent
performance, which no prior entry in this family has computed.

## 4. Per-day metrics (frozen list, computed for every calendar day with >=1 candidate event)

- Number of simultaneous qualifying candidates that day.
- Number the real `schedule_portfolio` (H_MEANREV_011's own control, unmodified) actually accepted.
- Number rejected specifically for capacity (portfolio already at the 4-position cap).
- ^NSEI (NIFTY) same-day return (already-available benchmark series, reused).
- A same-day volatility proxy: ^NSEI's own realized range or ATR-style measure over a short trailing
  window (exact choice frozen before the analysis runs — see reproducibility note, uses whatever
  this project's existing `market_intelligence.regime`/`market.indicators` volatility function
  already computes, not a newly invented formula).
- Market breadth that day: the existing `market_intelligence.market_breadth`/H_BREADTH_001
  infrastructure's own breadth measure (fraction of the universe with a qualifying up/down
  condition), reused, not reinvented.
- Mean and median `zscore_close_20` across that day's own candidates.
- Mean/median subsequent h10 return across ALL candidates that day (accepted and rejected pooled).
- Mean/median subsequent h10 return restricted to ACCEPTED candidates only.
- Mean/median subsequent h10 return restricted to REJECTED (capacity-only) candidates only.

## 5. Pre-registered clustering bins (frozen, not chosen after seeing results)

```
1 candidate
2 candidates
3-4 candidates
5-9 candidates
10+ candidates
```

## 6. Pre-registered comparison and decision rule

**Primary test**: does mean/median forward h10 return (net of `CostModel.india_nse_intraday_2026()`,
same as every prior entry in this family; ALL candidates pooled per bin, not just accepted ones)
deteriorate monotonically-or-near-monotonically as the bin's own candidate count increases?

**Pre-registered interpretation, exactly as specified by the user**:

- **Monotonic decline** (few candidates -> positive, many candidates -> negative or clearly worse):
  clustering is a real, economically meaningful mechanism. Next step: investigate whether it reflects
  genuine market-wide regime risk (correlated drawdown) vs. a measurement artifact.
- **Flat-or-positive across all bins** (few -> positive, medium -> positive, many -> positive, no
  clear degradation): capacity is most likely an IMPLEMENTATION problem (the portfolio should accept
  more positions, or size them differently, not avoid clustered days) rather than a genuine risk
  signal. This does NOT by itself justify raising `MAX_CONCURRENT_POSITIONS` in this analysis --
  that remains a separate, later, explicitly-flagged decision (see §8).
- **Random/unstable/no consistent pattern across splits**: the clustering hypothesis is not
  supported by this evidence; H_MEANREV's open bottleneck (§17 of the H_MEANREV_011 preregistration)
  remains genuinely unresolved, not explained by this analysis.

**Statistical treatment**: report bin-level means with confidence intervals via the same
`learning.profitability.compute_profitability_report_from_returns` machinery every other entry in
this family already uses (not a new statistical test invented for this analysis), applied per bin
per split (development/validation/out-of-sample), plus a pooled cross-split view disclosed as
descriptive only (not a fourth independent statistical test — the three real splits remain the
decisive evidence, matching this project's own established convention). Sample size per bin is
expected to be uneven (few-candidate days are common, 10+-candidate days are rare by construction);
any bin below the project's own 30-observation floor is reported as `INSUFFICIENT_DATA` for that
bin specifically, not silently dropped or merged into an adjacent bin after seeing the shortfall.

## 7. Survivorship bias — measured, not fixed, in this same pass

Per explicit user instruction: this analysis does NOT construct a point-in-time-correct historical
universe (no such data source exists in this project, per `H_XSECT_006`'s own S2 disclosure). It
DOES report the fraction of H_MEANREV_010 Candidate 2's own total net P&L, and this analysis's own
per-bin results, attributable to the ORIGINAL 32-symbol universe versus the EXPANDED-ONLY 176 (the
existing three-way ORIGINAL/EXPANDED-ONLY/COMBINED split machinery, reused) — as a partial, indirect
proxy for how much the result leans on the "widened via CURRENT F&O eligibility" set specifically. This
is a quantification of exposure to the bias, not a resolution of it. If a large share of any positive
result is concentrated in EXPANDED-ONLY (the set most directly built from current-not-historical
eligibility), that is reported as a material discount, not adjusted away.

## 8. What this analysis explicitly will NOT authorize by itself

Regardless of outcome, this analysis alone does not authorize: raising `MAX_CONCURRENT_POSITIONS`
above 4, lowering `capital_per_position` below 25%, or any other portfolio-construction retune. Per
the user's own explicit instruction, "don't loosen the 25% exposure limit until enough trades get
through" describes exactly the curve-fitting risk this preregistration exists to prevent. A finding
that clustering is NOT the driver would instead redirect attention to constructing a genuine
point-in-time universe before any further capital-allocation experiment, per the user's own stated
priority ("if clustering looks promising, the next major task should probably be constructing a
proper point-in-time universe... otherwise we could spend weeks analyzing an effect in a dataset that
already has a material selection bias").

## 9. Reproducibility record (filled in when the analysis actually runs, after today's NSE close)

- [ ] Dataset snapshot / instrument-master date used.
- [ ] Exact volatility-proxy function and window used (frozen at run time from this doc's own §4
      description, not chosen after seeing results).
- [ ] Script location under `audit/edge_feasibility/scripts/` (new, isolated audit script; does not
      modify `quant_research/mean_reversion_portfolio.py` or any other production file).
- [ ] Full per-bin, per-split results table.
- [ ] Verdict per §6's own pre-registered decision rule.
