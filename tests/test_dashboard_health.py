"""The /health dashboard route -- final-product-hardening, the mission's
own explicit requirement that the dashboard and CLI consume ONE shared
health source (core.health.collect_system_health), not two
independently-drifting implementations. Same TestClient pattern as
tests/test_dashboard_intelligence.py."""

import pytest
from starlette.testclient import TestClient


@pytest.fixture(autouse=True)
def _isolated_intelligence_dbs(monkeypatch, tmp_path):
    import dashboard.intelligence as intelligence_module

    monkeypatch.setattr(intelligence_module, "SCANNER_DB_PATH", tmp_path / "scanner.db")
    monkeypatch.setattr(intelligence_module, "RESEARCH_DB_PATH", tmp_path / "research.db")
    monkeypatch.setattr(intelligence_module, "DECISIONS_DB_PATH", tmp_path / "decisions.db")
    monkeypatch.setattr(intelligence_module, "PREDICTIONS_DB_PATH", tmp_path / "predictions.db")
    monkeypatch.setattr(intelligence_module, "PAPER_DB_PATH", tmp_path / "paper.db")
    monkeypatch.setattr(intelligence_module, "SCHEDULER_DB_PATH", tmp_path / "scheduler_runs.db")
    monkeypatch.setattr(intelligence_module, "STATE_DB_PATH", tmp_path / "live_state.db")
    yield tmp_path


@pytest.fixture
def client():
    from dashboard.app import app

    return TestClient(app)


def test_health_route_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_health_route_shows_overall_status(client):
    response = client.get("/health")
    assert "SYSTEM HEALTH" in response.text
    assert "Overall status:" in response.text


def test_health_route_lists_every_component(client):
    response = client.get("/health")
    for component in ("application", "database", "disk", "risk", "kill_switch", "scheduler"):
        assert component in response.text


def test_health_route_reflects_an_active_kill_switch(client, tmp_path):
    from live.state_store import LiveStateStore

    state_path = tmp_path / "live_state.db"
    store = LiveStateStore(state_path)
    store.activate_kill_switch(reason="dashboard health test")
    store.close()

    response = client.get("/health")

    assert "SAFE_STOP" in response.text


def test_health_route_reflects_a_corrupted_database(client, tmp_path):
    corrupt = tmp_path / "paper.db"
    corrupt.write_bytes(b"not a real sqlite database")

    response = client.get("/health")

    assert "FAILED" in response.text


def test_health_route_makes_no_market_data_fetch(client, monkeypatch):
    """Same "no side-effecting fetch on page load" discipline every other
    dashboard route follows -- confirms nothing in the /health path calls
    a market-data provider."""
    def _boom(*args, **kwargs):
        raise AssertionError("must not fetch market data on a /health page load")

    monkeypatch.setattr("market.data_provider.YahooFinanceProvider.fetch_ohlcv", _boom)

    response = client.get("/health")

    assert response.status_code == 200
