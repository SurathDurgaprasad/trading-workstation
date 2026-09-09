# H_MEANREV_004 — Executable Regime-Gated Mean Reversion, Pre-Registration

Written and frozen **before** any experiment code runs. Per this
project's own multiple-testing discipline: the signal definition, exit
mechanics, universe, splits, cost model, and success/failure criteria
are fixed here; none may change after seeing results.

## 1. Research question

Does `H_MEANREV_003`'s raw finding — oversold mean-reversion entries
conditioned on NIFTY's own `TRENDING_UP` regime, CI-decisive positive
across all three splits and both frozen candidates, at every horizon
tested — survive becoming a real, cost-aware, risk-sized trade? The
same "does the raw finding survive becoming an actual trade" question
`H_XSECT_002` already asked of `H_XSECT_001`'s own raw finding, and
`H_MEANREV_002` asked of its own US-only finding.

**Explicitly not assumed**: this project's own repeated lesson
(`H_XSECT_002`/`004`: a wide raw-measurement cost margin does not
guarantee an executable, stop/target-managed strategy survives, often
because of a stop mechanic mismatched to the signal's own mechanism)
applies here with equal force. No outcome is assumed.

## 2. Signal and exit mechanics (frozen)

Reuses `quant_research/mean_reversion_signal.py`'s existing
`MeanReversionSignalStrategy` completely unchanged in its stop/target
mechanic (`strategy.baseline.STOP_ATR_MULTIPLIER`/`TARGET_RISK_REWARD`,
the same frozen constants `H_MEANREV_001`'s own original candidates
already used) — this experiment tests the entry-timing question (does
adding a regime gate help) in isolation, not a new exit design, the
same "test one variable" isolation posture every hypothesis in this
project already takes.

Two new candidate predicates, added alongside (not replacing) the
existing `CANDIDATES` dict: `A_oversold_2std_trending_up`
(`zscore_close_20 < -2.0 AND market_trend_regime == "TRENDING_UP"`) and
`B_oversold_1_5std_trending_up` (`< -1.5 AND TRENDING_UP`) —
`H_MEANREV_001`'s own frozen thresholds, reused verbatim, with
`H_MEANREV_003`'s own regime gate added. `market_trend_regime` is
attached via the same `quant_research.context_experiments.
build_benchmark_regime_series`/`attach_external_regime` machinery
`H_MEANREV_003` already used.

## 3. Universe, data, costs (frozen)

Full original 32-symbol NSE universe
(`quant_research.universe_expansion.ORIGINAL_32_NSE_UNIVERSE`), 10
years daily — NSE-only, matching `H_MEANREV_003`'s own universe
exactly (not `H_MEANREV_001`'s original pooled NSE+US design).
`CostModel.india_nse_intraday_2026()` — a disclosed, deliberate
improvement over `H_MEANREV_001`'s own original runner, which used the
generic, non-NSE-specific default `CostModel()` (no fees/taxes,
smaller slippage) since that test predates this project's own later
`india_nse_intraday_2026()` preset. `risk.engine.RiskEngine`, default
config, matching every other `H_XSECT`/`H_MEANREV` executable test.

## 4. Splits and evaluation

`backtesting.splits.split_periods` 60/20/20, matching every prior entry
in this thread. Evaluated via `strategy/promotion_gate.py::evaluate_promotion`
(`backtesting.universe.per_trade_returns`), the same mechanical
dev/val/oos verdict every `H_XSECT_00x`/`H_MEANREV_00x` candidate is
judged by — no new or looser bar.

## 5. Success / failure criteria (frozen)

**Success**: at least one candidate reaches a confident
`POSITIVE_PERFORMANCE` verdict (development AND validation AND
out-of-sample) via `evaluate_promotion`.

**Failure**: neither candidate reaches a positive verdict in all three
splits — i.e., the raw price-behavior edge does not survive becoming
an actual, cost-aware, risk-sized trade.

## 6. Anti-p-hacking discipline

If this fails, the stop-width investigation this project already ran
once (`H_XSECT_004`: both a wider and an absent stop performed *worse*
than the original, a genuine, disclosed correction to a naive
diagnostic reading) is the most relevant prior precedent for how NOT
to respond — no stop/target retuning is planned as an automatic
follow-up. Any different exit design would need its own new, honestly
pre-registered hypothesis, decided only after seeing this result's own
exit-reason diagnostic (mirroring `H_XSECT_002`'s own diagnostic
methodology), not chased reflexively.

## 7. Reproducibility record

- Universe: `quant_research.universe_expansion.ORIGINAL_32_NSE_UNIVERSE`, all 32 built successfully (`failed_symbols: {}`).
- Benchmark: `^NSEI`, `period="10y"`, fetched once via `build_benchmark_regime_series`.
- Cost model: `CostModel.india_nse_intraday_2026()`.
- New module code: `quant_research/mean_reversion_signal.py` — `REGIME_GATED_CANDIDATES`, `MeanReversionSignalStrategy.__init__`'s new optional `candidates` parameter, `UniverseRegimeGatedMeanReversionExperimentResult`, `run_universe_regime_gated_mean_reversion_experiment` (18 new tests in `tests/test_mean_reversion_signal.py`, verified via the full-suite count delta: 1858→1876).

## 8. Results — REJECTED/INCONCLUSIVE (neither candidate clears the frozen success bar)

Full evidence: `H_MEANREV_004` in `strategy/hypothesis_registry.py`.

| Candidate | Split | n | Mean return | 95% CI | Verdict |
|---|---|---|---|---|---|
| A (−2.0σ) | development | 428 | +0.43% | [-0.15%,+1.00%] | STATISTICALLY_MEANINGLESS |
| A | validation | 126 | -0.14% | [-1.00%,+0.71%] | STATISTICALLY_MEANINGLESS |
| A | out-of-sample | 134 | +0.57% | [-0.20%,+1.34%] | STATISTICALLY_MEANINGLESS |
| B (−1.5σ) | development | 708 | +0.42% | [-0.02%,+0.85%] | STATISTICALLY_MEANINGLESS |
| B | validation | 208 | +0.20% | [-0.46%,+0.86%] | STATISTICALLY_MEANINGLESS |
| B | out-of-sample | 233 | +0.42% | [-0.15%,+0.99%] | STATISTICALLY_MEANINGLESS |

`evaluate_promotion` overall: Candidate A `REJECTED`, Candidate B
`INCONCLUSIVE`. **Neither candidate clears the frozen §5 success
criterion** ("at least one candidate reaches a confident
POSITIVE_PERFORMANCE verdict in all three splits") — every split for
both candidates has a CI straddling zero. This is §5's own explicit
failure condition.

**Mechanism (diagnostic on the already-computed trades, per §6 — not a
signal to retune anything)**: STOP exits dominate in every split for
both candidates (Candidate A: 58.9%/63.5%/58.2% of trades in dev/val/
oos; Candidate B: 58.1%/59.1%/57.1%). This is the same shape
`H_XSECT_002`'s own exit-reason diagnostic found for the cross-
sectional laggard signal: `strategy.baseline`'s frozen ATR stop, built
for `TrendMomentumBaseline`'s trend-*continuation* logic, plausibly
clips this reversal-type entry before the recovery `H_MEANREV_003`'s
own raw measurement captured can complete.

**Per §6's own frozen discipline: no stop/target retuning follows from
this result.** `H_XSECT_004` already tested exactly this idea (wider
stop, no stop at all) for an analogous reversal signal and found *both*
performed **worse**, not better — the working explanation there was
that a meaningful fraction of reversal candidates simply keep moving
against the position and never revert, and the stop was doing real,
protective work invisible in the raw pooled measurement. There is no
reason to expect a different outcome here without first testing it,
and testing it would itself need to be a new, honestly pre-registered
hypothesis — not assumed, not chased in this same run.

**Verdict: REJECTED.** `H_MEANREV_003`'s raw finding — clean, broad,
cost-margin-surviving, non-decaying at the raw-measurement level — does
**not** survive becoming an actual, stop/target-managed trade with this
project's existing, frozen exit mechanic. This is now the **second**
time in this project's history a cleanly-validated raw NSE measurement
has failed this specific conversion (`H_XSECT_001`→`H_XSECT_002` being
the first), which is itself a notable, recurring pattern about this
project's frozen stop/target design more than about either individual
signal. `H_MEANREV_003`'s own raw-measurement finding is **not**
invalidated by this result — it remains a real, well-validated
statistical fact about NSE price behavior under `TRENDING_UP`
conditioning; what is rejected is this specific executable design.
