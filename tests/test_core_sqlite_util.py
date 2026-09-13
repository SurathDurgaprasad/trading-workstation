"""core/sqlite_util.py -- the consolidated repository-wide SQLite
connection policy (WAL mode + explicit busy timeout)."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from core.sqlite_util import (
    DEFAULT_BUSY_TIMEOUT_SECONDS,
    DatabaseCorruptedError,
    MalformedRowError,
    connect,
    ensure_column,
    ensure_schema_version,
    get_schema_version,
    parse_model_json,
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


# --- autonomous hardening cycle: missing parent directory (a genuine fresh-clone bug) ---


def test_connect_creates_a_missing_parent_directory(tmp_path):
    """Real, reachable gap found by an SQLite-adversarial-resilience
    audit: sqlite3.connect() does NOT create a missing parent directory
    on its own (confirmed empirically -- it raises OperationalError).
    data/ is not tracked in git, so on a genuinely fresh clone this is
    exactly the first thing any command that touches a store hits."""
    nested_path = tmp_path / "does" / "not" / "exist" / "yet" / "test.db"
    assert not nested_path.parent.exists()

    conn = connect(nested_path)

    assert nested_path.parent.exists()
    conn.execute("CREATE TABLE t (x INTEGER)")  # confirms the connection is genuinely usable, not just the dir created
    conn.close()


def test_connect_creates_a_deeply_nested_missing_directory_tree():
    """The exact real scenario: a genuinely fresh clone where `data/`
    itself (not just a subdirectory of an existing data/) does not
    exist on disk at all yet."""
    import shutil
    import tempfile

    root = Path(tempfile.mkdtemp())
    try:
        db_path = root / "data" / "paper_trading.db"
        assert not db_path.parent.exists()

        conn = connect(db_path)

        assert db_path.parent.is_dir()
        conn.close()
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_connect_still_works_normally_for_memory_databases():
    """:memory: is not a real filesystem path -- confirms the new
    parent-directory-creation logic correctly skips it rather than
    trying to mkdir something meaningless."""
    conn = connect(":memory:")
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    assert conn.execute("SELECT x FROM t").fetchone()[0] == 1
    conn.close()


def test_connect_is_idempotent_when_the_parent_directory_already_exists(tmp_path):
    """Calling connect() twice against the same path (a real restart, or
    two stores sharing a data/ directory) must not raise on the second
    mkdir attempt."""
    db_path = tmp_path / "subdir" / "test.db"
    connect(db_path).close()

    conn2 = connect(db_path)  # must not raise
    conn2.close()


# --- autonomous hardening cycle: corrupted database file ------------------


def test_connect_against_a_corrupted_file_raises_a_clear_database_corrupted_error(tmp_path):
    """Real, reachable gap found by an SQLite-adversarial-resilience
    audit: sqlite3.connect() is lazy -- it succeeds even against a
    non-SQLite file, and only fails on the first real statement
    (PRAGMA journal_mode=WAL, issued by this exact function). Every
    one of the 12 stores' __init__ methods, and ~20+ of their real
    call sites across main.py/dashboard/mcp_server, previously let a
    raw sqlite3.DatabaseError propagate uncaught -- the dashboard in
    particular has no exception handler registered at all."""
    corrupt_path = tmp_path / "corrupted.db"
    corrupt_path.write_bytes(b"this is not a valid sqlite database file, deliberately corrupted for this test")

    with pytest.raises(DatabaseCorruptedError) as exc_info:
        connect(corrupt_path)
    assert str(corrupt_path) in str(exc_info.value)


def test_connect_against_a_truncated_file_also_raises_the_clear_error(tmp_path):
    """A truncated file (e.g. a process killed mid-write, or a copy that
    got cut off) is a distinct real-world corruption mode from a file
    that was never SQLite at all -- both must be caught the same way."""
    real_path = tmp_path / "real.db"
    connect(real_path).close()
    truncated_bytes = real_path.read_bytes()[:20]  # far too short to be a valid SQLite header/file
    truncated_path = tmp_path / "truncated.db"
    truncated_path.write_bytes(truncated_bytes)

    with pytest.raises(DatabaseCorruptedError):
        connect(truncated_path)


def test_connect_does_not_leave_a_dangling_open_connection_after_a_corruption_error(tmp_path):
    """The failed connection is explicitly closed before re-raising --
    confirms this by checking the corrupted file isn't left locked in a
    way that would prevent a subsequent attempt (e.g. after restoring
    from a backup) from opening it."""
    corrupt_path = tmp_path / "corrupted.db"
    corrupt_path.write_bytes(b"not a database")

    with pytest.raises(DatabaseCorruptedError):
        connect(corrupt_path)

    # Restoring a real database at the same path afterward must work cleanly --
    # proves the failed attempt above didn't leave anything locked or dangling.
    corrupt_path.unlink()
    restored = connect(corrupt_path)
    restored.execute("CREATE TABLE t (x INTEGER)")
    restored.close()


# --- autonomous hardening cycle: malformed data_json on read ---------------


def test_parse_model_json_round_trips_a_valid_row():
    from pydantic import BaseModel

    class _Model(BaseModel):
        name: str
        value: int

    original = _Model(name="test", value=42)

    parsed = parse_model_json(_Model, original.model_dump_json(), row_identifier="row-1")

    assert parsed == original


def test_parse_model_json_wraps_a_missing_required_field_in_a_clear_error():
    """The realistic real-world trigger: a required field genuinely
    missing from the stored JSON (external tampering, or a byte-level
    corruption of just this row rather than the whole file)."""
    import json

    from pydantic import BaseModel

    class _Model(BaseModel):
        name: str
        value: int

    malformed = json.dumps({"name": "test"})  # missing required "value"

    with pytest.raises(MalformedRowError) as exc_info:
        parse_model_json(_Model, malformed, row_identifier="row-42")

    assert "_Model" in str(exc_info.value)
    assert "row-42" in str(exc_info.value)


def test_parse_model_json_wraps_a_wrong_type_field_in_a_clear_error():
    import json

    from pydantic import BaseModel

    class _Model(BaseModel):
        name: str
        value: int

    malformed = json.dumps({"name": "test", "value": "not-an-int-and-not-coercible-xyz"})

    with pytest.raises(MalformedRowError):
        parse_model_json(_Model, malformed, row_identifier="row-1")


def test_parse_model_json_wraps_syntactically_invalid_json_too():
    from pydantic import BaseModel

    class _Model(BaseModel):
        name: str

    with pytest.raises(MalformedRowError):
        parse_model_json(_Model, "{not valid json at all", row_identifier="row-1")


def test_parse_model_json_error_names_the_actual_cause():
    """The wrapped error must still carry enough information to actually
    diagnose the problem, not just say "something went wrong"."""
    import json

    from pydantic import BaseModel

    class _Model(BaseModel):
        value: int

    with pytest.raises(MalformedRowError) as exc_info:
        parse_model_json(_Model, json.dumps({}), row_identifier="row-1")

    assert exc_info.value.model_name == "_Model"
    assert exc_info.value.row_identifier == "row-1"
