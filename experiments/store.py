"""Phase 37 -- experiment persistence. Same convention as predictions/
store.py's two-table, append-only design: stdlib sqlite3, explicit
transactions, data_json round-tripping through the real Pydantic model's
own validator. No update_experiment method exists -- an experiment,
once registered, is never rewritten; what happens to it later (ended,
annotated) is always a NEW row in experiment_events.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from experiments.models import Experiment, ExperimentEvent, ExperimentEventType

_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    config_type TEXT NOT NULL,
    config_version TEXT NOT NULL,
    started_at TEXT NOT NULL,
    data_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiment_events (
    event_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    data_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_experiment_events_experiment_id ON experiment_events(experiment_id, occurred_at);
"""


class ExperimentStore:
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

    # --- experiments ---------------------------------------------------------

    def save_experiment(self, experiment: Experiment) -> None:
        with self.transaction():
            self._conn.execute(
                "INSERT INTO experiments (experiment_id, name, config_type, config_version, started_at, data_json) VALUES (?,?,?,?,?,?)",
                (
                    experiment.experiment_id, experiment.name, experiment.config_type.value,
                    experiment.config_version, experiment.started_at.isoformat(), experiment.model_dump_json(),
                ),
            )

    def get_experiment(self, experiment_id: str) -> Experiment | None:
        row = self._conn.execute("SELECT data_json FROM experiments WHERE experiment_id = ?", (experiment_id,)).fetchone()
        return Experiment.model_validate_json(row[0]) if row else None

    def list_experiments(self, limit: int = 200) -> list[Experiment]:
        rows = self._conn.execute("SELECT data_json FROM experiments ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
        return [Experiment.model_validate_json(r[0]) for r in rows]

    # --- events ------------------------------------------------------------------

    def save_event(self, event: ExperimentEvent) -> None:
        with self.transaction():
            self._conn.execute(
                "INSERT INTO experiment_events (event_id, experiment_id, event_type, occurred_at, data_json) VALUES (?,?,?,?,?)",
                (event.event_id, event.experiment_id, event.event_type.value, event.occurred_at.isoformat(), event.model_dump_json()),
            )

    def list_events_for_experiment(self, experiment_id: str) -> list[ExperimentEvent]:
        rows = self._conn.execute(
            "SELECT data_json FROM experiment_events WHERE experiment_id = ? ORDER BY occurred_at",
            (experiment_id,),
        ).fetchall()
        return [ExperimentEvent.model_validate_json(r[0]) for r in rows]

    def latest_event_for_experiment(self, experiment_id: str) -> ExperimentEvent | None:
        row = self._conn.execute(
            "SELECT data_json FROM experiment_events WHERE experiment_id = ? ORDER BY occurred_at DESC LIMIT 1",
            (experiment_id,),
        ).fetchone()
        return ExperimentEvent.model_validate_json(row[0]) if row else None

    def is_ended(self, experiment_id: str) -> bool:
        """Derived from the latest event -- never a stored mutable flag.
        A NOTE event after an ENDED event does not "reopen" the
        experiment; only the single latest event's type matters, and an
        experiment is never expected to emit an event after ENDED in
        normal use (the CLI's own `experiment end` is the only writer of
        ENDED events, and refuses to run twice -- see main.py)."""
        latest = self.latest_event_for_experiment(experiment_id)
        return latest is not None and latest.event_type == ExperimentEventType.ENDED

    def ended_at(self, experiment_id: str):
        """Returns the occurred_at of the ENDED event, if any, else None."""
        events = self.list_events_for_experiment(experiment_id)
        for event in reversed(events):
            if event.event_type == ExperimentEventType.ENDED:
                return event.occurred_at
        return None
