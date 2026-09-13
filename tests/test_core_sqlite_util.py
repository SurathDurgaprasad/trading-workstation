"""core/sqlite_util.py -- the consolidated repository-wide SQLite
connection policy (WAL mode + explicit busy timeout)."""
from __future__ import annotations

import sqlite3
import threading

from core.sqlite_util import DEFAULT_BUSY_TIMEOUT_SECONDS, connect


def test_connect_enables_wal_mode(tmp_path):
    conn = connect(tmp_path / "test.db")
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
    conn.close()


def test_connect_sets_busy_timeout(tmp_path):
    conn = connect(tmp_path / "test.db")
    timeout_ms = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    assert timeout_ms == int(DEFAULT_BUSY_TIMEOUT_SECONDS * 1000)
    conn.close()


def test_connect_uses_autocommit_isolation_level(tmp_path):
    conn = connect(tmp_path / "test.db")
    assert conn.isolation_level is None
    conn.close()


def test_connect_accepts_a_string_path(tmp_path):
    conn = connect(str(tmp_path / "test.db"))
    conn.execute("SELECT 1")
    conn.close()


def test_wal_mode_survives_a_reopened_connection(tmp_path):
    """WAL is a persistent, on-disk property of the database file itself
    once set -- confirms a second connection to the SAME file (the normal
    restart-recovery pattern every store already uses) sees it too,
    without needing to re-issue the PRAGMA."""
    db_path = tmp_path / "test.db"
    conn1 = connect(db_path)
    conn1.execute("CREATE TABLE t (x INTEGER)")
    conn1.close()

    conn2 = sqlite3.connect(str(db_path))
    mode = conn2.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
    conn2.close()


def test_concurrent_reader_is_not_blocked_by_a_writer_under_wal(tmp_path):
    """The actual behavioral difference WAL mode provides over the
    default rollback-journal mode: a reader can proceed while a writer
    holds an open transaction, rather than blocking."""
    db_path = tmp_path / "test.db"
    setup = connect(db_path)
    setup.execute("CREATE TABLE t (x INTEGER)")
    setup.execute("INSERT INTO t VALUES (1)")
    setup.close()

    writer = connect(db_path)
    writer.execute("BEGIN IMMEDIATE")
    writer.execute("INSERT INTO t VALUES (2)")

    reader_result = {}

    def _read():
        reader = connect(db_path, busy_timeout_seconds=2.0)
        reader_result["rows"] = reader.execute("SELECT COUNT(*) FROM t").fetchone()[0]
        reader.close()

    thread = threading.Thread(target=_read)
    thread.start()
    thread.join(timeout=5.0)

    writer.execute("COMMIT")
    writer.close()

    assert not thread.is_alive(), "reader blocked on an in-progress writer under WAL mode -- should not happen"
    assert reader_result.get("rows") == 1  # sees the pre-transaction committed state, not the writer's uncommitted row
