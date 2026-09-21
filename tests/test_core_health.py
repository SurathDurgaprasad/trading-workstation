"""core/health.py -- the unified health model shared by main.py's
`health` command and the dashboard's `/health` route."""
from __future__ import annotations

from pathlib import Path

import pytest

from core.health import ComponentStatus, OverallStatus, collect_system_health


def test_collect_system_health_with_no_paths_is_healthy_or_degraded_never_crashes(tmp_path):
    """No databases exist yet (a genuinely fresh install) -- must not
    raise, and must not report FAILED for a store that simply hasn't
    been created."""
    health = collect_system_health(db_paths={}, probe_dir=tmp_path, check_ollama=False)

    assert health.overall in (OverallStatus.HEALTHY, OverallStatus.DEGRADED)
    database = health.get("database")
    assert database.status == ComponentStatus.UNKNOWN


def test_application_component_is_always_healthy(tmp_path):
    health = collect_system_health(db_paths={}, probe_dir=tmp_path, check_ollama=False)
    assert health.get("application").status == ComponentStatus.HEALTHY


def test_disk_check_fails_on_a_nonwritable_directory(tmp_path):
    """Simulates a disk-write failure by pointing the probe at a path
    that cannot be written to (a file, not a directory)."""
    not_a_directory = tmp_path / "not_a_dir.txt"
    not_a_directory.write_text("x")

    health = collect_system_health(db_paths={}, probe_dir=not_a_directory / "nested", check_ollama=False)

    assert health.get("disk").status == ComponentStatus.FAILED
    assert health.overall == OverallStatus.FAILED


def test_disk_check_reports_healthy_with_ample_free_space(tmp_path, monkeypatch):
    import shutil
    import types

    monkeypatch.setattr(shutil, "disk_usage", lambda path: types.SimpleNamespace(total=10**12, used=0, free=10 * 1024 * 1024 * 1024))

    health = collect_system_health(db_paths={}, probe_dir=tmp_path, check_ollama=False)

    assert health.get("disk").status == ComponentStatus.HEALTHY
    assert "10240MB free" in health.get("disk").detail


def test_disk_check_reports_degraded_when_free_space_is_low(tmp_path, monkeypatch):
    """Autonomous hardening cycle 6: closes a real, previously-disclosed
    gap (FINAL_FAILURE_MODE_ANALYSIS.md entry #8) -- a nearly-full disk
    previously gave zero advance warning anywhere; the first sign of
    trouble would have been a raw OSError/sqlite3.OperationalError at
    the point of write, with no lead time to act."""
    import shutil
    import types

    monkeypatch.setattr(shutil, "disk_usage", lambda path: types.SimpleNamespace(total=10**12, used=0, free=200 * 1024 * 1024))

    health = collect_system_health(db_paths={}, probe_dir=tmp_path, check_ollama=False)

    disk = health.get("disk")
    assert disk.status == ComponentStatus.DEGRADED
    assert "200MB free" in disk.detail
    assert health.overall == OverallStatus.DEGRADED


def test_disk_check_reports_failed_when_free_space_is_critically_low(tmp_path, monkeypatch):
    """disk is a CRITICAL component -- a critically low free-space
    reading must escalate all the way to overall FAILED (blocking the
    startup gate), the same fail-closed posture a genuine write failure
    already gets."""
    import shutil
    import types

    monkeypatch.setattr(shutil, "disk_usage", lambda path: types.SimpleNamespace(total=10**12, used=0, free=10 * 1024 * 1024))

    health = collect_system_health(db_paths={}, probe_dir=tmp_path, check_ollama=False)

    assert health.get("disk").status == ComponentStatus.FAILED
    assert health.overall == OverallStatus.FAILED


def test_disk_check_survives_a_disk_usage_lookup_failure(tmp_path, monkeypatch):
    """A disk_usage-specific failure (e.g. an unusual filesystem) must
    not be conflated with an actual write failure -- the write probe
    already proved the path works, so this degrades gracefully to
    HEALTHY-with-a-caveat rather than a false FAILED."""
    import shutil

    def _raise(path):
        raise OSError("disk_usage not supported on this filesystem")

    monkeypatch.setattr(shutil, "disk_usage", _raise)

    health = collect_system_health(db_paths={}, probe_dir=tmp_path, check_ollama=False)

    disk = health.get("disk")
    assert disk.status == ComponentStatus.HEALTHY
    assert "Free-space check unavailable" in disk.detail


def test_database_check_reports_healthy_for_a_real_clean_store(tmp_path):
    from paper.store import PaperStore

    db_path = tmp_path / "paper.db"
    PaperStore(db_path).close()  # creates a real, valid, empty store

    health = collect_system_health(db_paths={"paper": db_path}, probe_dir=tmp_path, check_ollama=False)

    assert health.get("database").status == ComponentStatus.HEALTHY


def test_database_check_reports_actual_checked_count_not_configured_count(tmp_path):
    """Real bug found via a clean-install smoke test: the HEALTHY detail
    message previously reported len(db_paths) (every configured path,
    whether or not its file actually existed) rather than how many were
    genuinely found and checked -- a fresh install with only 3 of 11
    stores ever created would misleadingly claim "11 store(s) checked"."""
    from paper.store import PaperStore

    paper_path = tmp_path / "paper.db"
    PaperStore(paper_path).close()

    health = collect_system_health(
        db_paths={"paper": paper_path, "scheduler": tmp_path / "does-not-exist.db"},
        probe_dir=tmp_path, check_ollama=False,
    )

    assert health.get("database").detail == "1 store(s) checked (of 2 configured), all ok."


def test_database_check_reports_failed_for_a_corrupted_file(tmp_path):
    db_path = tmp_path / "paper.db"
    db_path.write_bytes(b"this is not a valid sqlite database file, deliberately corrupted for this test")

    health = collect_system_health(db_paths={"paper": db_path}, probe_dir=tmp_path, check_ollama=False)

    database = health.get("database")
    assert database.status == ComponentStatus.FAILED
    assert health.overall == OverallStatus.FAILED


def test_kill_switch_active_maps_to_overall_safe_stop(tmp_path):
    from live.state_store import LiveStateStore

    db_path = tmp_path / "state.db"
    store = LiveStateStore(db_path)
    store.activate_kill_switch(reason="test halt")
    store.close()

    health = collect_system_health(db_paths={"live_state": db_path}, probe_dir=tmp_path, check_ollama=False)

    assert health.get("kill_switch").status == ComponentStatus.DEGRADED
    assert "ACTIVE" in health.get("kill_switch").detail
    assert health.overall == OverallStatus.SAFE_STOP


def test_kill_switch_inactive_is_healthy(tmp_path):
    from live.state_store import LiveStateStore

    db_path = tmp_path / "state.db"
    LiveStateStore(db_path).close()

    health = collect_system_health(db_paths={"live_state": db_path}, probe_dir=tmp_path, check_ollama=False)

    assert health.get("kill_switch").status == ComponentStatus.HEALTHY
    assert health.overall != OverallStatus.SAFE_STOP


def test_scheduler_check_reports_unknown_when_no_db_exists(tmp_path):
    health = collect_system_health(db_paths={}, probe_dir=tmp_path, check_ollama=False)
    assert health.get("scheduler").status == ComponentStatus.UNKNOWN


def test_scheduler_check_reports_degraded_for_an_active_lock(tmp_path):
    from datetime import datetime, timezone

    from scheduler.store import SchedulerRunStore

    db_path = tmp_path / "runs.db"
    store = SchedulerRunStore(db_path)
    store.start_run(run_id="r1", slot_name="intraday", run_date="2026-01-01", started_at=datetime.now(timezone.utc))
    store.close()

    health = collect_system_health(db_paths={"scheduler": db_path}, probe_dir=tmp_path, check_ollama=False)

    assert health.get("scheduler").status == ComponentStatus.DEGRADED


def test_scheduler_check_reports_healthy_for_a_single_failure(tmp_path):
    """A single bad tick is normal, expected operation (schedule loop
    already retries the next tick on its own) -- must not be flagged."""
    from datetime import datetime, timezone

    from scheduler.models import RunStatus
    from scheduler.store import SchedulerRunStore

    db_path = tmp_path / "runs.db"
    store = SchedulerRunStore(db_path)
    store.start_run(run_id="r1", slot_name="intraday", run_date="2026-01-01", started_at=datetime.now(timezone.utc))
    store.finish_run(run_id="r1", status=RunStatus.FAILED, error="one transient Yahoo timeout")
    store.close()

    health = collect_system_health(db_paths={"scheduler": db_path}, probe_dir=tmp_path, check_ollama=False)

    assert health.get("scheduler").status == ComponentStatus.HEALTHY


def test_scheduler_check_reports_degraded_for_a_sustained_failure_streak(tmp_path):
    """Autonomous hardening cycle 3: a real gap this cycle closed -- a
    sustained provider outage (every tick correctly finishes FAILED and
    releases its lock, so the old active-lock-only check saw nothing
    wrong) previously left the scheduler component HEALTHY throughout.
    Three consecutive failures with no success since must now surface as
    DEGRADED, naming the slot and the last failure's reason, and must
    roll up to overall DEGRADED (scheduler is an OPTIONAL component --
    this must never escalate to FAILED or block startup)."""
    from datetime import datetime, timezone

    from scheduler.models import RunStatus
    from scheduler.store import SchedulerRunStore

    db_path = tmp_path / "runs.db"
    store = SchedulerRunStore(db_path)
    for i in range(3):
        store.start_run(run_id=f"r{i}", slot_name="intraday", run_date="2026-01-01", started_at=datetime.now(timezone.utc))
        store.finish_run(run_id=f"r{i}", status=RunStatus.FAILED, error="simulated sustained Yahoo outage")
    store.close()

    health = collect_system_health(db_paths={"scheduler": db_path}, probe_dir=tmp_path, check_ollama=False)

    scheduler = health.get("scheduler")
    assert scheduler.status == ComponentStatus.DEGRADED
    assert "intraday" in scheduler.detail
    assert "3 consecutive" in scheduler.detail
    assert "simulated sustained Yahoo outage" in scheduler.detail
    assert health.overall == OverallStatus.DEGRADED


def test_scheduler_check_active_lock_takes_priority_over_failure_streak(tmp_path):
    """If a run is currently in progress, that is reported first -- the
    failure-streak check only looks at FINISHED runs, so a currently-
    running (not yet failed) attempt must not itself be miscounted."""
    from datetime import datetime, timezone

    from scheduler.models import RunStatus
    from scheduler.store import SchedulerRunStore

    db_path = tmp_path / "runs.db"
    store = SchedulerRunStore(db_path)
    for i in range(3):
        store.start_run(run_id=f"r{i}", slot_name="intraday", run_date="2026-01-01", started_at=datetime.now(timezone.utc))
        store.finish_run(run_id=f"r{i}", status=RunStatus.FAILED, error="boom")
    store.start_run(run_id="in-progress", slot_name="intraday", run_date="2026-01-02", started_at=datetime.now(timezone.utc))
    store.close()

    health = collect_system_health(db_paths={"scheduler": db_path}, probe_dir=tmp_path, check_ollama=False)

    scheduler = health.get("scheduler")
    assert scheduler.status == ComponentStatus.DEGRADED
    assert "in progress or possibly orphaned" in scheduler.detail


def test_scheduler_check_labels_a_stale_failure_streak_as_not_necessarily_active(tmp_path):
    """2026-09-21 real finding: an 11-day-old `market_open` failure streak
    (missing Dhan credentials in the invoking shell, 2026-09-10) was still
    reported with the exact same wording/urgency as an active, right-now
    failure on 2026-09-21, even though no `schedule loop`/`tick` process
    had attempted anything since. The streak/DEGRADED status itself must
    stay -- this only proves the message now HONESTLY distinguishes stale
    history from a live incident, without hiding or weakening the streak."""
    from datetime import datetime, timedelta, timezone

    from scheduler.models import RunStatus
    from scheduler.store import SchedulerRunStore

    db_path = tmp_path / "runs.db"
    store = SchedulerRunStore(db_path)
    old = datetime(2026, 9, 10, 3, 49, tzinfo=timezone.utc)
    for i in range(9):
        started = old + timedelta(minutes=i)
        store.start_run(run_id=f"r{i}", slot_name="market_open", run_date="2026-09-10", started_at=started)
        store.finish_run(run_id=f"r{i}", status=RunStatus.FAILED, error="Missing required environment variable(s): DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN.", finished_at=started)
    store.close()

    checked_at = datetime(2026, 9, 21, 4, 0, tzinfo=timezone.utc)  # 11 days later, matching the real incident's own gap
    health = collect_system_health(db_paths={"scheduler": db_path}, probe_dir=tmp_path, check_ollama=False, now=checked_at)

    scheduler = health.get("scheduler")
    assert scheduler.status == ComponentStatus.DEGRADED  # streak is real, unchanged, never hidden
    assert "market_open" in scheduler.detail
    assert "9 consecutive" in scheduler.detail
    assert "DHAN_CLIENT_ID" in scheduler.detail
    assert "STALE HISTORY" in scheduler.detail
    assert "not currently running" in scheduler.detail


def test_scheduler_check_labels_a_recent_failure_streak_as_active(tmp_path):
    """The symmetric case: a streak that finished minutes ago must be
    labeled as an active, ongoing pattern, not stale history -- an
    operator must not be falsely reassured that a live incident is old
    news."""
    from datetime import datetime, timedelta, timezone

    from scheduler.models import RunStatus
    from scheduler.store import SchedulerRunStore

    db_path = tmp_path / "runs.db"
    store = SchedulerRunStore(db_path)
    now = datetime(2026, 9, 21, 4, 0, tzinfo=timezone.utc)
    for i in range(3):
        started = now - timedelta(minutes=10 - i)
        store.start_run(run_id=f"r{i}", slot_name="intraday", run_date="2026-09-21", started_at=started)
        store.finish_run(run_id=f"r{i}", status=RunStatus.FAILED, error="simulated ongoing outage", finished_at=started)
    store.close()

    health = collect_system_health(db_paths={"scheduler": db_path}, probe_dir=tmp_path, check_ollama=False, now=now)

    scheduler = health.get("scheduler")
    assert scheduler.status == ComponentStatus.DEGRADED
    assert "active, ongoing pattern" in scheduler.detail
    assert "STALE HISTORY" not in scheduler.detail


def test_risk_config_check_is_healthy_by_default(tmp_path):
    health = collect_system_health(db_paths={}, probe_dir=tmp_path, check_ollama=False)
    assert health.get("risk").status == ComponentStatus.HEALTHY


def test_dhan_check_is_disabled_without_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv("DHAN_CLIENT_ID", raising=False)
    monkeypatch.delenv("DHAN_ACCESS_TOKEN", raising=False)

    health = collect_system_health(db_paths={}, probe_dir=tmp_path, check_ollama=False)

    assert health.get("dhan").status == ComponentStatus.DISABLED


def test_ollama_component_is_disabled_not_degraded_when_openai_is_the_active_provider(tmp_path, monkeypatch):
    """Final repository integrity audit finding: `health`/the dashboard
    System tab previously showed "ollama: DEGRADED" even when
    AI_PROVIDER=openai was configured and Ollama was never going to be
    used -- a misleading false-alarm signal for a daemon this session
    doesn't need. Fixed: DISABLED (not DEGRADED) when Ollama is not the
    active provider."""
    import core.config as config_module
    from core.config import LLMProvider, Settings

    monkeypatch.setattr(config_module, "get_settings", lambda: Settings(llm_provider=LLMProvider.OPENAI))

    health = collect_system_health(db_paths={}, probe_dir=tmp_path, check_ollama=True)
    ollama = health.get("ollama")
    assert ollama.status == ComponentStatus.DISABLED
    assert "not the active" in ollama.detail.lower()


def test_ollama_component_is_checked_normally_when_ollama_is_the_active_provider(tmp_path):
    # The common/default case today must be completely unaffected by the
    # fix above -- Ollama unreachable still reports DEGRADED, exactly as
    # every other existing test in this file already assumes.
    health = collect_system_health(db_paths={}, probe_dir=tmp_path, check_ollama=True)
    ollama = health.get("ollama")
    assert ollama.status in (ComponentStatus.HEALTHY, ComponentStatus.DEGRADED)
    assert "not the active" not in ollama.detail.lower()


def test_ollama_check_is_skipped_when_check_ollama_is_false(tmp_path):
    health = collect_system_health(db_paths={}, probe_dir=tmp_path, check_ollama=False)
    assert health.get("ollama") is None


def test_overall_status_is_degraded_not_failed_for_a_noncritical_component():
    """Dhan being unconfigured (DISABLED, not FAILED) or ollama being
    unreachable (DEGRADED) must not escalate the whole system to
    FAILED -- only a critical component (application/database/disk/risk)
    failing does that."""
    from core.health import ComponentHealth, SystemHealth, _derive_overall_status

    components = [
        ComponentHealth("application", ComponentStatus.HEALTHY),
        ComponentHealth("database", ComponentStatus.UNKNOWN),
        ComponentHealth("disk", ComponentStatus.HEALTHY),
        ComponentHealth("risk", ComponentStatus.HEALTHY),
        ComponentHealth("ollama", ComponentStatus.DEGRADED, "unreachable"),
    ]
    assert _derive_overall_status(components) == OverallStatus.DEGRADED


def test_overall_status_is_failed_when_database_integrity_check_fails():
    from core.health import ComponentHealth, _derive_overall_status

    components = [
        ComponentHealth("application", ComponentStatus.HEALTHY),
        ComponentHealth("database", ComponentStatus.FAILED, "corruption found"),
        ComponentHealth("disk", ComponentStatus.HEALTHY),
        ComponentHealth("risk", ComponentStatus.HEALTHY),
    ]
    assert _derive_overall_status(components) == OverallStatus.FAILED


def test_get_returns_none_for_an_unknown_component_name(tmp_path):
    health = collect_system_health(db_paths={}, probe_dir=tmp_path, check_ollama=False)
    assert health.get("does-not-exist") is None


def test_disk_check_survives_many_real_concurrent_callers_against_the_same_probe_dir(tmp_path):
    """15-symbol live-fleet validation mission, real defect found live:
    a single fixed probe filename let one process's unlink() delete
    another concurrently-running process's own probe file (a real
    TOCTOU race), causing a genuine, observed SAFE_STOP
    ("[WinError 2] The system cannot find the file specified") for one
    worker during a real 10-symbol fleet-supervise run. Real threads
    (not simulated), same probe_dir, hammering _check_disk() far harder
    than 15 fleet-supervise workers starting a second apart ever would
    -- every single call must report HEALTHY, never a false FAILED from
    another caller's own probe file."""
    import threading

    from core.health import ComponentStatus, _check_disk

    results: list[ComponentStatus] = []
    lock = threading.Lock()

    def _call():
        health = _check_disk(tmp_path)
        with lock:
            results.append(health.status)

    threads = [threading.Thread(target=_call) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(results) == 20
    assert all(status == ComponentStatus.HEALTHY for status in results), results
    # No probe files left behind by any caller.
    assert list(tmp_path.glob("tradingagents_health_write_probe_*.tmp")) == []
