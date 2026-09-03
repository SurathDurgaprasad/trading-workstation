"""Phase 28 -- `main.py schedule tick|loop|status` CLI wiring. Reuses the
same fake-provider fixtures as test_scheduler_runner.py (no real network/
Ollama here either)."""

from datetime import datetime, timedelta, timezone

import pytest

from live.dhan.market_session import IST
from market.data_provider import OHLCV, OHLCVBar
from main import parse_args, run_schedule_command

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


_TRADING_TIME = "2026-09-03T11:00:00+05:30"  # Thursday, inside the intraday window


def _db_args(tmp_path):
    return [
        "--scanner-db", str(tmp_path / "scanner.db"), "--research-db", str(tmp_path / "research.db"),
        "--decision-db", str(tmp_path / "decisions.db"), "--predictions-db", str(tmp_path / "predictions.db"),
        "--run-db", str(tmp_path / "runs.db"),
    ]


def test_schedule_tick_defaults():
    args = parse_args(["schedule", "tick", "--symbols", "AAPL"])
    assert args.command == "schedule"
    assert args.schedule_command == "tick"
    assert args.symbols == "AAPL"
    assert args.staleness_seconds == 1800.0
    assert args.now is None


def test_schedule_loop_defaults():
    args = parse_args(["schedule", "loop", "--symbols", "AAPL"])
    assert args.schedule_command == "loop"
    assert args.interval_seconds == 60.0
    assert args.max_ticks is None


def test_schedule_status_defaults():
    args = parse_args(["schedule", "status"])
    assert args.schedule_command == "status"
    assert args.limit == 20


def test_schedule_requires_a_subcommand():
    with pytest.raises(SystemExit):
        parse_args(["schedule"])


def test_schedule_tick_runs_and_prints(tmp_path, capsys):
    args = parse_args(["schedule", "tick", "--symbols", "AAPL", "--benchmark", "", "--now", _TRADING_TIME, *_db_args(tmp_path)])
    run_schedule_command(args)

    output = capsys.readouterr().out
    assert "[RAN] Slot 'intraday' completed" in output


def test_schedule_tick_skip_prints_reason_not_a_traceback(tmp_path, capsys):
    weekend = "2026-09-05T11:00:00+05:30"  # Saturday
    args = parse_args(["schedule", "tick", "--symbols", "AAPL", "--now", weekend, *_db_args(tmp_path)])
    run_schedule_command(args)

    output = capsys.readouterr().out
    assert "[SKIPPED]" in output
    assert "trading day" in output


def test_schedule_status_reports_no_runs_yet(tmp_path, capsys):
    args = parse_args(["schedule", "status", "--run-db", str(tmp_path / "runs.db")])
    run_schedule_command(args)
    assert "No scheduler runs recorded yet" in capsys.readouterr().out


def test_schedule_status_after_a_tick_shows_the_run(tmp_path, capsys):
    tick_args = parse_args(["schedule", "tick", "--symbols", "AAPL", "--benchmark", "", "--now", _TRADING_TIME, *_db_args(tmp_path)])
    run_schedule_command(tick_args)
    capsys.readouterr()

    status_args = parse_args(["schedule", "status", "--run-db", str(tmp_path / "runs.db")])
    run_schedule_command(status_args)
    output = capsys.readouterr().out
    assert "intraday" in output
    assert "COMPLETED" in output


def test_schedule_loop_stops_after_max_ticks_without_sleeping(tmp_path, capsys, monkeypatch):
    """--max-ticks bounds the loop for a scripted/CI-safe run; the second
    tick (same slot, same day, well within the frequency window) is
    expected to SKIP, proving the loop really ticks more than once."""
    slept = []
    monkeypatch.setattr("main.time.sleep", lambda seconds: slept.append(seconds))
    # Freeze "now" for every tick inside the loop by monkeypatching datetime.now via IST-aware fixed clock is
    # not directly supported by the CLI (no --now for loop, by design -- loop uses the real clock every
    # tick). Exercise it with the real clock instead; the assertion only needs "it ticked twice and slept once".
    args = parse_args(["schedule", "loop", "--symbols", "AAPL", "--benchmark", "", "--max-ticks", "2", "--interval-seconds", "5", *_db_args(tmp_path)])
    run_schedule_command(args)

    output = capsys.readouterr().out
    assert output.count("[RAN]") + output.count("[SKIPPED]") == 2
    assert slept == [5.0]  # sleeps BETWEEN ticks only, never after the last one
    assert "Loop stopped after 2 tick(s)" in output


def test_schedule_loop_handles_ctrl_c_cleanly(tmp_path, capsys, monkeypatch):
    """Graceful shutdown: KeyboardInterrupt mid-loop must produce a clean
    message and a normal return, never an uncaught traceback -- matching
    paper-live's own established Ctrl+C handling."""
    call_count = {"n": 0}

    def _fake_run_tick(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise KeyboardInterrupt
        from scheduler.models import TickResult
        return TickResult(ran=False, reason="no slot due")

    monkeypatch.setattr("main.time.sleep", lambda seconds: None)
    monkeypatch.setattr("scheduler.runner.run_tick", _fake_run_tick)

    args = parse_args(["schedule", "loop", "--symbols", "AAPL", *_db_args(tmp_path)])
    run_schedule_command(args)  # must return normally, not raise

    output = capsys.readouterr().out
    assert "Interrupted by user (Ctrl+C)" in output
    assert "Traceback" not in output


def test_schedule_tick_dry_run_now_flag_does_not_persist_anything_for_a_skip(tmp_path):
    from scheduler.store import SchedulerRunStore

    weekend = "2026-09-05T11:00:00+05:30"
    args = parse_args(["schedule", "tick", "--symbols", "AAPL", "--now", weekend, *_db_args(tmp_path)])
    run_schedule_command(args)

    store = SchedulerRunStore(tmp_path / "runs.db")
    runs = store.list_runs()
    store.close()
    assert runs == []
