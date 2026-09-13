"""Repository-wide SQLite connection policy -- final-product-hardening
phase. Before this module existed, all 12 of this project's SQLite
stores (paper/store.py, live/state_store.py, scheduler/store.py,
market_intelligence/store.py, market_intelligence/regime_store.py,
strategy/promotion_store.py, strategy/experiment_store.py,
decision_engine/store.py, research/store.py, predictions/store.py,
predictions/direction_forecast_store.py, experiments/store.py)
independently called `sqlite3.connect(self.db_path, isolation_level=None)`
with Python's stdlib defaults: no WAL mode (the default rollback-journal
mode blocks readers behind an in-progress writer), and a 5-second busy
timeout with nothing catching or retrying `sqlite3.OperationalError:
database is locked` if that window is exceeded.

This is a single, safe, behavior-preserving hardening: WAL mode lets
readers proceed concurrently with a writer (this project's own dashboard,
CLI, and scheduler can all touch the same DB file in the same window),
and a longer explicit busy timeout gives real contention (e.g. two
scheduler processes, or a dashboard request during a scheduler tick) more
room to resolve gracefully instead of raising. Converting an EXISTING
rollback-journal database to WAL is transparent and safe -- SQLite
handles it automatically on first connect, no data migration needed.

This does not change `isolation_level=None` (Python DBAPI autocommit
mode) or any store's own explicit `transaction()` BEGIN/COMMIT/ROLLBACK
pattern -- both are unchanged, this only touches how the connection
itself is opened.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_BUSY_TIMEOUT_SECONDS = 30.0
"""Six times Python's stdlib default (5s) -- long enough for real, brief
contention (a scheduler tick, a dashboard request) to resolve, short
enough that a genuinely stuck writer still surfaces as an error rather
than hanging forever."""


def connect(db_path: str | Path, *, busy_timeout_seconds: float = DEFAULT_BUSY_TIMEOUT_SECONDS) -> sqlite3.Connection:
    """The one place every store's own connection is opened. WAL mode +
    an explicit busy timeout, `isolation_level=None` (autocommit,
    matching every existing store's own convention unchanged)."""
    conn = sqlite3.connect(str(db_path), isolation_level=None, timeout=busy_timeout_seconds)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={int(busy_timeout_seconds * 1000)}")
    return conn


def integrity_check(conn: sqlite3.Connection) -> str:
    """`PRAGMA integrity_check` over the whole database file this
    connection points at (not just one table) -- returns "ok" for a
    healthy file, or SQLite's own semicolon-joined corruption findings
    otherwise. Previously implemented only once, in scheduler/store.py's
    own SchedulerRunStore.integrity_check -- extracted here so every
    store can offer the same capability without re-deriving it."""
    rows = conn.execute("PRAGMA integrity_check").fetchall()
    results = [row[0] for row in rows]
    return "; ".join(results) if results else "ok"


def db_size_bytes(db_path: str | Path) -> int:
    """Same convention as scheduler/store.py's own SchedulerRunStore.
    db_size_bytes -- the raw on-disk file size, 0 if the file does not
    exist (never an exception for a not-yet-created database)."""
    path = Path(db_path)
    return path.stat().st_size if path.exists() else 0


def ensure_column(conn: sqlite3.Connection, table: str, column: str, coltype: str) -> None:
    """Additive, idempotent migration for a table that may already exist
    on disk with an older schema. `CREATE TABLE IF NOT EXISTS` in a
    store's own `_SCHEMA` only creates a table that is entirely missing;
    it silently does nothing to add a new column to a table that already
    exists -- SQLite has no CREATE-OR-ALTER. Without this, a column added
    only to a `_SCHEMA` string works against a fresh test DB (created
    new, so it includes the column from the start) while breaking every
    real, already-created production DB the moment code tries to
    read/write the new column.

    Previously implemented once, independently, in live/state_store.py
    (final-product-hardening phase: extracted here, the same treatment
    already given to `integrity_check`/`db_size_bytes`, so a second store
    needing the identical migration primitive -- predictions/store.py's
    natural-key backfill -- does not have to re-derive or duplicate it).
    table/column names here are always our own hardcoded literals, never
    user input, so this f-string is not a SQL-injection risk despite not
    being parameterized (SQLite does not support parameterizing
    identifiers in DDL)."""
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


def try_create_unique_index(conn: sqlite3.Connection, *, index_name: str, table: str, columns: str) -> bool:
    """Attempts `CREATE UNIQUE INDEX IF NOT EXISTS` and reports whether it
    succeeded, rather than letting a real, already-deployed database that
    happens to already contain duplicate rows on `columns` (the exact
    scenario a NEW unique constraint is being added to prevent) crash
    application startup. This is deliberately soft-fail-and-report, not
    silent: a caller that gets False back has a genuine, disclosable
    known-limitation ("this store's natural-key uniqueness is not
    currently enforced at the database level because pre-existing
    duplicate rows were found") to surface via integrity_check or a
    startup log, rather than the process refusing to start over old
    data nothing can safely repair automatically (see this module's
    home mission's own "never delete critical trading state
    automatically" rule -- deduplicating existing rows is exactly that
    kind of automatic, unreviewed data deletion, so it is never
    attempted here)."""
    try:
        conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table}({columns})")
        return True
    except sqlite3.IntegrityError:
        return False
