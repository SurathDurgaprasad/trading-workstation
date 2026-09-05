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

    # Same fix as tests/test_shadow_run.py's own _wire_fakes: freeze the
    # critic's "now" near this fixture's own as_of, decoupling it from real
    # wall-clock drift (see that file's fixture for the full rationale).
    import critic.engine as critic_engine_module

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            frozen = entry_as_of + timedelta(days=1)
            return frozen.replace(tzinfo=tz) if tz else frozen

    monkeypatch.setattr(critic_engine_module, "datetime", _FrozenDatetime)

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
    assert args.initial_capital is None


def test_schedule_tick_initial_capital_override():
    args = parse_args(["schedule", "tick", "--symbols", "AAPL", "--initial-capital", "20000"])
    assert args.initial_capital == 20_000.0


def test_schedule_paper_execute_defaults_to_off():
    args = parse_args(["schedule", "tick", "--symbols", "AAPL"])
    assert args.paper_execute is False
    assert args.state_db is None


def test_schedule_paper_execute_flag_parses():
    args = parse_args(["schedule", "tick", "--symbols", "AAPL", "--paper-execute", "--state-db", "/tmp/s.db"])
    assert args.paper_execute is True
    assert args.state_db == "/tmp/s.db"


def test_schedule_loop_paper_execute_flag_parses():
    args = parse_args(["schedule", "loop", "--symbols", "AAPL", "--paper-execute", "--state-db", "/tmp/s.db"])
    assert args.paper_execute is True


def test_schedule_max_holding_bars_defaults_to_none():
    args = parse_args(["schedule", "tick", "--symbols", "AAPL"])
    assert args.max_holding_bars is None


def test_schedule_max_holding_bars_flag_parses():
    args = parse_args(["schedule", "tick", "--symbols", "AAPL", "--max-holding-bars", "5"])
    assert args.max_holding_bars == 5


def test_schedule_skip_critic_defaults_to_false():
    args = parse_args(["schedule", "tick", "--symbols", "AAPL"])
    assert args.skip_critic is False


def test_schedule_skip_critic_flag_parses():
    args = parse_args(["schedule", "tick", "--symbols", "AAPL", "--skip-critic"])
    assert args.skip_critic is True


def test_schedule_loop_defaults():
    args = parse_args(["schedule", "loop", "--symbols", "AAPL"])
    assert args.schedule_command == "loop"
    assert args.interval_seconds == 60.0
    assert args.max_ticks is None
    assert args.now is None


def test_schedule_loop_now_flag_reaches_every_tick(tmp_path, capsys):
    """Real gap found via a genuine weekend regression-suite run (2026-09-05
    -- a real Saturday): `loop` had no --now override at all, unlike
    `tick`, so any test asserting a tick actually ran was silently
    dependent on whatever real wall-clock day/time the suite happened to
    execute on. Closed by adding the same --now `tick` already had. This
    test proves the flag genuinely reaches run_tick (a known trading-hours
    timestamp ticks and runs), independent of what day it is for real."""
    args = parse_args([
        "schedule", "loop", "--symbols", "AAPL", "--benchmark", "", "--max-ticks", "1", "--interval-seconds", "0",
        "--now", _TRADING_TIME, *_db_args(tmp_path),
    ])
    run_schedule_command(args)

    output = capsys.readouterr().out
    assert "[RAN] Slot 'intraday' completed" in output


def test_schedule_loop_now_flag_correctly_skips_on_a_real_weekend_timestamp(tmp_path, capsys):
    weekend = "2026-09-05T11:00:00+05:30"  # Saturday
    args = parse_args([
        "schedule", "loop", "--symbols", "AAPL", "--max-ticks", "1", "--interval-seconds", "0",
        "--now", weekend, *_db_args(tmp_path),
    ])
    run_schedule_command(args)

    output = capsys.readouterr().out
    assert "[SKIPPED]" in output
    assert "trading day" in output


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


def test_schedule_status_check_integrity_prints_ok_and_size(tmp_path, capsys):
    tick_args = parse_args(["schedule", "tick", "--symbols", "AAPL", "--benchmark", "", "--now", _TRADING_TIME, *_db_args(tmp_path)])
    run_schedule_command(tick_args)
    capsys.readouterr()

    status_args = parse_args(["schedule", "status", "--check-integrity", "--run-db", str(tmp_path / "runs.db")])
    run_schedule_command(status_args)
    output = capsys.readouterr().out
    assert "Integrity check: ok" in output
    assert "file size:" in output


def test_schedule_status_without_check_integrity_omits_the_line(tmp_path, capsys):
    status_args = parse_args(["schedule", "status", "--run-db", str(tmp_path / "runs.db")])
    run_schedule_command(status_args)
    assert "Integrity check" not in capsys.readouterr().out


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
    # `loop` now supports --now too (added alongside the fix for the
    # weekend-flakiness gap this test file's own paper-execute test hit),
    # but this test only needs "it ticked twice and slept once" -- the
    # real clock is exercised here deliberately, not frozen, since that
    # property holds regardless of what real time it is.
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


def test_schedule_loop_continues_past_an_unexpected_tick_level_exception(tmp_path, capsys, monkeypatch):
    """Phase 39: an exception run_tick itself does NOT catch (e.g. a
    transient SQLite error from schedule_config.due_slot or the run
    store, raised before any RunRecord even exists) must not kill a
    long-lived, unattended `schedule loop` process -- only KeyboardInterrupt
    should stop it."""
    call_count = {"n": 0}

    def _fake_run_tick(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated transient scheduler-store error")
        from scheduler.models import TickResult
        return TickResult(ran=False, reason="no slot due")

    monkeypatch.setattr("main.time.sleep", lambda seconds: None)
    monkeypatch.setattr("scheduler.runner.run_tick", _fake_run_tick)

    args = parse_args(["schedule", "loop", "--symbols", "AAPL", "--max-ticks", "3", *_db_args(tmp_path)])
    run_schedule_command(args)  # must return normally, not raise

    output = capsys.readouterr().out
    assert call_count["n"] == 3  # the failed first tick did not stop the loop
    assert "Tick failed unexpectedly: RuntimeError: simulated transient scheduler-store error" in output
    assert "Traceback" not in output
    assert "Loop stopped after 3 tick(s), 1 unexpected tick failure(s)" in output


def test_schedule_loop_ctrl_c_still_stops_the_loop_even_after_a_prior_tick_failure(tmp_path, capsys, monkeypatch):
    """The new per-tick except-and-continue must not accidentally swallow
    KeyboardInterrupt -- Ctrl+C must still stop the loop cleanly."""
    call_count = {"n": 0}

    def _fake_run_tick(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated transient error")
        if call_count["n"] == 2:
            raise KeyboardInterrupt
        from scheduler.models import TickResult
        return TickResult(ran=False, reason="no slot due")

    monkeypatch.setattr("main.time.sleep", lambda seconds: None)
    monkeypatch.setattr("scheduler.runner.run_tick", _fake_run_tick)

    args = parse_args(["schedule", "loop", "--symbols", "AAPL", *_db_args(tmp_path)])
    run_schedule_command(args)

    output = capsys.readouterr().out
    assert call_count["n"] == 2  # stopped at the KeyboardInterrupt, never reached a third tick
    assert "Interrupted by user (Ctrl+C)" in output


def test_schedule_loop_log_file_writes_a_persistent_log(tmp_path, capsys):
    """Phase 39: --log-file attaches a rotating file handler so an
    operator running `schedule loop` unattended for days has a
    persistent record beyond stdout."""
    import logging

    log_path = tmp_path / "scheduler.log"
    root = logging.getLogger()
    added_before = list(root.handlers)
    try:
        args = parse_args([
            "schedule", "tick", "--symbols", "AAPL", "--benchmark", "", "--now", _TRADING_TIME,
            "--log-file", str(log_path), *_db_args(tmp_path),
        ])
        run_schedule_command(args)
        for handler in root.handlers:
            handler.flush()

        assert log_path.exists()
        assert "file logging enabled" in log_path.read_text()
    finally:
        for handler in list(root.handlers):
            if handler not in added_before:
                root.removeHandler(handler)
                handler.close()


def test_schedule_loop_says_no_paper_order_either_by_default(tmp_path, capsys):
    """Default OFF, honestly stated: without --paper-execute, `schedule
    loop` must claim (correctly) that no paper order is placed either --
    not just that no REAL broker order is placed."""
    args = parse_args(["schedule", "loop", "--symbols", "AAPL", "--max-ticks", "1", "--interval-seconds", "0", *_db_args(tmp_path)])
    run_schedule_command(args)
    output = capsys.readouterr().out
    assert "No real broker order is EVER placed" in output
    assert "No paper order is placed either" in output
    assert "--paper-execute is ON" not in output


def test_schedule_loop_paper_execute_on_prints_honest_warning_not_false_safety_claim(tmp_path, capsys):
    """Regression (self-audit finding): the loop header used to claim
    'No real or paper order is ever placed by this command' unconditionally
    -- false the moment --paper-execute submits a real paper order. Must
    never claim that when --paper-execute is on; must say so plainly instead.

    Uses a custom always-due ScheduleConfig (see test_scheduler_runner.py's
    own test_custom_schedule_config_is_honored for the same pattern) rather
    than relying on the built-in schedule's real time-of-day windows --
    found via self-audit: `schedule loop` used to have no `--now` override
    (by design, for genuine unattended operation), so a test asserting a
    real submission happened was silently dependent on whatever real
    wall-clock time the suite happened to run at, and would spuriously
    fail outside the built-in schedule's 09:15-15:30 IST shadow_run
    windows (reproduced: this test genuinely failed, unrelated to critic
    wiring, once real time crossed 15:30 IST during this session --
    confirmed by running it against the pre-critic-wiring commit at the
    same real time).

    SECOND real gap found the same way (weekend hardening regression run,
    2026-09-05 -- a genuine Saturday): the always-due schedule config
    only bypasses the SLOT's own after/before window, not run_tick's
    OWN separate, unconditional current_market_session(...).is_weekday
    gate -- which `loop` had no way to override at all, so this test
    would ALSO spuriously fail every real weekend regardless of the
    config fix above. Closed by adding the same `--now` override `tick`
    already had to `loop` too (main.py's loop_parser/`_run_tick_from_args`
    call site) -- verified: --max-ticks 1 makes one tick's worth of
    "now" sufficient, no time-advancement-across-ticks concern for this
    test-only escape hatch."""
    config_path = tmp_path / "always_due_schedule.yaml"
    config_path.write_text("slots:\n  - name: always_due\n    after: \"00:00\"\n    before: null\n    frequency_minutes: null\n    action: shadow_run\n")

    paper_db = tmp_path / "paper.db"
    state_db = tmp_path / "state.db"
    args = parse_args([
        "schedule", "loop", "--symbols", "AAPL", "--benchmark", "", "--max-ticks", "1", "--interval-seconds", "0",
        "--initial-capital", "20000", "--paper-execute", "--paper-db", str(paper_db), "--state-db", str(state_db),
        "--config", str(config_path), "--now", _TRADING_TIME,
        *_db_args(tmp_path),
    ])
    run_schedule_command(args)
    output = capsys.readouterr().out
    assert "No real broker order is EVER placed" in output  # still true, still stated
    assert "No paper order is placed either" not in output  # would be false here
    assert "--paper-execute is ON" in output
    assert str(paper_db) in output

    from paper.store import PaperStore

    store = PaperStore(paper_db)
    entries = store.list_journal_entries()
    store.close()
    assert len(entries) == 1  # the real CLI path actually submitted a paper order


def test_schedule_tick_paper_execute_on_prints_honest_warning(tmp_path, capsys):
    paper_db = tmp_path / "paper.db"
    state_db = tmp_path / "state.db"
    args = parse_args([
        "schedule", "tick", "--symbols", "AAPL", "--benchmark", "", "--now", _TRADING_TIME,
        "--initial-capital", "20000", "--paper-execute", "--paper-db", str(paper_db), "--state-db", str(state_db),
        *_db_args(tmp_path),
    ])
    run_schedule_command(args)
    output = capsys.readouterr().out
    assert "--paper-execute is ON" in output


def test_schedule_tick_dry_run_now_flag_does_not_persist_anything_for_a_skip(tmp_path):
    from scheduler.store import SchedulerRunStore

    weekend = "2026-09-05T11:00:00+05:30"
    args = parse_args(["schedule", "tick", "--symbols", "AAPL", "--now", weekend, *_db_args(tmp_path)])
    run_schedule_command(args)

    store = SchedulerRunStore(tmp_path / "runs.db")
    runs = store.list_runs()
    store.close()
    assert runs == []
