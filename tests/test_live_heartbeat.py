"""Operational-reliability mission: regression tests for live/heartbeat.py,
the module built after root-causing the 2026-09-16 simultaneous-fleet-stop
incident (a real OS reboot, confirmed via Windows Event Log Get-WinEvent --
Kernel-Power event 109, "Action: Power Action Reboot, Reason: Kernel API" --
not a code defect, but the fleet gave zero clue of that on its own)."""

from datetime import datetime, timedelta, timezone

import pytest

from live.heartbeat import (
    classify_previous_session,
    write_graceful_shutdown_marker,
    write_heartbeat,
)


@pytest.fixture
def paths(tmp_path):
    return tmp_path / "heartbeat.json", tmp_path / "graceful_shutdown.json"


def test_no_previous_session_when_heartbeat_file_never_existed(paths):
    heartbeat_path, shutdown_path = paths
    report = classify_previous_session(heartbeat_path, shutdown_path)
    assert report.classification == "NO_PREVIOUS_SESSION"
    assert report.last_heartbeat_at is None


def test_graceful_shutdown_detected_when_marker_is_at_or_after_the_last_heartbeat(paths):
    heartbeat_path, shutdown_path = paths
    t0 = datetime(2026, 9, 16, 9, 0, 0, tzinfo=timezone.utc)
    write_heartbeat(heartbeat_path, now=t0)
    write_graceful_shutdown_marker(shutdown_path, reason="max_bars reached", now=t0 + timedelta(seconds=1))

    report = classify_previous_session(heartbeat_path, shutdown_path)
    assert report.classification == "GRACEFUL_SHUTDOWN"
    assert report.graceful_shutdown_at is not None


def test_abnormal_termination_when_no_shutdown_marker_exists(paths):
    # Exactly the 2026-09-16 incident's own signature: a real heartbeat,
    # no graceful marker at all (a reboot gives Python no chance to write one).
    heartbeat_path, shutdown_path = paths
    write_heartbeat(heartbeat_path, now=datetime(2026, 9, 16, 9, 5, 0, tzinfo=timezone.utc))

    report = classify_previous_session(heartbeat_path, shutdown_path)
    assert report.classification == "ABNORMAL_TERMINATION"
    assert "crash, kill, power loss, or OS reboot" in report.detail


def test_abnormal_termination_when_shutdown_marker_predates_the_last_heartbeat(paths):
    # A stale marker from an EARLIER graceful stop, followed by a fresh
    # session that then itself died abnormally, must not be mistaken for
    # THIS session's own graceful exit -- only a marker at/after the most
    # recent heartbeat counts.
    heartbeat_path, shutdown_path = paths
    t0 = datetime(2026, 9, 16, 9, 0, 0, tzinfo=timezone.utc)
    write_graceful_shutdown_marker(shutdown_path, reason="earlier clean stop", now=t0)
    write_heartbeat(heartbeat_path, now=t0 + timedelta(minutes=30))  # a later session's heartbeat

    report = classify_previous_session(heartbeat_path, shutdown_path)
    assert report.classification == "ABNORMAL_TERMINATION"


def test_write_heartbeat_never_raises_when_the_directory_does_not_exist(tmp_path):
    # Best-effort observability -- must never interrupt the caller's own
    # bar-processing loop, even if the runtime directory was removed
    # underneath it.
    missing_dir_path = tmp_path / "does_not_exist" / "heartbeat.json"
    write_heartbeat(missing_dir_path)  # must not raise
    assert not missing_dir_path.exists()


def test_corrupted_heartbeat_file_is_treated_as_abnormal_not_silently_ignored(paths):
    heartbeat_path, shutdown_path = paths
    heartbeat_path.write_text("not valid json{{{")

    report = classify_previous_session(heartbeat_path, shutdown_path)
    assert report.classification == "ABNORMAL_TERMINATION"
    assert "could not be read/parsed" in report.detail
