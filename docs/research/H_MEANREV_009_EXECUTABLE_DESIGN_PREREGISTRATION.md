# H_MEANREV_009 — Initial Executable Design, Relative-Weakness Bucket, Pre-Registration

Written and frozen **before** any real backtest runs. Per this
project's own multiple-testing discipline: entry, exit, sizing, costs,
universe, and evaluation are all fixed here from ALREADY-ESTABLISHED
empirical values; nothing is newly searched or tuned.

**Explicit mandate for this entry**: the user has directly authorized
moving from pure measurement to an executable-design test — "derive
the initial executable design from the empirical distributions already
established, then test it honestly against OOS data. No parameter
optimization." This entry follows that instruction to the letter: every
design choice below is either an already-frozen constant reused
verbatim from `H_MEANREV_006`/`007`/`008`, or an already-established
technique/constant reused verbatim from an EARLIER, unrelated
hypothesis in this same codebase (`H_EXIT_005`, `H_XSECT_005`) for
exactly the same documented purpose. Nothing here is newly chosen by
searching, grid-testing, or peeking at this entry's own results.

## 1. Research question

Does the SIMPLEST, entirely non-optimized executable version of the
`H_MEANREV_006`/`007`/`008` relative-weakness bucket (Candidate B) —
using already-frozen entry logic, an already-established
wide-stop-to-neutralize-price-exits technique, and the
already-established primary holding horizon — clear this project's own
standard promotion bar (`strategy/promotion_gate.py`, unchanged), when
tested honestly against real trade simulation, real NSE costs, and
real position sizing?

**Why the relative-weakness bucket (B), not the high-volatility bucket
(C) or the joint bucket (D)**: `H_MEANREV_008` documented as an
explicit empirical constraint that any volatility-conditioned entry
(C, D) needs its own systemic/crisis-regime risk mechanism before being
responsibly deployed — no such mechanism has been designed or tested.
Bucket B is the ONLY bucket in this entire research thread
(`H_MEANREV_005`→`008`) that showed no sign reversal in any split,
including the 2020-contaminated development period — the
most-validated, most crisis-robust starting point, chosen for that
reason and disclosed as such, not because it has the largest raw mean.

## 2. Audit — why the frozen trend-continuation stop/target architecture is deliberately NOT used, and what already-established alternative is reused instead

Read directly: `strategy/baseline.py` (`STOP_ATR_MULTIPLIER=1.5`,
`TARGET_RISK_REWARD=2.0` — the project's frozen, trend-continuation-
calibrated defaults); `quant_research/mean_reversion_signal.py`'s own
`MeanReversionSignalStrategy.__init__` docstring; `H_EXIT_005`'s own
registry entry and pre-registration; `H_XSECT_005`'s own registry
entry; `backtesting/exit_experiments.py`'s
`run_time_based_exit_backtest`/`run_universe_time_based_exit_experiment`.

- **Established, repeated finding (three independent confirmations:
  `H_XSECT_002`, `H_MEANREV_004`, `H_EXIT_005`) NOT re-litigated here**:
  the frozen baseline stop/target (a trend-continuation-calibrated
  1.5x-ATR stop / 2:1 target) systematically damages reversal-type
  entries via STOP-domination. This entry does not retest that
  architecture.
- **Already-established alternative technique, reused verbatim, not
  invented here**: `MeanReversionSignalStrategy.__init__`'s own
  `stop_atr_multiplier` parameter, whose own docstring states its
  purpose precisely — "a deliberately wide value makes the price-based
  stop/target practically unreachable, satisfying RiskEngine's
  structural requirement for a valid stop/target without letting
  either dominate exits — the same technique `H_XSECT_005` already
  used." `H_EXIT_005` already used `DEFAULT_WIDE_STOP_ATR_MULTIPLIER =
  20.0` for exactly this purpose in this exact module. **This entry
  reuses `stop_atr_multiplier=20.0` verbatim — the same already-used
  number, not a new choice, not searched over.**
- **Already-established time-based force-close mechanism, reused
  verbatim, not invented here**: `run_time_based_exit_backtest`/
  `run_universe_time_based_exit_experiment` (`H_EXIT_004`'s own
  infrastructure) — `check_exit()` (now practically inert given the
  wide stop/target above) is checked first every bar, and the position
  is force-closed at `ExitReason.EXPIRED` once `max_holding_bars` is
  reached. **`max_holding_bars=10` is reused from `H_MEANREV_006`/
  `007`/`008`'s own already-established "primary horizon" (h10) — the
  SAME horizon used throughout this entire research thread for
  comparability, not selected because it looks best for this specific
  test** (the temporal-risk-evolution finding in `H_MEANREV_008`
  actually showed h5 has a HIGHER risk-adjusted ratio for Bucket B in
  out-of-sample specifically — h10 is used anyway, precisely to avoid
  the appearance of picking the horizon that performs best on the very
  data this entry will be tested against).
- **Net effect of both choices together**: with stop/target
  practically unreachable and the position force-closed at bar 10, the
  realized exit is (with very rare exception) governed by the
  time-cap — an executable approximation of the exact "hold N bars, no
  active stop/target" measurement `H_MEANREV_006`/`007`/`008` already
  characterized, now run through REAL trade simulation (real fills,
  real slippage, real per-fill costs, real fixed-fractional position
  sizing via the unmodified `RiskEngine`), not just a forward-return
  average.
- **Explicit, disclosed risk-architecture caveat**: a stop this wide is
  not "no stop" — `RiskEngine`'s fixed-fractional sizing means
  `risk_per_unit = stop_distance = 20 x ATR`, so position sizes will be
  correspondingly SMALL (a direct, disclosed, mechanical consequence,
  not a separate design choice) — but a genuinely catastrophic single-
  bar move beyond 20x ATR remains structurally possible before the stop
  would bind. This is disclosed honestly, not hidden; `H_MEANREV_008`'s
  own tail statistics (`expected_shortfall_5pct` around −13% to −26%
  for Bucket B depending on split) already characterize the plausible
  downside this design is exposed to.

## 3. Entry (frozen, reused verbatim from `H_MEANREV_006`/`007`/`008`)

`zscore_close_20 < -2.0` AND `relative_strength_20 <
RELSTRENGTH_MEDIAN` where `RELSTRENGTH_MEDIAN = -6.8845%` — the EXACT
threshold `H_MEANREV_006` froze from development-period-only pooled
triggering observations, reused verbatim, not re-derived.
`relative_strength_20` requires a REAL `market_series` (`^NSEI`) passed
to `add_alpha_features` — confirmed necessary in `H_MEANREV_006`'s own
reproducibility record (all-NaN under the default `market_series=None`
pipeline).

One new, small predicate in `quant_research/mean_reversion_signal.py`
(mirroring `_oversold_2std_trending_up`'s own exact style/precedent for
`H_MEANREV_004`) — `_oversold_2std_relative_weak` — and one new
one-entry candidates dict, `RELATIVE_WEAKNESS_GATED_CANDIDATES`, kept
SEPARATE from `CANDIDATES`/`REGIME_GATED_CANDIDATES` (matching this
module's own established convention of never silently merging a new
hypothesis's candidates into an earlier one's frozen dict). Only
Candidate A (`zscore_close_20 < -2.0`) is used — matching
`H_MEANREV_007`/`008`'s own established choice to keep this specific
thread to a single clean lens.

## 4. Exit (frozen, reused verbatim from established infrastructure)

`stop_atr_multiplier=20.0` (`H_EXIT_005`'s own already-used constant)
+ `max_holding_bars=10` (`H_MEANREV_006`/`007`/`008`'s own established
primary horizon), via `run_universe_time_based_exit_experiment`
(`H_EXIT_004`'s own unmodified infrastructure). No new exit logic
written.

## 5. Position sizing and costs (frozen, unmodified existing infrastructure)

`RiskEngine` with the default `RiskConfig`, completely unmodified —
the same fixed-fractional sizing every other hypothesis in this
registry uses. `CostModel.india_nse_intraday_2026()` — the standard,
already-established realistic NSE cost preset (`H_MEANREV_004`'s own
precedent for exactly this purpose), `initial_capital=100_000.0`
matching every prior universe-level executable test in this project.

## 6. Universe, splits (frozen, identical to `H_MEANREV_006`/`007`/`008`)

`COMBINED` (`ORIGINAL_32_NSE_UNIVERSE` ∪ `EXPANDED_ONLY`, 206/208
buildable symbols), 10 years daily. `backtesting.splits.split_periods`
60/20/20 development/validation/out-of-sample, the project's own
standard convention, applied per-symbol as every prior executable
universe-level test in this project already does (`H_MEANREV_004`'s
own precedent — note this per-symbol split convention is NOT
necessarily calendar-identical to `H_MEANREV_006`/`007`/`008`'s own
shared-universe-calendar split, since this test pools real EXECUTED
TRADES per symbol via the existing `split_periods` utility, matching
`H_MEANREV_004`'s own established pattern exactly, not the
cross-sectional `shared_period_boundaries` convention the raw-
measurement entries used — disclosed as a genuine, minor methodological
difference from the measurement-only entries, not an inconsistency).

## 7. Evaluation (frozen, unmodified existing infrastructure)

`strategy.promotion_gate.evaluate_promotion` — the EXACT SAME
dev/val/oos promotion-relevant verdict machinery every other
executable-conversion attempt in this registry (`H_XSECT_002`,
`H_MEANREV_004`, `H_EXIT_005`) has been held to, applied via
`backtesting.universe.per_trade_returns` on the real, executed,
cost-adjusted trades. `PROMOTED` requires ALL THREE splits to reach a
confident `POSITIVE_PERFORMANCE` verdict — the only outcome that would
clear the bar to become a candidate for live paper trading. Any other
verdict (`NEGATIVE`/`INCONCLUSIVE`/`REJECTED`/`INSUFFICIENT_DATA`) is
reported exactly as the machinery names it, not reinterpreted.

## 8. What will NOT change after this is pre-registered

No retuning `stop_atr_multiplier` (fixed at 20.0). No retuning
`max_holding_bars` (fixed at 10). No re-deriving `RELSTRENGTH_MEDIAN`.
No universe change. No switching entry candidates. No adjusting
position sizing or cost model after seeing results. If this design
does not clear the promotion bar, that is reported honestly as the
verdict — no second wide-stop value, no second holding horizon is
tried in the same entry. Any genuinely different design idea (e.g., a
distribution-derived stop rather than a practically-infinite one) is
recorded as a candidate FUTURE hypothesis, not retried here.

## 9. Statistical discipline

Same `>=30` trades per split floor as every prior entry
(`learning.profitability.MIN_SAMPLE_SIZE_FOR_A_VERDICT`, already
built into `evaluate_promotion` itself — a split below this
automatically reads `INSUFFICIENT_DATA`, not a forced verdict).

## 10. Scope note

Paper-only, no live/broker code touched. `run_time_based_exit_backtest`
is the same isolated, non-live backtesting primitive `H_EXIT_004`/
`H_MEANREV_004` already used — never reachable from `paper/`, `live/`,
or `main.py`'s own live-trading command paths. No scheduler dependency.
Does not touch `data/paper_trading.db`, `data/live_state.db`,
`data/scheduler_runs.db`, `data/direction_forecasts.db`, or
`data/predictions.db`.
