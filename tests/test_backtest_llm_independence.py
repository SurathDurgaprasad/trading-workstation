"""Spec §18/§21: the backtester must work with Ollama OFF, Claude OFF,
LangGraph OFF, Internet OFF (once data is cached). The strongest, cheapest
proof of that is structural: neither package can import the LLM/agent/graph
layers at all — there is nothing there to fail at runtime."""

import ast
from pathlib import Path

FORBIDDEN_TOP_LEVEL_MODULES = {"agents", "llm", "graph", "langgraph", "langchain_core", "langchain_ollama", "ollama", "rag"}

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CHECKED_PACKAGES = ["backtesting", "strategy", "risk"]


def _imported_top_level_modules(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:  # ignore relative imports
                modules.add(node.module.split(".")[0])
    return modules


def test_backtesting_and_strategy_packages_never_import_the_llm_layer():
    violations = {}
    for package in _CHECKED_PACKAGES:
        package_dir = _REPO_ROOT / package
        for py_file in package_dir.rglob("*.py"):
            found = _imported_top_level_modules(py_file) & FORBIDDEN_TOP_LEVEL_MODULES
            if found:
                violations[str(py_file.relative_to(_REPO_ROOT))] = found

    assert not violations, (
        f"Deterministic backtest/strategy code must not import the LLM/agent layer, "
        f"but found: {violations}"
    )


def test_market_indicators_and_data_provider_also_stay_llm_free():
    # market/ is shared by both the AI analyst (Phase 2) and the backtester
    # (Phase 3) — it must not have grown an LLM dependency either.
    for py_file in (_REPO_ROOT / "market").glob("*.py"):
        found = _imported_top_level_modules(py_file) & FORBIDDEN_TOP_LEVEL_MODULES
        assert not found, f"{py_file} imports {found}"
