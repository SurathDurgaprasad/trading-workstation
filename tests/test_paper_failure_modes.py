"""Spec Phase 6 §24: mandatory failure-mode coverage not already exercised
elsewhere (duplicate signal / stop / target / same-bar ambiguity /
end-of-data / transaction rollback all live in test_paper_engine.py and
test_paper_store.py — this file covers the remaining ones explicitly)."""

from datetime import datetime

import pytest

from paper.engine import Bar, PaperTradingEngine
from paper.models import JournalOutcome
from paper.store import PaperStore
from risk.config import RiskConfig
from risk.engine import RiskEngine
from strategy.signal import ReasonCode, Side, Signal


def _signal(**overrides) -> Signal:
    base = dict(
        symbol="TEST", generated_at=datetime(2026, 1, 1), side=Side.LONG,
        reference_price=100.0, stop_price=95.0, target_price=110.0, risk_reward=2.0,
        strategy_name="unit-test", reason_codes=[ReasonCode.TREND_CONFIRMED],
    )
    base.update(overrides)
    return Signal(**base)


# --- Ollama / AI is optional, never a dependency of paper execution ---------


def test_paper_trading_works_with_no_llm_module_imported_anywhere():
    """Spec §18: paper execution must work with Ollama completely
    unavailable. Proven the same way Phase 3's backtester/Phase 5's MCP
    server were: the paper package structurally never imports the LLM
    layer, so there is nothing to fail even if Ollama is not running."""
    import sys

    forbidden_already_imported = {
        name for name in sys.modules if name.split(".")[0] in {"langgraph", "langchain_ollama", "ollama"}
    }

    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    engine.submit_signal(_signal())
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=115.0, low=100.0, close=110.0))

    newly_imported = {
        name for name in sys.modules if name.split(".")[0] in {"langgraph", "langchain_ollama", "ollama"}
    } - forbidden_already_imported
    assert not newly_imported


def test_ai_explanation_is_a_separate_optional_step_paper_trading_does_not_call_it():
    """The paper/ package doesn't import agents.signal_explainer at all —
    explanation is something a CALLER does afterward, with the journaled
    Signal/RiskDecision, via the already-tested agents.signal_explainer
    module. Structural proof: paper/engine.py's own source never mentions it."""
    import inspect

    import paper.engine

    source = inspect.getsource(paper.engine)
    assert "signal_explainer" not in source
    assert "agents" not in source


# --- invalid inputs fail closed, not with a crash ----------------------------


def test_submit_signal_with_invalid_stop_is_rejected_not_a_crash():
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    journal = engine.submit_signal(_signal(stop_price=105.0))  # stop above entry, invalid for LONG
    assert journal.outcome == JournalOutcome.REJECTED


def test_submit_signal_with_insufficient_capital_is_rejected():
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, risk_engine=RiskEngine(RiskConfig(risk_per_trade_pct=50.0, max_exposure_pct=100.0)), initial_capital=1.0)
    journal = engine.submit_signal(_signal(reference_price=100.0, stop_price=95.0))
    assert journal.outcome == JournalOutcome.REJECTED
    from risk.veto import VetoReason
    decision = store.get_risk_decision(journal.risk_decision_id)
    assert VetoReason.INSUFFICIENT_CAPITAL in decision.veto_reasons or VetoReason.ZERO_POSITION_SIZE in decision.veto_reasons


# --- corrupted / missing journal state --------------------------------------


def test_get_journal_entry_for_an_unknown_signal_returns_none_not_an_error():
    store = PaperStore(":memory:")
    assert store.find_journal_entry_by_signal_id("this-signal-was-never-submitted") is None


def test_the_database_itself_refuses_to_orphan_a_position_from_its_signal():
    """First line of defense: SQLite's own FOREIGN KEY constraint (enabled
    in PaperStore.__init__) refuses to let the signals table lose a row
    that a paper_order still references — the corruption this test set out
    to simulate is actually impossible through normal deletion, which is a
    stronger guarantee than catching it after the fact."""
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    engine.submit_signal(_signal())

    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        store._conn.execute("DELETE FROM signals")


def test_position_referencing_a_missing_signal_fails_loudly_not_silently():
    """Second line of defense, in case FK enforcement were ever bypassed
    (e.g. PRAGMA foreign_keys=OFF): the engine's own code asserts rather
    than silently treating a position as something it isn't (spec §11's
    "fail loudly, do not silently repair")."""
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    engine.submit_signal(_signal())
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=101.5, low=100.5, close=101.0))

    # Force the corruption past FK enforcement, to test the application-level
    # safety net specifically (defense in depth, not relying on SQLite alone).
    store._conn.execute("PRAGMA foreign_keys = OFF")
    store._conn.execute("DELETE FROM signals")

    with pytest.raises(AssertionError):
        engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 3), open=101.0, high=120.0, low=100.0, close=115.0))


def test_empty_store_reconciles_cleanly():
    from paper.reconciliation import reconcile

    store = PaperStore(":memory:")
    PaperTradingEngine(store, initial_capital=100_000.0)  # just initializes the account row
    report = reconcile(store)
    assert report.ok, report.issues
