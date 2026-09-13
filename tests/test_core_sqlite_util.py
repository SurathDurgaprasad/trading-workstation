"""core/sqlite_util.py -- the consolidated repository-wide SQLite
connection policy (WAL mode + explicit busy timeout)."""
from __future__ import annotations

import sqlite3
import threading

import pytest

from core.sqlite_util import (
    DEFAULT_BUSY_TIMEOUT_SECONDS,
    connect,
    ensure_column,
    ensure_schema_version,
    get_schema_version,
    set_schema_version,
    try_create_unique_index,
)


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


def test_ensure_column_adds_a_missing_column(tmp_path):
    conn = connect(tmp_path / "test.db")
    conn.execute("CREATE TABLE t (x INTEGER)")

    ensure_column(conn, "t", "y", "TEXT")

    columns = {row[1] for row in conn.execute("PRAGMA table_info(t)").fetchall()}
    assert "y" in columns
    conn.close()


def test_ensure_column_is_idempotent_and_does_not_touch_existing_data(tmp_path):
    conn = connect(tmp_path / "test.db")
    conn.execute("CREATE TABLE t (x INTEGER, y TEXT)")
    conn.execute("INSERT INTO t VALUES (1, 'kept')")

    ensure_column(conn, "t", "y", "TEXT")  # column already exists -- must be a no-op, not an error
    ensure_column(conn, "t", "y", "TEXT")  # calling twice must also be safe

    row = conn.execute("SELECT x, y FROM t").fetchone()
    assert row == (1, "kept")
    conn.close()


def test_try_create_unique_index_succeeds_on_clean_data(tmp_path):
    conn = connect(tmp_path / "test.db")
    conn.execute("CREATE TABLE t (a TEXT, b TEXT)")
    conn.execute("INSERT INTO t VALUES ('x', 'y')")

    created = try_create_unique_index(conn, index_name="idx_t_ab", table="t", columns="a, b")

    assert created is True
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO t VALUES ('x', 'y')")
    conn.close()


def test_try_create_unique_index_reports_false_instead_of_raising_on_preexisting_duplicates(tmp_path):
    """The exact scenario this function exists for: a real, already-
    deployed database that already has duplicate rows on the columns a
    NEW unique constraint is being added to prevent going forward. Must
    not crash application startup -- reported as False so the caller can
    disclose the limitation instead."""
    conn = connect(tmp_path / "test.db")
    conn.execute("CREATE TABLE t (a TEXT, b TEXT)")
    conn.execute("INSERT INTO t VALUES ('dup', 'dup')")
    conn.execute("INSERT INTO t VALUES ('dup', 'dup')")

    created = try_create_unique_index(conn, index_name="idx_t_ab", table="t", columns="a, b")

    assert created is False
    conn.close()


def test_get_schema_version_is_zero_for_a_fresh_database(tmp_path):
    conn = connect(tmp_path / "test.db")
    assert get_schema_version(conn) == 0
    conn.close()


def test_set_schema_version_round_trips(tmp_path):
    conn = connect(tmp_path / "test.db")
    set_schema_version(conn, 3)
    assert get_schema_version(conn) == 3
    conn.close()


def test_schema_version_persists_across_a_reconnect(tmp_path):
    db_path = tmp_path / "test.db"
    conn1 = connect(db_path)
    set_schema_version(conn1, 2)
    conn1.close()

    conn2 = connect(db_path)
    assert get_schema_version(conn2) == 2
    conn2.close()


def test_ensure_schema_version_sets_the_version_on_a_fresh_database(tmp_path):
    conn = connect(tmp_path / "test.db")
    ensure_schema_version(conn, 1)
    assert get_schema_version(conn) == 1
    conn.close()


def test_ensure_schema_version_is_idempotent(tmp_path):
    conn = connect(tmp_path / "test.db")
    ensure_schema_version(conn, 1)
    ensure_schema_version(conn, 1)  # calling again must not error or change anything
    assert get_schema_version(conn) == 1
    conn.close()


def test_ensure_schema_version_never_lowers_an_existing_version(tmp_path):
    """A newer on-disk schema opened by older code should not silently
    regress its own version marker."""
    conn = connect(tmp_path / "test.db")
    set_schema_version(conn, 5)

    ensure_schema_version(conn, 1)

    assert get_schema_version(conn) == 5
    conn.close()


def test_ensure_schema_version_upgrades_an_old_preexisting_database(tmp_path):
    """Simulates a real, already-deployed database created before schema-
    version tracking existed -- its version is 0 (SQLite's own default
    for PRAGMA user_version, never having been set), and connecting to
    it with the current code should stamp it with the current version."""
    db_path = tmp_path / "test.db"
    raw = connect(db_path)  # simulates an old store's own connect(), version never set
    raw.execute("CREATE TABLE t (x INTEGER)")
    raw.close()

    reopened = connect(db_path)
    assert get_schema_version(reopened) == 0  # confirms the "old" starting state
    ensure_schema_version(reopened, 1)
    assert get_schema_version(reopened) == 1
    reopened.close()
