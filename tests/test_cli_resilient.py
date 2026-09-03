"""Phase 30 -- `--resilient` opt-in wiring on scan/evaluate/learn/shadow-run.
No real network: the underlying Yahoo provider factory is faked, matching
tests/test_shadow_run.py's own established fixture pattern."""

from datetime import datetime, timedelta, timezone

import pytest

from main import parse_args, run_evaluate_command, run_learn_command, run_scan_command, run_shadow_run_command
from market.data_provider import OHLCV, OHLCVBar

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
    def __init__(self, bars):
        self._bars = bars
        self.calls: list[str] = []

    def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
        self.calls.append(symbol)
        return OHLCV(symbol=symbol, interval=interval, bars=self._bars)


@pytest.fixture(autouse=True)
def _wire_fakes(monkeypatch):
    import backtesting.cache as cache_module
    import market.data_provider as market_data_provider_module
    import research.news as research_news_module
    import research.sector as research_sector_module
    from market.context import MarketContext

    fake_provider = _FakeMarketDataProvider(_uptrend_bars())
    monkeypatch.setattr(market_data_provider_module, "get_market_data_provider", lambda: fake_provider)
    monkeypatch.setattr(cache_module, "CachedMarketDataProvider", lambda inner: inner)  # identity -- always a "miss", every call reaches the (possibly resilient-wrapped) provider

    class _FakeNewsProvider:
        def fetch_news(self, symbol, *, limit=10):
            return []

    class _FakeSectorProvider:
        def fetch_sector_info(self, symbol):
            from research.models import SectorInfo

            return SectorInfo(symbol=symbol, sector=None, industry=None, as_of=datetime.now(timezone.utc))

    monkeypatch.setattr(research_news_module, "YahooNewsProvider", _FakeNewsProvider)
    monkeypatch.setattr(research_sector_module, "YahooSectorInfoProvider", _FakeSectorProvider)
    entry_as_of = _START + timedelta(days=80)
    monkeypatch.setattr(
        "market.context.get_market_context",
        lambda symbol, **kwargs: MarketContext(symbol=symbol, as_of=entry_as_of, price=260.0, atr_14=5.0),
    )
    yield fake_provider


def _db_args(tmp_path):
    return ["--db", str(tmp_path / "scanner.db")]


# --- scan --------------------------------------------------------------------


def test_scan_without_resilient_prints_no_metrics_line(tmp_path, capsys):
    args = parse_args(["scan", "--symbols", "AAPL", "--benchmark", "", *_db_args(tmp_path)])
    run_scan_command(args)
    assert "Provider metrics" not in capsys.readouterr().out


def test_scan_with_resilient_prints_metrics_and_still_finds_candidates(tmp_path, capsys):
    args = parse_args(["scan", "--symbols", "AAPL", "--benchmark", "", "--resilient", *_db_args(tmp_path)])
    run_scan_command(args)

    output = capsys.readouterr().out
    assert "Provider metrics (--resilient):" in output
    assert "calls=1 successes=1 failures=0" in output
    assert "AAPL" in output


def test_scan_resilient_default_is_false():
    args = parse_args(["scan", "--symbols", "AAPL"])
    assert args.resilient is False


# --- shadow-run ----------------------------------------------------------------


def test_shadow_run_with_resilient_prints_metrics(tmp_path, capsys):
    args = parse_args([
        "shadow-run", "--symbols", "AAPL", "--benchmark", "", "--skip-evaluate", "--resilient",
        "--scanner-db", str(tmp_path / "scanner.db"), "--research-db", str(tmp_path / "research.db"),
        "--decision-db", str(tmp_path / "decisions.db"), "--predictions-db", str(tmp_path / "predictions.db"),
    ])
    run_shadow_run_command(args)
    output = capsys.readouterr().out
    assert "Provider metrics (--resilient):" in output


def test_shadow_run_without_resilient_prints_no_metrics_line(tmp_path, capsys):
    args = parse_args([
        "shadow-run", "--symbols", "AAPL", "--benchmark", "", "--skip-evaluate",
        "--scanner-db", str(tmp_path / "scanner.db"), "--research-db", str(tmp_path / "research.db"),
        "--decision-db", str(tmp_path / "decisions.db"), "--predictions-db", str(tmp_path / "predictions.db"),
    ])
    run_shadow_run_command(args)
    assert "Provider metrics" not in capsys.readouterr().out


# --- evaluate / learn ------------------------------------------------------------


def test_evaluate_with_resilient_prints_metrics_even_with_nothing_pending(tmp_path, capsys):
    args = parse_args(["evaluate", "--resilient", "--db", str(tmp_path / "predictions.db")])
    run_evaluate_command(args)
    output = capsys.readouterr().out
    assert "Provider metrics (--resilient):" in output
    assert "calls=0" in output  # nothing pending -- the resilient provider was built but never called


def test_learn_with_resilient_prints_metrics(tmp_path, capsys):
    args = parse_args(["learn", "--resilient", "--predictions-db", str(tmp_path / "predictions.db")])
    run_learn_command(args)
    output = capsys.readouterr().out
    assert "Provider metrics (--resilient):" in output


def test_learn_without_resilient_prints_no_metrics_line(tmp_path, capsys):
    args = parse_args(["learn", "--predictions-db", str(tmp_path / "predictions.db")])
    run_learn_command(args)
    assert "Provider metrics" not in capsys.readouterr().out
