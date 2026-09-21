# Phase 2 — Evaluation Audit (partial pass — infrastructure verified, per-hypothesis pass pending)

Scope note: this pass verifies the SHARED evaluation infrastructure (cost model, sample-size floor,
multiple-testing correction) directly against source code, since these apply across most of the 56
entries and are the highest-leverage things to get right first. A full per-hypothesis leakage/split-
integrity audit of all 56 entries is still open (tracked in STATE.json) and will proceed in a later
pass.

## Cost model — VERIFIED, with one disclosed gap

`backtesting/costs.py::CostModel.india_nse_intraday_2026()`:
```python
brokerage_per_fill=20.0   # flat INR, charged on entry AND exit each (field docstring, verified)
fees_pct=0.00375          # NSE exchange charges
taxes_pct=0.025           # STT
entry_slippage_bps=5.0
exit_slippage_bps=10.0    # blueprint's own "0.05% baseline" MPP slippage estimate
```
The H_MEANREV_009 registry claim ("FIXED brokerage_per_fill=20.0... charged on entry AND exit") is
confirmed exactly against source, not just registry prose.

**Disclosed gap, not hidden**: the class's own docstring states GST and stamp duty are omitted
("small relative to STT/brokerage at this level of approximation; revisit before relying on this for
real P&L"). This is an honest, stated limitation. It does not change the qualitative conclusion for
any REJECTED entry (adding more cost only makes a negative result more negative), but it DOES mean
every POSITIVE_PERFORMANCE point estimate in the registry (e.g. H_MEANREV_010 Candidate 2/3) is
understated in cost by an unquantified amount. Real-money reliance on any INCONCLUSIVE-positive result
would need the fuller blueprint cost table first.

## 30-trade sample floor — VERIFIED

`strategy/promotion_gate.py`: `MIN_SAMPLE_SIZE_FOR_A_VERDICT=30`; any split below 30 trades yields
`INSUFFICIENT_DATA`, and the promotion verdict function documents "no amount of beating a benchmark
rescues" an insufficient-data split. Real, hardcoded, consistently referenced. Confirms the registry's
repeated "below the 30-trade floor -> INSUFFICIENT_DATA" language is accurate, not a post-hoc excuse
invented per-entry.

## Multiple-testing correction — VERIFIED as real infrastructure, with a real scope gap

`strategy/multiple_testing.py`: `bonferroni_corrected_z` and `apply_multiple_testing_correction` are
genuine, stdlib-based (`statistics.NormalDist`), mathematically standard Bonferroni correction, with a
real regression test file (`tests/test_strategy_multiple_testing.py`). Not ad hoc.

**Real scope gap, worth flagging explicitly**: `family_size` is, by the module's own docstring,
"the caller's own responsibility to define honestly... this module has no way to know how many tests
were 'really' run against a given dataset." In practice this means correction is applied LOCALLY, per
experiment (e.g. H_MEANREV_012 cites `family_size=3` — almost certainly the small set of candidates
compared WITHIN that one entry, not the registry as a whole). The module's own original docstring
scopes its FIRST use to "9 hypotheses recorded... H_ENTRY_001-005, H_EXIT_001-004" — the registry has
grown to 56 entries since. There is no evidence in the registry text or this module of a single,
registry-wide multiple-testing correction ever having been applied across all 56 (or even all 55
pre-existing) hypotheses tested against overlapping datasets (the 41-symbol and later 206/208-symbol
universes are reused across dozens of entries).

**Why this matters**: with 55+ hypotheses tested, many sharing a dataset, the CLASSICAL multiple-
comparisons risk is that at least one looks significant by chance alone even with zero true underlying
edges anywhere. Per-entry local correction (as practiced) protects against p-hacking WITHIN one
experiment's own candidate set, but does NOT protect against the registry-wide version of the same
risk. This is a genuine, quantifiable audit finding: a global correction is possible to compute
retroactively (Phase 3/4 work) and would be the single most rigorous test of whether the ONE
SUPPORTED-as-negative finding (H_ENTRY_001) and the strongest positive point estimates
(H_MEANREV_010 Candidate 2/3 validation/OOS) survive it. Not yet performed.

## Leakage / look-ahead — spot-checked, not exhaustively audited

`backtesting/engine.py`'s own docstring (seen earlier in this session, unrelated context): indicator
series are built so "a value at row i is derived only from rows <= i... this is what makes the
backtester's no-look-ahead guarantee possible." `market.indicators.compute_indicator_series` was
independently confirmed (this session, for a different purpose) to be the SAME function both the
live pipeline and the backtester use — a genuine, structural no-look-ahead guarantee for indicator
construction specifically, not a claim about every other stage (portfolio scheduling, cross-sectional
ranking, context-filter joins) of the pipeline. `quant_research/mean_reversion_portfolio.py`'s own
registry-cited evidence claims "no-look-ahead independently verified at both the rank-key level and
the full-scheduler level (tests/test_mean_reversion_portfolio.py)" for that specific module — cited,
not yet independently re-verified by this audit.

## 206/208 universe discrepancy — RESOLVED

`docs/research/H_XSECT_006_UNIVERSE_WIDENING_PREREGISTRATION.md` §8: the two excluded symbols are
named explicitly — `GVT&D.NS` and `M&M.NS` — excluded for a **mechanical, non-substantive reason**:
both fail a defensive filesystem-path-safety check ("Refusing to use symbol ... to construct a
filesystem path") because their tickers contain `&`. Not delisting, not a genuine data gap, not
survivorship-related. M&M (Mahindra & Mahindra) is a major, liquid, unambiguously-not-distressed
large-cap — its exclusion has no plausible effect on the mean-reversion (oversold/distressed-name)
results specifically. Low-priority code note (path-construction doesn't handle `&` in a ticker), not a
research-validity issue.

## Survivorship bias — RESOLVED, already disclosed, and the direction matters

The SAME document, §7 item 5, already states this explicitly, in the correct direction, and flags it
as unresolved rather than silently ignored: **the COMBINED universe reflects CURRENT (2026-09-09) F&O
eligibility, not point-in-time historical membership.** Any stock liquid/F&O-eligible at some point in
the 2016-2026 window but since delisted or made ineligible is **entirely absent**. Quoted directly:
"This could inflate the measured effect if such stocks would have disproportionately underperformed (a
classic survivorship-bias direction)." No point-in-time NSE membership data source exists in this
project to fix it.

**Why this matters for THIS audit specifically**: the mean-reversion signal targets severely oversold,
relatively-weak stocks — exactly the population most likely to include names that, in the full
historical record, kept falling and were eventually delisted rather than reverting. Their absence from
the tested universe means the true historical population of "severely oversold NSE stocks" was
systematically easier on this backtest than reality — the H_MEANREV_010 positive point estimates
should be read as a plausible upper bound on the effect's true historical strength, not a
survivorship-bias-free measurement. This does NOT invalidate the REJECTED verdicts elsewhere in the
registry (if anything, a harsher true population would make already-negative results more negative,
not less) — it specifically discounts confidence in the one genuinely positive result identified so
far, which is exactly the result the whole project's promotion decision would hinge on.

## Open (not yet done)

- Per-hypothesis pass over all 56 entries for: split date boundaries genuinely non-overlapping, and
  whether context/regime features (H_CONTEXT_*) that reference "today's" market/sector/VIX state could
  leak same-day information into the forward-return label.
- Retroactive registry-wide Bonferroni correction (family_size=55 or 56) applied to the strongest
  positive point estimates, to see whether they survive the more conservative bar.
- Direct read of `tests/test_mean_reversion_portfolio.py` to independently confirm the no-look-ahead
  claim for the portfolio scheduler, rather than citing the registry's own claim about itself.
