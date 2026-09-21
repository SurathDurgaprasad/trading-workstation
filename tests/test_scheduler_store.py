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


# --- autonomous hardening cycle 8: finish_run terminal-state guard ----------
#
# Real defect found via a state-machine attack: finish_run() previously had
# NO guard at all -- a "zombie" caller that finishes late, after its own
# run was already reclaimed as stale by another process, could silently
# overwrite RECLAIMED back to COMPLETED/FAILED, corrupting the audit trail.


def test_finish_run_on_a_reclaimed_run_raises_and_does_not_overwrite_it(store):
    from scheduler.errors import InvalidRunTransitionError

    started_at = datetime.now(timezone.utc) - timedelta(hours=2)
    store.start_run(run_id="r1", slot_name="intraday", run_date="2026-09-14", started_at=started_at)
    reclaimed = store.reclaim_stale_locks(staleness_seconds=1800, now=datetime.now(timezone.utc))
    assert reclaimed[0].status == RunStatus.RECLAIMED

    # A NEW run legitimately starts for the same slot once reclaim frees the lock.
    store.start_run(run_id="r2", slot_name="intraday", run_date="2026-09-14", started_at=datetime.now(timezone.utc))

    # The "zombie" original process (r1) finally wakes up and tries to report success.
    with pytest.raises(InvalidRunTransitionError, match="r1"):
        store.finish_run(run_id="r1", status=RunStatus.COMPLETED, detail="zombie process finished late")

    # r1's audit trail is untouched -- still RECLAIMED, not silently COMPLETED.
    assert store.get_run("r1").status == RunStatus.RECLAIMED
    # r2 (the real, current run) is completely unaffected.
    assert store.active_lock().run_id == "r2"


def test_finish_run_on_an_already_completed_run_raises(store):
    from scheduler.errors import InvalidRunTransitionError

    store.start_run(run_id="r1", slot_name="intraday", run_date="2026-09-14", started_at=datetime.now(timezone.utc))
    store.finish_run(run_id="r1", status=RunStatus.COMPLETED)

    with pytest.raises(InvalidRunTransitionError):
        store.finish_run(run_id="r1", status=RunStatus.FAILED, error="a duplicate/late finish_run call")

    assert store.get_run("r1").status == RunStatus.COMPLETED  # first result stands


def test_finish_run_on_an_already_failed_run_raises(store):
    from scheduler.errors import InvalidRunTransitionError

    store.start_run(run_id="r1", slot_name="intraday", run_date="2026-09-14", started_at=datetime.now(timezone.utc))
    store.finish_run(run_id="r1", status=RunStatus.FAILED, error="boom")

    with pytest.raises(InvalidRunTransitionError):
        store.finish_run(run_id="r1", status=RunStatus.COMPLETED)

    assert store.get_run("r1").status == RunStatus.FAILED


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


def test_reclaim_stale_locks_works_across_a_real_process_restart(tmp_path):
    """Final-product-hardening restart-recovery gap: the test above
    exercises reclaim_stale_locks on the SAME store instance that
    started the run -- a real crash means the ORIGINAL process (and its
    connection) is gone; recovery happens from a freshly-started process
    opening a NEW SchedulerRunStore on the same db file. This is the
    scenario that actually matters (a killed `schedule loop` process,
    restarted later) -- proves the on-disk RUNNING row, not any
    in-memory state, is what makes recovery real."""
    db_path = tmp_path / "runs.db"
    crashed = SchedulerRunStore(db_path)
    started_at = datetime.now(timezone.utc) - timedelta(hours=2)
    crashed.start_run(run_id="r1", slot_name="intraday", run_date="2026-09-03", started_at=started_at)
    # Simulate a crash: the process dies without ever calling finish_run.
    # No explicit close() either -- a real kill -9 wouldn't get one.

    restarted = SchedulerRunStore(db_path)
    assert restarted.active_lock() is not None  # the orphaned lock is visible to the new process

    reclaimed = restarted.reclaim_stale_locks(staleness_seconds=1800, now=datetime.now(timezone.utc))

    assert len(reclaimed) == 1
    assert reclaimed[0].run_id == "r1"
    assert reclaimed[0].status == RunStatus.RECLAIMED
    assert restarted.active_lock() is None  # a new run can now start
    restarted.close()


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


def test_try_start_run_is_atomic_under_real_os_subprocess_contention(tmp_path):
    """Autonomous hardening cycle 27 -- the thread-based test above proves
    the SQLite-level atomicity of try_start_run's `BEGIN IMMEDIATE` lock
    against two connections in ONE Python process; this test goes one
    level further, per this cycle's own mission ("Thread tests are
    useful but do not replace process-level tests for restart
    semantics"): two GENUINELY SEPARATE OS processes (real subprocess.
    Popen calls, not threads sharing one interpreter/GIL/page cache),
    each with their own independent sqlite3 connection, racing
    try_start_run against the SAME run-db file -- the faithful simulation
    of the exact scenario try_start_run's own docstring names: "an
    operator accidentally running both `schedule loop` and a
    cron-triggered `schedule tick` against one database."

    Repeated 10 times (fresh db per repetition), and each worker uses a
    real CROSS-PROCESS FILE BARRIER (not just launched back-to-back) --
    Python interpreter startup (~50-100ms) dwarfs the actual SQLite
    operations under test (microseconds), so two subprocesses merely
    Popen'd back-to-back rarely have their try_start_run calls genuinely
    overlap; a first version of this test without the barrier was found
    to NOT actually kill a deliberate mutation of try_start_run's own
    BEGIN IMMEDIATE -> plain BEGIN (deferred locking), passing 3/3 times
    regardless -- exactly the kind of silently-too-weak test this
    cycle's own mission warns about ("A surviving realistic safety
    mutant is a defect in either production code or test coverage").
    Each worker therefore completes ALL its slow setup (interpreter
    start, imports, opening its own SQLite connection) BEFORE signaling
    readiness via a marker file, then spins polling for the OTHER
    worker's marker file before calling try_start_run -- forcing both
    processes to enter the actual race window at nearly the same real
    wall-clock moment, the process-level equivalent of the thread test's
    threading.Barrier above."""
    import subprocess
    import sys

    from core.config import PROJECT_ROOT

    worker_path = tmp_path / "_try_start_run_worker.py"
    worker_path.write_text(
        "import sys, os, time\n"
        f"sys.path.insert(0, {str(PROJECT_ROOT)!r})\n"
        "from datetime import datetime, timezone\n"
        "from scheduler.store import SchedulerRunStore\n"
        "db_path, run_id, ready_dir = sys.argv[1], sys.argv[2], sys.argv[3]\n"
        "store = SchedulerRunStore(db_path)\n"  # all slow setup happens BEFORE the barrier
        "other = 'b' if run_id == 'a' else 'a'\n"
        "with open(os.path.join(ready_dir, run_id + '.ready'), 'w') as f:\n"
        "    f.write('1')\n"
        "deadline = time.time() + 10\n"
        "while not os.path.exists(os.path.join(ready_dir, other + '.ready')):\n"
        "    if time.time() > deadline:\n"
        "        print('BARRIER_TIMEOUT')\n"
        "        sys.exit(1)\n"
        "    time.sleep(0.0005)\n"
        "record = store.try_start_run(run_id=run_id, slot_name='intraday', run_date='2026-09-03', started_at=datetime.now(timezone.utc))\n"
        "print('ACQUIRED' if record is not None else 'NONE')\n"
        "store.close()\n",
        encoding="utf-8",
    )

    for i in range(10):
        db_path = tmp_path / f"subprocess_runs_{i}.db"
        SchedulerRunStore(db_path).close()  # create the file/schema before the subprocesses race on it
        ready_dir = tmp_path / f"ready_{i}"
        ready_dir.mkdir()

        p1 = subprocess.Popen([sys.executable, str(worker_path), str(db_path), "a", str(ready_dir)], stdout=subprocess.PIPE, text=True)
        p2 = subprocess.Popen([sys.executable, str(worker_path), str(db_path), "b", str(ready_dir)], stdout=subprocess.PIPE, text=True)
        out1, _ = p1.communicate(timeout=30)
        out2, _ = p2.communicate(timeout=30)

        results = [out1.strip(), out2.strip()]
        assert "BARRIER_TIMEOUT" not in results, f"repetition {i}: barrier itself failed (test infrastructure, not the property under test): {results}"
        assert results.count("ACQUIRED") == 1, f"repetition {i}: expected exactly one process to acquire the lock, got {results}"
        assert results.count("NONE") == 1, f"repetition {i}: expected exactly one process to be refused, got {results}"

        store = SchedulerRunStore(db_path)
        runs = store.list_runs()
        store.close()
        assert len(runs) == 1, f"repetition {i}: two real OS processes must never both persist a RUNNING row for the same lock -- found {len(runs)}"


def test_reopening_the_same_db_path_preserves_history(tmp_path):
    db_path = tmp_path / "runs.db"
    store1 = SchedulerRunStore(db_path)
    store1.start_run(run_id="r1", slot_name="pre_market", run_date="2026-09-03", started_at=datetime.now(timezone.utc))
    store1.finish_run(run_id="r1", status=RunStatus.COMPLETED)
    store1.close()

    store2 = SchedulerRunStore(db_path)
    assert store2.has_completed_today(slot_name="pre_market", run_date="2026-09-03") is True
    store2.close()


# --- Phase 39: integrity_check / db_size_bytes -------------------------------


def test_integrity_check_reports_ok_for_a_healthy_database(store):
    store.start_run(run_id="r1", slot_name="pre_market", run_date="2026-09-03", started_at=datetime.now(timezone.utc))
    assert store.integrity_check() == "ok"


def test_db_size_bytes_reflects_a_real_file_that_grows(tmp_path):
    db_path = tmp_path / "runs.db"
    store = SchedulerRunStore(db_path)
    empty_size = store.db_size_bytes()
    assert empty_size > 0  # sqlite always writes at least a header page

    for i in range(50):
        store.start_run(run_id=f"r{i}", slot_name="intraday", run_date="2026-09-03", started_at=datetime.now(timezone.utc))
        store.finish_run(run_id=f"r{i}", status=RunStatus.COMPLETED, detail="x" * 500)
    store.close()

    store2 = SchedulerRunStore(db_path)
    assert store2.db_size_bytes() >= empty_size
    store2.close()


def test_db_size_bytes_is_zero_for_a_path_that_does_not_exist(tmp_path):
    store = SchedulerRunStore(tmp_path / "runs.db")
    store.close()
    import os

    os.remove(tmp_path / "runs.db")
    assert store.db_size_bytes() == 0


# --- final-product-hardening: per-slot last-success/last-failure -----------


def test_last_successful_run_for_slot_is_none_when_nothing_has_run(store):
    assert store.last_successful_run_for_slot("pre_market") is None


def test_last_successful_run_for_slot_finds_the_most_recent_completion(store):
    store.start_run(run_id="r1", slot_name="pre_market", run_date="2026-09-01", started_at=datetime(2026, 9, 1, tzinfo=timezone.utc))
    store.finish_run(run_id="r1", status=RunStatus.COMPLETED, finished_at=datetime(2026, 9, 1, 1, tzinfo=timezone.utc))
    store.start_run(run_id="r2", slot_name="pre_market", run_date="2026-09-02", started_at=datetime(2026, 9, 2, tzinfo=timezone.utc))
    store.finish_run(run_id="r2", status=RunStatus.COMPLETED, finished_at=datetime(2026, 9, 2, 1, tzinfo=timezone.utc))

    last_success = store.last_successful_run_for_slot("pre_market")

    assert last_success.run_id == "r2"


def test_last_successful_run_for_slot_ignores_failed_runs():
    """A slot that has only ever failed must report None, not a FAILED
    run mistaken for a success."""
    store = SchedulerRunStore(":memory:")
    store.start_run(run_id="r1", slot_name="pre_market", run_date="2026-09-01", started_at=datetime(2026, 9, 1, tzinfo=timezone.utc))
    store.finish_run(run_id="r1", status=RunStatus.FAILED, error="boom")

    assert store.last_successful_run_for_slot("pre_market") is None
    store.close()


def test_last_failed_run_for_slot_carries_the_error_detail():
    store = SchedulerRunStore(":memory:")
    store.start_run(run_id="r1", slot_name="pre_market", run_date="2026-09-01", started_at=datetime(2026, 9, 1, tzinfo=timezone.utc))
    store.finish_run(run_id="r1", status=RunStatus.FAILED, error="simulated Yahoo outage")

    last_failure = store.last_failed_run_for_slot("pre_market")

    assert last_failure.error == "simulated Yahoo outage"
    store.close()


def test_most_recent_finished_run_for_slot_is_none_when_nothing_has_run(store):
    assert store.most_recent_finished_run_for_slot("pre_market") is None


def test_most_recent_finished_run_for_slot_prefers_the_newest_regardless_of_status():
    """Distinct from `last_failed_run_for_slot`, which skips straight to
    the newest FAILED row even if a newer RECLAIMED row exists -- this
    answers "what happened most recently for this slot, of any finished
    status," used by core.health to tell an active failure streak apart
    from stale history."""
    store = SchedulerRunStore(":memory:")
    store.start_run(run_id="r1", slot_name="pre_market", run_date="2026-09-01", started_at=datetime(2026, 9, 1, tzinfo=timezone.utc))
    store.finish_run(run_id="r1", status=RunStatus.FAILED, error="older failure", finished_at=datetime(2026, 9, 1, 1, tzinfo=timezone.utc))
    store.start_run(run_id="r2", slot_name="pre_market", run_date="2026-09-02", started_at=datetime(2026, 9, 2, tzinfo=timezone.utc))
    store.finish_run(run_id="r2", status=RunStatus.RECLAIMED, detail="newer, reclaimed", finished_at=datetime(2026, 9, 2, 1, tzinfo=timezone.utc))

    most_recent = store.most_recent_finished_run_for_slot("pre_market")

    assert most_recent.run_id == "r2"
    assert most_recent.status == RunStatus.RECLAIMED
    store.close()


def test_most_recent_finished_run_for_slot_excludes_a_currently_running_row():
    store = SchedulerRunStore(":memory:")
    store.start_run(run_id="r1", slot_name="pre_market", run_date="2026-09-01", started_at=datetime(2026, 9, 1, tzinfo=timezone.utc))
    store.finish_run(run_id="r1", status=RunStatus.FAILED, error="boom", finished_at=datetime(2026, 9, 1, 1, tzinfo=timezone.utc))
    store.start_run(run_id="r2", slot_name="pre_market", run_date="2026-09-02", started_at=datetime(2026, 9, 2, tzinfo=timezone.utc))  # still RUNNING, no finish_run

    most_recent = store.most_recent_finished_run_for_slot("pre_market")

    assert most_recent.run_id == "r1"
    store.close()


def test_distinct_slot_names_lists_every_slot_that_has_ever_run(store):
    store.start_run(run_id="r1", slot_name="pre_market", run_date="2026-09-01", started_at=datetime.now(timezone.utc))
    store.start_run(run_id="r2", slot_name="post_market", run_date="2026-09-01", started_at=datetime.now(timezone.utc))
    store.start_run(run_id="r3", slot_name="pre_market", run_date="2026-09-02", started_at=datetime.now(timezone.utc))  # same slot again

    assert store.distinct_slot_names() == ["post_market", "pre_market"]  # alphabetical, deduplicated


def test_distinct_slot_names_is_empty_when_nothing_has_run(store):
    assert store.distinct_slot_names() == []


# --- autonomous hardening cycle 3: sustained-failure detection --------------


def test_consecutive_failures_for_slot_is_zero_when_nothing_has_run(store):
    assert store.consecutive_failures_for_slot("pre_market") == 0


def test_consecutive_failures_for_slot_is_zero_after_a_success(store):
    store.start_run(run_id="r1", slot_name="pre_market", run_date="2026-09-01", started_at=datetime.now(timezone.utc))
    store.finish_run(run_id="r1", status=RunStatus.COMPLETED)
    assert store.consecutive_failures_for_slot("pre_market") == 0


def test_consecutive_failures_for_slot_counts_a_pure_failure_streak(store):
    for i in range(3):
        store.start_run(run_id=f"r{i}", slot_name="pre_market", run_date="2026-09-01", started_at=datetime.now(timezone.utc))
        store.finish_run(run_id=f"r{i}", status=RunStatus.FAILED, error="simulated provider outage")
    assert store.consecutive_failures_for_slot("pre_market") == 3


def test_consecutive_failures_for_slot_stops_counting_at_the_most_recent_success(store):
    """3 failures, then a success, then 2 more failures -- only the
    trailing 2 (since the last success) count, matching what an operator
    actually cares about: 'is this job broken RIGHT NOW.'"""
    for i in range(3):
        store.start_run(run_id=f"old-fail-{i}", slot_name="pre_market", run_date="2026-09-01", started_at=datetime.now(timezone.utc))
        store.finish_run(run_id=f"old-fail-{i}", status=RunStatus.FAILED, error="boom")
    store.start_run(run_id="success", slot_name="pre_market", run_date="2026-09-02", started_at=datetime.now(timezone.utc))
    store.finish_run(run_id="success", status=RunStatus.COMPLETED)
    for i in range(2):
        store.start_run(run_id=f"new-fail-{i}", slot_name="pre_market", run_date="2026-09-03", started_at=datetime.now(timezone.utc))
        store.finish_run(run_id=f"new-fail-{i}", status=RunStatus.FAILED, error="boom")

    assert store.consecutive_failures_for_slot("pre_market") == 2


def test_consecutive_failures_for_slot_treats_reclaimed_as_a_failure_too(store):
    """A RECLAIMED run (the process that started it crashed) is not a
    success either -- it must count toward the same sustained-failure
    streak as an ordinary FAILED run, not reset it."""
    started_at = datetime.now(timezone.utc) - timedelta(hours=2)
    store.start_run(run_id="r1", slot_name="pre_market", run_date="2026-09-01", started_at=started_at)
    store.reclaim_stale_locks(staleness_seconds=1800, now=datetime.now(timezone.utc))
    store.start_run(run_id="r2", slot_name="pre_market", run_date="2026-09-01", started_at=datetime.now(timezone.utc))
    store.finish_run(run_id="r2", status=RunStatus.FAILED, error="boom")

    assert store.consecutive_failures_for_slot("pre_market") == 2


def test_consecutive_failures_for_slot_ignores_a_currently_running_run(store):
    """The active (unfinished) run must not itself be counted as a
    failure -- only terminal outcomes count."""
    for i in range(3):
        store.start_run(run_id=f"r{i}", slot_name="pre_market", run_date="2026-09-01", started_at=datetime.now(timezone.utc))
        store.finish_run(run_id=f"r{i}", status=RunStatus.FAILED, error="boom")
    store.start_run(run_id="in-progress", slot_name="pre_market", run_date="2026-09-02", started_at=datetime.now(timezone.utc))

    assert store.consecutive_failures_for_slot("pre_market") == 3


def test_consecutive_failures_for_slot_is_scoped_to_one_slot(store):
    for i in range(3):
        store.start_run(run_id=f"r{i}", slot_name="pre_market", run_date="2026-09-01", started_at=datetime.now(timezone.utc))
        store.finish_run(run_id=f"r{i}", status=RunStatus.FAILED, error="boom")
    store.start_run(run_id="other-slot-ok", slot_name="post_market", run_date="2026-09-01", started_at=datetime.now(timezone.utc))
    store.finish_run(run_id="other-slot-ok", status=RunStatus.COMPLETED)

    assert store.consecutive_failures_for_slot("post_market") == 0


def test_schema_version_is_set_on_a_fresh_database(tmp_path):
    store = SchedulerRunStore(tmp_path / "runs.db")
    assert store.schema_version() == SchedulerRunStore.CURRENT_SCHEMA_VERSION
    store.close()


# --- autonomous hardening cycle: malformed data_json on read ----------------


def test_a_malformed_run_row_raises_a_clear_error_not_a_raw_pydantic_traceback(store):
    from core.sqlite_util import MalformedRowError

    store._conn.execute(
        "INSERT INTO scheduler_runs (run_id, slot_name, run_date, started_at, status, data_json) VALUES (?,?,?,?,?,?)",
        ("r1", "intraday", "2026-01-01", datetime.now(timezone.utc).isoformat(), "RUNNING", '{"run_id": "r1"}'),
    )

    with pytest.raises(MalformedRowError) as exc_info:
        store.get_run("r1")

    assert "RunRecord" in str(exc_info.value)
    assert "r1" in str(exc_info.value)
