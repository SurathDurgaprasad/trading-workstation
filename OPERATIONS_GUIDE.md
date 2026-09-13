# Operations Guide

Running this system unattended, monitoring it, and recovering it. For
one-off command usage, see `USER_GUIDE.md`. For what to do when
something breaks, see `TROUBLESHOOTING.md`.

## Startup gate

`paper-live` and `schedule tick`/`schedule loop` run a startup health
check (the same `core/health.py` model `health`/`/health` use) before
doing anything else. If a CRITICAL component is broken (database
corruption, a disk-write failure, an invalid risk config), the command
refuses to start at all (`[SAFE_STOP]`, exit code 1) rather than
proceeding against a system it cannot trust. If the kill switch is
active, it prints a warning and starts anyway (the kill switch already
blocks new orders downstream, and refusing to start would prevent you
from reaching the session needed to reset it). A DEGRADED optional
component (e.g. Ollama unreachable) prints an informational note and
continues normally. `--kill-switch`/`--reset-kill-switch` themselves,
and `schedule status`, always bypass the gate -- you can always reach
the tools needed to diagnose or recover a broken system.

## Starting unattended operation

```bash
python main.py readiness-check
python main.py schedule loop --symbols AAPL,MSFT,RELIANCE.NS --log-file logs/schedule.log
```

`schedule loop` runs continuously until interrupted (Ctrl+C stops it
cleanly). For a cron-triggered, one-shot invocation instead:

```bash
python main.py schedule tick --symbols AAPL,MSFT,RELIANCE.NS
```

Both use the same five-slot default schedule (pre-market, market-open,
intraday, pre-close, post-market — see `scheduler/config.py`'s own
`_default_slots()`), overridable via a YAML file:

```bash
python main.py schedule tick --config my_schedule.yaml --symbols AAPL,MSFT
```

A malformed schedule config (an inverted time window, a non-positive
`frequency_minutes`) now fails immediately with a clear
`SchedulerConfigurationError` at load time — not a slot that silently
never runs.

If a custom config defines two slots with overlapping eligibility
windows, `due_slot()` is deterministic, not ambiguous: it always
returns the *first* due slot in the order the slots are configured
(`scheduler/config.py::ScheduleConfig.due_slot`), never more than one
slot's worth of work per tick — a second due slot at the same tick is
simply picked up on the next one. If you rely on overlapping windows,
put the higher-priority slot first in your YAML.

## Checking on it

```bash
python main.py schedule status
python main.py health
```

`health` gives a single, unified HEALTHY/DEGRADED/SAFE_STOP/FAILED
verdict across application/database/disk/dhan/kill-switch/scheduler/
risk/ollama — the same underlying check (`core/health.py`) the
dashboard's `/health` page renders, so a script and a human looking at
the dashboard always see the same picture. `SAFE_STOP` specifically
means the kill switch is active (a deliberate halt, not a malfunction);
`FAILED` means a critical component (database corruption, a disk-write
failure, or an invalid risk config) — treat that as urgent.

Shows a per-slot summary (last success timestamp, last failure
timestamp + its error) followed by the recent run history. Add
`--check-integrity` to also run a read-only `PRAGMA integrity_check`
against the scheduler's own database and print its file size — useful
after days or weeks of unattended operation.

```bash
python main.py paper status
python main.py cache-status --symbols AAPL,MSFT,RELIANCE.NS
```

## Overlap prevention and crash recovery

The scheduler's overlap prevention is a real, on-disk lock (a RUNNING
row in `scheduler_runs.db`), not an in-memory flag — it survives a
process crash. If the process that held the lock is killed (power
loss, `kill -9`, OS crash), the next tick automatically reclaims any
lock older than `--staleness-seconds` (default 1800) and proceeds.
This is verified by a real restart test (a fresh
`SchedulerRunStore` instance opened on the same database file,
separate from the instance that started the run), not just an
in-process retry.

A tick-setup failure (e.g. a database error before any slot has
started) is caught and reported as a clean, non-crashing `TickResult`
— it never propagates out and kills a long-lived `schedule loop`
process. A failure *during* slot execution is caught the same way and
recorded as a FAILED run; the scheduler process itself keeps running
and will try again on the next tick.

**What is not (yet) protected**: a per-job timeout. If a single slot's
execution hangs (e.g. a network call inside it that never times out),
the scheduler will not preemptively kill it — it will eventually show
up as a stuck RUNNING lock, reclaimed by the next process restart's
staleness check. This is a known, disclosed architectural limitation
(see `FINAL_RELEASE_REMAINING_WORK.md`), not an oversight: the
scheduler runs jobs in-process, and a thread-based timeout would not
actually stop a hung call — it would only stop *waiting* for it while
the original call kept running unsupervised in the background, a worse
failure mode than today's. If a job hangs in practice, restart the
`schedule loop` process; the stale lock will be reclaimed automatically
on the next tick.

## Kill switch

```bash
python main.py paper-live --symbol AAPL   # interactive session; kill switch commands are available inside it
```

The kill switch is read fresh from disk on every check — no caching,
so it survives a restart reliably and cannot be silently "forgotten."
Activate it (via the interactive workstation or the dashboard) if you
need to immediately stop any further paper-order submission; existing
open positions are unaffected — the kill switch blocks new orders, it
does not force-close anything.

## Database maintenance

Every store supports a read-only integrity check and size report:

```python
from paper.store import PaperStore
store = PaperStore("data/paper_trading.db")
print(store.integrity_check())   # "ok", or SQLite's own corruption findings
print(store.db_size_bytes())
```

The same two methods exist on all 12 stores (`experiments`,
`decision_engine`, `live_state`, `strategy/promotion`,
`strategy/experiment`, `paper`, `scheduler`, `predictions`,
`predictions/direction_forecast`, `research`, `market_intelligence`,
`market_intelligence/regime`) and each also exposes `schema_version()`.

**No automatic startup diagnostic runs these across all 12 stores yet**
— run them individually, or via `schedule status --check-integrity`
(scheduler's own database only) and `readiness-check` (one database
by default), if you suspect corruption after an unclean shutdown or a
disk issue.

## Backup

There is no automated backup mechanism. Each store is a single SQLite
file under `data/` (or wherever `TRADING_*_DB_PATH` points it). To back
up: stop the process holding the connection (or accept a brief
WAL-checkpoint risk from copying a live file), then copy the `.db`
file(s). To restore: stop the process, replace the file(s), restart.
SQLite's WAL mode means a copied file may have a `-wal`/`-shm` sidecar
— copy those too if present, or run `PRAGMA wal_checkpoint(TRUNCATE)`
via a plain sqlite3 connection before copying to fold the WAL back into
the main file first.

## Log files

`--log-file <path>` on `schedule loop`/`schedule tick` writes a
rotating log (10MB × 5 backups) in addition to stdout. No credential
value is ever written to any log — see `SECURITY.md`.

## Restarting after any interruption

1. `python main.py readiness-check` — confirms kill switch state,
   leftover pending approvals, and cache freshness before you resume.
2. `python main.py schedule status` — confirms no orphaned lock is
   stuck (a genuinely stuck one self-heals on the next tick anyway,
   per the crash-recovery behavior above).
3. Resume `schedule loop`, or your own cron-triggered `schedule tick`.

No manual state repair is normally needed — predictions, positions,
capital, and the kill switch all persist correctly across a restart
(verified by dedicated restart tests; see `ARCHITECTURE.md`).
