"""Phase 15 §4/§23 security tests: credentials never land in source, in
logs, or in git-tracked files. No real credentials are used anywhere in
this file -- fake, obviously-not-real values throughout.
"""
import subprocess
from pathlib import Path

import pytest

from live.dhan.config import DhanCredentials, DhanCredentialsMissingError, load_dhan_credentials

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_load_dhan_credentials_raises_a_clear_error_when_unset(monkeypatch):
    monkeypatch.delenv("DHAN_CLIENT_ID", raising=False)
    monkeypatch.delenv("DHAN_ACCESS_TOKEN", raising=False)
    with pytest.raises(DhanCredentialsMissingError):
        load_dhan_credentials()


def test_load_dhan_credentials_error_message_never_echoes_a_partial_value(monkeypatch):
    monkeypatch.delenv("DHAN_CLIENT_ID", raising=False)
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "super-secret-value-should-never-appear")
    try:
        load_dhan_credentials()
    except DhanCredentialsMissingError as exc:
        assert "super-secret-value-should-never-appear" not in str(exc)


def test_load_dhan_credentials_reads_from_environment_only(monkeypatch):
    monkeypatch.setenv("DHAN_CLIENT_ID", "1000000001")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "fake.token.value")
    credentials = load_dhan_credentials()
    assert credentials.client_id == "1000000001"
    assert credentials.access_token == "fake.token.value"


def test_credentials_repr_masks_both_fields():
    """A stray print(credentials) or a debugger session must never dump
    the real client_id/access_token."""
    credentials = DhanCredentials(client_id="1000000001", access_token="fake.token.value")
    rendered = repr(credentials)
    assert "1000000001" not in rendered
    assert "fake.token.value" not in rendered
    assert "***" in rendered


def test_no_python_source_file_hardcodes_a_dhan_credential_variable_assignment():
    """Structural sweep: no live/dhan/*.py file assigns DHAN_CLIENT_ID or
    DHAN_ACCESS_TOKEN to a literal string -- only os.environ.get() reads."""
    package_dir = PROJECT_ROOT / "live" / "dhan"
    for py_file in package_dir.glob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        for forbidden_pattern in ('client_id = "', "client_id = '", 'access_token = "', "access_token = '"):
            assert forbidden_pattern not in text, f"{py_file.name} appears to hardcode a credential-shaped literal"


def test_gitignore_covers_env_files_and_key_material():
    gitignore_text = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in (".env", "*.pem", "*.key"):
        assert pattern in gitignore_text


def test_env_example_file_has_no_real_looking_values():
    """.env.example must document the variable NAMES only -- never a
    plausible-looking real value that someone might copy-paste and forget
    to replace."""
    example_path = PROJECT_ROOT / ".env.example"
    assert example_path.exists()
    text = example_path.read_text(encoding="utf-8")
    assert "DHAN_CLIENT_ID=" in text
    assert "DHAN_ACCESS_TOKEN=" in text
    # every assignment line's value must be empty (no accidental real-looking token)
    for line in text.splitlines():
        if line.startswith("DHAN_"):
            _, _, value = line.partition("=")
            assert value.strip() == "", f"{line!r} in .env.example should have an empty value"


@pytest.mark.skipif(not (PROJECT_ROOT / ".git").exists(), reason="Not running inside a git checkout")
def test_no_env_file_is_tracked_by_git():
    """Confirms .env (if it exists locally at all) was never actually
    committed -- distinct from merely being listed in .gitignore."""
    result = subprocess.run(
        ["git", "ls-files", ".env", ".env.local"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True,
    )
    assert result.stdout.strip() == ""


@pytest.mark.skipif(not (PROJECT_ROOT / ".git").exists(), reason="Not running inside a git checkout")
def test_no_tracked_file_contains_a_plausible_dhan_access_token_pattern():
    """Dhan access tokens are JWTs (three base64url segments separated by
    dots, starting "eyJ"). Scans every git-TRACKED file (not the whole
    working tree, which could contain this session's own local .env) for
    that shape -- a lightweight secret-scan gate before any push."""
    tracked_files = subprocess.run(
        ["git", "ls-files"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()

    import re

    jwt_pattern = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")
    offenders = []
    for relative_path in tracked_files:
        path = PROJECT_ROOT / relative_path
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except (UnicodeDecodeError, PermissionError):
            continue
        if jwt_pattern.search(text):
            offenders.append(relative_path)
    assert offenders == [], f"Possible real access token pattern found in tracked file(s): {offenders}"
