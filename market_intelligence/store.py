"""Phase 19 -- scanner history persistence. Same convention as
paper/store.py: stdlib sqlite3, one file, explicit transaction, each row's
`data_json` round-tripping through the real Pydantic model's own
validator -- never a hand-built dict bypassing ScanReport's validation.

Existing to satisfy the roadmap's own Phase 18/19 requirement ("Market
state can be persisted" / "Historical scanner output is stored") --
mutation-free: a report is written once and never updated in place,
matching the project's "no hindsight rewriting of history" principle
(roadmap §13), which applies just as much to scan history as to
prediction history.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from market_intelligence.models import ScanReport

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scan_reports (
    scan_id TEXT PRIMARY KEY,
    as_of TEXT NOT NULL,
    universe_mode TEXT NOT NULL,
    config_version TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scan_reports_as_of ON scan_reports(as_of);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ScanHistoryStore:
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

    def save_report(self, report: ScanReport) -> None:
        with self.transaction():
            self._conn.execute(
                "INSERT INTO scan_reports (scan_id, as_of, universe_mode, config_version, data_json, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (report.scan_id, report.as_of.isoformat(), report.universe_mode, report.config_version, report.model_dump_json(), _now()),
            )

    def get_report(self, scan_id: str) -> ScanReport | None:
        row = self._conn.execute("SELECT data_json FROM scan_reports WHERE scan_id = ?", (scan_id,)).fetchone()
        return ScanReport.model_validate_json(row[0]) if row else None

    def latest_report(self) -> ScanReport | None:
        row = self._conn.execute("SELECT data_json FROM scan_reports ORDER BY as_of DESC LIMIT 1").fetchone()
        return ScanReport.model_validate_json(row[0]) if row else None

    def list_reports(self, limit: int = 50) -> list[ScanReport]:
        rows = self._conn.execute(
            "SELECT data_json FROM scan_reports ORDER BY as_of DESC LIMIT ?", (limit,)
        ).fetchall()
        return [ScanReport.model_validate_json(r[0]) for r in rows]
