# Indian NSE Trading Decision & Prediction Engine — Report

Mission: "BUILD THE REAL INDIAN NSE TRADING DECISION AND PREDICTION
ENGINE" (2026-09-08). Goal: move the system materially closer to
answering, every day, for NSE — which stocks are worth attention, which
direction is more probable, how confident the system is, what evidence
supports and contradicts it, and whether past predictions were actually
correct. This report covers a full architecture audit, what was
genuinely missing versus already mature, what was built this segment,
and an honest current verdict.

## 1. What existed before this mission segment

A far more mature system than the mission's own text assumed — verified
by reading code, not taken on faith:

- **Scanner → decision → critic → risk → paper pipeline**:
  `market_intelligence.scanner.run_scan` (trend/momentum/breakout/
  relative-strength/sector-strength → `CandidateScore`) →
  `decision_engine.rules.classify` (BUY/WATCH/AVOID/EXIT/NO_ACTION,
  price-technical only) → `critic.engine.evaluate` (deterministic,
  APPROVE/DOWNGRADE/REJECT/INSUFFICIENT_EVIDENCE) → `risk.engine` →
  `paper.engine`. Fully real, fully tested, structurally paper-only.
- **A real prediction journal** (`predictions/` package, `Phase 23` of
  the original roadmap): `PredictionRecord`/`PredictionEvaluation`/
  `PredictionStore`, resolving BUY-shaped predictions against real
  subsequent bars into TARGET_HIT/STOP_HIT/EXPIRED/ACTIVE/
  INSUFFICIENT_DATA, with maximum-favorable/adverse-excursion tracking
  and a corporate-action anomaly guard.
- **A real learning/calibration layer** (`learning/` package, `Phase
  24/34/41`): `compute_real_confidence_calibration`,
  `compute_regime_performance`, `compute_signal_quality`,
  `compute_profitability_report` (Wilson-CI win rate, normal-approx
  return CI, an honest PROMOTED/NEGATIVE/INCONCLUSIVE/INSUFFICIENT_DATA
  verdict) — all wired into `main.py learn`/`evaluate`.
- **A real market-context engine** (`market_intelligence/regime.py`):
  breadth, NIFTY benchmark trend/volatility, generic GICS sector
  strength, 9 real official NIFTY sectoral indices, India VIX regime —
  all genuinely computed from live/cached Yahoo data, no fabrication.
- **A real research infrastructure**: hypothesis registry, promotion
  gate, dev/val/oos splitting, Bonferroni multiple-testing correction,
  a pure conditional-forward-return measurement engine
  (`quant_research/market_behavior.py`), 22 hypotheses already tested
  before this segment, zero promoted.
- **A live paper-trading scheduler**, running continuously through this
  entire mission segment, never restarted, never interfered with.

## 2. What was genuinely missing

Found by tracing the real pipeline, not assumed:

1. **No reproducible link from a Decision back to the market
   environment it was made in.** `market_intelligence.regime.
   MarketRegimeReport` already had everything the mission's
   "MarketSnapshot" concept wants, but was only ever computed by the
   standalone `regime` CLI command and printed — never saved.
2. **No UP/DOWN/NO_EDGE directional concept anywhere.**
   `decision_engine.rules.classify()` is structurally long-only
   (BUY/WATCH/AVOID/EXIT/NO_ACTION) — correctly so, since it drives
   real paper execution and this project must never grow a code path
   resembling short-selling. But that also means the system had no way
   to express or track a bearish forecast at all.
3. **No outcome tracking for anything except a BUY-shaped trade plan.**
   A DOWN or NO_EDGE call had nowhere to be recorded or later graded.
4. **No single "what should I look at today" report.** The pieces
   (scan, regime, decision) existed but were never combined into one
   ranked, evidence-labeled view.
5. **The live scheduler runs with zero holiday-calendar awareness**
   (no `--schedule-config` was ever passed to it) — a real, if
   low-frequency, correctness gap: `scheduler/runner.py`'s own
   `is_holiday` gate exists and works, it simply has nothing to check
   against for the currently-running process.
6. **A real Yahoo ticker format is silently unusable through the
   cache.** `INR=X` (USD/INR) is rejected by
   `backtesting.cache.CachedMarketDataProvider`'s own path-safety
   symbol validator (the `=` character isn't in its allowed set) — the
   guard is doing its job correctly, but it means this signal needs an
   uncached fetch, not the default path every other symbol uses.

## 3. What was built this segment

- `market_intelligence/regime_store.py::MarketRegimeStore` — persists
  `MarketRegimeReport`, keyed by the same `scan_id` `ScanHistoryStore`
  already uses.
- `Decision.scan_id` (new optional field) — every shadow-run decision
  now correlates back to the exact market snapshot it was made
  alongside. Verified end-to-end against real, live NSE data.
- `decision_engine/direction.py::classify_direction` — a UP/DOWN/
  NO_EDGE assessment, deliberately kept OUT of the live critic/risk/
  paper path, reusing `decision_engine.confidence.compute_confidence`'s
  existing score unchanged (no new threshold invented).
- `market_intelligence/nse_sector_map.py` — a conservative, disclosed
  NSE symbol → NIFTY-sector-index map, promoted from a research
  scratchpad into real, tested, reusable code.
- `main.py daily-report` — the mission's own literal "INDIAN MARKET
  DAILY DECISION REPORT," real and working against live data: per
  candidate, direction, confidence, market context, sector context,
  tradeability (reusing `classify()`'s real label), evidence, and a
  labeled research note citing specific hypotheses by ID, shown only
  for the exact condition each one actually tested.
- `predictions/direction_forecast.py` + `_store.py` + `main.py
  evaluate-forecasts` — outcome tracking for UP/DOWN/NO_EDGE forecasts,
  structurally separate from the BUY-shaped `PredictionRecord` (no
  trade-plan invariants — a forecast is not a trade). This is the first
  place the project can answer "when I said UP, how often was I right,"
  for both directions.
- Real 2026 NSE holiday dates, sourced and cross-checked against two
  independent sources (§13) — deliberately NOT written into
  `config/schedule.yaml` after discovering that path's mere existence
  silently changes the dashboard's own default holiday-awareness
  behavior (a real regression this segment caused and reverted, §13) —
  handed to the user in this report instead, so enabling it is their
  decision, not a silent side effect of this session.
- One further research hypothesis, `H_TRANSMISSION_002` (USD/INR →
  NSE IT+Pharma), REJECTED with a genuine, self-critical finding (§9).

Everything above: real end-to-end smoke-tested against live NSE data
(not only fakes), unit-tested, full-regression-tested (1817 tests
passing at the time of writing, up from 1758 at this segment's start),
committed in 5 reviewed, ff-only-merged commits.

## 4. Prediction architecture

Two, deliberately separate, tracks:

- **BUY-shaped trade predictions** (`predictions/`): a real entry/stop/
  target price plan, created only from an actual BUY decision, resolved
  against real subsequent bars into TARGET_HIT/STOP_HIT/EXPIRED. This
  is what could, in principle, become a real trade (paper-only).
- **Directional forecasts** (`predictions/direction_forecast.py`, new
  this segment): a bare UP/DOWN/NO_EDGE call with no price plan at all,
  resolved against a plain N-bar-forward return. This can never become
  a trade — it exists purely to measure "was the call right," including
  for DOWN and NO_EDGE, which the trade-prediction track structurally
  cannot represent.

## 5. Feature architecture

Reused, not rebuilt: `market_intelligence.scanner`'s five factors
(trend/momentum/breakout/relative-strength/sector-strength) are the
system's only decision-relevant stock-level features, each with a
plain-language explanation string already generated at scan time.
`decision_engine.direction.classify_direction` turns those same five
factors into bullish/bearish/contradicting evidence bullets via
`decision_engine.confidence.compute_confidence`, unchanged.

## 6. Market snapshot architecture

`market_intelligence.regime.MarketRegimeReport` (breadth, NIFTY
benchmark trend/volatility, generic sector strength, the 9 real NIFTY
sectoral indices, India VIX) is now the canonical "what did the market
look like" snapshot, persisted per shadow-run/daily-report by
`MarketRegimeStore` and referenced by every `Decision.scan_id`. Global
macro (USD/INR, crude, gold, DXY) remains confirmed-available but not
yet folded into this snapshot object itself — used directly by research
scripts instead (§9).

## 7. Outcome tracking

Both prediction tracks (§4) have real, working, tested evaluation
loops (`predictions.tracker.evaluate_prediction` /
`predictions.direction_forecast.evaluate_forecast`), both guarded
against corporate-action data anomalies, both exposed via CLI
(`evaluate` / `evaluate-forecasts`) with honest ACTIVE/PENDING states
when there isn't enough data yet — never a fabricated resolution.

## 8. Confidence calibration

The machinery (`learning.analysis.compute_real_confidence_calibration`)
already existed and was run against the REAL production database this
segment, not simulated. Result: **10 real predictions total, all still
ACTIVE, zero resolved** — confidence calibration is honestly
INSUFFICIENT_DATA right now. This is not a bug; the live scheduler has
only been accumulating history for a limited window. All 10 existing
predictions happen to fall in the MEDIUM (50–80%) confidence band, with
none LOW or HIGH — worth re-checking once real resolutions exist.

## 9. Research findings (this segment)

`H_TRANSMISSION_002`: does USD/INR's prior-day return predict NSE
IT+Pharma exporter stocks' forward returns? **REJECTED** — neither
direction (INR depreciation/appreciation) showed a stable, non-reversing
effect across development/validation/out-of-sample. The valuable part
of this result is a self-critical finding, not the headline verdict: a
per-symbol concentration check revealed all 5 IT stocks and all 4
Pharma stocks moved in OPPOSITE directions under the identical
condition — the pooled "exporter" bucket was never a valid single
group, and a real follow-up would test IT and Pharma completely
separately rather than pooled. (This segment's earlier Family A/B/C/D
context-conditioning research — market/sector divergence beating
agreement — was completed in this same session before this report's
own mission began; see `docs/INDIAN_TRADING_DECISION_BRAIN_REPORT.md`
for that full writeup, still current and unrepeated here.)

## 10. Rejected findings

`H_TRANSMISSION_002` (§9). Combined with the pre-existing registry
(`strategy/hypothesis_registry.py`), the project now holds **23
hypotheses, 0 promoted** — consistently, honestly reported across every
mission segment this project has run.

## 11. Data integrity findings

No new corruption found this segment (the 32-symbol NSE universe and
all India-context tickers were already repaired to genuine 5-year depth
in the immediately preceding mission segment). Two new, smaller
infrastructure findings, both disclosed rather than silently worked
around: `CachedMarketDataProvider`'s path-safety validator correctly
rejects `INR=X`-style tickers containing `=` (a real, working guard,
not a bug — worked around per-symbol with an uncached fetch, not
loosened); the live scheduler process has zero holiday-calendar
configuration (§2), remediable via `config/schedule.yaml` (real,
sourced 2026 dates below, §13) without any code change — left for the
operator to apply, not applied automatically (§13).

## 12. Live paper observations

The live `schedule loop --paper-execute --live-source dhan` process
ran continuously through this entire mission segment, checked
periodically, never restarted or interfered with. Market closed at
15:30 IST partway through this segment; the scheduler correctly ran its
`post_market` slot (evaluate + learn) and has been idling with
`[SKIPPED] No configured slot is due at this time.` ever since — exactly
the expected, healthy behavior. Real trade/prediction volume remains
small (10 predictions, all ACTIVE) — genuinely not yet enough live
history to draw a paper-trading-validation conclusion, honestly stated
rather than stretched.

## 13. Known limitations

- **Real 2026 NSE holiday dates, for the user to apply if desired**
  (sourced 2026-09-08 via live web search, cross-checked against two
  independent sources — groww.in and kotakneo.com, both agreeing on all
  16 dates — NOT the NSE's own official circular directly; verify
  against `https://www.nseindia.com/resources/exchange-communication-
  holidays` before relying on this for anything beyond an operator's own
  convenience): 2026-01-15 (Maharashtra municipal election), 01-26
  (Republic Day), 03-03 (Holi), 03-26 (Ram Navami), 03-31 (Mahavir
  Jayanti), 04-03 (Good Friday), 04-14 (Ambedkar Jayanti), 05-01
  (Maharashtra Day), 05-28 (Bakri Id), 06-26 (Muharram), 09-14 (Ganesh
  Chaturthi), 10-02 (Gandhi Jayanti), 10-20 (Dussehra), 11-10
  (Diwali-Balipratipada), 11-24 (Guru Nanak Jayanti), 12-25 (Christmas).
  **Deliberately not written into `config/schedule.yaml` by this
  session** — see the next bullet for why — copy this list into that
  file yourself (per `config/schedule.yaml.example`'s own format) to
  enable it for the live scheduler (on its next restart) and the
  dashboard.
- **A real regression this segment caused and reverted**: an earlier
  draft of this session DID write `config/schedule.yaml` with the list
  above, reasoning it was safe because the path is gitignored (matching
  this project's own established convention). It was not fully safe:
  `dashboard/app.py::_load_holidays` treats that path's mere
  *existence* on disk as a live signal (its own default-path
  fallback), so creating the file silently changed the dashboard's
  holiday-awareness behavior for anyone running it in this environment
  and broke `tests/test_dashboard_intelligence.py::
  test_intelligence_page_market_status_discloses_no_holiday_awareness`
  (caught by this session's own full-regression discipline before
  anything was committed). Reverted (file deleted) rather than patched
  around, since the dashboard's own behavior is correct and intentional
  — the fix was to stop silently creating operator-facing config,
  not to change how the dashboard reads it. Worth remembering: a
  gitignored file is safe from source control, not automatically safe
  from ambient-path-convention side effects elsewhere in the codebase.
- Confidence calibration (§8) cannot yet be evaluated — insufficient
  resolved history. This is the single most important thing that needs
  to simply accumulate over time, not be engineered around.
- `decision_engine.direction.classify_direction`'s label is a pure
  sign-of-composite-score readout, deliberately without a fabricated
  confidence-threshold cutoff for NO_EDGE (per the mission's own rule
  against unearned weights) — meaning NO_EDGE only ever means "composite
  score is exactly zero," a narrower case than a human might expect from
  the name. This is a disclosed design choice, not an oversight.
  Revisiting it would require the same evidence-first discipline as any
  other decision-quality change, not another arbitrary number.
- The NSE sector map (`market_intelligence/nse_sector_map.py`) covers
  only 20 of the 32-symbol universe and is hand-built, not sourced from
  an official index-constituent file — documented in its own module
  docstring.
- NSE price circuit limits (2%/5%/10%/20% daily bands) are not modeled
  anywhere in this codebase. Investigated this segment and deliberately
  NOT built: the research/paper universe is exclusively large/mega-cap
  NIFTY constituents, where circuit-limit hits are rare, and circuit-
  band data is not available through this project's existing free
  (Yahoo-backed) data path — building speculative infrastructure for an
  unavailable data source and a low-probability event on this universe
  would have been exactly the "unnecessary complexity" the mission
  explicitly warns against. Disclosed here rather than silently ignored.
- No real stock-split/dividend adjustment source is integrated anywhere
  in this project (both prediction-tracking modules share the same
  disclosed corporate-action anomaly guard, which detects and refuses
  to score an affected bar rather than adjusting for it) — a
  pre-existing, still-open limitation, not introduced this segment.
- `market_intelligence.regime.BenchmarkContext.trend_regime` and
  `backtesting.regime.TrendRegime` are two DIFFERENT enums with
  different string values (UPTREND/DOWNTREND vs. TRENDING_UP/
  TRENDING_DOWN) used in different parts of this codebase — a real
  source of confusion this segment's own first draft fell into (caught
  by live smoke-testing, then fixed). Worth remembering for any future
  code that branches on a `trend_regime` string.

## 14. Exact current verdict

The system is now materially closer to answering the mission's own
central question — a real, working `daily-report` command produces
exactly the ranked, evidence-labeled, ATTENTION/DIRECTION/CONFIDENCE/
CONTEXT/TRADEABILITY output the mission's success criteria describe,
against live NSE data, today. What it is NOT yet able to say is whether
that output is actually GOOD: confidence calibration is honestly
INSUFFICIENT_DATA (10 predictions, 0 resolved), and no context-research
finding from this or the prior segment has reached PROMOTED. The
correct, honest summary is: **the decision-and-prediction ARCHITECTURE
is now real and complete enough to be evaluated; the EVIDENCE that its
outputs are trustworthy does not yet exist in sufficient quantity, and
that evidence gap — not a missing capability — is the actual current
bottleneck.** The right next step is not more architecture; it is time
and continued, undisturbed live paper observation, run through
`evaluate`/`evaluate-forecasts`/`learn` as real predictions accumulate
and resolve.
