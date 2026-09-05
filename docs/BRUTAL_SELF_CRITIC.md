# Brutal Self-Critic

Scientific strategy research foundation, Priority #9. An independent,
adversarial audit of this project's own scientific claims — looking for
reasons every prior finding might be wrong, not confirming it. Source of
truth is always the code and real data, not this document; every claim
below is checked against what was actually run, not what was hoped for.

## 1. Data leakage — reviewed, structurally guarded, one boundary
   characteristic documented (not a leak)

**Look-ahead bias** (using information not yet available at decision
time) is guarded by dedicated tests at every layer that could introduce
it: `tests/test_backtest_lookahead.py` (the general pattern — mutate a
future row, confirm an earlier classification is unchanged),
`backtesting/regime.py`'s own `test_classify_trend_never_reads_rows_
after_index_look_ahead_safety` / `test_classify_volatility_never_reads_
rows_after_index_look_ahead_safety`, and `backtesting/walk_forward.py`'s
`test_walk_forward_fold_trades_never_depend_on_data_past_that_folds_own_
end`. These are genuine tests (verified failing before their fix, per
this project's own established discipline), not aspirational comments.

**A real, investigated boundary characteristic — not leakage**: rolling
indicators (SMA20/SMA50/RSI14/MACD/ATR14) are computed ONCE over each
symbol's FULL fetched series (`backtesting/runner.py`'s
`run_full_backtest`, `compute_indicator_series(ohlcv)` happens BEFORE
`split_periods`/`_slice_period`), so the validation period's own first
bars carry indicator values whose lookback windows extend back into the
development period. This is **not look-ahead** (indicators only ever use
PRIOR bars, never future ones) — it is standard, accepted practice for
chronological walk-forward validation, and the alternative (recomputing
indicators from scratch at each period boundary, discarding all prior
warm-up) would be LESS representative of how the strategy is actually
deployed (a real live system always has trailing history available).
The dangerous version of this concern — strategy PARAMETERS tuned using
data that included the out-of-sample period — does not apply:
`strategy/baseline.py`'s constants (`STOP_ATR_MULTIPLIER`,
`TARGET_RISK_REWARD`) are hardcoded, never fit to any period, and
`strategy/manifest.py`'s `manifest_matches_current_code()` mechanically
detects any silent drift in that source.

**Confirmed, not assumed**: no trade spans a period boundary. Each of
`run_full_backtest`'s three period backtests operates on an
INDEPENDENTLY sliced `indicator_series` (`_slice_period`), and
`backtesting/engine.py`'s own loop force-closes any position still open
at the end of its own slice via `END_OF_DATA` — a trade can never open
in development and resolve in validation. The honest cost of this: a
position opened near a period's end is forced to close early
(`END_OF_DATA`) at a potentially unrepresentative point, a real but
minor boundary distortion, not a leakage bug.

## 2. Survivorship bias — REAL, PRESENT, and (if anything) working
   AGAINST the negative finding, not for it

The 41-symbol universe (`data/market/`) is a hand-curated watchlist of
currently well-known, currently-listed large-cap companies (RELIANCE.NS,
TCS.NS, AAPL, MSFT, GOOGL, and 36 others) — not a systematic
reconstruction of "every company that existed in this universe 5 years
ago." **This is genuine survivorship bias**: any company that was
delisted, went bankrupt, or was acquired during the 5-year backtest
window is structurally absent, because a company in that state would not
appear on a watchlist assembled today. This was not previously stated
explicitly anywhere in this project's documentation and should have
been.

**Why this matters, and why it doesn't rescue the strategy**: survivorship
bias typically makes a backtest look BETTER than reality (failed
companies, which would have generated disproportionately large losses,
are excluded). This project's own real result is `TrendMomentumBaseline`
showing NEGATIVE_PERFORMANCE (mean return −0.64%, 95% CI entirely below
zero) on a sample that is *biased toward looking better than a
representative universe would*. If anything, this strengthens rather
than weakens the "no demonstrated edge" conclusion: a more representative
universe including delisted/failed companies would plausibly show
performance at least as poor, not better. **The negative finding is not
an artifact of an unlucky sample — a lucky (survivorship-biased) sample
still produced a negative result.**

## 3. Multiple testing bias — already mechanized, reviewed here as CLEAN

`strategy/multiple_testing.py`'s Bonferroni correction was applied for
real to this project's own 4 exit-hypothesis out-of-sample results
(family size 4, corrected z=2.4977): no split survived correction as
positive — the same conclusion as before correction. The 9-hypothesis
family size (H_ENTRY_001-005, H_EXIT_001-004) recorded in `strategy/
hypothesis_registry.py` was also used as a direct test fixture
(`bonferroni_corrected_z(9)`). **One honest limitation**: the correction
has only ever been applied to the 4 exit hypotheses' own out-of-sample
splits, not to the FULL space of every statistical comparison this
project has run (every regime bucket, every walk-forward fold, every
baseline comparison also carries a chance of a false positive if
considered as its own "test"). Given that NONE of these additional
comparisons produced a positive result to begin with, a wider correction
could only push already-negative/meaningless verdicts further from
significance, never create a false promotion — but the narrower scope of
what was actually corrected should be stated plainly rather than implied
to cover everything.

## 4. Overfitting — guarded structurally, not just by intention

No strategy parameter has ever been tuned against validation or
out-of-sample data in this project's own experiment history. This is not
merely a stated intention: `strategy/manifest.py`'s `entry_rules_hash`/
`exit_rules_hash` mechanically detect any silent drift in `strategy/
baseline.py` or `backtesting/execution.py`'s source, and every H_EXIT_*
exit-hypothesis experiment this project ran used a FULLY ISOLATED
execution engine (`backtesting/exit_experiments.py`) specifically so an
experiment could never accidentally alter the frozen baseline's own
historical results. **One real overfitting-adjacent risk, honestly
flagged**: the same 41-symbol, 5-year universe has now been reused across
9+ hypotheses. Even without literal parameter tuning, choosing WHICH
hypotheses to test next based on what's already been observed on this
SAME dataset (a human or LLM researcher's own judgment, informed by
prior results on this data) is a subtler form of the same risk that
multiple-testing correction partially, but not perfectly, addresses.

## 5. Insufficient sample sizes — explicitly enumerated, not glossed over

- **Regime buckets**: only TRENDING_UP + NORMAL_VOLATILITY (283 of 368
  pooled trades) has ≥30 trades. Every other (trend, volatility)
  combination is genuinely under-sampled — `strategy/hypothesis_registry.
  py`'s own H_ENTRY_005 record states this as INCONCLUSIVE, not falsely
  negative, for exactly this reason.
- **Entry hypotheses**: H_ENTRY_002/003/004 remain OPEN — never
  implemented or tested at all this mission, not merely under-sampled.
- **Walk-forward folds**: the smallest fold (Fold 0) has 33 trades, just
  above the 30-trade floor — a thinner margin than the other five folds,
  worth flagging as the least statistically robust single data point in
  that analysis even though it technically clears the floor.

## 6. Invalid statistical conclusions — reviewed, one caveat surfaced
   consistently, confirmed present everywhere it's needed

Every `ProfitabilityReport.reasoning` text this project's single
statistical standard (`learning.profitability.
compute_profitability_report_from_returns`) produces already states its
own limitation: "This is a normal-approximation interval over a still-
small sample for a trading system — treat it as directional evidence,
not proof." This caveat is structurally part of the report object
itself, not something a caller could omit by accident. No claim reviewed
in this project's own documentation (`docs/SCIENTIFIC_FINAL_REPORT.md`
and every phase-specific doc) asserts a conclusion stronger than what the
verdict label itself supports — verified by re-reading each real result
cited in this document and confirming the verdict label matches the
plain-language claim made about it.

## 7. Hidden coupling between development and out-of-sample datasets

Addressed directly in item 1 above (indicator warm-up crossing the
period boundary) — the one real form of coupling that exists, and it is
NOT the dangerous kind (no parameter fitting crosses the boundary, no
trade spans periods). No other coupling mechanism was found: each period
gets its own independently-sliced `run_backtest` call with no shared
mutable state between them, and `backtesting/exit_experiments.py`'s own
full-isolation design (see item 4) specifically prevents an exit-hypothesis
experiment from letting its results leak back into the frozen baseline's
own dev/val/oos numbers.

## Summary verdict of this audit

Every mechanism check performed here confirms this project's own existing
process is sound: no look-ahead leakage, no cross-period trade bleed, no
parameter tuning against held-out data, and honest, consistent
statistical caveats. **The one genuinely new, previously-unstated finding
is survivorship bias in the 41-symbol universe** — real, and worth
disclosing explicitly in every future report referencing this dataset,
but one that (on the evidence available) makes the existing
NEGATIVE_PERFORMANCE conclusion more credible, not less.
