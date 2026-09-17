"""Real-time strategy validation mission, multi-symbol hardening pass --
tests for live/fleet_supervisor.py: command construction, worker health
classification, and the bounded-restart decision.
"""
import subprocess
import sys
import time
from pathlib import Path

import pytest

from live.fleet_supervisor import (
    WorkerHandle,
    WorkerHealth,
    WorkerStatus,
    build_worker_command,
    build_worker_env,
    check_worker_health,
    format_fleet_status_line,
    launch_worker,
    poll_fleet_once,
    should_restart,
    shutdown_fleet,
)


# --- build_worker_command -----------------------------------------------------


def test_build_worker_command_includes_every_required_mission_flag():
    command = build_worker_command(
        python_executable="python", main_py_path="main.py", symbol="RELIANCE.NS",
        runtime_dir="runtime", interval="1m", cost_model="india_nse_intraday_2026",
        evaluate_every_n_bars=20,
    )
    assert command[:3] == ["python", "main.py", "paper-live"]
    assert "--source" in command and command[command.index("--source") + 1] == "dhan"
    assert "--symbol" in command and command[command.index("--symbol") + 1] == "RELIANCE.NS"
    assert "--runtime-dir" in command and command[command.index("--runtime-dir") + 1] == "runtime"
    assert "--record-predictions" in command
    assert "--evaluate-every-n-bars" in command and command[command.index("--evaluate-every-n-bars") + 1] == "20"
    assert "--cost-model" in command and command[command.index("--cost-model") + 1] == "india_nse_intraday_2026"
    # never the explicit --db/--state-db/--predictions-db -- --runtime-dir derives them,
    # and main.py's own guard rejects combining the two (see run_paper_live_command).
    assert "--db" not in command
    assert "--state-db" not in command
    assert "--predictions-db" not in command


def test_build_worker_command_source_defaults_to_dhan_the_only_real_production_value():
    command = build_worker_command(
        python_executable="python", main_py_path="main.py", symbol="RELIANCE.NS", runtime_dir="runtime",
    )
    assert command[command.index("--source") + 1] == "dhan"


def test_build_worker_command_supports_extra_args():
    command = build_worker_command(
        python_executable="python", main_py_path="main.py", symbol="TCS.NS",
        runtime_dir="runtime", extra_args=["--max-bars", "5"],
    )
    assert command[-2:] == ["--max-bars", "5"]


# --- build_worker_env ---------------------------------------------------------


def test_build_worker_env_preserves_the_base_environment():
    """The real bug this guards against: a naive `dict(overrides)` (not
    layered on the base environment) hands a Windows subprocess an
    almost-empty environment (no PATH, no SystemRoot) and the child
    interpreter fails to start correctly -- caught by this module's own
    real-subprocess integration test below, which exited 1 before this
    fix and 0 after."""
    base = {"PATH": r"C:\Windows\System32", "SYSTEMROOT": r"C:\Windows"}
    merged = build_worker_env(base_env=base, env_overrides=None)
    assert merged["PATH"] == r"C:\Windows\System32"
    assert merged["SYSTEMROOT"] == r"C:\Windows"


def test_build_worker_env_layers_overrides_on_top_without_dropping_the_rest():
    base = {"PATH": r"C:\Windows\System32", "SOME_OTHER_VAR": "keep-me"}
    merged = build_worker_env(base_env=base, env_overrides={"DHAN_CLIENT_ID": "abc123"})
    assert merged["PATH"] == r"C:\Windows\System32"
    assert merged["SOME_OTHER_VAR"] == "keep-me"
    assert merged["DHAN_CLIENT_ID"] == "abc123"


def test_build_worker_env_always_forces_unbuffered_output():
    merged = build_worker_env(base_env={"PYTHONUNBUFFERED": "0"}, env_overrides=None)
    assert merged["PYTHONUNBUFFERED"] == "1"


# --- check_worker_health -- process-liveness branch ---------------------------


class _FakeProcess:
    def __init__(self, poll_sequence):
        self._poll_sequence = list(poll_sequence)
        self.pid = 4242

    def poll(self):
        if not self._poll_sequence:
            return None
        return self._poll_sequence.pop(0)


def _handle(poll_sequence, tmp_path, restarts: int = 0) -> WorkerHandle:
    return WorkerHandle(
        symbol="RELIANCE.NS", process=_FakeProcess(poll_sequence), log_path=tmp_path / "session.log", restarts=restarts,
    )


def test_check_worker_health_exited_clean_when_process_exit_code_is_zero(tmp_path):
    status = check_worker_health(_handle([0], tmp_path), log_lines=[])
    assert status.health == WorkerHealth.EXITED_CLEAN
    assert status.exit_code == 0


def test_check_worker_health_exited_error_when_process_exit_code_is_nonzero(tmp_path):
    status = check_worker_health(_handle([1], tmp_path), log_lines=[])
    assert status.health == WorkerHealth.EXITED_ERROR
    assert status.exit_code == 1


# --- check_worker_health -- alive, log-scanning branch -------------------------


def test_check_worker_health_running_when_alive_with_no_gap_signal(tmp_path):
    log_lines = [
        "[RELIANCE.NS] bar#   1 2026-09-16T09:15:00  close=1234.50  NO_SIGNAL\n",
        "[RELIANCE.NS] bar#   2 2026-09-16T09:16:00  close=1235.00  NO_SIGNAL\n",
    ]
    status = check_worker_health(_handle([], tmp_path), log_lines=log_lines)
    assert status.health == WorkerHealth.RUNNING
    assert status.pid == 4242


def test_check_worker_health_gap_detected_when_gap_line_is_most_recent(tmp_path):
    log_lines = [
        "[RELIANCE.NS] bar#   1 2026-09-16T09:15:00  close=1234.50  NO_SIGNAL\n",
        "\n[RELIANCE.NS] [GAP DETECTED] connected, no new bar for 900s (expected within ~180s) -- feed may be delayed, not necessarily disconnected.\n",
    ]
    status = check_worker_health(_handle([], tmp_path), log_lines=log_lines)
    assert status.health == WorkerHealth.GAP_DETECTED
    assert "gap" in status.detail


def test_check_worker_health_running_again_once_a_new_bar_follows_the_gap(tmp_path):
    log_lines = [
        "\n[RELIANCE.NS] [GAP DETECTED] connected, no new bar for 900s (expected within ~180s) -- feed may be delayed, not necessarily disconnected.\n",
        "[RELIANCE.NS] bar#   2 2026-09-16T09:31:00  close=1235.00  NO_SIGNAL\n",
    ]
    status = check_worker_health(_handle([], tmp_path), log_lines=log_lines)
    assert status.health == WorkerHealth.RUNNING


def test_check_worker_health_repeated_gap_ongoing_line_still_counts_as_gap(tmp_path):
    log_lines = [
        "[RELIANCE.NS] bar#   1 2026-09-16T09:15:00  close=1234.50  NO_SIGNAL\n",
        "\n[RELIANCE.NS] [GAP DETECTED] connected, no new bar for 900s (expected within ~180s) -- feed may be delayed, not necessarily disconnected.\n",
        "\n[RELIANCE.NS] [GAP ONGOING] connected, no new bar for 960s (expected within ~180s) -- feed may be delayed, not necessarily disconnected.\n",
    ]
    status = check_worker_health(_handle([], tmp_path), log_lines=log_lines)
    assert status.health == WorkerHealth.GAP_DETECTED


def test_check_worker_health_running_again_once_a_new_bar_follows_a_disconnect(tmp_path):
    """Mirrors the gap-recovery test above but for FEED DISCONNECTED --
    a worker that reconnected and produced a fresh bar must not be
    stuck reporting GAP_DETECTED forever because a disconnect line is
    still somewhere in the tail window."""
    log_lines = [
        "\n[RELIANCE.NS] FEED DISCONNECTED: WebSocket closed unexpectedly.\n",
        "[RELIANCE.NS] bar#   2 2026-09-16T09:31:00  close=1235.00  NO_SIGNAL\n",
    ]
    status = check_worker_health(_handle([], tmp_path), log_lines=log_lines)
    assert status.health == WorkerHealth.RUNNING


def test_check_worker_health_feed_disconnected_counts_as_gap_detected(tmp_path):
    log_lines = [
        "[RELIANCE.NS] bar#   1 2026-09-16T09:15:00  close=1234.50  NO_SIGNAL\n",
        "\n[RELIANCE.NS] FEED DISCONNECTED: WebSocket closed unexpectedly.\n",
    ]
    status = check_worker_health(_handle([], tmp_path), log_lines=log_lines)
    assert status.health == WorkerHealth.GAP_DETECTED
    assert "disconnect" in status.detail


def test_check_worker_health_pending_human_approval_line_counts_as_fresh_activity(tmp_path):
    """The one branch (PENDING_HUMAN_APPROVAL) whose per-event line never
    contains "bar#" -- must still count as recent activity, not a false
    gap, via the "SIGNAL DETECTED" marker from _print_signal_block."""
    log_lines = [
        "\n[RELIANCE.NS] [GAP DETECTED] connected, no new bar for 900s (expected within ~180s) -- feed may be delayed, not necessarily disconnected.\n",
        "\nSIGNAL DETECTED\n",
        "  Signal ID: abc123\n",
    ]
    status = check_worker_health(_handle([], tmp_path), log_lines=log_lines)
    assert status.health == WorkerHealth.RUNNING


def test_check_worker_health_with_no_log_activity_yet_is_running_not_gap(tmp_path):
    """A freshly-launched worker that hasn't printed its first bar yet is
    RUNNING, not GAP_DETECTED -- there is no baseline to be gapped
    against (mirrors live/gap_monitor.py's own no-baseline-yet rule)."""
    status = check_worker_health(_handle([], tmp_path), log_lines=[])
    assert status.health == WorkerHealth.RUNNING


def test_check_worker_health_reads_the_real_log_file_when_no_lines_injected(tmp_path):
    log_path = tmp_path / "session.log"
    log_path.write_text("[RELIANCE.NS] bar#   1 2026-09-16T09:15:00  close=1234.50  NO_SIGNAL\n")
    handle = WorkerHandle(symbol="RELIANCE.NS", process=_FakeProcess([]), log_path=log_path)
    status = check_worker_health(handle)
    assert status.health == WorkerHealth.RUNNING


# --- should_restart -------------------------------------------------------------


def _status(health: WorkerHealth, restarts: int = 0) -> WorkerStatus:
    return WorkerStatus(symbol="RELIANCE.NS", health=health, pid=1, exit_code=None, restarts=restarts, detail="")


def test_should_restart_true_for_exited_error_under_the_cap():
    assert should_restart(_status(WorkerHealth.EXITED_ERROR, restarts=0), max_restarts=3) is True
    assert should_restart(_status(WorkerHealth.EXITED_ERROR, restarts=2), max_restarts=3) is True


def test_should_restart_false_once_the_cap_is_reached():
    assert should_restart(_status(WorkerHealth.EXITED_ERROR, restarts=3), max_restarts=3) is False


def test_should_restart_false_for_exited_clean_even_under_the_cap():
    """A worker that reached --max-bars and exited 0 did exactly what it
    was told -- restarting it would be wrong, not resilient."""
    assert should_restart(_status(WorkerHealth.EXITED_CLEAN, restarts=0), max_restarts=3) is False


def test_should_restart_false_for_running_and_gap_detected():
    """A live process is never a restart decision -- only a dead one is."""
    assert should_restart(_status(WorkerHealth.RUNNING, restarts=0), max_restarts=3) is False
    assert should_restart(_status(WorkerHealth.GAP_DETECTED, restarts=0), max_restarts=3) is False


# --- poll_fleet_once ------------------------------------------------------------


def test_poll_fleet_once_leaves_running_workers_untouched(tmp_path):
    handles = {"RELIANCE.NS": _handle([], tmp_path)}
    relaunch_calls = []
    snapshot = poll_fleet_once(handles, max_restarts=3, relaunch=lambda s, r: relaunch_calls.append((s, r)))
    assert relaunch_calls == []
    assert snapshot.restarted_symbols == []
    assert snapshot.exhausted_symbols == []
    assert snapshot.statuses[0].health == WorkerHealth.RUNNING


def test_poll_fleet_once_relaunches_a_crashed_worker_under_the_cap(tmp_path):
    handles = {"TCS.NS": _handle([1], tmp_path, restarts=0)}
    new_handle = _handle([], tmp_path, restarts=1)

    def relaunch(symbol, next_restart_count):
        assert symbol == "TCS.NS"
        assert next_restart_count == 1
        return new_handle

    snapshot = poll_fleet_once(handles, max_restarts=3, relaunch=relaunch)
    assert snapshot.restarted_symbols == ["TCS.NS"]
    assert snapshot.exhausted_symbols == []
    assert handles["TCS.NS"] is new_handle


def test_poll_fleet_once_reports_exhausted_without_relaunching_past_the_cap(tmp_path):
    handles = {"TCS.NS": _handle([1], tmp_path, restarts=3)}
    relaunch_calls = []
    snapshot = poll_fleet_once(handles, max_restarts=3, relaunch=lambda s, r: relaunch_calls.append((s, r)) or _handle([], tmp_path))
    assert relaunch_calls == []
    assert snapshot.restarted_symbols == []
    assert snapshot.exhausted_symbols == ["TCS.NS"]


def test_poll_fleet_once_does_not_relaunch_a_cleanly_exited_worker(tmp_path):
    handles = {"RELIANCE.NS": _handle([0], tmp_path)}
    relaunch_calls = []
    snapshot = poll_fleet_once(handles, max_restarts=3, relaunch=lambda s, r: relaunch_calls.append((s, r)) or _handle([], tmp_path))
    assert relaunch_calls == []
    assert snapshot.restarted_symbols == []
    assert snapshot.exhausted_symbols == []
    assert snapshot.statuses[0].health == WorkerHealth.EXITED_CLEAN


def test_poll_fleet_once_covers_every_symbol_in_the_fleet(tmp_path):
    handles = {
        "RELIANCE.NS": WorkerHandle(symbol="RELIANCE.NS", process=_FakeProcess([]), log_path=tmp_path / "r.log"),
        "TCS.NS": WorkerHandle(symbol="TCS.NS", process=_FakeProcess([0]), log_path=tmp_path / "t.log"),
    }
    snapshot = poll_fleet_once(handles, max_restarts=3, relaunch=lambda s, r: _handle([], tmp_path))
    assert {status.symbol for status in snapshot.statuses} == {"RELIANCE.NS", "TCS.NS"}


# --- poll_fleet_once -- adversarial hardening pass: per-symbol exception ------
# --- isolation ("one symbol failure cannot stop another symbol") --------------
#
# Real gap found by a dedicated audit agent: the per-symbol loop body had no
# exception boundary at all. A single symbol raising during check_worker_
# health (e.g. a transient log-file read error) or during relaunch (e.g.
# subprocess.Popen failing: missing interpreter, OS process-table
# exhaustion) propagated straight out of poll_fleet_once, out of
# run_fleet_supervise_command's while loop, into its own `finally:
# shutdown_fleet(handles)` -- terminating EVERY worker, including every
# other, perfectly healthy symbol. Fixed with a per-symbol try/except and a
# new WorkerHealth.SUPERVISION_ERROR status that surfaces the failure
# instead of letting it escape.


def test_poll_fleet_once_isolates_a_relaunch_failure_to_only_the_failing_symbol(tmp_path):
    # Built directly (not via the `_handle()` shortcut, which hardcodes
    # symbol="RELIANCE.NS" regardless of the dict key -- fine for the
    # single-symbol tests above, but this test needs two GENUINELY
    # distinct symbols to prove isolation between them).
    handles = {
        "RELIANCE.NS": WorkerHandle(symbol="RELIANCE.NS", process=_FakeProcess([]), log_path=tmp_path / "r.log"),  # healthy, must be entirely unaffected
        "TCS.NS": WorkerHandle(symbol="TCS.NS", process=_FakeProcess([1]), log_path=tmp_path / "t.log", restarts=0),  # crashed, its relaunch will fail
    }
    original_tcs_handle = handles["TCS.NS"]

    def relaunch(symbol, next_restart_count):
        raise OSError("simulated subprocess.Popen failure: no such file or directory")

    snapshot = poll_fleet_once(handles, max_restarts=3, relaunch=relaunch)

    by_symbol = {status.symbol: status for status in snapshot.statuses}
    assert by_symbol["RELIANCE.NS"].health == WorkerHealth.RUNNING  # entirely unaffected by TCS.NS's failure
    assert by_symbol["TCS.NS"].health == WorkerHealth.SUPERVISION_ERROR
    assert "simulated subprocess.Popen failure" in by_symbol["TCS.NS"].detail
    assert snapshot.restarted_symbols == []  # never counted as a successful restart
    assert handles["TCS.NS"] is original_tcs_handle  # previous handle preserved, not dropped or half-replaced
    assert handles["RELIANCE.NS"] is not None  # still present, untouched


def test_poll_fleet_once_isolates_a_health_check_failure_to_only_the_failing_symbol(tmp_path):
    class _RaisingProcess:
        pid = 9999

        def poll(self):
            raise OSError("simulated transient Windows file-handle error")

    handles = {
        "RELIANCE.NS": _handle([], tmp_path),
        "TCS.NS": WorkerHandle(symbol="TCS.NS", process=_RaisingProcess(), log_path=tmp_path / "t.log"),
    }

    snapshot = poll_fleet_once(handles, max_restarts=3, relaunch=lambda s, r: _handle([], tmp_path))

    by_symbol = {status.symbol: status for status in snapshot.statuses}
    assert by_symbol["RELIANCE.NS"].health == WorkerHealth.RUNNING  # entirely unaffected by TCS.NS's failure
    assert by_symbol["TCS.NS"].health == WorkerHealth.SUPERVISION_ERROR
    assert "simulated transient Windows file-handle error" in by_symbol["TCS.NS"].detail


# --- shutdown_fleet -- deterministic (fake processes, no real subprocess timing) --


class _FakeLongRunningProcess:
    """A fake subprocess.Popen-like object whose exit is controlled
    deterministically by which call (`terminate`/`kill`) it "responds"
    to, instead of a real process's own timing -- makes Item 6's
    graceful-shutdown/force-kill path testable without a flaky race
    against how fast a real child actually exits."""

    def __init__(self, *, already_exited: bool = False, responds_to: str = "terminate"):
        self.pid = 9999
        self._alive = not already_exited
        self._responds_to = responds_to  # "terminate" | "kill" | "never"
        self.terminate_called = False
        self.kill_called = False

    def poll(self):
        return None if self._alive else 0

    def terminate(self):
        self.terminate_called = True
        if self._responds_to == "terminate":
            self._alive = False

    def kill(self):
        self.kill_called = True
        if self._responds_to in ("kill", "never"):
            self._alive = False  # even "never" dies once kill() lands, for test determinism

    def wait(self, timeout=None):
        if self._alive:
            raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout)
        return 0


def _fake_handle(process, symbol="RELIANCE.NS", tmp_path=None) -> WorkerHandle:
    return WorkerHandle(symbol=symbol, process=process, log_path=(tmp_path or Path(".")) / "session.log")


def test_shutdown_fleet_leaves_an_already_exited_worker_untouched(tmp_path):
    process = _FakeLongRunningProcess(already_exited=True)
    shutdown_fleet({"RELIANCE.NS": _fake_handle(process, tmp_path=tmp_path)}, print_fn=lambda _: None)
    assert process.terminate_called is False
    assert process.kill_called is False


def test_shutdown_fleet_terminates_a_running_worker_that_exits_promptly(tmp_path):
    process = _FakeLongRunningProcess(responds_to="terminate")
    shutdown_fleet({"RELIANCE.NS": _fake_handle(process, tmp_path=tmp_path)}, print_fn=lambda _: None)
    assert process.terminate_called is True
    assert process.kill_called is False
    assert process.poll() == 0


def test_shutdown_fleet_force_kills_a_worker_that_ignores_terminate(tmp_path):
    """The real Item 6 safety-net path: a worker that does not exit on
    its own within the bounded timeout must be force-killed, not left
    running forever."""
    process = _FakeLongRunningProcess(responds_to="kill")
    shutdown_fleet({"RELIANCE.NS": _fake_handle(process, tmp_path=tmp_path)}, terminate_timeout_seconds=0.01, print_fn=lambda _: None)
    assert process.terminate_called is True
    assert process.kill_called is True
    assert process.poll() == 0


def test_shutdown_fleet_handles_every_worker_in_the_fleet_independently(tmp_path):
    already_done = _FakeLongRunningProcess(already_exited=True)
    needs_terminate = _FakeLongRunningProcess(responds_to="terminate")
    needs_kill = _FakeLongRunningProcess(responds_to="kill")
    handles = {
        "A": _fake_handle(already_done, symbol="A", tmp_path=tmp_path),
        "B": _fake_handle(needs_terminate, symbol="B", tmp_path=tmp_path),
        "C": _fake_handle(needs_kill, symbol="C", tmp_path=tmp_path),
    }
    shutdown_fleet(handles, terminate_timeout_seconds=0.01, print_fn=lambda _: None)
    assert already_done.terminate_called is False
    assert needs_terminate.terminate_called is True and needs_terminate.kill_called is False
    assert needs_kill.terminate_called is True and needs_kill.kill_called is True
    assert all(h.process.poll() == 0 for h in handles.values())


def test_shutdown_fleet_prints_a_status_line_for_each_action_taken():
    printed = []
    process = _FakeLongRunningProcess(responds_to="kill")
    shutdown_fleet({"RELIANCE.NS": _fake_handle(process)}, terminate_timeout_seconds=0.01, print_fn=printed.append)
    joined = "\n".join(printed)
    assert "terminating" in joined
    assert "RELIANCE.NS" in joined
    assert "killing" in joined


# --- format_fleet_status_line ----------------------------------------------------


def test_format_fleet_status_line_includes_symbol_health_pid_and_restarts():
    status = WorkerStatus(symbol="RELIANCE.NS", health=WorkerHealth.GAP_DETECTED, pid=4242, exit_code=None, restarts=1, detail="no newer bar since")
    line = format_fleet_status_line(status)
    assert "RELIANCE.NS" in line
    assert "GAP_DETECTED" in line
    assert "4242" in line
    assert "restarts=1" in line
    assert "no newer bar since" in line


# --- launch_worker -- real subprocess, --source mock (fast, no live dependency) --


def test_launch_worker_real_subprocess_runs_to_completion_and_logs_bars(tmp_path):
    repo_root = Path(__file__).resolve().parent.parent
    handle = launch_worker(
        symbol="AAPL", runtime_dir=str(tmp_path), python_executable=sys.executable,
        main_py_path=str(repo_root / "main.py"), source="mock",
        extra_args=["--period", "5d", "--max-bars", "3", "--no-human-approval"],
    )
    try:
        exit_code = handle.process.wait(timeout=60)
    except subprocess.TimeoutExpired:
        handle.process.kill()
        handle.process.wait(timeout=10)
        pytest.fail("worker subprocess did not exit within the timeout")

    assert exit_code == 0
    status = check_worker_health(handle)
    assert status.health == WorkerHealth.EXITED_CLEAN

    log_text = handle.log_path.read_text(encoding="utf-8", errors="replace")
    assert "bar#" in log_text
    assert handle.log_path.parent.name == "logs"
    assert handle.log_path.parent.parent.name == "AAPL"
