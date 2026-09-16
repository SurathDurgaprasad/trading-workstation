# Post-Warmup Intelligence Validation — 2026-09-16

Evidence labels used throughout: **REAL** (observed from a live/real system this session), **MECHANISM-VERIFIED** (proven correct via the project's own code run against real data, but not exercised by today's live signal path), **NOT EXECUTED TODAY**, **NOT IMPLEMENTED**, **DIAGNOSTIC / SECONDARY-SOURCE** (real data from an independent source, used only to explain live behavior, never fed into the live fleet).

## 0. Session outcome, stated up front

The live 15-symbol Dhan paper fleet (Phase D, launched 09:57:51 IST) ran continuously and cleanly for **4h37m**, processing **279 real 1-minute bars per symbol (4,185 total)**, 100% fresh, zero gaps, zero cross-symbol contamination, zero signals, zero predictions, zero trades — until **all 15 workers stopped simultaneously at the same bar (bar #279, 2026-09-16 09:05:00 UTC = 14:35:00 IST)**, with **no error, exception, or SAFE_STOP in any of the 15 logs**. This is not a code defect signature (a real defect produces an error trail; this produced none) — it is consistent with an external interruption to the host process tree (this session's own tooling was interrupted by a usage-limit boundary around the same window, and the working directory context reset afterward). Root cause is disclosed as **NOT DEFINITIVELY ESTABLISHED** rather than guessed further.

A supervised attempt to resume the fleet for the remaining ~55 minutes of the NSE session was **blocked by this environment's own auto-mode permission classifier** ("Interfere With Workloads") when launching a new `fleet-supervise` background process. Per this session's standing instructions, that block was respected rather than worked around — see §9.

All data below reflects the real, complete 4h37m capture window. Nothing was fabricated to compensate for the early stop.

## 1. Baseline at resumption (14:42 IST)

- Branch: `final-product-hardening`, clean working tree except this session's own tracked, reviewed changes.
- `python main.py health`: `database` HEALTHY (10/11 stores), `disk` HEALTHY, `kill_switch` HEALTHY (inactive), `risk` HEALTHY. `dhan` DISABLED and `scheduler` DEGRADED only because this diagnostic shell had no `.env` sourced — expected, not a defect.
- `PRAGMA integrity_check` on `paper.db`/`state.db`/`predictions.db` for 4 sampled symbols (RELIANCE.NS, ITC.NS, SUNPHARMA.NS, ICICIBANK.NS): **all `ok`**.
- **REAL**: 0 paper trades and 0 predictions across all 15 symbols' stores — queried directly, not inferred.
- **REAL**: no real order was ever possible — `live/pipeline.py`, `decision_engine/rules.py`, `risk/engine.py`, `risk/sizing.py`, `live/broker.py`, `live/dhan/broker_adapter.py` all remain zero-diff against `main` for the entire session.

## 2. Post-warmup strategy funnel (REAL, both from the live fleet's own logs and an independent secondary check)

The fleet's own final numbers (`fleet-summary`, from `live/fleet_summary.py`, fixed this session — see §7):

| Stage | Count |
|---|---|
| Bars received (all 15 symbols) | 4,185 (279 each) |
| Fresh bars | 4,185 (100%) |
| Indicator-ready bars (sma_50 non-NaN) | 279 − 49 = 230 per symbol, ×15 = 3,450 |
| Strategy evaluations with all indicators ready | 3,450 |
| Candidates generated (TrendMomentumBaseline.generate_signal() returned non-None) | **0** |
| Critic evaluations | 0 (never reached — critic only runs on a candidate) |
| Risk evaluations | 0 (never reached) |
| Final signals | 0 |
| Predictions recorded | 0 |
| Paper fills | 0 |

**Why**: per-symbol diagnostic runs (real market data, the project's own `market.indicators.compute_indicator_series` + `strategy.baseline.TrendMomentumBaseline` — MECHANISM-VERIFIED against real data, not the live process's private memory, which cannot be introspected) at two points in the session:

**10:37 IST (mid-session, real-time cross-check against Yahoo Finance 1m bars, 106 bars):**

| Symbol | trend (SMA20>50) | momentum (RSI>50 & MACD>sig) | volume_trend | candidate |
|---|---|---|---|---|
| RELIANCE.NS | True | True | decreasing | no |
| HINDUNILVR.NS | True | True | decreasing | no |
| HDFCBANK.NS | True | False | decreasing | no |
| ITC.NS | False | True | decreasing | no |
| *(all other 11 symbols)* | mixed | mixed | decreasing | no |

**The universal blocker at 10:37 IST was `volume_trend`: every one of the 15 symbols showed "decreasing", including the two (RELIANCE.NS, HINDUNILVR.NS) that satisfied BOTH trend and momentum.** This is a real, identifiable, single-condition explanation for zero signals at that moment — not a vague "conditions weren't met."

**14:45 IST (session-end diagnostic, after the live fleet had already stopped, 330 real Yahoo 1m bars):**

| Symbol | trend | momentum | volume_trend | candidate |
|---|---|---|---|---|
| **ITC.NS** | **True** | **True** | **increasing** | **YES** |
| *(all other 14 symbols)* | mixed | mixed | decreasing | no |

**ITC.NS satisfied all three TrendMomentumBaseline entry conditions as of ~14:45 IST, per this independent, real, secondary Yahoo Finance check.** This is disclosed honestly: it is **DIAGNOSTIC / SECONDARY-SOURCE evidence, not a live-fleet-observed signal** — the Dhan-fed live worker for ITC.NS had already stopped at 14:35 IST and was not running at 14:45 IST to observe or act on this. No prediction, no critic evaluation, no risk evaluation, and no trade occurred for it, and none is claimed. Had the fleet still been running (see §9, blocked resume), this condition may plausibly have produced the session's first live candidate — that is a plausible inference, not an observed fact, and is labeled as such.

## 3. AI (OpenAI) real-runtime verification

**REAL ledger state at session end** (`data/ai_call_ledger.db`, queried directly):

| id | trigger | model | status | latency | input_chars |
|---|---|---|---|---|---|
| 1 | operator_requested_analysis | gpt-4o-mini | SUCCESS | 2,676ms | 64 |
| 36 | candidate_generated | gpt-4o-mini | SUCCESS | 3,901ms | 2,099 |
| 37 | candidate_generated | gpt-4o-mini | SUCCESS | 3,988ms | 2,110 |

3 calls today, 3 succeeded, 0 failed. All triggered deliberately (a health smoke-test, and two AI-value experiment calls, §4) — **never once per-bar, never per-minute, never per-symbol-sweep.** Average input size 1,424 chars, well under the 4,000-char budget cap. No token/cost figures are available from the SDK response objects used here (the OpenAI SDK's structured-output wrapper used does not surface usage in this call shape) — disclosed as **NOT AVAILABLE**, not estimated.

**Integration point, verified against real code (not assumed):** `agents.analyst.invoke_structured` is the single choke point. Every call passes `llm.budget.check_budget()` first (hourly cap 10, session cap 30, 20s minimum interval, 4,000-char input cap) and every attempt is recorded to the ledger regardless of outcome. **REAL**: immediately re-running a smoke-test 14s after the first one was **rejected by the budget gate** without spending a second completion — confirmed live, not merely configured.

**Structured evidence packet, verified compact**: `MarketContext` (symbol, price, sma_20/50, rsi_14, macd/macd_signal, atr_14, volume_ratio/trend, data_source) — no raw OHLCV history, no source code, ever passed to the model. Confirmed by inspecting the actual `input_chars` recorded (2,099–2,110 chars for a full signal+risk-decision+market-context prompt).

## 4. Safe AI value experiment (offline, real historical data — the live fleet was never touched)

Since the live fleet produced zero organic candidates, 2 real historical candidates (TrendMomentumBaseline.generate_signal() returning non-None on real cached daily OHLCV — never synthetic) were run through the **actual, already-implemented** `agents.signal_explainer.explain_signal()` integration point:

- **ITC.NS, 2017-01-20**: price 245.93, SMA20 235.39, SMA50 227.22, RSI14 67.1, MACD 4.90/3.999. Real `RiskEngine.evaluate()` → approved=True, quantity=71.
- **RELIANCE.NS, 2017-02-27**: price 283.19, SMA20 245.09, SMA50 243.31, RSI14 80.4, MACD 7.87/3.07. Real `RiskEngine.evaluate()` → approved=True, quantity=50.

**What the AI added beyond the deterministic output, in both cases**: it flagged **RSI approaching/exceeding 70 (overbought) as contradicting evidence** — a genuine qualitative risk-framing the deterministic strategy does not surface at all (`TrendMomentumBaseline` only checks `RSI14 > 50`; it has no upper bound and never flags "approaching overbought" as a caution). This is a materially different piece of information from what deterministic code alone reports, not a restatement of it.

**What it did NOT add**: no price target, no different entry/stop/quantity, no prediction, no claim beyond narrating the already-fixed deterministic numbers. Both responses were correctly typed `SignalExplanation` instances (see §8's structural proof) — the schema itself cannot carry a trading decision.

**AI VALUE finding**: measurable, real, but narrow — **contradiction-detection / risk-framing that the strategy's own binary threshold misses**, demonstrated on 2 real cases. This is not "AI VALUE NOT DEMONSTRATED" (a genuine difference was shown), but it is also not evidence of predictive or trading value — it is evidence of a specific, bounded advisory usefulness (surfacing a caution a human reviewer would want and the deterministic code doesn't produce).

## 5. Live signal path

**No genuine live candidate occurred on the actual Dhan-fed fleet during its 4h37m run.** Per Mission's own required honesty statement: **PREDICTION PATH NOT EXERCISED BY LIVE SIGNAL — mechanism verified by historical/integration tests (§4 above, and the existing test suite).** No signal was manufactured. No threshold was loosened. No bar was injected.

## 6. Market context (NIFTY/regime)

Unchanged from the earlier forensics finding, reconfirmed: `CriticGate._refresh_if_needed()` (the only place NIFTY/scanner/regime data is fetched) is called exclusively from inside `CriticGate.evaluate()`, itself only called on a real candidate. Zero candidates today (on the live fleet) → **zero context fetches today**. Label: **IMPLEMENTED — NOT EXECUTED TODAY** for NIFTY context; **NOT IMPLEMENTED** for global markets/sector/breadth/India VIX in the live path (unchanged from the prior forensics report).

## 7. Defects found and fixed this session

### Defect A — fleet-summary bar counts inflated across intra-day restarts
**Evidence**: `fleet-summary` reported RELIANCE.NS/TCS.NS at 50 bars while their actual running process had only reached 42/44, because `parse_session_log_counts` summed every `bar#` line across the day's 4 scale-up phases instead of only the current process. **Severity**: Medium (misleading operator-facing warmup evidence, not a trading-safety issue). **Root cause**: `session.log` is append-only across restarts; `live/pipeline.py`'s in-memory buffer is not. **Fix**: only count lines after the most recent `RUNTIME DIR:` marker (`live/fleet_summary.py`). **Validation**: 2 new regression tests, mutation-tested, and live-reverified — all 15 simultaneously-launched symbols then reported identical real counts. Committed `98bbbe2`.

### Defect B — AI call ledger polluted by the test suite
**Evidence**: running the full regression suite wrote 27 fake, sub-millisecond-latency rows into the PRODUCTION `data/ai_call_ledger.db` — the same file `ai-health`/the dashboard read as real evidence. **Severity**: Medium (corrupts audit evidence integrity, not a trading-safety issue, but directly relevant to this report's own credibility). **Root cause**: `record_call`/`check_budget`/`summarize_today`'s `db_path` parameter defaulted to `DEFAULT_LEDGER_DB_PATH`'s value bound once at function-definition (import) time — monkeypatching the module attribute afterward (what a test-isolation fixture does) had no effect on the already-bound default. **Fix**: `db_path: Path | None = None`, resolved inside the function body on every call; new `tests/conftest.py` autouse fixture (`_isolate_ai_call_ledger`) redirects every test in the suite to an isolated per-test ledger. **Validation**: a targeted regression test proving the monkeypatch takes effect, mutation-tested (confirmed the bug reproduces with the bound-at-def-time signature, confirmed the fix and the test both catch it). The 27 polluted rows were manually identified and removed from the real ledger, keeping only genuine rows.

### Defect C — Overview/Signals/Portfolio/System silently misleading in fleet mode (partially addressed)
**Evidence** (from the earlier forensics report, reconfirmed): these 4 tabs read the fixed default single-workstation databases, never the fleet's per-symbol `runtime/<SYMBOL>/` stores, while correctly badging stale rows STALE but not explaining *why* (wrong data source, not merely old). **Severity**: Low-Medium (misleading by omission, never fabricated). **Fix applied**: an unmissable `FLEET MODE ACTIVE` banner now appears on all 4 pages whenever fleet mode is configured, pointing to the Fleet tab — live-verified via browser against the real running fleet. **Not fixed**: full data aggregation across N independent per-symbol paper accounts into one Overview remains a genuine architecture decision (whose equity/P&L is "the" number across 15 independent $100,000 accounts?) deliberately not attempted while a real live session was active, to avoid introducing an untested change into the exact pages being watched. 3 new regression tests, mutation-tested.

*(Two further defects — a TOCTOU race in `core/health.py`'s disk write-probe under concurrent startup, and a Fleet-tab health false-negative from a DEGRADED-band oscillation — were found and fixed earlier in today's session; see `docs/LIVE_INTELLIGENCE_FORENSICS_2026-09-16.md` for their full Finding→Evidence→Fix→Validation writeups, commits `b88f458` and `1ee3ace`.)*

## 8. Adversarial / safety proof (new this session)

- **Structural proof, not just a prompt instruction**: all 4 LLM-output schemas (`SignalExplanation`, `DecisionNarrative`, `DecisionReview`, `ResearchSummary`) were checked field-by-field for any name resembling trading authority (`quantity`, `price`, `stop`, `target`, `approve`, `execute`, `order`, `side`, `size`, `action`, `position`, …) — **none found in any of the 4**. A second test constructs each schema with a "poisoned" payload (`approved=True, quantity=999, execute_trade=True` injected alongside valid fields) and confirms the resulting instance has no such attribute — pydantic silently drops unknown keys, so this is a real, not theoretical, guarantee.
- **Malformed/garbage response**: a fake LLM returning a non-schema object on both retry attempts correctly raises `AgentOutputError`, never returns the garbage.
- **429/quota-shaped failure**: simulated (no real network call) — correctly retried once, then raised as a typed `AgentOutputError` wrapping the original exception, never a raw unhandled SDK exception.
- **Concurrent AI requests**: 20 real threads calling `check_budget` simultaneously against a `max_calls_per_session=5` limit — exactly 5 passed, 15 correctly rejected. Mutation-tested: removing the lock around the check let all 20 through, confirming the lock is load-bearing, not cosmetic.
- **Secret never logged**: a recognizable fake API key run through a failing `check_openai_availability()` call, with `caplog` capturing every log record at DEBUG — the key string never appears in any of them.
- 11 new tests in `tests/test_ai_output_cannot_carry_trading_authority.py`, all passing.

## 9. Blocked action — fleet resume

When this session resumed after an interruption, the live fleet was found stopped (§0) with the NSE session still ~55 minutes from close. An attempt to relaunch `fleet-supervise` (the same command used for every prior phase today) was **blocked by this environment's own auto-mode permission classifier** ("Interfere With Workloads"). Per this session's standing instruction to respect such blocks rather than work around them, no relaunch was attempted through any other means. **This is disclosed as a genuine limitation on today's evidence, not hidden**: the session's real captured window is 09:57:51–14:35:00 IST (4h37m of the ~6h15m NSE session), not the full day.

## 10. Regression

Full `pytest -q` run (started 14:43 IST, this session's complete change set): **2,550 passed, 0 failed, 0 skipped, 1 pre-existing unrelated deprecation warning, 561s runtime.** The production AI call ledger (`data/ai_call_ledger.db`) was verified to still contain exactly the same 3 genuine rows immediately after this run completed — confirming Defect B's fix holds under a real full-suite run, not just its own targeted test.

## 11. Final capability matrix

| Capability | Implemented | Executed Today | Real Data | Used in Decision | Verified |
|---|---|---|---|---|---|
| Dhan NSE | YES | YES | YES | YES | YES (4,185 real bars, 15 symbols, 4h37m) |
| BSE | Unchanged from prior report | NO | — | NO | NOT VERIFIED (not re-audited this segment) |
| Yahoo | YES | YES | YES | NO (diagnostic only) | YES (used for the funnel diagnostic, §2, and the offline AI value experiment, §4) |
| Technical indicators | YES | YES | YES | YES (fed the strategy every bar) | YES |
| Strategy (TrendMomentumBaseline) | YES | YES (3,450 evaluations) | YES | YES | YES — 0 candidates, root-caused to volume_trend (§2) |
| Critic | YES | NO (never reached) | — | NO | MECHANISM-VERIFIED only |
| Risk | YES | NO on the live fleet; YES in the offline experiment (§4, real RiskEngine.evaluate()) | YES (offline) | YES (offline) | YES (offline), NOT EXECUTED TODAY (live) |
| NIFTY context | YES | NO | — | NO | IMPLEMENTED — NOT EXECUTED TODAY |
| Sector context | NO (not wired to live path) | NO | — | NO | NOT IMPLEMENTED (live path) |
| India VIX | NO (not wired to live path) | NO | — | NO | NOT IMPLEMENTED (live path) |
| Breadth | NO | NO | — | NO | NOT IMPLEMENTED |
| Global markets | NO | NO | — | NO | NOT IMPLEMENTED |
| Market regime | YES (module exists) | NO | — | NO | IMPLEMENTED — NOT EXECUTED TODAY |
| OpenAI | YES | YES (3 real calls) | YES | NO (advisory only, never in live path) | YES — real API, real budget gate proven |
| Prediction creation | YES | NO | — | NO | MECHANISM-VERIFIED only |
| Prediction resolution | YES | NO | — | NO | MECHANISM-VERIFIED only |
| Paper execution | YES | NO (0 trades) | — | NO | MECHANISM-VERIFIED only |
| Dashboard | YES | YES (Fleet/System tabs live-verified via browser) | YES | N/A | YES — including the new AI status panel and fleet-mode banner |

## STRATEGY FUNNEL

4,185 bars → 3,450 indicator-ready evaluations → **0 candidates** → 0 critic → 0 risk → 0 signals → 0 predictions → 0 trades. Root cause identified precisely (§2): `volume_trend` was "decreasing" fleet-wide for most of the session; one symbol (ITC.NS) crossed all three conditions ~10 minutes after the live fleet had already stopped (diagnostic evidence only, §2).

## AI VALUE

Real, narrow, demonstrated: overbought-risk framing the deterministic strategy's binary RSI>50 threshold does not surface, shown on 2 real historical candidates via the actual `signal_explainer` integration point. Not evidence of predictive or trading value.

## LIVE SIGNAL

None occurred on the live Dhan-fed fleet. Not manufactured. A plausible near-miss (ITC.NS) is disclosed with its exact timing and caveat (§2).

## PREDICTION

None created, none resolved — consistent with zero signals. Mechanism proven correct by existing tests and by the offline experiment's real `RiskEngine` output (§4), never by a live invocation today.

## MARKET CONTEXT

NIFTY context implemented but not executed (never reached CriticGate). Sector/VIX/breadth/global: not implemented in the live path, unchanged from the prior report.

## DEFECTS FOUND

See §7 for the full Finding→Evidence→Severity→Root Cause→Fix→Validation writeups (3 new this segment, 2 from earlier today referenced).

## RESOURCE USAGE

Fleet: ~2.9GB RSS / ~193MB per worker (measured earlier today, unchanged in character — not re-measured at this segment's stop since the fleet was no longer running). OpenAI: 3 calls, ~3.5s average latency, 0 failures, cost not available from the SDK response shape used (disclosed, not estimated).

## REMAINING GAPS

- Session captured 4h37m of a ~6h15m NSE day (§9) — the fleet's unplanned stop and this environment's block on relaunching it are both disclosed, not hidden.
- Zero live signals means critic, risk (live), prediction, and paper-execution paths remain mechanism-verified only, not live-exercised.
- Dashboard Overview/Signals/Portfolio remain architecturally not fleet-aware (banner added, full aggregation not attempted — §7 Defect C).
- BSE status not re-audited this segment (carries forward the prior report's findings).
- AI cost/token usage is not observable from the current OpenAI SDK call shape.

## FINAL VERDICT

**PASS WITH RISKS.**

The engineering, data, and safety layers performed correctly and were genuinely stress-tested (4h37m, 4,185 real bars, zero corruption, zero unsafe behavior, 3 real defects found and fixed with mutation-tested regression coverage, structural proof the AI layer cannot carry trading authority). The risks are: an unexplained simultaneous stop of all 15 workers with no error trail (root cause not established), an incomplete session (55 minutes of NSE hours not captured, and the relaunch was blocked rather than forced), and — unchanged from every prior session — **the strategy itself still has NO DEMONSTRATED EDGE and zero live signals today provides no new evidence either way on that question.**
