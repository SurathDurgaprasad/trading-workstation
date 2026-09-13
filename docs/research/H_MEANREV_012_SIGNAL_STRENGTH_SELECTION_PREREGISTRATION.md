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

## 16. Results — ranking does NOT restore the gross edge; a genuinely mixed, non-flattering outcome

Full evidence: `H_MEANREV_012` in `strategy/hypothesis_registry.py`. Raw
per-split numbers below are from this entry's own scratch measurement
run (`quant_research/mean_reversion_portfolio.py`'s `schedule_portfolio`
and `schedule_portfolio_ranked`, `zscore_close_20_rank_key`, applied to
a freshly-built `COMBINED` universe, 206/208 buildable symbols, same 2
excluded by the pre-existing path-safety allowlist as every prior entry
in this family).

### [VERIFIED] Reproducibility check: Candidate A control exactly reproduces `H_MEANREV_011`'s own cited record

Before trusting Candidate B, Candidate A (`schedule_portfolio`,
unmodified) was run on this entry's own freshly-built datasets, per
split, as an internal consistency check on the dataset-build and
per-split-independent-scheduling methodology (NOT a re-litigation of
`H_MEANREV_011`'s own frozen, already-cited result, which remains the
historical record). Accepted-trade counts (555/111/105), gross P&L
(+₹43,460.67/−₹7,852.26/−₹4,789.98), and the mechanical
`PromotionVerdict.REJECTED` verdict all matched `H_MEANREV_011`'s own
committed figures exactly (development/validation/out_of_sample). This
confirms the universe, splits, and scheduling logic used to produce
Candidate B below are measured on the identical footing as
`H_MEANREV_011`'s own record — not a different setup masquerading as a
comparison.

### Headline numbers — Candidate A (control, alphabetical) vs Candidate B (ranked, `zscore_close_20`)

| Split | candidates | accepted A / B | accept rate A / B | gross P&L A / B | net P&L A / B | net mean (CI) A | net mean (CI) B |
|---|---|---|---|---|---|---|---|
| development | 7286 | 555 / 567 | 7.6% / 7.8% | +₹43,460.67 / +₹66,732.34 | +₹13,417.48 / +₹36,029.88 | +0.10% [−0.64%,+0.84%] | +0.26% [−0.57%,+1.09%] |
| validation | 1549 | 111 / 101 | 7.2% / 6.5% | −₹7,852.26 / −₹22,473.73 | −₹13,838.58 / −₹27,907.86 | −0.51% [−2.05%,+1.02%] | −1.13% [−2.96%,+0.69%] |
| out-of-sample | 1058 | 105 / 104 | 9.9% / 9.8% | −₹4,789.98 / −₹5,349.05 | −₹10,425.80 / −₹10,928.09 | −0.42% [−1.80%,+0.96%] | −0.46% [−1.59%,+0.67%] |

**Promotion verdict for BOTH candidates: `PromotionVerdict.REJECTED`**
— mechanically identical outcome, every split `STATISTICALLY_MEANINGLESS`
for both A and B (CIs straddle zero substantially in every case).
Ranking changed the point estimates but not the promotion-relevant
classification in any split.

### [TESTED] Central diagnostic (§9): does ranking restore the gross edge? — NO, not broadly, and it materially worsens validation

**[VERIFIED]** Development gross P&L improved under ranking
(+₹43,460.67 → +₹66,732.34, gross mean return +0.32% → +0.48%), but
**[INFERENCE]** the two splits' own gross-return confidence intervals
overlap substantially (control [−0.42%,+1.06%] vs ranked
[−0.35%,+1.31%]) — this point-estimate shift is NOT statistically
distinguishable from noise, and must not be read as ranking having
proven a development-sample improvement.

**[VERIFIED]** Validation gross P&L got MATERIALLY WORSE under ranking
(−₹7,852.26 → −₹22,473.73, nearly 3x more negative; gross mean return
−0.29% → −0.91%; net mean return −0.51% → −1.13%) — a large point-
estimate move, in the WRONG direction, on the split this project's own
established convention treats as the primary forward-looking
confirmation sample (development alone is not informative per this
project's standing dev/val/oos discipline).

**[VERIFIED]** Out-of-sample gross P&L was essentially unchanged,
marginally worse (−₹4,789.98 → −₹5,349.05; net mean return −0.42% →
−0.46%).

**[INFERENCE] Taken together, ranking by `zscore_close_20` magnitude
does NOT cleanly restore the raw signal's own gross edge under
portfolio contention.** It produces a statistically-insignificant
favorable shift in the largest, earliest (development) sample, and a
clearly unfavorable shift in validation, with out-of-sample
essentially flat. This is inconsistent with the hypothesis that
`H_MEANREV_011`'s own arbitrary alphabetical tie-break was the primary
cause of its disappointing validation/out-of-sample performance —
replacing it with an economically-motivated ranking made validation
demonstrably worse, not better. **This matches Outcome 2 of this
entry's own pre-registered interpretation (§13): the signal continues
to behave poorly under capital-constrained, simultaneous-candidate
competition regardless of which selection mechanism is used** — not a
confirmation that selection-mechanism was masking a real edge.

### [VERIFIED] Win rate fell under ranking in every split

Development 50.09% → 49.03%; validation 42.34% → 34.65% (a large
drop); out-of-sample 48.57% → 40.38%. **[INFERENCE]** Ranking toward
the most extreme (most negative) `zscore_close_20` readings appears to
select trades that win less often, not more — consistent with, though
not proof of, these being more extreme/"stretched" mean-reversion
setups whose eventual reversion is less reliable, not more.

### [VERIFIED] Symbol breadth widened under ranking, not narrowed (development)

Distinct symbols: control 163, ranked 178 (overlap 158; 20 symbols
appear ONLY under ranking, 5 appear ONLY under the alphabetical
control). **[INFERENCE]** Ranking by signal strength does not simply
concentrate the accepted sample into a small set of "usual suspect"
names — if anything it is marginally MORE diversified by symbol count
than the arbitrary alphabetical control on this split, a genuine,
disclosed, mildly counter-intuitive finding.

### [TESTED] Volatility-selection check: ranking selects modestly higher-magnitude trades, not dramatically so

Mean |net_return| per trade (development): control 5.96%, ranked
6.19% (+0.22 percentage points, ≈+3.7% relative). **[INFERENCE]** A
small, real effect in the expected direction (ranking toward more
extreme z-scores selects modestly more extreme outcomes), but too
small on its own to explain the validation-split deterioration above.

### [VERIFIED] Portfolio-level risk did not clearly improve or worsen under ranking — mixed by split

Max drawdown: development 39.34% → 34.73% (better under ranking);
validation 26.44% → 34.04% (worse under ranking); out-of-sample
26.90% → 26.30% (essentially unchanged). Worst single trade:
development −₹9,676.95 → −₹10,977.65 (worse); validation −₹7,836.97 →
−₹7,836.97 (same trade, unaffected — this specific candidate was
accepted under both selection rules); out-of-sample −₹4,952.23 →
−₹3,014.30 (better). **[INFERENCE] No consistent risk-profile
improvement or degradation is attributable to ranking** — the
per-split risk picture moves in different directions in different
splits, with no clear pattern.

### [VERIFIED] Average concurrent positions / capital utilization — both candidates ran similarly deployed

Calendar-time-weighted average concurrent positions (of the
`MAX_CONCURRENT_POSITIONS=4` cap), computed directly from each
accepted trade's own entry/exit timestamps: development 2.82 → 2.88
(control → ranked, ≈70.5%→72.1% capital utilization); validation 2.90
→ 2.63 (≈72.5%→65.7%); out-of-sample 2.84 → 2.81 (≈70.9%→70.3%).
**[VERIFIED]** These figures differ from `H_MEANREV_011`'s own cited
"~2.1-2.2 (~53-55% utilization)" — since the ACCEPTED TRADE COUNTS AND
GROSS P&L reproduced that entry's own record exactly (above), this
reflects a different, more precise time-weighted computation method in
this entry (a direct sweep-line over accepted trades' own entry/exit
timestamps) rather than a different scheduling result; `H_MEANREV_011`'s
own figure was explicitly disclosed as "rough." Turnover (trades /
average concurrent positions, the same simple definition
`H_MEANREV_011` used) is nearly identical between control and ranked in
every split (development ≈197 vs ≈197; validation ≈38 vs ≈38;
out-of-sample ≈37 vs ≈37) — ranking does not materially change
portfolio turnover.

### [VERIFIED, a serious, disclosed dependency carried over from `H_MEANREV_006`/`011`] Both candidates remain heavily dependent on 2020

Pooling all three splits: **[VERIFIED]** control — 73 of 771 total
trades (9.5%) occurred in 2020, contributing +₹19,707.01 of net P&L
against a total pooled net of −₹10,846.91 across all years (i.e.
EXCLUDING 2020, the control's total net across the full 2016-2026
span would be −₹30,553.92, more negative than the pooled figure).
**[VERIFIED]** ranked — 72 of 772 total trades (9.3%) occurred in
2020, contributing +₹29,528.87 of net P&L against a total pooled net
of −₹2,806.07 (EXCLUDING 2020, ranked's own total would be
−₹32,334.94). **[INFERENCE] Both candidates' relatively less-negative
overall net P&L is substantially dependent on the single 2020 crisis
year** — consistent with `H_MEANREV_006`'s own already-established
year-stability caveat, carried over unchanged, not a new finding
specific to ranking. Ranking does not reduce this dependency; if
anything the 2020 contribution is a LARGER share of ranked's own
(smaller-magnitude) total pooled net.

### Liquidity — [INCONCLUSIVE], as pre-registered

No average-daily-volume, free-float, or market-capitalization data
exists anywhere in this repository (unchanged from `H_MEANREV_011`'s
own confirmed search). Not resolved here, not silently assumed away.

### No look-ahead — [VERIFIED]

`zscore_close_20_rank_key` reads only the candidate's own
`signal_idx` row; `tests/test_mean_reversion_portfolio.py`'s
`test_zscore_close_20_rank_key_reads_only_the_signal_bar_not_future_bars`
and `test_schedule_portfolio_ranked_ignores_future_bars_beyond_each_signal_idx`
both directly confirm mutating bars strictly after a candidate's own
signal_idx does not change its ranking or acceptance outcome.

### Verdict

**REJECTED** for Candidate B, matching `strategy.promotion_gate.
evaluate_promotion`'s own unmodified mechanical verdict — identical to
Candidate A's own verdict (also `REJECTED`, both here and in
`H_MEANREV_011`'s own historical record). Mapped to
`HypothesisStatus.REJECTED`. **Precisely characterized**: this entry
demonstrates that a economically-motivated, non-invented,
pre-registered ranking rule (`zscore_close_20`, more negative = higher
priority) does NOT cleanly restore the raw signal's own gross edge
when candidates are capital-constrained — it shifts development
favorably within statistical noise, but shifts validation clearly
unfavorably and leaves out-of-sample essentially unchanged. **This
does NOT prove the ranking mechanism itself is harmful** (the
promotion verdict is identical to the alphabetical control's own, and
several diagnostics — symbol breadth, turnover, out-of-sample gross —
show no consistent degradation either) — **it demonstrates that the
arbitrary alphabetical tie-break was NOT the dominant explanation for
`H_MEANREV_011`'s own disappointing validation/out-of-sample
performance.** The underlying candidate-selection question this entry
set out to answer is now answered: replacing the selection mechanism
alone, with every other frozen component unchanged, does not turn this
signal into a promotable multi-position portfolio strategy.
`H_MEANREV_009` (`REJECTED`), `H_MEANREV_010` (`INCONCLUSIVE`), and
`H_MEANREV_011` (`REJECTED`) remain unmodified, cited as comparison
points only.

## 17. Scope note

Paper-only research throughout. `schedule_portfolio_ranked` is a pure,
isolated backtesting function — never reachable from `paper/`,
`live/`, or `main.py`'s own live-trading command paths. No broker
execution exists or is touched anywhere in this research path. No
scheduler dependency. Does not touch `data/paper_trading.db`,
`data/live_state.db`, `data/scheduler_runs.db`,
`data/direction_forecasts.db`, or `data/predictions.db`.
