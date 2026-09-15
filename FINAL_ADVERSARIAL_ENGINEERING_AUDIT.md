# Final Adversarial Engineering Audit — Trading Intelligence Platform

**Date**: 2026-09-15, 17:00–18:00 IST (after NSE/BSE market close — live tick
reception could not be exercised this session; connectivity was).
**Auditor**: Claude (autonomous), continuing directly from the prior
"multi-symbol hardening pass" mission (commit `bd85f04`, merged to `main`).
**Scope**: Independent re-verification of prior claims plus new forensic work
across data sourcing, provenance, LLM usage, security, concurrency,
deployability, reliability, and product/market positioning, per the
21-section brief this document answers.

Evidence labels used throughout, per this project's own established
convention: **[VERIFIED-LIVE]** (a real external call made this session),
**[VERIFIED-TEST]** (a real automated test, cited by path, run this session),
**[VERIFIED-CODE]** (confirmed by direct source reading this session),
**[CACHED/HISTORICAL]** (real market data, not fetched live this session),
**[CITED]** (a claim from an earlier session's own [VERIFIED-*] evidence,
independently re-checked for continued validity rather than re-derived from
scratch), **[SIMULATED]** (mock/deterministic test double), **[ASSUMED]**
(plausible, not independently confirmed this session), **[UNVERIFIED]**
(explicitly could not be confirmed — never presented as PASS).

---

## 1. Baseline

- Branch `final-product-hardening`, in sync with `origin`; `main` in sync at
  `bd85f04`. Working tree clean except the long-standing, confirmed-zero-diff
  `scheduler/store.py` CRLF artifact. **[VERIFIED-LIVE]**
- Python 3.14.4 (dev venv). Key dependencies: pandas 3.0.3, numpy 2.4.6,
  yfinance 1.4.1, requests 2.34.2, websocket-client 1.9.0, pydantic 2.13.4,
  langchain 1.3.9 / langchain-ollama 1.1.0 / chromadb 1.5.9, pytest 9.1.1.
  `requirements.txt` unchanged since the last clean-install verification
  (Phase 19, this campaign) — that evidence remains valid. **[VERIFIED-LIVE]**
- Full regression suite re-run this session: see §18 for the final count: the
  starting point (before this audit's own mutation-test cycle) was **2500
  passed, 0 failed**, confirmed in the immediately prior mission and
  independently re-confirmed by re-running the concurrency/security-relevant
  subset fresh (203 tests) plus the full failure-injection matrix (117
  tests) during this audit — all green. **[VERIFIED-TEST]**
- No automated mutation-testing framework is installed (`mutmut`/`cosmic-ray`
  both absent) — this project's mutation-testing discipline is manual
  (introduce a real regression, confirm the test fails, revert, confirm it
  passes again), demonstrated throughout this campaign and again in this
  audit (§9). **[VERIFIED-LIVE]**
- Prior reports (`FINAL_PRODUCT_READINESS_REPORT.md`,
  `FINAL_PRODUCT_CAPABILITY_MATRIX.md`, `FINAL_FAILURE_MODE_ANALYSIS.md`,
  53 entries) were read, not trusted blindly — every load-bearing claim used
  in this report was independently re-checked against the actual
  implementation this session (see per-section evidence below).

---

## 2–4. Data source forensics, provenance, real-time audit

### NSE via Dhan

- Real path traced: `live/dhan/market_data_source.py::DhanMarketDataSource`
  resolves symbols via `live/dhan/instruments.py::DhanInstrumentMap`
  (downloaded from Dhan's public scrip-master CSV, cached at
  `data/dhan/scrip-master.csv`) to a `(exchange_segment, security_id)` pair,
  subscribes over a real WebSocket (`live/dhan/wire.py`'s binary protocol),
  and reassembles ticks into bars via `CandleBuilder`.
- **Real, live connectivity re-verified this session** (`main.py
  readiness-check --deep`, credentials sourced from `.env` into the same
  shell invocation only, never printed): real HTTP 200 from `/fundlimit`
  (0.45s round-trip) and a real WebSocket `CONNECTED` state.
  **[VERIFIED-LIVE]**, timestamped 2026-09-15 17:12 IST.
- **Live tick reception could not be exercised this session** — the market
  closed at 15:30 IST and this check ran at 17:12 IST; the tool's own output
  correctly reported `NO_DATA within the 20s budget` and explained why
  (a freshly-subscribed symbol's first candle needs up to 60s even
  mid-session, let alone after close) rather than presenting silence as
  either success or failure. Live tick reception WAS previously verified on
  2026-09-15 during real market hours (322 real bars,
  `docs/LIVE_MARKET_VALIDATION_REPORT_2026-09-15.md`) — that evidence
  stands, re-cited, not re-derived. **[CITED]** + **[VERIFIED-LIVE]** for
  connectivity only, today.
- Duplicate/out-of-order bars, stale suppression, reconnect handling: all
  have real automated test coverage (`CandleBuilder`'s rejection counters,
  `live/freshness.py::FreshnessPolicy`, `live/gap_monitor.py` — the last one
  new this campaign, closing a real ~15-minute silent gap observed live on
  2026-09-15). Re-run fresh this session: **[VERIFIED-TEST]**
  (`tests/test_gap_monitor.py`, `tests/test_dhan_market_data_source.py`, all
  passing).
- Clock skew: **[VERIFIED-LIVE]**, measured fresh this session at **+6.2s**
  (WARNING band, >5s) via a real HTTP `Date` header comparison against
  Dhan's own server — consistent with the project's own memory record
  ("resynced from ~-130s to ~+7s between 2026-09-07 and 2026-09-14"). Real,
  non-fatal, already-classified and already-displayed to the operator; never
  silently absorbed.

### BSE via Dhan — **PARTIALLY IMPLEMENTED, NEVER LIVE-VERIFIED**

Per this audit's own explicit instruction not to assume BSE works because
NSE does: it does not, automatically.

- Exchange-segment mapping (`BSE_EQ`/`BSE_FNO`/`BSE_CURRENCY`), the wire
  protocol's byte-to-segment table, and `.BO`-suffix Yahoo-symbol resolution
  are all genuinely implemented in `live/dhan/instruments.py` and
  `live/dhan/wire.py`, and unit-tested against a realistic fixture CSV
  (`tests/test_dhan_instruments.py::test_lookup_bse_equity_is_a_different_security_id`,
  `test_lookup_yahoo_symbol_bo_suffix_maps_to_bse`, `test_underlying_symbols_with_active_derivative_respects_exchange_filter`)
  — genuinely correct code, not a stub. **[VERIFIED-TEST]** (fixture-based).
- **No real BSE WebSocket subscription or real BSE tick has ever been
  exercised** in this campaign's history — both real Dhan sessions
  (2026-09-07, 2026-09-15) used NSE symbols only. Confirmed by grepping
  every `docs/*.md` report for "BSE"/"​.BO" — zero live-session hits outside
  incidental Yahoo-aggregation mentions.
- **Classification: UNVERIFIED (live), VERIFIED (unit/fixture level).** Not
  a defect — the mapping logic is sound — but a real, disclosed gap in
  operational evidence. Recommendation: if a BSE symbol is ever added to a
  live session, treat its FIRST run as a fresh connectivity check, not an
  assumed extension of the NSE evidence.

### Yahoo Finance

- Real path traced: `market/data_provider.py::YahooFinanceProvider.fetch_ohlcv`
  wraps `yf.Ticker(...).history(...)`; **any exception or empty frame raises
  `MarketDataError`** — confirmed by direct code reading, there is no
  fallback-to-synthetic-data branch anywhere in this function.
  **[VERIFIED-CODE]**
- `backtesting/cache.py::CachedMarketDataProvider` — real, disclosed design:
  **on a cache hit, the cached range is returned unconditionally, with "no
  freshness/invalidation logic"** per its own docstring (line 56). This
  means once a symbol's CSV cache exists, a live Yahoo outage is invisible
  to a caller of `fetch_ohlcv()` — it simply gets the cached bars, with no
  error and no inline "this is 3 days old" flag on the returned object.
  Freshness IS still recoverable, but only via a SEPARATE tool
  (`cache-status --shallow-below-bars`, reading the `.meta.json` sidecar's
  `retrieved_at`), not attached to the data itself. **This applies to the
  historical/backtest/research path only** (`backtest`, `scan`,
  `daily-report`, `predict`) — the live Dhan paper-trading path uses an
  entirely separate freshness mechanism (`FreshnessPolicy`, live-verified
  above) and is not affected by this. **[VERIFIED-CODE]**, a real,
  already-partially-disclosed characteristic, correctly scoped here rather
  than conflated with the live-trading safety path.
- Malformed/corrupted cache files: raise a clear, actionable
  `MarketDataError` naming the file and the recovery step ("delete the file
  to refresh it") rather than a confusing pandas parser traceback — a real,
  previously-fixed defect (cycle 14), re-confirmed present in the current
  source. **[VERIFIED-CODE]**

### Provenance

- One value traced end-to-end: a Dhan tick →
  `live/dhan/wire.py::parse_ticker_packet` (security_id, LTP, exchange
  timestamp) → `CandleBuilder` (bucket, OHLC aggregation) → `Bar`
  (symbol, timestamp, OHLCV) → `LiveSimPipeline.process_next()` → strategy
  indicators → `Signal`/`Decision` → (if `--record-predictions`)
  `PredictionRecord` (symbol, entry price, horizon, generated_at).
- **What IS tracked per observation**: symbol, exchange (via the
  security_id → segment mapping), timestamp (both bar timestamp and, via
  `live/gap_monitor.py`'s new observability this campaign, an implicit
  receive-time signal through gap detection), freshness (`is_fresh`,
  printed on every bar line), cached-vs-live status (the `SOURCE: MOCK` /
  `SOURCE: DHAN` banner printed at every session start, and `STATUS:
  SIMULATED` always shown, never omitted).
- **What is NOT explicitly tracked as a first-class field**: a per-bar
  receive-timestamp distinct from the bar's own (exchange-derived)
  timestamp, and provider/instrument-ID are not attached to the persisted
  `PredictionRecord`/`Trade` rows themselves (they are re-derivable from the
  session's own startup banner and the `runtime/{SYMBOL}/` directory it ran
  in, but not stored per-row). **Genuine, disclosed auditability gap** — not
  fixed this session: adding a receive-timestamp column to every
  persisted row would touch schema on `paper/store.py`/`predictions/store.py`
  (both outside the 8 sacred files, but not a localized fix — a real schema
  migration across two stores) without a demonstrated defect it closes
  (the gap-monitor system already reconstructs delivery timing from process
  logs). Recorded here as a legitimate, scoped future item, not implemented
  speculatively.

---

## 5. Market calendar / hours

- `live/dhan/market_session.py::current_market_session` derives session
  state from real IST wall-clock time against NSE/BSE's published cash-
  market hours, with an explicit `holiday_calendar_consulted: bool` flag.
- **No authoritative, automatically-updated NSE/BSE holiday feed exists**
  (confirmed: `scheduler/config.py`'s `holidays` defaults to an empty
  tuple) — consistent with this project's own established finding that
  NSE/BSE/SEBI expose no official holiday API. This is **honestly
  surfaced, not silently assumed**: every relevant CLI banner
  (`paper-live`, `dashboard`, `readiness-check`) prints "does NOT account
  for exchange holidays -- pass --schedule-config to cross-check" whenever
  no calendar was supplied, verified fresh this session via a real
  `readiness-check --deep` run showing exactly this message. **[VERIFIED-
  LIVE]**
- **Classification: CORRECT AND HONEST, with a real, disclosed manual-input
  dependency** — not a defect.

---

## 6. LLM forensic audit

Traced actual runtime execution, not assumed from the module's existence.

- **Only Ollama is implemented**; NIM and OpenAI provider branches both
  `raise NotImplementedError` (`llm/provider.py`). **[VERIFIED-CODE]**
- **Real, fresh check this session**: Ollama is **NOT running** in this
  environment (`OllamaUnavailableError: ... not reachable at
  http://localhost:11434`). **[VERIFIED-LIVE]** — the LLM-explanation
  feature is DEGRADED right now, in practice, not merely in theory.
- **Where it is actually invoked in a trading-adjacent path**: exactly one
  place — `main.py::_try_ai_explain`, called from inside `paper-live`'s
  approval flow, ONLY when a signal reaches `PENDING_HUMAN_APPROVAL` and
  `--no-ai-explanation` was not passed.
- **Type-level (not just prompt-level) guarantee it cannot influence
  trading**: `agents/signal_explainer.py::explain_signal` returns a
  `schemas/explanation.py::SignalExplanation` — read directly, its ONLY
  fields are `supporting_evidence: list[str]`, `contradicting_evidence:
  list[str]`, `narrative: str`. **There is no field the model could
  populate that would change an entry, stop, target, quantity, or
  approval status** — this is enforced by the Pydantic schema itself, not
  merely a prompt instruction the model could ignore. **[VERIFIED-CODE]**,
  a genuinely strong architectural finding.
- **Failure handling**: `_try_ai_explain` wraps its entire body in a broad
  `except Exception: ... return None`, explicitly commented "AI explanation
  must never block approval." **[VERIFIED-CODE]**. Directly consistent
  with the real observed behavior today (Ollama down, and the rest of the
  system is unaffected — confirmed by the same readiness-check run showing
  every other component healthy).
- **Malformed-output/timeout handling**: `agents/analyst.py::invoke_structured`
  retries once, validates the LLM's return value is an actual instance of
  the requested Pydantic schema (not merely "looks parseable"), and raises
  a typed `AgentOutputError` rather than ever returning unstructured text.
  Timeout is enforced via `client_kwargs={"timeout":
  settings.ollama_timeout_seconds}` on the underlying `ChatOllama`/
  `OllamaEmbeddings` client. **[VERIFIED-CODE]**
- **Latency/token/cost observability**: **absent** — grepped for
  `token_usage`/`usage_metadata`/`latency_ms` across `llm/`, `agents/`,
  `mcp_server/`: zero hits. A real, minor, disclosed gap (LOW severity —
  Ollama is local/free and every call is already non-blocking and
  timeout-bounded, so the operational risk of not measuring this is low).
  **Not fixed this session**: this is a nice-to-have observability
  enhancement, not a defect — the underlying behavior is already correct
  and already covered by the "never blocks" guarantee above; adding new
  logging absent a demonstrated failure it would have caught is exactly
  the kind of unrequested hardening this campaign's own standing
  instruction says to avoid.
- **Separate deterministic-vs-LLM agent surface**: `agents/analyst.py` also
  powers the `analyze`/`research`/`review`/`decide` CLI commands (multi-
  agent market analysis) — these are explicitly research/explanation tools,
  never in the `paper-live` execution path, and were not the subject of new
  verification this session (no change since the last campaign's own
  characterization of them; re-confirmed only that they still route through
  the same `invoke_structured` guarantees above).
- **Verdict: the LLM contributes real, but narrow and honestly-scoped,
  value** — plain-language narration of an already-made decision, nothing
  more, with a genuine type-level guarantee it cannot become anything more
  without an explicit schema change. It is not "decorative" in the
  dismissive sense (the narration is real and the architecture around it is
  unusually careful), but it is also not a source of trading intelligence —
  correctly so, by design.

---

## 7–9. End-to-end journey, failure injection, concurrency

- **Full pipeline re-traced by direct code reading**: Market Data (Dhan/
  Yahoo/mock) → `CandleBuilder`/`OHLCV` normalization → `market.indicators`
  → strategy (`trend_momentum_baseline`) → optional `CriticGate` (real
  Dhan sessions only) → `RiskEngine` (two independent checks: at signal
  generation and again at the moment of human approval) → `PaperTradingEngine`
  (fill simulation with real cost model) → `PredictionStore` (opt-in) →
  `predictions/tracker.py` outcome resolution → `learning/profitability.py`
  → CLI reports / dashboard. Every stage above has dedicated, currently-
  passing tests; none were newly re-derived this session (the pipeline
  itself is unchanged since the last campaign's own end-to-end
  verification), but the CHAIN was re-confirmed intact by reading the
  actual call graph fresh, not merely trusting the diagram in a prior
  report. **[VERIFIED-CODE]**
- **Failure injection**: the project's own 110-row executable failure-
  injection matrix (`tests/failure_injection/`) was **re-run fresh this
  session**: **117 passed, 0 failed** — covering Dhan reconnect simulation,
  paper-execution crash-boundary behavior, and matrix-integrity self-checks.
  **[VERIFIED-TEST]**
- **Concurrency**: the highest-value concurrency/security-relevant test
  files (`test_fleet_supervisor.py`, `test_dhan_instruments.py`,
  `test_scheduler_store.py`, `test_approval_security.py`,
  `test_dhan_market_data_source.py`, `test_paper_engine.py`,
  `test_core_sqlite_util.py`, `test_dhan_credential_security.py`) were
  **re-run fresh this session under `-W
  error::pytest.PytestUnhandledThreadExceptionWarning`** (promoting any
  silently-swallowed thread exception to a hard failure): **203 passed, 0
  failed**. **[VERIFIED-TEST]**
- **A real, fresh mutation test was performed this session on the single
  highest-stakes safety property in the codebase**: the cycle-25 TOCTOU
  fix in `live/pipeline.py::approve_pending` (a second kill-switch check
  between the CAS claim and order submission, closing the exact window
  where a human's emergency stop could otherwise be missed by an
  in-flight approval). The check was removed, both of its regression
  tests — including a REAL two-thread, two-independent-SQLite-connection
  concurrency test
  (`test_a_real_concurrent_kill_switch_activation_during_approve_pending_never_creates_an_order`)
  — **correctly failed** (`APPROVED` instead of `KILL_SWITCH_ACTIVE`), the
  fix was restored byte-for-byte (`git diff live/pipeline.py` confirmed
  zero diff afterward), and all 12 `test_approval_security.py` tests
  passed again. This is fresh, independent, adversarial proof — not a
  restatement of a prior cycle's own claim — that this project's single
  most critical safety guard is still genuinely protected by a test that
  would catch its removal. **[VERIFIED-TEST]**, performed 2026-09-15 this
  session.
- No new concurrency defect was found this session. Consistent with the
  STOP-condition instruction ("no reproducible defect exists"), no further
  concurrency rework was attempted beyond the fresh proof above.

---

## 10. Security audit

- **Secrets**: `.env` is gitignored and untracked (confirmed via `git
  ls-files`); a repo-wide grep for hardcoded credential-shaped strings
  (`DHAN_ACCESS_TOKEN=`, `api_key=`, `password=`, `secret=` followed by a
  plausible literal) returned zero hits in tracked source; a full git-
  history search (`git log --all -S "DHAN_ACCESS_TOKEN="`) found no commit
  ever added a literal token, and no `.env` file was ever committed at any
  point in history. **[VERIFIED-LIVE]**, fresh this session.
- **Dependency vulnerability scan** (`pip-audit -r requirements.txt`, real,
  fresh this session): **5 known CVEs in exactly 1 package — chromadb
  1.5.9** (PYSEC-2026-311 / CVE-2026-45829 pre-auth code injection via
  `trust_remote_code`; PYSEC-2026-3813/14/3815, RBAC/cross-tenant
  authorization bypasses). **All five are specific to chromadb's HTTP
  SERVER mode** (`chroma run` / `chromadb.HttpClient`). Grepped the entire
  codebase: **zero references to server mode anywhere** — the only usage
  (`rag/retriever.py`) is `langchain_chroma.Chroma(persist_directory=...,
  embedding_function=...)`, the embedded, in-process, file-persisted local
  client, which never opens a network listener. **Reachability: NOT
  REACHABLE in this project's current usage.** No fixed version is yet
  published upstream (`fix_versions: []`). Every other scanned package
  (langgraph, langchain-core, pydantic, pyyaml, requests, yfinance, pandas,
  ollama, etc.) — zero known vulnerabilities. **[VERIFIED-LIVE]**
- **API/dashboard security**: `dashboard/app.py` exposes 7 routes;
  `/approve`, `/reject`, `/kill-switch/activate`, `/kill-switch/reset` are
  all state-mutating POST endpoints with **no authentication** — confirmed
  by direct code reading, no auth middleware exists anywhere in
  `dashboard/`. Mitigated by a safe default (`--host 127.0.0.1`,
  loopback-only) but **not structurally prevented** — passing `--host
  0.0.0.0` would expose kill-switch toggling and signal approval/rejection
  to anything on the local network with no credential. This is an
  already-documented, deliberately-deferred limitation (single-operator,
  loopback-only threat model) — re-confirmed accurate today, not newly
  discovered, and not fixed this session (adding auth is a real
  architectural addition, not a localized bug fix, and out of this audit's
  "minimal, localized fixes" mandate absent a demonstrated exploit in the
  actual deployed threat model). The `symbol` path parameter on
  `/intelligence/{symbol}` is HTML-escaped on render and passed to a
  parameterized SQL query (`WHERE symbol = ?`) — no injection or XSS path
  found. **[VERIFIED-CODE]**
- **SQL injection**: every user/external-input-adjacent query found uses
  parameterized placeholders (`?`). The only f-string-interpolated SQL in
  the codebase is in `core/sqlite_util.py`'s schema-migration helpers
  (`PRAGMA`/`ALTER TABLE`/`CREATE INDEX` — SQLite has no parameterized-
  identifier syntax) and one `# noqa: S608`-annotated internal table name
  in `paper/store.py`; both take only hardcoded, developer-controlled
  literals at every call site found — never user/external input.
  **[VERIFIED-CODE]**
- **Real-order path**: re-confirmed fresh this session by direct code
  reading — `live/dhan/broker_adapter.py`'s `place_order`/`modify_order`/
  `cancel_order` unconditionally `raise RealOrderPlacementDisabledError`.
  The MCP server (`mcp_server/server.py`, 23 tools) has an explicit
  comment confirming no order-placement tool exists there either. No code
  path anywhere in this session's diff or in the pre-existing source
  bypasses this. **[VERIFIED-CODE]**
- **Docker**: no `Dockerfile`/`docker-compose.yml` exists in the
  repository. Not fabricated as implemented; genuinely **N/A / NOT
  IMPLEMENTED**. Building one was not attempted this session — it is new
  infrastructure, not a fix for a discovered defect, and out of this
  audit's minimal-fix mandate.
- **LLM security**: prompt injection surface is narrow by design — the
  only external text reaching a prompt is already-structured, already-
  validated internal objects (`Signal`, `RiskDecision`, `MarketContext`),
  never raw scraped news/web text fed directly into a decision-relevant
  prompt in the `paper-live` path (the separate `research`/`review`
  commands do ingest news text for LLM summarization, but that output
  similarly cannot reach risk/execution — same type-walling architecture).
  Full independent line-by-line prompt-injection red-teaming of the
  `research` command's news-ingestion path was **not exhaustively
  performed this session** (scope triage) — recorded as **[UNVERIFIED]**
  rather than claimed clean.

---

## 11. Deployability

- Not re-run from a fresh clean-room environment this session (the last
  genuine clean-install verification — a different Python minor version,
  a from-scratch venv, a real multi-command smoke run — was Phase 19 of
  the prior mission, and `requirements.txt` has not changed since:
  confirmed via `git log -- requirements.txt`, last touched at cycle 7,
  long before Phase 19). That evidence is **[CITED]**, re-validated for
  continued applicability rather than re-derived, per this audit's own
  triage under real time constraints.
- Spot-re-verified TODAY in the existing dev environment: `main.py health`
  and `main.py readiness-check --deep` both ran correctly, produced the
  expected DEGRADED-with-clear-reasons status (Ollama down, no ambient
  Dhan credentials), and the `--deep` real-network checks succeeded.
  **[VERIFIED-LIVE]**
- **No Docker packaging** — "could another engineer deploy this without
  understanding the source code?" — **partially**. `INSTALLATION.md`/
  `OPERATIONS_GUIDE.md`/`USER_GUIDE.md` give a real, followable
  pip-install + CLI path (re-confirmed present and current this session),
  but there is no one-command containerized deploy; an operator needs to
  read documentation and run several CLI commands in sequence, not just
  `docker run`.

---

## 12. Long-run reliability

- **[CITED]**, not re-run this session: cycle 34's real, finite (not
  infinite) soak test — 9,000 ticks across 3 symbols through a real
  `LiveSimPipeline`+`PaperTradingEngine`+SQLite — found no thread leak, a
  bounded bar queue that stayed drained, and DB growth proportional to
  work done (77,824 bytes for ~9,000 bars). It DID find the indicator-
  history buffer growing unbounded (2,999 entries/symbol by the end), which
  was subsequently and genuinely FIXED (bounded to 1,000 bars, benchmarked
  3.10x faster / 74.4% less peak memory over 4,000 bars) — see
  `FINAL_FAILURE_MODE_ANALYSIS.md` entry #44, re-confirmed present in the
  current source this session (`live/pipeline.py::_SymbolBuffer`,
  zero-diff sacred file, unchanged and still bounded).
- Explicitly **not** claiming multi-week reliability from this evidence — a
  ~35-minute, single-process soak test does not prove that, and no
  longer-duration test exists.
- **New, not-yet-soak-tested risk surface**: this campaign's own new
  multi-symbol fleet supervisor (`live/fleet_supervisor.py`,
  `fleet-supervise`) launches N independent subprocesses, each with its own
  log file (`runtime/{SYMBOL}/logs/session.log`, opened in APPEND mode with
  no rotation) and its own SQLite stores. **No soak test has been run for
  this specific new surface** — 15 concurrent processes' aggregate memory/
  file-descriptor/log-growth over a multi-hour real session is
  **[UNVERIFIED]**, not assumed safe by extrapolation from the older,
  single-process soak test. This is the single most concrete open question
  for tomorrow's actual session to answer empirically (see §21).

---

## 13. Performance / cost

Real, measured figures (not estimated):

- Dhan REST round-trip: **0.45s** (this session, 2026-09-15 17:12 IST) and
  **0.63s** (2026-09-15 during real market hours, from
  `LIVE_MARKET_VALIDATION_REPORT_2026-09-15.md`) — consistent, real,
  live-verified twice.
- Indicator recompute cost: **~233ms/tick at 3,000 bars/symbol** (cycle
  34's soak test), confirmed to be an accepted, proportional cost at this
  project's real intended scale (1-minute bars, market hours only) and now
  bounded at 1,000 bars specifically to control this (entry #44).
- LLM latency: **not measured** (see §6) — Ollama itself was unreachable
  in every environment probed this session, so no real number could even
  be taken today; this is disclosed as absent rather than estimated.
- No premature optimization performed this session — no measured
  bottleneck materially affecting reliability/deployability was found
  beyond the already-fixed indicator-buffer cost above.

---

## 14. Automated validation

- Confirmed by direct reading that this project's own test-writing
  convention already distinguishes **contract tests** (schema/type
  guarantees, e.g. `SignalExplanation`'s field set), **integration tests**
  (real CLI → real pipeline → real SQLite, e.g.
  `test_run_paper_live_command_records_predictions_end_to_end`), **real-
  provider verification** (`readiness-check --deep`'s real Dhan REST/
  WebSocket calls), and **simulation tests** (`--source mock` end-to-end
  runs) — and does not present mocked-code-returns-what-the-mock-was-
  programmed-to-return as meaningful coverage; this was independently
  spot-checked across `tests/test_fleet_supervisor.py`,
  `tests/test_dhan_instruments.py`, and `tests/failure_injection/` this
  session and found to hold. **[VERIFIED-CODE]**

---

## 15. Market / competitive reality check

Compared honestly against the categories named in the brief, from general
knowledge of the space (not fabricated benchmark numbers):

- **Broker platforms** (Zerodha/Kite, Upstox, Dhan's own apps): not a
  competitor at all — this system deliberately never places a real order.
- **Algo platforms with real execution** (Streak, TradeTron, AlgoTest,
  QuantConnect w/ live brokerage): this project has comparable strategy/
  risk machinery but deliberately stops short of real execution — not
  competing on "deploy live capital," competing (if at all) on "safely
  validate a strategy before anyone risks real capital."
- **Quant research/backtesting frameworks** (backtrader, vectorbt,
  freqtrade, Zipline-successors): the closest real comparison. This
  project's walk-forward validation, regime analysis, Monte Carlo,
  hypothesis registry, and promotion gate are genuinely comparable in
  rigor — arguably MORE disciplined about avoiding p-hacking (explicit
  Bonferroni correction, a frozen and honestly-reported NO-EDGE verdict)
  than most hobbyist or even some commercial backtesting setups, which
  tend to report cherry-picked backtest curves. It is single-strategy,
  single-asset-class (cash equities), Python-code-level (no visual
  builder), with no community or plugin ecosystem — freqtrade in
  particular has all of that PLUS a live user base; this project has
  neither.
- **"AI trading" products**: this space is currently full of marketing
  claims about LLM-driven alpha that mostly do not survive scrutiny. This
  project's own architecture — LLM type-walled out of every numeric
  decision field, verified above at the schema level — is a genuine
  INTEGRITY differentiator versus that category, but it also means the
  "AI" angle is not a sellable hook here: the system is honest that the
  LLM adds narration, not edge.
- **Indian-market (NSE/BSE) focus with a real, working Dhan integration**:
  a genuine, underserved niche — most open-source algo frameworks are
  crypto- or US-equities-first. This is a real, structural point of
  differentiation, independent of strategy quality.
- **What would a user actually pay for, today?** Realistically: the safety
  architecture and evidence discipline are the most defensible asset (a
  team building a real trading system could learn from, or extend, the
  kill-switch/two-stage-risk-check/type-walled-LLM pattern) more than the
  current strategy itself, which has no demonstrated edge and is
  single-strategy/single-timeframe. As a standalone commercial product
  TODAY — no UI, no proven returns, no real execution, no
  community — the case is weak; as an ENGINEERING REFERENCE or a
  FOUNDATION for a future strategy that does demonstrate edge, the case is
  real.

---

## 16. Product / strategy reality check

Three separate questions, kept separate per the mission's own explicit
rule:

- **Engineering** — does the software work? Largely YES, with the specific,
  disclosed gaps in this report (BSE unverified live, no dashboard auth,
  no Docker, no fleet-scale soak test). Freshly re-verified this session,
  not merely re-asserted.
- **Trading strategy** — does it demonstrate positive risk-adjusted
  expectancy? **NO DEMONSTRATED EDGE** — this verdict is **unchanged,
  frozen, and was not re-derived, re-tuned, or revisited this session**,
  per this project's own standing rule and this audit's own explicit
  prohibition on strategy optimization. See `TRADING_STRATEGY_READINESS.md`
  (untouched this session).
- **Product** — is there a valuable product even if the strategy is weak?
  Honestly: the strongest current value is the ENGINEERING
  INFRASTRUCTURE itself (a genuinely safe, well-tested harness for
  validating a strategy without risking capital) — not yet a standalone
  product a typical user would pay for, absent either a demonstrated edge
  or a materially different go-to-market (e.g., positioning as
  infrastructure/tooling rather than a trading product).

---

## 17. Stop conditions applied

Recorded as **NOT VERIFIED** rather than pretending they passed, per the
brief's own instruction:

- BSE live tick reception (§2) — no reproducible way to verify without
  live BSE market hours and an explicit decision to subscribe a real BSE
  instrument, out of this session's safe scope.
- Multi-week (or even multi-day) continuous reliability (§12) — no test at
  that duration exists; not claimed.
- Full LLM prompt-injection red-team of the `research`/news-ingestion path
  (§10) — scoped out under real time constraints this session; the
  narrower, higher-stakes `paper-live` LLM path WAS fully verified.
- A from-scratch clean-room re-install (§11) — not re-run this session
  (the dependency set is unchanged since the last one, Phase 19, so that
  evidence was judged still valid rather than re-derived).

---

## 18. Final verification

1. Full regression suite (`pytest tests/ -q`), re-run in full after the
   mutation-test cycle in §9: **2500 passed, 0 failed** (442.17s), one
   unrelated third-party `DeprecationWarning` from `chromadb`'s
   OpenTelemetry integration (Python 3.16 forward-compat notice, not a
   test failure). Identical count to the prior mission's own final
   regression, confirming the mutation-test-and-restore cycle in this
   audit left zero residual change. **[VERIFIED-TEST]**
2. Mutation test: one fresh, real, adversarial mutation test performed on
   the highest-stakes safety property this session (§9) — caught, fix
   restored, `git diff` confirmed zero residual change.
3. Security scan: `pip-audit` run fresh — 1 package flagged, confirmed
   not reachable in this project's actual usage (§10).
4. Clean-install validation: not re-run fresh; prior evidence confirmed
   still valid (dependency set unchanged).
5. Docker validation: N/A, no Docker packaging exists.
6. Relevant integration tests: failure-injection matrix (117) and
   concurrency/security subset (203) re-run fresh, all green.
7. Real read-only providers: Dhan REST + WebSocket connectivity
   re-verified live this session; Yahoo path verified by code reading
   (no live fetch attempted this session — cached data already present
   locally covers the relevant tests).
8. No real-order path enabled: re-confirmed by direct code reading,
   `live/dhan/broker_adapter.py` and the 8 sacred files all zero-diff.
9. `git diff` verified clean at every mutation-test step this session.
10. No secrets entered the repository: confirmed via `git status`,
    `git ls-files`, and a repo + history secret scan, all clean.
11. Documentation: this report is new; no other doc required a change
    this session (the prior mission's own doc updates already cover the
    fleet-supervisor work).
12. Repository cleanliness: `git status --short` clean except the
    long-standing benign CRLF artifact on `scheduler/store.py`.

---

## 19. Findings table

| Finding | Evidence | Severity | Root Cause | Fix | Validation | Status |
|---|---|---|---|---|---|---|
| chromadb 1.5.9 has 5 known CVEs (server-mode auth/RBAC/code-injection) | `pip-audit` fresh run; codebase grep shows only embedded `Chroma(persist_directory=...)` usage, zero server-mode references | INFORMATIONAL (would be CRITICAL if reachable) | Upstream dependency; no fix version published yet | None needed — not reachable in current usage; documented here for future re-check if server mode is ever added | Reachability confirmed via full-codebase grep | CLOSED (disclosed, not exploitable as deployed) |
| BSE support via Dhan has never been live-verified | Grep of every `docs/*.md` live-session report; only NSE symbols used in both real sessions (2026-09-07, 2026-09-15) | MEDIUM (operational unknown, not a code defect) | Unit/fixture coverage exists; no live BSE session has ever been run | None — correctly scoped as an evidence gap, not a bug to fix | Instrument-mapping unit tests re-run fresh, all pass | OPEN — disclosed, requires a dedicated future BSE live check before relying on it |
| Fleet supervisor (`fleet-supervise`) has no multi-hour soak-test evidence for 15 concurrent processes | New code this campaign; the only prior soak test covered a single in-process pipeline, not N subprocesses | MEDIUM | Genuinely new capability, not yet exercised at real duration/scale | None — recommend treating tomorrow's real session as the first such data point, with `fleet-summary` used to inspect resource state afterward | N/A (not yet run at scale) | OPEN — first real evidence expected tomorrow |
| Dashboard state-mutating routes (`/approve`, `/reject`, `/kill-switch/*`) have no authentication | Direct code reading, `dashboard/app.py` | LOW (mitigated by loopback-only default) | Deliberate scope decision (single-operator threat model) | None — re-confirmed as an accepted, disclosed limitation; out of this audit's minimal-fix mandate | Re-confirmed the `--host 127.0.0.1` default is still in place | ACCEPTED LIMITATION (unchanged) |
| LLM latency/token usage is not measured anywhere | Grep across `llm/`, `agents/`, `mcp_server/` | LOW | Never built; Ollama is local/free, so cost-tracking was never a priority | None — no defect in underlying behavior (already non-blocking, already timeout-bounded) | N/A | INFORMATIONAL, not fixed (no demonstrated need) |
| Per-row provenance (receive-timestamp, provider/instrument-ID) is not persisted on `Trade`/`PredictionRecord` rows | Direct schema reading of `paper/store.py`, `predictions/store.py` | LOW | Never built; re-derivable from session logs/banners today | None — a real schema migration across two stores, not a localized fix, absent a demonstrated defect it closes | N/A | DISCLOSED, not implemented this session |
| The cycle-25 TOCTOU kill-switch guard is still genuinely protected | Fresh mutation test this session: removed, both regression tests (incl. a real 2-thread/2-connection race test) failed correctly, restored, `git diff` confirmed zero residual change | — (negative-result / re-verification finding) | N/A — behavior already correct | N/A | `tests/test_approval_security.py`, 12/12 pass post-restore | VERIFIED (re-confirmed, not a new finding) |
| Real-order placement remains structurally impossible | Direct code reading, `live/dhan/broker_adapter.py`, MCP server tool surface | — | N/A — behavior already correct | N/A | 8 sacred files confirmed zero-diff | VERIFIED |
| No secrets in source or git history | Repo-wide grep + full history search | — | N/A | N/A | Clean scan, fresh this session | VERIFIED |

---

## Answers to the mandatory questions

**1. Does the system actually work end-to-end?**
**PARTIALLY** (in the precise sense the evidence supports): the full
Market Data → Decision → Risk → Paper Execution → Prediction →
Resolution → Report chain is real, exercised by real tests, and was
exercised live (322 real Dhan bars, 2026-09-15) — but no live-session
signal has yet propagated all the way through prediction resolution with
a live-generated trade (the 2026-09-15 session generated zero signals,
an honest null result, not a gap in the machinery). The machinery is
YES; a full live-signal walk of every stage in one session is NOT YET
observed.

**2. Are we genuinely receiving the data we think we're receiving?**
- **NSE**: YES — real, live-verified connectivity today and real tick
  reception on 2026-09-15.
- **BSE**: implemented and unit-tested, but **UNVERIFIED live** — do not
  treat it as equivalent to the NSE evidence.
- **Yahoo**: YES for the historical/research path, with a disclosed,
  correctly-scoped (non-live-trading) caching caveat.
- **Cached data**: used extensively and correctly labeled as such; never
  found silently substituting for live data in the live-trading path.
- **Simulated data**: `--source mock` is clearly labeled in every banner
  and log line (`SOURCE: MOCK`), never conflated with real data anywhere
  found this session.

**3. Is the data sufficiently real-time and reliable?**
For NSE, yes, with measured latency (~0.45–0.63s REST round-trip, real
WebSocket ticks, gap observability now closing the one real silent-gap
incident found in this campaign). For BSE, unproven. Clock skew is small
(+6.2s today), monitored, and disclosed rather than silently biasing
freshness checks.

**4. Is the LLM genuinely integrated and providing value?**
Genuinely integrated, narrow value, correctly and provably non-decisional.
It explains an already-made decision in plain language and is
architecturally incapable (by schema, not just by prompt) of changing
that decision. It is currently non-functional in this environment
(Ollama not running) with zero effect on the rest of the system, which is
itself the intended, verified behavior.

**5. Is the architecture production-ready?**
**PARTIALLY**. The safety-critical path (risk, kill switch, order-
placement block, approval TOCTOU handling) is genuinely production-grade
and freshly re-proven this session. The surrounding operational surface
(no auth on the dashboard's mutating routes if misconfigured off
loopback, no Docker packaging, no multi-hour fleet soak test) is not.

**6. Is it secure enough to deploy?**
**WITH RISKS.** No secrets exposure, no SQL injection found, no reachable
dependency CVE, real-order path structurally blocked and re-confirmed.
Risks: dashboard has no auth (mitigated by the loopback default, not
eliminated by the code), no full LLM prompt-injection red-team was
performed on the news-ingestion path this session.

**7. Can another engineer deploy and operate it?**
**WITH DOCUMENTATION GAPS.** `INSTALLATION.md`/`OPERATIONS_GUIDE.md`/
`USER_GUIDE.md` give a real, followable path (pip install → configure →
health check → run), re-confirmed present and accurate this session. No
one-command containerized deploy exists.

**8. How does it compare with existing solutions?**
See §15 — genuinely differentiated on engineering rigor, safety
architecture, and Indian-market focus; not differentiated (and
deliberately not competing) on live execution, UI, community, or
multi-asset breadth; the "AI trading" framing that's common in this space
would NOT be an honest way to market it — "rigorously safety-engineered
research/paper-trading harness for the Indian market" would be.

**9. What are the biggest remaining technical risks, ranked?**
1. Multi-symbol fleet resource behavior over real multi-hour duration —
   unproven.
2. BSE live connectivity — unproven.
3. Dashboard auth if ever misconfigured off loopback.
4. No demonstrated live-signal walk through the full prediction/
   resolution chain (an evidence gap, not a code defect).

**10. What is fundamentally missing?**
A demonstrated trading edge (unchanged, honestly stated), and — separately —
any UI/execution/community layer that would make this a product a
non-engineer could use, as opposed to infrastructure an engineer can
build on.

**11. What should we STOP building?**
Further audit/report documents about readiness, absent a newly
discovered defect. This campaign has now produced an extensive, mutually
-reinforcing body of evidence (53+ failure-mode entries, multiple
capability matrices, multiple live-session reports); another pass of the
same kind without new evidence would be process for its own sake, not
engineering value. Also: do not build Docker packaging, dashboard auth,
or per-row provenance columns speculatively — build them only when a
concrete deployment scenario (a second operator, a non-loopback host, an
audit requirement) actually demands them.

**12. What should we build NEXT?**
Run the actual 15-symbol live session this system now exists to run, and
let `fleet-summary` produce the first real resource/behavior data point
for the new supervisor code at real scale. That is strictly higher-value
than any further speculative hardening.

**13. Is there a credible technical/product advantage?**
**UNCERTAIN, leaning YES on engineering, UNCERTAIN on product.** The
safety/evidence-discipline architecture is a real, demonstrable
advantage over most comparable open-source or indie tooling. Whether
that translates into a product someone pays for depends entirely on
either (a) eventually demonstrating a real edge, which remains
unproven, or (b) repositioning as infrastructure/tooling rather than a
trading product — a strategic decision, not an engineering one.

**14. Is this project actually worth continuing?**
For its STATED current purpose — a rigorously-tested harness to honestly
discover whether a real trading edge exists before ever risking capital —
**YES**, on the evidence gathered today. As a commercial product bet
today, **UNCERTAIN**, honestly, and that uncertainty should not be
resolved by continuing to build more engineering; it can only be
resolved by more real trading-strategy evidence (which this audit did
not and should not manufacture) or a deliberate product/positioning
decision outside engineering's scope.

---

## 20. FINAL VERDICT

## PASS WITH RISKS

Engineering, safety, and security fundamentals were independently
re-verified fresh this session and hold up; the specific, disclosed risks
above (BSE unverified live, unsoaked fleet supervisor, dashboard auth,
no Docker) are real but bounded, known, and do not represent unsafe
trading behavior. The verdict is NOT based on the high test count alone —
it rests on the fresh, adversarial re-verification performed this
session (a real mutation test against the highest-stakes safety check, a
real dependency scan with reachability analysis, real live connectivity
checks, and direct source reading of every safety-relevant claim), not on
re-citing prior reports uncritically.

---

## 21. TOMORROW READINESS — NEXT MARKET SESSION

**Ready for**: 15-symbol, independent-process, real Dhan, NSE, paper-only,
live-market, fleet-supervised, prediction-recording, cost-adjusted,
strategy-frozen operation, as specified.

**Not ready for, and should not be attempted**: any BSE symbol in the
same session (unverified live), any relaxation of the real-order block
(structurally impossible regardless), and any expectation that this
session by itself demonstrates a resource-safe multi-hour fleet — that
is exactly what tomorrow's session will be the FIRST real evidence for.

**What tomorrow's session CAN prove**: whether 15 independent Dhan
WebSocket connections behave correctly under real concurrent load; real
resource behavior (memory, file descriptors, log growth) for the new
fleet-supervisor code at real scale over real market hours; whether the
frozen strategy generates any signal across a genuinely broader NSE
universe than the single-symbol sessions so far; whether
`fleet-supervise`'s health/restart/shutdown machinery behaves correctly
under real (not simulated) conditions for a full session.

**What tomorrow's session CANNOT prove, and must not be reported as
proving**: profitability, a trading edge, or BSE readiness. **One
successful live session does not prove profitability — the objective is
evidence**, and today's audit adds engineering/security/safety evidence,
not strategy evidence, which remains, correctly, NO DEMONSTRATED EDGE.
