from datetime import datetime, timezone

from decision_engine.models import Decision, DecisionLabel, RiskContext
from decision_engine.store import DecisionStore
from market_intelligence.models import CandidateScore


def _candidate() -> CandidateScore:
    return CandidateScore(
        symbol="AAPL", as_of=datetime(2024, 6, 1), last_close=190.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.1, trend_score=1.0, momentum_score=0.5, breakout_score=0.01,
        relative_strength_score=0.02, sector_strength_score=None, composite_score=1.5,
        explanation=["fake"],
    )


def _decision(decision_id: str = "dec-1", symbol: str = "AAPL", as_of: datetime | None = None) -> Decision:
    as_of = as_of or datetime(2024, 6, 1, tzinfo=timezone.utc)
    return Decision(
        decision_id=decision_id, symbol=symbol, as_of=as_of, label=DecisionLabel.BUY,
        rationale=["all factors agree"], config_version="abc123", scanner_evidence=_candidate(),
        research_evidence=None, market_context=None, risk_context=RiskContext.unknown(),
        narrative="A synthesized explanation.", narrative_unavailable_reason=None,
    )


def test_save_and_get_round_trips_through_pydantic_validation(tmp_path):
    store = DecisionStore(tmp_path / "decisions.db")
    decision = _decision()
    store.save_decision(decision)

    fetched = store.get_decision(decision.decision_id)
    assert fetched == decision
    store.close()


def test_get_decision_returns_none_for_unknown_id(tmp_path):
    store = DecisionStore(tmp_path / "decisions.db")
    assert store.get_decision("does-not-exist") is None
    store.close()


def test_latest_decision_for_symbol_returns_the_most_recent(tmp_path):
    store = DecisionStore(tmp_path / "decisions.db")
    older = _decision(decision_id="dec-old", as_of=datetime(2024, 1, 1, tzinfo=timezone.utc))
    newer = _decision(decision_id="dec-new", as_of=datetime(2024, 6, 1, tzinfo=timezone.utc))
    store.save_decision(older)
    store.save_decision(newer)

    assert store.latest_decision_for_symbol("AAPL").decision_id == "dec-new"
    store.close()


def test_list_decisions_for_symbol_orders_newest_first_and_respects_limit(tmp_path):
    store = DecisionStore(tmp_path / "decisions.db")
    for i in range(5):
        store.save_decision(_decision(decision_id=f"dec-{i}", as_of=datetime(2024, 1, 1 + i, tzinfo=timezone.utc)))

    decisions = store.list_decisions_for_symbol("AAPL", limit=3)
    assert [d.decision_id for d in decisions] == ["dec-4", "dec-3", "dec-2"]
    store.close()


def test_store_persists_across_reconnect(tmp_path):
    db_path = tmp_path / "decisions.db"
    store = DecisionStore(db_path)
    store.save_decision(_decision())
    store.close()

    reopened = DecisionStore(db_path)
    assert reopened.get_decision("dec-1") is not None
    reopened.close()


def test_decisions_are_immutable_history_not_updated_in_place(tmp_path):
    """No update_decision method exists at all -- a decision, once
    persisted, is never rewritten. Saving a second decision for the same
    symbol creates a new row, never replaces the first."""
    store = DecisionStore(tmp_path / "decisions.db")
    store.save_decision(_decision(decision_id="dec-1", as_of=datetime(2024, 1, 1, tzinfo=timezone.utc)))
    store.save_decision(_decision(decision_id="dec-2", as_of=datetime(2024, 1, 2, tzinfo=timezone.utc)))

    assert not hasattr(store, "update_decision")
    assert len(store.list_decisions_for_symbol("AAPL")) == 2
    store.close()
