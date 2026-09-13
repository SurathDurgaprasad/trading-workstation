from datetime import datetime, timezone

from decision_engine.direction import DirectionalAssessment, DirectionLabel
from predictions.direction_forecast import DirectionForecastEvaluation, DirectionForecastRecord
from predictions.direction_forecast_store import DirectionForecastStore

_AS_OF = datetime(2024, 1, 10)


def _assessment(label=DirectionLabel.UP, symbol="RELIANCE.NS") -> DirectionalAssessment:
    return DirectionalAssessment(
        symbol=symbol, label=label, confidence=0.7,
        bullish_evidence=("Trend (+1.00)",), bearish_evidence=(), contradicting_evidence=(), unavailable_factors=(),
    )


def _forecast(symbol="RELIANCE.NS", as_of=_AS_OF, label=DirectionLabel.UP) -> DirectionForecastRecord:
    return DirectionForecastRecord.from_assessment(_assessment(label, symbol), as_of=as_of, reference_price=100.0, horizon_bars=5)


def test_save_and_get_round_trips(tmp_path):
    store = DirectionForecastStore(tmp_path / "forecasts.db")
    forecast = _forecast()
    store.save_forecast(forecast)

    fetched = store.get_forecast(forecast.forecast_id)
    assert fetched == forecast
    store.close()


def test_get_forecast_returns_none_for_unknown_id(tmp_path):
    store = DirectionForecastStore(tmp_path / "forecasts.db")
    assert store.get_forecast("does-not-exist") is None
    store.close()


def test_has_forecast_for_bar_detects_duplicate(tmp_path):
    store = DirectionForecastStore(tmp_path / "forecasts.db")
    forecast = _forecast()
    store.save_forecast(forecast)

    assert store.has_forecast_for_bar("RELIANCE.NS", _AS_OF) is True
    assert store.has_forecast_for_bar("RELIANCE.NS", datetime(2024, 2, 1)) is False
    assert store.has_forecast_for_bar("TCS.NS", _AS_OF) is False
    store.close()


def test_list_forecasts_needing_evaluation_excludes_resolved(tmp_path):
    store = DirectionForecastStore(tmp_path / "forecasts.db")
    resolved = _forecast(symbol="RESOLVED.NS")
    unresolved = _forecast(symbol="UNRESOLVED.NS")
    store.save_forecast(resolved)
    store.save_forecast(unresolved)

    store.save_evaluation(DirectionForecastEvaluation(
        evaluation_id=DirectionForecastEvaluation.new_id(), forecast_id=resolved.forecast_id,
        evaluated_at=datetime.now(timezone.utc), resolved=True, bars_observed=5, actual_return=0.02, correct=True, detail="resolved",
    ))
    store.save_evaluation(DirectionForecastEvaluation(
        evaluation_id=DirectionForecastEvaluation.new_id(), forecast_id=unresolved.forecast_id,
        evaluated_at=datetime.now(timezone.utc), resolved=False, bars_observed=1, actual_return=None, correct=None, detail="still open",
    ))

    needing = store.list_forecasts_needing_evaluation()
    assert {f.forecast_id for f in needing} == {unresolved.forecast_id}
    store.close()


def test_latest_evaluation_for_forecast_returns_the_newest(tmp_path):
    store = DirectionForecastStore(tmp_path / "forecasts.db")
    forecast = _forecast()
    store.save_forecast(forecast)

    older = DirectionForecastEvaluation(
        evaluation_id=DirectionForecastEvaluation.new_id(), forecast_id=forecast.forecast_id,
        evaluated_at=datetime(2024, 1, 11, tzinfo=timezone.utc), resolved=False, bars_observed=1, actual_return=None, correct=None, detail="early",
    )
    newer = DirectionForecastEvaluation(
        evaluation_id=DirectionForecastEvaluation.new_id(), forecast_id=forecast.forecast_id,
        evaluated_at=datetime(2024, 1, 15, tzinfo=timezone.utc), resolved=True, bars_observed=5, actual_return=0.03, correct=True, detail="resolved",
    )
    store.save_evaluation(older)
    store.save_evaluation(newer)

    latest = store.latest_evaluation_for_forecast(forecast.forecast_id)
    assert latest.evaluation_id == newer.evaluation_id
    store.close()


def test_store_persists_across_reconnect(tmp_path):
    db_path = tmp_path / "forecasts.db"
    store = DirectionForecastStore(db_path)
    store.save_forecast(_forecast())
    store.close()

    reopened = DirectionForecastStore(db_path)
    assert len(reopened.list_forecasts()) == 1
    reopened.close()


# --- final-product-hardening: DB-level duplicate prevention -----------------


def test_new_database_has_duplicate_prevention_enforced_at_db_level(tmp_path):
    store = DirectionForecastStore(tmp_path / "forecasts.db")
    assert store.duplicate_prevention_enforced_at_db_level is True
    store.close()


def test_saving_a_second_forecast_for_the_same_symbol_and_as_of_raises():
    import pytest

    from predictions.errors import DuplicateForecastError

    store = DirectionForecastStore(":memory:")
    store.save_forecast(_forecast(as_of=_AS_OF))

    with pytest.raises(DuplicateForecastError):
        store.save_forecast(_forecast(as_of=_AS_OF))

    store.close()


def test_migration_backfills_as_of_for_rows_written_before_the_column_existed(tmp_path):
    import sqlite3

    db_path = tmp_path / "forecasts.db"
    raw = sqlite3.connect(str(db_path))
    raw.execute("CREATE TABLE forecasts (forecast_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, created_at TEXT NOT NULL, data_json TEXT NOT NULL)")
    old_row = _forecast()
    raw.execute(
        "INSERT INTO forecasts (forecast_id, symbol, created_at, data_json) VALUES (?,?,?,?)",
        (old_row.forecast_id, old_row.symbol, old_row.created_at.isoformat(), old_row.model_dump_json()),
    )
    raw.commit()
    raw.close()

    migrated = DirectionForecastStore(db_path)

    assert migrated.duplicate_prevention_enforced_at_db_level is True
    row = migrated._conn.execute("SELECT as_of FROM forecasts WHERE forecast_id = ?", (old_row.forecast_id,)).fetchone()
    assert row[0] == _AS_OF.isoformat()
    migrated.close()


def test_integrity_check_reports_ok_for_a_healthy_database(tmp_path):
    store = DirectionForecastStore(tmp_path / "forecasts.db")
    assert store.integrity_check() == "ok"
    store.close()


def test_db_size_bytes_reflects_a_real_file(tmp_path):
    store = DirectionForecastStore(tmp_path / "forecasts.db")
    assert store.db_size_bytes() > 0
    store.close()


def test_schema_version_is_set_on_a_fresh_database(tmp_path):
    store = DirectionForecastStore(tmp_path / "forecasts.db")
    assert store.schema_version() == DirectionForecastStore.CURRENT_SCHEMA_VERSION
    store.close()
