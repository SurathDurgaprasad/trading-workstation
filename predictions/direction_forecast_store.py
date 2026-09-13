"""Persistence for predictions/direction_forecast.py -- same two-table,
append-only convention as predictions/store.py's PredictionStore
(forecasts / forecast_evaluations instead of predictions /
prediction_evaluations). Deliberately a separate store/database rather
than reusing PredictionStore's tables: a DirectionForecastRecord and a
PredictionRecord are structurally different models (no shared columns
beyond symbol/timestamps), and keeping them apart means an existing
predictions.db reader is never surprised by a differently-shaped row.
"""

import json
import sqlite3

from core import sqlite_util
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from predictions.direction_forecast import DirectionForecastEvaluation, DirectionForecastRecord
from predictions.errors import DuplicateForecastError

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
    CURRENT_SCHEMA_VERSION = 1
    """Final-product-hardening: see core.sqlite_util.ensure_schema_version's
    docstring, and predictions/store.py::PredictionStore's own identical
    note -- this store's real schema evolution is tracked by
    `duplicate_prevention_enforced_at_db_level`, more precise than a
    version bump here."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._conn = sqlite_util.connect(self.db_path)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self.duplicate_prevention_enforced_at_db_level = self._migrate_as_of_column_and_unique_index()
        sqlite_util.ensure_schema_version(self._conn, self.CURRENT_SCHEMA_VERSION)

    def schema_version(self) -> int:
        return sqlite_util.get_schema_version(self._conn)

    def _migrate_as_of_column_and_unique_index(self) -> bool:
        """Final-product-hardening: same migration as predictions/store.py's
        PredictionStore._migrate_entry_time_column_and_unique_index -- see
        its docstring for the full rationale. has_forecast_for_bar's own
        check-then-insert is non-atomic; this adds a real `as_of` column
        (backfilled from each row's own data_json) and a genuine
        UNIQUE(symbol, as_of) index, skipped gracefully (never crashing
        startup or deleting data) if a pre-existing database already has
        duplicate rows on that key."""
        sqlite_util.ensure_column(self._conn, "forecasts", "as_of", "TEXT")
        rows = self._conn.execute("SELECT forecast_id, data_json FROM forecasts WHERE as_of IS NULL").fetchall()
        for forecast_id, data_json in rows:
            as_of = json.loads(data_json)["as_of"]
            self._conn.execute("UPDATE forecasts SET as_of = ? WHERE forecast_id = ?", (as_of, forecast_id))
        return sqlite_util.try_create_unique_index(
            self._conn, index_name="idx_forecasts_symbol_as_of", table="forecasts", columns="symbol, as_of"
        )

    def close(self) -> None:
        self._conn.close()

    def integrity_check(self) -> str:
        """Final-product-hardening: PRAGMA integrity_check, extended to
        every store -- see core.sqlite_util.integrity_check's docstring."""
        return sqlite_util.integrity_check(self._conn)

    def db_size_bytes(self) -> int:
        return sqlite_util.db_size_bytes(self.db_path)

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
        """Raises DuplicateForecastError if the DB-level UNIQUE(symbol,
        as_of) constraint is active and this exact symbol+bar was
        already recorded -- see _migrate_as_of_column_and_unique_index."""
        try:
            with self.transaction():
                self._conn.execute(
                    "INSERT INTO forecasts (forecast_id, symbol, created_at, as_of, data_json) VALUES (?,?,?,?,?)",
                    (forecast.forecast_id, forecast.symbol, forecast.created_at.isoformat(), forecast.as_of.isoformat(), forecast.model_dump_json()),
                )
        except sqlite3.IntegrityError as exc:
            if "UNIQUE constraint failed" not in str(exc):
                raise
            raise DuplicateForecastError(symbol=forecast.symbol, as_of=forecast.as_of) from exc

    def get_forecast(self, forecast_id: str) -> DirectionForecastRecord | None:
        row = self._conn.execute("SELECT data_json FROM forecasts WHERE forecast_id = ?", (forecast_id,)).fetchone()
        return sqlite_util.parse_model_json(DirectionForecastRecord, row[0], row_identifier=forecast_id) if row else None

    def list_forecasts(self, limit: int = 500) -> list[DirectionForecastRecord]:
        rows = self._conn.execute("SELECT data_json FROM forecasts ORDER BY created_at LIMIT ?", (limit,)).fetchall()
        return [sqlite_util.parse_model_json(DirectionForecastRecord, r[0], row_identifier="list_forecasts") for r in rows]

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
        return [sqlite_util.parse_model_json(DirectionForecastRecord, r[0], row_identifier=f"symbol={symbol}") for r in rows]

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
        return [sqlite_util.parse_model_json(DirectionForecastEvaluation, r[0], row_identifier=f"forecast_id={forecast_id}") for r in rows]

    def latest_evaluation_for_forecast(self, forecast_id: str) -> DirectionForecastEvaluation | None:
        row = self._conn.execute(
            "SELECT data_json FROM forecast_evaluations WHERE forecast_id = ? ORDER BY evaluated_at DESC LIMIT 1",
            (forecast_id,),
        ).fetchone()
        return sqlite_util.parse_model_json(DirectionForecastEvaluation, row[0], row_identifier=f"forecast_id={forecast_id}") if row else None

    def list_all_evaluations(self, limit: int = 5000) -> list[DirectionForecastEvaluation]:
        rows = self._conn.execute("SELECT data_json FROM forecast_evaluations ORDER BY evaluated_at LIMIT ?", (limit,)).fetchall()
        return [sqlite_util.parse_model_json(DirectionForecastEvaluation, r[0], row_identifier="list_all_evaluations") for r in rows]
