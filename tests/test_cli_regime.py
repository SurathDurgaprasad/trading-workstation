"""Phase 33 -- `main.py regime` CLI, plus `scan`'s new breadth line. No
real network: a fake Yahoo provider serves synthetic bars."""

from datetime import datetime, timedelta, timezone

import pytest

from main import parse_args, run_regime_command, run_scan_command
from market.data_provider import OHLCV, OHLCVBar
from market_intelligence.models import CandidateScore, ScanReport
from market_intelligence.store import ScanHistoryStore

_START = datetime(2023, 1, 2)


def _uptrend_bars(n: int = 300, start: float = 100.0, step: float = 0.5) -> list[OHLCVBar]:
    return [
        OHLCVBar(timestamp=_START + timedelta(days=i), open=start + step * i, high=(start + step * i) * 1.01, low=(start + step * i) * 0.99, close=start + step * i, volume=1_000_000.0)
        for i in range(n)
    ]


class _FakeProvider:
    def __init__(self, bars: list[OHLCVBar]):
        self._bars = bars

    def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
        return OHLCV(symbol=symbol, interval=interval, bars=self._bars)


@pytest.fixture(autouse=True)
def _fake_yahoo(monkeypatch):
    import backtesting.cache as cache_module
    import market.data_provider as market_data_provider_module

    fake = _FakeProvider(_uptrend_bars())
    monkeypatch.setattr(market_data_provider_module, "get_market_data_provider", lambda: fake)
    monkeypatch.setattr(cache_module, "CachedMarketDataProvider", lambda inner: inner)
    yield fake


def _candidate(symbol: str, trend_score: float, composite: float = 0.0) -> CandidateScore:
    return CandidateScore(
        symbol=symbol, as_of=datetime(2024, 6, 1), last_close=100.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.0, trend_score=trend_score, momentum_score=0.0, breakout_score=0.0,
        relative_strength_score=None, sector_strength_score=None, composite_score=composite, explanation=["fake"],
    )


def _save_scan(db_path, *candidates: CandidateScore, benchmark_symbol="^NSEI"):
    store = ScanHistoryStore(db_path)
    store.save_report(ScanReport(
        scan_id="scan-1", as_of=datetime(2024, 6, 1, tzinfo=timezone.utc), universe_mode="watchlist",
        universe_size=len(candidates), benchmark_symbol=benchmark_symbol, benchmark_unavailable_reason=None,
        config_version="cfg1", candidates=list(candidates), excluded=[],
    ))
    store.close()


# --- regime command --------------------------------------------------------------


def test_regime_subcommand_defaults():
    args = parse_args(["regime"])
    assert args.command == "regime"
    assert args.benchmark is None
    assert args.period == "2y"
    assert args.interval == "1d"
    assert args.with_sectors is False
    assert args.resilient is False


def test_regime_reports_no_scan_honestly(tmp_path):
    args = parse_args(["regime", "--scanner-db", str(tmp_path / "no-such-scanner.db")])
    with pytest.raises(SystemExit):
        run_regime_command(args)


def test_regime_end_to_end_with_a_persisted_scan(tmp_path, capsys):
    db_path = tmp_path / "scanner.db"
    _save_scan(db_path, _candidate("A", trend_score=1.0), _candidate("B", trend_score=-1.0))

    args = parse_args(["regime", "--scanner-db", str(db_path)])
    run_regime_command(args)

    output = capsys.readouterr().out
    assert "MARKET REGIME & BREADTH" in output
    assert "Advancing:  1" in output
    assert "Declining:  1" in output
    assert "BENCHMARK (^NSEI):" in output
    assert "Trend regime:      UPTREND" in output  # synthetic bars are a steady uptrend
    assert "SECTOR STRENGTH: not computed" in output


def test_regime_with_sectors_builds_a_ranking(tmp_path, capsys, monkeypatch):
    import research.sector as sector_module

    class _FakeSectorProvider:
        def fetch_sector_info(self, symbol):
            from research.models import SectorInfo

            return SectorInfo(symbol=symbol, sector="IT" if symbol == "A" else "BANKING", industry=None, as_of=datetime.now(timezone.utc))

    monkeypatch.setattr(sector_module, "YahooSectorInfoProvider", _FakeSectorProvider)

    db_path = tmp_path / "scanner.db"
    _save_scan(db_path, _candidate("A", trend_score=1.0, composite=2.0), _candidate("B", trend_score=1.0, composite=0.5))

    args = parse_args(["regime", "--scanner-db", str(db_path), "--with-sectors"])
    run_regime_command(args)

    output = capsys.readouterr().out
    assert "SECTOR STRENGTH (2 sector(s)" in output
    assert "IT" in output and "BANKING" in output


def test_regime_benchmark_override(tmp_path, capsys):
    db_path = tmp_path / "scanner.db"
    _save_scan(db_path, _candidate("A", trend_score=1.0), benchmark_symbol="^NSEI")

    args = parse_args(["regime", "--scanner-db", str(db_path), "--benchmark", "^GSPC"])
    run_regime_command(args)

    output = capsys.readouterr().out
    assert "BENCHMARK (^GSPC):" in output


def test_regime_no_benchmark_configured(tmp_path, capsys):
    db_path = tmp_path / "scanner.db"
    _save_scan(db_path, _candidate("A", trend_score=1.0), benchmark_symbol=None)

    args = parse_args(["regime", "--scanner-db", str(db_path)])
    run_regime_command(args)

    output = capsys.readouterr().out
    assert "BENCHMARK (none configured):" in output


# --- scan's breadth line ----------------------------------------------------------


def test_scan_prints_market_breadth(tmp_path, capsys):
    args = parse_args(["scan", "--symbols", "AAPL", "--benchmark", "", "--db", str(tmp_path / "scanner.db")])
    run_scan_command(args)

    output = capsys.readouterr().out
    assert "Market breadth (this scan):" in output
    assert "1 advancing, 0 declining, 0 flat" in output
