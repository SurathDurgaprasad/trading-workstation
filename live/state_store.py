"""Phase 13 §14 — SQLite persistence for pending approvals and the kill
switch. A NEW, small store scoped to live/ with its OWN sqlite3 connection
to the SAME db file PaperStore already uses (or a dedicated one) — multiple
connections to one SQLite file are standard and safe; this deliberately
does NOT reach into PaperStore's internals or modify paper/store.py's
schema (spec: "do not blindly refactor").

Three tables:
  - pending_approvals: one row per signal ever sent to
    PENDING_HUMAN_APPROVAL, updated in place as its lifecycle advances —
    this is the durable audit trail spec §3 requires (signal_id,
    strategy_version, risk_config_version, requested/approved quantity,
    human decision, decision timestamp/reason, final execution result).
  - kill_switch: a single row, survives restart, requires an explicit
    reset (spec §8).
  - feed_status (Phase 15 §7/§22): one row per symbol, updated every time
    LiveSimPipeline processes a real bar — the ONLY way the dashboard (a
    separate process from whatever is actually driving the feed, e.g. the
    `paper-live` CLI) can honestly know the data source/status/age of the
    last bar seen, without polling the feed itself. This is deliberately
    NOT fabricated from the dashboard side; if no bar has ever been
    written here, the dashboard says so rather than guessing.
  - clock_skew (LIVE SYSTEM HARDENING mission, Part 11): a single row
    (like kill_switch), holding the last REAL measurement of local-vs-
    Dhan-server clock skew (see live/dhan/clock_skew.py). Written by
    `readiness-check --deep` and by `paper-live --source dhan` at session
    startup — never by the dashboard itself, which only reads this table
    (zero I/O on page load, same rule feed_status already follows). If no
    measurement has ever been taken, the table is empty and the dashboard
    must say "UNKNOWN", never fabricate a value or silently omit the row.
  - critic_rejections (LIVE SYSTEM HARDENING mission): one row per signal
    the deterministic critic (live/critic_gate.py, wrapping the SAME
    critic.engine.evaluate() shadow-run already uses) blocked before it
    ever reached risk sizing or an order. Multi-row (unlike clock_skew's
    single row) since many distinct signals can be rejected over a
    session; keyed by signal_id like pending_approvals, for the same
    "one row per thing that happened" reason. This is the durable record
    "rejection reason must be persisted... visible in dashboard" (mission
    requirement) depends on -- a critic-rejected signal never reaches
    pending_approvals or a JournalEntry at all, so without this table its
    rejection would leave no trace anywhere.
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

CREATE TABLE IF NOT EXISTS feed_status (
    symbol TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    bar_timestamp TEXT NOT NULL,
    received_at TEXT NOT NULL,
    connection_state TEXT,
    updated_at TEXT NOT NULL
    -- last_price added via _ensure_column() below, NOT here -- CREATE TABLE
    -- IF NOT EXISTS is a no-op against a table that already exists on disk
    -- (every real deployed live_state.db does), so a column added only to
    -- this DDL string would silently never reach a real database and the
    -- next save_feed_status() call against it would raise "no column
    -- named last_price". See _ensure_column's own docstring.
);

CREATE TABLE IF NOT EXISTS clock_skew (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    skew_seconds REAL NOT NULL,
    classification TEXT NOT NULL,
    detail TEXT NOT NULL,
    measured_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS critic_rejections (
    signal_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    verdict TEXT NOT NULL,
    reasons_json TEXT NOT NULL,
    checks_json TEXT NOT NULL,
    rejected_at TEXT NOT NULL
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


@dataclass
class ClockSkewRecord:
    skew_seconds: float
    classification: str  # "PASS" | "WARNING" | "FAIL"
    detail: str
    measured_at: str  # when the underlying REAL measurement was taken (UTC isoformat)
    updated_at: str  # when this row was last written (UTC isoformat) -- lets the dashboard tell a fresh row from a stale one


@dataclass
class CriticRejectionRecord:
    signal_id: str
    symbol: str
    verdict: str  # critic.models.CriticVerdict value -- REJECT or INSUFFICIENT_EVIDENCE, the two blocking verdicts
    reasons: list[str]
    checks: list[dict]  # each critic.models.CriticCheck, JSON-serialized (name/evaluated/passed/severity/detail)
    rejected_at: str  # UTC isoformat


@dataclass
class FeedStatusRecord:
    symbol: str
    source: str  # DataSource value, e.g. "DHAN", "MOCK" -- stored as plain text, not the enum itself (this store never imports market.data_provider)
    status: str  # DataStatus value, e.g. "LIVE", "SIMULATED"
    bar_timestamp: str
    received_at: str
    connection_state: str | None
    updated_at: str
    last_price: float | None = None
    """The bar's own close price at the moment this row was written --
    AUTONOMOUS LIVE PAPER-TRADING HARDENING mission, dashboard truth audit:
    the MARKET FEED table had a Data Health/Age column but no price at
    all, real gap against the mission's own "live prices" checklist item.
    None for any row written before this column existed (old real rows
    are never backfilled -- see _ensure_column) or if a source ever
    delivers a bar without a close (neither happens today, kept optional
    for honesty rather than assuming)."""


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, coltype: str) -> None:
    """Additive, idempotent migration for a table that may already exist
    on disk (every real deployed live_state.db does) with an older schema.
    CREATE TABLE IF NOT EXISTS in _SCHEMA only creates a table that is
    entirely missing; it silently does nothing to add a new column to a
    table that already exists -- SQLite has no CREATE-OR-ALTER. Without
    this, a column added only to the _SCHEMA string above would work
    against a fresh test DB (created new, so it includes the column from
    the start) while breaking every real, already-created production DB
    the moment code tries to read/write the new column -- exactly the
    "write migration-safe changes, do not break existing databases"
    hazard this project holds itself to. table/column names here are
    always our own hardcoded literals, never user input, so this f-string
    is not a SQL-injection risk despite not being parameterized (SQLite
    does not support parameterizing identifiers in DDL)."""
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


class LiveStateStore:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, isolation_level=None)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        _ensure_column(self._conn, "feed_status", "last_price", "REAL")

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

    # --- feed status (Phase 15) -------------------------------------------------

    def save_feed_status(
        self, *, symbol: str, source: str, status: str, bar_timestamp: datetime, received_at: datetime,
        connection_state: str | None = None, last_price: float | None = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO feed_status (symbol, source, status, bar_timestamp, received_at, connection_state, updated_at, last_price) "
            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(symbol) DO UPDATE SET "
            "source=excluded.source, status=excluded.status, bar_timestamp=excluded.bar_timestamp, "
            "received_at=excluded.received_at, connection_state=excluded.connection_state, updated_at=excluded.updated_at, "
            "last_price=excluded.last_price",
            (symbol, source, status, bar_timestamp.isoformat(), received_at.isoformat(), connection_state, _now(), last_price),
        )

    def get_feed_status(self, symbol: str) -> "FeedStatusRecord | None":
        row = self._conn.execute(
            "SELECT symbol, source, status, bar_timestamp, received_at, connection_state, updated_at, last_price FROM feed_status WHERE symbol = ?",
            (symbol,),
        ).fetchone()
        if row is None:
            return None
        return FeedStatusRecord(symbol=row[0], source=row[1], status=row[2], bar_timestamp=row[3], received_at=row[4], connection_state=row[5], updated_at=row[6], last_price=row[7])

    def list_feed_status(self) -> list["FeedStatusRecord"]:
        rows = self._conn.execute("SELECT symbol, source, status, bar_timestamp, received_at, connection_state, updated_at, last_price FROM feed_status ORDER BY symbol").fetchall()
        return [FeedStatusRecord(symbol=r[0], source=r[1], status=r[2], bar_timestamp=r[3], received_at=r[4], connection_state=r[5], updated_at=r[6], last_price=r[7]) for r in rows]

    # --- clock skew (LIVE SYSTEM HARDENING mission, Part 11) --------------------

    def save_clock_skew(
        self, *, skew_seconds: float, classification: str, detail: str, measured_at: datetime,
    ) -> None:
        self._conn.execute(
            "INSERT INTO clock_skew (id, skew_seconds, classification, detail, measured_at, updated_at) "
            "VALUES (1, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
            "skew_seconds=excluded.skew_seconds, classification=excluded.classification, "
            "detail=excluded.detail, measured_at=excluded.measured_at, updated_at=excluded.updated_at",
            (skew_seconds, classification, detail, measured_at.isoformat(), _now()),
        )

    def get_clock_skew(self) -> "ClockSkewRecord | None":
        row = self._conn.execute(
            "SELECT skew_seconds, classification, detail, measured_at, updated_at FROM clock_skew WHERE id = 1"
        ).fetchone()
        if row is None:
            return None
        return ClockSkewRecord(skew_seconds=row[0], classification=row[1], detail=row[2], measured_at=row[3], updated_at=row[4])

    # --- critic rejections (LIVE SYSTEM HARDENING mission) ----------------------

    def save_critic_rejection(
        self, *, signal_id: str, symbol: str, verdict: str, reasons: list[str], checks: list[dict], rejected_at: datetime,
    ) -> None:
        import json

        self._conn.execute(
            "INSERT INTO critic_rejections (signal_id, symbol, verdict, reasons_json, checks_json, rejected_at) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(signal_id) DO UPDATE SET "
            "symbol=excluded.symbol, verdict=excluded.verdict, reasons_json=excluded.reasons_json, "
            "checks_json=excluded.checks_json, rejected_at=excluded.rejected_at",
            (signal_id, symbol, verdict, json.dumps(reasons), json.dumps(checks), rejected_at.isoformat()),
        )

    def list_critic_rejections(self, limit: int = 50) -> list["CriticRejectionRecord"]:
        import json

        rows = self._conn.execute(
            "SELECT signal_id, symbol, verdict, reasons_json, checks_json, rejected_at FROM critic_rejections "
            "ORDER BY rejected_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            CriticRejectionRecord(
                signal_id=r[0], symbol=r[1], verdict=r[2], reasons=json.loads(r[3]), checks=json.loads(r[4]), rejected_at=r[5],
            )
            for r in rows
        ]


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
