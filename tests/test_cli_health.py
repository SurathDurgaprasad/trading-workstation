"""main.py's `health` command -- a thin CLI wrapper over the shared
core.health.collect_system_health, the same source the dashboard's
/health route reads."""
import pytest

from main import parse_args, run_health_command


def test_health_subcommand_parses():
    args = parse_args(["health"])
    assert args.command == "health"
    assert args.no_ollama is False


def test_health_no_ollama_flag_parses():
    args = parse_args(["health", "--no-ollama"])
    assert args.no_ollama is True


def test_health_is_recognized_as_a_known_command_not_misrouted_to_analyze():
    """Regression guard: _KNOWN_COMMANDS gates the bare-argv backward-
    compatibility fallback to `analyze` -- if "health" were missing from
    it, `python main.py health` would silently become
    `python main.py analyze health`."""
    args = parse_args(["health"])
    assert args.command == "health"


def test_health_command_runs_and_prints_overall_status(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("main.PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("DHAN_CLIENT_ID", raising=False)
    monkeypatch.delenv("DHAN_ACCESS_TOKEN", raising=False)

    run_health_command(parse_args(["health", "--no-ollama"]))

    output = capsys.readouterr().out
    assert "UNIFIED HEALTH CHECK" in output
    assert "application" in output
    assert "OVERALL STATUS:" in output
    assert "ollama" not in output  # --no-ollama skips it entirely, not just marks it


def test_health_command_includes_ollama_by_default(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("main.PROJECT_ROOT", tmp_path)

    run_health_command(parse_args(["health"]))

    output = capsys.readouterr().out
    assert "ollama" in output


def test_health_command_exits_nonzero_on_a_failed_overall_status(capsys, monkeypatch, tmp_path):
    """A corrupted database is a genuine FAILED-overall scenario --
    confirms the CLI actually surfaces it as a nonzero exit, not just
    printed text a script could miss."""
    monkeypatch.setattr("main.PROJECT_ROOT", tmp_path)
    corrupt_db = tmp_path / "data" / "paper_trading.db"
    corrupt_db.parent.mkdir(parents=True, exist_ok=True)
    corrupt_db.write_bytes(b"not a real sqlite file")
    monkeypatch.setattr("main.DEFAULT_PAPER_DB_PATH", corrupt_db)

    with pytest.raises(SystemExit) as exc_info:
        run_health_command(parse_args(["health", "--no-ollama"]))
    assert exc_info.value.code == 1

    output = capsys.readouterr().out
    assert "OVERALL STATUS: FAILED" in output
