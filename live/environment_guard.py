"""Startup environment invariant for real, unattended live sessions
(`fleet-supervise` and `paper-live --source dhan`).

2026-09-22 incident: today's `fleet-supervise` session was launched under the
SYSTEM Python interpreter (on PATH) rather than this project's own `venv`,
the only interpreter this project's dependencies (see ``requirements.txt``)
are actually installed into. Every one of the 15 spawned workers silently
inherited that same wrong interpreter (`live/fleet_supervisor.py::launch_worker`
defaults `python_executable` to `sys.executable` -- exactly correct in general,
since it means a worker always runs under whatever interpreter launched the
supervisor, but it also means the supervisor's own interpreter mistake
propagates to the entire fleet with nothing to catch it). The mistake was
non-fatal ONLY because the specific missing dependency (`yfinance`) is
reached through a LAZY import inside `predictions/tracker.py`'s periodic
auto-evaluation path, four hours into the session -- not at process start. A
different missing dependency reachable earlier in the live path (candle
building, strategy evaluation, risk sizing) would not have been this
forgiving; a production supervisor should fail loudly at startup rather than
discover its environment is wrong hours into a session.

This module answers, once, before a single worker is launched or a single
real network connection is opened: is this interpreter the project's own
venv, and does it actually have every direct dependency this project
declares in ``requirements.txt``? Both checks are cheap (a handful of
milliseconds) and are never repeated per worker or per bar.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# PyPI/requirements.txt distribution name -> the name you actually `import`,
# for the handful of entries where the two differ.
_DIST_TO_IMPORT_NAME = {
    "pyyaml": "yaml",
    "scikit-learn": "sklearn",
    "websocket-client": "websocket",
    "langchain-core": "langchain_core",
    "langchain-community": "langchain_community",
    "langchain-chroma": "langchain_chroma",
    "langchain-ollama": "langchain_ollama",
    "langchain-text-splitters": "langchain_text_splitters",
    "langchain-openai": "langchain_openai",
}

# requirements.txt entries that are test-only (never imported by a live
# production path -- see that file's own "# test-only" section marker).
# Excluded from the launch-blocking checks: a missing test-only package
# under a real venv is not a live-session risk.
_TEST_ONLY_DISTS = frozenset({"pytest", "hypothesis"})

_REQUIREMENT_LINE = re.compile(r"^([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.\-]+)$")


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class EnvironmentCheckReport:
    checks: tuple[CheckResult, ...]

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        return tuple(c for c in self.checks if not c.passed)

    def format_report(self) -> str:
        lines = ["STARTUP ENVIRONMENT CHECK:"]
        for c in self.checks:
            lines.append(f"  [{'PASS' if c.passed else 'FAIL'}] {c.name}: {c.detail}")
        return "\n".join(lines)


def _default_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def verify_venv_interpreter(*, executable: str | None = None, project_root: Path | None = None) -> CheckResult:
    """The project ships its own ``venv/`` (``Scripts/python.exe`` on
    Windows, ``bin/python`` on POSIX) -- the only interpreter this
    project's own dependencies are installed into. Checks that the running
    interpreter resolves INSIDE that specific directory, not merely that
    *some* venv is active (a different project's venv would pass a naive
    ``sys.prefix != sys.base_prefix`` check while still lacking this
    project's own dependencies -- exactly the kind of near-miss this check
    exists to rule out)."""
    exe = Path(executable if executable is not None else sys.executable).resolve()
    root = project_root if project_root is not None else _default_project_root()
    expected_dir = (root / "venv").resolve()
    try:
        exe.relative_to(expected_dir)
    except ValueError:
        return CheckResult(
            "venv_interpreter", False,
            f"{exe} is not inside this project's venv ({expected_dir}). Launch via "
            f"'{expected_dir / 'Scripts' / 'python.exe'}' (Windows) or "
            f"'{expected_dir / 'bin' / 'python'}' (POSIX), or activate the venv first.",
        )
    return CheckResult("venv_interpreter", True, f"{exe} is inside this project's venv ({expected_dir}).")


def _parse_requirements(requirements_path: Path) -> list[tuple[str, str]]:
    """[(distribution_name, pinned_version), ...] for every ``name==version``
    line; comments, blank lines, and anything without an exact ``==`` pin are
    skipped (``requirements.txt``'s own header documents that every real
    entry there is pinned)."""
    pairs: list[tuple[str, str]] = []
    for line in requirements_path.read_text(encoding="utf-8").splitlines():
        match = _REQUIREMENT_LINE.match(line.strip())
        if match:
            pairs.append((match.group(1), match.group(2)))
    return pairs


def _non_test_only(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [(name, version) for name, version in pairs if name.lower() not in _TEST_ONLY_DISTS]


def verify_required_runtime_imports(*, requirements_path: Path | None = None) -> CheckResult:
    """Every non-test-only distribution ``requirements.txt`` declares must
    actually import under the CURRENT interpreter. Deliberately broader than
    checking only the one dependency (``yfinance``) that caused the
    2026-09-22 incident -- that one is reached hours into a session via a
    lazy import; there is no reliable way to enumerate every lazy import a
    live session might ever reach other than checking the project's own
    full declared dependency list."""
    req_path = requirements_path if requirements_path is not None else _default_project_root() / "requirements.txt"
    if not req_path.exists():
        return CheckResult("required_imports", False, f"requirements.txt not found at {req_path} -- cannot verify.")
    pairs = _non_test_only(_parse_requirements(req_path))
    missing: list[str] = []
    for dist_name, _version in pairs:
        import_name = _DIST_TO_IMPORT_NAME.get(dist_name.lower(), dist_name.replace("-", "_"))
        try:
            importlib.import_module(import_name)
        except ImportError:
            missing.append(f"{dist_name} (import {import_name})")
    if missing:
        return CheckResult(
            "required_imports", False,
            f"{len(missing)} declared dependenc{'y is' if len(missing) == 1 else 'ies are'} not importable "
            f"under this interpreter ({sys.executable}): {', '.join(missing)}.",
        )
    return CheckResult("required_imports", True, f"all {len(pairs)} non-test-only declared dependencies import cleanly.")


def verify_dependency_fingerprint(*, requirements_path: Path | None = None) -> CheckResult:
    """Advisory only (this check's own ``CheckResult.passed`` is always
    True -- it never blocks launch): compares each declared dependency's
    INSTALLED version against ``requirements.txt``'s own pin. Drift is not
    itself proof of a problem (this project pins to "whatever venv/ already
    had," not to a tested-compatible range -- see ``requirements.txt``'s own
    header), but silent drift is exactly the kind of thing that should be
    visible at startup rather than discovered mid-incident."""
    req_path = requirements_path if requirements_path is not None else _default_project_root() / "requirements.txt"
    if not req_path.exists():
        return CheckResult("dependency_fingerprint", True, f"requirements.txt not found at {req_path} -- skipped.")
    pairs = _non_test_only(_parse_requirements(req_path))
    drifted: list[str] = []
    for dist_name, pinned_version in pairs:
        try:
            installed_version = importlib.metadata.version(dist_name)
        except importlib.metadata.PackageNotFoundError:
            continue  # already reported by verify_required_runtime_imports
        if installed_version != pinned_version:
            drifted.append(f"{dist_name}: requirements.txt pins {pinned_version}, installed {installed_version}")
    if drifted:
        return CheckResult(
            "dependency_fingerprint", True,
            f"{len(drifted)} version(s) drifted from requirements.txt (non-blocking): " + "; ".join(drifted),
        )
    return CheckResult("dependency_fingerprint", True, "every declared dependency's installed version matches requirements.txt.")


_REEXEC_GUARD_ENV_VAR = "TRADINGAGENTS_VENV_REEXEC_GUARD"


def _venv_python_path(project_root: Path) -> Path:
    venv_dir = (project_root / "venv").resolve()
    return venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def ensure_running_under_project_venv(
    *, executable: str | None = None, project_root: Path | None = None, argv: list[str] | None = None,
    runner=subprocess.run,
) -> bool:
    """Self-correcting launcher hardening, layered ON TOP of (never a
    replacement for) ``verify_venv_interpreter``'s own fail-closed check:
    call this FIRST, before any real work -- if the current process is not
    already running under this project's own venv, transparently
    re-executes the exact same command line under the correct interpreter
    instead of merely failing with a message an operator has to notice and
    act on themselves.

    This is what makes the 2026-09-22 incident ("fleet-supervise launched
    under the system Python for an entire session") structurally impossible
    to repeat, regardless of how the process was invoked -- typed directly,
    from a scheduled task, from a wrapper script -- rather than only
    detected after the fact. ``run_fleet_supervise_command`` and
    ``_build_market_data_source`` (main.py) both still call
    ``run_startup_environment_checks`` afterward, unconditionally -- this
    function is a convenience that makes that later check almost always
    find nothing to report, not a replacement for it (a machine with no
    venv at all, or a broken one, still needs that fail-closed check to
    actually stop the launch).

    Returns False whenever this process's own execution continues normally
    (already correct, or re-exec was not possible/needed -- e.g. no venv on
    this machine at all, left for the caller's own fail-closed check to
    report). When a re-exec IS performed, this function never returns at
    all: it calls ``sys.exit()`` with the spawned child's own exit code, so
    the parent process's only remaining job is to disappear once the real,
    correctly-launched child is done. Guarded by an environment variable
    against looping forever if the venv itself is missing or broken:
    re-execs AT MOST ONCE per process tree."""
    exe = Path(executable if executable is not None else sys.executable).resolve()
    root = project_root if project_root is not None else _default_project_root()
    expected_dir = (root / "venv").resolve()
    try:
        exe.relative_to(expected_dir)
        return False  # already correct -- the common case, must be a fast no-op
    except ValueError:
        pass

    if os.environ.get(_REEXEC_GUARD_ENV_VAR):
        return False  # already re-exec'd once in this process tree -- never loop

    venv_python = _venv_python_path(root)
    if not venv_python.exists():
        return False  # nothing to re-exec INTO; the caller's own fail-closed check reports this

    command_line = argv if argv is not None else sys.argv
    print(
        f"STARTUP: launched under {exe}, not this project's own venv ({expected_dir}) -- "
        f"transparently re-launching under {venv_python} instead.",
        flush=True,  # must land before the re-exec'd child's own output, across the process boundary
    )
    env = dict(os.environ)
    env[_REEXEC_GUARD_ENV_VAR] = "1"
    try:
        completed = runner([str(venv_python), *command_line], env=env)
    except OSError as exc:
        # Red-team finding (2026-09-22): this call sits BEFORE main()'s own
        # try/except _CONTROLLED_ERRORS block (it must -- the whole point is
        # to run before anything else does), so an OSError here (e.g.
        # venv_python.exists() is True but the file is a corrupted/non-PE
        # binary -- a real, distinct failure mode from "missing entirely")
        # would otherwise propagate as a raw, unactionable traceback instead
        # of this module's own clear, operator-facing message style. Fails
        # loudly and immediately either way -- subprocess.run against a
        # broken interpreter raises synchronously, it does not hang -- this
        # only changes HOW clearly that failure is reported.
        print(
            f"STARTUP: found {venv_python} but could not execute it ({type(exc).__name__}: {exc}) -- "
            "the venv may be corrupted or incomplete. Recreate it (e.g. 'python -m venv venv' followed by "
            "'pip install -r requirements.txt') and try again.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    sys.exit(completed.returncode)


def run_startup_environment_checks(
    *, executable: str | None = None, project_root: Path | None = None, requirements_path: Path | None = None,
) -> EnvironmentCheckReport:
    """The single entry point ``run_fleet_supervise_command`` (before
    launching any worker) and ``_build_market_data_source`` (before opening
    any real Dhan connection, covering standalone ``paper-live --source
    dhan`` too) call. ``venv_interpreter`` and ``required_imports`` are
    launch-BLOCKING (``EnvironmentCheckReport.passed`` is False if either
    fails); ``dependency_fingerprint`` is advisory-only and never blocks."""
    return EnvironmentCheckReport(checks=(
        verify_venv_interpreter(executable=executable, project_root=project_root),
        verify_required_runtime_imports(requirements_path=requirements_path),
        verify_dependency_fingerprint(requirements_path=requirements_path),
    ))
