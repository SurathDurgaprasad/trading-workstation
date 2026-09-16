# Live Intelligence Forensics — 2026-09-16 (NSE session, fleet running)

Performed **while the 15-symbol real-Dhan paper fleet was running and
untouched** (launched 09:57 IST, Phase D). Every finding below is from
real runtime state — running process command lines, live SQLite
ledgers, worker logs, filesystem timestamps, and live HTTP responses —
not from reading the source tree and inferring behaviour.

Evidence labels: **REAL** (observed in this live session),
**MECHANISM-VERIFIED** (proven by executing the project's own code,
not market data), **NOT EXECUTED** (implemented, but demonstrably did
not run today), **NOT IMPLEMENTED**.

---

## 1. Prediction path

**Status: PREDICTION PATH NOT EXERCISED BY LIVE SIGNAL — mechanism
verified by historical/integration tests.**

Traced in the running system:

| Question | Answer | Evidence |
|---|---|---|
| Where is a prediction created? | `live/prediction_recorder.py::record_prediction_for_signal` | source + call site |
| Call-site gate | `main.py:1264` — `if prediction_store is not None and result.signal is not None` | REAL (read from running build) |
| Fires for every eligible signal? | Yes — for **every** result carrying a signal, regardless of what happens next (PENDING_HUMAN_APPROVAL, CRITIC_REJECTED, KILL_SWITCH_ACTIVE, auto-approved) | source + its own docstring |
| Deterministic or LLM? | **Deterministic.** No LLM module is loaded in the live path at all (§3) | REAL |
| Inputs | `result.signal` (entry/stop/target from `strategy.signal.Signal`), a read-only `RiskEngine.evaluate()` recompute, `result.critic_assessment`, `pipeline.interval` | source |
| Stored where | `runtime/<SYMBOL>/predictions.db`, table `predictions` | REAL (schema read live) |
| Prediction ID | `PredictionRecord.new_id()`; `decision_id` = `signal.stable_id()` (live path has no `decision_engine.Decision`) | source |
| Horizon | 20 bars (`--prediction-horizon-bars` default), interval `1m` | REAL (process cmdline) |
| Predicted outcome | Entry/stop/target **price levels** — not a probability or direction score | source |
| Resolved by | `predictions/tracker.py::evaluate_prediction` — real future OHLCV vs those levels | source |
| Resolution data source | **Yahoo Finance historical**, a *separate* provider from the live Dhan feed (`main.py:1188`) | REAL |
| Costs in resolution? | **No.** `predictions/tracker.py` contains zero cost references — outcome is a gross price-level hit. Costs are applied only at the paper-execution layer (`CostModel.india_nse_intraday_2026`). **These two numbers must never be conflated.** | REAL (grep) |
| Resolve more than once? | Evaluations are **appended** as new rows (`prediction_evaluations`); the prediction record itself is immutable | source + schema |
| Orphaning | A prediction stays ACTIVE and is retried next cycle if evaluation fails; never partially applied | source |
| Restart preservation | Yes — SQLite file per symbol, survives restart | REAL (survived 4 phase restarts) |

**Today's ledger state (REAL, read-only query of all 15 DBs):**

```
predictions = 0,  prediction_evaluations = 0   (all 15 symbols)
```

Zero predictions because zero signals occurred (§2/§5). The mechanism
is covered by existing integration tests; it was **not** exercised by a
live signal today.

---

## 2. Why zero signals — the funnel

All 335 bars processed across 15 workers produced exactly one outcome
kind: `BAR_PROCESSED`. **Zero** `STALE_SIGNAL_SUPPRESSED`, **zero**
`CRITIC_REJECTED`, **zero** `PENDING_HUMAN_APPROVAL`, **zero**
`RISK_REJECTED`.

Per-symbol funnel (10:06 IST sample, current process):

```
every symbol:  bars=9  indicator_ready=0  candidates=0
               critic_rejected=0  risk_rejected=0  final_signals=0
```

**Root cause — Stage 1, insufficient indicator history.**
`TrendMomentumBaseline.generate_signal` returns `None` at its first
guard when any of `sma_20, sma_50, rsi_14, macd, macd_signal, atr_14,
volume_trend` is NaN. `sma_50` needs 50 bars.

Proven by executing the project's own indicator + strategy code
(MECHANISM-VERIFIED):

```
bars= 10  NaN: ['sma_20','sma_50','rsi_14','atr_14'] -> generate_signal: None
bars= 26  NaN: ['sma_50']                            -> generate_signal: None
bars= 49  NaN: ['sma_50']                            -> generate_signal: None
bars= 50  NaN: none                                  -> conditions evaluated
```

`live/pipeline.py::_SymbolBuffer` is **in-memory only** and starts
empty on every process start. All Phase D workers started 09:57 IST, so
the earliest any symbol can even *evaluate* its entry conditions is
**≈10:47 IST** (50 × 1m bars).

**Conclusion: zero signals is expected and mechanically necessary, not
a bottleneck, not a defect, and not evidence about the strategy.**

**Disclosed consequence:** an intraday worker restart discards 50
minutes of warmup. This is a known, previously-documented property
(`_SymbolBuffer` is not warm-started from history), confirmed live
today across four phase restarts.

---

## 3. LLM forensics

**Status: the LLM is NOT in the live trading path. REAL.**

| Probe | Result |
|---|---|
| Running worker command lines | all 15 include `--no-ai-explanation` (REAL, read from `Win32_Process`) |
| Ollama reachable right now? | **No** — `OllamaUnavailableError` at `localhost:11434` |
| Fleet behaviour with Ollama down | 335 bars processed, zero errors, zero degradation |
| LLM modules loaded by the live path | `import live.pipeline, live.prediction_recorder, live.critic_gate, live.dhan.market_data_source, paper.engine, risk.engine, strategy.baseline, critic.engine` → **`llm*`/`agents*`/`langchain*`/`ollama*` = NONE** |
| `decision_engine.engine` (the only module containing an LLM call) | **not imported** by the live path |

> **"If I disconnect Ollama right now, what breaks?"**
> **Nothing in the live trading path — it is already disconnected and
> nothing is broken.** What would break: the `analyze` and `review` CLI
> commands (fail clearly by design), and the optional AI summary /
> narrative in `research` / `decide`, which degrade to deterministic
> output.

> **"What useful intelligence does the LLM provide that deterministic
> code does not?"**
> **In the live trading path: none.** It is architecturally excluded —
> the live path imports only deterministic pieces of `decision_engine`
> (`DecisionLabel`, `RiskContext`, `compute_confidence`).

No LLM calls were added to improve this answer.

---

## 4. Global market intelligence

**Status: NOT IMPLEMENTED as a live capability.**

Repository-wide search for global instruments found **no** Dow, Nikkei,
Hang Seng, Shanghai, European indices, Treasury yields, DXY, Brent/WTI,
or gold anywhere. The only global tickers present are:

- `^GSPC` — used in `quant_research/` as the benchmark for **US-listed**
  symbols (`^NSEI` for `.NS`/`.BO`), not as global context for Indian stocks.
- `^IXIC` — appears only as a *description* of an archived research
  hypothesis (`H_TRANSMISSION_001`) in `strategy/hypothesis_registry.py`.

Nothing global was called, retrieved, stored, or used today.

---

## 5. Indian market context

| Capability | Implemented | Executed today | Used in decision |
|---|---|---|---|
| NIFTY 50 benchmark (`^NSEI`) trend + volatility regime | YES (`market_intelligence/regime.py::compute_benchmark_context`, wired into `live/critic_gate.py`) | **NO** | **NO** (see below) |
| Scanner evidence for the symbol | YES (`market_intelligence.scanner.run_scan`, wired into `critic_gate`) | **NO** | — |
| NIFTY sector indices (`^NSEBANK`, `^CNXIT`, `^CNXAUTO`, `^CNXPHARMA`, `^CNXFMCG`, `^CNXMETAL`, `^CNXREALTY`, `^CNXENERGY`, `NIFTY_FIN_SERVICE.NS`) | YES (`NIFTY_SECTOR_INDICES`) | **NO** | **NO — not wired to the live path at all** |
| India VIX (`^INDIAVIX`) | YES (`regime.py`) | **NO** | **NO — not wired to the live path** |
| SENSEX / BANK NIFTY as live context | Only `^NSEBANK` via sector map (not live-wired) | NO | NO |
| Market breadth / advance-decline | YES (`regime.py`, scan-derived) | **NO** | **NO — not wired to the live path** |
| FII/DII flows, INR, crude sensitivity, domestic macro/news | **NOT IMPLEMENTED** | — | — |

**Why nothing executed:** `CriticGate._refresh_if_needed()` — which
performs the scan + benchmark fetch — is called **only from inside
`CriticGate.evaluate()`**, and `evaluate()` is only called when a signal
exists. Zero signals ⇒ **zero context fetches**.

**Filesystem proof (REAL):**

```
find data/market -newermt "2026-09-16 00:00"   -> (empty)
data/scanner.db        last modified 2026-09-15 21:42
data/market_regime.db  last modified 2026-09-15 21:52
```

No market-data cache write, no scan, and no regime computation occurred
today.

**Even when it does run, it cannot change a trade.** The critic's
`REGIME_CONFLICT` check is `severity=CriticCheckSeverity.WARNING`, which
yields a `DOWNGRADE` verdict, and
`BLOCKING_VERDICTS = (REJECT, INSUFFICIENT_EVIDENCE)` — `DOWNGRADE` is
not blocking. **Market context is advisory only; it has no decision
authority in the live path.**

---

## 6. Market regime

**Status: IMPLEMENTED, NOT EXECUTED TODAY.** No regime value exists for
today — `market_regime.db` untouched since 2026-09-15 21:52, and no
`regime`/`scan` command has been run. Nothing invented to fill the gap.

---

## 7. Dashboard cross-check — two real defects found

### Defect 1 — Fleet tab reported a healthy fleet as unhealthy (FIXED)

**Finding:** the Fleet tab showed `0 / 15 HEALTHY` for a continuously
healthy fleet.
**Evidence (REAL):** sampled live against the running fleet —
`0 / 15 → 0 / 15 → 13 / 15 → 15 / 15 HEALTHY` within 36 seconds, while
all 15 workers had zero gaps, zero disconnects and 100% fresh bars.
**Severity:** MEDIUM (misleading in exactly the situation the tab exists for).
**Root cause:** `fleet_page()` required `data_label in ("CONNECTED","LIVE")`.
`_data_health_label` grades any feed older than 30s as `DEGRADED` — correct
as a conservative display badge, but the fleet runs `--interval 1m`, where a
30-60s age is the *normal* gap between bars. So every symbol was counted
unhealthy for roughly the second half of each minute.
**Fix:** count `DEGRADED` as healthy in the tally (data *is* arriving) while
still displaying the honest `DEGRADED` badge; `STALE`/`DISCONNECTED`/
`RECONNECTING`/`SOURCE_UNAVAILABLE`/`NOT AVAILABLE` remain unhealthy.
**Validation:** two regression tests added and mutation-tested (old criterion
reintroduced → new test failed → fix restored → passes); verified against the
live fleet: stable `15 / 15 HEALTHY` across three samples spanning a full
bar-gap cycle. Commit `1ee3ace`.

### Defect 2 — Dashboard's primary tabs do not show the running fleet (OPEN, disclosed)

**Finding:** Overview / Signals / Portfolio / System read the **fixed
default** workstation databases (`data/live_sim_trading.db`,
`data/live_state.db`), not the fleet's per-symbol `runtime/<SYMBOL>/`
stores. Only the Fleet tab is fleet-aware.
**Evidence (REAL):** with the 15-symbol fleet running, the Overview
watchlist rendered **AAPL, INFY.NS, RELIANCE.NS, TCS.NS — all STALE**
(rows dated 2026-09-07 and 2026-09-15), while
`runtime/RELIANCE.NS/state.db` held today's live row
(`DHAN / LIVE / CONNECTED / last_price=1250.20`).
**Severity:** MEDIUM. Mitigated — not fabricated: every stale row is
badged `STALE` and the page-wide banner says *"no active live session
appears to be running"*, so the dashboard is misleading **by omission**,
never by inventing data.
**Root cause:** architectural. The dashboard predates the per-symbol
runtime-dir fleet model; `live/workstation.py` resolves one fixed DB pair.
**Fix:** NOT attempted during the live session — pointing the primary tabs
at a per-symbol runtime dir is a real architectural change to
`live/workstation.py`'s path resolution, out of scope mid-session and
explicitly outside this mission's mandate.
**Recommended before the next session:** either teach the dashboard to
aggregate `runtime/<SYMBOL>/` stores, or make the tabs state plainly which
database they are reading.

---

## 8. Live intelligence status table

| Capability | Implemented | Executed Today | Real Data | Used in Decision | Evidence |
|---|---|---|---|---|---|
| NSE live data (Dhan) | YES | **YES** | **YES** | **YES** | 335 bars, 100% fresh, 15 symbols, zero gaps |
| BSE data | PARTIAL (instrument/wire mapping only) | NO | NO | NO | no BSE symbol subscribed |
| Yahoo (historical/research) | YES | **NO** | — | NO | zero `data/market` writes today |
| Global markets | **NO** | NO | NO | NO | no global tickers in source |
| Indian market context (NIFTY/sector/VIX/breadth) | PARTIAL (NIFTY benchmark + scan wired; sector/VIX/breadth not) | **NO** | NO | **NO** (WARNING → DOWNGRADE, non-blocking) | lazy behind `evaluate()`; zero scans today |
| Market regime | YES | **NO** | NO | NO | `market_regime.db` untouched since 09-15 |
| Technical indicators | YES | **YES** | **YES** | **YES** | computed per bar; `sma_50` NaN until 50 bars |
| Strategy (`trend_momentum_baseline`) | YES | **YES** (evaluated every bar) | **YES** | **YES** | returned `None` at warmup guard on all 335 bars |
| Critic (`CriticGate`) | YES | **NO** | NO | NO | constructed per worker; `evaluate()` never called |
| Risk engine | YES | **NO** | NO | NO | never reached (no signal) |
| LLM | YES (research paths only) | **NO** | NO | **NO** | Ollama down; zero LLM modules loaded |
| Prediction recording | YES | **NO** | NO | — | 0 rows in all 15 ledgers |
| Prediction resolution | YES | **NO** | NO | — | 0 evaluations; cadence not yet reached |
| Paper execution | YES | **NO** | NO | — | 0 trades |

---

## 9. Process & resource forensics (REAL, 10:20 IST)

A process census initially looked alarming — 30 processes matching
`paper-live` when 15 were expected — and was run down rather than
assumed benign:

```
real interpreters (>50MB):  15
launcher stubs   (<=50MB):  15
distinct symbols among real: 15
supervisor processes:         2  (same stub+real pair)
```

**Not orphans.** On Windows, `venv/Scripts/python.exe` is a small
launcher that spawns the real interpreter as a child; both carry the
same command line. Every pair shares one parent (the supervisor, PID
14448) and **all 30 were created at 09:57:47** — the Phase D launch
instant. **Zero processes survived from Phase A/B/C**, independently
confirming those phases' `shutdown_fleet()` terminations were clean and
left no orphaned workers competing for the same per-symbol databases.

Real resource figures for a 15-symbol 1-minute fleet:

| Metric | Value |
|---|---|
| Total fleet RSS | **≈ 2,958 MB (~2.9 GB)** |
| Mean per-worker RSS (real interpreter) | **≈ 193 MB** |
| Logical workers | 15 (1 per symbol, verified distinct) |
| OS processes | 32 (15 workers × 2 + supervisor × 2) |

At ~193 MB per worker, memory is the binding constraint on fleet width
on this machine, not CPU or the Dhan connection count.

---

## 10. Post-warmup re-verification and the OpenAI advisory-layer addition (REAL, 10:30–10:47 IST)

**A third real defect was found and fixed: fleet-summary's own BARS
column was itself wrong**, and it directly affected trust in the
warmup-completion evidence below.

`live/fleet_summary.py::parse_session_log_counts` counted every `bar#`
line in the WHOLE `session.log` file. That file is append-only and
accumulates across every separate `fleet-supervise` launch on the same
calendar day — today's own 4-phase scale-up rehearsal (A→B→C→D)
restarted RELIANCE.NS/TCS.NS's workers multiple times before the main
Phase D session began. But `live/pipeline.py`'s in-memory
`_SymbolBuffer` (the actual indicator input) resets to empty on every
restart. Result: at 10:37 IST, `fleet-summary` reported RELIANCE.NS/
TCS.NS at **50 bars** (cumulative across the day's four launches) while
the real, currently-running Phase D process — the only one whose buffer
matters for `sma_50` — had only reached **42 bars**. Every OTHER symbol,
launched only once (Phase D), was correctly reported. This was caught
by manually diffing the log's own `RUNTIME DIR:`/`MARKET SESSION:`
launch banners against the reported bar count, not assumed.

**Fixed** in `live/fleet_summary.py` (read-only reporting code — never
`live/pipeline.py`, never the trading path itself): only count lines
after the most recent `RUNTIME DIR:` banner, i.e. only what the
currently-running process has actually buffered. Two new regression
tests (a synthetic multi-restart log, and a backward-compatibility case
with no restart marker at all), mutation-tested (reverted the
truncation, confirmed the new test failed with `7 != 2`, restored it).
**Live re-verification**: immediately after the fix, all 15
simultaneously-launched symbols reported the identical real value (44,
then 48, then 50 as the session progressed) instead of the previous
skewed, restart-history-dependent numbers. Committed as a standalone
fix, pushed, not yet merged to `main`.

**True warmup completion, verified with the corrected metric**: all 15
symbols reached exactly 50 bars simultaneously at **10:47:31 IST**
(they were all launched together at 09:57:51 IST, so this is expected —
50 bars × ~1 bar/min ≈ 50 min). At that moment:

- `SIGNALS` and `TRADES` were still **0** for all 15 symbols.
- `grep -riE "SIGNAL DETECTED|CRITIC|RISK "` across every symbol's
  `session.log` found nothing new (the one match, ITC.NS's `SAFE_STOP`,
  is the same pre-existing Phase C entry already covered in §7/§9 of
  this report — not a new event).
- Every symbol's `predictions.db` still had **0 rows**.
- Zero new `[GAP DETECTED]`/`FEED DISCONNECTED` events fleet-wide.
- 15 real worker interpreters (>50MB RSS) confirmed still alive.

This is now a **stronger** result than before warmup: `sma_50` is
genuinely non-NaN and the strategy's NaN guard is genuinely passing, yet
its trend/momentum/breakout entry conditions still are not being met by
today's actual price action. Zero signals after warmup is a legitimate
"no candidate" outcome from the deterministic strategy, not a warmup
artifact — the same honest "PREDICTION PATH NOT EXERCISED BY LIVE
SIGNAL — mechanism verified by historical/integration tests" conclusion
from §1 stands, now on firmer ground.

**Separately, this session also added the OpenAI advisory-intelligence
provider** (a distinct, explicitly-scoped follow-up mission), entirely
inside the existing `llm.provider` abstraction and never touching the
live trading path:

- `core/config.py`: `AI_PROVIDER`/`OPENAI_*` env-var overrides (Settings
  previously had none at all); `OPENAI_API_KEY` deliberately never
  stored in `Settings`, read from the environment only at call time.
- `llm/provider.py`: `_create_openai_chat_model` (`langchain_openai.
  ChatOpenAI`, same `with_structured_output()` interface every existing
  caller already uses), `check_openai_availability()`, and a
  provider-agnostic `check_llm_availability()` dispatcher now used by
  all 5 existing call sites (decision narration, signal explanation,
  research summaries, decision review, `analyze`).
- `llm/budget.py` (new): a SQLite-backed call budget/audit ledger —
  hourly cap (10), per-session cap (30), 20s minimum interval, 4000-char
  max input — the single choke point every real OpenAI call passes
  through, wired into `agents.analyst.invoke_structured`.
- `main.py ai-health` (new command): configuration + a free
  `models.retrieve()` connectivity check, plus an opt-in `--smoke-test`
  that spends one real minimal completion.
- Dashboard System tab: new **AI INTELLIGENCE STATUS** panel (provider,
  model, AVAILABLE/UNAVAILABLE, calls today, last call) — reads
  `llm/budget.py`'s real ledger, never a static claim; never renders the
  key.

**Real evidence, not simulated**: `ai-health` reached `api.openai.com`
with a genuine HTTP 200 (2843ms) and a genuine `gpt-4o-mini` structured
completion (2676ms) via `--smoke-test`, both recorded to the ledger.
Immediately re-running `--smoke-test` was correctly **rejected** by the
20s minimum-interval budget gate without spending a second completion —
the rate limiter is real, not just configured. This advisory layer
remains **inactive by default** (`AI_PROVIDER`/`OPENAI_ENABLED` unset)
and was never wired into any of the 15 live workers — Phase 9's own
explicit caution ("do NOT immediately connect the LLM to every worker")
was honored; today's zero organic candidates gave no real trigger to
integrate it into the live path, so that remains a designed-but-not-yet-
activated boundary, documented as a known limitation rather than forced.

---

## 11. Honest summary

The **data plane** is genuinely working: 15 independent workers, real
Dhan WebSockets, 335 real bars, 100% fresh, zero gaps, zero
disconnects, zero cross-symbol contamination.

The **intelligence plane** was almost entirely **not exercised** today —
not because it is broken, but because it sits downstream of a signal
that (correctly) never fired during indicator warmup. Critic, risk,
prediction recording, prediction resolution, paper execution, market
context and regime all remain **mechanism-verified by tests, not
live-verified today**.

The **LLM contributes nothing to live trading**, by design, and this was
confirmed empirically rather than assumed.

Two real dashboard defects were found; one is fixed and validated
against the live fleet, one is disclosed with a recommended fix.

**Nothing about today's session says anything about strategy
profitability.** The frozen `NO DEMONSTRATED EDGE` verdict is unchanged
and was not revisited.
