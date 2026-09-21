# Phase 6 Decision Gate, and Terminal Report — Derivatives Research Program

Final controlled derivatives pass (2026-09-21, continuing from `8f6c9cb`). This document is the
mission's own required terminal report: data availability, data quality, what was tested, exact
preregistration, results, OOS evidence, multiple-testing treatment, economic implications, and
remaining limitations, for the ENTIRE derivatives research program (both the futures pass and this
options-volatility-surface pass).

## Phase 6 decision gate

Per the mission's own explicit instruction: **"If options volatility does NOT provide meaningful
incremental OOS information: CLOSE THE DERIVATIVES RESEARCH PROGRAM."** Neither DERIV_003 (ATM IV
level, ΔAUC negative on both splits) nor DERIV_004 (put/call IV skew, ΔAUC positive but 6-12x below
the pre-registered threshold on both splits) cleared the frozen decision rule. **The gate is not
passed. Phases 7-10 (frozen trading experiment, economic validity, portfolio realism, independent
replication) do not apply — they were explicitly gated behind this decision and are correctly not
executed.**

## Data availability (full program)

- **Futures**: real, historically deep (verified to 2015-12-31, 2,554 daily bars), and — a major
  mid-program discovery — already-continuous across contract rolls via Dhan's own
  `/charts/historical` with a relative `expiryCode` selector (no manual rollover-stitching needed
  for the index-futures case actually used).
- **Options OHLC/OI/volume**: real, available via both NSE bhavcopy (EOD, full chain, no IV) and
  Dhan's `/charts/rollingoption` (intraday, ATM-relative, with ready-made IV — used for this pass).
- **Options IV specifically**: real, available ONLY via Dhan's `/charts/rollingoption` — NSE
  bhavcopy carries no IV field at all. Confirmed historically available to at least ~4.5 years back,
  intraday (1-60 minute) resolution, for both index and stock options.
- **A real, reproducible Dhan API defect** was found and disclosed in this pass: `expiryCode=0`
  ("current/near expiry," the documented default) is rejected by `/charts/rollingoption`
  specifically; only `expiryCode=1`/`2` ("next"/"far") work — meaning genuine "current expiry" IV
  data is not obtainable from this endpoint at all, a real, disclosed ceiling on what "term
  structure" could ever mean using this data source (not attempted in this pass, per its own
  two-feature scoping).
- **yfinance**: confirmed (prior pass) to have zero NSE options capability at all.

## Data quality

- **Illiquidity**: the raw NSE bhavcopy full option chain is dominated by untraded strikes (85.8%/
  75.2% zero-volume for OPTSTK/OPTIDX, prior pass's own real measurement). The ATM-restricted Dhan
  rolling-option endpoint used in THIS pass is, by contrast, genuinely liquid: 0% zero-volume/
  zero-OI/null-IV in a full-month real sample.
- **A real, quantified defect found and guarded against this pass**: the final 1-2 trading sessions
  before a contract's own expiry show BOTH degenerate near-zero IV readings (0.0, 0.4) AND
  implausible volume spikes (~1,000x every other bar in the same series) — a genuine raw-feed
  artifact, not a processing bug. Guarded via two frozen, pre-registered, non-tuned rules
  (`MIN_PLAUSIBLE_IV_PCT=3.0`, a 20x-trailing-median volume ceiling), implemented in
  `quant_research/iv_surface.py` and verified this pass to remove 1.2%/4.8% of raw bars for the two
  features respectively — a small, targeted, disclosed exclusion, not a broad data-quality failure.

## What was tested (the full derivatives research family)

| ID | Question | Verdict |
|---|---|---|
| DERIV_001 | Futures basis: incremental h10 prediction beyond OHLCV? | NO MEANINGFUL INCREMENTAL INFORMATION |
| DERIV_002 | Futures OI change: incremental h10 prediction beyond OHLCV? | NO MEANINGFUL INCREMENTAL INFORMATION (weaker than DERIV_001, negative on OOS) |
| DERIV_003 | ATM IV level: incremental h10 prediction beyond OHLCV+futures? | NO MEANINGFUL INCREMENTAL INFORMATION (negative on both splits) |
| DERIV_004 | Put/call IV skew: incremental h10 prediction beyond OHLCV+futures? | NO MEANINGFUL INCREMENTAL INFORMATION (6-12x below threshold) |

**Four hypotheses, four genuinely distinct information families (price-level basis, positioning/OI
flow, volatility level, volatility asymmetry), all pre-registered before their own results were
seen, all decisively or near-decisively negative, none tuned or re-run after seeing its own
outcome.**

## Exact preregistrations (for the record)

- `docs/research/DERIV_001_FUTURES_BASIS_INFORMATION_CONTENT_PREREGISTRATION.md`
- `docs/research/DERIV_002_FUTURES_OI_CHANGE_INFORMATION_CONTENT_PREREGISTRATION.md`
- `docs/research/DERIV_003_004_IV_SURFACE_INFORMATION_CONTENT_PREREGISTRATION.md`

## Results and OOS evidence

See `DERIV_001_RESULTS.md`, `DERIV_002_RESULTS.md`, `DERIV_003_004_RESULTS.md` for full per-entry
detail (data, splits, ROC-AUC/Brier/calibration tables, decision-rule checks). Summary: every entry
evaluated its augmented model against untouched validation AND out-of-sample splits, never re-fit
after seeing a result. The best-performing single result across all four entries (DERIV_004,
put/call IV skew) still fell 6-12x short of the pre-registered 0.02 ΔAUC threshold on both
decision-relevant splits.

## Multiple-testing treatment

`strategy/multiple_testing.py`'s own `bonferroni_corrected_z` primitive applied at `family_size=4`
(the full derivatives program) → z=2.4977 (vs. uncorrected 1.96), disclosed for completeness in
`DERIV_003_004_RESULTS.md`. Not decision-relevant in practice: every entry's own decision rule used a
FIXED, pre-registered effect-size threshold (ΔAUC ≥ 0.02), not a p-value subject to this kind of
correction, and every entry missed that fixed threshold by a wide margin regardless of correction
stringency. This derivatives family was tracked entirely separately from the 59-entry OHLCV registry
throughout (`strategy/hypothesis_registry.py` was never touched by this program), per the mission's
own explicit "do not bury it inside the old count" instruction.

## Economic implications

None of the four tested information families reached the statistical bar (Phase 6) required to even
attempt a costed trading test (Phase 7). No brokerage/fee/slippage/liquidity/capital-constraint
analysis was performed on any of them, because none qualified — exactly matching the mission's own
explicit "do not claim trading edge from statistical prediction improvement alone" instruction, run
in the conservative direction (no result was strong enough to even warrant the economic-validity
check). Real order execution remains disabled throughout; this research program never came close to
a live/paper promotion decision.

## Remaining limitations (honest, complete accounting)

1. **DERIV_003/004's own sample size fell below the pre-registered floor** (validation n=77, out_of
   -sample n=84, vs. a target of ≥100) — a real, disclosed data-adequacy limitation stemming from the
   options IV data's own shorter reliable historical window (~2.2 years used) intersected with the
   temporal 60/20/20 split. Both results were decisive misses regardless (one negative-signed, the
   other an order of magnitude short), so this limitation affects confidence in "no effect exists at
   all," not the finding that "no effect was found at this sample size."
2. **Scope was deliberately narrow, by design, not by oversight**: NIFTY-index-level only (not
   individual stocks); a single horizon (h10); a single model class (logistic regression); two IV
   features out of five named candidate families (level, skew tested; strike-based skew and term
   structure explicitly deferred, per Phase 3's own disclosed scoping decision); `expiryCode=0`
   ("current/near expiry") could never be tested at all due to a real Dhan API defect. A materially
   different design along any of these axes was not attempted, matching the mission's own explicit
   "do not test dozens of alternatives" instruction — these remain genuinely open questions, not
   silently closed ones.
3. **No bid/ask data exists in either NSE bhavcopy or Dhan's rolling-option endpoint** — any future
   work needing microstructure/execution-cost realism at the OPTIONS level (as opposed to the
   underlying equity, which does have such data via other providers) cannot be built from either
   source used in this program.
4. **Stock-level (FUTSTK) continuous-futures-series behavior was never verified** — Dhan's own
   already-continuous rollover handling was confirmed only for NIFTY (`FUTIDX`); whether the same
   convenience extends to individual stock futures remains an open, untested question.

## Terminal classification

**NO DEMONSTRATED EDGE WITH CURRENT INFORMATION SET.**

Per the mission's own explicit closing instruction: at this point, the next research decision must
involve a genuinely different information source or market/data domain — not another derivatives
variant, not another threshold, not another model class applied to the same four information
families. This is a decision for the user, not an automatic next step this session takes on its own
initiative. No `DERIV_005` or later entry was created to keep the program going. Real order execution
remains disabled; the live fleet was not modified by any part of this research program.
