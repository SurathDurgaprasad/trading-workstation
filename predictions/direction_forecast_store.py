"""Persistence for predictions/direction_forecast.py -- same two-table,
append-only convention as predictions/store.py's PredictionStore
(forecasts / forecast_evaluations instead of predictions /
prediction_evaluations). Deliberately a separate store/database rather
than reusing PredictionStore's tables: a DirectionForecastRecord and a
PredictionRecord are structurally different models (no shared columns
beyond symbol/timestamps), and keeping them apart means an existing
predictions.db reader is never surprised by a differently-shaped row.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from predictions.direction_forecast import DirectionForecastEvaluation, DirectionForecastRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS forecasts (
    forecast_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    created_at TEXT NOT NULL,
    data_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS forecast_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    forecast_id TEXT NOT NULL REFERENCES forecasts(forecast_id),
    evaluated_at TEXT NOT NULL,
    resolved INTEGER NOT NULL,
    data_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_forecast_evaluations_forecast_id ON forecast_evaluations(forecast_id, evaluated_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DirectionForecastStore:
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

    # --- forecasts -----------------------------------------------------------

    def save_forecast(self, forecast: DirectionForecastRecord) -> None:
        with self.transaction():
            self._conn.execute(
                "INSERT INTO forecasts (forecast_id, symbol, created_at, data_json) VALUES (?,?,?,?)",
                (forecast.forecast_id, forecast.symbol, forecast.created_at.isoformat(), forecast.model_dump_json()),
            )

    def get_forecast(self, forecast_id: str) -> DirectionForecastRecord | None:
        row = self._conn.execute("SELECT data_json FROM forecasts WHERE forecast_id = ?", (forecast_id,)).fetchone()
        return DirectionForecastRecord.model_validate_json(row[0]) if row else None

    def list_forecasts(self, limit: int = 500) -> list[DirectionForecastRecord]:
        rows = self._conn.execute("SELECT data_json FROM forecasts ORDER BY created_at LIMIT ?", (limit,)).fetchall()
        return [DirectionForecastRecord.model_validate_json(r[0]) for r in rows]

    def has_forecast_for_bar(self, symbol: str, as_of: datetime) -> bool:
        """Same duplicate-prevention convention as predictions.store.
        PredictionStore.has_prediction_for_entry -- one forecast per
        symbol per bar, not one per report run."""
        existing = self.list_forecasts_for_symbol(symbol, limit=200)
        return any(f.as_of == as_of for f in existing)

    def list_forecasts_for_symbol(self, symbol: str, limit: int = 100) -> list[DirectionForecastRecord]:
        rows = self._conn.execute(
            "SELECT data_json FROM forecasts WHERE symbol = ? ORDER BY created_at DESC LIMIT ?",
            (symbol.strip().upper(), limit),
        ).fetchall()
        return [DirectionForecastRecord.model_validate_json(r[0]) for r in rows]

    def list_forecasts_needing_evaluation(self, limit: int = 500) -> list[DirectionForecastRecord]:
        all_forecasts = self.list_forecasts(limit=limit)
        result = []
        for forecast in all_forecasts:
            latest = self.latest_evaluation_for_forecast(forecast.forecast_id)
            if latest is None or not latest.resolved:
                result.append(forecast)
        return result

    # --- evaluations -----------------------------------------------------------

    def save_evaluation(self, evaluation: DirectionForecastEvaluation) -> None:
        with self.transaction():
            self._conn.execute(
                "INSERT INTO forecast_evaluations (evaluation_id, forecast_id, evaluated_at, resolved, data_json) VALUES (?,?,?,?,?)",
                (evaluation.evaluation_id, evaluation.forecast_id, evaluation.evaluated_at.isoformat(), int(evaluation.resolved), evaluation.model_dump_json()),
            )

    def list_evaluations_for_forecast(self, forecast_id: str) -> list[DirectionForecastEvaluation]:
        rows = self._conn.execute(
            "SELECT data_json FROM forecast_evaluations WHERE forecast_id = ? ORDER BY evaluated_at", (forecast_id,)
        ).fetchall()
        return [DirectionForecastEvaluation.model_validate_json(r[0]) for r in rows]

    def latest_evaluation_for_forecast(self, forecast_id: str) -> DirectionForecastEvaluation | None:
        row = self._conn.execute(
            "SELECT data_json FROM forecast_evaluations WHERE forecast_id = ? ORDER BY evaluated_at DESC LIMIT 1",
            (forecast_id,),
        ).fetchone()
        return DirectionForecastEvaluation.model_validate_json(row[0]) if row else None

    def list_all_evaluations(self, limit: int = 5000) -> list[DirectionForecastEvaluation]:
        rows = self._conn.execute("SELECT data_json FROM forecast_evaluations ORDER BY evaluated_at LIMIT ?", (limit,)).fetchall()
        return [DirectionForecastEvaluation.model_validate_json(r[0]) for r in rows]
