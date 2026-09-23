# Edge Discovery Final Report — 2026-09-23

**Mission**: determine whether this project has a defensible, statistically and economically meaningful trading edge. If not, prove that as efficiently as possible and stop. Offline only — no Dhan live data, no fleet launch, no strategy/RiskEngine/CriticGate changes, real-money execution remains structurally disabled.

**Baseline commit**: `d8ae04f` (branch `final-product-hardening`, synced with `main`). No historical evidence was rewritten, deleted, or reinterpreted; this report only adds new, clearly-labeled evidence.

Legend used throughout: **FACT** (verifiable, not an inference), **RESULT** (a number this session actually computed), **INFERENCE** (a conclusion drawn from results, stated with its own reasoning), **UNKNOWN** (genuinely undetermined, quantified where possible).

---

## 1. Executive Conclusion

**NO DEMONSTRATED EDGE WITH CURRENT INFORMATION SET.**

Prior to this mission, this project had already tested 59 OHLCV-family hypotheses (36 REJECTED, 22 INCONCLUSIVE, 1 SUPPORTED-as-confirmed-non-edge), a 4-hypothesis derivatives program (futures basis/OI, options IV/skew — all "no meaningful incremental information"), and a 1-phase ML triple-barrier baseline ("no evidence of economic edge"). **Zero hypotheses, in the project's entire history, have ever reached PROMOTED.**

This mission's own mandate was to test only genuinely new information sources not already covered by that history: corporate/event information (Family A), market microstructure (Family B), and cross-sectional/relative information materially different from what was already tested (Family C). Family B was closed immediately on a confirmed data gap (§4, §6). Five new, real hypotheses were preregistered and tested across Family A (corporate dividend events) and Family C (cross-sectional momentum, relative volume, relative volatility) — **all five REJECTED** (§9, §10). None reached even Stage-1 (pre-cost) statistical consistency across development/validation/out-of-sample splits, so no hypothesis required Stage-2 cost/portfolio-realism testing (§11, §12) — the same "stop before building unnecessary machinery on a dead signal" discipline this project has applied throughout its history.

**Total tally, this project's full history**: 64 pre-existing hypotheses + 5 new = **69 tested, 0 promoted.**

**Recommendation (§18)**: do not spend another rupee on live data to chase this line of research further. See §17 for what would have to change before that recommendation is revisited.

---

## 2. Existing Evidence Inventory

Full detail in the research-registry reconstruction performed at mission start (not duplicated at length here to keep this report from re-deriving what already exists on file). Summary:

- **Family A (TrendMomentumBaseline entry/exit variants)**: `strategy/hypothesis_registry.py` H_ENTRY_001–005, H_EXIT_001–005. Baseline REJECTED (H_BASELINE_001), confirmed live 2026-09-21 (4.7% win rate vs. ~33% breakeven).
- **Mean reversion**: H_MEANREV_001–014. Best raw finding (H_MEANREV_003 regime-gated oversold) fails at execution (H_MEANREV_004) and, after point-in-time universe correction, fails at portfolio level even at the single-symbol stage that survived (H_MEANREV_014) — formally closed in `audit/edge_feasibility/CAPITAL_ALLOCATION_DECISION_FINAL.md` ("Path 1... closed").
- **Breakout/relative strength/momentum**: H_RELSTRENGTH_001, H_BREAKOUT_001, H_VOL_001, H_EXTREME_001, H_MOMENTUM_001 — all REJECTED or INCONCLUSIVE-underpowered.
- **Cross-sectional laggard reversal**: H_XSECT_001–006. Strongest raw measurement in project history (H_XSECT_001, survives era-stability and a cost haircut) — but every executable wrapper (ATR stop/target) fails (H_XSECT_002/004), and universe-widening reverses the raw effect (H_XSECT_006).
- **Market/sector/VIX context (F_CONTEXT)**: H_CONTEXT_MARKET/SECTOR/VIX/ALIGN/TRANSMISSION_* — era-unstable effect (sign reverses 2016–2022 vs. 2022–2026), neither of two pre-declared explanatory regime variables (realized vol, India VIX) explains the instability. Formally closed (H_CONTEXT_MARKET_007, "Path 2... closed").
- **Gap/calendar/breadth/sector-rotation**: H_GAP_001–003, H_CALENDAR_001–002, H_BREADTH_001, H_SECTOR_ROTATION_001 — real, replicated effects (Tuesday effect, gap-fade) that die on realistic cost margins, execution-vehicle limits, or liquidity/sector concentration under adversarial "try to kill it" validation.
- **Derivatives**: `audit/derivatives_research/` DERIV_001–004 — futures basis/OI and options IV/skew all show no meaningful incremental OOS information beyond OHLCV; terminal report explicitly instructs that the next step must be a genuinely different information source, not another derivatives variant.
- **ML Phase 1**: triple-barrier baseline, `data/ml_research/phase1_results.json` — "no evidence of economic edge."
- **Promotion gate**: `strategy/promotion_gate.py::evaluate_promotion` — mechanical, reused for every verdict in this report too. No hypothesis, in 69 total, has ever cleared it.

This inventory was reconstructed, not re-run — none of the above was retested; only its existence and verdicts were confirmed against the actual source files this session.

---

## 3. Closed Research Families

Explicitly, standing-prohibited from further variants (per their own closure documents, unaffected by this mission):

- TrendMomentumBaseline v1.0 as a production hypothesis (H_BASELINE_001: "Do not optimize, tune, or redeploy").
- OHLCV mean reversion, Path 1 (H_MEANREV_014 / `CAPITAL_ALLOCATION_DECISION_FINAL.md`: "do not create H_MEANREV_015").
- Market/sector/VIX regime filters, Path 2 (H_CONTEXT_MARKET_007: "no third regime variable will be sought").
- Derivatives (futures basis/OI, options IV/skew): terminal, next step must be a different information source.

Not standing-prohibited, but exhaustively falsified this history: breakout/momentum-acceleration ("buying strength"), gap-fade, calendar effects, market breadth, global→India transmission, cross-sectional laggard-reversal execution (raw measurement not invalidated, only every attempted execution design).

---

## 4. New Families Tested This Mission

| Family | Status | Basis |
|---|---|---|
| **A — Corporate/event information** | Tested (2 hypotheses) | Real, free, historical yfinance dividend data confirmed available (§6) |
| **B — Market microstructure** | **Closed, no hypothesis written** | No historical bid/ask, quote-imbalance, order-flow, or order-book data exists anywhere in this repository or via any free source this project already trusts. Confirmed by direct source-code/data-directory inspection before any hypothesis was preregistered (`quant_research/derivatives_data.py`'s own terminal report already disclosed this absence for the derivatives program; re-confirmed independently this session — no local cache, no free NSE/Dhan endpoint provides it). Per this mission's own Section 10 stop condition ("required data does not exist" → close immediately) and Section 4 ("do NOT fabricate it, do NOT purchase it automatically"), this family is closed on a genuine data gap, not a research failure. |
| **C — Cross-sectional/relative information** | Tested (3 hypotheses) | Deliberately restricted to mechanisms materially different from the closed H_XSECT (laggard reversal) and F_CONTEXT (regime filters on the baseline) families — see each hypothesis's own `rationale` field in the registry for the specific distinction drawn. |

---

## 5. Preregistered Hypotheses (full text: `strategy/hypothesis_registry.py`, entries `H_EVENT_001`, `H_EVENT_002`, `H_XMOM_001`, `H_XVOL_001`, `H_XVOLATILITY_001`)

All five were preregistered — `description`/`rationale`/`expected_effect`/`dataset_restrictions`/`experiment_design`/`success_criteria`/`failure_criteria` written and committed to the registry with `status=OPEN` **before** any experiment was run or any result inspected. This report's own evidence text was added only after that commit, using the registry's own real-evidence discipline (no result was ever "un-run" or reworded after being seen).

| ID | One-line hypothesis |
|---|---|
| H_EVENT_001 | Post-ex-dividend-date short-horizon price drift beyond the mechanical price drop |
| H_EVENT_002 | Pre-ex-dividend-date anticipatory run-up (N=5 trading days before), under a disclosed, INFERRED SEBI LODR Reg. 42 advance-disclosure assumption |
| H_XMOM_001 | Cross-sectional momentum: top-quintile 60-day NIFTY-relative trailing return continues to outperform over 20 days |
| H_XVOL_001 | Abnormal volume relative to same-date universe peers predicts 1/3/5-day forward return |
| H_XVOLATILITY_001 | Abnormal realized volatility relative to same-date universe peers predicts 1/3/5-day forward return |

Total new hypotheses: **5** (within this mission's own cap of ≤3 families × ≤3 hypotheses = ≤9).

---

## 6. Data Sources

| Source | Used for | Status |
|---|---|---|
| `data/market/<SYMBOL>/1d.csv` (existing local cache) | OHLCV base for all 5 new hypotheses | Reused, zero new fetch cost |
| yfinance `Ticker.dividends` (full history, not the bounded `dividend_history_limit=3` live API) | H_EVENT_001/002 event timestamps | **Confirmed live** before coding: RELIANCE.NS alone returned 31 real dividend events spanning 1996–2026; universe-wide run found 1149 total events across 32 symbols, zero symbols with missing history. Free, already-trusted dependency, no scraping, no new credential. |
| yfinance `Ticker.earnings_dates` | Considered for a corporate-event earnings-drift hypothesis | **NOT used** — probed live and found to fail (`ImportError: lxml`), a missing optional dependency. Rather than add a new dependency for a data source of uncertain quality for NSE-listed tickers (Yahoo's Indian-market earnings-calendar coverage is known to be inconsistent), this branch was deliberately not pursued — an UNKNOWN, disclosed rather than silently worked around. |
| Bid/ask, order book, quote imbalance (any source) | Family B | **Confirmed absent** — no local cache, no free API this project already trusts. Closed without spending money to acquire it, per this mission's explicit rule. |
| `market_intelligence/nse_sector_map.py` | Considered for Family C sector-relative variants | Not used this round — already exhausted by the closed F_CONTEXT program; reusing it risked disguising a re-test of a closed family, so cross-sectional work this round used NIFTY-relative and pure universe cross-section instead, deliberately avoiding the sector map. |

---

## 7. Leakage Audits

Performed **before** any split was inspected, for every one of the 5 hypotheses:

- **H_EVENT_001**: information timestamp = the ex-dividend date itself, a real historical fact. Forward returns measured strictly AFTER that date (`trading_days_since_ex_div == 0` is the entry bar; `fwd_return_h` columns are the project's own pre-existing, already-audited forward-return labels). No OHLCV data on or after the event date is used to *define* the event. **Clean — no lookahead.**
- **H_EVENT_002**: the ex-date itself is a real historical fact, but the TRUE public-announcement timestamp (when the market first learned the record date) is not present in yfinance's data — only the ex-date is. This experiment relies on an **INFERRED**, not directly verified, external fact: SEBI LODR Regulation 42 requires listed companies to intimate exchanges of a record date/book closure a minimum number of working days in advance. N=5 trading days (pre-chosen, conservative, never tuned after seeing a result) is used as a safely-inside-the-minimum entry point. **This assumption was never independently verified against a real historical announcement-date dataset** — disclosed as a genuine, unresolved leakage risk in the registry entry itself. The result (§9) turned out to fail on its own stated statistical criteria regardless, making the leakage question moot for THIS decision, but the assumption remains unverified and any future reuse of this design would need to resolve it first.
- **H_XMOM_001 / H_XVOL_001 / H_XVOLATILITY_001**: all three score columns (`nifty_relative_return_60`, cross-sectional volume z-score, cross-sectional realized-volatility z-score) are constructed from strictly backward-looking rolling windows (`pct_change(60)`, `rolling(20).std()`) and same-date-only cross-sectional statistics (verified by construction in `quant_research/cross_sectional_relative.py::attach_cross_sectional_zscore_column` — a date is only scored using that SAME date's values across symbols, never a future date). `fwd_return_h` labels are the same pre-existing, already-audited columns. **Clean — no lookahead.**
- **Survivorship / point-in-time universe**: all 5 new hypotheses used `ORIGINAL_32_NSE_UNIVERSE` (today's current F&O-eligible constituents) applied uniformly across the full 10-year window — the SAME known, disclosed limitation (`MASTER_KNOWN_ISSUES.md` open item R1) as most of the pre-existing registry. Not survivorship-bias-corrected. Given all 5 results were clean rejections (not marginal passes), this limitation does not change any conclusion here, but is disclosed rather than omitted.
- **Universe choice**: `ORIGINAL_32_NSE_UNIVERSE` was chosen specifically because it is the SAME default universe most prior hypotheses used — not selected after seeing which universe would flatter a new-family result. No cherry-picking of symbols or dates occurred; full 10-year history, full universe, no exclusions beyond a symbol genuinely failing to build (0 of 32 failed).

---

## 8. Development Results / 9. Validation Results / 10. Out-of-Sample Results

(Combined here — each hypothesis's Stage-1 raw measurement was run across all three splits in the same pass, exactly as `quant_research.market_behavior.measure_condition` / `quant_research.cross_sectional.rank_cross_sectionally` already do for every existing hypothesis in this registry.)

### H_EVENT_001 — post-ex-dividend-date drift (NSE, 10y, 32 symbols, 1149 events)

| Split | h=1 | h=2 | h=3 | h=5 |
|---|---|---|---|---|
| Development (n=313) | mean +0.02%, CI [−0.19%,+0.23%] | mean −0.20%, CI [−0.50%,+0.11%] | mean −0.09%, CI [−0.44%,+0.26%] | mean +0.15%, CI [−0.30%,+0.60%] |
| Validation (n=101) | mean −0.23%, CI [−0.51%,+0.05%] | mean +0.04%, CI [−0.37%,+0.45%] | mean +0.22%, CI [−0.23%,+0.66%] | mean +0.09%, CI [−0.50%,+0.68%] |
| Out-of-sample (n=105–107) | mean −0.04%, CI [−0.28%,+0.20%] | mean +0.03%, CI [−0.33%,+0.38%] | mean +0.19%, CI [−0.24%,+0.63%] | mean +0.51%, CI [−0.07%,+1.08%] |

**Every cell straddles zero.** No split, no horizon, is CI-decisive. **Verdict: REJECTED (STATISTICALLY_MEANINGLESS throughout).**

### H_EVENT_002 — pre-ex-dividend-date run-up, N=5 trading days (n=279/101/107)

| Split | h=1 | h=3 | h=5 |
|---|---|---|---|
| Development | mean +0.09%, CI [−0.14%,+0.32%] | mean +0.07%, CI [−0.37%,+0.51%] | mean **−0.77%**, CI **[−1.37%,−0.17%]** (decisive negative) |
| Validation | mean **+0.47%**, CI **[+0.17%,+0.77%]** (decisive positive) | mean **+0.45%**, CI **[+0.01%,+0.88%]** (decisive positive) | mean −0.38%, CI [−0.98%,+0.21%] |
| Out-of-sample | mean −0.05%, CI [−0.35%,+0.25%] | mean −0.14%, CI [−0.73%,+0.44%] | mean **−1.07%**, CI **[−1.78%,−0.36%]** (decisive negative) |

**Sign flips across splits at h=5** (negative → not-decisive → negative, with validation showing a decisive POSITIVE at shorter horizons). Two splits (development h=5, out-of-sample h=5) are decisively NEGATIVE — the opposite of the stated expected effect. **Verdict: REJECTED** (promotion-gate rule: any split confidently NEGATIVE_PERFORMANCE disqualifies regardless of other splits).

### H_XMOM_001 — cross-sectional momentum, Q1(leaders)/Q5(laggards), h=20

| Split | Q1 (leaders) | Q5 (laggards) | Unconditioned |
|---|---|---|---|
| Development (n≈9961/8538/47456) | +1.53%, CI [1.36%,1.69%] | +1.65%, CI [1.45%,1.85%] | +1.42%, CI [1.34%,1.50%] |
| Validation (n≈3437/2946/15712) | +1.30%, CI [1.10%,1.51%] | **+2.38%**, CI [2.15%,2.61%] | +1.92%, CI [1.82%,2.02%] |
| Out-of-sample (n≈3359/2879/15352) | **−0.47%**, CI [−0.71%,−0.24%] | **+0.49%**, CI [0.26%,0.72%] | +0.001%, CI [−0.10%,+0.10%] |

Laggards (Q5) outperform leaders (Q1) in development and validation — **opposite of the momentum hypothesis**; out-of-sample Q1 flips to decisively negative while the unconditioned mean is ~0. **Verdict: REJECTED**, cleanly, in the direction opposite to what was hypothesized.

### H_XVOL_001 — cross-sectional relative volume, Q1(high)/Q5(low), h=1/3/5

| Split | h | Q1 (hi-vol) | Q5 (lo-vol) |
|---|---|---|---|
| Development | 5 | +0.40%, CI [0.31%,0.49%] | +0.34%, CI [0.26%,0.42%] |
| Validation | 5 | +0.36%, CI [0.24%,0.47%] | **+0.57%**, CI [0.46%,0.69%] |
| Out-of-sample | 5 | +0.0004%, CI [−0.11%,+0.11%] | +0.02%, CI [−0.09%,+0.13%] |

Spread direction reverses between development and validation; effect collapses to CI-meaningless out-of-sample at h≥3. **Verdict: REJECTED.**

### H_XVOLATILITY_001 — cross-sectional relative realized volatility, Q1(high)/Q5(low), h=1/3/5

| Split | h | Q1 (hi-vol) | Q5 (lo-vol) |
|---|---|---|---|
| Development | 5 | +0.36%, CI [0.26%,0.45%] | +0.41%, CI [0.33%,0.49%] |
| Validation | 5 | **+0.47%**, CI [0.34%,0.59%] | +0.32%, CI [0.22%,0.43%] |
| Out-of-sample | 5 | +0.14%, CI [0.02%,0.25%] | −0.02%, CI [−0.13%,+0.09%] |

Direction reverses between development (low-vol slightly ahead) and validation (high-vol ahead); out-of-sample only a marginal, low-magnitude effect survives. **Verdict: REJECTED.**

---

## 11. Costs / 12. Portfolio Realism

**Not applied to any of the 5 hypotheses.** Every hypothesis failed Stage 1 (raw, cost-free measurement) — no split-consistent, CI-decisive, correctly-signed effect survived even before transaction costs, slippage, or position sizing were considered. Per this mission's own stop-condition discipline (Section 10: "OOS fails → close... do NOT generate another variant to rescue a failed branch") and this project's own established two-stage convention (e.g. H_XSECT_001 → H_XSECT_002), building a costed, portfolio-realistic executable wrapper around a signal that already failed raw measurement would only ever make the result worse, never better — `backtesting/costs.py::CostModel.india_nse_intraday_2026()` (~0.21% realistic NSE round-trip cost) was reviewed and is available for reuse, but applying it here would have been performative, not informative.

---

## 13. Statistical Corrections

No hypothesis reached even an uncorrected pass, so a multiple-testing correction (Bonferroni-style, matching `strategy/multiple_testing.py`'s own established use of a wider z for `family_size` simultaneous tests) would only widen every confidence interval shown in §8–10 and could not turn any REJECTED result into a promotable one. Applying it was therefore not necessary to reach a conclusion, but is noted here for completeness: with `family_size=5` (this mission's own new hypothesis count), the Bonferroni-adjusted two-sided z would be ≈2.58 (95%→~99% per-test confidence) — every CI reported in §8–10 would only get WIDER under that correction, meaning any borderline "decisive" cell (e.g. validation h=1/h=3 in H_EVENT_002, already contradicted by other splits) would be even less likely to remain decisive, not more. This correction reinforces, and cannot reverse, the REJECTED verdicts above.

---

## 14. Adversarial Audits

Performed after all 5 new hypotheses (this mission's cap made a mid-point 3-hypothesis checkpoint and a final 5-hypothesis checkpoint substantively the same review; both questions are answered together here):

- **Did we accidentally test an old family?** No — verified against the full inventory (§2/§3) before writing each hypothesis's own `rationale` field, which explicitly names and distinguishes each new hypothesis from the closest prior entry (H_XMOM_001 vs. H_XSECT_001's opposite bucket/direction; H_XVOL_001/H_XVOLATILITY_001 vs. H_ENTRY_002's own-history-only volume filter and H_VOL_001's own-history-only volatility regime).
- **Did we introduce lookahead?** One disclosed, unresolved risk (H_EVENT_002's N=5 assumption, §7) — moot for this decision since the hypothesis failed regardless, but flagged, not hidden.
- **Did we optimize against validation?** No — every threshold (N=5 days, n_buckets=5, min_symbols_per_date=10, 60-day/20-day lookbacks) was fixed in the preregistered `experiment_design` before any split was inspected. No parameter was changed after seeing a result.
- **Did survivorship enter?** Yes, via the known, disclosed, unresolved R1 limitation (current-snapshot universe applied historically) — does not affect these particular verdicts since none were marginal passes.
- **Did multiple testing get understated?** Addressed in §13 — a correction was reasoned through, not skipped, and reinforces rather than reverses every verdict.
- **Are costs realistic?** N/A — no hypothesis reached the costing stage; costs were never needed to reach a REJECTED verdict, so no cost-realism question could distort this outcome.
- **Is the sample adequate?** Yes throughout — every split's sample size is one to three orders of magnitude above the 30-observation floor (smallest: n=101, largest: n≈47,456). The failure mode across all 5 hypotheses is sign-instability across splits, not underpowering.
- **Are we mistaking statistical significance for economic significance?** No case arose where this distinction mattered — no hypothesis reached statistical significance in the first place.
- **Are we continuing because evidence is promising, or because we don't want to stop?** Evidence is uniformly not promising. Per this mission's own Section 11 ("maximum 9... if all fail: DECLARE NO DEMONSTRATED EDGE... then STOP. Do not invent H60/H61/H62 merely to keep the project alive"), no H_EVENT_003, H_XMOM_002, or additional variant was created to rescue any of the 5 failed hypotheses.

**No contamination found. No result required invalidation or rerun.**

---

## 15. Failed Branches

All 5: H_EVENT_001 (statistically meaningless throughout), H_EVENT_002 (sign-unstable, two splits decisively negative), H_XMOM_001 (effect opposite of hypothesized direction, then sign-reverses out-of-sample), H_XVOL_001 (sign-unstable across splits), H_XVOLATILITY_001 (sign-unstable across splits). Family B closed on data absence before any hypothesis was written.

---

## 16. Candidate Edges

**None.** No hypothesis in this mission cleared even Stage 1 (raw, cost-free measurement). This report does not proceed to Section 12 of the mission's own live-validation gate (`docs/EDGE_DISCOVERY_FINAL_REPORT.md`'s own §18 below is the terminal recommendation, not a live-validation proposal) — there is no candidate to validate live.

---

## 17. Remaining Unknowns

- **Earnings-date-based event studies** (yfinance `earnings_dates`, blocked by a missing `lxml` dependency and uncertain NSE coverage quality) — genuinely untested. If pursued, the dependency question (install `lxml`, a free, standard PyPI package) is trivial, but the DATA-QUALITY question (does Yahoo's Indian-market earnings calendar have reliable historical dates, not just forward estimates) is UNKNOWN and would need to be verified before any hypothesis is preregistered on it.
- **H_EVENT_002's N=5 assumption** was never independently verified against a real historical corporate-announcement-timestamp dataset (§7) — remains genuinely UNKNOWN whether 5 trading days is inside or outside the true, symbol-by-symbol disclosure lead time. Moot for this report's conclusion (the hypothesis failed regardless) but would block any future reuse of this exact design.
- **Point-in-time universe correction (R1, `MASTER_KNOWN_ISSUES.md`)** remains unapplied to any hypothesis in this report — an existing, carried-over limitation, not newly introduced. Given all 5 results were clean rejections rather than marginal passes, it is very unlikely a point-in-time correction would flip any of them to PROMOTED (point-in-time correction has historically only ever made effects WEAKER — see H_MEANREV_014 — never stronger), but this is an INFERENCE from precedent, not directly tested here.
- **Market microstructure (Family B)** remains a genuine, unquantified UNKNOWN — not "tested and failed," but "untestable with any data this project can access for free." A paid Level-2/tick-level NSE data subscription could in principle answer the Family B question, but no cost estimate was sought (this mission's own rule: do not spend money to discover whether an offline hypothesis works) and no such spend is recommended by this report.

---

## 18. Recommendation

**Do not spend another rupee on live Dhan data to pursue this research line.** Across 69 total hypotheses tested in this project's full history (64 pre-existing + 5 new this mission), spanning technical/OHLCV signals, ML, mean reversion, breakout/momentum, market context/regime, calendar/gap/breadth effects, derivatives (futures basis/OI, options IV/skew), corporate-event timing, and cross-sectional momentum/relative-volume/relative-volatility, **zero have reached this project's own promotion gate.** The two strongest raw measurements in the entire history (H_XSECT_001 cross-sectional laggard reversal, H_MEANREV_014's point-in-time-corrected single-symbol result) both independently die at the portfolio/execution stage, not the signal-detection stage — a structural pattern (real short-horizon price patterns exist and can be measured, but do not survive becoming a tradable, cost-aware, portfolio-realistic retail strategy on this account size and this cost structure) that this mission's own 5 new tests did not overturn or even approach overturning.

Live-market execution paths remain structurally disabled and are not modified by this report. If this conclusion is ever revisited, it should be conditioned on one of: (a) a genuinely new, currently-inaccessible data source becoming available (paid microstructure data, a verified corporate-announcement-timestamp feed, verified NSE earnings-date history), (b) a materially different account size or cost structure that changes the economics of the two near-miss raw measurements already on file, or (c) point-in-time universe correction being wired into the shared backtest engine (R1) and re-applied — none of which this report recommends funding today.

---

*Compiled 2026-09-23. Registry entries: `strategy/hypothesis_registry.py` (H_EVENT_001, H_EVENT_002, H_XMOM_001, H_XVOL_001, H_XVOLATILITY_001). New reusable modules: `quant_research/event_study.py`, `quant_research/cross_sectional_relative.py`. Experiment driver was an uncommitted scratch script, consistent with this project's own established convention (see `quant_research/universe_expansion.py`'s own module docstring) of committing reusable library code and written-up evidence, not one-off runner scripts.*
