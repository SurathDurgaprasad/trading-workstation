# DERIV_002 — Futures OI-Change Information-Content Test, Pre-Registration

Written and frozen **before** any model is fit or any result is inspected. Second and, per the
mission's own explicit "do not automatically test dozens of alternatives" discipline, **last**
information-content test in this initial derivatives research pass unless a materially different
research design (not merely a third indicator swapped in) is separately justified later.

## 1. Research question (frozen)

"Does day-over-day NIFTY futures open-interest change improve out-of-sample prediction of NIFTY's
own forward return direction, relative to the same OHLCV baseline DERIV_001 already used?"

## 2. Why OI change, and why now

`futures_oi_change_pct` was explicitly named and deliberately DEFERRED (not tested) in
`DERIV_001_FUTURES_BASIS_INFORMATION_CONTENT_PREREGISTRATION.md` §4 — this is not a new, ad hoc
choice made after seeing DERIV_001's own negative result; it was the pre-declared next candidate.
Per Phase 3's own classification (`PHASE3_DATA_FEASIBILITY_GATE.md`), futures OI/OI-change is
Classification A, the same tier as basis. Economically distinct rationale from basis: OI change
reflects new position-taking/unwinding (a flow/positioning signal), whereas basis reflects a
price-level relationship between two markets (a valuation/arbitrage-pressure signal) — genuinely
different information, not a cosmetic variant.

**This is the last derivatives-information-content test in this initial pass.** Per the mission's
own explicit instruction, no third variant (options OI imbalance, put/call structure, IV in any
form) will be tested automatically regardless of this entry's own outcome — a further test would
require a separately-justified, materially different research design, decided by the user, not
triggered automatically by this entry's own result.

## 3. Frozen baseline (identical to DERIV_001)

`trend_ratio`, `rsi_14`, `atr_pct`, `zscore_close_20` — unchanged from DERIV_001, same data, same
computation.

## 4. Frozen augmented feature

`futures_oi_change_pct = (futures_oi_t - futures_oi_{t-1}) / futures_oi_{t-1}`, computed from the
SAME already-verified, already-continuous Dhan `/charts/historical` NIFTY futures series
DERIV_001 used (no new data source).

## 5. Frozen target, model, splits, statistical discipline, decision rule

**Identical to DERIV_001** in every respect except the one substituted feature: `y = 1 if
fwd_return_10 > 0 else 0`; logistic regression, development-only fit; the same 60/20/20 splits on
the same merged spot+futures frame; the same ΔAUC ≥ 0.02-on-both-splits-with-no-Brier-worsening
decision rule; the same ≥100-observations-per-split floor. This entry is #2 of the same
newly-tracked derivatives research family (Phase 10) — a family-size=2 Bonferroni correction is
reported alongside the uncorrected result once both entries exist.

## 6. What will NOT change after this is pre-registered

No new baseline feature. No third derivatives feature substituted in. No threshold adjustment. No
re-derivation of the target horizon. No retroactive change to DERIV_001's own verdict.
