"""Phase 23 -- prediction persistence. Two linked, append-only tables --
the first genuinely multi-table store among this session's new packages
(market_intelligence/research/decision_engine's stores are all single-
table; paper/store.py's signals/risk_decisions/orders/fills/positions/
trades split is the closest existing precedent for linking related
records by ID across tables rather than mutating one).

No update_prediction or update_evaluation method exists anywhere in this
class -- a prediction, once recorded, is never rewritten; what happens
to it later is always a NEW row in prediction_evaluations, referencing
the original by prediction_id.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from predictions.models import PredictionEvaluation, PredictionOutcomeState, PredictionRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    created_at TEXT NOT NULL,
    data_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prediction_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    prediction_id TEXT NOT NULL REFERENCES predictions(prediction_id),
    evaluated_at TEXT NOT NULL,
    outcome TEXT NOT NULL,
    data_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prediction_evaluations_prediction_id ON prediction_evaluations(prediction_id, evaluated_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PredictionStore:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, isolation_level=None)
        self._conn.execute("PRAGMA foreign_keys = ON")
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

    # --- predictions -------------------------------------------------------

    def save_prediction(self, prediction: PredictionRecord) -> None:
        with self.transaction():
            self._conn.execute(
                "INSERT INTO predictions (prediction_id, decision_id, symbol, created_at, data_json) VALUES (?,?,?,?,?)",
                (prediction.prediction_id, prediction.decision_id, prediction.symbol, prediction.created_at.isoformat(), prediction.model_dump_json()),
            )

    def get_prediction(self, prediction_id: str) -> PredictionRecord | None:
        row = self._conn.execute("SELECT data_json FROM predictions WHERE prediction_id = ?", (prediction_id,)).fetchone()
        return PredictionRecord.model_validate_json(row[0]) if row else None

    def list_predictions(self, limit: int = 200) -> list[PredictionRecord]:
        rows = self._conn.execute("SELECT data_json FROM predictions ORDER BY created_at LIMIT ?", (limit,)).fetchall()
        return [PredictionRecord.model_validate_json(r[0]) for r in rows]

    def list_predictions_needing_evaluation(self, limit: int = 200) -> list[PredictionRecord]:
        """A prediction needs evaluation if it has no evaluation yet, or its
        most recent evaluation's outcome is still ACTIVE. Resolved
        (TARGET_HIT/STOP_HIT), EXPIRED, and INSUFFICIENT_DATA predictions
        are done -- re-evaluating them would only ever repeat the same
        historical answer, since the bars that resolved them don't change."""
        all_predictions = self.list_predictions(limit=limit)
        result = []
        for prediction in all_predictions:
            latest = self.latest_evaluation_for_prediction(prediction.prediction_id)
            if latest is None or latest.outcome == PredictionOutcomeState.ACTIVE:
                result.append(prediction)
        return result

    # --- evaluations ---------------------------------------------------------

    def save_evaluation(self, evaluation: PredictionEvaluation) -> None:
        with self.transaction():
            self._conn.execute(
                "INSERT INTO prediction_evaluations (evaluation_id, prediction_id, evaluated_at, outcome, data_json) VALUES (?,?,?,?,?)",
                (evaluation.evaluation_id, evaluation.prediction_id, evaluation.evaluated_at.isoformat(), evaluation.outcome.value, evaluation.model_dump_json()),
            )

    def list_evaluations_for_prediction(self, prediction_id: str) -> list[PredictionEvaluation]:
        rows = self._conn.execute(
            "SELECT data_json FROM prediction_evaluations WHERE prediction_id = ? ORDER BY evaluated_at",
            (prediction_id,),
        ).fetchall()
        return [PredictionEvaluation.model_validate_json(r[0]) for r in rows]

    def latest_evaluation_for_prediction(self, prediction_id: str) -> PredictionEvaluation | None:
        row = self._conn.execute(
            "SELECT data_json FROM prediction_evaluations WHERE prediction_id = ? ORDER BY evaluated_at DESC LIMIT 1",
            (prediction_id,),
        ).fetchone()
        return PredictionEvaluation.model_validate_json(row[0]) if row else None

    def list_all_evaluations(self, limit: int = 2000) -> list[PredictionEvaluation]:
        rows = self._conn.execute("SELECT data_json FROM prediction_evaluations ORDER BY evaluated_at LIMIT ?", (limit,)).fetchall()
        return [PredictionEvaluation.model_validate_json(r[0]) for r in rows]
