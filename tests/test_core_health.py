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


def test_database_check_reports_healthy_for_a_real_clean_store(tmp_path):
    from paper.store import PaperStore

    db_path = tmp_path / "paper.db"
    PaperStore(db_path).close()  # creates a real, valid, empty store

    health = collect_system_health(db_paths={"paper": db_path}, probe_dir=tmp_path, check_ollama=False)

    assert health.get("database").status == ComponentStatus.HEALTHY


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


def test_risk_config_check_is_healthy_by_default(tmp_path):
    health = collect_system_health(db_paths={}, probe_dir=tmp_path, check_ollama=False)
    assert health.get("risk").status == ComponentStatus.HEALTHY


def test_dhan_check_is_disabled_without_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv("DHAN_CLIENT_ID", raising=False)
    monkeypatch.delenv("DHAN_ACCESS_TOKEN", raising=False)

    health = collect_system_health(db_paths={}, probe_dir=tmp_path, check_ollama=False)

    assert health.get("dhan").status == ComponentStatus.DISABLED


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
