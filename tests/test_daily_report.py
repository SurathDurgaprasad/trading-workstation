"""NSE PREDICTION ENGINE mission: tests for the `daily-report` CLI
command -- pure wiring tests (does scan -> regime -> direction -> sector
context -> tradeability correctly flow through and get printed/
persisted), same posture as tests/test_shadow_run.py's own docstring.
No real network anywhere: the market-data provider is replaced with a
fake serving a deterministic uptrend series for every symbol.
"""
from datetime import datetime, timedelta

import pytest

from main import parse_args, run_daily_report_command
from market.data_provider import OHLCV, OHLCVBar

_START = datetime(2023, 1, 2)


def _bars(n: int = 300, start: float = 100.0, step: float = 0.5) -> list[OHLCVBar]:
    bars = []
    for i in range(n):
        close = start + step * i
        bars.append(OHLCVBar(
            timestamp=_START + timedelta(days=i), open=close, high=close * 1.001, low=close * 0.999,
            close=close, volume=100_000.0,
        ))
    return bars


class _FakeMarketDataProvider:
    """Serves the SAME rising series for any symbol requested -- including
    ^NSEI and the 9 NIFTY sector indices/India VIX, so --with-nifty-sectors/
    --with-india-vix exercise real code paths without any real fetch."""

    def __init__(self, bars: list[OHLCVBar]):
        self._bars = bars

    def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
        return OHLCV(symbol=symbol, interval=interval, bars=self._bars)


@pytest.fixture(autouse=True)
def _wire_fake_provider(monkeypatch):
    import backtesting.cache as cache_module
    import market.data_provider as market_data_provider_module

    fake_provider = _FakeMarketDataProvider(_bars())
    monkeypatch.setattr(market_data_provider_module, "get_market_data_provider", lambda: fake_provider)
    monkeypatch.setattr(cache_module, "CachedMarketDataProvider", lambda inner: inner)


def test_daily_report_requires_symbols_or_watchlist_file(capsys):
    args = parse_args(["daily-report"])
    with pytest.raises(SystemExit) as exc:
        run_daily_report_command(args)
    assert exc.value.code == 2
    assert "one of --symbols or --watchlist-file is required" in capsys.readouterr().err


def test_daily_report_prints_the_expected_sections(tmp_path, capsys):
    args = parse_args([
        "daily-report", "--symbols", "RELIANCE.NS,TCS.NS", "--benchmark", "", "--top", "2",
        "--scanner-db", str(tmp_path / "scanner.db"), "--regime-db", str(tmp_path / "regime.db"),
    ])
    run_daily_report_command(args)

    output = capsys.readouterr().out
    assert "INDIAN MARKET DAILY DECISION REPORT" in output
    assert "MARKET:" in output
    assert "TOP 2 STOCK OBSERVATIONS" in output
    assert "Direction:" in output
    assert "Tradeability:" in output
    assert "Bullish evidence:" in output


def test_daily_report_persists_scan_and_regime_snapshot_with_matching_scan_id(tmp_path, capsys):
    args = parse_args([
        "daily-report", "--symbols", "RELIANCE.NS,TCS.NS", "--benchmark", "",
        "--scanner-db", str(tmp_path / "scanner.db"), "--regime-db", str(tmp_path / "regime.db"),
    ])
    run_daily_report_command(args)

    from market_intelligence.regime_store import MarketRegimeStore
    from market_intelligence.store import ScanHistoryStore

    scan_store = ScanHistoryStore(tmp_path / "scanner.db")
    scan_report = scan_store.latest_report()
    assert scan_report is not None
    scan_store.close()

    regime_store = MarketRegimeStore(tmp_path / "regime.db")
    report = regime_store.latest_report()
    assert report is not None
    assert report.scan_id == scan_report.scan_id
    regime_store.close()


def test_daily_report_with_nifty_sectors_and_india_vix_populates_both(tmp_path, capsys):
    args = parse_args([
        "daily-report", "--symbols", "TCS.NS", "--benchmark", "", "--with-nifty-sectors", "--with-india-vix",
        "--scanner-db", str(tmp_path / "scanner.db"), "--regime-db", str(tmp_path / "regime.db"),
    ])
    run_daily_report_command(args)

    output = capsys.readouterr().out
    assert "NIFTY SECTOR INDICES:" in output
    assert "NIFTY_IT" in output
    assert "INDIA VIX:" in output

    from market_intelligence.regime_store import MarketRegimeStore

    regime_store = MarketRegimeStore(tmp_path / "regime.db")
    report = regime_store.latest_report()
    assert len(report.sector_index_regimes) == 9
    assert report.india_vix is not None
    regime_store.close()


def test_daily_report_shows_sector_context_for_a_mapped_symbol():
    """TCS.NS is in market_intelligence.nse_sector_map.NSE_SECTOR_MAP
    (-> NIFTY_IT); its sector context line must name that sector, not
    'not classified'."""
    args = parse_args(["daily-report", "--symbols", "TCS.NS", "--benchmark", "", "--with-nifty-sectors"])
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_daily_report_command(args)
    output = buf.getvalue()
    assert "Sector context: NIFTY_IT" in output


def test_daily_report_does_not_record_any_prediction_or_touch_paper_state(tmp_path, capsys):
    """This is a READ-ONLY report -- no predictions.db is ever created or
    written to by this command, unlike shadow-run."""
    args = parse_args([
        "daily-report", "--symbols", "RELIANCE.NS", "--benchmark", "",
        "--scanner-db", str(tmp_path / "scanner.db"), "--regime-db", str(tmp_path / "regime.db"),
    ])
    run_daily_report_command(args)

    assert not (tmp_path / "predictions.db").exists()


def test_daily_report_does_not_record_forecasts_unless_forecasts_db_given(tmp_path, capsys):
    args = parse_args([
        "daily-report", "--symbols", "RELIANCE.NS", "--benchmark", "",
        "--scanner-db", str(tmp_path / "scanner.db"), "--regime-db", str(tmp_path / "regime.db"),
    ])
    run_daily_report_command(args)

    assert not (tmp_path / "forecasts.db").exists()
    assert "Forecasts recorded" not in capsys.readouterr().out


def test_daily_report_forecasts_db_records_one_forecast_per_symbol_and_is_duplicate_safe(tmp_path, capsys):
    args = parse_args([
        "daily-report", "--symbols", "RELIANCE.NS,TCS.NS", "--benchmark", "", "--top", "2",
        "--scanner-db", str(tmp_path / "scanner.db"), "--regime-db", str(tmp_path / "regime.db"),
        "--forecasts-db", str(tmp_path / "forecasts.db"),
    ])
    run_daily_report_command(args)
    assert "Forecasts recorded this run: 2" in capsys.readouterr().out

    from predictions.direction_forecast_store import DirectionForecastStore

    store = DirectionForecastStore(tmp_path / "forecasts.db")
    assert len(store.list_forecasts()) == 2
    store.close()

    # Same bar, run again -- must not duplicate.
    run_daily_report_command(args)
    assert "Forecasts recorded this run: 0" in capsys.readouterr().out

    store = DirectionForecastStore(tmp_path / "forecasts.db")
    assert len(store.list_forecasts()) == 2
    store.close()


# --- cache staleness (real incident: a symbol whose cache silently went stale --
# still a cache HIT, so a forecast/report could be recorded against a stale
# reference_price with no warning at all) --------------------------------------


@pytest.fixture
def _stale_cache_symbol():
    """Writes a REAL meta.json (backtesting.cache.CACHE_ROOT is a bound
    default on report_cache_staleness, so monkeypatching the module-level
    name would NOT reach it -- this exercises the real, default cache
    root main.py itself uses, with a throwaway, obviously-test symbol
    name, cleaned up in teardown)."""
    import json
    from datetime import timezone
    from pathlib import Path

    from backtesting.cache import CACHE_ROOT

    symbol = "ZZ_STALE_TEST_SYMBOL"
    symbol_dir = CACHE_ROOT / symbol
    symbol_dir.mkdir(parents=True, exist_ok=True)
    old = datetime.now(timezone.utc) - timedelta(days=13)
    meta_path = symbol_dir / "1d.meta.json"
    meta_path.write_text(json.dumps({
        "symbol": symbol, "interval": "1d", "period": "1y",
        "start": (old - timedelta(days=365)).isoformat(), "end": old.isoformat(),
        "retrieved_at": old.isoformat(), "bar_count": 250,
    }))
    try:
        yield symbol
    finally:
        for f in symbol_dir.glob("*"):
            f.unlink()
        symbol_dir.rmdir()


def test_daily_report_warns_and_skips_forecast_for_stale_cached_symbol(tmp_path, capsys, _stale_cache_symbol):
    args = parse_args([
        "daily-report", "--symbols", f"RELIANCE.NS,{_stale_cache_symbol}", "--benchmark", "", "--top", "2",
        "--scanner-db", str(tmp_path / "scanner.db"), "--regime-db", str(tmp_path / "regime.db"),
        "--forecasts-db", str(tmp_path / "forecasts.db"),
    ])
    run_daily_report_command(args)

    output = capsys.readouterr().out
    assert "DATA STALENESS WARNING" in output
    assert _stale_cache_symbol in output
    assert "STALE DATA" in output
    assert "1 skipped -- stale data" in output
    assert "Forecasts recorded this run: 1 " in output

    from predictions.direction_forecast_store import DirectionForecastStore

    store = DirectionForecastStore(tmp_path / "forecasts.db")
    recorded_symbols = {f.symbol for f in store.list_forecasts()}
    assert _stale_cache_symbol not in recorded_symbols
    assert "RELIANCE.NS" in recorded_symbols
    store.close()


def test_daily_report_no_staleness_warning_when_cache_is_fresh(tmp_path, capsys):
    args = parse_args([
        "daily-report", "--symbols", "RELIANCE.NS,TCS.NS", "--benchmark", "", "--top", "2",
        "--scanner-db", str(tmp_path / "scanner.db"), "--regime-db", str(tmp_path / "regime.db"),
    ])
    run_daily_report_command(args)

    output = capsys.readouterr().out
    assert "DATA STALENESS WARNING" not in output
