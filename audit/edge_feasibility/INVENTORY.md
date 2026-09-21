# Phase 0 — Inventory

## Correction to the audit's own starting premise

The audit brief assumed 44 hypotheses (26 REJECTED, 17 INCONCLUSIVE, 1 SUPPORTED). Verified directly
against `strategy.hypothesis_registry.build_hypothesis_registry()`:

```
venv/Scripts/python.exe -c "from strategy.hypothesis_registry import build_hypothesis_registry; ..."
```

**Actual total: 56 entries.** 33 REJECTED, 22 INCONCLUSIVE, 1 SUPPORTED (0 duplicate IDs). Of the 33
REJECTED, one (`H_BASELINE_001`) was added this session (2026-09-21) as the top-level archival record
for the baseline itself, not a pre-existing research finding — so the pre-existing research program is
55 entries: 32 REJECTED, 22 INCONCLUSIVE, 1 SUPPORTED. This correction matters because the audit's own
credibility depends on starting from the real number, not the number carried over from an earlier,
truncated CLI grep in this same session.

Full ID/status/description table: `audit/edge_feasibility/_all_56_raw.tsv` (generated directly from the
Python module, not hand-transcribed).

## Hypothesis families present

- `H_ENTRY_*` (5): timing/regime modifications to the frozen baseline's own entry rule.
- `H_EXIT_*` (5): exit-management modifications (breakeven stop, partial profit, ATR trailing stop, time exit, structural redesign).
- `H_MEANREV_*` (12): oversold mean-reversion, **the deepest single thread in the registry** — see finding below.
- `H_RELSTRENGTH_001`, `H_BREAKOUT_001`, `H_VOL_001`, `H_EXTREME_001`, `H_BREADTH_001`, `H_SECTOR_ROTATION_001`: single-shot independent-mechanism tests.
- `H_CONTEXT_MARKET_*` (5), `H_CONTEXT_SECTOR_*` (2), `H_CONTEXT_VIX_*` (2), `H_CONTEXT_ALIGN_001`: does market/sector/VIX regime context change the frozen BUY condition's own forward returns.
- `H_TRANSMISSION_*` (4): cross-market transmission (Nasdaq -> NIFTY IT, USD/INR -> IT/Pharma exporters).
- `H_GAP_*` (3): overnight gap fade/recovery.
- `H_OPENRANGE_001`, `H_CALENDAR_*` (2): opening-range and day-of-week effects.
- `H_XSECT_*` (6): cross-sectional momentum/laggard ranking, its own exit redesign, and cost-realism follow-ups.
- `H_MOMENTUM_001`: single-stock short-term weakness reversal.
- `H_BASELINE_001`: this session's new top-level archival entry for the whole frozen strategy.

## HEADLINE FINDING (flagged for priority attention in Phase 1/2)

The `H_MEANREV_006` -> `H_MEANREV_012` sub-chain is materially different in kind from every other
entry in the registry and requires its own dedicated audit pass, not the same lightweight per-entry
pass as the single-shot hypotheses:

1. **H_MEANREV_009** (first executable design, real RiskEngine sizing, real `CostModel.india_nse_intraday_2026()`):
   found a GROSS (pre-cost) positive edge consistent with the raw forward-return measurement (gross
   +0.56%/+1.97%/+1.42% dev/val/oos, win rate 53.8%-59.5%) that was completely destroyed net-of-cost
   (net -8.81%/-5.29%/-5.81%) by a diagnosed mechanism: a wide stop (needed to avoid stop-domination)
   shrinks fixed-fractional position size to near-minimum (36-39% of trades at exactly 1 share), and a
   FIXED per-fill brokerage (Rs 20, charged both legs) then consumes ~7.2%-9.4% of notional — roughly
   15x the entire gross edge.
2. **H_MEANREV_010** isolated this mechanism with two independent controls. Candidate 2 (fixed-notional
   sizing) showed validation net +1.51% (CI [+0.94%, +2.08%], CI-decisive POSITIVE_PERFORMANCE) and
   out-of-sample net +0.98% (CI [+0.52%, +1.44%], CI-decisive POSITIVE_PERFORMANCE) — development was
   STATISTICALLY_MEANINGLESS. Overall verdict INCONCLUSIVE, specifically because of (a) development's
   own non-decisiveness and (b) a disclosed, serious tail-risk concern from 100%-capital-per-position
   sizing (development worst single trade -65.03%, best +80.35%). This is the single strongest
   positive, CI-decisive, cost-inclusive result found anywhere in the registry.
3. **H_MEANREV_011** attempted a realistic multi-position portfolio (4-concurrent-position cap, 25%
   capital-per-position, matching `RiskConfig.max_exposure_pct`) to remove the disqualifying
   100%-into-one-position concentration. Result: 82%-93% of candidate signals rejected by
   capacity/cash constraints before ever reaching the one-position-per-symbol rule; sample collapsed
   from hundreds-to-thousands of trades down to 105-555; verdict reverted to STATISTICALLY_MEANINGLESS
   in all three splits (REJECTED per the project's own mechanical promotion rule, but explicitly
   disclosed as "underpowered and mixed-direction, not confirmed harm").
4. **H_MEANREV_012** tested whether the portfolio scheduler's arbitrary alphabetical tie-break (used
   under the capacity constraint) explains H_MEANREV_011's disappointment, by substituting an
   economically-motivated signal-strength ranking. Result: REJECTED — ranking did not restore the edge
   (validation got materially WORSE under ranking); the chain's own conclusion is that the arbitrary
   tie-break was NOT the dominant cause, i.e. the portfolio-capacity attrition itself, not the
   selection rule, is what is killing the single-position result at the portfolio level.

**Net state of this thread as of H_MEANREV_012: UNRESOLVED, not conclusively negative.** A real,
mechanism-diagnosed, cost-inclusive positive effect exists at the single-position level (H_MEANREV_010
Candidate 2); nobody has yet found a portfolio-construction approach that both (a) removes the
disqualifying single-position concentration risk and (b) preserves statistical power. This is the
single most important finding for Phase 4 Synthesis and directly bears on possibility C ("methodology
killing a genuine effect") — except here the methodology itself already caught, diagnosed, and
partially resolved its own confound; what remains unresolved is a genuinely hard portfolio-construction
problem, not an undetected bug.

## Promotion / experiment infrastructure

- `strategy/promotion_gate.py` (299 lines) + `strategy/promotion_store.py` (110 lines): append-only,
  persistent (`data/promotion_gate.db`) promotion-verdict evaluator. `evaluate_promotion` verdicts seen
  in registry text: PROMOTED, NEGATIVE, REJECTED, INSUFFICIENT_DATA (implies POSITIVE_PERFORMANCE /
  NEGATIVE_PERFORMANCE / STATISTICALLY_MEANINGLESS per-split classifications feed a pooled verdict).
  One real evaluation on file: `trend_momentum_baseline` -> NEGATIVE, 2026-09-05T04:56:47Z.
- `main.py experiment {start,end,list,compare,recommend}`: live-experiment comparison CLI, backed by
  `data/experiments.db`. Currently empty (0 registered) — built but not yet exercised for live-vs-paper
  comparison work.
- 30-trade minimum sample floor and Bonferroni family-wise correction are both referenced directly in
  registry text (H_MEANREV_012 cites `family_size=3, corrected z=2.394`) — real, not assumed. To be
  verified against the actual implementation in Phase 2.

## Dataset/evaluation code inventory (file list, not yet audited — Phase 1/2 work)

`backtesting/`: `baselines.py`, `cache.py`, `costs.py`, `engine.py`, `equity.py`, `execution.py`,
`execution_robustness.py`, `exit_experiments.py`, `forensics.py`, `metrics.py`, `random_baseline.py`,
`regime.py`, `report.py`, `runner.py`, `splits.py`, `trade.py`, `universe.py`, `walk_forward.py`.

`quant_research/`: `alpha_features.py`, `breakout_signal.py`, `context_experiments.py`,
`cross_sectional.py`, `cross_sectional_portfolio.py`, `cross_sectional_strategy.py`,
`market_behavior.py`, `market_breadth.py`, `mean_reversion_execution_structure.py`,
`mean_reversion_portfolio.py`, `mean_reversion_signal.py`, `relative_strength_signal.py`,
`risk_characterization.py`, `universe_expansion.py`, `us_weakness_reversal_signal.py`,
`volume_signal.py`.

## Live-fix evidence (already fully documented this session, cited not re-derived)

Commit `b99e7d7` (Dhan Ticker->Quote mode fix), `H_BASELINE_001` archival entry (commit `e0350fc`),
73 natural live signals, 43 resolved predictions (2 wins, 4.7% win rate, -0.076% mean return, 41/41
resolved stop-outs at bar 1), all under a Critic-flagged `^NSEI` DOWNTREND regime. Full detail already
in conversation record and `strategy/hypothesis_registry.py::H_BASELINE_001`; not re-derived here.

## Open items for Phase 0 completion

- [ ] Verify Bonferroni/FDR correction is a real, shared utility (not ad hoc per-entry text) — Phase 2.
- [ ] Verify the 30-trade floor is enforced in code, not just stated in prose — Phase 2.
- [ ] Confirm `CostModel.india_nse_intraday_2026()`'s exact fee schedule (the Rs 20 fixed brokerage
      claim above) against `backtesting/costs.py` directly — Phase 1/2.
- [ ] Confirm survivorship-bias handling for the 206/208-symbol "COMBINED universe" (2 symbols short of
      208 — is this delisting, a data gap, or something else?) — Phase 1.
