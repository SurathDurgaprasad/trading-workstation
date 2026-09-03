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
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, isolation_level=None)
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

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
        return RunRecord.model_validate_json(row[0]) if row else None

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
        return RunRecord.model_validate_json(rows[0][0])

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
            record = RunRecord.model_validate_json(data_json)
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
        return RunRecord.model_validate_json(row[0]) if row else None

    def list_runs(self, limit: int = 100) -> list[RunRecord]:
        rows = self._conn.execute(
            "SELECT data_json FROM scheduler_runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [RunRecord.model_validate_json(r[0]) for r in rows]

    def integrity_check(self) -> str:
        """Phase 39 -- long-run operations: a read-only `PRAGMA
        integrity_check` an operator can run after days/weeks of
        unattended `schedule loop` operation, without writing raw SQL.
        Returns "ok" for a healthy database; anything else is SQLite's
        own list of corruption findings, joined by "; "."""
        rows = self._conn.execute("PRAGMA integrity_check").fetchall()
        results = [row[0] for row in rows]
        return "; ".join(results) if results else "ok"

    def db_size_bytes(self) -> int:
        return Path(self.db_path).stat().st_size if Path(self.db_path).exists() else 0
