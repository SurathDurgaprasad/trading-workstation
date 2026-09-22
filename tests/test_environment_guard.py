"""live/environment_guard.py -- the startup invariant added after the
2026-09-22 incident where a real fleet-supervise session ran for hours
under the wrong (system, not venv) Python interpreter before the gap was
noticed. See that module's own docstring for the full incident."""

from pathlib import Path

import pytest

from live.environment_guard import (
    EnvironmentCheckReport,
    CheckResult,
    run_startup_environment_checks,
    verify_dependency_fingerprint,
    verify_required_runtime_imports,
    verify_venv_interpreter,
)


def _make_fake_venv(tmp_path: Path) -> Path:
    exe = tmp_path / "venv" / "Scripts" / "python.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("not a real interpreter, just needs to exist for Path.resolve()")
    return exe


# --- verify_venv_interpreter -------------------------------------------------


def test_verify_venv_interpreter_passes_when_executable_is_inside_the_projects_own_venv(tmp_path):
    exe = _make_fake_venv(tmp_path)
    result = verify_venv_interpreter(executable=str(exe), project_root=tmp_path)
    assert result.passed
    assert "is inside this project's venv" in result.detail


def test_verify_venv_interpreter_fails_when_executable_is_the_system_interpreter(tmp_path):
    _make_fake_venv(tmp_path)  # the project's real venv exists, just isn't the one used
    system_python = tmp_path / "AppData" / "Local" / "Programs" / "Python" / "Python314" / "python.exe"
    system_python.parent.mkdir(parents=True)
    system_python.write_text("system interpreter stand-in")

    result = verify_venv_interpreter(executable=str(system_python), project_root=tmp_path)

    assert not result.passed
    assert "is not inside this project's venv" in result.detail
    assert "Scripts" in result.detail or "bin" in result.detail  # tells the operator how to fix it


def test_verify_venv_interpreter_fails_when_executable_is_a_DIFFERENT_projects_venv(tmp_path):
    """Real near-miss this check specifically guards against: a naive
    `sys.prefix != sys.base_prefix` check would pass for ANY active venv,
    including one that has none of this project's own dependencies."""
    _make_fake_venv(tmp_path)
    other_project_venv = tmp_path.parent / "some_other_project" / "venv" / "Scripts" / "python.exe"
    other_project_venv.parent.mkdir(parents=True, exist_ok=True)
    other_project_venv.write_text("a different project's venv")

    result = verify_venv_interpreter(executable=str(other_project_venv), project_root=tmp_path)

    assert not result.passed


# --- verify_required_runtime_imports -----------------------------------------


def test_verify_required_runtime_imports_passes_when_every_declared_dependency_imports(tmp_path):
    req = tmp_path / "requirements.txt"
    req.write_text("pyyaml==6.0.3\nrequests==2.34.2\n")  # both real, both installed in this test venv

    result = verify_required_runtime_imports(requirements_path=req)

    assert result.passed
    assert "all 2 non-test-only declared dependencies import cleanly" in result.detail


def test_verify_required_runtime_imports_fails_and_names_every_missing_dependency(tmp_path):
    req = tmp_path / "requirements.txt"
    req.write_text("pyyaml==6.0.3\ndefinitely-not-a-real-package==1.0.0\nalso-not-real==2.0.0\n")

    result = verify_required_runtime_imports(requirements_path=req)

    assert not result.passed
    assert "definitely-not-a-real-package" in result.detail
    assert "also-not-real" in result.detail
    assert "pyyaml" not in result.detail  # the one real, importable dependency is not reported as missing


def test_verify_required_runtime_imports_applies_the_distribution_to_import_name_mapping(tmp_path):
    """pyyaml -> `import yaml`, not `import pyyaml` -- the exact mismatch
    class this project's requirements.txt has several of."""
    req = tmp_path / "requirements.txt"
    req.write_text("pyyaml==6.0.3\n")

    result = verify_required_runtime_imports(requirements_path=req)

    assert result.passed


def test_verify_required_runtime_imports_skips_test_only_distributions(tmp_path, monkeypatch):
    """pytest/hypothesis are test-only per requirements.txt's own section
    marker -- a real production live session never needs them, so a
    hypothetically-missing test-only dependency must never block launch.
    Proven directly (not just "pytest happens to be importable anyway")
    by patching the exclusion set to cover a guaranteed-nonexistent name."""
    import live.environment_guard as environment_guard

    monkeypatch.setattr(environment_guard, "_TEST_ONLY_DISTS", frozenset({"definitely-not-a-real-package"}))
    req = tmp_path / "requirements.txt"
    req.write_text("pyyaml==6.0.3\ndefinitely-not-a-real-package==1.0.0\n")

    result = verify_required_runtime_imports(requirements_path=req)

    assert result.passed, "the test-only-excluded package must not cause a failure even though it is not importable"


def test_verify_required_runtime_imports_fails_clearly_when_requirements_file_is_missing(tmp_path):
    result = verify_required_runtime_imports(requirements_path=tmp_path / "does_not_exist.txt")

    assert not result.passed
    assert "not found" in result.detail


# --- verify_dependency_fingerprint (advisory-only) ---------------------------


def test_verify_dependency_fingerprint_never_blocks_even_when_a_version_has_drifted(tmp_path):
    req = tmp_path / "requirements.txt"
    req.write_text("pyyaml==0.0.1\n")  # real package, deliberately wrong pinned version

    result = verify_dependency_fingerprint(requirements_path=req)

    assert result.passed, "dependency_fingerprint must always report passed=True -- it is advisory, never blocking"
    assert "pyyaml" in result.detail
    assert "0.0.1" in result.detail


def test_verify_dependency_fingerprint_reports_a_clean_match_when_versions_agree(tmp_path):
    import importlib.metadata

    installed = importlib.metadata.version("pyyaml")
    req = tmp_path / "requirements.txt"
    req.write_text(f"pyyaml=={installed}\n")

    result = verify_dependency_fingerprint(requirements_path=req)

    assert result.passed
    assert "matches requirements.txt" in result.detail


# --- run_startup_environment_checks (the single entry point) ----------------


def test_run_startup_environment_checks_fails_overall_when_the_venv_check_fails(tmp_path):
    req = tmp_path / "requirements.txt"
    req.write_text("pyyaml==6.0.3\n")
    system_python = tmp_path / "system" / "python.exe"
    system_python.parent.mkdir(parents=True)
    system_python.write_text("stand-in")

    report = run_startup_environment_checks(executable=str(system_python), project_root=tmp_path, requirements_path=req)

    assert isinstance(report, EnvironmentCheckReport)
    assert not report.passed
    assert any(c.name == "venv_interpreter" and not c.passed for c in report.failures)


def test_run_startup_environment_checks_passes_when_interpreter_and_dependencies_are_both_correct(tmp_path):
    exe = _make_fake_venv(tmp_path)
    req = tmp_path / "requirements.txt"
    req.write_text("pyyaml==6.0.3\n")

    report = run_startup_environment_checks(executable=str(exe), project_root=tmp_path, requirements_path=req)

    assert report.passed
    assert report.failures == ()


def test_environment_check_report_format_report_shows_pass_and_fail_per_check(tmp_path):
    report = EnvironmentCheckReport(checks=(
        CheckResult("a", True, "fine"),
        CheckResult("b", False, "broken"),
    ))

    text = report.format_report()

    assert "[PASS] a: fine" in text
    assert "[FAIL] b: broken" in text
