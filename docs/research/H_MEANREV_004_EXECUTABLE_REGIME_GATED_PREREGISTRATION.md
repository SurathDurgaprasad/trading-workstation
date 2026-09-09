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

## 7. Reproducibility record (filled in at execution time)

To be completed after the experiment runs: exact trade counts per
split per candidate, exit-reason breakdown, and the promotion-gate
verdict.
