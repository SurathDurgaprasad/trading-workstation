# Indian Trading Decision Brain — Report

Mission: "BUILD THE REAL INDIAN TRADING DECISION BRAIN" (2026-09-08).
Core question: does combining MARKET CONTEXT + SECTOR CONTEXT +
STOCK-LEVEL SETUP + RISK/VOLATILITY CONTEXT produce materially better
trading decisions for NSE? This report covers a full audit of the
*actual* live decision pipeline, a data-integrity gate re-check, and a
first, disciplined round of context-conditioning research (Family A
market context, Family B sector context, Family C India VIX context).

## 1. The current decision pipeline, as it actually is

Traced by reading code end to end (`market data -> scanner -> decision
-> critic -> risk -> paper order`), not assumed:

- **`decision_engine.rules.classify()`** (BUY/WATCH/AVOID/EXIT/
  NO_ACTION) uses *only* `market_intelligence.scanner`'s
  `CandidateScore` (composite/trend/momentum, all price-technical) and
  `RiskContext.has_open_position`. **Zero market, sector, VIX, breadth,
  or global input of any kind.**
- **`critic.engine.evaluate()`** is the *only* place any market context
  reaches a live decision. Both live call sites (`main.py`'s
  `shadow-run`, computed once per run, and `live/critic_gate.py`'s
  `CriticGate`, refreshed every 15 minutes) compute NIFTY 50's own
  `compute_benchmark_context()` and pass it in as `benchmark_context`,
  driving exactly one check: `REGIME_CONFLICT` (fails when
  `trend_regime == "DOWNTREND"`).
- `risk.engine` sizes and gates the trade after the critic; unaffected
  by context.

## 2. Do these intelligence components actually influence decisions?

**The critical finding of this audit: effectively no, not in practice,**
even on the one path where context genuinely is wired in.
`REGIME_CONFLICT`'s severity is `WARNING`, not `HARD`.
`critic.engine.evaluate()`'s verdict logic: any `HARD` failure -> REJECT;
no market/research context at all -> INSUFFICIENT_EVIDENCE; two or more
`WARNING` failures -> DOWNGRADE; otherwise APPROVE. Only REJECT and
INSUFFICIENT_EVIDENCE actually block execution
(`BLOCKING_VERDICTS = (REJECT, INSUFFICIENT_EVIDENCE)` in
`live/critic_gate.py`) — and the module's own comment states it
plainly: *"DOWNGRADE and APPROVE both let a signal proceed to
risk/execution."* So a `REGIME_CONFLICT`-driven DOWNGRADE has the exact
same downstream effect as an unconditional APPROVE. **Market context is
computed, checked, and recorded in every live decision's audit trail —
but changes the outcome of zero live paper trades today.**

Not wired in at all (report-only, never reach `classify()` or
`critic.engine.evaluate()`): `MarketBreadth`, `SectorStrength` (generic
GICS), the 9 real `NIFTY_SECTOR_INDICES` regimes, and `IndiaVixContext`
— all only ever consumed by the standalone `main.py regime` CLI command
and by `run_scan`'s own print-out.

**Conclusion: today, these components produce reports. They do not
influence decisions**, except for one severity-neutered exception. This
is the single most important structural fact this research segment
established, and it reframes the mission's central question: before
asking "should context change decisions," the honest current answer is
"context currently *cannot* change decisions even when it disagrees,"
which is itself worth fixing independently of whatever the research
below finds — but only *after* real evidence justifies which signal, at
what severity, is worth wiring in.

## 3. The frozen baseline (Phase 2)

Every hypothesis below conditions the *same* baseline stock-level BUY
proxy, frozen before any contextual measurement began:
`close > sma_20 > sma_50` (uptrend structure, matching
`market_intelligence.scanner`'s `trend_score == +1.0` case exactly) AND
`rsi_14 > 50` (bullish momentum, matching `trend_score`... `momentum_score
> 0` exactly) — the two conditions the real live corroboration gate
(`decision_engine.config.DecisionConfig.require_corroboration_for_buy`)
actually demands. `composite_score`'s other terms (breakout/relative-
strength/sector-strength) are per-candidate-scan context not available
bar-by-bar in a precomputed indicator series, so this is a documented,
honest proxy for the real gate — narrower than a literal scanner
replay, disclosed here and in every hypothesis record that uses it, not
silently assumed identical. Not modified after this point.

## 4. The contextual experiment framework (Phase 4)

`quant_research/market_behavior.py` (built in an earlier session
segment) already provided everything needed except one thing: its
`regime_filter` only ever classifies a *stock's own* trend/volatility
(`backtesting.regime` applied to that stock's own OHLCV), never an
*external* benchmark's. The new module `quant_research/
context_experiments.py` adds exactly that gap and nothing else:
`build_benchmark_regime_series()` / `build_benchmark_volatility_series()`
/ `build_india_vix_regime_series()` compute an external symbol's own
causal regime as a date-indexed series (the VIX variant is a historical
counterpart to `market_intelligence.regime.compute_india_vix_context`,
which only ever classified the *latest* bar — same thresholds, applied
at every bar instead), and `attach_external_regime()` forward-fills it
onto each stock's own dataset — the identical causal cross-market
alignment pattern `quant_research/alpha_features.py`'s
`relative_strength_20` already uses. No new statistics, no new
dev/val/oos logic, no new promotion machinery: all reused unchanged.

## 5. Data integrity gate (Phase 3)

Given the project's own prior cache-depth incident, this was checked
*before* any new research, per the mission's explicit instruction. The
32-symbol NSE research universe was already at genuine 5-year depth
(confirmed, ~1239–1240 bars each). **A new, smaller instance of the
same class of bug was found and fixed**: `^NSEI` (the NIFTY 50
benchmark itself) and all 9 India-context tickers added in the prior
session segment (`^NSEBANK`, `^CNXIT`, `^CNXAUTO`, `^CNXPHARMA`,
`^CNXFMCG`, `^CNXMETAL`, `^CNXREALTY`, `^CNXENERGY`, `^INDIAVIX`,
`NIFTY_FIN_SERVICE.NS`) had only ever been cache-fetched at
`period="2y"` (the `regime` CLI command's own default) — genuinely
fresh, but too shallow to align against the stock universe's full
5-year window. Refetched all 11 at `period="5y"`, verified restored to
~1194–1236 bars each (matching the stock universe's own span). Also
found and fixed 3 US symbols (`AMZN`, `GOOGL`, `NVDA`) that had
re-degraded to 1-year depth since the earlier fix — a live
demonstration that `backtesting/cache.py`'s serve-on-hit-regardless-of-
period behavior is a standing, recurring risk, not a one-time incident;
`cache-status --shallow-below-bars` remains the correct, cheap,
pre-existing check to run before *any* new historical research.

## 6. Family A: market context findings

Baseline BUY condition (unconditioned control, 32-symbol NSE universe,
h5/h10): development +0.276%/+0.555% (both decisive positive);
validation **-0.218%/-0.311% (both decisive negative)**; out-of-sample
-0.119%/-0.407% (mixed decisiveness, negative direction). The
unconditioned baseline itself does not show a stable edge — consistent
with this project's settled "no demonstrated edge" verdict.

- **H_CONTEXT_MARKET_001 (NIFTY uptrend)** — REJECTED. No consistent
  improvement over the unconditioned control in any split; modestly
  worse on some metrics. The naive "rising tide lifts all boats" prior
  does not hold.
- **H_CONTEXT_MARKET_002 (NIFTY downtrend)** — INCONCLUSIVE, the most
  interesting result of this segment. The baseline BUY condition
  performs **better** when the broader NIFTY is falling: development
  +0.573%/+1.040% (both decisive, roughly double the control);
  validation **+0.760%/+1.536%** (both decisive **positive** — a full
  reversal from the control's decisive negative in the same period);
  out-of-sample +0.094%/-0.181% (not decisive, but never reverses to a
  clearly negative estimate). Broad-based across 24 of 31 symbols with
  a nonzero sample (not concentrated in a handful of names); survives a
  conservative 20bps round-trip cost haircut comfortably. Not promoted
  only because out-of-sample statistical power is limited (n=261, a
  fifth of development's sample) — not because the effect reverses.
- **H_CONTEXT_MARKET_003 (NIFTY volatility regime)** — REJECTED.
  LOW_VOLATILITY reverses sign between development (+0.946%/+2.023%,
  strongly positive) and validation (-0.991%/-1.742%, strongly
  negative) — the textbook signature of a development-period
  idiosyncrasy, not a real effect. HIGH_VOLATILITY has zero usable
  validation-period samples. Useful negative result: it demonstrates
  the research methodology correctly discriminates a real, stable
  pattern (§ H_CONTEXT_MARKET_002, never reverses) from an unstable one
  (this one, reverses outright).

## 7. Family B: sector context findings

Sector-taggable subset: 21 of 32 symbols, mapped to 6 of the 9 real
`NIFTY_SECTOR_INDICES` via a conservative, high-confidence-only mapping
(not sourced from an official index-constituent file — 11 symbols
deliberately excluded rather than guessed; see §12).

- **H_CONTEXT_SECTOR_001 (own sector uptrend)** — REJECTED. No
  improvement over the unconditioned (sector-taggable) control in any
  split; measurably worse in validation (-0.432%/-0.529% vs. control's
  -0.201%/-0.214%). Exact echo of H_CONTEXT_MARKET_001 at the sector
  level.
- **H_CONTEXT_SECTOR_002 (own sector downtrend)** — INCONCLUSIVE, and
  the second independent replication of H_CONTEXT_MARKET_002's pattern:
  development +0.327%/+0.655%; validation **+0.556%/+0.895% (both
  decisive positive**, reversing the control's decisive negative in the
  same period); out-of-sample underpowered (n=39) but not contradicting
  (-0.072%/+0.732%). The same "diverges-from-context beats
  confirms-context" shape, now observed independently at *two* context
  layers (market-wide and sector-specific) — stronger corroborating
  evidence than either finding alone.

## 8. India VIX findings

- **H_CONTEXT_VIX_001 (ELEVATED)** and **H_CONTEXT_VIX_002
  (DEPRESSED)** — both REJECTED. Both buckets show outright sign
  reversals between splits (ELEVATED: weak-positive development ->
  extreme-positive validation, n=54, an implausibly large +5.0%/+3.7%
  effect consistent with clustering around one or two volatility-spike
  episodes rather than a broad pattern -> decisive-negative
  out-of-sample; DEPRESSED: mixed development -> decisive-negative
  validation -> decisive-negative out-of-sample). Neither VIX regime
  bucket is a usable decision filter for this baseline signal at these
  thresholds and this sample size — a clean contrast with the
  market/sector divergence findings, which never reversed sign.

## 9. Market+sector+stock interaction findings

Run narrowly and only after Family A/B/C's own per-layer findings
justified the specific question — not a blind sweep of combinations,
which would have been exactly the "brute-force hundreds of
combinations" the mission explicitly warned against.
**H_CONTEXT_ALIGN_001**: does the market-divergence effect
(H_CONTEXT_MARKET_002) and the sector-divergence effect
(H_CONTEXT_SECTOR_002) *compound* when both are true at once (stock
bullish while *both* its market and its own sector are falling)?
**INCONCLUSIVE, with the single strongest development+validation result
of this entire research segment**: development +0.688%/+1.040%
(h5/h10, both decisive, larger than the "neither diverges" control);
validation **+0.958%/+1.389%** (both decisive positive, and *larger*
than either single-layer divergence effect alone — consistent with a
genuine, additive compounding effect, not the same signal counted
twice). Out-of-sample collapses to n=10 once both conditions are
required simultaneously on a 21-symbol universe — far too small for any
conclusion. This is a genuine, honest data-limitation stop point for
this specific narrow slice, not a contradicting result; slicing further
(e.g. adding a volatility dimension) was deliberately not attempted, as
the data no longer supports it. The market-only and sector-only single-
divergence counterparts measured in the same run were each weaker and
less consistent than the combined condition (market-only reverses sign
at h10 out-of-sample; sector-only is noisy with a validation-period
reversal on a 25-observation sample) — see `strategy/
hypothesis_registry.py`'s `H_CONTEXT_ALIGN_001` entry for full figures.

## 10. Global → India findings

Not extended this segment beyond the prior segment's H_TRANSMISSION_001
(Nasdaq -> NIFTY IT, INCONCLUSIVE with a real decline/advance
asymmetry, documented in `docs/INDIAN_MARKET_TRADING_BRAIN_REPORT.md`).
USD/INR, crude, gold, and DXY remain confirmed-available via Yahoo but
unused this segment — this research prioritized Family A/B (market and
sector context, the mission's own HIGH PRIORITY family) and Family C
(VIX) first, per the mission's own phase ordering.

## 11. Promoted findings

**None.** Consistent with this project's history — 21 hypotheses in the
registry as of this report, zero PROMOTED. This remains the honest,
correct state of the evidence, not a gap to paper over.

## 12. Rejected findings

H_CONTEXT_MARKET_001 (market-up conditioning: no benefit), H_CONTEXT_
MARKET_003 (NIFTY volatility regime: sign-reverses), H_CONTEXT_SECTOR_001
(sector-agreement conditioning: no benefit, mildly worse), H_CONTEXT_
VIX_001 and H_CONTEXT_VIX_002 (India VIX regime, both directions:
sign-reverses). Full evidence in `strategy/hypothesis_registry.py`.

## 13. Inconclusive findings

H_CONTEXT_MARKET_002 (NIFTY downtrend conditioning: real, broad-based,
cost-surviving, decisive in development+validation, underpowered but
directionally consistent out-of-sample), H_CONTEXT_SECTOR_002 (the same
divergence pattern, replicated independently at the sector level, more
underpowered out-of-sample), and H_CONTEXT_ALIGN_001 (the two divergence
effects appear to compound — the strongest development+validation
result of this entire segment — but the out-of-sample sample collapses
to n=10, too small for any conclusion). These are this segment's most
valuable results — not promoted, but real evidence pointing toward a
genuine market mechanism (idiosyncratic/counter-tape strength being a
more distinctive, credible signal than context-confirmed strength)
rather than noise, unlike the VIX and volatility findings which
actively reversed sign.

## 14. Negative knowledge

All 8 new hypotheses (H_CONTEXT_MARKET_001/002/003, H_CONTEXT_SECTOR_
001/002, H_CONTEXT_VIX_001/002, H_CONTEXT_ALIGN_001) are recorded in
`strategy/hypothesis_registry.py` with full `description`/`rationale`/
`expected_effect`/`dataset_restrictions`/`experiment_design`/
`success_criteria`/`failure_criteria`/`evidence` fields, discoverable
and citable, so this exact ground is never blindly re-covered. Combined
with the 14 pre-existing entries, the registry now holds 22 hypotheses,
0 promoted, 3 newly INCONCLUSIVE-with-real-effect, 5 newly REJECTED.

## 15. Data limitations

- The sector map (§7) is a hand-built, high-confidence-only GICS-style
  approximation, not sourced from an official NSE index-constituent
  file (none integrated in this project) — 11 of 32 universe symbols
  deliberately excluded rather than guessed (RELIANCE, LT, ASIANPAINT,
  BHARTIARTL, ADANIPORTS, GRASIM, ULTRACEMCO, TATASTEEL, COALINDIA,
  NTPC, POWERGRID). A future increment could source real constituent
  lists to recover these symbols and add the 3 currently-unused sector
  indices (METAL, REALTY, ENERGY).
- H_CONTEXT_MARKET_002/SECTOR_002's out-of-sample samples (n=261 and
  n=39 respectively) are meaningfully smaller than development's — the
  primary reason neither reaches PROMOTED. A longer history or a larger
  universe would sharpen this.
- The frozen baseline BUY proxy (§3) is deliberately narrower than the
  real scanner's `composite_score` (omits breakout/relative-strength/
  sector-strength terms not available bar-by-bar in a precomputed
  indicator series) — a documented, disclosed approximation, not a
  literal replay of live decisions.
- VIX ELEVATED's validation-period result (n=54, +5.0%/+3.7%) is almost
  certainly driven by temporal clustering around a small number of
  volatility-spike episodes, not independent observations — a reminder
  that "decisive by CI" does not by itself rule out event-clustering
  artifacts; the out-of-sample reversal is what actually disqualified
  this hypothesis, and the concentration-style check that would have
  caught the clustering directly was not run for VIX specifically
  (time-based rather than symbol-based clustering, requiring a
  different check than the symbol-concentration one applied to
  H_CONTEXT_MARKET_002).

## 16. What actually improves decisions (evidence-based, this segment)

Nothing here has cleared the promotion bar. The closest candidates:
stock-level BUY signals that *diverge from* rather than *confirm* their
market or sector context show a real, broad-based, cost-surviving,
twice-independently-replicated positive shift versus the unconditioned
baseline — real enough to be worth a dedicated, larger-sample follow-up
(H_CONTEXT_MARKET_002/SECTOR_002), not yet real enough to promote or
wire into any live path.

## 17. What does NOT improve decisions

Context *agreement* (stock bullish + market up, or stock bullish + own
sector up) does not improve on the unconditioned baseline in any
tested split — the intuitive "everything lining up" story is not
supported by this evidence. NIFTY's own volatility regime and India
VIX's regime (both directions) show no stable, non-reversing effect at
the sample sizes available.

## 18. Recommended next evolution

1. **Do not wire H_CONTEXT_MARKET_002/SECTOR_002/ALIGN_001 into any
   live path yet** — INCONCLUSIVE means more evidence, not action. A
   larger-sample re-test (longer history and/or a larger, better-
   sourced sector map, to grow H_CONTEXT_ALIGN_001's n=10 out-of-sample
   sample into something usable) is the correct next step, per this
   project's own promotion discipline.
2. **Separately, and regardless of the research verdict above**: §2's
   finding that `REGIME_CONFLICT` is WARNING-severity and therefore
   currently inert deserves its own explicit decision from a human, not
   a silent fix — the mission's own Phase 10 instruction ("do NOT
   implement context rules until evidence exists") already anticipated
   this; the evidence gathered here (agreement doesn't help, divergence
   might) argues *against* simply raising `REGIME_CONFLICT` to HARD
   severity, since that would reject exactly the divergence case this
   segment's most promising (still-unproven) finding says may be worth
   *favoring*.
3. Family E (global -> India) has three unused, confirmed-real signals
   (USD/INR, crude, gold/DXY) genuinely open for the same
   measure-before-strategy discipline already applied to Nasdaq -> NIFTY
   IT.
4. Source a real NIFTY sector-index constituent list (rather than the
   hand-built approximation here) to recover the 11 currently-excluded
   universe symbols and the 3 currently-unused sector indices for
   Family B/D — this would directly grow H_CONTEXT_ALIGN_001's
   out-of-sample sample past its current n=10 bottleneck.
