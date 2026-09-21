# Phase 3 — Research Infrastructure Audit

Each item verified directly against source code (not assumed from prior documentation), except
where explicitly marked as re-citing an earlier, already-completed verification from this same
audit session.

| Item | Finding | Classification |
|---|---|---|
| A. Time split logic | `backtesting/splits.py::split_periods` — fixed 60/20/20 dev/val/oos, applied consistently via `shared_period_boundaries` for portfolio-level work and per-symbol `split_periods` elsewhere. Verified directly. | NO ISSUE |
| B. Purge/embargo | No embargo gap exists between splits (`_period_mask`: `<= development_end` / `> development_end & <= validation_end`, no buffer). A trade signaled near a split boundary has its own forward-return label computed a few bars into the next split's calendar window. **Not classic train/test leakage**: every strategy predicate tested is a fixed, pre-specified rule (never a parameter fit on development data), so there is no risk of the model "learning" validation-period information — this only affects a small number of boundary trades' own economic-outcome measurement window, a standard, accepted backtesting convention, not a defect. | ACCEPTED ASSUMPTION (documented here, not previously written down explicitly) |
| C. Label construction | `add_forward_return_targets`: `fwd_return_h = close.shift(-h)/close - 1`, its own docstring explicitly forbids use by any signal-generating code — verified no `Strategy`/predicate function reads a `fwd_return_*` column. | NO ISSUE |
| D/E. Entry/exit timestamp | `compute_fixed_notional_trade`: entry at `signal_idx+1`'s OPEN (slippage-adjusted), exit at `signal_idx+holding_bars`'s CLOSE (slippage-adjusted) — verified directly this session (MEANREV_CHAIN_AUDIT.md). | NO ISSUE |
| F/G. Costs/slippage | `CostModel.india_nse_intraday_2026()` verified directly against source this session (EVALUATION_AUDIT.md): real STT/exchange-fee/brokerage/slippage. GST/stamp duty disclosed-omitted (not hidden). | ACCEPTED ASSUMPTION (already disclosed) |
| H/I/J. Sizing/cash/exposure | `_run_schedule` verified directly this session: chronological, capacity-capped, cash-capped, one-position-per-symbol. | NO ISSUE |
| K. Concurrent-position handling | Same function — verified correct release-before-accept ordering. | NO ISSUE |
| L. Universe membership timing | Current-F&O-eligibility-based, not point-in-time — the central Phase 2 finding, PARTIALLY_AVAILABLE fix path identified, not implemented this session. | DATA LIMITATION (already quantified: 14.7%/140.8% split) |
| M. Corporate actions | No explicit split/dividend-adjustment code exists anywhere in this project. Re-citing an earlier verification from this same session (Priority 6 of the prior live-fleet audit): empirically confirmed against real RELIANCE.NS data spanning its actual 2024-10-28 split that Yahoo applies split-adjustment to OHLC regardless of `auto_adjust=False` — splits are correctly, transparently handled by the data source itself. Dividends are NOT adjusted (`auto_adjust=False`), which is the deliberate, correct choice for realistic as-traded price simulation, not a gap. | ACCEPTED ASSUMPTION (already verified correct, not merely assumed) |
| N. Delisted symbols | No point-in-time delisting handling exists (ties to L) — a delisted symbol simply has no further data past its last trading day and silently stops appearing in any dataset build past that point; its own historical (pre-delisting) trades are still included if it was ever in the queried universe. Given the universe itself is CURRENT-membership (L), a genuinely delisted name would typically already be absent from `EXPANDED_ONLY`/`COMBINED` regardless — this compounds, rather than independently adds to, the survivorship-bias finding already quantified. | DATA LIMITATION (subsumed by L) |
| O/P. Missing/duplicate bars | `OHLCV.from_dataframe` verified directly: filters any row with NaN OHLCV and validates OHLC internal consistency (`_row_has_valid_ohlc_relationship`) before ever constructing a bar. No explicit duplicate-date dedup exists, but Yahoo's own daily-bar API structurally cannot return two rows for the same calendar date for one symbol — a genuine, low-risk assumption, not an oversight. | ACCEPTED ASSUMPTION |
| Q/R. Timezone/session handling | `core/timeutil.to_naive`/`_align_tzinfo` verified: consistently strips/aligns tzinfo before any comparison, matching the same pattern already verified in `critic/engine.py` earlier this session. Daily-bar research does not need intraday session-boundary logic (that's the LIVE pipeline's own, separately-audited concern from earlier today). | NO ISSUE |
| S. Trade ordering (simultaneous signals) | Chronological + alphabetical tie-break, verified directly this session, and already identified (H_MEANREV_011's own preregistration, re-confirmed by H_MEANREV_012/013) as a real, disclosed selection-bias risk for MULTI-POSITION portfolio construction specifically — does not affect single-position measurements. | RESEARCH-DESIGN LIMITATION (already disclosed, already partially tested and NOT found to be the dominant mechanism per H_MEANREV_012) |
| T/U. Statistical CI / sample floor | `learning/profitability.py::compute_profitability_report_from_returns` (95% CI via `_CONFIDENCE_Z`, Wilson-score win-rate CI) and `strategy/promotion_gate.py::MIN_SAMPLE_SIZE_FOR_A_VERDICT=30` both verified directly against source this session (EVALUATION_AUDIT.md). | NO ISSUE |
| V. Multiple-testing accounting | `strategy/multiple_testing.py` verified real (stdlib Bonferroni), but scoped per-experiment, never registry-wide across all 56 hypotheses. This IS a genuine, real, already-identified gap (EVALUATION_AUDIT.md) — addressed further in Phase 4/8 below, not re-litigated here. | RESEARCH-DESIGN LIMITATION (already identified, not yet resolved) |
| W/X. Reproducibility | H_MEANREV_013's own execution this session found development's accepted-trade count reproduced EXACTLY (555 vs. 555 cited) but validation/out-of-sample counts differed by ~9-11 trades from H_MEANREV_011/012's own cited numbers — explained (not a bug): `period="10y"` is a rolling window ending "now," and today's "now" is later than when those entries originally ran, so the window's own tail genuinely includes newer calendar data. **This means "period=10y" experiments are not byte-for-byte reproducible across different run dates by design** — a real, previously-undocumented reproducibility caveat worth recording. | RESEARCH-DESIGN LIMITATION (newly identified this session; not a defect, but should be disclosed on every future `period="10y"`-based experiment) |

## Genuine defects found: NONE

No item above rose to the level of a genuine implementation BUG requiring a code fix, regression
test, or mutation test. All findings are either NO ISSUE (verified correct), ACCEPTED ASSUMPTION
(a deliberate, reasonable, or already-verified-correct design choice), or a DATA/RESEARCH-DESIGN
LIMITATION already substantially disclosed by this project's own prior research discipline. Per
the mission's own instruction ("Only modify code for genuine defects"), no code was changed in
this phase.

## One newly-identified, worth-recording finding

**W/X reproducibility**: any `period="10y"`-style rolling-window experiment is not exactly
reproducible on a later run date. This should be disclosed on every such experiment's own results
going forward (a documentation practice, not a code change) — recorded here rather than silently
noticed and dropped.
