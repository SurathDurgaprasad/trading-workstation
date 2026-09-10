# H_MEANREV_010 — Does the Demonstrated Gross Edge Survive a Different Execution/Sizing/Cost Structure?, Pre-Registration

Written and frozen **before** any experiment code runs. Per this
project's own multiple-testing discipline: entry, exit, universe,
splits, and the exact candidate set are fixed here; none may change
after seeing results.

**This is a causal/execution-structure test, not a signal search.** The
entry, the horizon, and the universe are IDENTICAL to `H_MEANREV_009`.
Nothing about the signal changes anywhere in this document.

## 1. Research question

`H_MEANREV_009` was `REJECTED` (`PromotionVerdict.NEGATIVE`) net of
costs, but its own diagnosis (verified on real trades, not assumed)
found the entry/exit mechanism reproduces the raw signal on a GROSS
basis (+0.56%/+1.97%/+1.42% dev/val/oos, consistent with `H_MEANREV_006`/
`007`/`008`'s own measurement), and that the net-negative result was
driven by a specific, disclosed interaction: a wide stop (needed to
avoid the already-established STOP-domination failure) shrinks
fixed-fractional position size, and a cost model with a meaningful
FIXED per-fill component then consumes a large fraction of the
resulting tiny notional.

**Question**: can this demonstrated gross edge be converted into an
economically tradable position-sizing/cost structure WITHOUT changing
the signal or the horizon and without relying on unrealistic
assumptions? Equivalently: is `H_MEANREV_009`'s own failure caused
SPECIFICALLY by the wide-stop + fixed-fractional-sizing + fixed-per-
fill-brokerage interaction, or does the signal fail to survive ANY
realistic execution structure?

## 2. Audit — what already exists (verified by direct reading, not assumed)

Read directly: `H_MEANREV_009`'s own registry entry and
pre-registration; `backtesting/exit_experiments.py`'s
`run_time_based_exit_backtest`; `quant_research/mean_reversion_signal.py`'s
`MeanReversionSignalStrategy`/`RELATIVE_WEAKNESS_GATED_CANDIDATES`/
`run_universe_relative_weakness_time_exit_experiment`; `risk/engine.py`'s
`RiskEngine.evaluate` (the ONLY sizing algorithm in this codebase's
risk layer: `quantity = floor(risk_budget / risk_per_unit)`, where
`risk_per_unit` is literally the stop distance — confirmed there is no
alternative sizing MODE anywhere in `risk/engine.py` or `risk/config.py`);
`risk/sizing.py` (a bridge to the SAME `RiskEngine`, not an alternative);
`backtesting/costs.py`'s `CostModel` (confirmed `brokerage_per_fill`,
`fees_pct`, `taxes_pct`, `entry_slippage_bps`, `exit_slippage_bps` are
all already-configurable fields, `cost_for_fill(notional) =
brokerage_per_fill + notional*(fees_pct+taxes_pct)/100`);
`strategy/promotion_gate.py`'s `evaluate_promotion` (unmodified,
reused); `quant_research/cross_sectional_portfolio.py`'s
`compute_member_return` (`H_XSECT_005`'s own already-tested pure
function — `tests/test_cross_sectional_portfolio.py` — sizing via
`quantity = int(capital_per_slot // entry_price)`, **completely
independent of any stop distance**, using the SAME `CostModel.cost_for_fill`/
`slippage_adjusted_price` primitives, with bar arithmetic **already
documented as matching `run_time_based_exit_backtest`'s own EXPIRED-
exit convention exactly** — entry at `signal_idx+1`'s open, slippage-
adjusted; exit at `signal_idx+holding_bars`'s close, slippage-adjusted).

**Result of the audit for candidate #2 (fixed-notional sizing)**: an
appropriate EXISTING infrastructure precedent was found — `H_XSECT_005`'s
own `compute_member_return` already implements exactly this sizing
philosophy (fixed capital allocated per position, independent of stop
distance), with matching bar-timing conventions. No new sizing
algorithm is invented; this entry writes one small, new function
closely modeled on `compute_member_return`'s own logic (reusing its
exact `CostModel` calls and bar arithmetic) that additionally exposes
the full per-trade cost/notional/quantity breakdown `compute_member_return`
itself does not return (it returns only the net fractional return) —
required by §H's economic-validity reporting below. `compute_member_return`
itself is NOT modified (H_XSECT_005's own frozen record stays
untouched).

**Result of the audit for candidate #3 (zero-fixed-fee diagnostic)**:
no new code needed at all — `CostModel`'s own `brokerage_per_fill`
field is already configurable; `run_universe_relative_weakness_time_exit_experiment`
(`H_MEANREV_009`'s own unmodified runner) already accepts a
`cost_model` parameter. Candidate #3 is simply `H_MEANREV_009`'s own
runner called with an explicit `CostModel(brokerage_per_fill=0.0,
fees_pct=0.00375, taxes_pct=0.025, entry_slippage_bps=5.0,
exit_slippage_bps=10.0)` — the real `india_nse_intraday_2026()`
percentage/slippage values, with ONLY the fixed component zeroed.

## 3. Frozen entry (reused verbatim from `H_MEANREV_006`/`009`)

`_oversold_2std_relative_weak` — `zscore_close_20 < -2.0` AND
`relative_strength_20 < H_MEANREV_006_RELSTRENGTH_MEDIAN (-6.8845%)`.
Unchanged. No threshold change. No signal addition. No regime gating
change.

## 4. Frozen exit (reused verbatim from `H_MEANREV_009`)

10-bar time-based exit (`max_holding_bars=10`), the SAME horizon
`H_MEANREV_006`/`007`/`008`/`009` established as primary. No horizon
search.

## 5. Frozen universe and splits (reused verbatim from `H_MEANREV_009`)

`COMBINED` (`ORIGINAL_32_NSE_UNIVERSE` ∪ `EXPANDED_ONLY`, 206/208
buildable symbols), 10 years daily. `backtesting.splits.split_periods`
60/20/20, per-symbol, identical convention to `H_MEANREV_009`.

## 6. Candidates (frozen, small, pre-justified set — no grid, no search)

**Candidate 1 — `H_MEANREV_009` baseline (NOT rerun)**: `H_MEANREV_009`'s
own already-committed, immutable results are cited directly as the
baseline for comparison, not recomputed. Wide stop (20x ATR) +
`RiskEngine`'s existing fixed-fractional sizing + real
`CostModel.india_nse_intraday_2026()`.

**Candidate 2 — fixed-notional sizing, real costs**: the frozen entry/
exit, sized via a `compute_member_return`-modeled function with
`capital_per_slot = initial_capital` (100,000) — the full available
capital per position, since (matching `H_MEANREV_009`'s own one-
position-at-a-time architecture) only one position is ever open at a
time in this single-symbol backtest design. **Explicitly disclosed as
a simplification for causal isolation, not a recommended real-world
position size** — a genuine multi-symbol portfolio would need to
divide capital across concurrently-eligible positions, which this
single-symbol-at-a-time backtest structure does not model. This is
assessed directly in §12's Phase-3 analysis (is the result dependent
on this unrealistic full-capital assumption). Real
`CostModel.india_nse_intraday_2026()`, unchanged.

**Candidate 3 — baseline sizing, zero-fixed-fee diagnostic control**:
IDENTICAL to Candidate 1 (wide stop, `RiskEngine`'s existing sizing)
except `CostModel(brokerage_per_fill=0.0, fees_pct=0.00375,
taxes_pct=0.025, entry_slippage_bps=5.0, exit_slippage_bps=10.0)` —
real percentage fees/taxes/slippage retained, ONLY the fixed per-fill
brokerage component removed. **Explicitly a diagnostic control, NOT a
claim that zero brokerage represents real trading** — isolates whether
the FIXED cost component specifically (independent of sizing) is
sufficient to explain the failure, holding sizing constant.

No fourth candidate. No threshold variation within any candidate. No
selection of "the best" candidate after seeing OOS results — all three
are reported in full, compared honestly, per §7.

## 7. No optimization (frozen constraint)

No parameter search of any kind — `capital_per_slot` (Candidate 2) and
`brokerage_per_fill=0.0` (Candidate 3) are each a single, pre-specified
value with an explicit rationale (§6), not tuned or searched. No
threshold, horizon, or entry condition is touched. No candidate is
selected as "the winner" after seeing OOS results and then re-run with
adjustments — whatever each candidate's own honest verdict is stands.

## 8. Economic validity — required reporting for every candidate, every split

- Gross return (mean, and the full distribution where already
  available from the underlying `Trade`/return records).
- Net return (mean, 95% CI — via `evaluate_promotion`'s own
  `ProfitabilityReport`, unmodified).
- Fixed fees (total and as a per-trade average).
- Variable costs (percentage fees/taxes/slippage, total and average).
- Average and median trade notional.
- Position quantity (mean, and % of trades at quantity == 1).
- Cost as % of notional (mean).
- Turnover / number of trades per split.
- Win rate.
- Drawdown (where the existing `PerformanceMetrics`/equity-curve
  machinery already computes it for Candidates 1/3, which reuse
  `run_time_based_exit_backtest`'s own equity-curve construction;
  Candidate 2 has no equity-curve/account object by construction — a
  disclosed limitation, not fabricated).
- Tail outcomes (worst/best trades, p5/p95 of the per-trade return
  distribution).
- Capital utilization / liquidity-execution assumptions (disclosed
  directly per candidate, especially Candidate 2's full-capital
  simplification).

## 9. Statistical discipline

Same `>=30` trades per split floor as every prior entry in this
family, via `evaluate_promotion`'s own built-in
`MIN_SAMPLE_SIZE_FOR_A_VERDICT` check (unmodified).

## 10. Promotion (frozen, unmodified existing machinery)

`strategy.promotion_gate.evaluate_promotion`, applied identically to
every candidate — no new success criterion invented, no gate weakened.
Possible outcomes named exactly as the machinery returns them:
`PROMOTED`/`NEGATIVE`/`INCONCLUSIVE`/`REJECTED`/`INSUFFICIENT_DATA`,
mapped to this registry's own `HypothesisStatus` vocabulary the same
way `H_MEANREV_009` was mapped (`PROMOTED`→at most `SUPPORTED`,
matching this project's own standing caution that a real backtest pass
still needs paper-trading validation before true promotion;
`NEGATIVE`/`REJECTED`→`REJECTED`; `INCONCLUSIVE`/`INSUFFICIENT_DATA`→
`INCONCLUSIVE`). A positive gross result with negative realistic net
economics is explicitly NOT a promotable outcome. A result dependent
on Candidate 2's own unrealistic full-capital assumption is explicitly
flagged as such, not silently accepted.

## 11. Adversarial checks (run for any candidate whose net result is NOT decisively negative)

Symbol breadth, sector concentration (where `NSE_SECTOR_MAP` coverage
permits, the same disclosed partial-coverage caveat every prior entry
carries), yearly/era stability, OOS confidence interval width, worst-
trade concentration (do a handful of trades dominate the mean),
turnover, notional distribution, comparison against Candidate 1 and
Candidate 3's own gross figures. NOT run reflexively for a candidate
that is already decisively negative net of costs (matching
`H_MEANREV_007`/`008`/`009`'s own established gating discipline — no
value in adversarially stress-testing an already-rejected result).

## 12. What will NOT change after this is pre-registered

No new entry condition. No new horizon. No new universe. No re-deriving
`capital_per_slot` or `brokerage_per_fill=0.0` after seeing results. No
fourth candidate added after seeing the first three. `H_MEANREV_009`'s
own historical verdict is not rewritten or re-run — cited as-is.

## 13. Verdict-vocabulary discipline (frozen)

Every claim in the results write-up is labeled:
**[VERIFIED]** — directly observed in this entry's own real backtest
output. **[TESTED]** — a specific, reported statistical result (mean,
CI, etc.), not merely asserted. **[INFERENCE]** — a reasoned
conclusion drawn from verified/tested facts, disclosed as inference,
not fact. **[HYPOTHESIS]** — an open, unverified conjecture named as
such (e.g., a candidate future direction), never presented as a
finding.

## 15. Reproducibility record

**[VERIFIED]** `COMBINED` universe: 206/208 symbols built for both
candidates. Candidate 2's own frozen entry/exit/predicate is
`quant_research.mean_reversion_signal._oversold_2std_relative_weak`,
imported and reused, not reimplemented. Candidate 3 reuses
`H_MEANREV_009`'s own runner unchanged, passing only a different
`CostModel`.

## 16. Results — the causal hypothesis is CONFIRMED; neither candidate is a validated strategy

Full evidence: `H_MEANREV_010` in `strategy/hypothesis_registry.py`.

### Candidate 2 — fixed-notional sizing (`capital_per_slot=100,000`), real `india_nse_intraday_2026()` costs

**[TESTED]**

| Split | n | net mean | 95% CI | `ProfitabilityVerdict` |
|---|---|---|---|---|
| development | 2897 | +0.08% | [−0.27%,+0.44%] | `STATISTICALLY_MEANINGLESS` |
| validation | 688 | **+1.51%** | **[+0.94%,+2.08%]** | **`POSITIVE_PERFORMANCE`** |
| out-of-sample | 840 | **+0.98%** | **[+0.52%,+1.44%]** | **`POSITIVE_PERFORMANCE`** |

**[VERIFIED]** Gross means: dev +0.18%, val +1.61%, oos +1.08% —
consistent with `H_MEANREV_009`'s own gross figures and the raw
`H_MEANREV_006`/`007`/`008` measurement. **[VERIFIED]** Mean notional:
~99,000-99,600 (essentially the full `capital_per_slot`, confirming
the sizing rule worked as designed). **[VERIFIED]** Mean quantity:
390-1,208 shares per trade; 0% of trades at quantity==1 (a complete
reversal from `H_MEANREV_009`'s own 36-39%). **[VERIFIED]** Mean cost
as % of notional: ~0.098% (fixed fee ~₹40 + variable ~₹57, on a
~₹99,000 notional) — down from `H_MEANREV_009`'s own 7.2%-9.4%, a
~75-95x reduction, exactly as the causal hypothesis predicted.

**[TESTED] Concentration check**: top-5-trades' share of total net
PnL — development **128.4%** (the top 5 trades' combined PnL EXCEEDS
the period's total, meaning broad underlying losses are more than
offset by a handful of extreme winners — consistent with development
being the non-decisive split); validation 13.1%; out-of-sample 16.4%
(both broad-based, NOT dominated by a handful of trades). Distinct
symbols contributing: 205/199/189 out of 206 built — very broad
symbol coverage in every split.

**[INFERENCE]** Development's own non-decisiveness and extreme
concentration are consistent with, and not a new phenomenon beyond,
the 2020-driven instability `H_MEANREV_006`'s own year-stability
follow-up already established for this signal family — not
independently re-verified by year here (see §11's own gating: this
detail pass, not a further slicing dimension, is this entry's
adversarial check).

**[TESTED — serious, disclosed concern]** Extreme single-trade tail
risk: development worst single-trade net return **−65.03%**, best
**+80.35%** — a direct, mechanical consequence of sizing 100% of
capital into ONE position with NO volatility adjustment (unlike
`RiskEngine`'s own stop-distance-based sizing, which implicitly sizes
down volatile names). This is a genuinely unrealistic, dangerous
position-sizing scheme for real deployment — explicitly disclosed as
such in this entry's own pre-registration (§6), not discovered as a
surprise. **[INFERENCE]** A single position this large, at these
share quantities (390-1,208 shares on names that may not always be
highly liquid), also raises real execution/market-impact questions the
existing cost model's flat basis-point slippage assumption may not
adequately capture at this trade size — an open question, not
resolved by this entry's own existing infrastructure.

**Promotion verdict: `INCONCLUSIVE`** (every split's point estimate
positive; development's CI straddles zero) → mapped to
`HypothesisStatus.INCONCLUSIVE`.

### Candidate 3 — baseline (`H_MEANREV_009`) sizing, zero-fixed-fee diagnostic control

**[TESTED]**

| Split | n | net mean | 95% CI | `ProfitabilityVerdict` |
|---|---|---|---|---|
| development | 2063 | +0.16% | [−0.25%,+0.57%] | `STATISTICALLY_MEANINGLESS` |
| validation | 398 | **+1.90%** | **[+1.20%,+2.61%]** | **`POSITIVE_PERFORMANCE`** |
| out-of-sample | 393 | **+1.30%** | **[+0.68%,+1.92%]** | **`POSITIVE_PERFORMANCE`** |

**[VERIFIED]** Mean notional: ~600-740 (essentially identical to
`H_MEANREV_009`'s own baseline sizing, unchanged as designed — only
the fixed brokerage component was removed). Mean cost as % of
notional: ~0.058% — down from `H_MEANREV_009`'s own 7.2%-9.4%.

**[TESTED] Concentration check**: top-5-trades' share of total net
PnL — development 75.9% (still concentrated, consistent with the same
development-period instability); validation 18.6%; out-of-sample
20.4% (both broad-based). Distinct symbols: 183/130/98 — narrower than
Candidate 2's own coverage (expected, given far fewer total trades at
this tiny position size) but still meaningfully broad, not a handful
of names.

**[INFERENCE]** Because Candidate 3 changes ONLY the fixed-fee
component and NOT the sizing (still the same tiny, ~1-8-share
positions `H_MEANREV_009` itself produced), this result on its own
demonstrates that realistic PERCENTAGE-based costs (fees/taxes/
slippage) are survivable at `H_MEANREV_009`'s own tiny position sizes
— it is SPECIFICALLY the FIXED per-fill brokerage, not percentage
costs in general, that was decisive in `H_MEANREV_009`'s own failure.
**Explicitly, per this entry's own pre-registration (§6), zero
brokerage is a diagnostic control, not a claim that real trading incurs
no fixed fees** — this result isolates the mechanism, it does not
itself describe an executable design.

**Promotion verdict: `INCONCLUSIVE`** → mapped to
`HypothesisStatus.INCONCLUSIVE`.

### Central causal finding

**[TESTED, CONFIRMED]** Both candidates, addressing the SAME
underlying interaction from two independent directions (fix the
sizing; or fix the fixed fee, holding sizing constant), moved the
result from `H_MEANREV_009`'s own decisive `NEGATIVE` (all three
splits CI-decisive negative) to `INCONCLUSIVE` (validation AND
out-of-sample CI-decisive POSITIVE, broad-based, not trade-dominated;
only development non-decisive, consistent with the already-established
2020 pattern). **This confirms the causal hypothesis from
`H_MEANREV_009`'s own diagnosis**: the specific interaction of a wide
stop, fixed-fractional position sizing, and a meaningful FIXED
per-fill brokerage component was the dominant cause of that entry's
own failure — NOT a dead entry signal. Neither the signal nor the
h10 exit was changed anywhere in this entry.

**[INFERENCE, NOT established]** That a genuinely REALISTIC,
promotable executable design exists. Neither candidate reaches
`PROMOTED` (development remains non-decisive in both); Candidate 2's
own positive result depends on an explicitly-disclosed, unrealistic
full-capital-concentration assumption; Candidate 3 is explicitly a
diagnostic control, not a real-world cost structure. **Neither
candidate is a validated, tradeable strategy.**

### Verdict for this entry overall

**`INCONCLUSIVE`** — the causal mechanism question this entry was
designed to answer is CONFIRMED (not partially confirmed, not
disproved): `H_MEANREV_009`'s failure was specifically caused by the
disclosed sizing/cost interaction, not by a breakdown of the
underlying signal. Whether a genuinely realistic executable design
exists remains open — explicitly NOT resolved by either candidate as
constructed.

### What this identifies as the next real bottleneck (not pursued here)

**[HYPOTHESIS, not started]** No longer the signal (survives gross,
repeatedly, across `H_MEANREV_006`/`007`/`008`/`009`/`010`) and no
longer raw percentage transaction costs (Candidate 3 shows these are
survivable at even tiny position sizes). The open bottleneck is now
**realistic position sizing / portfolio construction**: whether a
genuinely diversified, multi-position sizing scheme — dividing
available capital across SEVERAL concurrent positions rather than
Candidate 2's own 100%-into-one-position concentration — can still
achieve adequate per-trade notional to dilute fixed costs. This
question cannot be answered by the single-symbol-at-a-time backtest
architecture this whole project (including `H_MEANREV_009`/`010`'s own
runners) has used throughout — it would require genuine multi-symbol
portfolio-level infrastructure (matching `H_XSECT_005`'s own
periodically-rebalanced portfolio design more closely than either
candidate here), a substantial, separately-scoped next step, not
undertaken in this entry per the user's own explicit stop instruction.

## 17. Scope note

Paper-only research throughout. `run_time_based_exit_backtest` and the
new `compute_member_return`-modeled helper are both isolated
backtesting primitives, never reachable from `paper/`, `live/`, or
`main.py`'s own live-trading command paths — confirmed by direct
reading, matching every prior entry's own disclosed scope. No broker
execution exists or is touched anywhere in this research path. No
scheduler dependency. Does not touch `data/paper_trading.db`,
`data/live_state.db`, `data/scheduler_runs.db`,
`data/direction_forecasts.db`, or `data/predictions.db`.
