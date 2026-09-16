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


def test_summarize_today_reports_the_most_recent_call(ledger_db):
    record_call(role="r1", model="m1", trigger="t1", status="FAILURE", error_class="TimeoutError", db_path=ledger_db)
    time.sleep(0.01)
    record_call(role="r2", model="m2", trigger="t2", status="SUCCESS", latency_ms=123.0, db_path=ledger_db)

    summary = summarize_today(db_path=ledger_db)
    assert summary["last_call"]["status"] == "SUCCESS"
    assert summary["last_call"]["model"] == "m2"
