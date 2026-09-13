# ML Phase 1 — Triple-Barrier Baseline Pre-Registration

Frozen before any `ml_research/` code is written, per `PHASE_1_IMPLEMENTATION_SPEC.md`'s
own frozen implementation sequence (§13, steps 1–6). This document is the
pre-registration that sequence requires — it restates and freezes the six
inputs (data availability, `H`, universe, label semantics, walk-forward
geometry, cost model) using **real, directly-observed evidence**, not
assumption. Once committed, none of the six may change based on results
produced by code written after this point (invariant: "no goalpost
movement", `PHASE_1_IMPLEMENTATION_SPEC.md` §1 / user's Phase 1 mission
message §2).

`experiment_version: ML_PHASE1_v1`

## 1. Falsifiable objective (unchanged, restated)

> Determine whether an intraday feature vector contains economically
> useful, out-of-sample information about triple-barrier trade outcomes
> after costs.

## 2. Data availability — [VERIFIED], not a blocker

Probed directly (`market.data_provider.YahooFinanceProvider.fetch_ohlcv`,
unmodified, reused as-is) on 2026-09-13:

- **Interval**: `5m` bars are available and reliable via yfinance.
  `period="60d"` returns the full available window; `period="max"`
  paradoxically returns *less* (yfinance appears to clamp intraday `"max"`
  to a shorter internal default) — `period="60d"` is therefore the
  correct explicit request, not `"max"`.
- **Universe probed**: all 32 symbols of
  `quant_research.universe_expansion.ORIGINAL_32_NSE_UNIVERSE` —
  **32/32 succeeded**, zero fetch errors.
- **Depth**: exactly **59 distinct trading sessions**, `2026-06-22` to
  `2026-09-11`, identical first/last session across every one of the 32
  symbols.
- **Bars per session**: 72–75 (NSE's ~6.25-hour session at 5-minute
  granularity is ~75 bars; the observed range reflects ordinary
  session-length variation, not missing-bar corruption).
- **Duplicate timestamps**: zero, across all 32 symbols, directly counted.
- **Timestamp representation**: naive `datetime` (no `tzinfo`), values
  starting at `09:15` and ending at `15:10`–`15:30` — consistent with IST
  wall-clock NSE session hours, matching this project's own established
  convention (naive-IST) rather than a UTC or unlabeled timezone.
- **Missing-bar rate within a session**: not separately quantified bar-by-
  bar in this probe (the per-session count range of 72–75 is consistent
  with essentially complete intraday coverage, not a material gap rate,
  and is treated as [INFERENCE] rather than a directly-counted per-bar
  audit — the label generator's own resolution loop, Section 5, will
  surface any real intraday gap directly during actual generation).

**Real, disclosed constraint** (this is the load-bearing finding of this
pre-registration): only **59 trading sessions** (~3 calendar months) of
5-minute history exist via this project's sole real market-data provider.
This is dramatically shorter than the 10-year daily history this
project's other research (the `H_MEANREV_*`/`H_XSECT_*` family) has used.
Consequences, accepted and disclosed rather than avoided:
- Walk-forward fold count and per-fold sample size are both small relative
  to this project's daily-bar research history.
- The 59-session window almost certainly represents a narrow slice of
  market regimes (a single ~3-month stretch), not the multi-year regime
  diversity `market_intelligence/regime.py`/`learning/regime.py` could in
  principle stratify by on a longer daily series. Regime-conditioned
  analysis in the final report is disclosed as underpowered by
  construction, not treated as a full regime study.
- This constraint was discovered, not assumed — `main.py`'s own existing
  code comment (`main.py:1872-1884`) already stated no workflow in this
  project had ever exercised an intraday interval; this pre-registration
  is the first time that gap has actually been measured.

**Conclusion: NOT BLOCKED.** Proceeding with a deliberately small,
disclosed-as-underpowered-where-relevant first experiment, consistent with
invariant 10 ("failure to demonstrate edge is a valid and useful result")
and this project's own established practice of running an honestly
underpowered first pass rather than waiting for data that does not exist
via any repository-supported source.

## 3. Horizon `H` — frozen at 8 bars (40 minutes)

Chosen from the specification's own candidate range (6–12 bars / 30–60
minutes on 5-minute bars), **before any label or model result exists**,
for a stated, non-results-driven reason:

- 8 bars leaves the large majority of each ~73-bar session able to reach a
  full, same-session resolution (Section 5's own session square-off rule
  removes the remainder rather than reading into the next session).
- 8 five-minute bars is a direct, proportionate intraday analogue of this
  project's own established `h10` daily-bar holding convention (used
  throughout the `H_MEANREV_*` family) — not an arbitrary new number, an
  adaptation of an existing, already-used holding-period philosophy to a
  finer timeframe.

`H = 8` is frozen. It is not revisited after seeing any label distribution
or model result within `ML_PHASE1_v1`.

## 4. Universe — frozen at `ORIGINAL_32_NSE_UNIVERSE` (32 symbols)

Not the full `COMBINED` (206-symbol) universe. Frozen reasons, stated
before any result:
- Directly verified clean (32/32, zero errors, identical session coverage)
  in Section 2's own probe — not assumed extendable to the other 174
  symbols without a separate check.
- This project's own longest-standing, most-vetted universe (used since
  `H_XSECT_001`), the most conservative, least-novel choice available for
  a deliberately boring first baseline.
- A smaller universe reduces total 5-minute data volume for this first
  run (32 × ~4,300 bars ≈ 137,600 rows before any filtering), keeping
  Phase 1 tractable without the added complexity of validating 206
  symbols' worth of intraday reliability in one pass.

Universe expansion to `COMBINED` is explicitly deferred to a later,
separately pre-registered phase — not attempted here.

**Survivorship-bias disclosure** (carried over unchanged from this
project's own prior `docs/BRUTAL_SELF_CRITIC.md` finding): `ORIGINAL_32_
NSE_UNIVERSE` is a hand-curated, currently-listed large-cap watchlist,
not a systematic historical reconstruction — the same disclosed bias
already documented for this project's daily-bar research applies
identically here.

## 5. Label semantics — triple-barrier, frozen

Adapts `predictions/tracker.py::evaluate_prediction` and
`backtesting/execution.py::check_exit` verbatim — the resolution mechanics
are reused, not reinvented.

**Entry**: `entry_reference_price` = the next bar's (`t+1`) open. No
slippage model is applied at the feature/label-generation stage itself
(slippage is applied later, only inside the economic evaluation layer,
Section 9's `expected_value.py`, via the unmodified `CostModel`) — kept
separate so the label itself reflects a clean, comparable-to-any-cost-
assumption price outcome.

**Stop and target** — reusing `strategy/baseline.py`'s existing frozen
constants, verified directly against current source this session:
```text
STOP_ATR_MULTIPLIER = 1.5      # strategy/baseline.py:8
TARGET_RISK_REWARD  = 2.0      # strategy/baseline.py:9

stop_price   = entry_reference_price - 1.5 * atr_14_at_t
target_price = entry_reference_price + 2.0 * (entry_reference_price - stop_price)
```

**Horizon**: `H = 8` bars (Section 3).

**Intraday session boundary — the one refinement this pre-registration
adds beyond `PHASE_1_IMPLEMENTATION_SPEC.md`'s own text**, decided here
from the data's own shape (Section 2), not from any label/model result:
if bar `t+H` would fall in a *different* trading session than bar `t+1`
(i.e., resolving the barrier would require reading past the current
session's own last bar), the label resolves as `TIMEOUT` **at the current
session's own last available bar** — never by reading into the next
session's bars. This keeps every label a genuinely intraday quantity
(consistent with the mission's own "intraday trading intelligence"
framing) and avoids introducing overnight gap risk into a barrier
mechanism that was never designed to price it. A useful, disclosed
side-effect: because no label ever crosses a session boundary, walk-
forward folds split cleanly on whole sessions (Section 6) with **zero**
possibility of a training label's resolution window leaking into a
different session's validation data — the purge/embargo requirement is
satisfied by construction for cross-session boundaries, with an
additional explicit embargo (Section 6) retained anyway as defense in
depth.

**Resolution loop**, per bar from `t+1` onward within the same session:
```text
if low <= stop_price and high >= target_price:  # same-bar ambiguity
    outcome = STOP_FIRST          # reuses check_exit's own conservative rule, unchanged
elif low <= stop_price:
    outcome = STOP_FIRST
elif high >= target_price:
    outcome = TARGET_FIRST
elif bars_observed >= H or bar is the session's own last bar:
    outcome = TIMEOUT
else:
    continue
```

**Anomaly guard**: reuses `predictions/tracker.py`'s existing
`ANOMALOUS_BAR_GAP_THRESHOLD = 0.5` unchanged — a >50% single-bar move
resolves to `INSUFFICIENT_DATA`, excluded from training, never imputed.

**Label representation**: `label_target_first: int` — `1` if
`TARGET_FIRST`, `0` if `STOP_FIRST` or `TIMEOUT` (matching the user's own
Phase 1 mission message §8 binary convention: `TARGET_FIRST = 1`,
`STOP_OR_TIMEOUT = 0`). `INSUFFICIENT_DATA` rows are excluded from
training entirely, not encoded as `0`.

## 6. Walk-forward geometry — frozen, session-level

Given Section 5's session-boundary rule (no label ever crosses a session
boundary), fold boundaries are defined on whole **trading sessions**, not
individual bars — this is simpler and strictly safer than bar-level
splitting for this dataset's own shape.

- **Final held-out test window**: the **last 12 sessions** of the 59
  (≈20%, matching this project's own established ~20% out-of-sample
  proportion convention from `backtesting/splits.py`'s default fractions,
  applied here at session granularity), evaluated **exactly once**, after
  every other Phase 1 choice is frozen.
- **Walk-forward pool**: the remaining **47 sessions**, expanding-window,
  **4 folds**, each validation block **7 sessions**, computed
  programmatically (not hand-picked) by an expanding-window fold builder
  in `ml_research/walk_forward.py`, with an explicit **1-session embargo**
  between each fold's training end and its validation start (defense in
  depth; Section 5 already makes cross-session label leakage structurally
  impossible, so this embargo is a deliberate belt-and-suspenders margin,
  not a load-bearing requirement).
- **Retrain cadence**: the logistic regression is refit at every fold
  boundary (cheap for this model class) — never fit once and reused
  across folds.
- Exact fold boundaries (session dates) are computed and persisted by the
  implementation, not hand-specified in this document, to avoid an
  arithmetic transcription error between this document and the code.

## 7. Cost model — unchanged

`backtesting/costs.py::CostModel.india_nse_intraday_2026()`, reused
without modification: `brokerage_per_fill=20.0`, `fees_pct=0.00375`,
`taxes_pct=0.025`, `entry_slippage_bps=5.0`, `exit_slippage_bps=10.0`.
**Every report this pipeline produces must repeat, verbatim, the
existing disclosed omission**: GST, stamp duty, and SEBI charges are not
included in this preset.

## 8. What will NOT change after this is pre-registered

Data availability findings (Section 2), `H=8` (Section 3), the 32-symbol
universe (Section 4), the triple-barrier/session-boundary label semantics
(Section 5), the fold geometry (Section 6), and the cost model (Section
7) are frozen as of this commit. If a downstream discovery (e.g., a data
quality problem found only during full dataset construction) invalidates
one of these, the correct response is to **stop, document the
invalidation, and open a new, separately versioned `ML_PHASE1_v2`**, not
to edit this document or the code silently — per the user's own explicit
"no goalpost movement" instruction.

## 9. Verdict vocabulary

Every claim in the eventual results report is labeled `[VERIFIED]`
(directly observed), `[TESTED]` (a specific, reported statistical
result), `[INFERENCE]` (a reasoned conclusion from verified/tested facts,
disclosed as inference), or `[HYPOTHESIS]` (an open, unverified
conjecture) — this project's own established discipline, applied to this
first ML experiment exactly as to every prior `H_MEANREV_*`/`H_XSECT_*`
hypothesis.

## 10. Scope note

Paper/research-only. No component built for this experiment is reachable
from `main.py`'s live commands, `live/`, `paper/`, or `decision_engine/`.
`ml_research/` is architecturally isolated in the same posture
`quant_research/`'s own module docstrings already establish for that
package. No LLM is used anywhere in this pipeline. No live order
execution exists or is touched.
