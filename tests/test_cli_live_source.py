"""Phase 31 -- `--live-source dhan` wiring on `size`/`predict`. No real
Dhan connection anywhere in this file: credentials, the instrument map
download, and build_dhan_adapter are all faked."""

from datetime import datetime

import pytest

from decision_engine.models import Decision, DecisionLabel, RiskContext
from decision_engine.store import DecisionStore
from live.dhan.config import DhanCredentialsMissingError
from main import _build_live_snapshot_provider, parse_args, run_predict_command, run_size_command
from market.context import MarketContext
from market_intelligence.models import CandidateScore


def _seed_buy_decision(decision_db) -> None:
    store = DecisionStore(decision_db)
    candidate = CandidateScore(
        symbol="AAPL", as_of=datetime(2024, 6, 1), last_close=190.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.1, trend_score=1.0, momentum_score=0.5, breakout_score=0.01,
        relative_strength_score=0.02, sector_strength_score=None, composite_score=1.5,
        explanation=["fake"],
    )
    store.save_decision(Decision(
        decision_id="dec-1", symbol="AAPL", as_of=datetime(2024, 6, 1, 12, 0, 0), label=DecisionLabel.BUY,
        rationale=["all factors agree"], config_version="cfg1", scanner_evidence=candidate, research_evidence=None,
        market_context=None, risk_context=RiskContext.unknown(), narrative=None, narrative_unavailable_reason=None,
    ))
    store.close()


def test_size_live_source_defaults_to_none():
    args = parse_args(["size", "--symbol", "AAPL"])
    assert args.live_source is None


def test_predict_live_source_defaults_to_none():
    args = parse_args(["predict", "--symbol", "AAPL"])
    assert args.live_source is None


def test_size_live_source_rejects_an_unsupported_choice():
    with pytest.raises(SystemExit):
        parse_args(["size", "--symbol", "AAPL", "--live-source", "nse"])


def test_build_live_snapshot_provider_returns_none_when_not_requested():
    args = parse_args(["size", "--symbol", "AAPL"])
    assert _build_live_snapshot_provider(args) is None


def test_build_live_snapshot_provider_raises_a_clear_error_with_no_credentials(monkeypatch):
    monkeypatch.delenv("DHAN_CLIENT_ID", raising=False)
    monkeypatch.delenv("DHAN_ACCESS_TOKEN", raising=False)
    args = parse_args(["size", "--symbol", "AAPL", "--live-source", "dhan"])
    with pytest.raises(DhanCredentialsMissingError):
        _build_live_snapshot_provider(args)


def test_build_live_snapshot_provider_constructs_a_dhan_adapter_when_configured(monkeypatch):
    import live.dhan.config as dhan_config_module
    import live.dhan.instruments as dhan_instruments_module
    import market_data.adapters.dhan as dhan_adapter_module

    fake_credentials = object()
    fake_instrument_map = object()
    fake_adapter = object()

    monkeypatch.setattr(dhan_config_module, "load_dhan_credentials", lambda: fake_credentials)
    monkeypatch.setattr(dhan_instruments_module.DhanInstrumentMap, "download", classmethod(lambda cls, **kw: fake_instrument_map))
    captured = {}

    def _fake_build(*, credentials, instrument_map, interval, **kwargs):
        captured["credentials"] = credentials
        captured["instrument_map"] = instrument_map
        captured["interval"] = interval
        return fake_adapter

    monkeypatch.setattr(dhan_adapter_module, "build_dhan_adapter", _fake_build)

    args = parse_args(["size", "--symbol", "AAPL", "--live-source", "dhan"])
    result = _build_live_snapshot_provider(args)

    assert result is fake_adapter
    assert captured["credentials"] is fake_credentials
    assert captured["instrument_map"] is fake_instrument_map


def test_run_size_command_with_live_source_dhan_passes_the_provider_through(tmp_path, capsys, monkeypatch):
    import market.context as market_context_module

    _seed_buy_decision(tmp_path / "decisions.db")

    fake_live_provider = object()
    monkeypatch.setattr("main._build_live_snapshot_provider", lambda args: fake_live_provider)

    captured = {}

    def _fake_get_market_context(symbol, **kwargs):
        captured["live_snapshot_provider"] = kwargs.get("live_snapshot_provider")
        return MarketContext(symbol="AAPL", as_of=datetime(2024, 6, 1), price=200.0, atr_14=5.0, data_source="DHAN", data_status="LIVE")

    monkeypatch.setattr(market_context_module, "get_market_context", _fake_get_market_context)

    args = parse_args(["size", "--symbol", "AAPL", "--decision-db", str(tmp_path / "decisions.db"), "--live-source", "dhan"])
    run_size_command(args)

    assert captured["live_snapshot_provider"] is fake_live_provider
    output = capsys.readouterr().out
    assert "Data source:    DHAN (LIVE)" in output


def test_run_predict_command_with_live_source_dhan_passes_the_provider_through(tmp_path, capsys, monkeypatch):
    import market.context as market_context_module

    _seed_buy_decision(tmp_path / "decisions.db")

    fake_live_provider = object()
    monkeypatch.setattr("main._build_live_snapshot_provider", lambda args: fake_live_provider)

    captured = {}

    def _fake_get_market_context(symbol, **kwargs):
        captured["live_snapshot_provider"] = kwargs.get("live_snapshot_provider")
        return MarketContext(symbol="AAPL", as_of=datetime(2024, 6, 1), price=200.0, atr_14=5.0, data_source="DHAN", data_status="LIVE")

    monkeypatch.setattr(market_context_module, "get_market_context", _fake_get_market_context)

    args = parse_args([
        "predict", "--symbol", "AAPL", "--decision-db", str(tmp_path / "decisions.db"),
        "--db", str(tmp_path / "predictions.db"), "--live-source", "dhan",
    ])
    run_predict_command(args)

    assert captured["live_snapshot_provider"] is fake_live_provider
    output = capsys.readouterr().out
    assert "Data source:    DHAN (LIVE)" in output


def test_run_size_command_without_live_source_passes_none(tmp_path, monkeypatch):
    import market.context as market_context_module

    _seed_buy_decision(tmp_path / "decisions.db")

    captured = {}

    def _fake_get_market_context(symbol, **kwargs):
        captured["live_snapshot_provider"] = kwargs.get("live_snapshot_provider")
        return MarketContext(symbol="AAPL", as_of=datetime(2024, 6, 1), price=200.0, atr_14=5.0)

    monkeypatch.setattr(market_context_module, "get_market_context", _fake_get_market_context)

    args = parse_args(["size", "--symbol", "AAPL", "--decision-db", str(tmp_path / "decisions.db")])
    run_size_command(args)

    assert captured["live_snapshot_provider"] is None
