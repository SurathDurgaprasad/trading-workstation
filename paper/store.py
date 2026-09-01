"""SQLite persistence (spec §9: "if no suitable persistence exists, use
SQLite" — none existed anywhere in the project; stdlib sqlite3, no new
dependency). One file, one connection, explicit BEGIN/COMMIT/ROLLBACK
transactions (spec §10) — no ORM, no ambient/implicit transaction magic.

Every row stores a full `data_json` (the object's own model_dump_json())
alongside a handful of scalar columns needed for lookups (symbol, status,
signal_id). Reconstruction always goes through the real Pydantic model's
own validator (`Model.model_validate_json(...)`) — this store never
hand-builds a dict that bypasses the model's own validation.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from backtesting.trade import Trade
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
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, isolation_level=None)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def transaction(self):
        """Explicit BEGIN/COMMIT/ROLLBACK (spec §10) — no partial writes on
        failure. Nested calls are NOT supported (a single flat transaction
        per paper-trading step is all this phase needs); attempting one
        raises rather than silently misbehaving."""
        self._conn.execute("BEGIN")
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
        return Signal.model_validate_json(row[0]) if row else None

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
        return RiskDecision.model_validate_json(row[0]) if row else None

    # --- orders --------------------------------------------------------------

    def save_order(self, order: PaperOrder) -> None:
        self._conn.execute(
            "INSERT INTO paper_orders (order_id, signal_id, symbol, status, data_json, created_at) VALUES (?,?,?,?,?,?)",
            (order.order_id, order.signal_id, order.symbol, order.status.value, order.model_dump_json(), _now()),
        )

    def update_order(self, order: PaperOrder) -> None:
        self._conn.execute(
            "UPDATE paper_orders SET status = ?, data_json = ? WHERE order_id = ?",
            (order.status.value, order.model_dump_json(), order.order_id),
        )

    def get_pending_order(self, symbol: str) -> PaperOrder | None:
        row = self._conn.execute(
            "SELECT data_json FROM paper_orders WHERE symbol = ? AND status = 'PENDING' ORDER BY created_at LIMIT 1",
            (symbol,),
        ).fetchone()
        return PaperOrder.model_validate_json(row[0]) if row else None

    # --- fills -----------------------------------------------------------------

    def save_fill(self, fill: PaperFill) -> None:
        self._conn.execute(
            "INSERT INTO paper_fills (fill_id, order_id, symbol, fill_kind, data_json, created_at) VALUES (?,?,?,?,?,?)",
            (fill.fill_id, fill.order_id, fill.symbol, fill.fill_kind.value, fill.model_dump_json(), _now()),
        )

    def get_fill(self, fill_id: str) -> PaperFill | None:
        row = self._conn.execute("SELECT data_json FROM paper_fills WHERE fill_id = ?", (fill_id,)).fetchone()
        return PaperFill.model_validate_json(row[0]) if row else None

    # --- positions ---------------------------------------------------------------

    def save_position(self, position: Position) -> None:
        self._conn.execute(
            "INSERT INTO positions (position_id, symbol, status, signal_id, data_json, updated_at) VALUES (?,?,?,?,?,?)",
            (position.position_id, position.symbol, position.status.value, position.signal_id, position.model_dump_json(), _now()),
        )

    def update_position(self, position: Position) -> None:
        self._conn.execute(
            "UPDATE positions SET status = ?, data_json = ?, updated_at = ? WHERE position_id = ?",
            (position.status.value, position.model_dump_json(), _now(), position.position_id),
        )

    def get_open_position(self, symbol: str) -> Position | None:
        row = self._conn.execute(
            "SELECT data_json FROM positions WHERE symbol = ? AND status = 'OPEN' ORDER BY updated_at LIMIT 1",
            (symbol,),
        ).fetchone()
        return Position.model_validate_json(row[0]) if row else None

    def get_position(self, position_id: str) -> Position | None:
        row = self._conn.execute("SELECT data_json FROM positions WHERE position_id = ?", (position_id,)).fetchone()
        return Position.model_validate_json(row[0]) if row else None

    def list_positions(self) -> list[Position]:
        rows = self._conn.execute("SELECT data_json FROM positions ORDER BY updated_at").fetchall()
        return [Position.model_validate_json(r[0]) for r in rows]

    # --- trades ------------------------------------------------------------------

    def save_trade(self, trade: Trade, *, position_id: str, trade_id: str, execution_model_version: str) -> None:
        self._conn.execute(
            "INSERT INTO trades (trade_id, position_id, symbol, execution_model_version, data_json, created_at) VALUES (?,?,?,?,?,?)",
            (trade_id, position_id, trade.symbol, execution_model_version, trade.model_dump_json(), _now()),
        )

    def list_trades(self) -> list[Trade]:
        rows = self._conn.execute("SELECT data_json FROM trades ORDER BY created_at").fetchall()
        return [Trade.model_validate_json(r[0]) for r in rows]

    def sum_realized_trade_pnl(self) -> float:
        row = self._conn.execute("SELECT data_json FROM trades").fetchall()
        return sum(Trade.model_validate_json(r[0]).net_pnl for r in row)

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
        return JournalEntry.model_validate_json(row[0]) if row else None

    def list_journal_entries(self) -> list[JournalEntry]:
        rows = self._conn.execute("SELECT data_json FROM journal_entries ORDER BY created_at").fetchall()
        return [JournalEntry.model_validate_json(r[0]) for r in rows]

    # --- account (single row, always id=1) ----------------------------------------

    def get_account(self) -> Account | None:
        row = self._conn.execute("SELECT data_json FROM account WHERE id = 1").fetchone()
        return Account.model_validate_json(row[0]) if row else None

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
