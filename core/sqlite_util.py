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


class DatabaseCorruptedError(Exception):
    """Autonomous hardening cycle: a real, previously-unguarded gap found
    by an SQLite-adversarial-resilience audit. `sqlite3.connect()` is
    lazy -- it succeeds even against a non-SQLite file (a text file, a
    truncated/corrupted .db) because it doesn't parse the file header;
    that only happens on the first real statement, which every caller of
    `connect()` hits immediately via the `PRAGMA journal_mode=WAL` call
    below. Previously, that raised a raw `sqlite3.DatabaseError: file is
    not a database` straight out of every one of the 12 stores'
    `__init__` methods, uncaught by any of their ~20+ real call sites
    across `main.py`/`dashboard/`/`live/workstation.py`/`mcp_server/` --
    the dashboard in particular has no exception handler registered at
    all, so this would have 500'd a request with a raw traceback rather
    than a clear, actionable error. Caught here, once, for every store
    at the single shared connection point, and re-raised as this clear,
    project-specific type naming the actual path -- a caller that wants
    to handle "this specific database file is corrupted" (as opposed to
    "locked" or "missing directory," both different, already-handled
    conditions) now has one exception type to catch instead of a bare
    sqlite3.DatabaseError that could also mean something else."""

    def __init__(self, db_path: str | Path, *, cause: Exception):
        self.db_path = str(db_path)
        super().__init__(
            f"Database file '{self.db_path}' could not be opened -- it may be corrupted, "
            f"truncated, or not a valid SQLite database ({type(cause).__name__}: {cause}). "
            "Restore from a backup, or move the file aside and let the application create a fresh one "
            "(this will lose the data in the corrupted file -- do this only if you have no other copy)."
        )


def connect(db_path: str | Path, *, busy_timeout_seconds: float = DEFAULT_BUSY_TIMEOUT_SECONDS) -> sqlite3.Connection:
    """The one place every store's own connection is opened. WAL mode +
    an explicit busy timeout, `isolation_level=None` (autocommit,
    matching every existing store's own convention unchanged).

    Autonomous hardening cycle: a real, reachable gap found by a
    dedicated SQLite-adversarial-resilience audit -- `sqlite3.connect()`
    does NOT create a missing parent directory (confirmed empirically:
    it raises `sqlite3.OperationalError: unable to open database file`),
    and this was previously the caller's job, done only ad hoc in a
    minority of call sites (`dashboard/intelligence.py`,
    `live/workstation.py`) -- absent from most of `main.py`'s ~20 direct
    store-construction sites and from every store's own `__init__`.
    `data/` itself is not tracked in git (no `.gitkeep`), so on a
    genuinely fresh clone it does not exist on disk at all. A prior
    "clean install" verification missed this entirely by accident: it
    ran the full `pytest` suite BEFORE the first real CLI smoke command,
    and some test's own side effect had already created `data/` along
    the way -- the true "first command ever run against a truly fresh
    clone" scenario (a real, plausible operator action: skip the tests,
    just try `python main.py scan ...`) was never actually exercised.
    Fixed here, once, for every one of the 12 stores' own `connect()`
    call -- not `exist_ok`-raced against a concurrent creator, since
    `mkdir(parents=True, exist_ok=True)` is already this project's own
    established idiom for exactly this (see `main.py`'s own
    `DEFAULT_LIVE_SIM_DB_PATH.parent.mkdir(...)`). `:memory:` (used
    throughout the test suite) is excluded -- it is not a real
    filesystem path, and `Path(":memory:").parent` would resolve to
    something meaningless."""
    db_path_str = str(db_path)
    if db_path_str != ":memory:":
        Path(db_path_str).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path_str, isolation_level=None, timeout=busy_timeout_seconds)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError as exc:
        # See DatabaseCorruptedError's own docstring: this is where a
        # corrupted/non-SQLite file at db_path actually fails (SQLite's
        # header is only parsed here, not at connect() itself).
        conn.close()
        raise DatabaseCorruptedError(db_path_str, cause=exc) from exc
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


def get_schema_version(conn: sqlite3.Connection) -> int:
    """SQLite's own built-in per-database-file integer, `PRAGMA
    user_version` -- zero cost (no extra table, no extra row), zero
    migration of its own (every database, including ones created before
    this function existed, already has it; it simply reads 0 for a file
    that has never had it set). Chosen over a hand-rolled
    `schema_version` table specifically because it needs no schema of
    its own to bootstrap -- a version-tracking mechanism that itself
    requires a successful migration to exist would be a contradiction."""
    return conn.execute("PRAGMA user_version").fetchone()[0]


def set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    """`version` is always this codebase's own hardcoded integer
    constant, never user input -- PRAGMA does not support parameter
    binding for its value, so this f-string is not a SQL-injection
    risk despite not being parameterized (same reasoning as
    `ensure_column`'s table/column names above)."""
    conn.execute(f"PRAGMA user_version = {int(version)}")


def ensure_schema_version(conn: sqlite3.Connection, version: int) -> None:
    """Records `version` via `set_schema_version` if the database's
    current version is lower -- idempotent (safe to call on every
    connect, not just once at creation), and never LOWERS an existing
    version (a newer on-disk schema opened by older code should not
    silently regress its own version marker, though nothing in this
    codebase does that today). Each store calls this once in its own
    `__init__`, after its own `_SCHEMA`/`ensure_column` calls have run,
    with its own store-specific `CURRENT_SCHEMA_VERSION` constant --
    there is no single shared version number across all 12 stores,
    since each has its own independent schema."""
    if get_schema_version(conn) < version:
        set_schema_version(conn, version)


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


class MalformedRowError(Exception):
    """Autonomous hardening cycle: a real, previously-unguarded gap found
    by an SQLite-adversarial-resilience audit. Every store in this
    project reconstructs its own model objects via
    `Model.model_validate_json(row["data_json"])`, unwrapped, at every
    `list_*`/`get_*` call site -- if a row's `data_json` is syntactically
    valid JSON but fails the model's own validation (a required field
    missing, a wrong type), this raised a raw, uncaught
    `pydantic.ValidationError` straight out of the store method. Under
    NORMAL operation this cannot happen (every row is written from an
    already-validated Pydantic instance's own `model_dump_json()`); it
    is reachable only via external tampering, low-level disk
    corruption of the row bytes specifically (as opposed to the whole
    file, already handled by `DatabaseCorruptedError`), or a genuine
    application bug -- schema EVOLUTION is deliberately NOT a cause,
    since this project's own established convention is to add new
    fields as optional-with-a-default (see `paper/models.py`'s
    `JournalEntry.decision_id`, `predictions/models.py`'s own
    documented backward-compatible-deserialization tests) specifically
    so old rows keep validating after a schema change. Low probability,
    but the impact of an unhandled crash (a whole scheduler tick
    aborted, or an unhandled dashboard 500 -- the dashboard registers no
    exception handler at all) is real enough to warrant a clear,
    typed, diagnosable error instead of a raw traceback."""

    def __init__(self, *, model_name: str, row_identifier: str, cause: Exception):
        self.model_name = model_name
        self.row_identifier = row_identifier
        super().__init__(
            f"A stored {model_name} row ({row_identifier}) failed to deserialize: "
            f"{type(cause).__name__}: {cause}. This row's data_json is malformed or no longer "
            f"matches the {model_name} schema -- this should not happen under normal operation "
            "(every row is written from an already-validated model instance)."
        )


def parse_model_json(model_cls, data_json: str, *, row_identifier: str = "?"):
    """The shared, safe replacement for a bare `model_cls.model_validate_json(data_json)`
    call -- wraps pydantic's own `ValidationError` (and a malformed-JSON
    `ValueError`, which `model_validate_json` also raises for syntactically
    invalid JSON) into the clear `MalformedRowError` above, naming the
    model and the row, instead of letting a raw pydantic exception
    propagate. `row_identifier` should be whatever this row's own natural
    key is (a prediction_id, order_id, run_id, ...) -- purely for a
    diagnostic message, never used for any lookup."""
    from pydantic import ValidationError

    try:
        return model_cls.model_validate_json(data_json)
    except (ValidationError, ValueError) as exc:
        raise MalformedRowError(model_name=model_cls.__name__, row_identifier=row_identifier, cause=exc) from exc
