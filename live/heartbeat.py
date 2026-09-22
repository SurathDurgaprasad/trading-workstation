"""Operational-reliability mission: real forensic gap found and root-caused
2026-09-16 -- the entire 15-symbol fleet stopped simultaneously at 14:35
IST with zero error/exception in any of the 15 session.log files. The ONLY
way to determine what happened was manual Windows Event Log archaeology
(Get-WinEvent), which confirmed a genuine OS-initiated reboot at 14:37:04
IST (Kernel-Power event 109, "Action: Power Action Reboot, Reason: Kernel
API"). That investigation should not need to happen by hand next time.

This module gives every `paper-live` process a lightweight, file-based
liveness trail INSIDE its own runtime directory (never a new store, never
a new dependency):

  heartbeat.json        -- overwritten periodically while the process is
                            alive (pid, written_at). A SIGKILL, power loss,
                            or OS reboot leaves this file exactly as it was
                            at the last write -- it cannot lie about
                            "still alive" after the fact, unlike a
                            log line the process itself chooses to print.
  graceful_shutdown.json -- written ONLY from a normal exit path (loop
                            completion, or a caught KeyboardInterrupt/
                            SystemExit via try/finally) -- never written
                            by a signal/reboot that skips Python cleanup
                            entirely, which is exactly the property that
                            makes its ABSENCE meaningful evidence.

classify_previous_session() compares the two, purely by timestamp -- no
PID-liveness check (unreliable across a reboot: PIDs get reused) -- so a
future startup can print, in one line, "the prior session for this symbol
ended abnormally at approximately <heartbeat time>" without anyone needing
to open Event Viewer.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def _now_iso(now: datetime | None) -> str:
    return (now or datetime.now(timezone.utc)).isoformat()


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def write_heartbeat(path: Path, *, now: datetime | None = None) -> None:
    """Overwrite the heartbeat file with the current pid/timestamp.
    Best-effort observability only -- a write failure here must never
    interrupt the caller's own bar-processing loop."""
    try:
        path.write_text(json.dumps({"pid": os.getpid(), "written_at": _now_iso(now)}))
    except OSError:
        pass


def write_graceful_shutdown_marker(path: Path, *, reason: str, now: datetime | None = None) -> None:
    """Written only from a normal/caught exit path -- see module docstring
    for why its absence (relative to the last heartbeat) is the actual
    signal an abnormal termination happened."""
    try:
        path.write_text(json.dumps({"pid": os.getpid(), "shutdown_at": _now_iso(now), "reason": reason}))
    except OSError:
        pass


def read_heartbeat_age_seconds(path: Path, *, now: datetime | None = None) -> float | None:
    """Red-team finding (2026-09-22): nothing in this codebase reads
    heartbeat.json WHILE a session is running -- classify_previous_session
    above only ever looks at it at the NEXT process's own startup, and
    live/fleet_supervisor.py's own health check never opens it at all,
    relying entirely on log-line content with no time component. A worker
    that hangs inside a blocking call (e.g. a feed read with no timeout)
    stops calling write_heartbeat() -- exactly like it stops printing new
    log lines -- so this file going silently stale IS real, load-bearing
    evidence of a stuck loop, not merely a liveness nicety. Returns None
    (not 0, not raising) if the file is missing or unreadable -- an
    absent/corrupt heartbeat is a DIFFERENT condition from a genuinely
    stale one, and callers should decide separately how to treat "no
    evidence at all" versus "evidence this is old." Best-effort, matching
    write_heartbeat's own posture: a read failure here must never raise
    into a caller's own health-check loop."""
    try:
        data = json.loads(path.read_text())
        last_heartbeat_at = _parse_iso(data["written_at"])
    except (OSError, ValueError, KeyError):
        return None
    return ((now or datetime.now(timezone.utc)) - last_heartbeat_at).total_seconds()


@dataclass(frozen=True)
class PreviousSessionReport:
    classification: str
    """One of: NO_PREVIOUS_SESSION, GRACEFUL_SHUTDOWN, ABNORMAL_TERMINATION."""
    detail: str
    last_heartbeat_at: datetime | None
    graceful_shutdown_at: datetime | None


def classify_previous_session(heartbeat_path: Path, shutdown_marker_path: Path) -> PreviousSessionReport:
    """Read-only: call BEFORE this process's own first write_heartbeat()
    call, or it will just be classifying itself."""
    if not heartbeat_path.exists():
        return PreviousSessionReport(
            classification="NO_PREVIOUS_SESSION", detail="No heartbeat file found -- first session for this symbol/runtime-dir.",
            last_heartbeat_at=None, graceful_shutdown_at=None,
        )

    try:
        heartbeat_data = json.loads(heartbeat_path.read_text())
        last_heartbeat_at = _parse_iso(heartbeat_data["written_at"])
    except (OSError, ValueError, KeyError) as exc:
        return PreviousSessionReport(
            classification="ABNORMAL_TERMINATION",
            detail=f"A previous heartbeat file exists but could not be read/parsed ({type(exc).__name__}: {exc}) -- treated as abnormal.",
            last_heartbeat_at=None, graceful_shutdown_at=None,
        )

    graceful_shutdown_at = None
    if shutdown_marker_path.exists():
        try:
            shutdown_data = json.loads(shutdown_marker_path.read_text())
            graceful_shutdown_at = _parse_iso(shutdown_data["shutdown_at"])
        except (OSError, ValueError, KeyError):
            graceful_shutdown_at = None

    if graceful_shutdown_at is not None and graceful_shutdown_at >= last_heartbeat_at:
        return PreviousSessionReport(
            classification="GRACEFUL_SHUTDOWN",
            detail=f"Previous session shut down normally at {graceful_shutdown_at.isoformat()}.",
            last_heartbeat_at=last_heartbeat_at, graceful_shutdown_at=graceful_shutdown_at,
        )

    return PreviousSessionReport(
        classification="ABNORMAL_TERMINATION",
        detail=(
            f"Previous session's last heartbeat was {last_heartbeat_at.isoformat()}, with no matching graceful-shutdown "
            "marker at or after it -- consistent with a crash, kill, power loss, or OS reboot, not an intentional stop."
        ),
        last_heartbeat_at=last_heartbeat_at, graceful_shutdown_at=graceful_shutdown_at,
    )
