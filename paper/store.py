"""SQLite persistence (spec §9: "if no suitable persistence exists, use
SQLite" — none existed anywhere in the project; stdlib sqlite3, no new
dependency). One file, one connection, explicit BEGIN/COMMIT/ROLLBACK
transactions (spec §10) — no ORM, no ambient/implicit transaction magic.

Every row stores a full `data_json` (the object's own model_dump_json())
alongside a handful of scalar columns needed for lookups (symbol, status,
signal_id). Reconstruction always goes through the real Pydantic model's
own validator, via `core.sqlite_util.parse_model_json` (a thin wrapper
around `Model.model_validate_json(...)` that turns a malformed row -- a
real, if rare, reachable failure mode found by an autonomous hardening
cycle's SQLite-adversarial-resilience audit -- into a clear
`MalformedRowError` instead of a raw, uncaught `pydantic.ValidationError`)
— this store never hand-builds a dict that bypasses the model's own
validation.
"""

import json
import sqlite3

from core import sqlite_util
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from backtesting.trade import Trade
from paper.errors import DuplicateTradeForPositionError, InvalidOrderTransitionError, InvalidPositionTransitionError
from paper.models import JournalEntry, JournalOutcome, PaperFill, PaperOrder, Position
from risk.account import Account
from risk.contracts import RiskDecision
from strategy.signal import Signal

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    signal_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_decisions (
    risk_decision_id TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL REFERENCES signals(signal_id),
    approved INTEGER NOT NULL,
    risk_config_version TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_orders (
    order_id TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL REFERENCES signals(signal_id),
    symbol TEXT NOT NULL,
    status TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_fills (
    fill_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES paper_orders(order_id),
    symbol TEXT NOT NULL,
    fill_kind TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    position_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    status TEXT NOT NULL,
    signal_id TEXT NOT NULL,
    data_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
    trade_id TEXT PRIMARY KEY,
    position_id TEXT NOT NULL REFERENCES positions(position_id),
    symbol TEXT NOT NULL,
    execution_model_version TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journal_entries (
    journal_entry_id TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL UNIQUE,
    symbol TEXT NOT NULL,
    outcome TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    data_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Phase 7A: the last bar timestamp processed per symbol, persisted so
-- duplicate/out-of-order detection (paper/engine.py's process_bar) and
-- PaperSession's resume-after-restart both survive a process restart, not
-- just an in-memory Python object.
CREATE TABLE IF NOT EXISTS bar_cursor (
    symbol TEXT PRIMARY KEY,
    last_bar_timestamp TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PaperStore:
    CURRENT_SCHEMA_VERSION = 1
    """Final-product-hardening: see core.sqlite_util.ensure_schema_version's
    docstring for why this is PRAGMA user_version, not a table. Bump this
    (and add a real migration step in __init__) the next time this
    store's own _SCHEMA changes in a way existing on-disk databases need
    to catch up to."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._conn = sqlite_util.connect(self.db_path)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self.trade_position_uniqueness_enforced_at_db_level = self._migrate_trades_unique_position_id_index()
        sqlite_util.ensure_schema_version(self._conn, self.CURRENT_SCHEMA_VERSION)

    def _migrate_trades_unique_position_id_index(self) -> bool:
        """Continuous red-team follow-up, 2026-09-23 (G14, docs/MASTER_KNOWN_ISSUES.md):
        `trades.position_id` (a position closes into a Trade at most once)
        previously had no DB-level uniqueness at all -- application
        discipline only (a single call site, plus store.transaction()'s
        own atomicity). No column backfill is needed here (`position_id`
        has always been a populated, NOT NULL column, unlike
        predictions/store.py's own entry_time migration, which had to add
        and backfill a brand-new column first) -- this is purely an
        additive index. Mirrors predictions/store.py's own
        `_migrate_entry_time_column_and_unique_index` exactly: attempts a
        real `CREATE UNIQUE INDEX IF NOT EXISTS`, and if an already-
        deployed database happens to already contain duplicate
        position_id rows in `trades` (only possible under the old
        app-level-only discipline, and not observed in this project's own
        databases), the index creation is skipped rather than crashing
        startup or silently deleting a row -- see
        core.sqlite_util.try_create_unique_index's own docstring. Returns
        whether the DB-level constraint is actually active, surfaced via
        `trade_position_uniqueness_enforced_at_db_level` so a caller/
        health-check can know which guarantee it's actually getting."""
        return sqlite_util.try_create_unique_index(
            self._conn, index_name="idx_trades_position_id_unique", table="trades", columns="position_id"
        )

    def close(self) -> None:
        self._conn.close()

    def integrity_check(self) -> str:
        """Final-product-hardening phase: `PRAGMA integrity_check` for
        the paper-trading database -- previously only scheduler/store.py
        had this capability, despite this being one of the two most
        safety-critical stores in the project (real account/position
        state). Returns "ok" for a healthy database, or SQLite's own
        corruption findings otherwise."""
        return sqlite_util.integrity_check(self._conn)

    def db_size_bytes(self) -> int:
        return sqlite_util.db_size_bytes(self.db_path)

    def schema_version(self) -> int:
        return sqlite_util.get_schema_version(self._conn)

    @contextmanager
    def transaction(self):
        """Explicit BEGIN/COMMIT/ROLLBACK (spec §10) — no partial writes on
        failure. Nested calls are NOT supported (a single flat transaction
        per paper-trading step is all this phase needs); attempting one
        raises rather than silently misbehaving.

        Continuous red-team follow-up, 2026-09-23 (G9): `BEGIN IMMEDIATE`,
        not plain `BEGIN` (SQLite's default DEFERRED mode). A deferred
        transaction only acquires the write lock at its FIRST write
        statement, so two concurrent processes (e.g. the dashboard and a
        `paper-live` CLI session sharing the same default
        `data/live_sim_trading.db`) could each start a transaction, each
        run their own read-then-decide logic against a snapshot that does
        not yet reflect the other's still-uncommitted write, and then both
        commit — a classic cross-process check-then-act race (lost
        updates / duplicate orders for the same symbol), independent of
        and in addition to the in-memory `self.account` staleness
        `PaperTradingEngine._refresh_account` closes. `BEGIN IMMEDIATE`
        acquires SQLite's own RESERVED lock atomically at the START of the
        transaction instead: a second, concurrent `BEGIN IMMEDIATE` on
        another connection blocks (via the busy timeout already configured
        in `core.sqlite_util.connect`) until the first transaction commits
        or rolls back, then proceeds against the now-current state — never
        two writers interleaved. This uses SQLite's own native OS-level
        file lock, not an application-level lock row: it cannot be left
        stale by a crashed holder (the OS releases the lock the instant
        the crashed process's file descriptor closes), and a losing
        transaction either waits briefly or fails loudly with
        `sqlite3.OperationalError: database is locked` — never silently
        proceeds against stale data. See tests/test_paper_engine.py's
        cross-process concurrency tests."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")

    # --- signals -----------------------------------------------------------

    def save_signal(self, signal: Signal, *, strategy_version: str) -> None:
        self._conn.execute(
            "INSERT INTO signals (signal_id, symbol, strategy_name, strategy_version, data_json, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (signal.stable_id(), signal.symbol, signal.strategy_name, strategy_version, signal.model_dump_json(), _now()),
        )

    def get_signal(self, signal_id: str) -> Signal | None:
        row = self._conn.execute("SELECT data_json FROM signals WHERE signal_id = ?", (signal_id,)).fetchone()
        return sqlite_util.parse_model_json(Signal, row[0], row_identifier=signal_id) if row else None

    # --- risk decisions ------------------------------------------------------

    def save_risk_decision(self, risk_decision_id: str, signal_id: str, decision: RiskDecision, *, risk_config_version: str) -> None:
        self._conn.execute(
            "INSERT INTO risk_decisions (risk_decision_id, signal_id, approved, risk_config_version, data_json, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (risk_decision_id, signal_id, int(decision.approved), risk_config_version, decision.model_dump_json(), _now()),
        )

    def get_risk_decision(self, risk_decision_id: str) -> RiskDecision | None:
        row = self._conn.execute(
            "SELECT data_json FROM risk_decisions WHERE risk_decision_id = ?", (risk_decision_id,)
        ).fetchone()
        return sqlite_util.parse_model_json(RiskDecision, row[0], row_identifier=risk_decision_id) if row else None

    # --- orders --------------------------------------------------------------

    def save_order(self, order: PaperOrder) -> None:
        self._conn.execute(
            "INSERT INTO paper_orders (order_id, signal_id, symbol, status, data_json, created_at) VALUES (?,?,?,?,?,?)",
            (order.order_id, order.signal_id, order.symbol, order.status.value, order.model_dump_json(), _now()),
        )

    def update_order(self, order: PaperOrder) -> None:
        """Autonomous hardening cycle: FILLED is PaperOrder's own
        terminal state (see InvalidOrderTransitionError's own
        docstring for the full rationale, mirroring
        update_position's identical guard) -- `WHERE status != 'FILLED'`
        rather than trusting the caller. A 0-row update means an
        order that is either already FILLED or does not exist; either
        way, silently doing nothing would hide a real bug."""
        cursor = self._conn.execute(
            "UPDATE paper_orders SET status = ?, data_json = ? WHERE order_id = ? AND status != 'FILLED'",
            (order.status.value, order.model_dump_json(), order.order_id),
        )
        if cursor.rowcount == 0:
            existing = self._conn.execute("SELECT 1 FROM paper_orders WHERE order_id = ?", (order.order_id,)).fetchone()
            if existing is None:
                raise ValueError(f"Cannot update order {order.order_id!r}: no such order exists.")
            raise InvalidOrderTransitionError(order_id=order.order_id, attempted_status=order.status.value)

    def get_pending_order(self, symbol: str) -> PaperOrder | None:
        row = self._conn.execute(
            "SELECT data_json FROM paper_orders WHERE symbol = ? AND status = 'PENDING' ORDER BY created_at LIMIT 1",
            (symbol,),
        ).fetchone()
        return sqlite_util.parse_model_json(PaperOrder, row[0], row_identifier=f"symbol={symbol}") if row else None

    def list_pending_orders(self) -> list[PaperOrder]:
        """Every symbol's pending order, not just one -- needed to advance
        ALL outstanding orders (see paper/advance.py), since a single
        single-position account can hold multiple simultaneous PENDING
        orders across different symbols (nothing vetoes a second symbol's
        order until one of them actually FILLS -- see risk/engine.py's
        own account-wide, fill-time-only single-position check)."""
        rows = self._conn.execute(
            "SELECT data_json FROM paper_orders WHERE status = 'PENDING' ORDER BY created_at"
        ).fetchall()
        return [sqlite_util.parse_model_json(PaperOrder, r[0], row_identifier="list_pending_orders") for r in rows]

    # --- fills -----------------------------------------------------------------

    def save_fill(self, fill: PaperFill) -> None:
        self._conn.execute(
            "INSERT INTO paper_fills (fill_id, order_id, symbol, fill_kind, data_json, created_at) VALUES (?,?,?,?,?,?)",
            (fill.fill_id, fill.order_id, fill.symbol, fill.fill_kind.value, fill.model_dump_json(), _now()),
        )

    def get_fill(self, fill_id: str) -> PaperFill | None:
        row = self._conn.execute("SELECT data_json FROM paper_fills WHERE fill_id = ?", (fill_id,)).fetchone()
        return sqlite_util.parse_model_json(PaperFill, row[0], row_identifier=fill_id) if row else None

    # --- positions ---------------------------------------------------------------

    def save_position(self, position: Position) -> None:
        self._conn.execute(
            "INSERT INTO positions (position_id, symbol, status, signal_id, data_json, updated_at) VALUES (?,?,?,?,?,?)",
            (position.position_id, position.symbol, position.status.value, position.signal_id, position.model_dump_json(), _now()),
        )

    def update_position(self, position: Position) -> None:
        """Final-product-hardening: CLOSED is the position state
        machine's one terminal state (paper/models.py::PositionStatus)
        -- once closed, no further mutation is valid (not a reopen, not
        a second close, not a stray bars_held update racing a close).
        Guarded here with `WHERE status != 'CLOSED'` rather than trusting
        every caller to re-check `get_position().status` first, since
        this is the single call site every position mutation already
        flows through (see paper/engine.py's `_process_open_position`
        and `_close_position`). A 0-row update means the guard fired --
        raised as InvalidPositionTransitionError, never a silent no-op,
        since a caller reaching this state has a real bug worth
        surfacing (e.g. two exit paths racing on the same position)."""
        cursor = self._conn.execute(
            "UPDATE positions SET status = ?, data_json = ?, updated_at = ? WHERE position_id = ? AND status != 'CLOSED'",
            (position.status.value, position.model_dump_json(), _now(), position.position_id),
        )
        if cursor.rowcount == 0:
            existing = self.get_position(position.position_id)
            if existing is None:
                raise ValueError(f"Cannot update position {position.position_id!r}: no such position exists.")
            raise InvalidPositionTransitionError(position_id=position.position_id, attempted_status=position.status.value)

    def get_open_position(self, symbol: str) -> Position | None:
        row = self._conn.execute(
            "SELECT data_json FROM positions WHERE symbol = ? AND status = 'OPEN' ORDER BY updated_at LIMIT 1",
            (symbol,),
        ).fetchone()
        return sqlite_util.parse_model_json(Position, row[0], row_identifier=f"symbol={symbol}") if row else None

    def get_position(self, position_id: str) -> Position | None:
        row = self._conn.execute("SELECT data_json FROM positions WHERE position_id = ?", (position_id,)).fetchone()
        return sqlite_util.parse_model_json(Position, row[0], row_identifier=position_id) if row else None

    def list_positions(self) -> list[Position]:
        rows = self._conn.execute("SELECT data_json FROM positions ORDER BY updated_at").fetchall()
        return [sqlite_util.parse_model_json(Position, r[0], row_identifier="list_positions") for r in rows]

    # --- trades ------------------------------------------------------------------

    def save_trade(self, trade: Trade, *, position_id: str, trade_id: str, execution_model_version: str) -> None:
        """Raises DuplicateTradeForPositionError if the DB-level
        UNIQUE(position_id) index (see
        _migrate_trades_unique_position_id_index, G14) is active and a
        trade for this position_id was already saved -- mirroring
        predictions/store.py's own save_prediction/DuplicatePredictionError
        pattern. If the constraint is not active (a pre-existing database
        with unresolved historical duplicates), this still succeeds,
        matching the prior behavior exactly."""
        try:
            self._conn.execute(
                "INSERT INTO trades (trade_id, position_id, symbol, execution_model_version, data_json, created_at) VALUES (?,?,?,?,?,?)",
                (trade_id, position_id, trade.symbol, execution_model_version, trade.model_dump_json(), _now()),
            )
        except sqlite3.IntegrityError as exc:
            if "UNIQUE constraint failed" not in str(exc):
                raise
            raise DuplicateTradeForPositionError(position_id=position_id) from exc

    def list_trades(self) -> list[Trade]:
        rows = self._conn.execute("SELECT data_json FROM trades ORDER BY created_at").fetchall()
        return [sqlite_util.parse_model_json(Trade, r[0], row_identifier="list_trades") for r in rows]

    def sum_realized_trade_pnl(self) -> float:
        row = self._conn.execute("SELECT data_json FROM trades").fetchall()
        return sum(sqlite_util.parse_model_json(Trade, r[0], row_identifier="sum_realized_trade_pnl").net_pnl for r in row)

    # --- journal -----------------------------------------------------------------

    def save_journal_entry(self, entry: JournalEntry) -> None:
        self._conn.execute(
            "INSERT INTO journal_entries "
            "(journal_entry_id, signal_id, symbol, outcome, data_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (entry.journal_entry_id, entry.signal_id, entry.symbol, entry.outcome.value, entry.model_dump_json(), _now(), _now()),
        )

    def update_journal_entry(self, entry: JournalEntry) -> None:
        self._conn.execute(
            "UPDATE journal_entries SET outcome = ?, data_json = ?, updated_at = ? WHERE journal_entry_id = ?",
            (entry.outcome.value, entry.model_dump_json(), _now(), entry.journal_entry_id),
        )

    def find_journal_entry_by_signal_id(self, signal_id: str) -> JournalEntry | None:
        row = self._conn.execute(
            "SELECT data_json FROM journal_entries WHERE signal_id = ?", (signal_id,)
        ).fetchone()
        return sqlite_util.parse_model_json(JournalEntry, row[0], row_identifier=f"signal_id={signal_id}") if row else None

    def list_journal_entries(self) -> list[JournalEntry]:
        rows = self._conn.execute("SELECT data_json FROM journal_entries ORDER BY created_at").fetchall()
        return [sqlite_util.parse_model_json(JournalEntry, r[0], row_identifier="list_journal_entries") for r in rows]

    # --- account (single row, always id=1) ----------------------------------------

    def get_account(self) -> Account | None:
        row = self._conn.execute("SELECT data_json FROM account WHERE id = 1").fetchone()
        return sqlite_util.parse_model_json(Account, row[0], row_identifier="account") if row else None

    def save_account(self, account: Account) -> None:
        self._conn.execute(
            "INSERT INTO account (id, data_json, updated_at) VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET data_json = excluded.data_json, updated_at = excluded.updated_at",
            (account.model_dump_json(), _now()),
        )

    # --- bar cursor (Phase 7A: duplicate/out-of-order bar detection + resume) ------

    def get_last_bar_timestamp(self, symbol: str) -> datetime | None:
        row = self._conn.execute("SELECT last_bar_timestamp FROM bar_cursor WHERE symbol = ?", (symbol,)).fetchone()
        return datetime.fromisoformat(row[0]) if row else None

    def set_last_bar_timestamp(self, symbol: str, timestamp: datetime) -> None:
        self._conn.execute(
            "INSERT INTO bar_cursor (symbol, last_bar_timestamp, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(symbol) DO UPDATE SET last_bar_timestamp = excluded.last_bar_timestamp, updated_at = excluded.updated_at",
            (symbol, timestamp.isoformat(), _now()),
        )

    # --- raw access for reconciliation / tests --------------------------------------

    def _fetch_all_json(self, table: str) -> list[dict]:
        rows = self._conn.execute(f"SELECT data_json FROM {table}").fetchall()  # noqa: S608 - table name is internal-only, never user input
        return [json.loads(r[0]) for r in rows]

    def list_trade_position_ids(self) -> list[tuple[str, str]]:
        """(trade_id, position_id) pairs, straight from the trades table's
        own columns — used by reconciliation's orphan-trade check."""
        return self._conn.execute("SELECT trade_id, position_id FROM trades").fetchall()
