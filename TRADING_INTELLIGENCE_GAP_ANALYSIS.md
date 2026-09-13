# Trading Intelligence Gap Analysis — Phase 0.5

Analysis only. No code, libraries, databases, or thresholds were changed to produce this document. All file:line citations were independently verified by direct code reads (five parallel read-only research passes plus manual spot-checks) against the `TradingAgents` repository at commit `982b7d4549e9a7fb1e558fe17435c1292eeeb6a9`. Where a claim could not be verified with code-level evidence, it is marked **[UNVERIFIED]** rather than assumed.

---

# Executive Summary

The forensic audit (Phase 0) established that this repository is real, working infrastructure, not a roadmap fiction. This phase answers a narrower, harder question: **does that infrastructure currently produce anything resembling a statistically validated trading edge, and if not, what specifically is missing?**

The answer, traced to the exact numeric values flowing through `decision_engine.engine.make_decision`:

1. **The live decision is driven by five hand-weighted technical sub-scores summed with equal, untuned weights**, corroborated by a hard sign-agreement check on two of them. No indicator, research fact, or market-context field beyond those five sub-scores and one boolean (`has_open_position`) ever reaches the label decision — confirmed by direct reading of `decision_engine/rules.py::classify()`.
2. **"Prediction" in this codebase means a recorded price plan (entry/stop/target) or a sign label (UP/DOWN/NO_EDGE), later resolved into a deterministic outcome by comparing subsequent bars against fixed thresholds.** No probability, expected value, or confidence interval is ever attached to an individual forecast *before* it resolves. The one score that looks like a probability (`confidence`, 0.0–1.0) is explicitly documented in its own source as an **uncalibrated fraction of agreeing factors**, not a probability.
3. **The only genuine inferential statistics in the entire repository — Wilson score intervals and normal-approximation confidence intervals on mean return** (`learning/profitability.py`) — are real, correctly implemented, and are applied exclusively **after the fact**, to already-resolved historical hypothesis results, never to a live, still-open prediction.
4. **No machine-learning library, fitted classifier, or regression model exists anywhere in the live pipeline.** The only two model-fitting operations found in the entire codebase are a hand-rolled OLS slope (`np.polyfit`, `market/indicators.py`, used only to classify volume trend as increasing/decreasing/neutral) and a rolling z-score (`quant_research/alpha_features.py`), the latter fully quarantined to an offline research package that never reaches production.
5. **The backtesting engine is realistic about slippage and flat/percentage costs, but silent about spread, price impact, partial fills, and gap-through-stop risk**, and its India cost preset explicitly omits GST/stamp duty/SEBI charges by disclosed design.
6. **The statistical research machinery (promotion gate, Bonferroni correction, hypothesis registry) is genuinely rigorous and already battle-tested across 55 hypotheses** — the gap is not method, it is that the *features* the mission wants to test (VWAP distance, time-of-day, global-market context, sector breadth) mostly do not exist yet.
7. **No workflow in this project has ever actually run on an intraday interval** — confirmed by the codebase's own comment (`main.py:1882`, "No real workflow in this project uses an intraday `--interval` today"). Before any intraday label horizon is chosen, the intraday data path itself needs to be exercised and verified, not assumed.

**Bottom line**: this system has excellent research and audit infrastructure and a completely honest, deterministic decision engine — but it does not yet have anything that could be called a quantitative prediction model. The path from here is well-defined and narrow: build a feature engine, a triple-barrier label generator, and one simple baseline classifier, then let the *existing* promotion-gate machinery honestly answer whether it beats the current deterministic rule. Nothing about this requires an LLM, a new database, or a new architecture.

---

# Current Decision Pipeline

```text
ScanHistoryStore.latest_report()  ──► CandidateScore (scanner.py)
                                            │
ResearchStore.latest_report_for_symbol() ──┤ (stored on Decision, NOT read by classify())
                                            │
market.context.get_market_context() ───────┤ (stored on Decision, NOT read by classify())
                                            │
PaperStore.get_account()/get_open_position()──► RiskContext.has_open_position (the ONLY field read)
                                            │
                                            ▼
                        decision_engine.rules.classify(candidate, risk_context, config)
                                            │
                                            ▼
                              DecisionLabel: BUY / WATCH / AVOID / EXIT / NO_ACTION
                                            │
                        decision_engine.confidence.compute_confidence(candidate)  (independent, post-hoc)
                                            │
                        (optional) decision_engine.engine.narrate_decision(decision)  ──► LLM narrative string only
                                            │
                                            ▼
                                     Decision (persisted)
```

**Exact rule** (`decision_engine/rules.py:22-66`), quoted in full because this is the single most load-bearing piece of logic in the whole platform:

```python
if risk_context.has_open_position:
    if candidate is None:
        return NO_ACTION
    return EXIT if candidate.composite_score <= 0 else WATCH

if candidate is None:
    return NO_ACTION

if config.require_corroboration_for_buy:        # default True
    factors_agree = (
        candidate.composite_score > 0
        and candidate.trend_score > 0
        and candidate.momentum_score > 0
    )
    if factors_agree:
        return BUY
    elif candidate.composite_score > 0:
        return WATCH
    else:
        return AVOID
else:
    return BUY if candidate.composite_score > 0 else AVOID
```

`Decision.market_context`, `Decision.research_evidence`, `Decision.risk_context.consecutive_losses`, and `Decision.risk_context.note` are all persisted for audit purposes but **never read by this function** — confirmed: `classify()`'s signature (`rules.py:22-23`) does not accept `research` or `market_context` at all, and only `has_open_position` is ever accessed on `risk_context`. This is a known, disclosed Phase 21 limitation (`decision_engine/engine.py:12-15`), not a bug — the module was deliberately built to keep the label auditable and simple, at the cost of ignoring most of the evidence the system otherwise collects.

---

# Current Feature Vector

| Feature | Exists | Used by decision (`classify()`) | Source | Timeframe | Numeric | Tested | Stored |
|---|---|---|---|---|---|---|---|
| `has_open_position` | Yes | **Yes** | `paper.store.PaperStore` account state | current | bool | Yes | `decisions.db` |
| `composite_score` | Yes | **Yes** (primary gate, every branch) | `market_intelligence/scanner.py:274-280`, equal-weighted (1.0 each) sum of the 5 rows below | per-scan | float | Yes | `scanner.db`, `decisions.db` |
| `trend_score` | Yes | **Yes** (corroboration check) | `scanner.py:201-208`: SMA20 vs SMA50 vs close → {-1, 0, +1} | 20/50-bar SMA | float (ternary) | Yes | `scanner.db`, `decisions.db` |
| `momentum_score` | Yes | **Yes** (corroboration check) | `scanner.py:210-211`: `(RSI14 - 50) / 50` | 14-bar RSI | float, ≈[-1,+1] | Yes | `scanner.db`, `decisions.db` |
| `require_corroboration_for_buy` | Yes | **Yes** (rule selector) | `decision_engine/config.py:22-30`, config, default `True` | static | bool | Yes | `DecisionConfig.version_id()` |
| `breakout_score` | Yes | No (feeds `composite_score` only) | `scanner.py:213-216`: `(last_close - 20-bar prior high) / prior high` | 20-bar lookback | float | Yes | `scanner.db` |
| `relative_strength_score` | Yes | No (feeds `composite_score` only) | `scanner.py:218-229`: 20-bar trailing return minus benchmark (`^NSEI`) trailing return | 20-bar | float\|None | Yes | `scanner.db` |
| `sector_strength_score` | Yes | No (feeds `composite_score` only) | `scanner.py:239-270`: sector-average trailing return minus universe-average, computed internally over the scanned universe (not an external sector index) | 20-bar | float\|None | Yes | `scanner.db` |
| `volume_ratio` | Yes | No (screening gate + display only) | `market/indicators.py`: current volume / 20-bar SMA volume | 20-bar | float | Yes | `market_intelligence` cache |
| `volume_trend` | Yes | No | `market/indicators.py:206-267`: OLS slope (`np.polyfit`) of last 5 bars' volume, normalized, classified increasing/decreasing/neutral at ±5% | 5-bar | categorical (from a real regression) | Yes | Not persisted per-decision |
| `sma_20` / `sma_50` | Yes | No (only indirectly, via `trend_score`) | `market/indicators.py:54-55` | 20/50-bar | float | Yes | Not persisted per-decision |
| `rsi_14` | Yes | No (only indirectly, via `momentum_score`) | `market/indicators.py:58-72`, Wilder-style EWM | 14-bar | float | Yes | Not persisted per-decision |
| `macd` / `macd_signal` / `macd_histogram` | Yes | **No** — computed, never referenced by `scanner.py` or `classify()` at all | `market/indicators.py:75-94` | 12/26/9-bar EMA | float | Yes | `MarketContext` only |
| `atr_14` | Yes | No (used for stop/target sizing in `strategy/baseline.py`, not by `classify()`) | `market/indicators.py:97-112` | 14-bar | float | Yes | `MarketContext` only |
| `data_source` / `data_status` / `data_freshness_seconds` | Yes | No | `market/context.py:44-60` (Phase 31 live-overlay provenance) | current | categorical/float | Yes | `MarketContext` only |
| `ai_summary.confidence` | Yes | **No** — the one numeric field in the whole research pipeline, never read by `classify()` or `narrate_decision()` | `research/models.py:44-53`, LLM self-reported | per-report | float [0,1] | Yes | `research.db` |
| `confidence` (decision-level) | Yes | **No** (computed independently, after the label) | `decision_engine/confidence.py:52-88`: fraction of the 5 `CandidateScore` sub-scores agreeing in sign with `composite_score` | per-scan | float [0,1], **not calibrated** | Yes | `decisions.db` |
| VWAP (numeric) | **No** | No | Referenced only as a free-text LLM prompt field (`schemas/technical.py::TechnicalAnalysis.vwap: str`), never computed as a number anywhere in `market/indicators.py` | — | — | — | — |
| Market regime (UPTREND/DOWNTREND/UNKNOWN) | Yes | **No** — not a field on `MarketContext` at all; lives only in `market_intelligence/regime.py`/`regime_store.py`, correlated to a `Decision` only loosely via a shared `scan_id` string | `learning/regime.py:25-63`: last close vs trailing SMA | window-dependent | categorical | Yes | `market_regime.db` |
| Liquidity | Partial | No | `market_intelligence/config.py::ScannerConfig.min_avg_daily_value` — a screening gate that **defaults to `0.0` (no-op)** | 20-bar avg(close×volume) | float | Yes (as a gate) | `scanner.db` |
| Research news / sector text | Yes | No (narrative only) | `research/models.py`: `NewsItem`, `SectorInfo` | current | text | Yes | `research.db` |

**The single most important finding of this section**: only 4 numeric fields and 1 boolean drive the label. Every other row in this table — including three of the five scanner sub-scores, every raw indicator except SMA/RSI (indirectly), MACD (never used at all), ATR, market regime, liquidity, and all research/news evidence — is computed, persisted, and displayed, but has zero causal effect on `BUY`/`WATCH`/`AVOID`/`EXIT`/`NO_ACTION`.

---

# Current Prediction System

## Signal maturity classification

Using the mission's own A–H taxonomy, applied to every stage of the pipeline:

| Signal | Classification | Evidence |
|---|---|---|
| OHLCV bar (open/high/low/close/volume) | **A. Raw market observation** | `market/data_provider.py:158` |
| `sma_20`, `sma_50`, `rsi_14`, `macd`/`macd_signal`/`macd_histogram`, `atr_14`, `volume_ratio` | **B. Derived indicator** | `market/indicators.py` |
| `volume_trend` (increasing/decreasing/neutral) | **B→C hybrid**: a real OLS regression (`np.polyfit`) collapsed into a fixed-threshold categorical rule (±5%) | `market/indicators.py:206-267` |
| `trend_score` (SMA20 vs SMA50 vs close → {-1,0,+1}) | **C. Deterministic trading rule** (a rule applied to a derived indicator) | `scanner.py:201-208` |
| `momentum_score`, `breakout_score`, `relative_strength_score`, `sector_strength_score` | **B. Derived indicator** (continuous transforms, no threshold applied yet) | `scanner.py:210-270` |
| `composite_score` (equal-weighted sum) | **C. Deterministic trading rule** — weights are hand-set to 1.0, never fit to data | `scanner.py:274-280` |
| `classify()` → BUY/WATCH/AVOID/EXIT/NO_ACTION | **C. Deterministic trading rule** | `decision_engine/rules.py:22-66` |
| `direction` (UP/DOWN/NO_EDGE) | **C. Deterministic trading rule** — a hard sign test on `composite_score`, despite living in a module named "forecast" | `decision_engine/direction.py:93-124`, `predictions/direction_forecast.py` |
| `confidence` score | **Mislabeled B presented as F.** It is a derived heuristic (fraction of agreeing factors) with the *shape* of a probability (0.0–1.0) but none of the substance — not fit to historical outcomes, not calibrated at construction time. The codebase's own docstring says so explicitly (`decision_engine/confidence.py:1-16`). This is the single riskiest naming choice in the codebase for a future reader or operator. | `decision_engine/confidence.py:52-88` |
| `ai_summary.confidence` (research) | Same category as above — an LLM's **self-reported** confidence about evidence substantiveness, not a statistical estimate of anything | `research/models.py:44-53` |
| Win rate / mean-return 95% CI (Wilson / normal approximation) | **D. Statistical signal** — genuine, correctly implemented inferential statistics | `learning/profitability.py:139-165` — **but applied only retrospectively, to already-resolved trade batches, never prospectively to a single new prediction** |
| `zscore_close_20` (mean-reversion research) | **D. Statistical signal** in principle (a real rolling z-score), but used only as a fixed-threshold rule (**C**) and fully quarantined to `quant_research/`, never reaching production | `quant_research/alpha_features.py:63-65` |
| Any ML/regression prediction | **E/F. Does not exist.** No `sklearn`/`torch`/`tensorflow`, no `.fit()`/`.predict()` model-style call anywhere in production code. | Repo-wide grep, zero hits |
| LLM narratives (`DecisionNarrative`, `SignalExplanation`, `DecisionReview`, `ResearchSummary`) | **G. LLM interpretation** — narration only, structurally incapable of altering a label (see Executive Summary point 1 and `decision_engine/engine.py:32-65`) | Multiple, see `AUDIT_BASELINE.json.agents` |
| `RiskEngine.evaluate()` veto rules, position sizing | **H. Risk constraint** | `risk/engine.py:44-127` |

## What "prediction" actually means today

```text
CURRENT PREDICTION:
Two distinct mechanisms, both deterministic:
(1) A recorded trade plan (entry_price, stop_price, target_price, horizon_bars)
    later resolved to TARGET_HIT / STOP_HIT / EXPIRED / ACTIVE / INSUFFICIENT_DATA
    by comparing subsequent OHLC bars against those fixed price levels.
(2) A UP / DOWN / NO_EDGE label from a hard sign test on composite_score,
    later resolved to correct/incorrect by comparing the sign of the actual
    N-bar-forward return.

ACTUAL MATHEMATICAL MODEL:
None. (1) reuses backtesting.execution.check_exit verbatim -- the identical
"if high >= target: TARGET_HIT elif low <= stop: STOP_HIT" rule the
backtester uses on historical data, just run against live-forward bars.
(2) is `1 if composite_score > 0 else (-1 if composite_score < 0 else 0)`.

INPUTS:
(1) entry_price / stop_price / target_price (from strategy/risk sizing,
    themselves ATR-based, not model-fit) + horizon_bars.
(2) composite_score's sign only.

OUTPUT:
A categorical outcome label plus, once resolved, a realized return
(actual_return = exit_price/entry_price - 1). Never a probability,
expected value, or interval attached BEFORE resolution.

TRAINING:
None. Every threshold in the pipeline (SMA windows 20/50, RSI midpoint 50,
composite weights all 1.0, breakout/relative-strength/volume-trend lookback
windows all 20, volume-trend classification cutoff ±5%, ANOMALOUS_BAR_GAP_
THRESHOLD 50%) is a hand-chosen constant. Nothing anywhere in the live
pipeline is fit to historical data.

CALIBRATION:
Checked only as a retrospective diagnostic: `learning/analysis.py::
compute_real_confidence_calibration` buckets past decisions' `confidence`
scores into fixed LOW(<0.5)/MEDIUM(0.5-0.8)/HIGH(>=0.8) bands and reports
the REALIZED win rate per band -- a report, never a feedback loop. The
confidence score itself is never adjusted based on this check anywhere in
the codebase.

OUT-OF-SAMPLE VALIDATION:
Exists, but only at the offline HYPOTHESIS/backtest level -- promotion_
gate.py's development/validation/out-of-sample split with Wilson/normal-
approximation 95% CIs, Bonferroni-corrected across a stated hypothesis
family (strategy/multiple_testing.py). This machinery has NEVER been
applied to the live decision/prediction pipeline's own real-time output --
predictions/direction_forecast.py's own evaluation produces only a raw
accuracy percentage (correct/(correct+incorrect)), with no CI, no
significance test, no promotion-gate-style verdict.

LIMITATIONS:
No genuine probabilistic model exists anywhere in the live pipeline. The
"confidence" score's 0.0-1.0 shape strongly invites misreading as a
probability of a good outcome, when it measures only sign-agreement among
five hand-weighted, untuned technical factors. Every "prediction" in this
system is operationally identical to a backtest rule running on live data
one bar at a time -- which is a legitimate, honest design (see README's
own evidence-classification discipline), but it means the mission's
premise -- "statistically validated intraday trading intelligence" -- is
not yet met by anything currently running live.
```

---

# Quantitative Capability Assessment

| Capability the mission asks about | Present today? | Evidence |
|---|---|---|
| P(return > 0 \| features) classification | **Missing** | No fitted classifier anywhere |
| P(return > threshold) directional classification | **Missing** | `direction.py`'s UP/DOWN/NO_EDGE is a sign test, not a probability |
| E[R \| features] regression | **Missing** | No regression model |
| Expected volatility forecast | **Missing** | `atr_14` is a trailing realized-range measure, not a forward forecast |
| Triple-barrier labeling | **Partially present as infrastructure, not as an ML target** | `predictions/tracker.py::evaluate_prediction` already implements the exact target/stop/timeout mechanics — it just assigns a deterministic label instead of feeding a model |
| Cross-sectional ranking by expected risk-adjusted return | **Missing** | No rank field exists on `CandidateScore`; symbols are gated/scored independently, never ranked against each other in a stored field |

**Recommended initial target: Triple-barrier classification, `P(target hit first | features)`.**

Rationale: (1) the entry/stop/target/horizon-bar structure is *already* the load-bearing data model across `paper/`, `predictions/`, and `strategy/baseline.py` — no new trade-plan concept needs inventing; (2) `predictions/tracker.py::evaluate_prediction` already implements the exact barrier-resolution mechanics needed to produce the label, by reusing `backtesting/execution.py::check_exit` — the labeling function is a light adaptation of code that already exists and is already tested; (3) triple-barrier naturally respects the ATR-based, risk/reward-asymmetric stop/target convention this project has used since `strategy/baseline.py`'s original frozen constants, unlike a raw fixed-horizon return regression which would ignore that asymmetry entirely; (4) a 3-class (or, initially, simplified 2-class: target-first vs. not-target-first, folding stop+timeout together) classification output plugs directly into an expected-value calculation (`P(target) * reward − P(stop) * risk`) that the existing `risk/engine.py` sizing formula can consume without modification.

---

# Missing Features

Full inventory (existing + proposed) is in `TRADING_FEATURE_CATALOG.json`. Summary by category:

## Market
| Feature | Status |
|---|---|
| NIFTY return | **EXISTING** — `^NSEI`, used as the default benchmark everywhere |
| BANK NIFTY return | **EXISTING, opt-in** — `^NSEBANK`, only under `--with-nifty-sectors` |
| Market breadth | **EXISTING** — `market_intelligence/regime.py` |
| India VIX | **EXISTING, opt-in** — `^INDIAVIX`, only under `--with-india-vix` |
| Index momentum (a named, stored feature) | **MISSING** — the `trend_score`-style logic is never applied to the index itself as a stored field |

## Sector
| Feature | Status |
|---|---|
| Sector relative strength | **EXISTING** — `sector_strength_score`, but computed **internally** (sector-average vs universe-average trailing return), not from an external sector index |
| Sector return (external index) | **PARTIAL, opt-in, disconnected** — `market_intelligence/regime.py`'s 8 NIFTY sector indices exist but are a **separate module never unified with `sector_strength_score`** — a real internal inconsistency worth resolving before adding more sector features |
| Sector breadth | **MISSING** |
| Sector momentum (of an external sector index, not the internal proxy) | **MISSING** |

## Stock
| Feature | Status |
|---|---|
| Returns, momentum, volatility (ATR), volume ratio/trend | **EXISTING** |
| VWAP distance | **MISSING** — referenced only as an LLM prompt text field, never computed numerically anywhere |
| Gap (overnight/opening) | **MISSING** — the only "gap" concept in the codebase is a *data-quality guard* (`ANOMALOUS_BAR_GAP_THRESHOLD`), not a feature |
| Intraday range (normalized) | **PARTIAL** — raw high/low exist, no normalized-range feature is computed |

## Cross-sectional
| Feature | Status |
|---|---|
| Relative strength | **EXISTING** (`relative_strength_score`) |
| Stock rank / sector rank / volume rank / momentum percentile | **MISSING** — no rank or percentile field exists anywhere; every score is computed independently per symbol, never ranked against the scanned universe |

## Market microstructure
| Feature | Status |
|---|---|
| 5-level bid/ask depth | **UNRELIABLE / not reaching production** — `live/dhan/wire.py` genuinely parses 5-level depth from `FULL` packets, but `live/dhan/market_data_source.py::_send_subscribe` only ever sends `SUBSCRIBE_TICKER` — depth data never reaches any consumer today |
| 20-level market depth | **MISSING** — `SUBSCRIBE_DEPTH` request code exists but has **no corresponding response parser implemented anywhere** |
| Order imbalance, trade intensity | **MISSING** |

## Derivatives
| Feature | Status |
|---|---|
| Open interest | **UNRELIABLE / not reaching production** — `wire.py` parses OI fields from `OI`/`FULL` packets, but the live pipeline only subscribes in Ticker mode, so OI never reaches a consumer; also absent entirely from the static instrument master (OI is streaming-only) |
| Futures basis, OI change, implied volatility, PCR, options volume | **MISSING** — zero references anywhere in the repo; no options-pricing infrastructure exists |

## Global
| Feature | Status |
|---|---|
| S&P 500 (`^GSPC`) | **PARTIAL** — exists only as a relative-strength benchmark fallback for non-Indian symbols in `quant_research/`, never wired into `decision_engine/` |
| NASDAQ, USD/INR | **MISSING as standing features** — each appears exactly once, in one archived, one-off `strategy/hypothesis_registry.py` experiment, with no reusable fetch function |
| GIFT Nifty | **MISSING, confirmed unavailable** — explicitly investigated and found not reliably available via Yahoo (`market_intelligence/regime.py:77-79`) |
| DXY, crude oil, Asian markets | **MISSING** — zero references anywhere |

## Calendar
| Feature | Status |
|---|---|
| Market holiday | **EXISTING, operational only** — used by the scheduler/session logic, not exposed as a decision-engine feature |
| Time of day | **MISSING as a feature** — `live/dhan/market_session.py` derives an operational PRE_OPEN/OPEN/CLOSED state from wall-clock time, but nothing turns "minutes since open" into a numeric feature |
| Expiry proximity, economic event proximity | **MISSING** — no options-expiry calendar or economic-calendar integration exists anywhere |

## Not worth adding yet
Full order-book depth beyond 5 levels (no reliable data path); options IV/PCR/OI-based signals (no options pricing infrastructure, no verified reliable free data source); DXY/crude oil (no evidenced relevance to NSE intraday equities established anywhere in this project's own research history — would add data-source surface area without a hypothesis motivating it); GIFT Nifty (confirmed unavailable).

---

# Data Quality Risks

| Risk | Status | Evidence |
|---|---|---|
| Unadjusted price data (corporate actions) | **Present, partially mitigated** | `market/data_provider.py` fetches with `auto_adjust=False`; `predictions/tracker.py`'s `ANOMALOUS_BAR_GAP_THRESHOLD=0.5` guard was built specifically to catch an unadjusted-split-shaped price jump and report `INSUFFICIENT_DATA` rather than a fabricated outcome — a real, disclosed, Phase-36 mitigation, not a fix |
| Survivorship bias | **Present, disclosed, previously self-audited** | `docs/BRUTAL_SELF_CRITIC.md` section 2: the current universe is a hand-curated, currently-listed watchlist; delisted/failed companies are structurally absent |
| Look-ahead bias | **Guarded, tested** | Dedicated tests exist at every backtest layer (`tests/test_backtest_lookahead.py` and equivalents in `backtesting/regime.py`/`walk_forward.py`) — verified failing-before-fix per project convention |
| Timezone/timestamp handling | **Previously buggy, fixed, recurring bug class** | A naive/UTC-aware datetime mismatch caused real crashes three separate times (Phases 33, 37, 42) — a systemic convention gap that point-fixes have not fully closed (see `AUDIT_BASELINE.json.known_bugs`) |
| Symbol changes / delisted stocks | **Not handled** | The universe is a static watchlist; no delisting-detection logic exists |
| Market-hours filtering for intraday features | **Unverified — no intraday workflow has ever run** | `main.py:1872-1884`'s own comment: "No real workflow in this project uses an intraday `--interval` today" |
| Missing/stale bars | **Partially handled** | `live/state_store.py`'s `feed_status` tracks freshness; `market_data/resilience.py` exists but is opt-in only (`--resilient`) |
| Future sector classification bleeding into a historical feature | **Not evaluated — sector_strength_score is computed from the CURRENT scanned universe, so a historical backtest using it would need to confirm sector membership itself doesn't silently use present-day classification for past dates** | Flagged as an open question, not confirmed either way — `market_intelligence/nse_sector_map.py` is a static, present-day lookup table with no historical versioning |

**Conclusion**: the deterministic backtest itself is well-guarded against look-ahead. The specific *new* risks a feature/label engine would introduce (future corporate actions, future sector tags, future index constituents, future news bleeding into an "as of" evidence snapshot) have not yet been tested because the components that would create them (a feature store, a label generator) do not exist yet — this is why Section "Data Leakage Audit" below is written as a design, not a report of clean-bill-of-health.

---

# Label Design

**Recommended initial target**: triple-barrier, 2-class first (`target_hit_first: bool`, folding STOP and EXPIRED together as `False` initially, to keep the first baseline simple; a 3-class TARGET/STOP/TIMEOUT split is the natural next iteration once the 2-class baseline is validated).

**Horizon**: cannot be responsibly fixed by this document alone. `main.py`'s own code comment confirms no workflow has ever run on an intraday interval — before choosing "15 minutes" or "60 minutes," the actual depth/reliability of yfinance intraday history for the intended universe must be verified empirically (this is P0 work, listed below), since intraday history windows from free providers are frequently much shorter than daily history and this has never been checked in this repo. Pending that check, the recommended **starting hypothesis** is a 30–60 minute horizon on 5-minute bars, matching the README's own confirmed 5m/15m/60m availability claim for the existing (unused) intraday capability, and reusing the SAME ATR-based stop/target convention `strategy/baseline.py` already uses for consistency with the rest of the system.

**Target/stop**: reuse the existing `STOP_ATR_MULTIPLIER`/`TARGET_RISK_REWARD` convention from `strategy/baseline.py` rather than inventing a new sizing rule — this keeps the label consistent with what a real trade using this system's own risk engine would actually attempt.

**Timeout**: `horizon_bars`, matching the field that already exists on `PredictionRecord`.

**Overlapping-label problem**: a real, currently-unaddressed risk. If candidate signals fire on consecutive or near-consecutive bars for the same symbol, their triple-barrier outcome windows overlap in time and are **not statistically independent** — but every CI in `learning/profitability.py` (Wilson score interval, normal-approximation mean-return interval) assumes i.i.d. samples. This is not a new problem this project invented — it is the well-known financial-ML "overlapping labels" issue — but nothing in the current codebase accounts for it. **This must be addressed (e.g. non-overlapping sampling, or a sample-weighting scheme) before trusting any CI computed over triple-barrier-labeled data**, and is listed explicitly as a P0/P1 research task below.

**Market regime conditioning**: reuse `learning/regime.py::classify_regime_at` (or `market_intelligence/regime.py`'s richer breadth/trend classification) as a stratification variable — this matches the existing hypothesis-registry convention of regime-bucketed analysis already used in this project's own prior mean-reversion research.

**Why not a raw N-minute forward-return regression?** It was considered and rejected as the *first* target: it ignores the asymmetric stop/target structure this project encodes everywhere else, produces a noisier training signal for a comparable sample size, and doesn't map onto any existing data structure the way triple-barrier does onto `PredictionRecord`. It remains a reasonable *second* target once triple-barrier classification is validated.

---

# ML Problem Formulation

Given the above: **Problem = binary/ternary classification, `P(target hit before stop, within horizon | feature vector at signal time)`.** Model choice is addressed in Baseline Models below; the important point for problem formulation is that this maps cleanly onto every downstream consumer already in the codebase — `risk/engine.py`'s sizing formula, `paper/`'s trade-plan structure, and `predictions/`'s outcome tracking all already speak "entry/stop/target," so a probability of the target-side barrier requires no new consumer-side plumbing, only a new producer.

---

# Backtesting Limitations

| Friction | Modeled? | Evidence |
|---|---|---|
| Flat brokerage | **Yes** | `backtesting/costs.py::CostModel.brokerage_per_fill = 20.0` |
| Exchange fees (fees_pct) | **Yes, blended** | `india_nse_intraday_2026()`: `fees_pct=0.00375` — labeled "NSE exchange charges" |
| STT | **Yes, blended into `taxes_pct`** | `taxes_pct=0.025`, explicitly documented as STT only |
| GST | **No — explicitly omitted by disclosed design** | Cost-model docstring: "GST and stamp duty are omitted... small relative to STT/brokerage at this level of approximation; revisit before relying on this for real P&L" |
| Stamp duty | **No — same disclosed omission** | Same as above |
| SEBI charges | **No — not mentioned anywhere in the cost model at all** | Confirmed absent from both fields and docstring |
| Entry/exit slippage | **Yes, fixed bps** | `entry_slippage_bps=5.0`, `exit_slippage_bps=10.0` |
| Bid-ask spread (as a distinct concept from slippage) | **No** | `backtesting/execution.py` — only slippage bps exist; no separate spread model |
| Price impact scaling with order size | **No** | Confirmed absent |
| Partial fills | **No** | Confirmed absent |
| Gap-through-stop (price gaps past the stop level) | **No — a real, quantified risk** | `check_exit` (`execution.py:32-44`) always fills at exactly `position.stop_price`, never at a worse gapped price, even when the bar's `low` is far below the stop |
| Order-to-fill latency | **No, except a discrete Monte Carlo perturbation** | `backtesting/execution_robustness.py`'s `fill_delay_probability=0.15` simulates "one extra bar of delay" only in the robustness Monte Carlo, not in the standard engine |
| Monte Carlo robustness scope | **Entry-fill mechanics only** | `ExecutionRobustnessConfig` (`missed_fill_probability`, `fill_delay_probability`, `slippage_multiplier_range=(0.5,3.0)`) — exit-side mechanics (`check_exit`/`close_trade`) and the cost-model fee/tax rates are never perturbed |

**THEORETICAL P&L** (what the current engine reports): idealized next-bar-open entry, exact-price stop/target fills, fixed slippage bps, blended STT+exchange-fee cost model, no spread/impact/partial-fill/gap-through/latency friction.

**EXECUTABLE P&L** (what a real account would realize): requires real spread capture, real gap-through-stop losses (a live account WILL sometimes exit worse than the nominal stop on a gapping instrument — this backtester currently cannot show that), real partial-fill/rejection modeling for larger size, and a fully itemized cost model (GST, stamp duty, SEBI charges added back in). **No component of this repository currently produces an Executable P&L estimate distinct from the Theoretical one** — the Monte Carlo robustness test is the closest approximation that exists, and it explicitly covers only entry-side timing/slippage variance.

---

# Trading Edge Research Plan

The existing infrastructure (`strategy/hypothesis_registry.py`, `strategy/promotion_gate.py`, `strategy/multiple_testing.py`) **is genuinely sufficient to run this research program as-is** — it has already been exercised across 55 pre-registered hypotheses in this project's own history, with sample-size floors (30 trades/split), Wilson/normal-approximation 95% CIs, max drawdown, profit factor, and Bonferroni-corrected family-wise error control. **There is no Sharpe or Sortino ratio anywhere in the codebase** (confirmed by repo-wide grep — the only related metric, `return_volatility`, is explicitly and repeatedly disclaimed in its own docstring as "NOT a Sharpe ratio... trades are not evenly spaced, and this project tracks no risk-free rate") — add one only if a real need for it emerges; per-trade profit factor and the mean-return CI already answer "is this distinguishable from noise" without it.

**Gap is feature availability, not statistical method.** The mission's own example hypothesis —

```text
Market bullish + sector strong + stock relative strength strong +
price above VWAP + volume expansion + momentum confirmation
```

— cannot be tested today because VWAP distance does not exist as a feature. A version using only *currently existing* features is immediately runnable:

> **Hypothesis #1 (proposed, NOT run)**: does requiring full 5-factor corroboration (`composite_score > 0 AND trend_score > 0 AND momentum_score > 0 AND breakout_score > 0 AND relative_strength_score > 0`, extending the existing 2-factor corroboration check to all 5 sub-scores already computed by the scanner) produce a statistically distinguishable positive expectancy versus the current 2-factor rule, using the *exact same* `promotion_gate.py`/dev-val-oos machinery already in place?

This requires zero new features, zero new infrastructure, and directly tests whether the scanner's own already-computed-but-unused evidence (`breakout_score`, `relative_strength_score`, `sector_strength_score`) carries real signal when actually required rather than merely stored. **This is the cheapest, most immediately actionable research task in this entire analysis** and is listed first under P0.

**One real gap in the existing experiment infrastructure**: `experiments/comparison.py::compare_experiments` produces only point-estimate `win_rate`/`average_return`/`profit_factor` per experiment window — it does **not** apply `promotion_gate.py`'s CI/significance machinery to compare two experiments against each other. If rigorous A/B comparison between two live configs becomes a priority, this is a real, scoped gap (not proposed for implementation here, per the mission's own "analysis only" constraint).

---

# ML vs LLM Responsibility

The mission's proposed matrix is directionally correct and matches this project's own architecture in every deterministic/risk/audit row. Two rows are challenged based on repo evidence:

| Task | Deterministic | Statistical/ML | LLM |
|---|---|---|---|
| Indicator calculation | **YES** (confirmed: `market/indicators.py`) | NO | NO |
| Risk calculation | **YES** (confirmed: `risk/engine.py`) | NO | NO |
| Position sizing | **YES** (confirmed: `risk/engine.py`, ATR-based) | NO | NO |
| Market prediction | **YES, today** — the mission's matrix says NO/YES(ML)/NOT PRIMARY(LLM), describing an intended future state; **today it is 100% deterministic** (`composite_score` sign test), not ML, not LLM | Target state, not current state | NOT PRIMARY |
| Probability estimation | Currently **N/A — does not exist** anywhere in the live pipeline | **YES**, target state | NO |
| News extraction | NO | OPTIONAL | **YES** (confirmed: `research/summarizer.py`, narration only, no structured classification exists today) |
| News reasoning | NO | OPTIONAL | **YES** |
| Research synthesis | NO | OPTIONAL | **YES** (confirmed: `research/summarizer.py`) |
| Explanation | NO | NO | **YES** (confirmed: `agents/signal_explainer.py`, `decision_engine/engine.py::narrate_decision`) |
| **Tool orchestration** | **CHALLENGED — today this is deterministic Python, NOT LLM.** `main.py`'s command dispatch and `shadow-run`'s scan→research→decide→predict→evaluate→learn sequencing are plain, fixed Python function calls (`main.py`, `scheduler/runner.py`). The MCP server (`mcp_server/server.py`) *exposes* 23 tools *to an external LLM client* — it does not itself use an LLM to decide which of its own internal functions to call next. If a future architecture wants an internal LLM-driven orchestration loop, that is new work, not something already in place. | NO | Only for an *external* client via MCP, not internally |
| Trade authorization | **YES** (confirmed: `risk/engine.py` veto rules; `live/approval.py` state machine; independently re-verified real-order-execution is structurally disabled) | NO | NO |
| Audit record | **YES** (confirmed: deterministic `config_version`/`decision_id` hashing) | NO | **PARTIAL GAP** — AI-output records carry zero provenance metadata (provider/model/prompt version/timestamp/cost), a real, confirmed absence — see LLM Auditability below |

---

# LLM Requirements

Based on what the codebase already asks an LLM to do (confirmed, not proposed): narrate a fixed decision label, explain a fixed signal, produce an adversarial second opinion on a fixed label, synthesize collected news/sector evidence into free text with a self-reported confidence, and (in the legacy `analyze` pipeline only) narrate a full multi-agent debate.

None of these are latency-critical (all are post-decision narration, never gating the deterministic label), none require large context (each prompt operates on one symbol's already-collected evidence), and none currently require tool-calling loops (the LLM never calls back into the system — it receives a pre-built prompt and returns one structured Pydantic object via `invoke_structured`).

**Task → model tier mapping (recommendation, not implementation):**

| Task | Suggested tier |
|---|---|
| Decision narration, signal explanation | Fast, cheap, local is fine — low-stakes, already narrow-scoped by type signatures |
| Research synthesis (news + sector → summary) | Medium — benefits from stronger reasoning if news volume/complexity grows, but current scope (a handful of headlines) doesn't demand it |
| Adversarial decision review (`decision_reviewer`) | Stronger reasoning model recommended — this is the one task explicitly meant to find flaws a weaker model might miss |
| Numeric calculation of any kind | **No LLM, ever** — already fully enforced structurally |

**One concrete, already-present quality risk**: `core/config.py:30`'s own comment states `qwen2.5-coder:7b` is a **substituted** default because the originally-intended `llama3.1:8b` "isn't pulled locally" — i.e. the current model choice is a hardware/availability compromise, not a considered fit for financial narration/reasoning tasks (it is, by name, a *code*-oriented model). **[UNVERIFIED]** whether output quality is adequate for the research-synthesis/adversarial-review tasks — no evaluation harness for LLM output quality exists anywhere in this repo.

---

# OpenAI vs Anthropic vs LiteLLM vs Ollama

**Not implementing any of this.** Analysis only, as instructed.

**Ollama (current)**
- *Advantages, confirmed by evidence*: local (no data leaves the machine — relevant given this is a personal trading tool), zero per-token cost, already fully integrated (`llm/provider.py`), every non-AI command works with it absent (confirmed graceful-degradation design).
- *Disadvantages, confirmed*: hardware-limited (the `qwen2.5-coder:7b` substitution above is direct evidence of this constraint biting already), no cloud-grade reliability SLA, and — unverified but plausible given model size — likely weaker structured-output reliability and reasoning depth than a frontier cloud model for the adversarial-review task specifically.

**OpenAI** — stronger structured-output/tool-calling support and generally stronger reasoning at the model sizes typically available; per-token cost; requires network reliability; data leaves the local machine (a real consideration if this project's privacy stance is intentional, not incidental — the README repeatedly emphasizes "local-first"). **[UNVERIFIED]** exact current-generation model capabilities/pricing — out of scope for a code audit to assert without checking live pricing pages, and doing so is unnecessary for this recommendation.

**Anthropic** — same tradeoff profile as OpenAI (stronger reasoning, cloud dependency, per-token cost); comparatively strong for the adversarial-critique use case specifically (long-context, careful reasoning), consistent with what `decision_reviewer`'s own prompt already asks for. **[UNVERIFIED]** exact current pricing/latency — same caveat as above.

**LiteLLM** — a routing/abstraction layer, not a model. **This repository already has its own thin abstraction** (`llm/provider.py::get_chat_model`, keyed by an `LLMProvider` enum with `OLLAMA`/`NIM`/`OPENAI` members, the latter two currently unconditional `NotImplementedError` stubs). Recommendation: **do not add LiteLLM as a second abstraction layer on top of an abstraction layer that already exists.** Either (a) implement the existing `NIM`/`OPENAI` stubs directly — simpler, zero new dependency, and the enum already anticipates exactly this — or (b) if and when the number of providers/models genuinely grows past what a 10-line dispatch function can cleanly handle, replace (not layer) the existing abstraction with LiteLLM. There is no concrete operational benefit to introducing it today, since exactly one provider is in active use.

```text
Application
   ↓
llm/provider.py (existing, thin)
   ├── Ollama (implemented)
   ├── NIM (stub, NotImplementedError)
   └── OpenAI (stub, NotImplementedError)
```
is already the right shape; it just needs its two stub branches implemented if/when a second provider is genuinely required.

---

# Model Routing

**Not justified today.** The system's own AI-touching workload is small, low-frequency (single-user, non-high-frequency per the roadmap's own single-user framing), and currently entirely served by one local model with no reported quality complaint on record. Introducing multiple models/tiers now would add operational complexity (which role uses which model, keeping N models pulled/warm, routing logic) without a demonstrated need. **Recommendation**: keep one model; if and when a *specific* role (most likely `decision_reviewer`, the adversarial-critique task) is found to underperform, upgrade *that one role* first via the existing per-role `AgentRole`/temperature mechanism already in `core/config.py`, rather than introducing a general multi-model routing architecture pre-emptively.

---

# LLM Auditability

**Confirmed absent, comprehensively.** `agents/analyst.py::invoke_structured` — the single call site every AI-output-carrying function in the system routes through — performs no logging beyond a bare `print(f"Running {label}...")`. Every AI-output schema in the codebase (`SignalExplanation`, `DecisionReview`, `DecisionNarrative`, `ResearchSummary`, `TradingDecision`, `CriticAssessment`, `DebateSummary`, `RiskAssessment`, `TechnicalAnalysis`) was read in full and **none carries a provider, model name, model version, prompt version, call timestamp, input hash, output hash, latency, or token/cost field.**

**Recommended schema for every AI operation** (design only, matching the mission's own list, and matching this project's own existing conventions — the `DecisionConfig.version_id()` SHA-256 pattern for deterministic config, and `core/events.py::log_event`, which already exists and is already called at each pipeline stage but never wraps an LLM call):

```text
provider          (e.g. "ollama")
model              (e.g. "qwen2.5-coder:7b")
model_version      (if the provider exposes one; else omitted, not fabricated)
prompt_version     (a stable identifier for the exact prompt template used --
                    could reuse the SAME sha256-hash-of-content convention
                    DecisionConfig already uses)
timestamp
input_hash         (sha256 of the exact prompt sent)
output_hash        (sha256 of the raw structured output)
latency_ms
token_usage        (prompt/completion, where the provider reports it)
cost               (where knowable; None for Ollama, not fabricated as 0)
structured_output_ref  (the record id this call produced, e.g. decision_id)
source_evidence_refs   (scan_id / research report_id / etc already available)
```

This is a small, targeted addition — one new log call inside `invoke_structured`, reusing the existing `log_event` mechanism — not a new subsystem, consistent with this project's own demonstrated preference for minimal, targeted fixes over infrastructure builds (see `docs/OBSERVABILITY.md`'s own "deliberately a small, targeted addition... not a new metrics/observability infrastructure build-out" precedent).

---

# RAG Assessment

**Content**: exactly one file, `documents/strategy.pdf` (1.08MB), loaded by exactly one script (`build_vector_db.py`), chunked at 1000 chars / 200 overlap. Confirmed via directory listing — `documents/` contains nothing else. No trading history, strategy backtest result, company filing, or news archive has ever been written to the vector store — `rag/vector_store.py::create_vector_store` is called from exactly one place in the entire codebase.

**Does RAG contribute to the current decision engine?** No. `rag/retriever.get_context()` is called from exactly one place — `main.py:85`, inside the legacy `analyze` command — and its result is explicitly labeled in the consuming prompt as **"qualitative context, not a market-data source"** (`agents/technical_agent.py:36`). `decision_engine/`, `predictions/`, `research/`, and every Phase-18-onward command never import `rag/` at all.

**Predictive vs. explanatory value**: with its current single-static-document content, RAG **cannot plausibly provide predictive value** — there is no market data, no historical outcome, no company-specific fact in the corpus for it to retrieve. It can only ever provide explanatory/qualitative framing (e.g., background strategy philosophy) for the one legacy pipeline that already restricts it to that role by explicit prompt instruction.

**Recommendation (per the mission's own explicit instruction): do NOT auto-integrate RAG into the decision engine.** If RAG is ever to provide predictive value, that would require deliberately ingesting something with actual forecasting content — e.g., a corpus of past `hypothesis_registry.py` results, or a genuine news archive with resolved-outcome labels — which is a distinct, much larger undertaking than "turn RAG on," and is not recommended until the basic feature/label/baseline-model work below is validated.

---

# Recommended Target Architecture

```text
Market Data                          [EXISTING: market/, live/dhan/]
    ↓
Normalized Data                      [EXISTING: market/indicators.py::compute_indicator_series]
    ↓
Feature Engine                       [NEW: a dedicated module, additive only --
                                       consolidates existing indicators + VWAP
                                       distance, time-of-day, normalized
                                       intraday range, cross-sectional rank/
                                       percentile fields. Does NOT modify
                                       scanner.py or decision_engine/.]
    ↓
Historical Feature Store             [NEW: schema below. Read-only from the
                                       live pipeline's perspective -- an
                                       offline/research artifact, like
                                       quant_research/'s own data today.]
    ↓
Label Generator                      [NEW: a thin adaptation of the EXISTING
                                       predictions/tracker.py::evaluate_
                                       prediction / backtesting/execution.py::
                                       check_exit mechanics, applied to
                                       historical bars to produce triple-
                                       barrier labels instead of live outcomes.]
    ↓
Baseline Models                      [PARTIAL EXISTING: SimpleMomentumBaseline,
                                       SimpleTrendBaseline, RandomEntryStrategy,
                                       buy-and-hold (strategy/simple_baselines.py,
                                       backtesting/random_baseline.py,
                                       backtesting/baselines.py).
                                       NEW: one logistic regression baseline.]
    ↓
Walk-Forward Evaluation              [PARTIAL EXISTING: backtesting/walk_
                                       forward.py's fixed-window re-application
                                       needs a NEW retrain-per-fold extension,
                                       since no trainable model has existed
                                       until now.]
    ↓
Probability Calibration              [NEW: does not exist anywhere today.]
    ↓
Expected Value                       [NEW: P(target)*reward - P(stop)*risk,
                                       a direct, small calculation.]
    ↓
Risk Engine                          [EXISTING, UNCHANGED: risk/engine.py]
    ↓
Paper Trading                        [EXISTING, UNCHANGED: paper/]
    ↓
Outcome Tracking                     [EXISTING, UNCHANGED: predictions/]
    ↓
Learning / Research                  [EXISTING, UNCHANGED: learning/,
                                       strategy/promotion_gate.py,
                                       strategy/multiple_testing.py]
```

Only after this chain produces a promotion-gate-validated, statistically defensible edge should the second layer be considered:

```text
LLM Research Layer
        ↓
News/Event Intelligence      [EXTENDS existing research/ -- currently
                               narration-only, would need real structured
                               classification if used as a feature]
        ↓
Historical Context            [Would require RAG to be deliberately re-scoped
                               beyond its current single-document content --
                               see RAG Assessment]
        ↓
Explanation                   [EXISTING, already works: signal_explainer,
                               decision_narrator]
        ↓
Adversarial Review             [EXISTING, already works: decision_reviewer]
```

This ordering matches the mission's own explicit instruction and this analysis's own central finding: the quantitative gap, not the LLM gap, is what currently prevents this from being a statistically validated trading-intelligence platform.

---

# P0 Research Tasks (no code)

1. Pre-register **Hypothesis #1** (full 5-factor corroboration using only existing `CandidateScore` fields) in `strategy/hypothesis_registry.py`'s own format, following this project's own established pre-registration discipline.
2. **Verify intraday data depth/reliability** for the intended universe via yfinance before committing to any horizon — confirm actual available history length and gap rate for 5m/15m bars; this is currently a genuine unknown, not an assumption (`main.py`'s own comment confirms no workflow has ever exercised an intraday interval).
3. Formally pre-register the triple-barrier target/stop/timeout design (a written document, matching this project's own convention) before any label-generation code is written.
4. Design (not build) the leakage-test suite extending the existing `tests/test_backtest_lookahead.py` pattern to a feature engine and label generator, covering every vector named in "Data Leakage Audit" below.
5. Resolve the `sector_strength_score` (internal, universe-relative) vs. `market_intelligence/regime.py`'s external NIFTY sector indices inconsistency — decide, on paper, which is authoritative before building any new sector feature on top of either.

# P1 Implementation Tasks (deferred, not started by this document)

1. Build a new, additive feature-engine module: VWAP distance, time-of-day, normalized intraday range, opening-gap, cross-sectional rank/percentile fields — none of these modify `scanner.py` or `decision_engine/`.
2. Build a triple-barrier label generator by adapting `predictions/tracker.py::evaluate_prediction`/`backtesting/execution.py::check_exit` for historical, offline batch use.
3. Build the historical feature store (schema below).
4. Implement one logistic-regression baseline over the existing + new features, evaluated exclusively through the *existing* `promotion_gate.py` machinery — no new statistical infrastructure.
5. Implement the existing `llm/provider.py::NIM`/`OPENAI` stubs **only if** a concrete need for a non-Ollama provider is confirmed by P0/P1 findings (e.g., `decision_reviewer` quality issues).
6. Implement the LLM-auditability logging addition described above (one new `log_event` call site inside `invoke_structured`).

# P2 Validation Tasks

1. Extend `backtesting/walk_forward.py` with a retrain-per-fold mode (expanding or rolling training window), since the existing module explicitly has no retraining mechanism today.
2. Apply `strategy/multiple_testing.py`'s Bonferroni correction across every new feature/model variant actually tested — not just the final chosen one, to avoid quietly reintroducing the multiple-comparisons risk this project has otherwise taken seriously.
3. Run the leakage-test suite (P0 item 4, now built) against the new feature engine and label generator.
4. **Run the central empirical test this entire analysis exists to enable**: compare the new logistic-regression baseline against the existing deterministic `composite_score` rule, on identical data/splits, through `promotion_gate.py`, and report the verdict honestly regardless of outcome.

# P3 Controlled Paper Trading

Only if P0–P2 produce a statistically defensible edge (a `PROMOTED` or at minimum a repeatedly `INCONCLUSIVE`-but-directionally-consistent verdict, never a self-declared one): wire the validated model's calibrated probability into a **new, clearly and separately labeled experimental decision path**, parallel to (never replacing) the existing deterministic `decision_engine`. Paper-trade only, through the existing `paper/` engine and reconciliation infrastructure, promotion-gated, with the same "no live execution" constraint this project has verified end-to-end and unconditionally maintained throughout its history.

---

# Explicitly Deferred Features

- Options/derivatives analytics (IV, PCR, OI-based signals) — no reliable data path exists; the only OI-capable code (`live/dhan/wire.py`) is unused by the live subscription mode today.
- DXY, crude oil, Asian-market indices — no relevance ever evidenced by this project's own research history; would add data-source surface area without a motivating hypothesis.
- GIFT Nifty — confirmed unavailable via the project's own prior investigation.
- Full order-book depth beyond 5 levels — no reliable data path (the 20-level `SUBSCRIBE_DEPTH` protocol has no implemented response parser at all).
- NIFTY constituent-index-based universe modes (50/100/200/500) — already a known, disclosed gap (no verifiable membership source), unrelated to but compounding the feature-availability gap for any cross-sectional-ranking feature that would want a "real" index universe rather than a hand-curated watchlist.
- Any autonomous or live order execution — explicitly out of scope by this mission's own instruction and independently, structurally disabled throughout the codebase (re-verified in the prior audit phase).

---

# Risks

- **Overlapping-label autocorrelation** would silently invalidate every Wilson/normal-approximation CI computed over triple-barrier-labeled data unless explicitly addressed (non-overlapping sampling or a weighting scheme) — the single largest statistical risk in the proposed plan.
- **Survivorship bias** in the current hand-curated universe remains present and disclosed; any new cross-sectional feature (rank, percentile) inherits it.
- **Unadjusted price data** means any large historical corporate action could corrupt a feature/label near its ex-date; today's mitigation (`ANOMALOUS_BAR_GAP_THRESHOLD`) discards the affected sample rather than truly correcting it — acceptable for now, but a real, standing data-quality debt.
- **Local LLM suitability for financial text tasks is unproven** — `qwen2.5-coder:7b` is a disclosed hardware-driven substitution, not a considered choice, and no evaluation harness for LLM output quality exists to check this claim either way.
- **Scope creep**: this document's own P1/P2 items are substantial engineering work; the mission's explicit "do not implement yet" constraint must be honored by whoever picks this up next — a plan is not an authorization.

# Unknowns

- Exact yfinance intraday history depth/reliability for the intended universe — **not yet checked**, and load-bearing for the horizon decision in Section "Label Design."
- Whether `qwen2.5-coder:7b`'s output quality is adequate for the `decision_reviewer`/research-synthesis tasks — **[UNVERIFIED]**, no evaluation harness exists.
- Whether Dhan's real 5-level depth data, if ever actually subscribed to, would be reliable/low-latency enough to be a useful feature — **never tested**, since the live pipeline has never subscribed in any mode beyond Ticker.
- The true magnitude of the omitted GST/stamp-duty/SEBI-charge gap in the cost model at realistic trade volumes — **not quantified**, only disclosed as a simplification.
- Whether `sector_strength_score`'s internal (universe-relative) computation and `market_intelligence/regime.py`'s external NIFTY-sector-index computation would agree or materially diverge if compared directly — **never compared**.

# Final Recommendation

Build the smallest defensible pipeline — feature engine → triple-barrier label generator → one logistic-regression baseline → walk-forward evaluation through the *already-existing* promotion-gate machinery — using **only currently-available, already-computed features first** (the full-5-factor-corroboration hypothesis costs nothing and should run before any new feature is built at all). Let that pipeline's own honest, already-rigorous statistical verdict answer whether *anything* here beats the current deterministic rule before spending further effort on new data sources, LLM integration, or RAG expansion. This is not a new architecture — it is four new, additive modules layered onto infrastructure that already exists, evaluated by machinery that has already proven itself honest across 55 prior hypotheses.

---

# Addendum: Phase 1 refinements (informed by external review)

A review of this document raised four points precise enough to fold directly into the plan rather than merely note. Nothing below changes the conclusions above — it sharpens the execution.

## Separate "model prediction" from "trade decision"

This document's own recommended target (`P(target hit first | features)`) must not be allowed to collapse into a decision by itself. Two distinct layers are required:

```text
MODEL LAYER                          DECISION LAYER
P(target | X_t)                      expected_net_return =
P(stop | X_t)              ──────►     P(target) * target_return
P(timeout | X_t)                       - P(stop) * stop_return
                                        - transaction_cost - slippage - impact
                                      then: risk limits, existing positions,
                                      portfolio exposure, liquidity
```

A model reporting `P(target)=0.54` does **not** itself mean `BUY` — it means the *decision layer* (the existing `risk/engine.py` sizing/veto machinery, unmodified) receives an expected-value number instead of a bare label, and decides from there exactly as it does today. This preserves the project's own evidence → forecast → expected value → decision → risk → execution → outcome → learning shape rather than letting a probability become an order directly — see the diagram accompanying this document.

## Success criteria, fixed before fitting

Committing to an evaluation set *before* seeing results is this project's own established discipline (`strategy/hypothesis_registry.py`'s entire pre-registration convention) and must extend to the first ML baseline. Required, not optional:

- Discrimination: ROC-AUC, PR-AUC, log loss, Brier score.
- Calibration: reliability curve / calibration error, not just the point accuracy.
- Decision-relevant: precision at the probability thresholds actually usable for sizing, hit rate.
- Economic: expectancy, profit factor, maximum drawdown, turnover, transaction-cost-adjusted return, out-of-sample and regime-conditioned performance — all via the *existing* `learning/profitability.py`/`promotion_gate.py` machinery, no new statistical code required.
- **Comparison against trivial baselines is mandatory, not optional**: random, majority-class, always-long, and the *existing deterministic rule*, all on identical periods/symbols/labels/execution assumptions/cost model. A model beating random is not evidence of anything; a model beating the existing deterministic rule after costs is the actual bar.

## Experiment matrix (design, not run)

| Model | Features | Purpose |
|---|---|---|
| Existing deterministic rule | Current 5-score system | Baseline this project already has |
| Logistic regression | Existing numeric features only | First ML baseline — does *any* signal exist at all |
| Logistic regression | Existing + new intraday features (VWAP distance, gap, range) | Feature-value test |
| Logistic regression | Existing + market/sector context | Context-value test |
| Logistic regression | Full approved feature set | Upper baseline before adding model complexity |
| LLM (news/context only) | Text evidence only | Later, incremental — never the first experiment |

Every row uses the same periods, symbols, labels, execution assumptions, and cost model — the comparison is only meaningful if nothing else changes between rows.

## Reframing "62 features" as 62 candidate signals

`TRADING_FEATURE_CATALOG.json`'s 62 entries are candidates, not a feature set — each still has to clear availability → data quality → temporal safety (`leakage_risk`) → redundancy → an actual economic hypothesis before it is a *usable* feature. Feature count is nearly irrelevant to whether a model works; provenance and temporal integrity are what determine it. This is already the discipline the catalog's own schema (`available_today`, `used_in_decision`, `training_safe`, `leakage_risk`, `quality`) was built to enforce — the reframing is a naming correction, not a new requirement.

## Refined task breakdown (supersedes the P0–P3 list above in granularity, not in scope or ordering)

**P0 — Data**
1. Exercise the 5-minute intraday pipeline end-to-end for the first time in this project's history.
2. Validate historical depth available per symbol at that interval.
3. Validate timestamp/timezone correctness and session-boundary handling.
4. Build the reproducible `FeatureSnapshot(symbol, timestamp, features, feature_version, data_version)` contract — the as-of freeze every training row must respect.
5. Validate missing-bar and duplicate-bar behavior.
6. Resolve corporate-action handling (the existing anomaly guard discards; a real dataset needs a considered policy, not just a guard).
7. Establish the historical universe policy (which symbols, over which span, with survivorship bias explicitly stated per-run, not just once in a doc).

**P1 — Labels**
8. Implement offline triple-barrier label generation (adapting `predictions/tracker.py`/`backtesting/execution.py::check_exit`).
9. Define target/stop from the existing ATR convention (`strategy/baseline.py`), not a new sizing rule.
10. Fix the horizon only after task 2's findings, not before.
11. Address the overlapping-label problem explicitly (non-overlapping sampling or a weighting scheme) before trusting any CI computed over the result.
12. Define same-bar target+stop ambiguity handling (reuse the existing conservative "stop wins" rule for consistency with the backtester, unless a specific reason to diverge is found).
13. Generate an immutable, versioned labeled dataset — never regenerated silently in place.

**P1 — Baseline**
14. Logistic regression, nothing more complex, first.
15. Train-only preprocessing (fit any scaler/imputer on the training fold only, never the full dataset).
16. Probability calibration (e.g. Platt scaling / isotonic) — does not exist anywhere in this codebase today.
17. Walk-forward evaluation (extending `backtesting/walk_forward.py` with the retrain-per-fold mode this document already identifies as missing).
18. Compare against the existing deterministic rule, same data, same split, no exceptions.
19. Evaluate net of the existing cost model (`CostModel.india_nse_intraday_2026()`), acknowledging its own disclosed GST/stamp-duty/SEBI-charge omission rather than treating the result as final.

**P2 — Features**
20–26. VWAP distance, opening gap, normalized intraday range, time-of-day, index momentum, sector breadth, cross-sectional ranks — each added and re-evaluated one at a time against the experiment matrix above, not all at once.

**P2 — Statistical validation**
27. Multiple-testing correction (`strategy/multiple_testing.py`, already built) applied across every feature/model variant actually tried, not just the final chosen one.
28. Regime-stratified evaluation (`learning/regime.py`/`market_intelligence/regime.py`).
29. Confirm the overlapping-label treatment (task 11) actually holds under the real dataset, not just in design.
30. Confidence intervals on every reported metric, not point estimates alone.
31. An explicit, pre-stated economic-significance threshold (e.g. "must beat the deterministic rule's net expectancy by more than transaction-cost noise, over N trades") — not just statistical significance.

**P3 — Intelligence (only after P0–P2 produce a defensible edge)**
32. News/event extraction as a structured (not narrative-only) feature.
33. RAG re-scoped beyond its current single-document content, only if 32 shows promise.
34. LLM research synthesis as a feature input, evaluated the same way any other feature addition is (experiment matrix, not assumed).
35. LLM adversarial review, unchanged from its current narrative-only role, unless a concrete case is made otherwise.
36. A quant + qualitative ensemble experiment — last, not first.

**Bottom line, restated**: do not make the LLM the brain of the trading system. First determine, with the same rigor this project already applies to every hypothesis in `strategy/hypothesis_registry.py`, whether the market data it already has contains a measurable, out-of-sample, cost-adjusted predictive signal. The infrastructure to run that experiment already exists.
