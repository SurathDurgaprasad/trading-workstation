"""NSE PREDICTION ENGINE mission: CLI wiring tests for `evaluate-forecasts`,
same posture as tests/test_daily_report.py -- no real network, a fake
provider serves a deterministic series for every symbol.
"""
from datetime import datetime, timedelta, timezone

import pytest

from decision_engine.direction import DirectionalAssessment, DirectionLabel
from main import parse_args, run_evaluate_forecasts_command
from market.data_provider import OHLCV, OHLCVBar
from predictions.direction_forecast import DirectionForecastRecord
from predictions.direction_forecast_store import DirectionForecastStore

_AS_OF = datetime(2024, 1, 10)


def _bars_from(as_of: datetime, closes: list[float]) -> list[OHLCVBar]:
    bars = []
    for i, close in enumerate(closes):
        ts = as_of + timedelta(days=i + 1)
        bars.append(OHLCVBar(timestamp=ts, open=close, high=close * 1.001, low=close * 0.999, close=close, volume=100_000.0))
    return bars


class _FakeMarketDataProvider:
    def __init__(self, bars: list[OHLCVBar]):
        self._bars = bars

    def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
        return OHLCV(symbol=symbol, interval=interval, bars=self._bars)


@pytest.fixture(autouse=True)
def _wire_fake_provider(monkeypatch):
    import backtesting.cache as cache_module
    import market.data_provider as market_data_provider_module

    fake_provider = _FakeMarketDataProvider(_bars_from(_AS_OF, [101.0, 102.0, 110.0]))
    monkeypatch.setattr(market_data_provider_module, "get_market_data_provider", lambda: fake_provider)
    monkeypatch.setattr(cache_module, "CachedMarketDataProvider", lambda inner: inner)


def _seed_forecast(db_path, *, label=DirectionLabel.UP, horizon_bars=3) -> str:
    store = DirectionForecastStore(db_path)
    assessment = DirectionalAssessment(
        symbol="RELIANCE.NS", label=label, confidence=0.75,
        bullish_evidence=("Trend (+1.00)",), bearish_evidence=(), contradicting_evidence=(), unavailable_factors=(),
    )
    forecast = DirectionForecastRecord.from_assessment(assessment, as_of=_AS_OF, reference_price=100.0, horizon_bars=horizon_bars)
    store.save_forecast(forecast)
    store.close()
    return forecast.forecast_id


def test_evaluate_forecasts_resolves_a_real_up_forecast_correctly(tmp_path, capsys):
    db_path = tmp_path / "forecasts.db"
    _seed_forecast(db_path, label=DirectionLabel.UP, horizon_bars=3)

    args = parse_args(["evaluate-forecasts", "--db", str(db_path)])
    run_evaluate_forecasts_command(args)

    output = capsys.readouterr().out
    assert "DIRECTIONAL FORECAST EVALUATION" in output
    assert "CORRECT" in output
    assert "Accuracy:         100.0%" in output


def test_evaluate_forecasts_summarizes_no_edge_separately(tmp_path, capsys):
    db_path = tmp_path / "forecasts.db"
    _seed_forecast(db_path, label=DirectionLabel.NO_EDGE, horizon_bars=3)

    args = parse_args(["evaluate-forecasts", "--db", str(db_path)])
    run_evaluate_forecasts_command(args)

    output = capsys.readouterr().out
    assert "N/A (NO_EDGE)" in output
    assert "NO_EDGE resolved: 1" in output
    assert "Accuracy:         n/a" in output
