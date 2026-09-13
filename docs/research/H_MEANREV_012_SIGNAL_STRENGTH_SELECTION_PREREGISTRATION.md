# H_MEANREV_012 — Signal-Strength Candidate Selection, Pre-Registration

Written and frozen **before** any experiment code runs. Per this
project's own multiple-testing discipline: entry, exit, universe,
portfolio constraints, and the ranking rule are all fixed here; none
may change after seeing results.

**This is a test of PORTFOLIO SIGNAL SELECTION, not a new alpha
hypothesis.** The signal, the h10 exit, the universe, and every
portfolio parameter `H_MEANREV_011` already froze are IDENTICAL here.
The ONLY changed variable is HOW the portfolio chooses among several
simultaneously-eligible candidates when more exist than available
slots.

## 1. Research question

`H_MEANREV_011` found that only 7-10% of 9,893 candidate signals were
accepted into its own 4-slot portfolio — 82-93% rejected, mostly
because the portfolio was already full — and that the accepted subset,
selected by an ARBITRARY chronological-then-alphabetical tie-break, no
longer cleanly reproduced the raw signal's own positive gross edge
(gross P&L itself turned negative in validation/out-of-sample there,
unlike every single-position entry in this family).

**Question**: can simultaneous `H_MEANREV_006` signals be selected
using a pre-existing, economically meaningful measure of signal
strength instead of arbitrary alphabetical ordering, while keeping
every other component frozen? Does removing the arbitrary selection
restore the gross behavior the raw signal and the single-position
executable designs (`H_MEANREV_009`/`010`) already showed?

## 2. Audit — searching for an existing signal-strength measure (verified by direct reading, not assumed)

Read directly: `quant_research/mean_reversion_signal.py`'s
`_oversold_2std_relative_weak` (the frozen entry — gates on
`zscore_close_20 < -2.0` AND `relative_strength_20 <
H_MEANREV_006_RELSTRENGTH_MEDIAN`); `quant_research/mean_reversion_portfolio.py`'s
`schedule_portfolio` (`H_MEANREV_011`'s own frozen, event-by-event,
chronologically-ordered acceptance loop — confirmed NOT modified by
this entry, cited not rerun for the control); `quant_research/cross_sectional.py`'s
`rank_cross_sectionally` (a GENERIC cross-sectional ranking UTILITY
parameterized by an arbitrary `score_column` — not itself a distinct
signal-strength FIELD; confirmed it offers no independent third
ranking measure, only a mechanism that would rank by the SAME fields
already identified below); a repository-wide search for
`signal_strength`/`signal_score`/`ranking_score`/`strength_score`
found nothing specific to this entry signal (only unrelated fields in
`decision_engine/confidence.py`'s own composite BUY/WATCH/AVOID score,
which combines MULTIPLE indicators for a different decision pathway
entirely — explicitly NOT reused here, since using it would mean
combining fields, forbidden by this entry's own frozen design below).

**Result of the audit**: exactly TWO already-existing, already-causal
fields are part of the frozen entry condition itself and each already
carries an established directional meaning in this codebase:
- `zscore_close_20` — `H_MEANREV_001`'s own original module docstring:
  "a large negative z-score predicts a higher forward return" — MORE
  NEGATIVE already means MORE OVERSOLD, an established semantic, not
  invented here.
- `relative_strength_20` — MORE NEGATIVE already means MORE
  RELATIVELY WEAK vs. `^NSEI`, the exact quantity `H_MEANREV_006`'s own
  gate already thresholds.

**No third, independent ranking mechanism exists that is "clearly
applicable" per this entry's own frozen gate — Candidate C is
therefore NOT created.**

## 3. Frozen entry, exit, universe, portfolio constraints (all reused verbatim from `H_MEANREV_006`/`009`/`010`/`011`, nothing changed)

- Entry: `_oversold_2std_relative_weak`, unchanged.
- Exit: h10 time-based exit via `compute_fixed_notional_trade`, unchanged.
- Universe: `COMBINED` (206/208 buildable symbols), unchanged.
- Splits: shared calendar-based dev/val/oos, unchanged
  (`development_end=2023-11-25`, `validation_end=2025-04-17`).
- Portfolio: `MAX_CONCURRENT_POSITIONS=4`, `capital_per_position=25,000`
  (25% of `initial_capital=100,000`, from `RiskConfig.max_exposure_pct`),
  real `CostModel.india_nse_intraday_2026()`, one open position per
  symbol, identical event-driven capital accounting. NOT re-derived,
  NOT re-justified — reused exactly as `H_MEANREV_011` froze them.

## 4. Candidates (frozen, exactly two, no grid)

**Candidate A — control**: `H_MEANREV_011`'s own already-committed
result, cited directly, NOT rerun (the scheduler is deterministic,
confirmed by that entry's own tests — re-running would only reproduce
identical numbers at the cost of a redundant full-universe backtest).

**Candidate B — ranked**: identical portfolio mechanics, except
candidates sharing the SAME signal date are ranked by `zscore_close_20`
**ascending** (more negative = higher priority = accepted first) BEFORE
applying the identical accept/reject rule (symbol-already-open →
capacity → cash → data-availability), instead of `H_MEANREV_011`'s own
flat chronological-then-alphabetical order. Ties within a date (equal
`zscore_close_20`, vanishingly rare with real float data) are broken
by symbol name — the same deterministic convention `H_MEANREV_011`
itself already uses, not a new choice.

**No Candidate C.** No combination of `zscore_close_20` and
`relative_strength_20`. No weighting. No alternate ranking direction
tried and compared.

## 5. No optimization (frozen constraint)

The ranking field (`zscore_close_20`), its direction (ascending =
more-negative-first), and the tie-break (symbol name) are each fixed
here, before any result is examined, with the justification stated in
§2. No alternative field, direction, or tie-break is tried or compared
after seeing results. If Candidate B fails to restore the gross edge,
that is reported as the honest finding — not a prompt to try
`relative_strength_20` instead, or a combination, in this same entry.

## 6. No look-ahead (frozen requirement, independently tested)

The ranking key for a candidate at `(symbol, signal_idx)` reads ONLY
`datasets[symbol].frame.iloc[signal_idx]["zscore_close_20"]` — the
SAME already-causal value (a rolling 20-bar window using only rows
`<= signal_idx`) the frozen entry condition itself already evaluates
at that exact bar. No bar after the signal index is read by the
ranking function. This is independently unit-tested (§7) by
constructing a synthetic scenario where a FUTURE bar's own value is
deliberately set to an extreme, ranking-reversing value and confirming
the accepted order is unaffected.

## 7. Minimal implementation (frozen scope)

One new function, `schedule_portfolio_ranked`, added to the EXISTING
`quant_research/mean_reversion_portfolio.py` module (`H_MEANREV_011`'s
own `schedule_portfolio` is NOT modified, NOT duplicated wholesale —
reused unchanged for the control's own citation; `CandidateEntryEvent`/
`PortfolioSchedulingResult`/`summarize_portfolio`/`compute_fixed_notional_trade`
are all reused verbatim, unchanged). `schedule_portfolio_ranked` takes
an injectable `rank_key` callable (`(event, datasets) -> float`,
ascending = higher priority) rather than hardcoding
`zscore_close_20` internally — a configurable candidate-selection
strategy per the mission's own explicit preference, not a duplicated
simulator. This entry's own scratch measurement script supplies
`zscore_close_20` as that callable; no other ranking function is
defined or tried.

Required targeted tests (written and run BEFORE any real-universe
experiment): deterministic ranking; simultaneous-signal ranking
correctness; correct ranking direction (more negative wins); slot
limitation; one-position-per-symbol; capital exhaustion; no-look-ahead
(§6); alphabetical control (`schedule_portfolio`) remains reproducible
and untouched; equal-strength deterministic tie-break; portfolio
accounting (gross/fixed/variable/net) unchanged from the underlying
`compute_fixed_notional_trade`; h10 exit timing unchanged; costs
unchanged.

## 8. Reporting (frozen, per split, for both candidates)

Trade count; accepted/rejected signal counts by reason; mean and
median return; gross P&L; net P&L; transaction costs (fixed +
variable); win rate; portfolio drawdown; worst and best trade; average
and maximum concurrent positions; capital utilization; distinct
symbols; symbol concentration (top-5 share, disclosed with the same
small-sample caveat `H_MEANREV_011` already found this metric carries
at low net P&L); year-by-year performance where the sample in a given
split permits it without fabricating precision from too few
observations.

## 9. Critical diagnostic (frozen)

The primary comparison is NOT net return alone. Compare Candidate B's
own GROSS return against (a) `H_MEANREV_011`'s own gross figures and
(b) the raw `H_MEANREV_006`/`007`/`008` forward-return measurement, to
determine whether ranking specifically restores the gross edge the
arbitrary alphabetical selection lost — the central causal question
this entry exists to answer.

## 10. Adversarial checks (run for Candidate B only if its own result is not decisively negative, matching this family's own established gating discipline)

OOS confidence interval; annual stability where sample permits;
symbol breadth; top-trade/top-symbol concentration; worst trade/worst
period; drawdown; turnover; 2020 dependence (already an established
risk for this signal family); a direct check of whether ranking simply
selects more volatile names (comparing accepted-trade notional/
magnitude distribution against Candidate A's own); look-ahead audit
(§6, already required regardless of outcome); duplicate-signal audit
(the same symbol firing on consecutive bars before its own exit,
already handled by the existing one-position-per-symbol rule, reused
unchanged).

## 11. Promotion (frozen, unmodified existing machinery)

`strategy.promotion_gate.evaluate_promotion`, unmodified, applied
identically to Candidate B. No new threshold. No manual override of a
positive-looking validation/OOS result into `PROMOTED` — only the
machinery's own verdict is reported. Even a `PROMOTED`-equivalent
result here would still require further paper-trading validation
before any live consideration, and would remain primarily evidence
about the PORTFOLIO-SELECTION methodology, not a validated trading
strategy.

## 12. Liquidity (frozen, unchanged from `H_MEANREV_011`)

Marked **[INCONCLUSIVE]** — no average-daily-volume, free-float, or
market-capitalization data exists anywhere in this repository
(re-confirmed, not re-searched from scratch, since `H_MEANREV_011`'s
own direct search already established this and nothing has changed).
Not assumed unlimited.

## 13. Interpretation frozen in advance (per the mission's own three possible outcomes)

**Outcome 1 — ranking restores the gross edge**: supports the
inference that `H_MEANREV_011`'s own arbitrary selection materially
distorted its accepted sample. Does NOT itself prove a profitable
strategy — the next bottleneck would become portfolio risk/cost/
liquidity validation at this now-more-representative sample.

**Outcome 2 — ranking does not restore the gross edge**: the signal
may genuinely behave poorly when capital-constrained across
simultaneous opportunities — recorded honestly, without immediately
trying a different ranking field in this same entry.

**Outcome 3 — ranking improves but remains underpowered**: classified
`INCONCLUSIVE`, with the exact reason (sample size, wide CI, etc.)
stated precisely — not tuned further.

## 14. What will NOT change after this is pre-registered

No change to the entry, the exit, the universe, the portfolio
constraints, the ranking field, the ranking direction, or the
tie-break. No Candidate C added after seeing Candidate B's own result.
`H_MEANREV_009` (`REJECTED`), `H_MEANREV_010` (`INCONCLUSIVE`), and
`H_MEANREV_011` (`REJECTED`) are cited, not rewritten, not rerun with
modified logic.

## 15. Verdict-vocabulary discipline (frozen, matching `H_MEANREV_010`/`011`)

Every claim in the results write-up is labeled **[VERIFIED]**,
**[TESTED]**, **[INFERENCE]**, or **[HYPOTHESIS]**, exactly as the two
prior entries in this sub-thread already established.

## 16. Scope note

Paper-only research throughout. `schedule_portfolio_ranked` is a pure,
isolated backtesting function — never reachable from `paper/`,
`live/`, or `main.py`'s own live-trading command paths. No broker
execution exists or is touched anywhere in this research path. No
scheduler dependency. Does not touch `data/paper_trading.db`,
`data/live_state.db`, `data/scheduler_runs.db`,
`data/direction_forecasts.db`, or `data/predictions.db`.
