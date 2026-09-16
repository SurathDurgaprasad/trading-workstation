"""OpenAI Intelligence Integration, Phase 4/13: the cost-control choke
point every real OpenAI call must pass through. These tests use a real
temp SQLite ledger (never the production one) and never make a real
network call -- llm.budget has no network dependency at all, it only
gates and records, which is exactly why it can be tested in isolation
from agents.analyst/llm.provider.
"""

import time

import pytest

from llm.budget import (
    AIBudgetExceededError,
    BudgetLimits,
    _reset_session_count_for_tests,
    check_budget,
    record_call,
    summarize_today,
)


@pytest.fixture(autouse=True)
def _reset_session_counter():
    # llm.budget's session-call counter is deliberately process-local
    # (a fresh CLI invocation is a fresh session) -- reset it around every
    # test so accumulation across test functions/files can't make
    # max_calls_per_session assertions order-dependent/flaky.
    _reset_session_count_for_tests()
    yield
    _reset_session_count_for_tests()


@pytest.fixture
def ledger_db(tmp_path):
    return tmp_path / "ai_call_ledger.db"


def test_first_call_is_allowed(ledger_db):
    check_budget(input_chars=100, db_path=ledger_db, limits=BudgetLimits())


def test_min_interval_blocks_a_second_call_too_soon(ledger_db):
    limits = BudgetLimits(min_interval_seconds=5.0)
    check_budget(input_chars=10, db_path=ledger_db, limits=limits)
    record_call(role="r", model="m", trigger="t", status="SUCCESS", db_path=ledger_db)

    with pytest.raises(AIBudgetExceededError):
        check_budget(input_chars=10, db_path=ledger_db, limits=limits)


def test_min_interval_allows_a_call_after_enough_time_passes(ledger_db):
    limits = BudgetLimits(min_interval_seconds=0.05)
    check_budget(input_chars=10, db_path=ledger_db, limits=limits)
    record_call(role="r", model="m", trigger="t", status="SUCCESS", db_path=ledger_db)

    time.sleep(0.06)
    check_budget(input_chars=10, db_path=ledger_db, limits=limits)  # must not raise


def test_max_calls_per_hour_is_enforced(ledger_db):
    limits = BudgetLimits(max_calls_per_hour=2, min_interval_seconds=0.0)
    for _ in range(2):
        check_budget(input_chars=10, db_path=ledger_db, limits=limits)
        record_call(role="r", model="m", trigger="t", status="SUCCESS", db_path=ledger_db)

    with pytest.raises(AIBudgetExceededError):
        check_budget(input_chars=10, db_path=ledger_db, limits=limits)


def test_max_calls_per_session_is_enforced(ledger_db):
    limits = BudgetLimits(max_calls_per_session=2, min_interval_seconds=0.0, max_calls_per_hour=1000)
    for _ in range(2):
        check_budget(input_chars=10, db_path=ledger_db, limits=limits)
        record_call(role="r", model="m", trigger="t", status="SUCCESS", db_path=ledger_db)

    with pytest.raises(AIBudgetExceededError):
        check_budget(input_chars=10, db_path=ledger_db, limits=limits)


def test_max_input_chars_is_enforced_before_any_db_access(ledger_db):
    limits = BudgetLimits(max_input_chars=50)
    with pytest.raises(AIBudgetExceededError):
        check_budget(input_chars=51, db_path=ledger_db, limits=limits)


def test_budget_rejected_calls_do_not_themselves_count_toward_the_hourly_limit(ledger_db):
    # A caller that hits the budget gate and gets rejected, then records a
    # BUDGET_REJECTED row (as agents.analyst.invoke_structured does), must
    # not have that rejection itself count as a "call" for future budget
    # checks -- otherwise a burst of rejections would permanently wedge
    # the hourly counter even though zero real OpenAI requests fired.
    limits = BudgetLimits(max_calls_per_hour=100, min_interval_seconds=1000.0)
    check_budget(input_chars=10, db_path=ledger_db, limits=limits)
    record_call(role="r", model="m", trigger="t", status="SUCCESS", db_path=ledger_db)

    for _ in range(5):
        with pytest.raises(AIBudgetExceededError):
            check_budget(input_chars=10, db_path=ledger_db, limits=limits)
        record_call(role="r", model="m", trigger="t", status="BUDGET_REJECTED", db_path=ledger_db)

    summary = summarize_today(db_path=ledger_db)
    assert summary["calls_today"] == 6
    assert summary["successes_today"] == 1


def test_record_call_never_writes_the_prompt_text_or_api_key(ledger_db):
    # llm.budget's schema has no column for prompt text, API key, or
    # request/response body -- this test locks that in structurally,
    # rather than just trusting the current column list stays that way.
    record_call(role="r", model="m", trigger="t", status="SUCCESS", input_chars=999, db_path=ledger_db)

    import sqlite3

    conn = sqlite3.connect(str(ledger_db))
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(ai_calls)")}
    finally:
        conn.close()

    forbidden = {"prompt", "response", "api_key", "authorization", "output", "text"}
    assert not (columns & forbidden), f"ai_calls table has a column that could hold sensitive content: {columns & forbidden}"


def test_check_budget_and_record_call_honor_a_monkeypatched_default_ledger_path(monkeypatch, tmp_path):
    # Real production incident this session: record_call/check_budget's
    # db_path parameter previously defaulted to the module-level
    # DEFAULT_LEDGER_DB_PATH VALUE bound once at import time --
    # monkeypatching llm.budget.DEFAULT_LEDGER_DB_PATH afterward (exactly
    # what tests/conftest.py's autouse _isolate_ai_call_ledger fixture
    # does for every test in this suite) had NO effect on already-defined
    # functions' default arguments, so every caller that omits db_path
    # (agents.analyst.invoke_structured always does) kept silently
    # writing to the REAL production ledger no matter what was patched.
    # This test proves the fix (db_path=None, resolved inside the
    # function body) actually honors the patched value -- independent of
    # tests/conftest.py's own autouse fixture (which has already patched
    # DEFAULT_LEDGER_DB_PATH to its OWN tmp_path by the time this test
    # body runs), so it re-patches to a second, distinct fake path here
    # and asserts writes land there, not wherever conftest last pointed.
    import llm.budget as budget_module

    ledger_before_this_test = budget_module.DEFAULT_LEDGER_DB_PATH  # conftest's per-test tmp_path, not production
    fake_ledger = tmp_path / "isolated.db"
    monkeypatch.setattr(budget_module, "DEFAULT_LEDGER_DB_PATH", fake_ledger)

    check_budget(input_chars=10)  # no db_path passed -- must resolve to the patched value
    record_call(role="r", model="m", trigger="t", status="SUCCESS")  # same

    # Query fake_ledger directly rather than just checking existence --
    # check_budget's own read-only _connect() call creates an empty
    # SQLite file as a side effect regardless of whether record_call's
    # write actually lands there, so file existence alone would not have
    # caught the original bug (a mutation confirmed this: the mutated
    # record_call() still passed a fake_ledger.exists()-only assertion,
    # because check_budget innocently created the empty file first).
    row_count_in_fake_ledger = summarize_today(db_path=fake_ledger)["calls_today"]
    assert row_count_in_fake_ledger == 1, (
        f"expected record_call's row in the monkeypatched ledger {fake_ledger}, found {row_count_in_fake_ledger}"
    )
    assert fake_ledger != ledger_before_this_test


def test_summarize_today_reports_the_most_recent_call(ledger_db):
    record_call(role="r1", model="m1", trigger="t1", status="FAILURE", error_class="TimeoutError", db_path=ledger_db)
    time.sleep(0.01)
    record_call(role="r2", model="m2", trigger="t2", status="SUCCESS", latency_ms=123.0, db_path=ledger_db)

    summary = summarize_today(db_path=ledger_db)
    assert summary["last_call"]["status"] == "SUCCESS"
    assert summary["last_call"]["model"] == "m2"
