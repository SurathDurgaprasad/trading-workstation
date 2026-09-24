# Operations

An end-to-end operational walkthrough: install → configure → run offline → run paper →
(optionally) run against live data → shut down. For exhaustive detail on any one step,
this page links to the dedicated document rather than repeating it.

Developed and tested on **Windows**. The application code itself is plain, portable
Python plus SQLite with no Windows-specific API calls in the core pipeline (see
[`INSTALLATION.md`](../INSTALLATION.md#requirements)) — but no test run on Linux/macOS
is on record, so treat cross-platform support as a reasoned claim about the code, not an
empirically verified one. The **shutdown guidance in §6 below is Windows-specific**
(`taskkill`) because that is what real incident recovery on this project has actually
used; a Linux/macOS operator would use the standard `kill`/process-group signal
equivalent instead, which has not been exercised here.

## 1. Install

Full detail: [`INSTALLATION.md`](../INSTALLATION.md).

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/macOS (unverified)
pip install -r requirements.txt
pytest                       # no credentials required — see step 3
```

## 2. Credential setup (optional — everything in step 3 works without this)

Copy `.env.example` to `.env` (already `.gitignore`d) or export the variables directly
in your shell/secret manager. Nothing in this repository auto-loads a `.env` file — see
[`SECURITY.md`](../SECURITY.md#credentials) for exactly how and when each credential is
read.

| Variable | Required for | Optional? |
|---|---|---|
| `DHAN_CLIENT_ID`, `DHAN_ACCESS_TOKEN` | Real Dhan market-data/account reads (`--source dhan`) | Yes — every offline/paper command works without these |
| `AI_PROVIDER`, `OPENAI_API_KEY`, `OPENAI_ENABLED` | Optional OpenAI advisory layer | Yes — defaults to a local Ollama provider, itself optional (see below) |
| `TRADING_*_DB_PATH` (9 variables) | Overriding a store's default `data/<name>.db` location | Yes — every store defaults to `data/` |

**Verify credentials are present without printing them:**

```bash
python main.py readiness-check          # checks presence/reachability, never logs a value
python main.py readiness-check --deep   # + a real, minimal Dhan/Ollama connectivity probe
python main.py ai-health                # OpenAI connectivity check, zero completion cost
```

## 3. Run offline (no credentials, no network dependency beyond Yahoo Finance)

```bash
python main.py backtest --symbol RELIANCE.NS
python main.py paper --symbol RELIANCE.NS
python main.py paper-live --symbol RELIANCE.NS --interval 1d --period 1y   # mock/replay source
python main.py shadow-run --symbols RELIANCE.NS,TCS.NS
python main.py dashboard
```

The full test suite (`pytest`) requires no credentials and no live connection; a small
number of tests use a locally-cached market-data snapshot and skip cleanly when it's
absent.

## 4. Run against live Dhan data (optional, consumes Dhan API usage, paper execution only)

```bash
python main.py paper-live --symbol RELIANCE.NS --source dhan
python main.py fleet-supervise --watchlist-file market_data/watchlists/starter_nse.yaml --runtime-dir runtime --source dhan
python main.py fleet-summary --watchlist-file market_data/watchlists/starter_nse.yaml --runtime-dir runtime
```

**No command in this repository can place a real order — see [`SAFETY.md`](../docs/SAFETY.md).**
`--source dhan` only changes where market data comes from; execution is always paper.

**Never run these with real trading intent** — the strategy has no demonstrated edge
(see [`LIMITATIONS.md`](LIMITATIONS.md)), and no real-order path exists regardless.

## 5. Stale-data and reconnect behavior (what to expect on a real feed)

- A bar arriving out of order or as a duplicate is dropped before it can pollute the
  indicator history (`DUPLICATE_SKIPPED`).
- A stale bar (per `FreshnessPolicy`) can never fill a pending order or close an open
  position, and never generates a new signal (`STALE_SIGNAL_SUPPRESSED`).
- An idle connection reconnects automatically after `connected_idle_timeout_seconds`
  (default 300s); a stalled connection attempt times out and retries after
  `connect_timeout_seconds` (default 30s).
- `[GAP DETECTED]` / `[GAP ONGOING]` log lines are pure observability (`BarGapMonitor`,
  180s threshold) — they do not by themselves halt anything.
- See [`LIVE_VALIDATION.md`](LIVE_VALIDATION.md) for what was actually observed across
  six real sessions, including one recurring, still-unexplained ~15-minute interruption
  pattern.

## 6. Shutdown

- Single-process commands: `Ctrl+C` (handled cleanly; `schedule loop` finishes its
  current tick before exiting).
- `fleet-supervise`: `Ctrl+C` the supervisor, which stops each worker in turn. If a
  worker is unresponsive, this project's own established fallback (documented from real
  incident recovery) is `taskkill /PID <pid> /T` first, then `taskkill /PID <pid> /F /T`
  if the graceful signal doesn't land — expected for a plain console app on Windows.

## 7. Database setup

Every store is SQLite, one file per concern, auto-created under `data/` on first use —
there is no separate database-setup step. See [`ARCHITECTURE.md`](../ARCHITECTURE.md#persistence)
for the full list of stores and their concurrency model, and
[`OPERATIONS_GUIDE.md`](../OPERATIONS_GUIDE.md#database-maintenance) for maintenance
(integrity checks, backup, restart-after-interruption).

## 8. Test commands

```bash
pytest                                   # full suite, no credentials required
pytest tests/test_dhan_no_real_orders.py # the real-order safety regression (see SAFETY.md)
pytest -k "not slow"                     # skip any explicitly marked slow tests, if present
python main.py health                    # runtime system-health check, not a test-suite run
```

## 9. Troubleshooting

Symptom → cause → recovery for common failures: [`TROUBLESHOOTING.md`](../TROUBLESHOOTING.md).
