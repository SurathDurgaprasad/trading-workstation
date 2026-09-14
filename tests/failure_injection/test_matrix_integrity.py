"""Autonomous hardening cycle 7 -- the failure matrix's own regression
test. This is what makes failure_matrix.yaml an EXECUTABLE artifact
rather than a second prose document that can silently go stale the way
FINAL_FAILURE_MODE_ANALYSIS.md could (and did, until cycle 5 caught it
by hand): every row's `test` field must name a REAL, currently-
collectible pytest function. A renamed test, a deleted test, or a typo
in the matrix fails THIS test on the very next regression run -- no
separate manual audit step required.

Deliberately does not re-EXECUTE every referenced test (they already run
as part of the normal `pytest tests/` invocation this file is itself
part of -- re-running them here would be redundant and slower). This
file only proves each row's claim is still backed by something real.
"""
import importlib
import importlib.util
from pathlib import Path

import pytest
import yaml

_MATRIX_PATH = Path(__file__).parent / "failure_matrix.yaml"
_REPO_ROOT = Path(__file__).parent.parent.parent

_REQUIRED_FIELDS = {"id", "component", "failure", "injection_method", "expected", "test", "evidence_grade"}
_REQUIRED_EXPECTED_FIELDS = {"detection", "safe_response", "recovery", "safety_invariant"}
_VALID_EVIDENCE_GRADES = {"A", "B", "C", "D", "E"}


def _load_matrix() -> list[dict]:
    return yaml.safe_load(_MATRIX_PATH.read_text(encoding="utf-8"))


def test_matrix_file_exists_and_parses():
    assert _MATRIX_PATH.exists()
    matrix = _load_matrix()
    assert isinstance(matrix, list)
    assert len(matrix) > 0


def test_matrix_has_no_duplicate_ids():
    matrix = _load_matrix()
    ids = [row["id"] for row in matrix]
    assert len(ids) == len(set(ids)), f"duplicate id(s) in failure_matrix.yaml: {[i for i in ids if ids.count(i) > 1]}"


@pytest.mark.parametrize("row", _load_matrix(), ids=lambda row: row["id"])
def test_every_row_has_the_required_fields(row):
    missing = _REQUIRED_FIELDS - row.keys()
    assert not missing, f"{row.get('id', '?')} is missing required field(s): {missing}"
    missing_expected = _REQUIRED_EXPECTED_FIELDS - row["expected"].keys()
    assert not missing_expected, f"{row['id']}'s 'expected' block is missing: {missing_expected}"
    assert row["evidence_grade"] in _VALID_EVIDENCE_GRADES, f"{row['id']} has an invalid evidence_grade: {row['evidence_grade']!r}"


@pytest.mark.parametrize("row", _load_matrix(), ids=lambda row: row["id"])
def test_every_row_test_reference_is_real_and_collectible(row):
    """The core anti-drift check: `test` must be "path/to/file.py::func",
    the file must exist under the repo root, and the named function must
    actually be defined in it -- not merely a plausible-looking string."""
    test_ref = row["test"]
    assert "::" in test_ref, f"{row['id']}'s test reference {test_ref!r} is not in 'path::function' form"
    file_part, func_name = test_ref.split("::", 1)
    file_path = _REPO_ROOT / file_part
    assert file_path.exists(), f"{row['id']} references a test file that does not exist: {file_part}"

    spec = importlib.util.spec_from_file_location(f"_matrix_check_{row['id']}", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # noqa: this is the whole point -- prove the module actually imports

    assert hasattr(module, func_name), f"{row['id']} references {func_name!r}, which does not exist in {file_part}"
    assert callable(getattr(module, func_name)), f"{row['id']}'s {func_name!r} in {file_part} is not callable"
