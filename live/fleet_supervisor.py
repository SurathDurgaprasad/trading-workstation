"""Real-time strategy validation mission, multi-symbol hardening pass --
launches and supervises N independent, single-symbol `paper-live`
subprocesses: the production mechanism for tomorrow's multi-symbol
session (see live/runtime_layout.py's own module docstring for why a
single-process multi-symbol pipeline is NOT used -- CriticGate is
symbol-bound, and live/pipeline.py is not modified to work around that).

Pure process orchestration: this module has ZERO knowledge of trading
logic, strategy, risk, or CriticGate -- it launches `python main.py
paper-live ...` as a subprocess per symbol (treating it as an opaque,
already-hardened CLI command) and watches process liveness plus each
worker's own log output (the SAME [GAP DETECTED]/[GAP ONGOING]/FEED
DISCONNECTED signals live/gap_monitor.py and live/pipeline.py already
print -- reused here, not re-implemented) for health signals. Never
writes to any trading database; the end-of-session summary reads them
read-only.

Command construction, health classification, and the bounded-restart
decision are all pure functions, independently testable without
spawning a real process -- `launch_worker` is the one function that
actually does, and is covered separately by an integration test using
`--source mock` (fast, no live dependency).
"""

import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from live.runtime_layout import symbol_runtime_paths


class WorkerHealth(str, Enum):
    RUNNING = "RUNNING"
    EXITED_CLEAN = "EXITED_CLEAN"
    """Process exited with code 0 -- e.g. a --max-bars session that
    reached its bound and shut down normally."""
    EXITED_ERROR = "EXITED_ERROR"
    """Process exited with a non-zero code -- a real failure."""
    GAP_DETECTED = "GAP_DETECTED"
    """Process still alive, but its own most recent log activity is a
    gap/disconnect signal with no newer bar since -- see
    live/gap_monitor.py entry #-- this reuses that existing signal
    rather than re-detecting gaps a second, independent way."""
    SUPERVISION_ERROR = "SUPERVISION_ERROR"
    """Adversarial hardening pass finding: `poll_fleet_once`'s per-symbol
    loop previously had no exception boundary at all around
    `check_worker_health`/`relaunch` -- a single symbol raising (e.g. a
    transient Windows file-lock on its own log during `_tail_lines`, or
    `subprocess.Popen` failing during a relaunch: missing interpreter,
    OS process-table exhaustion, a bad path) propagated out of the ENTIRE
    poll cycle, out of run_fleet_supervise_command's while loop, straight
    into its `finally: shutdown_fleet(handles)` -- which terminates EVERY
    worker, including every other symbol that was perfectly healthy.
    This status makes that failure visible (surfaced via the same
    format_fleet_status_line every other status uses) INSTEAD of letting
    it escape and take the whole fleet down -- see poll_fleet_once's own
    per-symbol try/except for the fix."""


@dataclass(frozen=True)
class WorkerStatus:
    symbol: str
    health: WorkerHealth
    pid: int | None
    exit_code: int | None
    restarts: int
    detail: str


@dataclass
class WorkerHandle:
    symbol: str
    process: subprocess.Popen
    log_path: Path
    restarts: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def build_worker_command(
    *, python_executable: str, main_py_path: str, symbol: str, runtime_dir: str,
    source: str = "dhan", interval: str = "1m", cost_model: str = "india_nse_intraday_2026",
    evaluate_every_n_bars: int = 20, extra_args: list[str] | None = None,
) -> list[str]:
    """Pure -- builds the exact argv for one symbol's paper-live worker.
    Factored out from launch_worker() so the EXACT command a real launch
    would use is independently testable without spawning a real
    process. Deliberately mirrors this mission's own required flags:
    --record-predictions, --evaluate-every-n-bars, --cost-model
    india_nse_intraday_2026 (never silently the generic zero-cost
    model), --runtime-dir (deterministic per-symbol isolation).
    `source` defaults to "dhan" (the only real production value); tests
    override it to "mock" rather than relying on argparse's
    last-flag-wins behavior with a duplicated --source in extra_args."""
    args = [
        python_executable, main_py_path, "paper-live",
        "--source", source, "--symbol", symbol, "--interval", interval,
        "--runtime-dir", runtime_dir,
        "--record-predictions", "--evaluate-every-n-bars", str(evaluate_every_n_bars),
        "--cost-model", cost_model,
        "--auto-approve", "--no-ai-explanation",
    ]
    if extra_args:
        args.extend(extra_args)
    return args


def build_worker_env(*, base_env: dict, env_overrides: dict | None = None) -> dict:
    """Pure -- layers env_overrides on top of base_env (never replaces
    it) and forces PYTHONUNBUFFERED=1. Factored out of launch_worker()
    so the merge behavior itself is unit-testable without spawning a
    real process; `base_env` is normally os.environ but is passed in
    explicitly so tests don't depend on this process's own real
    environment."""
    worker_env = dict(base_env)
    worker_env.update(env_overrides or {})
    worker_env["PYTHONUNBUFFERED"] = "1"
    return worker_env


def launch_worker(
    *, symbol: str, runtime_dir: str, python_executable: str = sys.executable,
    main_py_path: str = "main.py", source: str = "dhan", interval: str = "1m",
    cost_model: str = "india_nse_intraday_2026", evaluate_every_n_bars: int = 20,
    extra_args: list[str] | None = None, env_overrides: dict | None = None,
) -> WorkerHandle:
    """Launches ONE symbol's paper-live worker as a real subprocess, its
    stdout+stderr redirected to {runtime_dir}/{symbol}/logs/session.log.
    PYTHONUNBUFFERED=1 is set in the subprocess's own environment --
    never left to be forgotten by whoever invokes this, closing the
    real, live-found stdout-buffering observability gap from
    FINAL_FAILURE_MODE_ANALYSIS.md entry #48 (that finding was from a
    manually-invoked session; this is the automated equivalent).
    `env_overrides` is layered ON TOP of this process's own inherited
    environment (os.environ), never a replacement for it -- a bare
    `subprocess.Popen(..., env={"PYTHONUNBUFFERED": "1"})` hands the
    child an almost-empty environment (no PATH, no SystemRoot, ...),
    which on Windows makes the interpreter itself fail to start
    correctly. This was caught by this module's own integration test
    (a real subprocess launch that must exit 0), not anticipated in
    advance."""
    paths = symbol_runtime_paths(runtime_dir, symbol)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = paths.logs_dir / "session.log"

    command = build_worker_command(
        python_executable=python_executable, main_py_path=main_py_path, symbol=paths.symbol,
        runtime_dir=str(runtime_dir), source=source, interval=interval, cost_model=cost_model,
        evaluate_every_n_bars=evaluate_every_n_bars, extra_args=extra_args,
    )
    worker_env = build_worker_env(base_env=os.environ, env_overrides=env_overrides)

    log_file = open(log_path, "a")
    process = subprocess.Popen(command, stdout=log_file, stderr=subprocess.STDOUT, env=worker_env)
    return WorkerHandle(symbol=paths.symbol, process=process, log_path=log_path)


# These literal substrings are read directly off main.py's own
# _run_paper_live_loop print statements (verified against the source, not
# guessed): "[GAP DETECTED]"/"[GAP ONGOING]" from the gap_monitor wiring;
# "FEED DISCONNECTED" from the FEED_DISCONNECTED branch; "bar#" from
# every one of the KILL_SWITCH_ACTIVE/CRITIC_REJECTED/default branches'
# per-bar line, and "SIGNAL DETECTED" from _print_signal_block, which is
# the one branch (PENDING_HUMAN_APPROVAL) that never prints "bar#". If
# main.py's own wording ever changes, tests/test_fleet_supervisor.py's
# real-subprocess integration test (not just the injected-log-lines unit
# tests) will catch the drift.
_GAP_MARKERS = ("[GAP DETECTED]", "[GAP ONGOING]")
_DISCONNECT_MARKERS = ("FEED DISCONNECTED",)
_NEW_DATA_MARKERS = ("bar#", "SIGNAL DETECTED")


def _tail_lines(path: Path, *, max_lines: int = 200) -> list[str]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    return lines[-max_lines:]


def check_worker_health(handle: WorkerHandle, *, log_lines: list[str] | None = None) -> WorkerStatus:
    """Read-only health check for ONE worker: process liveness (exit
    code if it already died) plus a light scan of its own recent log
    output for the gap/disconnect markers _run_paper_live_loop and
    live/gap_monitor.py already print -- reuses that existing signal
    rather than re-implementing gap detection a second, independently-
    drifting way. `log_lines` is injectable for deterministic testing;
    defaults to actually reading the worker's own log file."""
    exit_code = handle.process.poll()
    if exit_code is not None:
        health = WorkerHealth.EXITED_CLEAN if exit_code == 0 else WorkerHealth.EXITED_ERROR
        return WorkerStatus(
            symbol=handle.symbol, health=health, pid=handle.process.pid, exit_code=exit_code,
            restarts=handle.restarts, detail=f"process exited with code {exit_code}",
        )

    recent = log_lines if log_lines is not None else _tail_lines(handle.log_path, max_lines=50)
    last_gap_index = max((i for i, line in enumerate(recent) if any(m in line for m in _GAP_MARKERS)), default=-1)
    last_disconnect_index = max((i for i, line in enumerate(recent) if any(m in line for m in _DISCONNECT_MARKERS)), default=-1)
    last_new_data_index = max((i for i, line in enumerate(recent) if any(m in line for m in _NEW_DATA_MARKERS)), default=-1)

    if last_disconnect_index > last_new_data_index:
        return WorkerStatus(
            symbol=handle.symbol, health=WorkerHealth.GAP_DETECTED, pid=handle.process.pid, exit_code=None,
            restarts=handle.restarts, detail="feed disconnected message is the most recent log activity",
        )
    if last_gap_index > last_new_data_index:
        return WorkerStatus(
            symbol=handle.symbol, health=WorkerHealth.GAP_DETECTED, pid=handle.process.pid, exit_code=None,
            restarts=handle.restarts, detail="most recent log activity is a gap warning, no newer bar since",
        )
    return WorkerStatus(
        symbol=handle.symbol, health=WorkerHealth.RUNNING, pid=handle.process.pid, exit_code=None,
        restarts=handle.restarts, detail="alive, no gap/disconnect signal in recent log output",
    )


def should_restart(status: WorkerStatus, *, max_restarts: int) -> bool:
    """Pure bounded-retry decision. The mission's own explicit
    requirement: 'Do not automatically restart endlessly. Bound retries
    and clearly report worker health.' Only EXITED_ERROR is ever a
    restart candidate -- EXITED_CLEAN means the worker did exactly what
    it was told (e.g. reached --max-bars) and restarting it would be
    wrong, and RUNNING/GAP_DETECTED workers are still alive and are not
    a restart decision at all (a gap is a data-delivery observation, not
    proof the process itself needs replacing)."""
    if status.health != WorkerHealth.EXITED_ERROR:
        return False
    return status.restarts < max_restarts


@dataclass(frozen=True)
class FleetSnapshot:
    statuses: list[WorkerStatus]
    restarted_symbols: list[str]
    exhausted_symbols: list[str]
    """Symbols that just exited with an error AND have already used up
    their restart budget -- these need a human to look at them; nothing
    further will be attempted automatically for them."""


def poll_fleet_once(
    handles: dict[str, WorkerHandle], *, max_restarts: int, relaunch: Callable[[str, int], WorkerHandle],
) -> FleetSnapshot:
    """One supervision cycle across the whole fleet: check every
    worker's health, and for any that crashed (EXITED_ERROR) under the
    restart cap, relaunch it via the injected `relaunch(symbol,
    next_restart_count)` callback -- injected so this stays testable
    with a fake relaunch function, no real subprocess required. Mutates
    `handles` in place (replacing a restarted worker's entry with its
    new WorkerHandle) since it IS the live fleet registry, not a pure
    computation -- callers keep a reference to the same dict across
    polls."""
    statuses: list[WorkerStatus] = []
    restarted: list[str] = []
    exhausted: list[str] = []
    for symbol, handle in list(handles.items()):
        # Adversarial hardening pass finding: this used to have NO
        # exception boundary at all -- one symbol raising here (a
        # transient log-file read error, subprocess.Popen failing on
        # relaunch) propagated straight out of the ENTIRE poll cycle,
        # into run_fleet_supervise_command's `finally: shutdown_fleet(
        # handles)`, tearing down every other, perfectly healthy worker
        # too. Violates this project's own "one symbol failure cannot
        # stop another symbol" requirement. The failing symbol's
        # PREVIOUS handle is kept (never silently dropped or replaced
        # with something half-constructed) so the next poll cycle gets
        # another chance at it.
        try:
            status = check_worker_health(handle)
            statuses.append(status)
            if status.health == WorkerHealth.EXITED_ERROR:
                if should_restart(status, max_restarts=max_restarts):
                    handles[symbol] = relaunch(symbol, handle.restarts + 1)
                    restarted.append(symbol)
                else:
                    exhausted.append(symbol)
        except Exception as exc:  # noqa: BLE001 -- one symbol's supervision failure must never abort the whole fleet's poll cycle
            # `.pid` only, deliberately -- NOT another `.poll()` call: if
            # `.poll()` itself is what raised (a real scenario this fix
            # covers), calling it again here would raise a second time and
            # defeat the very isolation this except block exists for.
            # `.pid` is set at process-construction time and is safe to
            # read regardless of whatever `.poll()` is currently doing.
            statuses.append(WorkerStatus(
                symbol=symbol, health=WorkerHealth.SUPERVISION_ERROR, pid=handle.process.pid,
                exit_code=None, restarts=handle.restarts, detail=f"supervision itself failed for this symbol: {exc}",
            ))
    return FleetSnapshot(statuses=statuses, restarted_symbols=restarted, exhausted_symbols=exhausted)


def format_fleet_status_line(status: WorkerStatus) -> str:
    """Pure -- one human-readable line per worker for a supervision
    loop's own console output. Not a substitute for Item 4's end-of-
    session aggregation report (that reads the persisted DBs; this is
    live, in-the-moment process/feed health only)."""
    pid_part = f"pid={status.pid}" if status.pid is not None else "pid=?"
    restarts_part = f"restarts={status.restarts}"
    return f"[{status.symbol:<12}] {status.health.value:<13} {pid_part} {restarts_part}  {status.detail}"


def shutdown_fleet(
    handles: dict[str, WorkerHandle], *, terminate_timeout_seconds: float = 30.0, print_fn: Callable[[str], None] = print,
) -> None:
    """Item 6 (graceful shutdown): terminates every still-running worker
    and waits for a clean exit, with a bounded per-worker force-kill as
    a safety net -- factored out of main.py's run_fleet_supervise_command
    so this logic is independently testable against FAKE long-running
    processes (deterministic: no real subprocess timing races) rather
    than only provable by racing a real subprocess's own completion
    time.

    On Windows/POSIX, a Ctrl+C in this process's own console is already
    broadcast to every child in the same console process group, so in
    the common case every worker is already exiting through its OWN
    existing shutdown path by the time this runs -- terminate()/kill()
    here only matters for a worker that does not exit on its own within
    the timeout (hung, or launched detached from this console)."""
    for symbol, handle in handles.items():
        if handle.process.poll() is None:
            print_fn(f"  terminating {symbol} (pid={handle.process.pid}) ...")
            handle.process.terminate()
    for symbol, handle in handles.items():
        try:
            handle.process.wait(timeout=terminate_timeout_seconds)
        except subprocess.TimeoutExpired:
            print_fn(f"  {symbol} did not exit within {terminate_timeout_seconds:.0f}s -- killing.")
            handle.process.kill()
            handle.process.wait(timeout=10)
