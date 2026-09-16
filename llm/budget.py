"""AI call budget/rate limiting and audit ledger.

The OpenAI credit balance behind this project is small and prepaid. This
module is the single choke point every real LLM call must pass through
before firing a request, and the single place every call (success or
failure) gets recorded -- so `ai-health`, the dashboard AI status, and the
final report can all read one source of truth instead of re-deriving usage
from scattered logs.

Deliberately SQLite-backed (not in-memory) so the hourly/session limits are
honest across separate CLI invocations, not just within one long-running
process -- a `decide` command run 10 times in a row from 10 separate shells
must still be capped.

Nothing here ever stores or logs the API key; only call metadata (role,
model, latency, token counts if the SDK reports them, and the exception
*class name* -- never the exception's full text, since a raised HTTP error
can otherwise leak an Authorization header value into str(exc)).
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from llm.errors import AIBudgetExceededError

DEFAULT_LEDGER_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "ai_call_ledger.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ai_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc TEXT NOT NULL,
    role TEXT NOT NULL,
    model TEXT NOT NULL,
    trigger TEXT NOT NULL,
    status TEXT NOT NULL,
    latency_ms REAL,
    input_chars INTEGER,
    output_tokens INTEGER,
    error_class TEXT
)
"""

_lock = threading.Lock()


@dataclass(frozen=True)
class BudgetLimits:
    """Conservative defaults for a small prepaid OpenAI balance.

    max_input_chars caps the structured evidence packet (Phase 5) -- this
    project must never dump raw source code or full bar histories into a
    prompt; a compact per-symbol snapshot is a few hundred characters, so
    4000 is already generous headroom, not a target to fill.
    """

    max_calls_per_hour: int = 10
    max_calls_per_session: int = 30
    min_interval_seconds: float = 20.0
    max_input_chars: int = 4000


DEFAULT_LIMITS = BudgetLimits()

# Session = this process's lifetime. Intentionally process-local (not
# persisted) -- a fresh CLI invocation is a fresh session by definition.
_session_call_count = 0


@contextmanager
def _connect(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    try:
        conn.execute(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def check_budget(
    *,
    input_chars: int,
    db_path: Path | None = None,
    limits: BudgetLimits = DEFAULT_LIMITS,
) -> None:
    """Raise AIBudgetExceededError if firing a call now would violate any limit.

    Must be called immediately before every real OpenAI request, with no
    other gate in between -- callers must not cache a "budget OK" result
    across calls.

    db_path defaults to None (resolved to the CURRENT value of
    DEFAULT_LEDGER_DB_PATH inside the function body, not at def time) so
    that tests/conftest.py's autouse fixture -- which monkeypatches
    llm.budget.DEFAULT_LEDGER_DB_PATH to an isolated tmp_path for every
    test -- actually takes effect. A plain `db_path: Path =
    DEFAULT_LEDGER_DB_PATH` default is bound once at import time and would
    silently keep pointing at the real production ledger no matter what a
    test patches afterward -- exactly the real defect this project's own
    test suite hit: every mocked/fake LLM call exercised by
    agents.analyst.invoke_structured's tests (decision narration, research
    summarizer, decision reviewer, etc., none of which pass a db_path)
    was being recorded into data/ai_call_ledger.db, corrupting the
    real ai-health/dashboard call history with sub-millisecond,
    obviously-fake test latencies."""
    resolved_db_path = db_path if db_path is not None else DEFAULT_LEDGER_DB_PATH
    global _session_call_count

    if input_chars > limits.max_input_chars:
        raise AIBudgetExceededError(
            f"input is {input_chars} chars, exceeds max_input_chars={limits.max_input_chars}"
        )

    with _lock:
        if _session_call_count >= limits.max_calls_per_session:
            raise AIBudgetExceededError(
                f"session call count {_session_call_count} >= max_calls_per_session={limits.max_calls_per_session}"
            )

        with _connect(resolved_db_path) as conn:
            now = datetime.now(timezone.utc)
            one_hour_ago = (now - timedelta(hours=1)).isoformat()
            hour_count = conn.execute(
                "SELECT COUNT(*) FROM ai_calls WHERE ts_utc >= ? AND status != 'BUDGET_REJECTED'",
                (one_hour_ago,),
            ).fetchone()[0]
            if hour_count >= limits.max_calls_per_hour:
                raise AIBudgetExceededError(
                    f"{hour_count} calls in the last hour >= max_calls_per_hour={limits.max_calls_per_hour}"
                )

            last_row = conn.execute(
                "SELECT ts_utc FROM ai_calls WHERE status != 'BUDGET_REJECTED' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if last_row is not None:
                last_ts = datetime.fromisoformat(last_row[0])
                elapsed = (now - last_ts).total_seconds()
                if elapsed < limits.min_interval_seconds:
                    raise AIBudgetExceededError(
                        f"only {elapsed:.1f}s since the last call, "
                        f"< min_interval_seconds={limits.min_interval_seconds}"
                    )

        _session_call_count += 1


def record_call(
    *,
    role: str,
    model: str,
    trigger: str,
    status: str,
    latency_ms: float | None = None,
    input_chars: int | None = None,
    output_tokens: int | None = None,
    error_class: str | None = None,
    db_path: Path | None = None,
) -> None:
    """Append one row to the audit ledger. status is a short label, e.g.
    'SUCCESS', 'FAILURE', 'TIMEOUT', 'BUDGET_REJECTED'.

    db_path resolved lazily -- see check_budget's docstring for why."""
    resolved_db_path = db_path if db_path is not None else DEFAULT_LEDGER_DB_PATH
    with _connect(resolved_db_path) as conn:
        conn.execute(
            "INSERT INTO ai_calls (ts_utc, role, model, trigger, status, latency_ms, "
            "input_chars, output_tokens, error_class) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(),
                role,
                model,
                trigger,
                status,
                latency_ms,
                input_chars,
                output_tokens,
                error_class,
            ),
        )


def _reset_session_count_for_tests() -> None:
    """Test-only: reset the process-local session call counter so tests in
    the same pytest process don't accumulate toward max_calls_per_session
    across unrelated test functions/files."""
    global _session_call_count
    with _lock:
        _session_call_count = 0


def summarize_today(db_path: Path | None = None) -> dict:
    """Read-only rollup used by `ai-health` and the dashboard AI status panel.

    db_path resolved lazily -- see check_budget's docstring for why."""
    resolved_db_path = db_path if db_path is not None else DEFAULT_LEDGER_DB_PATH
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    with _connect(resolved_db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM ai_calls WHERE ts_utc >= ?", (today_start,)).fetchone()[0]
        success = conn.execute(
            "SELECT COUNT(*) FROM ai_calls WHERE ts_utc >= ? AND status = 'SUCCESS'", (today_start,)
        ).fetchone()[0]
        last_row = conn.execute(
            "SELECT ts_utc, status, latency_ms, model, error_class FROM ai_calls ORDER BY id DESC LIMIT 1"
        ).fetchone()

    last_call = None
    if last_row is not None:
        last_call = {
            "ts_utc": last_row[0],
            "status": last_row[1],
            "latency_ms": last_row[2],
            "model": last_row[3],
            "error_class": last_row[4],
        }

    return {
        "calls_today": total,
        "successes_today": success,
        "last_call": last_call,
    }
