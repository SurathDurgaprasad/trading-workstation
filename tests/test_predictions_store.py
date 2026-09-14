import sqlite3
from datetime import datetime, timezone

import pytest

from decision_engine.models import DecisionLabel
from predictions.errors import DuplicatePredictionError
from predictions.models import PredictionEvaluation, PredictionOutcomeState, PredictionRecord
from predictions.store import PredictionStore


def _prediction(
    prediction_id: str = "p1", symbol: str = "AAPL", created_at: datetime | None = None, entry_time: datetime | None = None
) -> PredictionRecord:
    return PredictionRecord(
        prediction_id=prediction_id, decision_id="dec-1", symbol=symbol,
        created_at=created_at or datetime(2024, 1, 1, tzinfo=timezone.utc), label=DecisionLabel.BUY,
        entry_price=100.0, stop_price=95.0, target_price=110.0, entry_time=entry_time or datetime(2024, 1, 2),
        horizon_bars=20, interval="1d",
    )


def _evaluation(
    prediction_id: str = "p1", evaluation_id: str = "e1", outcome=PredictionOutcomeState.ACTIVE,
    evaluated_at: datetime | None = None,
) -> PredictionEvaluation:
    return PredictionEvaluation(
        evaluation_id=evaluation_id, prediction_id=prediction_id, evaluated_at=evaluated_at or datetime(2024, 1, 3, tzinfo=timezone.utc),
        outcome=outcome, bars_observed=1, exit_time=None, exit_price=None, actual_return=None,
        max_favorable_excursion=0.0, max_adverse_excursion=0.0, detail="test",
    )


def test_save_and_get_prediction_round_trips(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    prediction = _prediction()
    store.save_prediction(prediction)

    assert store.get_prediction("p1") == prediction
    store.close()


def test_get_prediction_returns_none_for_unknown_id(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    assert store.get_prediction("does-not-exist") is None
    store.close()


def test_save_and_get_prediction_round_trips_a_real_risk_decision(tmp_path):
    """Mission auditability requirement: the persisted trade plan
    (quantity/capital/risk amount) must survive the ACTUAL sqlite
    store round trip, not just an in-memory JSON round trip."""
    from decision_engine.models import Decision, RiskContext
    from market.context import MarketContext
    from market_intelligence.models import CandidateScore
    from risk.account import new_account
    from risk.sizing import size_decision

    candidate = CandidateScore(
        symbol="AAPL", as_of=datetime(2024, 1, 1), last_close=100.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.1, trend_score=1.0, momentum_score=0.5, breakout_score=0.01,
        relative_strength_score=0.02, sector_strength_score=None, composite_score=1.5, explanation=["fake"],
    )
    decision = Decision(
        decision_id="dec-1", symbol="AAPL", as_of=datetime(2024, 1, 1, tzinfo=timezone.utc), label=DecisionLabel.BUY,
        rationale=["fake"], config_version="cfg1", scanner_evidence=candidate, research_evidence=None,
        market_context=None, risk_context=RiskContext.unknown(), narrative=None, narrative_unavailable_reason=None,
    )
    market_context = MarketContext(symbol="AAPL", as_of=datetime(2024, 1, 1), price=100.0, atr_14=2.5)
    risk_decision = size_decision(decision, market_context=market_context, account=new_account(20_000.0))

    prediction = PredictionRecord(
        prediction_id="p-sized", decision_id="dec-1", symbol="AAPL", created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        label=DecisionLabel.BUY, entry_price=100.0, stop_price=95.0, target_price=110.0, entry_time=datetime(2024, 1, 2),
        horizon_bars=20, interval="1d", risk_decision=risk_decision,
    )

    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(prediction)
    fetched = store.get_prediction("p-sized")
    store.close()

    assert fetched is not None
    assert fetched.risk_decision is not None
    assert fetched.risk_decision.account_equity == 20_000.0
    assert fetched.risk_decision.position_size.quantity == risk_decision.position_size.quantity
    assert fetched == prediction


def test_save_and_list_evaluations_round_trip(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(_prediction())
    store.save_evaluation(_evaluation())

    evaluations = store.list_evaluations_for_prediction("p1")
    assert len(evaluations) == 1
    assert evaluations[0].evaluation_id == "e1"
    store.close()


def test_latest_evaluation_for_prediction_returns_the_most_recent(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(_prediction())
    store.save_evaluation(_evaluation("p1", "e-old", PredictionOutcomeState.ACTIVE, datetime(2024, 1, 3, tzinfo=timezone.utc)))
    store.save_evaluation(_evaluation("p1", "e-new", PredictionOutcomeState.TARGET_HIT, datetime(2024, 1, 10, tzinfo=timezone.utc)))

    latest = store.latest_evaluation_for_prediction("p1")
    assert latest.evaluation_id == "e-new"
    assert latest.outcome == PredictionOutcomeState.TARGET_HIT
    store.close()


def test_latest_evaluation_for_prediction_returns_none_when_never_evaluated(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(_prediction())
    assert store.latest_evaluation_for_prediction("p1") is None
    store.close()


def test_list_predictions_needing_evaluation_includes_never_evaluated_and_active(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(_prediction("p1", entry_time=datetime(2024, 1, 2)))  # never evaluated
    store.save_prediction(_prediction("p2", entry_time=datetime(2024, 1, 3)))
    store.save_evaluation(_evaluation("p2", "e2", PredictionOutcomeState.ACTIVE))
    store.save_prediction(_prediction("p3", entry_time=datetime(2024, 1, 4)))
    store.save_evaluation(_evaluation("p3", "e3", PredictionOutcomeState.TARGET_HIT))

    pending = store.list_predictions_needing_evaluation()
    pending_ids = {p.prediction_id for p in pending}

    assert pending_ids == {"p1", "p2"}
    assert "p3" not in pending_ids  # resolved -- done, never re-queued
    store.close()


def test_list_predictions_needing_evaluation_excludes_expired_and_insufficient_data(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(_prediction("p1", entry_time=datetime(2024, 1, 2)))
    store.save_evaluation(_evaluation("p1", "e1", PredictionOutcomeState.EXPIRED))
    store.save_prediction(_prediction("p2", entry_time=datetime(2024, 1, 3)))
    store.save_evaluation(_evaluation("p2", "e2", PredictionOutcomeState.INSUFFICIENT_DATA))

    assert store.list_predictions_needing_evaluation() == []
    store.close()


def test_list_all_evaluations_returns_every_row_including_superseded_ones(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(_prediction())
    store.save_evaluation(_evaluation("p1", "e-old", PredictionOutcomeState.ACTIVE, datetime(2024, 1, 3, tzinfo=timezone.utc)))
    store.save_evaluation(_evaluation("p1", "e-new", PredictionOutcomeState.TARGET_HIT, datetime(2024, 1, 10, tzinfo=timezone.utc)))

    all_evaluations = store.list_all_evaluations()
    assert len(all_evaluations) == 2
    store.close()


def test_no_update_methods_exist_predictions_and_evaluations_are_append_only(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    assert not hasattr(store, "update_prediction")
    assert not hasattr(store, "update_evaluation")
    store.close()


def test_list_predictions_for_symbol_filters_and_orders_most_recent_first(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(_prediction("p1", symbol="AAPL", created_at=datetime(2024, 1, 1, tzinfo=timezone.utc), entry_time=datetime(2024, 1, 1)))
    store.save_prediction(_prediction("p2", symbol="MSFT", created_at=datetime(2024, 1, 2, tzinfo=timezone.utc), entry_time=datetime(2024, 1, 2)))
    store.save_prediction(_prediction("p3", symbol="AAPL", created_at=datetime(2024, 1, 3, tzinfo=timezone.utc), entry_time=datetime(2024, 1, 3)))

    result = store.list_predictions_for_symbol("AAPL")

    store.close()
    assert [p.prediction_id for p in result] == ["p3", "p1"]  # most recent first, MSFT excluded


def test_list_predictions_for_symbol_normalizes_case(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(_prediction("p1", symbol="AAPL"))
    result = store.list_predictions_for_symbol("aapl")
    store.close()
    assert len(result) == 1


def test_list_predictions_for_symbol_empty_for_unknown_symbol(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(_prediction("p1", symbol="AAPL"))
    result = store.list_predictions_for_symbol("ZZZZ")
    store.close()
    assert result == []


def test_list_predictions_for_symbol_respects_limit(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    for i in range(5):
        store.save_prediction(_prediction(
            f"p{i}", symbol="AAPL",
            created_at=datetime(2024, 1, 1 + i, tzinfo=timezone.utc), entry_time=datetime(2024, 1, 1 + i),
        ))
    result = store.list_predictions_for_symbol("AAPL", limit=2)
    store.close()
    assert len(result) == 2


def test_has_prediction_for_entry_true_after_saving_one(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    entry_time = datetime(2024, 6, 1)
    store.save_prediction(_prediction("p1", symbol="AAPL", created_at=entry_time).model_copy(update={"entry_time": entry_time}))
    result = store.has_prediction_for_entry("AAPL", entry_time)
    store.close()
    assert result is True


def test_has_prediction_for_entry_false_for_a_different_bar(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(_prediction("p1", symbol="AAPL").model_copy(update={"entry_time": datetime(2024, 6, 1)}))
    result = store.has_prediction_for_entry("AAPL", datetime(2024, 6, 2))
    store.close()
    assert result is False


def test_has_prediction_for_entry_false_for_a_different_symbol(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    entry_time = datetime(2024, 6, 1)
    store.save_prediction(_prediction("p1", symbol="AAPL").model_copy(update={"entry_time": entry_time}))
    result = store.has_prediction_for_entry("MSFT", entry_time)
    store.close()
    assert result is False


def test_has_prediction_for_entry_false_when_nothing_recorded(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    result = store.has_prediction_for_entry("AAPL", datetime(2024, 6, 1))
    store.close()
    assert result is False


def test_store_persists_across_reconnect(tmp_path):
    db_path = tmp_path / "predictions.db"
    store = PredictionStore(db_path)
    store.save_prediction(_prediction())
    store.save_evaluation(_evaluation())
    store.close()

    reopened = PredictionStore(db_path)
    assert reopened.get_prediction("p1") is not None
    assert reopened.latest_evaluation_for_prediction("p1") is not None
    reopened.close()


# --- Real-time strategy validation mission, Phase J: crash resilience for
# the live-path prediction-recording write itself (live/prediction_
# recorder.py's own tests already prove the higher-level DuplicatePrediction
# Error/failure-isolation behavior around save_prediction -- these two
# tests prove the actual SQLite-level durability guarantee that behavior
# depends on, using the SAME real database engine, not a mock). ------------


def test_an_uncommitted_write_leaves_no_partial_row_simulating_a_crash_mid_write(tmp_path):
    """Simulates a process crash BETWEEN save_prediction's own BEGIN and
    COMMIT (see PredictionStore.transaction's own BEGIN/COMMIT/ROLLBACK):
    manually BEGIN + INSERT via the raw connection, then abandon it
    without ever calling COMMIT or ROLLBACK -- exactly what a real SIGKILL
    mid-transaction leaves behind. A restart (a fresh PredictionStore
    connection to the same file) must see NOTHING, not a corrupted or
    half-written row -- SQLite's own durability guarantee, verified
    against the real database engine this project actually uses, not
    assumed."""
    db_path = tmp_path / "predictions.db"
    store = PredictionStore(db_path)
    crashed_prediction = _prediction(prediction_id="crashed-p1")
    store._conn.execute("BEGIN")
    store._conn.execute(
        "INSERT INTO predictions (prediction_id, decision_id, symbol, created_at, entry_time, data_json) VALUES (?,?,?,?,?,?)",
        (
            crashed_prediction.prediction_id, crashed_prediction.decision_id, crashed_prediction.symbol,
            crashed_prediction.created_at.isoformat(), crashed_prediction.entry_time.isoformat(), crashed_prediction.model_dump_json(),
        ),
    )
    # Deliberately NO commit/rollback/close -- simulates the process
    # disappearing mid-transaction. Drop the reference to release the
    # connection object without any orderly shutdown.
    del store

    restarted = PredictionStore(db_path)
    assert restarted.get_prediction("crashed-p1") is None
    assert restarted.list_predictions() == []
    restarted.close()


def test_a_committed_prediction_survives_an_abrupt_connection_loss(tmp_path):
    """The other half of the same guarantee: a prediction that DID
    complete save_prediction's own commit must survive even if the
    connection is then lost abruptly (never explicitly .close()'d) --
    proving durability does not depend on an orderly shutdown sequence,
    exactly the real-world shape of "the process was recording a
    prediction and then the machine lost power/was killed one instant
    later."""
    db_path = tmp_path / "predictions.db"
    store = PredictionStore(db_path)
    store.save_prediction(_prediction(prediction_id="survivor-p1"))
    # No store.close() -- simulate the process disappearing immediately
    # after the write it cared about completed, with no chance to run
    # any cleanup.
    del store

    restarted = PredictionStore(db_path)
    recovered = restarted.get_prediction("survivor-p1")
    assert recovered is not None
    assert recovered.symbol == "AAPL"
    restarted.close()


# --- final-product-hardening: DB-level duplicate prevention ---------------


def test_new_database_has_duplicate_prevention_enforced_at_db_level(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    assert store.duplicate_prevention_enforced_at_db_level is True
    store.close()


def test_saving_a_second_prediction_for_the_same_symbol_and_entry_time_raises():
    """The real gap this migration closes: has_prediction_for_entry alone
    is a non-atomic check-then-insert -- two concurrent callers could both
    pass it before either inserts. The DB-level UNIQUE(symbol, entry_time)
    constraint is what actually prevents the double-insert."""
    store = PredictionStore(":memory:")
    entry_time = datetime(2024, 6, 1)
    store.save_prediction(_prediction("p1", symbol="AAPL", entry_time=entry_time))

    with pytest.raises(DuplicatePredictionError):
        store.save_prediction(_prediction("p2", symbol="AAPL", entry_time=entry_time))

    store.close()


def test_a_different_entry_time_for_the_same_symbol_is_not_a_duplicate():
    store = PredictionStore(":memory:")
    store.save_prediction(_prediction("p1", symbol="AAPL", entry_time=datetime(2024, 6, 1)))
    store.save_prediction(_prediction("p2", symbol="AAPL", entry_time=datetime(2024, 6, 2)))  # must not raise

    store.close()


def test_migration_backfills_entry_time_for_rows_written_before_the_column_existed(tmp_path):
    """Simulates a real, already-deployed predictions.db created before
    this migration existed: entry_time only ever lived inside data_json,
    never as its own column. Confirms a fresh PredictionStore connecting
    to that exact on-disk shape backfills it from each row's own
    data_json (not a guess) and the unique index becomes active."""
    db_path = tmp_path / "predictions.db"
    raw = sqlite3.connect(str(db_path))
    raw.execute(
        "CREATE TABLE predictions (prediction_id TEXT PRIMARY KEY, decision_id TEXT NOT NULL, "
        "symbol TEXT NOT NULL, created_at TEXT NOT NULL, data_json TEXT NOT NULL)"
    )
    old_row = _prediction("p1", symbol="AAPL", entry_time=datetime(2024, 6, 1))
    raw.execute(
        "INSERT INTO predictions (prediction_id, decision_id, symbol, created_at, data_json) VALUES (?,?,?,?,?)",
        (old_row.prediction_id, old_row.decision_id, old_row.symbol, old_row.created_at.isoformat(), old_row.model_dump_json()),
    )
    raw.commit()
    raw.close()

    migrated = PredictionStore(db_path)

    assert migrated.duplicate_prevention_enforced_at_db_level is True
    row = migrated._conn.execute("SELECT entry_time FROM predictions WHERE prediction_id = 'p1'").fetchone()
    assert row[0] == "2024-06-01T00:00:00"
    migrated.close()


def test_migration_disables_the_unique_index_gracefully_when_preexisting_duplicates_exist(tmp_path):
    """The scenario core.sqlite_util.try_create_unique_index exists for:
    a real database that, under the OLD app-level-only duplicate
    prevention, already accumulated two rows for the same symbol+
    entry_time BEFORE this migration ever ran against it. The migration
    must not crash startup or delete data -- it reports the constraint
    as inactive instead. Simulated with raw sqlite3, deliberately never
    going through PredictionStore first, since going through it even
    once would already have created (and thereby enforce) the index."""
    db_path = tmp_path / "predictions.db"
    raw = sqlite3.connect(str(db_path))
    raw.execute(
        "CREATE TABLE predictions (prediction_id TEXT PRIMARY KEY, decision_id TEXT NOT NULL, "
        "symbol TEXT NOT NULL, created_at TEXT NOT NULL, entry_time TEXT, data_json TEXT NOT NULL)"
    )
    for prediction_id in ("p1", "p2-legacy-dup"):
        row = _prediction(prediction_id, symbol="AAPL", entry_time=datetime(2024, 6, 1))
        raw.execute(
            "INSERT INTO predictions (prediction_id, decision_id, symbol, created_at, entry_time, data_json) VALUES (?,?,?,?,?,?)",
            (row.prediction_id, row.decision_id, row.symbol, row.created_at.isoformat(), row.entry_time.isoformat(), row.model_dump_json()),
        )
    raw.commit()
    raw.close()

    store = PredictionStore(db_path)

    assert store.duplicate_prevention_enforced_at_db_level is False
    assert len(store.list_predictions_for_symbol("AAPL")) == 2  # neither pre-existing row was deleted
    store.close()


def test_integrity_check_reports_ok_for_a_healthy_database(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    assert store.integrity_check() == "ok"
    store.close()


def test_db_size_bytes_reflects_a_real_file(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    assert store.db_size_bytes() > 0
    store.close()


def test_schema_version_is_set_on_a_fresh_database(tmp_path):
    store = PredictionStore(tmp_path / "predictions.db")
    assert store.schema_version() == PredictionStore.CURRENT_SCHEMA_VERSION
    store.close()


def test_schema_version_upgrades_a_preexisting_pre_versioning_database(tmp_path):
    """A real, already-deployed predictions.db created before schema-
    version tracking existed has version 0 (PRAGMA user_version's own
    default, never having been set) -- opening it with current code
    must stamp it with the current version, same as the entry_time
    backfill migration already does for its own column."""
    db_path = tmp_path / "predictions.db"
    raw = sqlite3.connect(str(db_path))
    raw.execute(
        "CREATE TABLE predictions (prediction_id TEXT PRIMARY KEY, decision_id TEXT NOT NULL, "
        "symbol TEXT NOT NULL, created_at TEXT NOT NULL, data_json TEXT NOT NULL)"
    )
    assert raw.execute("PRAGMA user_version").fetchone()[0] == 0
    raw.commit()
    raw.close()

    migrated = PredictionStore(db_path)

    assert migrated.schema_version() == PredictionStore.CURRENT_SCHEMA_VERSION
    migrated.close()


# --- autonomous hardening cycle: malformed data_json on read ----------------


def test_a_malformed_prediction_row_raises_a_clear_error_not_a_raw_pydantic_traceback():
    from core.sqlite_util import MalformedRowError

    store = PredictionStore(":memory:")
    store._conn.execute(
        "INSERT INTO predictions (prediction_id, decision_id, symbol, created_at, entry_time, data_json) VALUES (?,?,?,?,?,?)",
        ("p1", "dec-1", "AAPL", "2024-01-01T00:00:00+00:00", "2024-01-02T00:00:00", '{"prediction_id": "p1"}'),
    )

    with pytest.raises(MalformedRowError) as exc_info:
        store.get_prediction("p1")

    assert "PredictionRecord" in str(exc_info.value)
    assert "p1" in str(exc_info.value)
