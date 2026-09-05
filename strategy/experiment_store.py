"""Scientific strategy research foundation, Priority #1 -- SQLite
persistence for every ExperimentRecord ever built. Append-only, exactly
mirroring strategy/promotion_store.py's own established convention
(stdlib sqlite3, one file, one connection, explicit BEGIN/COMMIT/
ROLLBACK): rows are never updated or deleted, only inserted, so an
experiment's full history -- including a hypothesis that was later
found to have been overfit, or a manifest that was later superseded --
always remains visible, never quietly overwritten. "No silent
overwrites" is this project's own explicit rule for this registry.

A NEW, small store scoped to strategy/, with its OWN sqlite3 connection
to its OWN db file -- does not reach into promotion_store.py's or
live/state_store.py's internals.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from strategy.experiment_registry import ExperimentRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiment_log (
    experiment_id TEXT PRIMARY KEY,
    hypothesis_id TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    verdict TEXT NOT NULL,
    data_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExperimentRegistryStore:
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

    def record_experiment(self, record: ExperimentRecord) -> str:
        """Inserts ONE new, permanent row keyed by the record's OWN
        experiment_id (already a fresh UUID from build_experiment_record)
        -- attempting to insert the SAME experiment_id twice raises
        sqlite3's own IntegrityError (PRIMARY KEY violation) rather than
        silently overwriting, since experiment_id is generated fresh per
        record and should never collide in real use."""
        with self.transaction():
            self._conn.execute(
                "INSERT INTO experiment_log (experiment_id, hypothesis_id, manifest_hash, strategy_id, verdict, data_json, recorded_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    record.experiment_id, record.hypothesis_id, record.manifest_hash, record.strategy_id,
                    record.evaluation.verdict.value, record.model_dump_json(), _now(),
                ),
            )
        return record.experiment_id

    def get(self, experiment_id: str) -> ExperimentRecord | None:
        row = self._conn.execute(
            "SELECT data_json FROM experiment_log WHERE experiment_id = ?", (experiment_id,)
        ).fetchone()
        return ExperimentRecord.model_validate_json(row[0]) if row else None

    def history_for_hypothesis(self, hypothesis_id: str) -> list[ExperimentRecord]:
        """Every experiment ever recorded for this hypothesis, oldest
        first -- never hides a past result behind a later, more
        favorable re-run of the same hypothesis."""
        rows = self._conn.execute(
            "SELECT data_json FROM experiment_log WHERE hypothesis_id = ? ORDER BY recorded_at ASC",
            (hypothesis_id,),
        ).fetchall()
        return [ExperimentRecord.model_validate_json(row[0]) for row in rows]

    def history_for_manifest_hash(self, manifest_hash: str) -> list[ExperimentRecord]:
        """Every experiment ever recorded against this EXACT strategy
        configuration (content-hashed) -- distinct from history_for_
        hypothesis, since one hypothesis can be tested with several
        manifests (different universes/cost models) and one manifest can
        be referenced by several hypotheses (e.g. a regime-consistency
        check reusing the frozen baseline's own manifest)."""
        rows = self._conn.execute(
            "SELECT data_json FROM experiment_log WHERE manifest_hash = ? ORDER BY recorded_at ASC",
            (manifest_hash,),
        ).fetchall()
        return [ExperimentRecord.model_validate_json(row[0]) for row in rows]

    def all_experiments(self) -> list[ExperimentRecord]:
        """Every experiment ever recorded, oldest first -- the full,
        immutable history this registry exists to preserve."""
        rows = self._conn.execute("SELECT data_json FROM experiment_log ORDER BY recorded_at ASC").fetchall()
        return [ExperimentRecord.model_validate_json(row[0]) for row in rows]
