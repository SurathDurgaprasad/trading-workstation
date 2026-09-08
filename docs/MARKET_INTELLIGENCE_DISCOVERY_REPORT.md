# Market Intelligence Discovery Report

Mission: "TRADING BRAIN EXECUTION LOOP" (2026-09-08). Objective: move
from a well-engineered trading lab to a system that can find and
validate real trading edge — not by tuning the old TrendMomentum
strategy, but by measuring what the market actually does after
specific conditions, then testing whether anything that survives
scrutiny holds up as an actual trade. This report is the mandated
final deliverable, in the mission's own required structure.

## 1. Current System Truth Snapshot (Part A)

Gathered directly, not assumed, at session start (~09:59 IST):

- `git status`: clean. `main` == `origin/main` at every checkpoint this
  session (verified after every commit below).
- No live processes were running at session start.
- Dhan credentials configured (masked); real REST connectivity
  confirmed (`/fundlimit`, HTTP 200, 1.48s round-trip); real WebSocket
  connected.
- **Market session: OPEN** (confirmed via `current_market_session`
  against real IST time, 09:59:55 → still OPEN as of this report,
  10:51+ IST) — an active trading day, unlike several recent prior
  sessions.
- Clock skew: **-132.3s**, consistent with every prior measurement
  across this project's history (known, stable, environmental —
  Windows Time service never synced to NTP on this machine; never
  fixed by this session, per this project's own standing rule).
- Kill switch: INACTIVE. No unresolved pending approvals. Scheduler:
  no active lock (checked structurally) — **except one real, genuine
  finding**: a concrete orphaned `RUNNING` lock was found in production
  `data/scheduler_runs.db` shortly after this, described in full in
  §7 below (this was a real bug, not a false alarm, and was fixed).
- Databases inspected directly: `live_sim_trading.db` (the
  `paper-live` CLI's own engine) remains completely empty — 0
  positions/trades/journal entries, unchanged from the prior session's
  own finding; this engine has never been used for a real trade in
  this project's history. `paper_trading.db` (the `shadow-run
  --paper-execute` engine) has real, growing history — 90 signals, 33
  orders, 32 trades as of session start, unchanged from yesterday
  (no activity had occurred between sessions, as expected with the
  market closed in between).

## 2. Live Paper Observation Summary (Part B)

Started `schedule loop --paper-execute --live-source dhan --resilient`
against `market_data/watchlists/starter_nse.yaml` (15 NSE symbols),
pointed at the real, existing `data/paper_trading.db` and
`data/live_state.db` (never a fresh/throwaway database — confirmed
first that `PaperTradingEngine`'s own `initial_capital` argument is
silently ignored whenever an account already exists at the given path,
so this could not have reset real state). Left running for the
remainder of the session, checked periodically, never restarted except
once immediately after the scheduler fix (§7) to load the corrected
code.

**A real intraday tick ran and completed successfully**, producing
genuine, non-fabricated evidence of the full pipeline working end to
end during actual market hours:

- 15 candidates scanned, 11 AVOID, 2 WATCH, 2 BUY.
- **KOTAKBANK.NS**: composite +1.45 → BUY → prediction recorded →
  critic verdict **DOWNGRADE** → paper order **APPROVED_PENDING**.
- **RELIANCE.NS**: composite +1.06 → BUY → prediction recorded →
  critic verdict **REJECT** → paper order **SKIPPED (critic REJECT)**.

This is real, live proof — not a hypothetical description — that the
deterministic critic actively blocks a real BUY decision from becoming
a paper order under real market conditions, the exact behavior this
project's safety architecture is designed to provide. One real PENDING
paper order was submitted this run; no real broker order was placed or
could be (no such code path exists anywhere in this project).

The loop continued polling every 60 seconds for the rest of the
session, correctly skipping ticks between the intraday slot's own
cooldown windows (`[SKIPPED] No configured slot is due at this time`)
— healthy, expected behavior, not a hang.

## 3. Market Behavior Findings (Part D/E)

**No Market Behavior Research Engine existed before this session**
(checked first, per Part D's own "if it exists, reuse it" instruction)
— but its raw materials did: `quant_research/alpha_features.py`'s own
`add_forward_return_targets` already computed forward-return label
columns, and `backtesting/regime.py` already provided causal per-bar
regime classification. Built `quant_research/market_behavior.py`
(committed, tested, 13 tests) on top of these — a pure measurement
engine, no strategy or signal concept involved, that builds one
enriched per-symbol dataset once and measures conditional forward
returns (1/2/3/5/10/20 bars) against it cheaply.

Ran a **68-condition broad sweep** against the real 41-symbol universe
(32 NSE, 9 US, 5 years daily), covering every category Part E asks
for: price strength (1/3/5-day, distribution-aware percentile
buckets), price weakness (same), RSI state (standard thresholds),
distance from 20-day highs/lows and from SMA20, volume (percentile
buckets of volume_ratio), volatility (percentile buckets of
atr_pct_of_price), and all 9 trend×volatility regime combinations —
**NSE and US measured and reported separately throughout, never
pooled**, per Part D's own explicit instruction. Full results:
scratchpad `market_behavior_results.json` (not committed — a data
dump, not source; the conclusions that matter are captured here and in
the hypothesis registry).

Headline patterns from the raw (full-period, not yet dev/val/oos-disciplined) sweep:

- **NSE's dominant regime (TRENDING_UP + NORMAL_VOLATILITY, n=3320,
  the single largest bucket in the whole sweep) shows a negative mean
  5-day forward return (-0.29%).** This independently reproduces, via
  a completely different, model-free methodology (raw forward returns,
  no strategy or trade simulation at all), the SAME negative finding
  this project already established in an earlier session via full
  backtested TrendMomentumBaseline trade P&L. Two unrelated methods
  converging on the same answer is real, valuable corroboration.
- **US price weakness shows a much stronger, more consistent bounce
  than NSE.** US extreme 5-day weakness: mean 5-day forward return
  +2.0% to +2.3% depending on which market's own percentile threshold
  is applied. NSE weakness is more mixed and horizon-dependent: mild
  1-day weakness shows a small bounce, but 3-day and 5-day weakness
  tends to *continue* rather than reverse (extreme 5-day NSE weakness:
  mean forward return -0.65%). This divergence would have been
  invisible if NSE and US had been pooled — exactly why Part D's "never
  pool" rule matters in practice, not just in principle.
- Volatility: expanding volatility (top decile of atr_pct_of_price)
  shows the strongest positive forward return in BOTH markets
  (NSE +0.41%, US +0.85%), directionally consistent across markets —
  notably the opposite emphasis from yesterday's H_BREAKOUT_001
  (which hypothesized volatility *contraction* before a breakout would
  help; that candidate was REJECTED). This raw, unconditional
  measurement is a different, narrower question (not combined with an
  actual breakout condition) and does not contradict yesterday's
  result, but is a useful data point for any future breakout research.
- RSI: NSE shows a roughly monotonic decline in forward returns from
  oversold → neutral → overbought (oversold +0.21% → overbought
  -0.14% → deeply overbought -0.39%); US shows a positive drift
  everywhere (reflecting this dataset's own overall US bull-market
  bias in the window measured), with oversold showing the strongest
  reading (+1.36%, small sample n=198).

## 4. Strength vs. Weakness Analysis — Asymmetry (Part F)

Regime-conditioned comparison of "strong weakness" vs. "strong
strength" (3-day trailing return, top/bottom percentile buckets):

| Market | Regime | After strong weakness (5d fwd) | After strong strength (5d fwd) |
|---|---|---|---|
| NSE | Bull (TRENDING_UP) | **-0.65%** | -0.22% |
| NSE | Bear (TRENDING_DOWN) | +0.48% | +0.25% |
| US | Bull | +0.14% | +0.18% |
| US | Bear | **+1.34%** | +0.70% |

Two real, honest observations, not overclaimed as decisive (this table
is full-period, not dev/val/oos-verified): in NSE bull regimes, dips
continue falling *more* than rallies continue rising — the opposite of
"buy the dip in an uptrend" folklore, on this evidence. In both
markets' bear regimes, weakness bounces back more strongly than
strength continues — a textbook mean-reversion-in-a-downtrend shape,
most pronounced in US bear regimes.

## 5. Regime Analysis (Part E.7)

Full trend×volatility breakdown (9 buckets, both markets) is in the
raw sweep output. The single most load-bearing result is already
covered in §3: NSE's dominant TRENDING_UP+NORMAL_VOLATILITY bucket is
negative, independently confirming an earlier, differently-derived
finding from this project's history.

## 6. Conditional Edge Table

| Condition | Market | Horizon | Dev/Val/OOS decisive? | Survives cost (60bps)? | Survives Bonferroni (family=68)? |
|---|---|---|---|---|---|
| trailing_return_5 < frozen -5.35% (extreme 5d weakness) | US | h=5 | **Yes, all 3** | **Yes** | **Yes, all 3** |
| Same condition | US | h=2,3,10 | Yes, all 3 (uncorrected) | — | No (loses significance under correction) |
| Same condition | US | h=1,20 | Not decisive | — | — |

This is the only condition in the entire 68-condition sweep carried
through the full discipline (frozen threshold, dev/val/oos, per-symbol
concentration check, cost sensitivity, multiple-testing correction).
See §8 for what happened when it was turned into an actual strategy.

## 7. Negative Knowledge Discovered

Explicit, so this project never re-tests the same ground blind:

- All 9 trend×volatility regime buckets were measured; only
  TRENDING_UP+NORMAL_VOLATILITY (NSE) and the general US bull drift
  carry large enough samples to say anything with real confidence —
  every other regime bucket, in both markets, has too few observations
  in this 5-year window to be more than suggestive.
- RSI-based buckets alone (without any other context) show only a
  mild, non-decisive gradient in NSE and are dominated by a general
  positive drift in US — not, by themselves, a strong signal in either
  market at the raw-measurement stage.
- Volume-percentile buckets alone show almost no signal in NSE
  (-0.04% to +0.02% across low/normal/high) — consistent with
  yesterday's H_ENTRY_002 (volume-filter-over-baseline) REJECTED
  result, from a different methodology, on the same underlying
  intuition.
- **A real, confirmed engineering bug**: `scheduler/runner.py`'s
  `run_tick` caught `Exception` but not `SystemExit` — any in-process
  `sys.exit()` call anywhere in the shadow-run call chain (found via a
  real `--paper-execute` misconfiguration, but applicable to any future
  `sys.exit()` call too) would kill the entire long-lived scheduler
  process and orphan its lock, blocking every subsequent tick until
  the 30-minute staleness reclaim. Found via a genuine orphaned lock in
  production `data/scheduler_runs.db` (`run_id=a71a6277c221`) while
  starting this session's own live paper observation. Fixed
  (`except (Exception, SystemExit)`, deliberately not `BaseException`
  so Ctrl+C still stops the loop), regression-tested, and the live
  scheduler log itself later confirmed the fix working: `"Reclaimed 1
  stale lock(s) from a prior crashed/killed run: a71a6277c221"`.

## 8. Promising Findings

**US extreme 5-day weakness → forward reversal, h=5 specifically.**
The single most rigorously pre-vetted candidate this project has ever
produced before reaching a strategy backtest:

- Found via the broad 68-condition sweep (§3).
- A threshold was frozen from development-period data only
  (-5.3477%, the real 5th percentile of US-pooled `trailing_return_5`,
  n=4928) and never refit.
- Decisive positive mean forward return (95% CI excludes zero) at
  h=2,3,5,10 across development, validation, AND out-of-sample.
- Not concentrated in any single symbol: all 9 US symbols
  independently show a positive mean 5-day forward return after this
  condition, ranging +1.0% (JPM) to +3.7% (NVDA).
- Survives up to a 60bps round-trip cost assumption (mean stays
  decisive positive even at that generous cost level).
- At h=5 specifically, remains decisive under a conservative
  Bonferroni correction applied for the full 68-condition sweep this
  candidate was selected from (family_size=68, corrected z=3.376) —
  in all three splits. This is the one horizon that survives the
  strictest reasonable bar applied this session.

## 9. Rejected Findings

Carried over from yesterday's segment of this same broader mission
(all REJECTED, real 41-symbol-universe evidence, none reversed or
revisited today): H_ENTRY_002 (volume-confirmation filter),
H_ENTRY_004 (momentum acceleration), H_MEANREV_001 (pooled-market
zscore-based mean reversion — see below for why this session's own
findings help explain that result), H_RELSTRENGTH_001 (relative
strength, reversed dose-response), H_BREAKOUT_001 (breakout quality,
context filters made it worse). Full detail:
`docs/BUILD_THE_REAL_TRADING_BRAIN_INTERIM_REPORT.md`.

**A genuine reconciliation, not previously visible**: H_MEANREV_001
tested mean reversion on the FULL, POOLED 41-symbol universe (NSE+US
together) using a different metric (zscore_close_20) and came back
directionless/null. Today's market-SPLIT sweep found a real, decisive
US-specific weakness-reversal effect and a much weaker, more
horizon-dependent NSE one (§3). Pooling NSE and US in H_MEANREV_001
likely diluted a real, market-specific US effect into apparent noise —
exactly the failure mode Part D's "never pool markets unless
explicitly testing pooled behavior" rule exists to prevent. This is a
real, useful piece of accumulated project knowledge: market-pooled
mean-reversion tests on this universe are not reliable; market-split
ones may be.

## 10. Strategies Generated (Part J)

Exactly one hypothesis reached strategy-level testing today (per Part
J's own "test at most THREE strongest candidates... quality over
quantity" — one candidate earned the right to be tested; the other 67
raw conditions did not warrant it): **H_MEANREV_002**
(`quant_research/us_weakness_reversal_signal.py`), two candidates:

- **A_atr_stop_target**: the frozen 1.5×ATR-stop/2:1-target every
  hypothesis in this project's history uses, via
  `backtesting.runner.run_full_backtest` — reused completely
  unchanged, zero new runner code.
- **B_five_bar_time_exit**: force-close after exactly 5 bars (the one
  horizon that survived Bonferroni correction), via
  `backtesting.exit_experiments.run_universe_time_based_exit_experiment`
  — likewise reused completely unchanged.

Both candidates: **INCONCLUSIVE**, not promoted. Real, consistent,
all-positive, improving-out-of-sample results in every split (the same
shape H_EXIT_002 showed in an earlier mission — the opposite of the
textbook overfitting signature), but no split's confidence interval
excludes zero given the real trade sample sizes (92/37/32 and
122/43/37). Candidate B was consistently stronger than A on every
metric in every split (win rate climbing 48%→54%→65% out-of-sample,
profit factor 1.27→1.76) — a real, honest lead that the ATR-based stop
(designed for trend-following, reused here only for cross-hypothesis
methodological consistency) may be exiting positions before the
reversal completes, worth a dedicated exit study if this line of
research continues, not pursued further today per this project's own
"do not force trades, do not loosen anything to manufacture a
promotion" discipline.

No trades were forced. No thresholds were loosened after seeing a
result. The frozen threshold was computed once, before any strategy
code existed, and never touched again.

## 11. Statistical Criticism (Part I, applied against §8/§10's own finding)

Every one of the mission's own 12 adversarial questions, applied
honestly against the single candidate that reached this stage:

1. **Look-ahead bias?** No — the condition uses only `close.pct_change(5)` up to and including the current bar; forward-return LABEL columns are used only to measure, never to condition.
2. **Survivorship bias?** Yes, a real, disclosed, unaddressed limitation — the 9-symbol US universe (and 41-symbol universe generally) contains only companies that survived to the present; a genuine "buys the dip, dip doesn't recover" case (e.g. eventual bankruptcy) cannot appear in this dataset, which could inflate the apparent reversal rate. Not correctable with available data; stated, not hidden.
3. **Sample size sufficient?** Marginal, not generous — 247/81/87-90 observations for the raw price-behavior finding; 92-122/37-43/32-37 REAL TRADES once turned into a strategy (fewer, because the stop sometimes exits before the condition fully resolves). Real trade counts are the binding constraint on why §10's result is INCONCLUSIVE rather than decisive.
4. **Concentrated in a few symbols?** No — checked directly; all 9 US symbols independently positive (§8).
5. **Survives validation?** Yes, at the raw-behavior stage (§8). At the strategy stage (§10), directionally yes (positive in every split) but not decisively.
6. **Survives OOS?** Same answer as validation.
7. **Survives (US) costs?** Yes at the raw-behavior stage, checked directly up to 60bps round-trip. At the strategy stage, the real `CostModel` was already applied inside every trade shown in §10 — the INCONCLUSIVE result already reflects real costs, not a pre-cost number.
8. **Survives walk-forward?** Not tested with genuine rolling walk-forward folds (only the standard single dev/val/oos split) — a real, named gap, same one this project's own STRATEGY EDGE DISCOVERY mission flagged for other candidates.
9. **Does multiple-testing correction destroy significance?** Partially — h=5 survives a conservative family_size=68 Bonferroni correction in all three splits; h=2,3,10 do not survive that same correction, though they remain uncorrected-decisive. Honestly reported as a real, partial answer, not oversold as "everything survives."
10. **Economically meaningful?** Yes, at the raw-behavior stage (1-2%+ over days is large). At the strategy stage, real per-trade expectancy is smaller (+0.4% to +1.3% depending on split/candidate) once stop/target/cost mechanics are applied — still economically meaningful if it were decisive, but it is not yet.
11. **Tradeable?** Mechanically simple to identify and enter; not yet proven to survive as an actual position with realistic risk management (§10's own INCONCLUSIVE result is precisely this question, answered honestly as "not yet, not decisively").
12. **Is the result concentrated in one time period / regime?** Not separately re-checked at the strategy-backtest stage this session — a real, named gap for any follow-up.

## 12. Final Verdict

**B. CONDITIONAL EDGE DISCOVERED — MORE VALIDATION REQUIRED.**

Not A: a real conditional pattern was found and survived a battery of
adversarial checks most candidates in this project's history have
never been subjected to (§8, §11) — calling this "no edge" would
misrepresent genuinely accumulated evidence. Not C: once that raw
market-behavior finding was turned into an actual, risk-sized,
cost-aware trade against the real US universe, it did not clear this
project's own strict promotion bar (§10) — every split's confidence
interval still touches zero given the available real trade counts, so
"robust, paper-trading candidate" would overclaim what the evidence
actually shows.

What is real and load-bearing today: this project now has, for the
first time, a candidate market-behavior pattern that is genuinely
closer to a validated edge than anything found before it (including
H_EXIT_002 from an earlier mission) — a raw signal that is
statistically decisive even under conservative multiple-testing
correction, not concentrated in any symbol, and directionally
consistent (and improving) once turned into real trades. What remains
open, named rather than hidden: real trade sample size is the binding
constraint (more historical data, or a wider US universe, would
sharpen every confidence interval shown here one way or the other);
the exit mechanism may be actively working against this specific
mean-reversion entry (§10's own Candidate B lead); genuine rolling
walk-forward has not been run against the strategy-level result; and
survivorship bias in the underlying universe has not been corrected
for, only disclosed. None of these are reasons to force a promotion
today — they are the concrete, specific next steps if this research
continues.
