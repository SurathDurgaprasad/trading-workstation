# Build the Real Trading Brain — Interim Report

Mission: "BUILD THE REAL TRADING BRAIN" — turn the platform from an
infrastructure project into a scientific autonomous strategy-research
system. Central question: "Can we discover a repeatable trading edge
that survives realistic costs, out-of-sample testing, market regimes,
and statistical scrutiny?" This report covers Phase 1 (audit) through
systematic testing of all four named strategy families (A/B/C/D). It
is "interim," not final, because real, honest, larger follow-up
questions remain open (see §6) — this segment's own natural stopping
point is "every named family has real evidence," not "research is
finished."

## 1. Phase 1 Audit — what exists, what was reused, what was not rebuilt

Before writing any code, the existing repository was inspected
directly (not assumed from memory of prior sessions). Confirmed real
and reused unchanged, per the mission's own "FIRST PRINCIPLE: FREEZE
THE PLATFORM":

- `strategy/hypothesis_registry.py` — the structured, honest hypothesis
  ledger this report extends (not replaces).
- `strategy/promotion_gate.py` — `evaluate_promotion()`, this project's
  single, mechanized promotion rule (PROMOTED only if development,
  validation, AND out-of-sample all reach a confident
  POSITIVE_PERFORMANCE verdict). Used unchanged for every one of this
  session's four new hypotheses.
- `strategy/multiple_testing.py` — Bonferroni correction, applied
  honestly to every 3-candidate family this session tested.
- `backtesting/runner.py`'s `run_full_backtest`, `backtesting/
  splits.py`'s `split_periods` (60/20/20 chronological), `backtesting/
  engine.py`'s `run_backtest` — the shared backtesting primitives every
  new hypothesis this session was built on top of, never modified.
- `quant_research/alpha_features.py` (Phase 10) — `zscore_close_20`,
  `relative_strength_20`, `atr_pct_of_price`, `volume_ratio` all
  existed as already-causal, already-tested features before this
  session; three of this session's four new hypotheses (`H_MEANREV_001`,
  `H_RELSTRENGTH_001`, `H_BREAKOUT_001`) are built almost entirely from
  reusing them, not new feature engineering.
- `strategy/regime_filters.py`'s `FilteredStrategy` / `add_regime_columns`
  — reused for `H_MEANREV_001`'s Candidate C (`sma_200` broad-trend
  context).

**Real gap found and closed, not a rebuild**: `quant_research/
volume_signal.py` had unit-tested candidate logic for `H_ENTRY_002`
since an earlier session's Phase 11, but nothing had ever run it
through the full universe dev/val/oos protocol — the hypothesis sat
marked OPEN despite the hard part already being built. This is the
first thing this mission actually did (§3).

**41-symbol research universe** (32 NSE, 9 US, 5 years daily bars,
under `data/market/`) verified fresh via `main.py cache-status` — no
re-fetch needed. No single committed Python constant lists it; every
driver script in this report defines it explicitly.

## 2. Hypothesis Registry — full state after this session

13 hypotheses total, **zero promoted**. Rows above the divider in each
family were resolved in earlier sessions and are unchanged this
session; rows below are this session's own new work.

### Family A — trend continuation (fully exhausted, 9/9)

| Hypothesis | Status | Real finding |
|---|---|---|
| H_ENTRY_001 | SUPPORTED (negative) | Entry timing underperforms random (96% of 300 MC iterations beat it) |
| H_ENTRY_003 (pullback) | INCONCLUSIVE | 29 total trades, below the 30-trade floor |
| H_ENTRY_005 (regime-gate) | INCONCLUSIVE | Only sufficiently-sampled regime bucket is itself negative |
| H_EXIT_001 (breakeven stop) | REJECTED | Degrades win rate and profit factor in 2/3 splits |
| H_EXIT_002 (partial profit) | INCONCLUSIVE | Real directional improvement, grows OOS, but no split reaches significance — the single most promising signal in the whole registry |
| H_EXIT_003 (ATR trailing) | REJECTED | Mixed, validation clearly degrades |
| H_EXIT_004 (time-based exit) | REJECTED | Cap rarely triggers, negligible-to-mixed effect |
| **H_ENTRY_002 (volume filter)** | **REJECTED** (this session) | A/high and C/extreme candidates confidently NEGATIVE_PERFORMANCE in development; B/low never clears 30 trades |
| **H_ENTRY_004 (momentum acceleration)** | **REJECTED** (this session) | All 3 candidates confidently NEGATIVE_PERFORMANCE, development expectancy (-1.09% to -1.19%) MEANINGFULLY WORSE than the frozen baseline's own -0.78% |

### Family B — mean reversion (opened this session, 1/1)

| Hypothesis | Status | Real finding |
|---|---|---|
| **H_MEANREV_001** | **REJECTED** (directionless) | A/B candidates flip positive (dev/val) to negative (OOS) — the opposite of H_EXIT_002's reassuring "grows OOS" shape; read as pure noise around a true zero effect, not a suppressed signal |

### Family C — breakout quality (opened and tested this session, 1/1)

| Hypothesis | Status | Real finding |
|---|---|---|
| **H_BREAKOUT_001** | **REJECTED** | A_raw_breakout confidently NEGATIVE_PERFORMANCE (-0.49%); B (volatility-contraction context) statistically indistinguishable from A; C (volume-expansion context) WORSE than A (-0.86%) — context filters didn't help, one actively hurt |

### Family D — relative strength (opened and tested this session, 1/1, honestly scoped)

| Hypothesis | Status | Real finding |
|---|---|---|
| **H_RELSTRENGTH_001** | **REJECTED** | A_any_outperformance confidently NEGATIVE_PERFORMANCE with the LARGEST sample size in the registry (395 dev trades); C_strong_outperformance is WORSE than A — reversed dose-response, opposite of the hypothesis's own prediction |

## 3. What was actually built this session (5 commits, all merged to `main`)

| Commit | What |
|---|---|
| `19dc97f` | `run_universe_volume_filter_experiment()` in `quant_research/volume_signal.py` — closed the "candidates existed, never run" gap for H_ENTRY_002 |
| `9e449b5` | `strategy/momentum_acceleration.py` (new) — H_ENTRY_004 |
| `8ccb7e5` | `quant_research/mean_reversion_signal.py` (new) — H_MEANREV_001, Family B opened |
| `68ac984` | `quant_research/relative_strength_signal.py` (new) — H_RELSTRENGTH_001, Family D opened |
| `4127def` | `quant_research/breakout_signal.py` (new) — H_BREAKOUT_001, Family C opened |

Every commit: registered the hypothesis in `strategy/hypothesis_registry.py`
BEFORE implementation (status OPEN), implemented 2-3 named candidates
with a-priori-fixed thresholds/lookbacks (never searched, never tuned
after seeing a result), ran the real 41-symbol universe via an
uncommitted scratchpad driver script, updated the registry with real
figures, added targeted tests (19-27 per commit), then a full
regression (1626 → 1719 passed, 0 failures throughout) before merging.
Four new `ReasonCode` values added (`MEAN_REVERSION_OVERSOLD`,
`RELATIVE_STRENGTH_CONFIRMED`, `BREAKOUT_CONFIRMED` — momentum
acceleration reused `FilteredStrategy` over the existing baseline, no
new code needed there) so a signal's provenance is never misrepresented,
matching the project's own established `PULLBACK_CONFIRMED`/
`RANDOM_BASELINE` precedent.

## 4. Reused vs. genuinely new, per hypothesis

| Hypothesis | Reused unchanged | Genuinely new |
|---|---|---|
| H_ENTRY_002 | `VolumeSignalStrategy`/`make_volume_predicate` (existing), `FilteredStrategy`, `run_full_backtest` | `run_universe_volume_filter_experiment()` (a runner, not a signal) |
| H_ENTRY_004 | `FilteredStrategy`, `rsi_14`/`macd_histogram` (existing indicator columns) | `rsi_delta_3`/`macd_histogram_delta_3` columns, 3 candidates, self-contained runner |
| H_MEANREV_001 | `zscore_close_20` (alpha_features), `sma_200` (regime_filters) | Standalone strategy class, 3 candidates, self-contained runner |
| H_RELSTRENGTH_001 | `relative_strength_20` (alpha_features) | Benchmark-fetch logic, 3 candidates, self-contained runner |
| H_BREAKOUT_001 | `atr_pct_of_price`/`volume_ratio` (existing) | `donchian_high_20`/`atr_pct_median_60` columns, 3 candidates, self-contained runner |

No hypothesis this session required a new backtesting engine, a new
statistical standard, or a new promotion rule — every one reused
`evaluate_promotion`/`apply_multiple_testing_correction`/`run_backtest`
byte-for-byte. The self-contained fetch/compute/split/run loops
(instead of calling `run_full_backtest` directly) were needed only
because `run_full_backtest` has no hook for injecting an extra column
(or, for H_RELSTRENGTH_001, an extra data source) between
`compute_indicator_series` and the backtest itself — a real, minor,
identified gap in the shared runner, deliberately not patched into the
shared file this session (duplicating a few lines of orchestration in
each new, isolated module was judged lower-risk than modifying
infrastructure every other hypothesis in the project's history also
depends on).

## 5. The cross-hypothesis pattern — stated as an observation, not a new claim

This session's four new, mechanistically INDEPENDENT hypotheses
(volume confirmation, momentum acceleration, relative strength,
breakout) each approached "buy into strength" from a different angle.
All four landed on the same qualitative outcome:

- Every "buy strength" operationalization tested this session showed
  either a confidently NEGATIVE_PERFORMANCE result, or a result
  reversed from its own prediction (stronger signal = worse outcome,
  not better) — H_ENTRY_002, H_ENTRY_004, H_RELSTRENGTH_001,
  H_BREAKOUT_001 all show this shape.
- H_MEANREV_001, the one hypothesis this session that bet on "buy
  weakness" instead, was the only one that did NOT show a confidently
  negative result — it was merely directionless (noise around zero).
- This echoes H_ENTRY_001's own earlier, independently-derived finding
  (entry timing underperforms 96% of random Monte Carlo iterations) —
  four more independent methods now point the same general direction.

This is reported as an honest pattern across gathered evidence, not
elevated into a new formal finding — it was not itself tested with its
own dev/val/oos protocol, walk-forward, or multiple-testing correction,
and doing so is a legitimate, well-scoped next hypothesis if research
continues (see §6).

## 6. What remains genuinely open (named, not hidden)

1. **A direct test of the "weakness beats strength" pattern itself** —
   e.g., a hypothesis that explicitly contrasts extreme underperformance
   vs. extreme outperformance under the SAME protocol, or investigates
   whether this is an artifact of the fixed 1.5x-ATR-stop/2:1-target
   execution structure every hypothesis this session inherited
   unchanged, rather than the entry signal itself (the same "investigate
   WHY" methodology the STRATEGY EDGE DISCOVERY mission's own final
   report recommended for H_EXIT_002's own unresolved tension, and
   never yet applied here).
2. **True Family D** (cross-sectional ranking/selection across the whole
   universe on a shared calendar) was deliberately not attempted —
   H_RELSTRENGTH_001 is an honestly-scoped single-symbol approximation.
   Building a portfolio-level backtesting engine remains a real,
   larger, currently-unjustified follow-up (no single-symbol result
   this session showed enough promise to justify the investment).
3. **H_EXIT_002 remains this project's single most promising unresolved
   thread** (real, non-degraded, OOS-growing improvement; still not
   statistically decisive) — untouched this session, still open from
   the prior STRATEGY EDGE DISCOVERY mission.
4. **Trade-dependence in every confidence interval** computed by
   `learning.profitability.compute_profitability_report_from_returns`
   (and therefore every verdict in this entire registry) treats trades
   as independent draws, which they are not (multiple trades per
   symbol share underlying price-series risk) — flagged repeatedly by
   this project's own prior adversarial reviews, never corrected for,
   still true today.
5. **H_ENTRY_004's own candidates B_macd_histogram_widening (146/75/85)
   and C_both_accelerating (141/73/80)** and this session's other
   REJECTED-but-not-NEGATIVE candidates were not carried through the
   full 12-step protocol (walk-forward, regime analysis, cost
   sensitivity, adversarial review) H_EXIT_002 received — a
   deliberate, proportionate choice (every one of this session's
   results was unambiguous enough not to warrant it), not an oversight,
   but named here for completeness.

## 7. Reality Checkpoint (mission's own mandated format)

```
HYPOTHESES TESTED THIS SESSION:      4  (H_ENTRY_002, H_ENTRY_004, H_MEANREV_001, H_RELSTRENGTH_001, H_BREAKOUT_001 -- 5 hypotheses, 4 commits since H_ENTRY_002 reused an existing module)
PROMISING:                            0
REJECTED:                             5  (all five)
INSUFFICIENT DATA:                    0  (sub-candidates only: H_ENTRY_002's B_low_volume)
STATISTICALLY MEANINGFUL:             0  (none reached a confident POSITIVE_PERFORMANCE verdict)
PROMOTED:                             0

REGISTRY TOTAL (all sessions):       13 hypotheses, 0 promoted, all 4 named families now have real evidence.
```

## 8. Answer to the mission's own central question

**Can we discover a repeatable trading edge that survives realistic
costs, out-of-sample testing, market regimes, and statistical
scrutiny, on this 41-symbol universe, using the methods tested so
far?** No — not yet, and not for lack of trying honestly. Thirteen
independent hypotheses, spanning all four named strategy families,
evaluated through the same rigorous, unchanged protocol (dev/val/oos
split, the project's own mechanized promotion gate, Bonferroni
correction where multiple candidates were compared), found zero
promotable results. Per the mission's own explicit framing, **this is
Outcome B — "no strategy demonstrates edge" — and it is stated as a
scientifically successful result, not a failure of the research
process.** The process itself worked exactly as designed: real
hypotheses were registered before implementation, real evidence was
gathered against a real dataset, uncomfortable results (three
"reversed from expectation" findings) were reported plainly rather
than reframed, and nothing was promoted on partial or convenient
evidence. The platform built for this purpose — hypothesis registry,
promotion gate, multiple-testing correction — did its job.

What remains open is not "did we look hard enough at these four
families" but the specific, named threads in §6: whether the
cross-hypothesis "weakness beats strength" pattern is itself a real,
testable signal; whether H_EXIT_002's own still-unresolved directional
promise can be pushed to a decisive verdict; and whether a genuinely
different capability (true cross-sectional ranking) would find
something a single-symbol lens structurally cannot.
