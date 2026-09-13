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

import json
import sqlite3

from core import sqlite_util
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from predictions.errors import DuplicatePredictionError
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
    CURRENT_SCHEMA_VERSION = 1
    """Final-product-hardening: see core.sqlite_util.ensure_schema_version's
    docstring for why this is PRAGMA user_version, not a table. This
    store's real schema evolution (the entry_time column + unique index)
    is tracked by its own `duplicate_prevention_enforced_at_db_level`
    flag, which is more precise than a version bump here (it captures
    "did the migration actually succeed on THIS database," not just
    "has this code run against it") -- CURRENT_SCHEMA_VERSION stays at
    1, consistent with every other store, as a general schema-identity
    marker for future changes."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._conn = sqlite_util.connect(self.db_path)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self.duplicate_prevention_enforced_at_db_level = self._migrate_entry_time_column_and_unique_index()
        sqlite_util.ensure_schema_version(self._conn, self.CURRENT_SCHEMA_VERSION)

    def schema_version(self) -> int:
        return sqlite_util.get_schema_version(self._conn)

    def _migrate_entry_time_column_and_unique_index(self) -> bool:
        """Final-product-hardening: `has_prediction_for_entry` (below)
        was, until this migration, the ONLY duplicate-prevention this
        table had -- an application-level check-then-insert with no
        transaction spanning the check and the insert, so two concurrent
        callers (e.g. a manual `predict` overlapping a scheduled one)
        could both pass the check and double-insert a prediction for the
        same symbol+entry bar. `prediction_id` is a UUID surrogate key
        that never collides in practice, so the PRIMARY KEY alone gave
        no protection against this.

        Adds a real `entry_time` column (previously only inside each
        row's opaque `data_json` blob) via core.sqlite_util.ensure_column
        (safe on an existing production predictions.db -- additive, does
        not touch existing rows' data_json), backfills it for any
        pre-existing rows by parsing their own data_json (their own
        already-recorded truth, not a guess), then attempts a genuine
        UNIQUE(symbol, entry_time) index. If an already-deployed database
        happens to already contain duplicate (symbol, entry_time) rows
        (possible under the old app-level-only check), the index
        creation is skipped rather than crashing startup or silently
        deleting a row -- see core.sqlite_util.try_create_unique_index's
        own docstring. Returns whether the DB-level constraint is
        actually active, surfaced via `duplicate_prevention_enforced_at_db_level`
        so a caller/health-check can know which guarantee it's actually
        getting rather than assuming the stronger one always holds."""
        sqlite_util.ensure_column(self._conn, "predictions", "entry_time", "TEXT")
        rows = self._conn.execute(
            "SELECT prediction_id, data_json FROM predictions WHERE entry_time IS NULL"
        ).fetchall()
        for prediction_id, data_json in rows:
            entry_time = json.loads(data_json)["entry_time"]
            self._conn.execute("UPDATE predictions SET entry_time = ? WHERE prediction_id = ?", (entry_time, prediction_id))
        return sqlite_util.try_create_unique_index(
            self._conn, index_name="idx_predictions_symbol_entry_time", table="predictions", columns="symbol, entry_time"
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

    # --- predictions -------------------------------------------------------

    def save_prediction(self, prediction: PredictionRecord) -> None:
        """Raises DuplicatePredictionError if the DB-level UNIQUE(symbol,
        entry_time) constraint is active (see
        _migrate_entry_time_column_and_unique_index) and this exact
        symbol+entry_time was already recorded -- an atomic guarantee
        `has_prediction_for_entry`'s check-then-insert alone cannot give,
        since two callers can both pass that check before either has
        inserted. If the constraint is not active (a pre-existing
        database with unresolved historical duplicates -- see
        `duplicate_prevention_enforced_at_db_level`), this still
        succeeds, matching the prior behavior exactly."""
        try:
            with self.transaction():
                self._conn.execute(
                    "INSERT INTO predictions (prediction_id, decision_id, symbol, created_at, entry_time, data_json) VALUES (?,?,?,?,?,?)",
                    (
                        prediction.prediction_id, prediction.decision_id, prediction.symbol,
                        prediction.created_at.isoformat(), prediction.entry_time.isoformat(), prediction.model_dump_json(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if "UNIQUE constraint failed" not in str(exc):
                raise
            raise DuplicatePredictionError(symbol=prediction.symbol, entry_time=prediction.entry_time) from exc

    def get_prediction(self, prediction_id: str) -> PredictionRecord | None:
        row = self._conn.execute("SELECT data_json FROM predictions WHERE prediction_id = ?", (prediction_id,)).fetchone()
        return PredictionRecord.model_validate_json(row[0]) if row else None

    def list_predictions(self, limit: int = 200) -> list[PredictionRecord]:
        rows = self._conn.execute("SELECT data_json FROM predictions ORDER BY created_at LIMIT ?", (limit,)).fetchall()
        return [PredictionRecord.model_validate_json(r[0]) for r in rows]

    def has_prediction_for_entry(self, symbol: str, entry_time: datetime) -> bool:
        """Phase 36 -- duplicate-prevention check: has a prediction
        already been recorded for this exact symbol + entry bar?
        `entry_time` is bar-granularity (the market_context.as_of the
        signal was priced against), so this naturally catches "the same
        day's data was recorded twice" (e.g. shadow-run run twice against
        an unchanged daily bar) while still allowing a genuinely NEW
        prediction on the next bar/day. Filters in Python over the
        existing symbol-scoped listing rather than adding an indexed
        column -- personal-scale data volumes don't need one, and this
        avoids a schema migration for an existing table."""
        existing = self.list_predictions_for_symbol(symbol, limit=200)
        return any(p.entry_time == entry_time for p in existing)

    def list_predictions_for_symbol(self, symbol: str, limit: int = 50) -> list[PredictionRecord]:
        """Phase 35 -- same convention as decision_engine.store.DecisionStore.
        list_decisions_for_symbol / research.store.ResearchStore.
        list_reports_for_symbol. Most recent first (unlike list_predictions,
        which is oldest-first for evaluate's own processing order) -- a
        dashboard reader wants the latest prediction at the top."""
        rows = self._conn.execute(
            "SELECT data_json FROM predictions WHERE symbol = ? ORDER BY created_at DESC LIMIT ?",
            (symbol.strip().upper(), limit),
        ).fetchall()
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
