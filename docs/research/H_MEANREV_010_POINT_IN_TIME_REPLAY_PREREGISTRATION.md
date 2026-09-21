# H_MEANREV_010 — Point-in-Time Universe Replay, Pre-Registration

Written and frozen **before** the replay's own results were inspected (the code itself was written,
reviewed for correctness against the original H_MEANREV_010 loop structure, and committed to run
before any trade-level output was read). Path 1 of the user's own capital-allocation mission
(2026-09-21): "Build the security-identity/corporate-action layer... Then determine whether the
20.6% problematic population can be recovered... If yes: Run the corrected H_MEANREV_010 once. If it
fails again, close mean reversion permanently for this research cycle. If it survives, then we
investigate whether the effect survives realistic portfolio constraints."

## 1. What is frozen, unchanged from the original H_MEANREV_010 (`docs/research/H_MEANREV_010_EXECUTION_STRUCTURE_PREREGISTRATION.md`)

- **Entry signal**: `quant_research.mean_reversion_signal._oversold_2std_relative_weak`, imported and
  reused verbatim — no threshold change, no new condition.
- **Exit**: 10-bar time-based exit (`holding_bars=10`), unchanged.
- **Sizing**: `compute_fixed_notional_trade`, `capital_per_slot=100,000`, one position at a time per
  symbol — the SAME explicitly-disclosed single-symbol-dedicated-capital simplification the original
  Candidate 2 used (not a portfolio simulation — that is the separate, subsequent step per the
  user's own sequencing, only reached if this replay survives).
- **Costs**: `CostModel.india_nse_intraday_2026()`, unchanged.
- **Splits**: `backtesting.splits.split_periods`, the same 60/20/20 per-symbol convention.
- **Loop structure**: verified line-by-line against `quant_research.mean_reversion_execution_
  structure.run_universe_fixed_notional_time_exit_experiment`'s own committed code — period-sliced
  frame, `i += holding_bars` on an accepted trade, `i += 1` otherwise. The ONLY addition is a
  point-in-time eligibility check inserted exactly where the original's own "trade is None" branch
  already lived, so an ineligible signal is treated identically to "no signal fired here" — no other
  change to loop semantics, bar arithmetic, or acceptance logic.

## 2. What is genuinely new (the one intended methodological correction)

**Universe membership is now date-varying**, built from real, dated NSE F&O bhavcopy snapshots
(`audit/edge_feasibility/scripts/build_point_in_time_snapshots.py`) instead of a single current
-Dhan-snapshot applied uniformly across 10 years:

- 11 real snapshots retrieved (annual anchors 2016–2025 plus 2026-09-18), each via NSE's own
  authoritative archive (Phase A's own verified classic/UDiFF formats), with a holiday/weekend
  fallback (±1..5 calendar days) — never a fabricated date.
- Each snapshot's raw FUTSTK/STF symbols are resolved through `quant_research/security_identity_map.py`
  (8 verified rename/merger-survivor mappings, 3 confirmed non-recoverable merger-extinguished
  exclusions, 3 unresolved exclusions — see that module's own docstring for full sourcing).
- A signal is accepted only if its own symbol was present in the **latest snapshot at or before**
  the signal's own date (a step-function membership timeline) — dates before the first snapshot
  (2016-06-15) are treated as **not eligible** (no evidence, never assumed eligible).
- The universe is **not** `ORIGINAL_32_NSE_UNIVERSE ∪ EXPANDED_ONLY` — it is every canonical symbol
  that was F&O-eligible at ANY sampled snapshot, letting the real historical evidence determine
  membership rather than assuming `ORIGINAL_32`'s own blue-chip set was always eligible.

## 3. Known, disclosed limitations of this specific replay (stated before results, not after)

- **Annual granularity**: a symbol gaining/losing eligibility mid-year is only reflected at the NEXT
  annual snapshot — a bounded timing-precision limitation, not a correctness bug (consistent with
  Phase A's own stated proportionality reasoning).
- **Partial identity resolution**: only the 14-symbol sample Phase A's own 2022-vs-2026 diff
  surfaced was investigated for corporate-action identity; symbols this replay's own broader,
  full-10-year snapshot comparison surfaces as unfetchable (e.g., PSU-bank-merger casualties like
  ALBK/ANDHRABANK, or companies that underwent NCLT resolution like DHFL) were NOT individually
  investigated this session — they are excluded via the normal per-symbol fetch-failure path
  (`MarketDataError` → skipped, logged), the same honest, non-fabricating behavior every prior
  universe-level runner in this project already uses for a symbol it cannot build.
- **No embargo/purge gap** at split boundaries (an already-documented, accepted assumption per
  Phase 3 item B — unchanged here).

## 4. Required reporting (frozen list, per the user's own instruction)

N trades, win rate, mean/median return, net return, gross return, 95% CI, profit factor, worst/best
trade, turnover (trades per split), distinct-symbol count, universe coverage (buildable/total),
missing-data count, and a direct split-by-split comparison against the original H_MEANREV_010
Candidate 2 numbers (development n=2897 +0.08% [-0.27%,+0.44%]; validation n=688 +1.51%
[+0.94%,+2.08%]; out-of-sample n=840 +0.98% [+0.52%,+1.44%]). Drawdown/equity-curve is **not**
reported, matching the original Candidate 2's own already-disclosed limitation (no equity-curve
object exists for this single-symbol-dedicated-capital design — a carried-forward, not new,
limitation). Multiple-testing correction is applied separately, after this entry's own raw result is
recorded (per `strategy/multiple_testing.py`, matching Phase 8's established practice) — not baked
into the primary reported numbers, to keep this entry's own result directly comparable to the
original.

## 5. Decision rule (frozen, matching the user's own explicit sequencing)

- If the point-in-time-corrected result is **decisively negative or statistically meaningless in
  validation AND out-of-sample** (i.e. does not replicate the original's own two CI-decisive
  positive splits): **mean reversion is closed for this research cycle.** No further portfolio
  -construction or replication step is pursued.
- If the point-in-time-corrected result **remains CI-decisive positive in at least validation and
  out-of-sample**: proceed to the next step in the user's own sequence — realistic portfolio
  construction (reusing `quant_research/mean_reversion_portfolio.py`'s own already-built,
  unmodified simulator), then independent replication if that survives.

No parameter is retuned after this result is seen. No fourth universe-construction variant is tried
if this one disappoints.
