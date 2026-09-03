"""Phase 21 -- decision persistence. Same convention as paper/store.py,
market_intelligence/store.py, and research/store.py: stdlib sqlite3, one
file, explicit transaction, data_json round-tripping through the real
Pydantic model's own validator. A decision is written once and never
updated in place -- the roadmap's "decision version is stored" criterion
plus this project's "no hindsight rewriting of history" principle,
applied here exactly as it already is to scan and research history.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from decision_engine.models import Decision

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    as_of TEXT NOT NULL,
    label TEXT NOT NULL,
    config_version TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_decisions_symbol_as_of ON decisions(symbol, as_of);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DecisionStore:
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

    def save_decision(self, decision: Decision) -> None:
        with self.transaction():
            self._conn.execute(
                "INSERT INTO decisions (decision_id, symbol, as_of, label, config_version, data_json, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    decision.decision_id, decision.symbol, decision.as_of.isoformat(), decision.label.value,
                    decision.config_version, decision.model_dump_json(), _now(),
                ),
            )

    def get_decision(self, decision_id: str) -> Decision | None:
        row = self._conn.execute("SELECT data_json FROM decisions WHERE decision_id = ?", (decision_id,)).fetchone()
        return Decision.model_validate_json(row[0]) if row else None

    def latest_decision_for_symbol(self, symbol: str) -> Decision | None:
        row = self._conn.execute(
            "SELECT data_json FROM decisions WHERE symbol = ? ORDER BY as_of DESC LIMIT 1",
            (symbol.strip().upper(),),
        ).fetchone()
        return Decision.model_validate_json(row[0]) if row else None

    def list_decisions_for_symbol(self, symbol: str, limit: int = 50) -> list[Decision]:
        rows = self._conn.execute(
            "SELECT data_json FROM decisions WHERE symbol = ? ORDER BY as_of DESC LIMIT ?",
            (symbol.strip().upper(), limit),
        ).fetchall()
        return [Decision.model_validate_json(r[0]) for r in rows]
