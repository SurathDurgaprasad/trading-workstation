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
