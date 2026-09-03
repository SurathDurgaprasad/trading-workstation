"""Phase 20 -- research report persistence. Same convention as
paper/store.py and market_intelligence/store.py: stdlib sqlite3, one
file, explicit transaction, data_json round-tripping through the real
Pydantic model's own validator. A report is written once and never
updated in place -- no hindsight rewriting of research history, the same
principle market_intelligence/store.py already applies to scan history.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from research.models import ResearchReport

_SCHEMA = """
CREATE TABLE IF NOT EXISTS research_reports (
    report_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    as_of TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_research_reports_symbol_as_of ON research_reports(symbol, as_of);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ResearchStore:
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

    def save_report(self, report: ResearchReport) -> None:
        with self.transaction():
            self._conn.execute(
                "INSERT INTO research_reports (report_id, symbol, as_of, data_json, created_at) VALUES (?,?,?,?,?)",
                (report.report_id, report.symbol, report.as_of.isoformat(), report.model_dump_json(), _now()),
            )

    def get_report(self, report_id: str) -> ResearchReport | None:
        row = self._conn.execute("SELECT data_json FROM research_reports WHERE report_id = ?", (report_id,)).fetchone()
        return ResearchReport.model_validate_json(row[0]) if row else None

    def latest_report_for_symbol(self, symbol: str) -> ResearchReport | None:
        row = self._conn.execute(
            "SELECT data_json FROM research_reports WHERE symbol = ? ORDER BY as_of DESC LIMIT 1",
            (symbol.strip().upper(),),
        ).fetchone()
        return ResearchReport.model_validate_json(row[0]) if row else None

    def list_reports_for_symbol(self, symbol: str, limit: int = 50) -> list[ResearchReport]:
        rows = self._conn.execute(
            "SELECT data_json FROM research_reports WHERE symbol = ? ORDER BY as_of DESC LIMIT ?",
            (symbol.strip().upper(), limit),
        ).fetchall()
        return [ResearchReport.model_validate_json(r[0]) for r in rows]
