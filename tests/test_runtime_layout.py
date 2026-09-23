"""Real-time strategy validation mission, multi-symbol hardening pass --
tests for live/runtime_layout.py: deterministic per-symbol runtime
directories and the cross-symbol-contamination guard.
"""
import pytest

from live.runtime_layout import (
    CrossSymbolContaminationError,
    ensure_symbol_runtime_dirs,
    symbol_runtime_paths,
    verify_no_cross_symbol_contamination,
)


# --- symbol_runtime_paths ----------------------------------------------------


def test_derives_the_exact_documented_layout(tmp_path):
    paths = symbol_runtime_paths(tmp_path, "RELIANCE.NS")
    assert paths.root == tmp_path / "RELIANCE.NS"
    assert paths.paper_db == tmp_path / "RELIANCE.NS" / "paper.db"
    assert paths.state_db == tmp_path / "RELIANCE.NS" / "state.db"
    assert paths.predictions_db == tmp_path / "RELIANCE.NS" / "predictions.db"
    assert paths.logs_dir == tmp_path / "RELIANCE.NS" / "logs"


def test_normalizes_symbol_case_and_whitespace(tmp_path):
    lower = symbol_runtime_paths(tmp_path, "reliance.ns")
    padded = symbol_runtime_paths(tmp_path, "  RELIANCE.NS  ")
    canonical = symbol_runtime_paths(tmp_path, "RELIANCE.NS")
    assert lower.root == canonical.root
    assert padded.root == canonical.root
    assert lower.symbol == "RELIANCE.NS"


def test_different_symbols_never_collide(tmp_path):
    a = symbol_runtime_paths(tmp_path, "RELIANCE.NS")
    b = symbol_runtime_paths(tmp_path, "TCS.NS")
    assert a.root != b.root
    assert a.paper_db != b.paper_db
    assert {a.paper_db, a.state_db, a.predictions_db} & {b.paper_db, b.state_db, b.predictions_db} == set()


def test_empty_symbol_raises():
    with pytest.raises(ValueError):
        symbol_runtime_paths("runtime", "")
    with pytest.raises(ValueError):
        symbol_runtime_paths("runtime", "   ")


@pytest.mark.parametrize("hostile_symbol", ["../../etc/passwd", "..\\..\\windows\\system32", "AAPL/../../secret", "A/B", "A\\B"])
def test_a_symbol_containing_a_path_separator_or_parent_reference_is_rejected(hostile_symbol):
    """Defensive hardening (2026-09-22 continuous red-team pass): every
    current caller sources `symbol` from a trusted, operator-supplied
    place -- not independently exploitable today -- but symbol_runtime_
    paths must never resolve outside the given runtime_dir tree, so this
    is rejected explicitly rather than left to accidentally work."""
    with pytest.raises(ValueError, match="path separator"):
        symbol_runtime_paths("runtime", hostile_symbol)


def test_an_ordinary_dotted_symbol_still_works(tmp_path):
    """Regression guard: the new check must not reject legitimate NSE-
    suffixed symbols like 'RELIANCE.NS', which contain a dot but no path
    separator or '..' sequence."""
    paths = symbol_runtime_paths(str(tmp_path), "RELIANCE.NS")
    assert paths.symbol == "RELIANCE.NS"
    assert paths.root == tmp_path / "RELIANCE.NS"


# --- ensure_symbol_runtime_dirs ----------------------------------------------


def test_ensure_dirs_creates_root_and_logs(tmp_path):
    paths = symbol_runtime_paths(tmp_path, "RELIANCE.NS")
    assert not paths.root.exists()
    ensure_symbol_runtime_dirs(paths)
    assert paths.root.is_dir()
    assert paths.logs_dir.is_dir()


def test_ensure_dirs_is_idempotent_and_never_disturbs_existing_files(tmp_path):
    paths = symbol_runtime_paths(tmp_path, "RELIANCE.NS")
    ensure_symbol_runtime_dirs(paths)
    paths.paper_db.write_text("not really a db, just proving it survives")
    ensure_symbol_runtime_dirs(paths)  # a second call, e.g. a restart
    assert paths.paper_db.read_text() == "not really a db, just proving it survives"


# --- verify_no_cross_symbol_contamination ------------------------------------


def test_passes_silently_when_store_is_empty():
    verify_no_cross_symbol_contamination(expected_symbol="RELIANCE.NS", observed_symbols=set())


def test_passes_silently_when_store_only_has_the_expected_symbol():
    verify_no_cross_symbol_contamination(expected_symbol="RELIANCE.NS", observed_symbols={"RELIANCE.NS"})


def test_passes_when_expected_symbol_case_differs_from_observed():
    verify_no_cross_symbol_contamination(expected_symbol="reliance.ns", observed_symbols={"RELIANCE.NS"})


def test_raises_when_a_different_symbol_is_found():
    with pytest.raises(CrossSymbolContaminationError, match="TCS.NS"):
        verify_no_cross_symbol_contamination(expected_symbol="RELIANCE.NS", observed_symbols={"TCS.NS"})


def test_raises_when_the_expected_symbol_is_mixed_with_another():
    """The real, dangerous case: a store that has BOTH the correct
    symbol's data AND some contamination from another symbol -- must
    still be rejected, not waved through because SOME of the data is
    right."""
    with pytest.raises(CrossSymbolContaminationError, match="TCS.NS"):
        verify_no_cross_symbol_contamination(
            expected_symbol="RELIANCE.NS", observed_symbols={"RELIANCE.NS", "TCS.NS"},
        )


def test_error_message_names_every_unexpected_symbol():
    with pytest.raises(CrossSymbolContaminationError) as excinfo:
        verify_no_cross_symbol_contamination(
            expected_symbol="RELIANCE.NS", observed_symbols={"TCS.NS", "HDFCBANK.NS"},
        )
    assert "TCS.NS" in str(excinfo.value)
    assert "HDFCBANK.NS" in str(excinfo.value)
