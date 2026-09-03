"""Phase 40 -- end-to-end system validation: Market Data -> Intelligence
-> Research -> Decision -> Position Sizing -> Prediction -> Persistence
-> Evaluation -> Learning -> Dashboard, validated as ONE coherent chain
rather than per-stage unit tests (which already exist extensively --
tests/test_shadow_run.py in particular already proves per-symbol
scan/research/decide/predict isolation and persistence in depth; this
file deliberately does not re-prove that).

What this file adds that did not exist before:
  1. Failure injection at the EVALUATE stage -- a real gap this phase
     found: unlike the decide-stage per-symbol loop, neither `evaluate`
     nor shadow-run's own evaluate phase isolated one prediction's
     unexpected failure from the rest of the batch. Fixed in main.py
     (both run_evaluate_command and run_shadow_run_command); tested here.
  2. A genuine restart-across-process-boundary test: shadow-run writes
     to disk, then completely separate `evaluate` and `learn` CLI
     invocations (fresh store objects, no in-memory carryover) pick up
     from ONLY the persisted database files.
  3. A full-stack read-path check: the dashboard's /intelligence/<symbol>
     page renders the exact decision/prediction a real shadow-run wrote,
     proving the write path (shadow-run) and read path (dashboard) are
     wired to the same stores.

No real network, Ollama, or cache-file write anywhere in this file --
reuses the exact fake-provider fixture tests/test_shadow_run.py and
tests/test_scheduler_runner.py already established.
"""

from datetime import datetime, timedelta, timezone

import pytest

from main import parse_args, run_evaluate_command, run_learn_command, run_shadow_run_command
from market.data_provider import OHLCV, MarketDataError, OHLCVBar

_START = datetime(2023, 1, 2)


def _uptrend_bars(n: int = 100, start: float = 100.0, step: float = 2.0) -> list[OHLCVBar]:
    bars = []
    for i in range(n):
        close = start + step * i
        bars.append(OHLCVBar(
            timestamp=_START + timedelta(days=i), open=close, high=close * 1.001, low=close * 0.999,
            close=close, volume=100_000.0,
        ))
    return bars


class _FakeMarketDataProvider:
    def __init__(self, bars: list[OHLCVBar]):
        self._bars = bars

    def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
        return OHLCV(symbol=symbol, interval=interval, bars=self._bars)


class _FakeNewsProvider:
    def fetch_news(self, symbol, *, limit=10):
        return []


class _FakeSectorProvider:
    def fetch_sector_info(self, symbol):
        from research.models import SectorInfo

        return SectorInfo(symbol=symbol, sector=None, industry=None, as_of=datetime.now(timezone.utc))


@pytest.fixture(autouse=True)
def _wire_fakes(monkeypatch):
    import backtesting.cache as cache_module
    import market.data_provider as market_data_provider_module
    import research.news as research_news_module
    import research.sector as research_sector_module
    from market.context import MarketContext

    bars = _uptrend_bars()
    fake_provider = _FakeMarketDataProvider(bars)

    monkeypatch.setattr(market_data_provider_module, "get_market_data_provider", lambda: fake_provider)
    monkeypatch.setattr(cache_module, "CachedMarketDataProvider", lambda inner: inner)
    monkeypatch.setattr(research_news_module, "YahooNewsProvider", _FakeNewsProvider)
    monkeypatch.setattr(research_sector_module, "YahooSectorInfoProvider", _FakeSectorProvider)

    entry_as_of = _START + timedelta(days=80)
    monkeypatch.setattr(
        "market.context.get_market_context",
        lambda symbol, **kwargs: MarketContext(symbol=symbol, as_of=entry_as_of, price=260.0, atr_14=5.0),
    )
    yield


def _db_args(tmp_path):
    return [
        "--scanner-db", str(tmp_path / "scanner.db"), "--research-db", str(tmp_path / "research.db"),
        "--decision-db", str(tmp_path / "decisions.db"), "--predictions-db", str(tmp_path / "predictions.db"),
    ]


# --- failure injection: evaluate stage ----------------------------------------


def test_standalone_evaluate_isolates_one_predictions_unexpected_failure_from_the_rest(tmp_path, capsys, monkeypatch):
    """Regression for the gap this phase found: an unexpected exception
    (NOT the MarketDataError evaluate_prediction already handles
    internally) evaluating one prediction must not abort the batch."""
    run_shadow_run_command(parse_args(["shadow-run", "--symbols", "AAPL,MSFT", "--benchmark", "", "--skip-evaluate", *_db_args(tmp_path)]))
    capsys.readouterr()

    import predictions.tracker as tracker_module

    real_evaluate = tracker_module.evaluate_prediction
    call_count = {"n": 0}

    def _flaky_evaluate(prediction, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise ValueError("simulated unexpected bug evaluating this one prediction")
        return real_evaluate(prediction, **kwargs)

    monkeypatch.setattr("predictions.tracker.evaluate_prediction", _flaky_evaluate)

    run_evaluate_command(parse_args(["evaluate", "--db", str(tmp_path / "predictions.db")]))
    output = capsys.readouterr().out

    assert "FAILED" in output
    assert "simulated unexpected bug" in output
    assert "Summary (latest evaluation per prediction):" in output  # the batch completed, not aborted
    assert "Total:             1" in output  # only the SECOND (non-failing) prediction produced a saved evaluation

    from predictions.store import PredictionStore

    store = PredictionStore(tmp_path / "predictions.db")
    evaluations = {e.prediction_id: e for e in store.list_all_evaluations()}
    store.close()
    assert len(evaluations) == 1  # only the SECOND (non-failing) prediction got a saved evaluation


def test_shadow_run_own_evaluate_phase_isolates_one_predictions_unexpected_failure(tmp_path, capsys, monkeypatch):
    """Same fix, exercised through shadow-run's own [3/4] evaluate phase
    (a separate code path from the standalone `evaluate` command)."""
    run_shadow_run_command(parse_args(["shadow-run", "--symbols", "AAPL,MSFT", "--benchmark", "", "--skip-evaluate", *_db_args(tmp_path)]))
    capsys.readouterr()

    import predictions.tracker as tracker_module

    real_evaluate = tracker_module.evaluate_prediction

    def _flaky_evaluate(prediction, **kwargs):
        if prediction.symbol == "AAPL":
            raise RuntimeError("simulated unexpected bug for AAPL specifically")
        return real_evaluate(prediction, **kwargs)

    monkeypatch.setattr("predictions.tracker.evaluate_prediction", _flaky_evaluate)

    run_shadow_run_command(parse_args(["shadow-run", "--symbols", "AAPL,MSFT", "--benchmark", "", *_db_args(tmp_path)]))
    output = capsys.readouterr().out

    assert "AAPL" in output and "FAILED" in output and "simulated unexpected bug for AAPL" in output
    assert "[4/4] Learning summary" in output  # reached the end, not aborted
    assert "Total:             1" in output  # only MSFT's evaluation was recorded this pass


# --- restart across a process boundary ----------------------------------------


def test_full_pipeline_survives_a_restart_between_every_stage(tmp_path, capsys):
    """The genuinely new check this phase adds: shadow-run writes to
    disk, then `evaluate` and `learn` run as COMPLETELY SEPARATE CLI
    invocations against fresh store objects -- simulating the process
    being restarted between each stage (e.g. `schedule loop` itself
    being killed and relaunched, or an operator running each command by
    hand on different days) rather than one continuous in-memory run."""
    db_args = _db_args(tmp_path)

    run_shadow_run_command(parse_args(["shadow-run", "--symbols", "AAPL", "--benchmark", "", "--skip-evaluate", *db_args]))
    first_output = capsys.readouterr().out
    assert "prediction recorded" in first_output

    # "Restart" #1: a fresh `evaluate` invocation, no shared state with the run above.
    run_evaluate_command(parse_args(["evaluate", "--db", str(tmp_path / "predictions.db")]))
    evaluate_output = capsys.readouterr().out
    assert "Predictions needing evaluation: 1" in evaluate_output
    assert "TARGET_HIT" in evaluate_output or "STOP_HIT" in evaluate_output or "ACTIVE" in evaluate_output or "EXPIRED" in evaluate_output

    # "Restart" #2: a fresh `learn` invocation, reading only what's on disk.
    run_learn_command(parse_args([
        "learn", "--predictions-db", str(tmp_path / "predictions.db"), "--decision-db", str(tmp_path / "decisions.db"),
    ]))
    learn_output = capsys.readouterr().out
    assert "LEARNING REPORT" in learn_output or "Strategy performance" in learn_output or "config" in learn_output.lower()

    # The full chain is provably intact end to end, purely from disk.
    from decision_engine.store import DecisionStore
    from predictions.store import PredictionStore

    decision_store = DecisionStore(tmp_path / "decisions.db")
    decision = decision_store.latest_decision_for_symbol("AAPL")
    decision_store.close()
    assert decision is not None and decision.label.value == "BUY"

    prediction_store = PredictionStore(tmp_path / "predictions.db")
    predictions = prediction_store.list_predictions()
    evaluations = prediction_store.list_all_evaluations()
    prediction_store.close()
    assert len(predictions) == 1
    assert len(evaluations) == 1
    assert evaluations[0].prediction_id == predictions[0].prediction_id


# --- full-stack: write path (shadow-run) feeds the read path (dashboard) -----


def test_dashboard_renders_exactly_what_a_real_shadow_run_persisted(tmp_path, monkeypatch):
    from starlette.testclient import TestClient

    import dashboard.intelligence as intelligence_module

    db_args = _db_args(tmp_path)
    monkeypatch.setattr(intelligence_module, "SCANNER_DB_PATH", tmp_path / "scanner.db")
    monkeypatch.setattr(intelligence_module, "RESEARCH_DB_PATH", tmp_path / "research.db")
    monkeypatch.setattr(intelligence_module, "DECISIONS_DB_PATH", tmp_path / "decisions.db")
    monkeypatch.setattr(intelligence_module, "PREDICTIONS_DB_PATH", tmp_path / "predictions.db")

    run_shadow_run_command(parse_args(["shadow-run", "--symbols", "AAPL", "--benchmark", "", "--skip-evaluate", *db_args]))

    from decision_engine.store import DecisionStore

    decision_store = DecisionStore(tmp_path / "decisions.db")
    decision = decision_store.latest_decision_for_symbol("AAPL")
    decision_store.close()
    assert decision is not None

    from dashboard.app import app

    client = TestClient(app)
    response = client.get("/intelligence/AAPL")
    assert response.status_code == 200
    body = response.text
    assert "AAPL" in body
    assert "No decision recorded" not in body  # proves a real decision was found, not the empty-state fallback
    assert decision.config_version in body
    assert "tag-long'>BUY" in body
