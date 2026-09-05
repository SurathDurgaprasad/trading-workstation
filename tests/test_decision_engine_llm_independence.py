"""Strategy science, Phase 10 (LLM contribution audit). This session's
own audit traced every path that reaches RiskEngine.evaluate() or a
real PaperTradingEngine/backtester fill and found two: (1)
TrendMomentumBaseline, already proven LLM-free by
tests/test_backtest_llm_independence.py, and (2) a SECOND, separate
bridge -- decision_engine.rules.classify()'s deterministic label feeds
risk/sizing.py's build_signal_for_buy()/size_decision(), which can
reach a real (opt-in, --paper-execute) PaperTradingEngine.submit_signal()
call. That second bridge was NOT covered by the existing AST-import-scan
test (which only checks backtesting/strategy/risk, not decision_engine
-- a mixed package where decision_engine/engine.py's own
narrate_decision() intentionally DOES call the LLM, so the whole
package cannot be scanned uniformly). This file closes that specific
gap for the two files that actually determine Decision.label:
decision_engine/rules.py (classify) and decision_engine/confidence.py
(compute_confidence) -- deliberately NOT decision_engine/engine.py,
which legitimately imports the LLM layer (deferred, inside
narrate_decision()) for narration only.

Also closes the audit's other named gap: no test previously asserted,
by name, that schemas.decision.TradingDecision (the agents/graph
pipeline's own LLM-produced action) never reaches the execution
packages at all.
"""

import ast
import inspect
from pathlib import Path

from decision_engine.rules import classify

FORBIDDEN_TOP_LEVEL_MODULES = {"agents", "llm", "graph", "langgraph", "langchain_core", "langchain_ollama", "ollama", "rag"}

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DETERMINISTIC_DECISION_ENGINE_FILES = ["decision_engine/rules.py", "decision_engine/confidence.py"]
_EXECUTION_PACKAGES = ["backtesting", "strategy", "risk", "paper"]


def _imported_top_level_modules(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                modules.add(node.module.split(".")[0])
    return modules


def test_decision_engine_classify_and_confidence_never_import_the_llm_layer():
    # classify() determines Decision.label -- the value that flows into
    # risk/sizing.py's real Signal-construction bridge. It must stay as
    # LLM-free as strategy/baseline.py's own generate_signal(), even
    # though it lives in a package (decision_engine) whose OTHER module
    # (engine.py's narrate_decision) legitimately imports the LLM layer.
    violations = {}
    for relative_path in _DETERMINISTIC_DECISION_ENGINE_FILES:
        py_file = _REPO_ROOT / relative_path
        found = _imported_top_level_modules(py_file) & FORBIDDEN_TOP_LEVEL_MODULES
        if found:
            violations[relative_path] = found

    assert not violations, f"decision_engine's deterministic label/confidence code must not import the LLM/agent layer, but found: {violations}"


def test_decision_engine_narration_module_does_still_import_the_llm_layer():
    # Sanity check for the test above: decision_engine/engine.py's
    # narrate_decision() DOES import agents.analyst (deferred, inside
    # the function). If this ever stopped being true, the "mixed
    # package" reasoning behind scanning only rules.py/confidence.py
    # (not the whole decision_engine package) would need revisiting.
    engine_file = _REPO_ROOT / "decision_engine" / "engine.py"
    found = _imported_top_level_modules(engine_file) & FORBIDDEN_TOP_LEVEL_MODULES
    assert found, "decision_engine/engine.py was expected to import the LLM layer (for narration) -- if this changed, reconsider scanning the whole package."


def test_classify_signature_has_no_llm_or_narrative_derived_parameter():
    # Locks in the structural guarantee the audit flagged as fragile:
    # classify() currently cannot be influenced by LLM output only
    # because its signature doesn't accept anything narrative/LLM-
    # shaped. If a future change added such a parameter, this test
    # would need to be touched -- forcing a deliberate decision rather
    # than a silent regression.
    forbidden_terms = ("narrative", "llm", "ai_", "explanation", "summary")
    params = set(inspect.signature(classify).parameters.keys())
    for param in params:
        for term in forbidden_terms:
            assert term not in param.lower(), f"classify()'s parameter '{param}' looks LLM/narrative-derived -- verify it cannot carry LLM output into the deterministic label."
    assert params == {"symbol", "candidate", "risk_context", "config"}


def test_execution_packages_never_import_the_agents_graph_pipeline_schema():
    # schemas.decision.TradingDecision is the agents/graph pipeline's
    # own LLM-produced action (BUY/WAIT/SELL/...). Explicit, named
    # proof that none of the packages capable of opening a real (paper)
    # position ever import it at all -- there is no code path for it to
    # reach a Signal, RiskDecision, or PaperOrder if the module that
    # defines it is never even imported.
    violations = {}
    for package in _EXECUTION_PACKAGES:
        package_dir = _REPO_ROOT / package
        for py_file in package_dir.rglob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == "schemas.decision":
                    violations[str(py_file.relative_to(_REPO_ROOT))] = [a.name for a in node.names]
                if isinstance(node, ast.ImportFrom) and node.module == "schemas" and any(a.name == "decision" for a in node.names):
                    violations[str(py_file.relative_to(_REPO_ROOT))] = ["decision"]

    assert not violations, f"Execution packages must never import schemas.decision (TradingDecision), but found: {violations}"
