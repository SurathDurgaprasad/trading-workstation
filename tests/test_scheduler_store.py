import threading
from datetime import datetime, timedelta, timezone

import pytest

from scheduler.models import RunStatus
from scheduler.store import SchedulerRunStore


@pytest.fixture
def store(tmp_path):
    s = SchedulerRunStore(tmp_path / "runs.db")
    yield s
    s.close()


def test_start_run_persists_a_running_record(store):
    now = datetime.now(timezone.utc)
    record = store.start_run(run_id="r1", slot_name="pre_market", run_date="2026-09-03", started_at=now)
    assert record.status == RunStatus.RUNNING
    assert record.finished_at is None

    fetched = store.get_run("r1")
    assert fetched is not None
    assert fetched.slot_name == "pre_market"
    assert fetched.status == RunStatus.RUNNING


def test_finish_run_updates_status_and_finished_at(store):
    store.start_run(run_id="r1", slot_name="intraday", run_date="2026-09-03", started_at=datetime.now(timezone.utc))
    updated = store.finish_run(run_id="r1", status=RunStatus.COMPLETED, detail="1 candidate scanned")

    assert updated.status == RunStatus.COMPLETED
    assert updated.finished_at is not None
    assert updated.detail == "1 candidate scanned"

    fetched = store.get_run("r1")
    assert fetched.status == RunStatus.COMPLETED


def test_finish_run_raises_for_unknown_run_id(store):
    with pytest.raises(ValueError, match="never started"):
        store.finish_run(run_id="does-not-exist", status=RunStatus.COMPLETED)


def test_active_lock_is_none_when_nothing_running(store):
    assert store.active_lock() is None


def test_active_lock_returns_the_running_record(store):
    store.start_run(run_id="r1", slot_name="pre_market", run_date="2026-09-03", started_at=datetime.now(timezone.utc))
    lock = store.active_lock()
    assert lock is not None
    assert lock.run_id == "r1"


def test_active_lock_ignores_finished_runs(store):
    store.start_run(run_id="r1", slot_name="pre_market", run_date="2026-09-03", started_at=datetime.now(timezone.utc))
    store.finish_run(run_id="r1", status=RunStatus.COMPLETED)
    assert store.active_lock() is None


def test_reclaim_stale_locks_leaves_fresh_locks_alone(store):
    now = datetime.now(timezone.utc)
    store.start_run(run_id="r1", slot_name="intraday", run_date="2026-09-03", started_at=now)

    reclaimed = store.reclaim_stale_locks(staleness_seconds=1800, now=now + timedelta(seconds=60))
    assert reclaimed == []
    assert store.active_lock() is not None  # still held


def test_reclaim_stale_locks_frees_an_orphaned_lock_for_restart_recovery(store):
    started_at = datetime.now(timezone.utc) - timedelta(hours=2)
    store.start_run(run_id="r1", slot_name="intraday", run_date="2026-09-03", started_at=started_at)

    reclaimed = store.reclaim_stale_locks(staleness_seconds=1800, now=datetime.now(timezone.utc))

    assert len(reclaimed) == 1
    assert reclaimed[0].run_id == "r1"
    assert reclaimed[0].status == RunStatus.RECLAIMED
    assert store.active_lock() is None  # lock is free again -- a new run can start


def test_has_completed_today_true_only_for_a_completed_run_on_that_date(store):
    store.start_run(run_id="r1", slot_name="pre_market", run_date="2026-09-03", started_at=datetime.now(timezone.utc))
    assert store.has_completed_today(slot_name="pre_market", run_date="2026-09-03") is False  # still RUNNING

    store.finish_run(run_id="r1", status=RunStatus.COMPLETED)
    assert store.has_completed_today(slot_name="pre_market", run_date="2026-09-03") is True
    assert store.has_completed_today(slot_name="pre_market", run_date="2026-09-04") is False
    assert store.has_completed_today(slot_name="market_open", run_date="2026-09-03") is False


def test_failed_run_does_not_count_as_completed(store):
    """A FAILED run must not satisfy 'already done' -- otherwise a
    transient failure would permanently block that slot for the rest of
    the trading day, contradicting the roadmap's "safely resume" goal."""
    store.start_run(run_id="r1", slot_name="pre_market", run_date="2026-09-03", started_at=datetime.now(timezone.utc))
    store.finish_run(run_id="r1", status=RunStatus.FAILED, error="boom")
    assert store.has_completed_today(slot_name="pre_market", run_date="2026-09-03") is False


def test_latest_run_for_slot_today_returns_most_recent_finished_run(store):
    t1 = datetime.now(timezone.utc) - timedelta(hours=2)
    t2 = datetime.now(timezone.utc) - timedelta(hours=1)
    store.start_run(run_id="r1", slot_name="intraday", run_date="2026-09-03", started_at=t1)
    store.finish_run(run_id="r1", status=RunStatus.COMPLETED, finished_at=t1)
    store.start_run(run_id="r2", slot_name="intraday", run_date="2026-09-03", started_at=t2)
    store.finish_run(run_id="r2", status=RunStatus.COMPLETED, finished_at=t2)

    latest = store.latest_run_for_slot_today(slot_name="intraday", run_date="2026-09-03")
    assert latest is not None
    assert latest.run_id == "r2"


def test_latest_run_for_slot_today_ignores_still_running(store):
    store.start_run(run_id="r1", slot_name="intraday", run_date="2026-09-03", started_at=datetime.now(timezone.utc))
    assert store.latest_run_for_slot_today(slot_name="intraday", run_date="2026-09-03") is None


def test_list_runs_orders_most_recent_first(store):
    t1 = datetime.now(timezone.utc) - timedelta(minutes=10)
    t2 = datetime.now(timezone.utc)
    store.start_run(run_id="r1", slot_name="pre_market", run_date="2026-09-03", started_at=t1)
    store.start_run(run_id="r2", slot_name="market_open", run_date="2026-09-03", started_at=t2)

    runs = store.list_runs(limit=10)
    assert [r.run_id for r in runs] == ["r2", "r1"]


def test_list_runs_respects_limit(store):
    for i in range(5):
        store.start_run(run_id=f"r{i}", slot_name="intraday", run_date="2026-09-03", started_at=datetime.now(timezone.utc))
    assert len(store.list_runs(limit=2)) == 2


def test_try_start_run_inserts_when_no_lock_is_held(tmp_path):
    store = SchedulerRunStore(tmp_path / "runs.db")
    record = store.try_start_run(run_id="r1", slot_name="intraday", run_date="2026-09-03", started_at=datetime.now(timezone.utc))
    store.close()
    assert record is not None
    assert record.run_id == "r1"


def test_try_start_run_returns_none_when_a_lock_is_already_held(store):
    store.start_run(run_id="held", slot_name="intraday", run_date="2026-09-03", started_at=datetime.now(timezone.utc))
    second = store.try_start_run(run_id="r2", slot_name="intraday", run_date="2026-09-03", started_at=datetime.now(timezone.utc))
    assert second is None
    assert [r.run_id for r in store.list_runs()] == ["held"]  # nothing extra was inserted


def test_try_start_run_is_atomic_under_real_concurrent_contention(tmp_path):
    """Two SEPARATE connections to the SAME db file (simulating two
    scheduler processes racing on one run-db) must never both succeed --
    this is the actual regression test for the TOCTOU race
    `active_lock()` + `start_run()` used to have."""
    # Each thread opens its OWN sqlite3 connection to the same file --
    # Python's sqlite3 module forbids sharing one connection across
    # threads (`check_same_thread=True` by default), and a connection
    # opened per thread is also the more faithful simulation of two
    # separate OS processes each holding their own connection anyway.
    db_path = tmp_path / "runs.db"
    SchedulerRunStore(db_path).close()  # create the file/schema before threads race on it

    results: dict[str, object] = {}
    barrier = threading.Barrier(2)

    def _attempt(key: str) -> None:
        store = SchedulerRunStore(db_path)
        try:
            barrier.wait()
            results[key] = store.try_start_run(run_id=key, slot_name="intraday", run_date="2026-09-03", started_at=datetime.now(timezone.utc))
        finally:
            store.close()

    t1 = threading.Thread(target=_attempt, args=("a",))
    t2 = threading.Thread(target=_attempt, args=("b",))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    winners = [key for key, value in results.items() if value is not None]
    assert len(winners) == 1, f"exactly one racing start must win a shared lock, got {results}"


def test_reopening_the_same_db_path_preserves_history(tmp_path):
    db_path = tmp_path / "runs.db"
    store1 = SchedulerRunStore(db_path)
    store1.start_run(run_id="r1", slot_name="pre_market", run_date="2026-09-03", started_at=datetime.now(timezone.utc))
    store1.finish_run(run_id="r1", status=RunStatus.COMPLETED)
    store1.close()

    store2 = SchedulerRunStore(db_path)
    assert store2.has_completed_today(slot_name="pre_market", run_date="2026-09-03") is True
    store2.close()
