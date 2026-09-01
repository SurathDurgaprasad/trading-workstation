"""Phase 13 §14 — SQLite persistence for pending approvals and the kill
switch. A NEW, small store scoped to live/ with its OWN sqlite3 connection
to the SAME db file PaperStore already uses (or a dedicated one) — multiple
connections to one SQLite file are standard and safe; this deliberately
does NOT reach into PaperStore's internals or modify paper/store.py's
schema (spec: "do not blindly refactor").

Two tables:
  - pending_approvals: one row per signal ever sent to
    PENDING_HUMAN_APPROVAL, updated in place as its lifecycle advances —
    this is the durable audit trail spec §3 requires (signal_id,
    strategy_version, risk_config_version, requested/approved quantity,
    human decision, decision timestamp/reason, final execution result).
  - kill_switch: a single row, survives restart, requires an explicit
    reset (spec §8).
"""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from strategy.signal import Signal

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pending_approvals (
    signal_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    signal_json TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    risk_config_version TEXT NOT NULL,
    requested_quantity INTEGER NOT NULL,
    state TEXT NOT NULL,
    history_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    decided_at TEXT,
    decision TEXT,
    decision_reason TEXT,
    approved_quantity INTEGER,
    final_execution_result TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kill_switch (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    active INTEGER NOT NULL,
    activated_at TEXT,
    reason TEXT,
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PendingApprovalRecord:
    signal_id: str
    symbol: str
    signal: Signal
    strategy_version: str
    risk_config_version: str
    requested_quantity: int
    state: str
    history: list[tuple[str, str]]
    created_at: str
    expires_at: str
    decided_at: str | None = None
    decision: str | None = None
    decision_reason: str | None = None
    approved_quantity: int | None = None
    final_execution_result: str | None = None


class LiveStateStore:
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

    # --- pending approvals ---------------------------------------------------

    def save_pending_approval(
        self, *, signal: Signal, strategy_version: str, risk_config_version: str,
        requested_quantity: int, state: str, history: list[tuple], created_at: datetime, expires_at: datetime,
    ) -> None:
        signal_id = signal.stable_id()
        history_json = _serialize_history(history)
        self._conn.execute(
            "INSERT INTO pending_approvals "
            "(signal_id, symbol, signal_json, strategy_version, risk_config_version, requested_quantity, "
            " state, history_json, created_at, expires_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(signal_id) DO UPDATE SET state=excluded.state, history_json=excluded.history_json, updated_at=excluded.updated_at",
            (signal_id, signal.symbol, signal.model_dump_json(), strategy_version, risk_config_version, requested_quantity,
             state, history_json, created_at.isoformat(), expires_at.isoformat(), _now()),
        )

    def update_decision(
        self, signal_id: str, *, state: str, history: list[tuple], decision: str | None = None,
        decision_reason: str | None = None, approved_quantity: int | None = None, final_execution_result: str | None = None,
        decided_at: datetime | None = None,
    ) -> None:
        self._conn.execute(
            "UPDATE pending_approvals SET state=?, history_json=?, decision=?, decision_reason=?, "
            "approved_quantity=?, final_execution_result=?, decided_at=?, updated_at=? WHERE signal_id=?",
            (state, _serialize_history(history), decision, decision_reason, approved_quantity, final_execution_result,
             decided_at.isoformat() if decided_at else None, _now(), signal_id),
        )

    def get(self, signal_id: str) -> PendingApprovalRecord | None:
        row = self._conn.execute("SELECT * FROM pending_approvals WHERE signal_id = ?", (signal_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def list_pending(self) -> list[PendingApprovalRecord]:
        """Only rows still in PENDING_HUMAN_APPROVAL -- used to restore
        in-memory pipeline state after a restart."""
        rows = self._conn.execute("SELECT * FROM pending_approvals WHERE state = 'PENDING_HUMAN_APPROVAL'").fetchall()
        return [self._row_to_record(r) for r in rows]

    def list_all(self) -> list[PendingApprovalRecord]:
        rows = self._conn.execute("SELECT * FROM pending_approvals ORDER BY created_at").fetchall()
        return [self._row_to_record(r) for r in rows]

    def _row_to_record(self, row) -> PendingApprovalRecord:
        cols = [d[0] for d in self._conn.execute("SELECT * FROM pending_approvals LIMIT 0").description]
        d = dict(zip(cols, row))
        return PendingApprovalRecord(
            signal_id=d["signal_id"], symbol=d["symbol"], signal=Signal.model_validate_json(d["signal_json"]),
            strategy_version=d["strategy_version"], risk_config_version=d["risk_config_version"],
            requested_quantity=d["requested_quantity"], state=d["state"], history=_deserialize_history(d["history_json"]),
            created_at=d["created_at"], expires_at=d["expires_at"], decided_at=d["decided_at"], decision=d["decision"],
            decision_reason=d["decision_reason"], approved_quantity=d["approved_quantity"],
            final_execution_result=d["final_execution_result"],
        )

    # --- kill switch -----------------------------------------------------------

    def is_kill_switch_active(self) -> bool:
        row = self._conn.execute("SELECT active FROM kill_switch WHERE id = 1").fetchone()
        return bool(row[0]) if row else False

    def kill_switch_state(self) -> tuple[bool, str | None, str | None]:
        """(active, activated_at, reason)."""
        row = self._conn.execute("SELECT active, activated_at, reason FROM kill_switch WHERE id = 1").fetchone()
        if row is None:
            return (False, None, None)
        return (bool(row[0]), row[1], row[2])

    def activate_kill_switch(self, reason: str = "manual activation") -> None:
        self._conn.execute(
            "INSERT INTO kill_switch (id, active, activated_at, reason, updated_at) VALUES (1, 1, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET active=1, activated_at=excluded.activated_at, reason=excluded.reason, updated_at=excluded.updated_at",
            (_now(), reason, _now()),
        )

    def reset_kill_switch(self) -> None:
        self._conn.execute(
            "INSERT INTO kill_switch (id, active, activated_at, reason, updated_at) VALUES (1, 0, NULL, NULL, ?) "
            "ON CONFLICT(id) DO UPDATE SET active=0, activated_at=NULL, reason=NULL, updated_at=excluded.updated_at",
            (_now(),),
        )


def _serialize_history(history: list[tuple]) -> str:
    import json

    # state may be a SignalLifecycleState enum member OR a plain string --
    # .value for the former, the string itself for the latter. str(enum)
    # would wrongly produce "SignalLifecycleState.SIGNAL_GENERATED" instead
    # of "SIGNAL_GENERATED" (found via the restart test on real AAPL data).
    return json.dumps([
        [state.value if hasattr(state, "value") else str(state), ts.isoformat() if hasattr(ts, "isoformat") else str(ts)]
        for state, ts in history
    ])


def _deserialize_history(raw: str) -> list[tuple[str, str]]:
    import json

    return [tuple(item) for item in json.loads(raw)]
