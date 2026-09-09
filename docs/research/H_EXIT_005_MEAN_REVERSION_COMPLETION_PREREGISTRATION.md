# H_EXIT_005 — Mean-Reversion-Completion Exit, Pre-Registration

Written and frozen **before** any experiment code runs. Per this
project's own multiple-testing discipline: the exit rule, entry
conditions, universe, splits, cost model, and success/failure criteria
are fixed here; none may change after seeing results.

## 1. Question

`H_XSECT_002` and `H_MEANREV_004` — two structurally unrelated
reversal-type signals — both failed executable conversion via the
identical mechanism: the project's frozen, trend-continuation-
calibrated ATR stop (`strategy.baseline.STOP_ATR_MULTIPLIER`/
`TARGET_RISK_REWARD`) dominates exits (57-66% of trades) before the
reversal thesis can complete. `H_XSECT_004` already showed that
naively widening or removing that same stop makes things *worse*, not
better, for a related signal. This is **not** a further stop-width
search. The question is whether a **structurally different** exit —
one that reads the reversal thesis's own defining metric directly,
rather than an arbitrary ATR-based price distance — changes the
outcome: does `H_MEANREV_003`'s regime-gated oversold entry survive
becoming a real trade when the exit is "the reversion has completed"
instead of "price moved N×ATR"?

## 2. Parent hypotheses

`H_XSECT_002` (executable conversion fails, STOP-dominated), `H_XSECT_004`
(naive stop-width changes make it worse), `H_XSECT_005` (a genuinely
different, non-price-stop execution design — periodic rebalance — DID
change the outcome, to positive), `H_MEANREV_004` (the same STOP-
domination mechanism confirmed on an unrelated signal).

## 3. Architecture audit — what already exists (verified against the actual code, not filenames)

| Component | Verified behavior |
|---|---|
| Entry timing | Signal at bar `i`; fill at bar `i+1`'s open, slippage-adjusted (`backtesting/exit_experiments.py`) |
| Stop logic | Hard-required by `RiskEngine.evaluate` (`reference_price <= stop_price` is a structural veto); checked every bar, always before any other exit (`backtesting/execution.py::check_exit`) |
| Target logic | Same priority tier as stop; stop wins on same-bar ambiguity |
| Holding-period logic | Fallback only, in `run_time_based_exit_backtest` — increments only when `check_exit` already returned `None` for that bar; price exits always take priority |
| Position sizing | Fixed-fractional risk: `quantity = floor(risk_budget / (reference_price - stop_price))` — a wider stop mechanically shrinks position size (`risk/engine.py`) |
| Portfolio handling | `RiskEngine` hard-vetoes any signal while the account already holds a position — at most one open position per backtest `Account` |
| Rebalancing | No concept in the price-target/time-cap path; only `H_XSECT_005`'s own separate portfolio runner has it |
| Transaction costs | `CostModel.cost_for_fill` + `slippage_adjusted_price`, applied identically regardless of exit reason |

**Exit mechanisms that exist**: price-stop, price-target (both always
checked first, every bar), time-cap fallback (`EXPIRED`, only in
`run_time_based_exit_backtest`), end-of-data forced close. That is the
complete set. All were designed for `TrendMomentumBaseline`'s own
trend-continuation logic (`strategy/baseline.py`) and reused unchanged
by every reversal-type candidate tested so far.

**Exit mechanisms searched for in the registry and confirmed
untested** (`grep` across `strategy/hypothesis_registry.py`, `H_EXIT_
001`–`004` read in full — all four scoped to the baseline
trend-continuation signal, never a reversal signal): signal-decay exit,
mean-reversion-completion exit, regime-invalidation exit, opposite-
signal exit. A time-cap-only design has been tested, but only for the
baseline signal (`H_EXIT_004`, REJECTED there) and for the
cross-sectional signal (`H_XSECT_005`'s portfolio design, positive but
INSUFFICIENT_DATA) — never in a single-symbol design for the
mean-reversion signal specifically.

## 4. Selection reasoning (why mean-reversion-completion, not the alternatives)

Considered: signal-decay, mean-reversion-completion, regime-
invalidation, portfolio-rebalance-exit, opposite-signal-exit.
**Mean-reversion-completion selected**: it is the most direct,
non-arbitrary operationalization of the entry signal's own defining
claim. The entry fires when `zscore_close_20` (price's deviation from
its own trailing 20-bar mean, in standard-deviation units) falls below
a threshold; the economically coherent exit is "exit once that same
metric shows the deviation has closed" — not a price distance borrowed
from a different strategy's own logic. Regime-invalidation (exit when
`TRENDING_UP` ends) is a real, plausible alternative but is secondary —
it is a property of the entry *filter* `H_MEANREV_003` added, not of
the core reversion thesis itself (the un-gated oversold condition,
`H_MEANREV_001`, is the base signal `TRENDING_UP` merely conditions).
Mean-reversion-completion is tested first as the more fundamental
question; regime-invalidation remains a named, explicit candidate for
a future, separately pre-registered hypothesis if this one is
inconclusive or rejected — not chosen by default, and not tested here.
No Stop Gate #6 (ambiguous, evidence-free choice among several
plausible definitions) applies: the reasoning above is a real,
evidence-based preference, not an arbitrary pick.

## 5. Frozen strategy definition

**Entry** (unchanged from `H_MEANREV_004`): `quant_research.
mean_reversion_signal.py`'s `REGIME_GATED_CANDIDATES`
(`A_oversold_2std_trending_up` / `B_oversold_1_5std_trending_up`) —
`zscore_close_20 < -2.0`/`< -1.5` AND `market_trend_regime ==
"TRENDING_UP"`. Both candidates kept, matching every prior
`H_MEANREV_00x` entry's own A/B convention — this is not "multiple exit
hypotheses," the exit mechanism is the single new variable; the A/B
entry-threshold split is the same established convention reused
unchanged.

**Exit** (the single new variable, frozen): exit at the **earliest**
of —
1. `zscore_close_20 >= 0.0` — the position has returned to (or above)
   its own trailing 20-bar mean; the reversion thesis has completed.
   `0.0` is not a searched threshold — it is the literal zero-crossing
   of the same metric the entry itself is defined on, the most
   minimal, non-arbitrary choice available.
2. `backtesting.exit_experiments.DEFAULT_MAX_HOLDING_BARS` (= 20 bars)
   held — this project's own existing, already-established standard
   safety cap (reused verbatim, not a new number), preventing an
   unbounded hold if reversion never happens.

No real price-based stop is used: `RiskEngine.evaluate` structurally
requires a `stop_price` below `reference_price` to approve any signal
at all, so an artificially wide, practically unreachable stop distance
is set purely to satisfy that structural requirement — the identical,
already-established technique `H_XSECT_005` used for its own "no real
stop" design. This is a **deliberate, disclosed** choice, not an
oversight: keeping the *original* ATR stop active would let it dominate
exits again before the new zscore-based condition ever gets a chance
to fire, exactly reproducing `H_MEANREV_004`'s own result and
defeating the point of this test. Target: none — profit-taking is
folded into the reversion-completion condition itself (once the mean is
reached, the position exits, whether that represents a gain or a
loss), a genuinely different design from a fixed R:R target, not merely
a relabeling of one.

New `ExitReason.MEAN_REVERSION_COMPLETE` value, matching the exact
precedent `H_EXIT_002`/`H_EXIT_003` already established (each adding
its own reason code for an isolated, self-contained runner never
touching `check_exit`/the standard backtester).

## 6. Universe and data (frozen)

Full **original 32-symbol** NSE universe
(`quant_research.universe_expansion.ORIGINAL_32_NSE_UNIVERSE`) — per
this mission's own explicit instruction, NOT the 208-symbol expansion
(`H_XSECT_006` already showed universe expansion can reverse an
apparent edge; that is a separate, later question if this result is
promising). 10 years daily, matching `H_MEANREV_003`/`004`.

## 7. Costs (frozen)

`CostModel.india_nse_intraday_2026()` — unchanged, the same realistic
estimate every `H_XSECT_00x`/`H_MEANREV_00x` executable test uses. Not
reduced.

## 8. Splits and evaluation

`backtesting.splits.split_periods` 60/20/20, matching every prior entry
in this thread. Evaluated via `strategy/promotion_gate.py::evaluate_promotion`
— the same mechanical dev/val/oos verdict, no new or looser bar.

## 9. Success / failure / verdict vocabulary (frozen, using this project's own precise definitions)

- **`PROMOTED`**: all three splits reach a confident `POSITIVE_
  PERFORMANCE` verdict — full success.
- **`INCONCLUSIVE`**: no split is confidently negative and every
  split's own point estimate is positive, but at least one split's CI
  still straddles zero — a real, promising, not-yet-decisive result
  (matches `H_XSECT_005`'s own precedent; would warrant checking
  whether legitimate statistical power exists to increase, e.g. a
  different non-overlapping cadence or more history, NOT universe
  expansion by default).
- **`REJECTED`** (point estimates mixed, none confidently negative) or
  **`NEGATIVE`** (at least one split confidently negative): the new
  exit does not rescue the signal either — reported as such, and no
  further exit-design iteration follows in this same run.
- **`INSUFFICIENT_DATA`**: reported honestly if any split falls below
  the 30-trade floor.

## 10. What will NOT change after this is pre-registered

No ATR-multiplier search. No stop-width grid. No target optimization.
No retuning the `0.0` zscore threshold or the 20-bar cap after seeing
results. No switching entry candidates. No universe change. If this
result is REJECTED/NEGATIVE, the next step is a genuinely new,
separately-motivated hypothesis (e.g. regime-invalidation exit,
explicitly named in §4 as the next candidate) — not a retry of this
one with adjusted numbers.

## 11. Reproducibility record

- Universe: `ORIGINAL_32_NSE_UNIVERSE`, all 32 built successfully (`failed_symbols: {}`).
- Benchmark: `^NSEI`, `period="10y"`.
- Cost model: `CostModel.india_nse_intraday_2026()`.
- New code: `backtesting/trade.py`'s `ExitReason.MEAN_REVERSION_COMPLETE`; `quant_research/mean_reversion_signal.py`'s `MeanReversionSignalStrategy.__init__`'s new `stop_atr_multiplier` override, `decide_completion_exit` (pure, extracted), `DEFAULT_WIDE_STOP_ATR_MULTIPLIER=20.0`, `UniverseMeanReversionCompletionExitExperimentResult`, `run_universe_mean_reversion_completion_exit_experiment` — an isolated, self-contained bar-processing loop (never modifying `backtesting/execution.py`'s shared `check_exit`/`OpenPosition`/`close_trade`, the exact isolation posture `backtesting/exit_experiments.py`'s own module docstring establishes for `H_EXIT_001`-`004`). 11 new tests found and fixed one real bug before the real run: `bar.get()` on a genuinely missing column returns `None`, not NaN — the original NaN-only check (`zscore == zscore`) missed this, since `None == None` is `True` in Python. Fixed with an explicit `pd.notna()` check.

## 12. Results — NEGATIVE (a clean, decisive, mechanistically-understood rejection)

Full evidence: `H_EXIT_005` in `strategy/hypothesis_registry.py`.

| Candidate | Split | n | Win rate | Mean return | 95% CI |
|---|---|---|---|---|---|
| A (−2.0σ) | development | 129 | 3.9% | **-6.11%** | [-7.09%,-5.14%] |
| A | validation | 49 | 10.2% | **-3.82%** | [-4.93%,-2.72%] |
| A | out-of-sample | 54 | 24.1% | **-3.52%** | [-4.81%,-2.22%] |
| B (−1.5σ) | development | 157 | 7.6% | **-5.63%** | [-6.51%,-4.75%] |
| B | validation | 79 | 7.6% | **-4.33%** | [-5.33%,-3.34%] |
| B | out-of-sample | 72 | 16.7% | **-3.68%** | [-4.68%,-2.67%] |

`evaluate_promotion` overall verdict: **`NEGATIVE`** for both
candidates — every single one of six splits is individually
CI-decisive negative (not merely non-decisive, unlike `H_MEANREV_004`'s
own `STATISTICALLY_MEANINGLESS` result). This is a **stronger**
negative than the stop/target design it replaced.

**Mechanism — a genuine, previously-unconsidered structural flaw in
"exit at reversion completion," not merely "no stop is bad" repeated**:
exit-reason counts show `MEAN_REVERSION_COMPLETE` is the *majority*
exit reason in every split (e.g. Candidate A development: 99 of 129
trades, 77%) — most trades DO eventually see `zscore_close_20` recover
to ≥0.0. Yet win rates are catastrophically low (3.9%-24.1%). The
explanation: **the moving average itself is not a fixed target**.
`zscore_close_20` measures deviation from the trailing 20-bar mean, and
during a genuine, ongoing decline that mean is *itself falling*
alongside price. "Price has returned to its own trailing mean" is
therefore satisfied long before "price has returned to (or above) the
entry price" in exactly the cases where the entry caught a real,
sustained decline rather than a temporary dip — the exit fires, but on
a trade that is still underwater, sometimes deeply. This is a different
and arguably more fundamental problem than `H_XSECT_002`/`H_MEANREV_004`'s
own STOP-domination story: it is not that a mismatched stop cuts
winners short, but that the chosen exit *condition itself* does not
imply profitability for the entry it was paired with. The minority of
trades that hit the 20-bar `EXPIRED` cap instead (23-27% of trades)
compound this: with no real stop, a position that never reverts at all
rides the full decline until forced closed, producing the large losses
visible in the low win rates.

**Comparison with parent hypotheses**: `H_XSECT_002`/`H_MEANREV_004`
were held back by STOP exits cutting positions short before a real
reversion could complete. This entry removed that constraint entirely
and got a *worse* result, not a better one — directly falsifying the
implicit assumption (carried over from this project's own working
hypothesis after `H_MEANREV_004`) that the stop was the primary
obstacle. The real obstacle is more fundamental: a meaningful fraction
of "oversold" entries are not temporary dips at all, and no exit rule
defined purely in terms of price recovering to a *moving* reference
point can distinguish "reverted" from "the reference point declined to
meet a still-falling price" after the fact.

**Verdict: REJECTED (`NEGATIVE`)** — clean, decisive, without
ambiguity. Per §10's own frozen discipline, no further retuning of the
`0.0` threshold or the 20-bar cap follows from this result. Per §4, the
next candidate this analysis explicitly names — regime-invalidation
exit (exit when `TRENDING_UP` ends) — remains open but is **not**
assumed more promising by default; if pursued, it would need its own
fresh pre-registration, informed by this entry's own key lesson: any
exit condition tested on a reversal signal should be checked for
whether it can fire on a trade that is still net-unprofitable, not just
for whether it eventually fires at all.
