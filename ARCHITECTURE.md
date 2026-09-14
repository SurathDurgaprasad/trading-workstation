# Architecture

A reference map of the system as it exists today. For the history of
how it got here, see `docs/PHASE_HISTORY.md`. For day-to-day usage,
see `USER_GUIDE.md`. For running it unattended, see
`OPERATIONS_GUIDE.md`.

## Two pipelines, one shared foundation

The system has two independent pipelines that share market-data and
risk infrastructure but never call into each other's execution logic:

```
                    Market Data (Yahoo / mock / Dhan)
                              |
        +---------------------+---------------------+
        |                                             |
   Intraday simulation                          market_intelligence
   (paper/, live/, strategy/)                   scan -> research -> decide
        |                                             |
    Strategy                                    sizing (preview only)
        |                                             |
    Risk Engine                                predictions (shadow-only)
        |                                             |
  AI explanation (optional)                     learning (read-only report)
        |
  Human approval
        |
  Risk check again
        |
  Paper execution
        |
  Position monitoring
        |
     Journal
```

**Pipeline A — intraday paper trading** (`paper/`, `live/`, `strategy/`,
`risk/`): a bar-by-bar simulation or real-market-data-driven loop that
generates a signal, sizes it, optionally routes it through human
approval, and executes it as a paper (never real) order.

**Pipeline B — market intelligence** (`market_intelligence/`,
`research/`, `decision_engine/`, `predictions/`, `learning/`): scans a
watchlist, gathers evidence, produces a deterministic label, previews
a position size, records a shadow prediction, and later scores that
prediction against real outcomes. No command in this pipeline can place
an order, real or paper — it never imports `paper/` or a broker
adapter for anything beyond an optional, read-only open-position
lookup.

**The bridge** (`shadow-run --paper-execute`, `schedule tick
--paper-execute`): the one deliberate, opt-in, never-default connection
between the two — a risk-approved, critic-approved BUY decision from
pipeline B becomes a real `PaperTradingEngine` order via the exact same
`submit_signal` mechanism pipeline A's own `paper`/`paper-live`
commands use. There is no second, parallel order-submission path.

## Component map

| Component | Role | Depends on |
|---|---|---|
| `market/data_provider.py` | `OHLCVBar`/`OHLCV` models, Yahoo Finance fetch, row-level data-quality filtering (drops NaN or OHLC-impossible rows at construction) | `yfinance` |
| `market_data/validation.py` | Series-level data-quality classification (HEALTHY/DEGRADED/INVALID) — duplicates, ordering, gaps, symbol identity, staleness | `market/data_provider.py`, `live/freshness.py` |
| `market/indicators.py` | SMA/RSI/MACD/ATR/volume-trend computation | `market/data_provider.py` |
| `strategy/baseline.py` | `TrendMomentumBaseline` — the one deterministic, rule-based signal generator | `market/indicators.py` |
| `risk/engine.py`, `risk/config.py`, `risk/sizing.py` | Fail-closed position sizing and trade veto logic — the one safety boundary every signal must pass through | `strategy/` |
| `paper/engine.py`, `paper/store.py` | Paper-trading state machine (signals → orders → fills → positions → trades), SQLite-persisted, restart-safe | `risk/`, `strategy/` |
| `live/pipeline.py`, `live/mock_source.py`, `live/dhan/` | Bar-by-bar streaming (mock replay or real Dhan feed), freshness suppression, human-approval lifecycle, kill switch | `paper/`, `risk/` |
| `market_intelligence/scanner.py` | Ranks a watchlist by trend/momentum/breakout/relative-strength; gates on data quality first | `market/`, `market_data/validation.py` |
| `research/summarizer.py` | Real news + sector evidence, optional AI summary | `market_intelligence/` |
| `decision_engine/engine.py` | Deterministic BUY/WATCH/AVOID/EXIT/NO_ACTION label from scanner + research evidence | `market_intelligence/`, `research/` |
| `critic/engine.py` | 13-check deterministic re-examination of a proposed BUY before it can become a paper order | `decision_engine/`, `live/state_store.py` |
| `predictions/`, `predictions/direction_forecast*.py` | Immutable shadow predictions, evaluated later against real outcomes | `decision_engine/` |
| `learning/` | Read-only performance/calibration reports over prediction history | `predictions/` |
| `experiments/`, `strategy/experiment_store.py`, `strategy/promotion_store.py` | Named experiment tracking and advisory-only promotion recommendations | `learning/` |
| `scheduler/` | Unattended triggering of `shadow-run`/`evaluate`/`learn` on a configurable schedule, with overlap prevention and crash recovery | `main.py`'s own command functions (in-process, not subprocess) |
| `dashboard/` | Read-only Starlette web UI over the same stores every CLI command reads/writes | All of the above, read-only |
| `mcp_server/` | Optional MCP tool server (23 read-only/paper-only tools) for AI-assistant observability | `paper/`, `live/workstation.py` — opt-in, not imported by `main.py`'s core command set |
| `core/timeutil.py` | The one place naive-vs-aware datetime normalization is decided (two documented conventions: market/bar data stays naive, record/system metadata is UTC-aware) | stdlib `datetime`, `pandas` |
| `core/sqlite_util.py` | The one place every SQLite connection is opened (WAL mode, busy timeout, auto-creates a missing parent directory, raises a clear `DatabaseCorruptedError` for a corrupt/non-SQLite file), plus shared migration primitives (`ensure_column`, `ensure_schema_version`, `try_create_unique_index`), health primitives (`integrity_check`, `db_size_bytes`), and `parse_model_json` (wraps every store's `Model.model_validate_json(row)` read, raising a clear `MalformedRowError` instead of a raw `pydantic.ValidationError` for a malformed row) | stdlib `sqlite3` |
| `core/health.py` | The one unified health model — `collect_system_health()` returns a `SystemHealth` (per-component status + one overall HEALTHY/DEGRADED/SAFE_STOP/FAILED verdict), consumed identically by `main.py health`, the dashboard's `/health` route, and `main.py`'s own startup gate (`_run_startup_gate`, wired into `paper-live` and `schedule tick`/`schedule loop`: FAILED refuses to start, SAFE_STOP/DEGRADED warn and continue). The scheduler check covers both an active/orphaned lock AND a sustained per-slot failure streak (3+ consecutive FAILED/RECLAIMED runs with no success since, via `SchedulerRunStore.consecutive_failures_for_slot`) — the latter closes a real gap where a multi-hour provider outage left every tick correctly finishing FAILED (and thus releasing its lock cleanly) while the health check itself stayed silently HEALTHY throughout. The disk check covers both a real write probe AND real free-space headroom (`shutil.disk_usage`, DEGRADED below 500MB, FAILED below 50MB) — previously a full disk gave zero advance warning anywhere, only a raw `OSError` at the point of an actual failed write | `core/sqlite_util.py`-backed store `integrity_check()`, `llm/provider.py`, `live/state_store.py`, `risk/config.py`, `scheduler/store.py` |

## Persistence

Every store is SQLite, one file per concern, under `data/` by default
(overridable per-store via `TRADING_*_DB_PATH` — see `.env.example`).
All 12 stores share the same connection policy (`core/sqlite_util.py`):
WAL journal mode, a 30-second busy timeout, `PRAGMA foreign_keys = ON`
where relevant, and a `PRAGMA user_version`-based schema-version stamp.
Nine of the twelve have never needed a real schema migration beyond
the shared additive-column mechanism (`ensure_column`); three
(`predictions.db`, `predictions_direction_forecasts.db` /
`live_state.db`'s `feed_status` table) have used it for a real,
backfilled column addition.

Two stores (`predictions.db`, the forecast store) additionally enforce
a `UNIQUE(symbol, entry_time)` / `UNIQUE(symbol, as_of)` constraint at
the database level, not just in application logic — closing a genuine
race where a manual CLI run overlapping a scheduled run could
previously double-insert.

## Datetime policy

Two genuinely different conventions coexist, by design, documented in
`core/timeutil.py`'s own module docstring:

1. **Market/bar data** (`to_naive`): normalized to naive — Yahoo/mock
   bars are naive by convention; real Dhan bars are UTC-aware; both
   are stripped to naive before comparison so a series stays internally
   consistent.
2. **Record/system metadata** (`as_utc_aware`): normalized to
   UTC-aware — predictions, decisions, and experiment records are
   meant to be UTC; a bare value just means tzinfo was never attached.
3. **Matching a scalar against an existing index** (`match_index_awareness`):
   adapts the scalar to whatever the index already is, in either
   direction — never invents or discards the series' own real
   timezone information.

This consolidation exists because the same bug class (comparing a
naive and an aware datetime) recurred three times independently before
`core/timeutil.py` existed (documented in that module's own docstring).
New code touching a datetime comparison should use one of these three
functions, not reinvent a fourth pattern.

## Data-quality policy

`market_data/validation.py::validate_ohlcv` classifies a fetched
series HEALTHY, DEGRADED, or INVALID:

- **INVALID** (duplicate timestamps, non-chronological ordering, a
  symbol-identity mismatch, or an empty series): the symbol is
  excluded from the scan — `market_intelligence/scanner.py` never
  computes indicators or a decision for it, the same path a fetch
  failure already takes.
- **DEGRADED** (a large gap that may be a legitimate market
  holiday/weekend, or a stale last bar): visible in the finding, not
  blocking — the caller decides.

Separately, `market/data_provider.py::OHLCV.from_dataframe` drops any
individual row with an impossible OHLC relationship (high below low,
close outside `[low, high]`) at construction time, the same mechanism
it already used for NaN rows.

## Property-based testing and the executable failure matrix

Autonomous hardening cycle 7 added two new, deliberately bounded testing
layers alongside the existing example-based suite:

- **`hypothesis`** (test-only dependency, pinned in `requirements.txt`):
  a small number of properties derived directly from a function's own
  documented contract (currently `risk/engine.py::RiskEngine.evaluate`
  in `tests/test_risk_sizing_properties.py`), run with `max_examples`
  capped and `derandomize=True` for full reproducibility -- never
  unbounded fuzzing, never a substitute for example-based tests. Found
  a real defect on first use: a NaN `target_price` silently authorized
  a trade (see the "Safety invariants" section below).
- **`tests/failure_injection/`**: a machine-readable failure registry
  (`failure_matrix.yaml`) plus `test_matrix_integrity.py`, which asserts
  on every regression run that every row's referenced test still exists
  and is collectible -- turning "did we document this failure mode" into
  something that fails CI on drift, rather than a prose claim that can
  silently go stale (as `FINAL_FAILURE_MODE_ANALYSIS.md` itself once
  did — see that document's entry #24). Each row carries an evidence
  grade (A=real production execution, B=integration test with real
  infrastructure, C=deterministic simulation/injection, D=static
  inspection, E=assumption) so a claim's actual strength is never
  overstated.

## Safety invariants (enforced, not just documented)

- **Live order execution is structurally blocked** — see `SECURITY.md`.
- **No LLM anywhere in the deterministic decision/risk/execution path**
  — narration and RAG context are advisory text, never an input to
  `risk/engine.py` or `paper/engine.py`.
- **A prediction is never rewritten** — `predictions/store.py` has no
  `update_prediction` method; an outcome is always a new row in
  `prediction_evaluations`, referencing the original by ID.
- **A paper position's CLOSED state is terminal** — `paper/store.py`'s
  `update_position()` rejects any further mutation of an already-closed
  position at the database layer.
- **The kill switch is read fresh from disk on every check** — zero
  caching, so a restart can never silently "forget" an active kill
  switch.
- **Every kill-switch activation/reset is logged** — `LiveStateStore.
  activate_kill_switch`/`reset_kill_switch` (the one choke point every
  caller, CLI or dashboard, goes through) emits a `logger.warning`, so
  the event is visible in a `--log-file`-backed log stream, not only by
  actively polling `health`/`readiness-check`.
- **Approving and rejecting the same pending signal from two racing
  requests can never create a duplicate order or a misleading audit
  label** — `LiveStateStore.update_decision` CLAIMS a `signal_id`
  (`WHERE state='PENDING_HUMAN_APPROVAL'`) before `submit_signal` ever
  runs, not after; the losing caller returns `ALREADY_DECIDED` without
  ever reaching `submit_signal`. Found and fixed cycle 20 after a
  first, guard-too-late fix attempt was itself caught by cycle 19's
  own concurrency test.
- **Submitting the same signal from two racing processes is genuinely
  idempotent** — `PaperTradingEngine.submit_signal` catches the
  `sqlite3.IntegrityError` a real check-then-act race can produce
  (found via a genuine multi-threaded test, cycle 15) and returns the
  winner's already-committed `JournalEntry` to the loser, instead of
  letting it crash. The DB-level `UNIQUE` constraint already prevented
  an actual duplicate row; this closes the "loser crashes instead of
  returning gracefully" gap in that same guarantee.
- **A scheduler run's terminal status can never be silently overwritten**
  — `SchedulerRunStore.finish_run` guards its UPDATE with `WHERE status =
  'RUNNING'`, raising `InvalidRunTransitionError` otherwise. Found via a
  state-machine attack (autonomous hardening cycle 8): a "zombie"
  process finishing late, after its own run was already reclaimed as
  stale by another process, previously silently overwrote the RECLAIMED
  status back to COMPLETED/FAILED, corrupting the audit trail.
  `scheduler/runner.py::run_tick` catches this specific error on both
  its success and failure paths.
- **A Dhan feed connection can never hang in CONNECTING forever** —
  `connect_timeout_seconds` (default 30s) routes a stalled connection
  attempt through the same reconnect funnel every other failure already
  uses. Found and fixed cycle 8, revisiting a gap cycle 7 had explicitly
  disclosed but left unfixed pending a dedicated re-audit.
- **A Dhan feed consumer that falls behind can never grow memory
  without bound** — `DhanMarketDataSource._bar_queue` is a bounded
  `queue.Queue(maxsize=max_queued_bars)` (default 2000); the wire
  callback enqueues via a `put_nowait()`-based `_enqueue_bar()` that
  NEVER blocks the WebSocket library's own receive thread, dropping the
  OLDEST queued bar (and logging a warning) to make room on overflow.
  Found and disclosed cycle 16 (a naive `maxsize` fix was deliberately
  deferred, since a blocking `put()` once full would have traded the
  original risk for a worse one — a stalled receive thread); fixed
  cycle 21 with the deliberate drop-oldest/never-blocking design,
  proven by five dedicated tests (cap never exceeded, never blocks,
  oldest dropped not newest, warning names the dropped symbol, a
  keeping-up consumer never drops).
- **A stale bar can never fill a pending order or close an open
  position** — `PaperTradingEngine.process_bar(..., is_fresh=...)`
  skips its entry-fill/stop-target block entirely when the caller
  passes `is_fresh=False`; `live/pipeline.py` computes its own
  `FreshnessPolicy` check BEFORE calling `process_bar` (previously
  after) and threads the result through. Found and fixed cycle 22: a
  fresh bar could risk-approve a signal into a PENDING order, but the
  LATER bar that actually filled it (or checked an OPEN position's
  stop/target) was never itself subject to the same freshness gate —
  `STALE_SIGNAL_SUPPRESSED` only ever blocked generating a *new*
  signal, never an entry/exit already in flight. Every non-live caller
  of `process_bar` (backtest replay, catch-up fills, direct tests)
  defaults to `is_fresh=True`, completely unaffected.
- **A duplicate or out-of-order bar can never pollute the indicator
  history** — `live/pipeline.py::process_next` only calls
  `buffer.append(bar)` AFTER confirming `PaperTradingEngine.process_bar`
  did not reject the bar as `DUPLICATE_SKIPPED` or out-of-order. Found
  and fixed cycle 23: the execution layer's own dedup/ordering guarantee
  was always correct, but a SEPARATE consumer of the same bar — the
  indicator-history buffer `generate_signal()` reads from — had no such
  gate, silently skewing every subsequent SMA/RSI/ATR/MACD computation
  with an extra or misplaced row. A stale (but genuinely new, in-order)
  bar is still appended — its data is real, just late; only its
  signal-generation consequence is suppressed.
- **A PENDING order can never fill after the kill switch or a risk
  circuit breaker activates mid-flight** — `PaperTradingEngine.
  process_bar(..., allow_new_fill=...)` skips the fill-a-pending-order
  branch entirely when `allow_new_fill=False`; `live/pipeline.py`
  computes it immediately before every `process_bar` call: false only
  when no position is open yet for the symbol AND (an account-level
  circuit breaker is active OR the kill switch is active). Found and
  fixed cycle 24, mirroring a guard `paper/advance.py` already carried
  at its own (batch/catch-up) call site — the actual continuous LIVE
  path had no equivalent protection until this cycle. Deliberately does
  NOT gate an already-OPEN position's stop/target check, which always
  runs regardless — refusing to manage an existing position during a
  halt would strand it with no way to exit.
- **The MCP boundary cannot bypass or crash past risk evaluation** —
  `evaluate_risk_tool`/`paper_trade_signal_tool` inherit `RiskEngine`'s
  `NON_FINITE_VALUE` guard (proven with executable tests, not just
  inspection, cycle 11); a malformed `account_equity` now raises the
  same clean `ToolError` contract every other invalid-input path in the
  server already uses, instead of a raw, uncaught `ValidationError`
  (a real defect found and fixed cycle 11).
- **NaN/Infinity can never authorize a trade** — `RiskEngine.evaluate`
  runs an explicit `math.isfinite()` guard across every safety-relevant
  numeric input (`reference_price`/`stop_price`/`target_price`/
  `risk_reward`/`account.equity`) before any other logic, raising a
  dedicated `VetoReason.NON_FINITE_VALUE`. Found via property-based
  testing (autonomous hardening cycle 7): a NaN `target_price`
  previously slipped past every existing `<=`/`>=` structural check
  (every comparison against NaN is `False`) and produced a fully
  APPROVED trade with a nonsensical target — a real, reproduced defect,
  not a theoretical one.
