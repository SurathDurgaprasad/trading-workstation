"""Strategy science, Phase 6 -- SQLite persistence for every promotion-
gate evaluation ever run (spec: "never hide negative results", "never
silently modify strategy parameters"). Append-only audit trail: rows
are never updated or deleted, only inserted, so a candidate's full
history -- including every past NEGATIVE/REJECTED verdict -- always
remains visible, never quietly overwritten by a later re-evaluation.

A NEW, small store scoped to strategy/, with its OWN sqlite3 connection
to its OWN db file -- mirrors live/state_store.py's own convention
(spec §9: "if no suitable persistence exists, use SQLite"; one file,
one connection, explicit BEGIN/COMMIT/ROLLBACK per spec §10) without
reaching into paper/store.py's or live/state_store.py's internals.
"""

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from strategy.promotion_gate import PromotionEvaluation

_SCHEMA = """
CREATE TABLE IF NOT EXISTS promotion_log (
    evaluation_id TEXT PRIMARY KEY,
    candidate_name TEXT NOT NULL,
    verdict TEXT NOT NULL,
    data_json TEXT NOT NULL,
    evaluated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PromotionGateStore:
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

    def record_evaluation(self, evaluation: PromotionEvaluation) -> str:
        """Inserts ONE new, permanent row (never an update -- re-evaluating
        the same candidate again always adds another row, never replaces
        the last one) and returns the generated evaluation_id."""
        evaluation_id = str(uuid.uuid4())
        with self.transaction():
            self._conn.execute(
                "INSERT INTO promotion_log (evaluation_id, candidate_name, verdict, data_json, evaluated_at) "
                "VALUES (?,?,?,?,?)",
                (evaluation_id, evaluation.candidate_name, evaluation.verdict.value, evaluation.model_dump_json(), _now()),
            )
        return evaluation_id

    def get(self, evaluation_id: str) -> PromotionEvaluation | None:
        row = self._conn.execute(
            "SELECT data_json FROM promotion_log WHERE evaluation_id = ?", (evaluation_id,)
        ).fetchone()
        return PromotionEvaluation.model_validate_json(row[0]) if row else None

    def history_for_candidate(self, candidate_name: str) -> list[PromotionEvaluation]:
        """Every evaluation ever recorded for this candidate, oldest
        first -- never hides a past negative result behind a later,
        more favorable one."""
        rows = self._conn.execute(
            "SELECT data_json FROM promotion_log WHERE candidate_name = ? ORDER BY evaluated_at ASC",
            (candidate_name,),
        ).fetchall()
        return [PromotionEvaluation.model_validate_json(row[0]) for row in rows]

    def latest_for_candidate(self, candidate_name: str) -> PromotionEvaluation | None:
        history = self.history_for_candidate(candidate_name)
        return history[-1] if history else None
