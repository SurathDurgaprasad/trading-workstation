# Troubleshooting

Common failure scenarios, in SYMPTOM → CAUSE → DETECTION → AUTOMATIC
RECOVERY → MANUAL ACTION → SAFE-STATE GUARANTEE form. None of these
require editing source code — every manual action here is a CLI
command, a config file edit, or a restart.

---

### `pip install -r requirements.txt` fails

- **Cause**: unsupported Python version, or a network-blocked pip
  index — neither is specific to this project.
- **Detection**: the `pip install` error message itself (a compatible
  version constraint failure, or a connection error).
- **Manual action**: use Python 3.11+; if behind a corporate proxy,
  configure `pip`'s proxy settings per pip's own documentation.

### `pytest` reports failures right after a fresh install

- **Cause**: normally none — the suite is self-contained and requires
  no network, no Ollama, no Dhan credentials.
- **Detection**: the specific failing test names in pytest's output.
- **Manual action**: re-run with `-v` to see the actual assertion; if
  the failure is in a market-data-cache-dependent test, confirm it is
  actually being skipped (cache-dependent tests skip cleanly when
  `data/market/` is absent, which it is on a fresh clone) rather than
  failing for an unrelated reason.

### "Ollama is not reachable at http://localhost:11434..."

- **Cause**: Ollama is not installed, not running, or running on a
  different port.
- **Detection**: this exact, clear error message — never a crash or a
  silent hang.
- **Automatic recovery**: none needed for most commands — `research`
  and `decide` continue with their real evidence/label and simply omit
  the AI summary/narrative. Only `analyze` and `review` (whose entire
  purpose is the AI step) actually fail.
- **Manual action**: `ollama serve`, and confirm the two models are
  pulled (`ollama pull qwen2.5-coder:7b`, `ollama pull nomic-embed-text`).
- **Safe-state guarantee**: no command anywhere degrades to a
  fabricated or guessed AI output — it is either the real output or an
  explicit "unavailable" marker.

### A `RagStoreNotFoundError`

- **Cause**: the Chroma vector store directory (`vectorstore/`) has not
  been built yet — the RAG feature needs documents ingested first.
- **Detection**: the error message names the missing directory.
- **Manual action**: build the vector store via the project's own
  document-ingestion step (see `rag/loader.py`) before using RAG-backed
  features; every non-RAG feature is unaffected.

### Yahoo Finance data fetch fails or returns nothing

- **Cause**: network issue, Yahoo rate limiting, or an invalid/unlisted
  symbol.
- **Detection**: `MarketDataError` with a message naming the symbol;
  `market_intelligence/scanner.py` records it in the scan's `excluded`
  list with the reason, rather than aborting the whole scan.
- **Automatic recovery**: one symbol's failure never aborts a
  multi-symbol scan/shadow-run — every other symbol is processed
  normally.
- **Manual action**: verify the symbol against `python main.py
  universe --symbols <symbol>`; retry later if it looks like rate
  limiting; pass `--resilient` to `scan`/`shadow-run`/`evaluate`/
  `learn`/`schedule tick`/`schedule loop` for automatic retry with
  backoff + a circuit breaker.

### A symbol is silently excluded from a scan with a "Data quality" reason

- **Cause**: `market_data/validation.py::validate_ohlcv` classified the
  fetched series INVALID — duplicate timestamps, non-chronological
  ordering, or a symbol-identity mismatch from the provider.
- **Detection**: the exclusion reason in `scan_report.excluded`
  (printed in `scan`/`shadow-run` output, and in the scan history).
- **Safe-state guarantee**: this is working as intended — an INVALID
  series is excluded before any indicator, decision, or paper trade can
  be derived from it. This is not a bug to "fix" by forcing the symbol
  through; if it persists across multiple fetches, the upstream data
  source itself is the problem, not this codebase.

### `sqlite3.OperationalError: database is locked`

- **Cause**: real, sustained concurrent write contention beyond the
  30-second busy timeout every store now uses (e.g. the scheduler,
  dashboard, and a manual CLI command all writing to the same database
  file within the same window).
- **Detection**: the raised `OperationalError` itself, naming the
  operation.
- **Automatic recovery**: WAL mode (enabled on every store) means
  readers are never blocked by an in-progress writer — only genuine
  writer-vs-writer contention can hit this, and the 30-second timeout
  gives real contention room to resolve first.
- **Manual action**: if this recurs frequently, avoid running the CLI
  against the same database file the scheduler is actively using at
  the same moment; retry the command.

### `DatabaseCorruptedError: Database file '...' could not be opened`

- **Cause**: the database file itself is corrupted, truncated, or not a
  valid SQLite file (e.g. a process was killed mid-write at the
  filesystem level, or the file was overwritten by something else).
- **Detection**: this exact, clear error, naming the file — not a raw
  `sqlite3.DatabaseError` traceback (every store's connection point
  catches and wraps this).
- **Automatic recovery**: none — a corrupted file cannot be repaired
  automatically, and this project never attempts to guess at a repair.
- **Manual action**: restore the named file from a backup (see "Backup"
  in `OPERATIONS_GUIDE.md`). If you have no backup and are willing to
  lose the file's contents, move it aside (do not delete it, in case
  you change your mind) — the application will create a fresh, empty
  one at that path the next time it runs.

### `MalformedRowError: A stored ... row (...) failed to deserialize`

- **Cause**: a specific row's stored data no longer matches what the
  application expects to read back — genuinely rare under normal
  operation (every row is written from an already-validated object;
  this project's own convention is to add new fields as optional so a
  schema change never breaks old rows). Realistic causes: external
  tampering with the database file, or low-level disk corruption of
  just that row (as opposed to the whole file, which raises
  `DatabaseCorruptedError` instead).
- **Detection**: this exact, clear error, naming the affected model and
  row — not a raw `pydantic.ValidationError` traceback.
- **Automatic recovery**: none — this row's data is genuinely
  unreconstructable from what's stored.
- **Manual action**: this is a real, if rare, finding worth
  investigating rather than dismissing — if you did not tamper with the
  database file yourself, treat this as a possible sign of disk-level
  corruption and consider running `python main.py health` (which
  includes a `PRAGMA integrity_check` across every store) to check
  whether the corruption is isolated to this one row or wider.

### A prior run's paper order/position looks stuck or duplicated

- **Cause**: this should not happen — `paper/store.py::update_position`
  enforces CLOSED as a terminal state at the database layer, and
  `paper/engine.py::process_bar` rejects a replayed/duplicate bar at
  the same timestamp as a no-op, both verified by dedicated tests
  including a real restart scenario.
- **Detection**: `python main.py paper status`, or query the store
  directly.
- **Manual action**: if you believe you have found a genuine instance
  of this, it is a real bug — check `python main.py paper status`
  output against what you expect and file/investigate with the actual
  symbol, timestamps, and position IDs involved; do not attempt to
  manually edit the SQLite file to "fix" it.

### Scheduler shows a run stuck as RUNNING after a crash

- **Cause**: the process that started the run was killed before it
  could finish.
- **Detection**: `python main.py schedule status` shows the run with
  no `finished_at`.
- **Automatic recovery**: the next tick's `reclaim_stale_locks` call
  (staleness threshold `--staleness-seconds`, default 1800s) marks it
  RECLAIMED and frees the lock for a new run — verified across a real
  process restart, not just the same instance retrying.
- **Manual action**: none required; if you need it freed immediately
  rather than waiting for the staleness window, restart the scheduler
  process (the next tick's reclaim runs immediately on startup).

### Kill switch appears active but you don't remember activating it

- **Cause**: it was activated in a prior session (by you, or by the
  critic/risk layer's own automatic response to a detected unsafe
  condition) and never explicitly reset.
- **Detection**: `python main.py readiness-check` reports it, with the
  reason and activation timestamp.
- **Manual action**: review the reason before resetting it — it exists
  precisely so an unsafe condition is not silently bypassed by a
  restart. Reset it via the interactive `paper-live` session or the
  dashboard once you've confirmed it's safe to resume.

### Real (not paper) order concerns

There is no scenario in which this system places a real order — see
`SECURITY.md`'s "Live trading is structurally blocked" section for the
verified evidence. If you ever see behavior that looks like it might
be attempting a real order, stop the process immediately and treat it
as a critical bug report, not a configuration issue.
