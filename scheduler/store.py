"""Phase 28 -- scheduler run-history persistence. Same SQLite convention
as every other store in this project (predictions/store.py, decision_engine/
store.py, market_intelligence/store.py): stdlib sqlite3, explicit BEGIN/
COMMIT/ROLLBACK, one `data_json` column holding the record's own
`model_dump_json()`.

This store is the ONLY thing that makes overlap prevention and restart
recovery real rather than in-memory-only: a RUNNING row with no
finished_at IS the lock, and it survives a process crash because it's on
disk, not in a variable.
"""

import sqlite3

from core import sqlite_util
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from scheduler.models import RunRecord, RunStatus

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scheduler_runs (
    run_id TEXT PRIMARY KEY,
    slot_name TEXT NOT NULL,
    run_date TEXT NOT NULL,
    started_at TEXT NOT NULL,
    status TEXT NOT NULL,
    data_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scheduler_runs_slot_date ON scheduler_runs(slot_name, run_date);
CREATE INDEX IF NOT EXISTS idx_scheduler_runs_status ON scheduler_runs(status);
"""


class SchedulerRunStore:
    CURRENT_SCHEMA_VERSION = 1
    """Final-product-hardening: see core.sqlite_util.ensure_schema_version's
    docstring for why this is PRAGMA user_version, not a table. Bump this
    (and add a real migration step in __init__) the next time this
    store's own _SCHEMA changes in a way existing on-disk databases need
    to catch up to."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._conn = sqlite_util.connect(self.db_path)
        self._conn.executescript(_SCHEMA)
        sqlite_util.ensure_schema_version(self._conn, self.CURRENT_SCHEMA_VERSION)

    def close(self) -> None:
        self._conn.close()

    def schema_version(self) -> int:
        return sqlite_util.get_schema_version(self._conn)

    @contextmanager
    def transaction(self):
        self._conn.execute("BEGIN")
        try:
            yield
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")

    def start_run(self, *, run_id: str, slot_name: str, run_date: str, started_at: datetime) -> RunRecord:
        record = RunRecord(run_id=run_id, slot_name=slot_name, run_date=run_date, started_at=started_at, status=RunStatus.RUNNING)
        with self.transaction():
            self._conn.execute(
                "INSERT INTO scheduler_runs (run_id, slot_name, run_date, started_at, status, data_json) VALUES (?,?,?,?,?,?)",
                (record.run_id, record.slot_name, record.run_date, record.started_at.isoformat(), record.status.value, record.model_dump_json()),
            )
        return record

    def try_start_run(self, *, run_id: str, slot_name: str, run_date: str, started_at: datetime) -> RunRecord | None:
        """Atomic check-for-an-active-lock-then-insert, in ONE `BEGIN
        IMMEDIATE` transaction -- fixes a genuine TOCTOU race that
        `active_lock()` followed by a separate `start_run()` call has:
        two scheduler processes racing on the SAME run-db (e.g. an
        operator accidentally running both `schedule loop` and a
        cron-triggered `schedule tick` against one database) could both
        observe "no lock held" before either had inserted its own row,
        and both then start an overlapping run. `BEGIN IMMEDIATE`
        acquires SQLite's RESERVED write lock immediately, so the second
        caller's transaction blocks until the first COMMITs, then sees
        the first's row and returns None instead of inserting a second
        RUNNING record. Returns None (no row inserted) if a lock is
        already held; the returned RunRecord otherwise."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute("SELECT 1 FROM scheduler_runs WHERE status = ? LIMIT 1", (RunStatus.RUNNING.value,)).fetchone()
            if row is not None:
                self._conn.execute("ROLLBACK")
                return None
            record = RunRecord(run_id=run_id, slot_name=slot_name, run_date=run_date, started_at=started_at, status=RunStatus.RUNNING)
            self._conn.execute(
                "INSERT INTO scheduler_runs (run_id, slot_name, run_date, started_at, status, data_json) VALUES (?,?,?,?,?,?)",
                (record.run_id, record.slot_name, record.run_date, record.started_at.isoformat(), record.status.value, record.model_dump_json()),
            )
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")
        return record

    def finish_run(self, *, run_id: str, status: RunStatus, detail: str = "", error: str | None = None, finished_at: datetime | None = None) -> RunRecord:
        existing = self.get_run(run_id)
        if existing is None:
            raise ValueError(f"No scheduler run found with run_id={run_id!r} -- cannot finish a run that was never started.")
        updated = existing.model_copy(update={
            "finished_at": finished_at or datetime.now(timezone.utc),
            "status": status,
            "detail": detail,
            "error": error,
        })
        with self.transaction():
            self._conn.execute(
                "UPDATE scheduler_runs SET status = ?, data_json = ? WHERE run_id = ?",
                (updated.status.value, updated.model_dump_json(), run_id),
            )
        return updated

    def get_run(self, run_id: str) -> RunRecord | None:
        row = self._conn.execute("SELECT data_json FROM scheduler_runs WHERE run_id = ?", (run_id,)).fetchone()
        return sqlite_util.parse_model_json(RunRecord, row[0], row_identifier=run_id) if row else None

    def active_lock(self) -> RunRecord | None:
        """Any run still RUNNING (no finished_at) -- the overlap-prevention
        lock. At most one should ever exist if callers only ever start a
        run through `runner.run_tick` (which checks this first), but this
        reads ALL of them and returns the oldest, defensively, rather than
        assuming exactly zero-or-one."""
        rows = self._conn.execute(
            "SELECT data_json FROM scheduler_runs WHERE status = ? ORDER BY started_at ASC", (RunStatus.RUNNING.value,)
        ).fetchall()
        if not rows:
            return None
        return sqlite_util.parse_model_json(RunRecord, rows[0][0], row_identifier="active_lock")

    def reclaim_stale_locks(self, *, staleness_seconds: float, now: datetime | None = None) -> list[RunRecord]:
        """Restart recovery: a RUNNING row started more than
        `staleness_seconds` ago with no finished_at means the process
        that owned it is gone (crashed, killed, machine rebooted) --
        nothing will ever finish it. Mark every such row RECLAIMED so
        `active_lock()` stops seeing it as held, and return the
        reclaimed records for the caller to log/audit."""
        now = now or datetime.now(timezone.utc)
        rows = self._conn.execute(
            "SELECT data_json FROM scheduler_runs WHERE status = ?", (RunStatus.RUNNING.value,)
        ).fetchall()
        reclaimed = []
        for (data_json,) in rows:
            record = sqlite_util.parse_model_json(RunRecord, data_json, row_identifier="reclaim_stale_locks")
            age_seconds = (now - record.started_at).total_seconds()
            if age_seconds >= staleness_seconds:
                updated = self.finish_run(
                    run_id=record.run_id, status=RunStatus.RECLAIMED, finished_at=now,
                    detail=f"Reclaimed after {age_seconds:.0f}s with no completion -- the process that started this run is presumed gone.",
                )
                reclaimed.append(updated)
        return reclaimed

    def has_completed_today(self, *, slot_name: str, run_date: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM scheduler_runs WHERE slot_name = ? AND run_date = ? AND status = ? LIMIT 1",
            (slot_name, run_date, RunStatus.COMPLETED.value),
        ).fetchone()
        return row is not None

    def latest_run_for_slot_today(self, *, slot_name: str, run_date: str) -> RunRecord | None:
        row = self._conn.execute(
            "SELECT data_json FROM scheduler_runs WHERE slot_name = ? AND run_date = ? "
            "AND status IN (?, ?) ORDER BY started_at DESC LIMIT 1",
            (slot_name, run_date, RunStatus.COMPLETED.value, RunStatus.FAILED.value),
        ).fetchone()
        return sqlite_util.parse_model_json(RunRecord, row[0], row_identifier=f"slot_name={slot_name}") if row else None

    def list_runs(self, limit: int = 100) -> list[RunRecord]:
        rows = self._conn.execute(
            "SELECT data_json FROM scheduler_runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [sqlite_util.parse_model_json(RunRecord, r[0], row_identifier="list_runs") for r in rows]

    def last_successful_run_for_slot(self, slot_name: str) -> RunRecord | None:
        """Final-product-hardening: release-gate mission section 11 asks
        every scheduled job to be able to answer "last completed" and
        "last failed," not just today's -- distinct from
        `latest_run_for_slot_today` (deliberately date-scoped, used by
        `due_slot()`'s own frequency check). This answers "when did this
        job last actually succeed at all," which matters after a
        multi-day failure streak or a scheduler restart, when today's own
        history may show nothing but failures or nothing yet."""
        row = self._conn.execute(
            "SELECT data_json FROM scheduler_runs WHERE slot_name = ? AND status = ? ORDER BY started_at DESC LIMIT 1",
            (slot_name, RunStatus.COMPLETED.value),
        ).fetchone()
        return sqlite_util.parse_model_json(RunRecord, row[0], row_identifier=f"last_success:{slot_name}") if row else None

    def last_failed_run_for_slot(self, slot_name: str) -> RunRecord | None:
        """Symmetric with last_successful_run_for_slot -- surfaces the
        most recent failure (with its own `detail`/`error` fields) for an
        operator to see WHY a job has not been succeeding, without
        scrolling through `list_runs`'s full history to find it."""
        row = self._conn.execute(
            "SELECT data_json FROM scheduler_runs WHERE slot_name = ? AND status = ? ORDER BY started_at DESC LIMIT 1",
            (slot_name, RunStatus.FAILED.value),
        ).fetchone()
        return sqlite_util.parse_model_json(RunRecord, row[0], row_identifier=f"last_failure:{slot_name}") if row else None

    def consecutive_failures_for_slot(self, slot_name: str, *, limit: int = 1000) -> int:
        """Final-product-hardening (autonomous hardening cycle 3): how many
        of this slot's most recent FINISHED runs, counting back from the
        newest, are NOT a COMPLETED run -- i.e. FAILED or RECLAIMED,
        stopping at the first COMPLETED (or at `limit` runs, whichever
        comes first). A currently-RUNNING row is excluded, since
        `active_lock()`/`_check_scheduler` already covers "is a run stuck
        right now" separately from "has this job stopped succeeding."

        This exists because a genuinely sustained failure (e.g. a market-
        data provider outage lasting hours or days) previously left NO
        trace in `core.health.collect_system_health` at all: every tick
        correctly finishes with status=FAILED and releases its lock, so
        `_check_scheduler`'s old "is there an active/orphaned lock" check
        reported HEALTHY throughout -- the one place an operator is told
        to look for trouble stayed silent while a real, recurring
        production risk (a provider outage) went undetected for as long
        as it lasted."""
        rows = self._conn.execute(
            "SELECT status FROM scheduler_runs WHERE slot_name = ? AND status != ? ORDER BY started_at DESC LIMIT ?",
            (slot_name, RunStatus.RUNNING.value, limit),
        ).fetchall()
        streak = 0
        for (status,) in rows:
            if status == RunStatus.COMPLETED.value:
                break
            streak += 1
        return streak

    def distinct_slot_names(self) -> list[str]:
        """Every slot name that has ever actually run, derived from run
        history rather than a schedule config file -- so a per-slot
        summary works even when the caller has no config loaded (the
        default schedule, or a config that changed since some of these
        runs happened)."""
        rows = self._conn.execute("SELECT DISTINCT slot_name FROM scheduler_runs ORDER BY slot_name").fetchall()
        return [row[0] for row in rows]

    def integrity_check(self) -> str:
        """Phase 39 -- long-run operations: a read-only `PRAGMA
        integrity_check` an operator can run after days/weeks of
        unattended `schedule loop` operation, without writing raw SQL.
        Returns "ok" for a healthy database; anything else is SQLite's
        own list of corruption findings, joined by "; ". Final-product-
        hardening phase: now delegates to core.sqlite_util (the same
        capability was previously implemented only here; every other
        store can now offer it too without re-deriving this)."""
        return sqlite_util.integrity_check(self._conn)

    def db_size_bytes(self) -> int:
        return sqlite_util.db_size_bytes(self.db_path)
