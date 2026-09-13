"""main.py's `_run_startup_gate` -- the release-gate mission's own
explicit "startup diagnostics" requirement: CRITICAL failure -> refuse
to start (SAFE_STOP), OPTIONAL failure -> DEGRADED (warn, continue).
Wired into the trading-adjacent entry points (`paper-live`, `schedule
tick`/`schedule loop`) only -- diagnostic tools (`dashboard`, `health`,
`readiness-check`) are deliberately never gated on their own health
check, so a broken system stays diagnosable.
"""
import pytest

from core.health import ComponentHealth, ComponentStatus, OverallStatus, SystemHealth
from main import _run_startup_gate, parse_args, run_paper_live_command, run_schedule_command


def _health(overall: OverallStatus, components=()) -> SystemHealth:
    return SystemHealth(overall=overall, components=tuple(components))


def test_healthy_status_prints_nothing_and_does_not_exit(capsys, monkeypatch):
    monkeypatch.setattr("core.health.collect_system_health", lambda **kwargs: _health(OverallStatus.HEALTHY))

    _run_startup_gate(command_name="test-command")

    assert capsys.readouterr().out == ""


def test_failed_status_refuses_to_start(capsys, monkeypatch):
    components = (ComponentHealth("database", ComponentStatus.FAILED, "corruption found"),)
    monkeypatch.setattr("core.health.collect_system_health", lambda **kwargs: _health(OverallStatus.FAILED, components))

    with pytest.raises(SystemExit) as exc_info:
        _run_startup_gate(command_name="test-command")

    assert exc_info.value.code == 1
    stderr = capsys.readouterr().err
    assert "SAFE_STOP" in stderr
    assert "test-command" in stderr
    assert "corruption found" in stderr


def test_safe_stop_status_warns_but_does_not_exit(capsys, monkeypatch):
    components = (ComponentHealth("kill_switch", ComponentStatus.DEGRADED, "ACTIVE -- new paper orders are blocked until reset."),)
    monkeypatch.setattr("core.health.collect_system_health", lambda **kwargs: _health(OverallStatus.SAFE_STOP, components))

    _run_startup_gate(command_name="test-command")  # must not raise

    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "ACTIVE" in out
    assert "test-command" in out


def test_degraded_status_warns_but_does_not_exit(capsys, monkeypatch):
    components = (ComponentHealth("ollama", ComponentStatus.DEGRADED, "unreachable"),)
    monkeypatch.setattr("core.health.collect_system_health", lambda **kwargs: _health(OverallStatus.DEGRADED, components))

    _run_startup_gate(command_name="test-command")  # must not raise

    out = capsys.readouterr().out
    assert "DEGRADED" in out
    assert "ollama" in out
    assert "test-command" in out


# --- wiring: the gate is actually reached by the real entry points -----------


def test_paper_live_is_blocked_by_a_failed_startup_gate(monkeypatch, tmp_path):
    monkeypatch.setattr("core.health.collect_system_health", lambda **kwargs: _health(
        OverallStatus.FAILED, (ComponentHealth("disk", ComponentStatus.FAILED, "write probe failed"),)
    ))
    args = parse_args([
        "paper-live", "--symbol", "AAPL", "--interval", "1d", "--period", "1y",
        "--db", str(tmp_path / "paper.db"), "--state-db", str(tmp_path / "state.db"),
    ])

    with pytest.raises(SystemExit) as exc_info:
        run_paper_live_command(args)
    assert exc_info.value.code == 1


def test_paper_live_kill_switch_admin_actions_bypass_the_gate(capsys, monkeypatch, tmp_path):
    """--kill-switch/--reset-kill-switch must remain reachable even when
    the gate would otherwise refuse to start -- an operator must always
    be able to activate or reset the kill switch."""
    monkeypatch.setattr("core.health.collect_system_health", lambda **kwargs: _health(
        OverallStatus.FAILED, (ComponentHealth("disk", ComponentStatus.FAILED, "write probe failed"),)
    ))
    args = parse_args(["paper-live", "--kill-switch", "--state-db", str(tmp_path / "state.db")])

    run_paper_live_command(args)  # must NOT raise SystemExit

    assert "KILL SWITCH ACTIVATED" in capsys.readouterr().out


def test_schedule_tick_is_blocked_by_a_failed_startup_gate(monkeypatch, tmp_path):
    monkeypatch.setattr("core.health.collect_system_health", lambda **kwargs: _health(
        OverallStatus.FAILED, (ComponentHealth("risk", ComponentStatus.FAILED, "invalid config"),)
    ))
    args = parse_args(["schedule", "tick", "--symbols", "AAPL", "--run-db", str(tmp_path / "runs.db")])

    with pytest.raises(SystemExit) as exc_info:
        run_schedule_command(args)
    assert exc_info.value.code == 1


def test_schedule_status_bypasses_the_gate(monkeypatch, tmp_path):
    """`schedule status` is a read-only audit view -- it must remain
    reachable even when the gate would otherwise refuse to start, same
    reasoning as dashboard/health/readiness-check never being gated."""
    monkeypatch.setattr("core.health.collect_system_health", lambda **kwargs: _health(
        OverallStatus.FAILED, (ComponentHealth("disk", ComponentStatus.FAILED, "write probe failed"),)
    ))
    args = parse_args(["schedule", "status", "--run-db", str(tmp_path / "runs.db")])

    run_schedule_command(args)  # must NOT raise SystemExit
