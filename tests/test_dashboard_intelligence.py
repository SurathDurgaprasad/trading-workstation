"""Phase 26 -- the new /intelligence dashboard route. Uses Starlette's
TestClient (httpx-backed, no real sockets), matching tests/test_dashboard.py's
own established pattern exactly. Every fixture writes real Phase 18-25
store objects to tmp_path databases and points dashboard.intelligence's
module-level path constants at them via monkeypatch -- no real network,
no real Ollama call, no real market-data fetch anywhere in this file
(dashboard.intelligence's own functions never call fetch_ohlcv/
invoke_structured/check_ollama_availability at all, so there is nothing
to fake).
"""

from datetime import datetime, timezone

import pytest
from starlette.testclient import TestClient

from decision_engine.models import Decision, DecisionLabel, RiskContext
from decision_engine.store import DecisionStore
from market_intelligence.models import CandidateScore, ScanReport
from market_intelligence.store import ScanHistoryStore
from predictions.models import PredictionEvaluation, PredictionOutcomeState, PredictionRecord
from predictions.store import PredictionStore


@pytest.fixture(autouse=True)
def _isolated_intelligence_dbs(monkeypatch, tmp_path):
    import dashboard.intelligence as intelligence_module

    monkeypatch.setattr(intelligence_module, "SCANNER_DB_PATH", tmp_path / "scanner.db")
    monkeypatch.setattr(intelligence_module, "RESEARCH_DB_PATH", tmp_path / "research.db")
    monkeypatch.setattr(intelligence_module, "DECISIONS_DB_PATH", tmp_path / "decisions.db")
    monkeypatch.setattr(intelligence_module, "PREDICTIONS_DB_PATH", tmp_path / "predictions.db")
    yield tmp_path


@pytest.fixture
def client():
    from dashboard.app import app

    return TestClient(app)


def _candidate(symbol: str = "AAPL", composite: float = 1.5) -> CandidateScore:
    return CandidateScore(
        symbol=symbol, as_of=datetime(2024, 6, 1), last_close=190.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.1, trend_score=1.0, momentum_score=0.5, breakout_score=0.01,
        relative_strength_score=0.02, sector_strength_score=None, composite_score=composite,
        explanation=["fake"],
    )


def _save_scan(db_path, *candidates: CandidateScore):
    store = ScanHistoryStore(db_path)
    store.save_report(ScanReport(
        scan_id="scan-1", as_of=datetime(2024, 6, 1, tzinfo=timezone.utc), universe_mode="watchlist",
        universe_size=len(candidates), benchmark_symbol=None, benchmark_unavailable_reason=None,
        config_version="cfg1", candidates=list(candidates), excluded=[],
    ))
    store.close()


def _save_decision(db_path, symbol: str, label: DecisionLabel, candidate: CandidateScore | None, market_context=None):
    store = DecisionStore(db_path)
    store.save_decision(Decision(
        decision_id=f"dec-{symbol}", symbol=symbol, as_of=datetime(2024, 6, 1, tzinfo=timezone.utc), label=label,
        rationale=["fake rationale"], config_version="cfg1", scanner_evidence=candidate, research_evidence=None,
        market_context=market_context, risk_context=RiskContext.unknown(), narrative=None, narrative_unavailable_reason=None,
    ))
    store.close()


def _save_prediction_and_evaluation(predictions_db, symbol: str, decision_id: str, outcome: PredictionOutcomeState, actual_return: float | None):
    store = PredictionStore(predictions_db)
    store.save_prediction(PredictionRecord(
        prediction_id=f"pred-{symbol}", decision_id=decision_id, symbol=symbol, created_at=datetime.now(timezone.utc),
        label=DecisionLabel.BUY, entry_price=100.0, stop_price=95.0, target_price=110.0, entry_time=datetime(2024, 6, 1),
        horizon_bars=20, interval="1d",
    ))
    store.save_evaluation(PredictionEvaluation(
        evaluation_id=f"eval-{symbol}", prediction_id=f"pred-{symbol}", evaluated_at=datetime.now(timezone.utc),
        outcome=outcome, bars_observed=5, exit_time=None, exit_price=None, actual_return=actual_return,
        max_favorable_excursion=0.1, max_adverse_excursion=0.02, detail="test",
    ))
    store.close()


# --- empty state --------------------------------------------------------------


def test_intelligence_page_empty_state_when_nothing_persisted(client):
    response = client.get("/intelligence")
    assert response.status_code == 200
    assert "No scan has been run yet" in response.text
    assert "No evaluated predictions yet" in response.text
    assert "READ-ONLY SNAPSHOT" in response.text


# --- populated scan + decisions -------------------------------------------------


def test_intelligence_page_shows_latest_scan_and_decision(client, _isolated_intelligence_dbs):
    tmp_path = _isolated_intelligence_dbs
    candidate = _candidate("AAPL", composite=1.75)
    _save_scan(tmp_path / "scanner.db", candidate)
    _save_decision(tmp_path / "decisions.db", "AAPL", DecisionLabel.BUY, candidate)

    response = client.get("/intelligence")

    assert "AAPL" in response.text
    assert "+1.75" in response.text
    assert "BUY" in response.text
    assert "cfg1" in response.text


def test_intelligence_page_shows_data_source_and_status_when_present(client, _isolated_intelligence_dbs):
    """Phase 32: a decision whose market_context was populated (e.g. by
    shadow-run) must surface its data_source/data_status on the page --
    the honest "is this live or historical" answer the roadmap's own
    safety rule asks for."""
    from market.context import MarketContext

    tmp_path = _isolated_intelligence_dbs
    candidate = _candidate("AAPL", composite=1.75)
    _save_scan(tmp_path / "scanner.db", candidate)
    context = MarketContext(symbol="AAPL", as_of=datetime(2024, 6, 1), price=190.0, data_source="DHAN", data_status="LIVE")
    _save_decision(tmp_path / "decisions.db", "AAPL", DecisionLabel.BUY, candidate, market_context=context)

    response = client.get("/intelligence")

    assert "DHAN / LIVE" in response.text


def test_intelligence_page_shows_n_a_when_market_context_absent(client, _isolated_intelligence_dbs):
    """A decision with no market_context at all (e.g. from standalone
    `decide`, which does not build one) must show an honest "n/a" --
    never a fabricated source/status."""
    tmp_path = _isolated_intelligence_dbs
    candidate = _candidate("AAPL", composite=1.75)
    _save_scan(tmp_path / "scanner.db", candidate)
    _save_decision(tmp_path / "decisions.db", "AAPL", DecisionLabel.BUY, candidate)  # market_context=None

    response = client.get("/intelligence")

    assert "n/a" in response.text


def test_intelligence_page_handles_a_candidate_with_no_decision_gracefully(client, _isolated_intelligence_dbs):
    tmp_path = _isolated_intelligence_dbs
    _save_scan(tmp_path / "scanner.db", _candidate("MSFT"))
    # deliberately no decision saved for MSFT

    response = client.get("/intelligence")

    assert response.status_code == 200
    assert "MSFT" in response.text
    assert "no decision recorded" in response.text


# --- learning snapshot -----------------------------------------------------------


def test_intelligence_page_shows_learning_snapshot(client, _isolated_intelligence_dbs):
    tmp_path = _isolated_intelligence_dbs
    _save_decision(tmp_path / "decisions.db", "AAPL", DecisionLabel.BUY, _candidate("AAPL"))
    _save_prediction_and_evaluation(tmp_path / "predictions.db", "AAPL", "dec-AAPL", PredictionOutcomeState.TARGET_HIT, 0.10)

    response = client.get("/intelligence")

    assert "1 evaluated prediction(s) considered." in response.text
    assert "cfg1" in response.text
    assert "100.0%" in response.text  # win rate: 1/1 resolved, all wins


# --- HTML escaping -----------------------------------------------------------------


def test_intelligence_page_escapes_symbol_names(client, _isolated_intelligence_dbs):
    tmp_path = _isolated_intelligence_dbs
    malicious_symbol = "<script>alert(1)</script>"
    _save_scan(tmp_path / "scanner.db", _candidate(malicious_symbol))

    response = client.get("/intelligence")

    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text
