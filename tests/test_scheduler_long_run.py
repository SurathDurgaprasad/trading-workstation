"""Phase 39 -- long-run operations & recovery: proves the scheduler
stays correct across MANY simulated trading days, not just a single
tick. This does not (and cannot) fabricate real elapsed-time evidence
(see docs/phases/phase-39-long-run-operations-recovery.html's own
stated limitation) -- it deterministically drives `run_tick` forward
through a sequence of injected `now` timestamps spanning 10 simulated
trading days, which is the correct way to test scheduling LOGIC (day
boundaries, frequency gating, restart recovery) without waiting.

Reuses the exact fake-provider fixture test_scheduler_runner.py already
established -- no real network/Ollama anywhere in this file.
"""

from datetime import datetime, time as dtime, timedelta, timezone

import pytest

from live.dhan.market_session import IST
from market.data_provider import OHLCV, OHLCVBar
from scheduler.config import ScheduleConfig
from scheduler.models import RunStatus
from scheduler.runner import run_tick
from scheduler.store import SchedulerRunStore

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


@pytest.fixture
def run_store(tmp_path):
    s = SchedulerRunStore(tmp_path / "runs.db")
    yield s
    s.close()


def _db_paths(tmp_path):
    return dict(
        scanner_db=str(tmp_path / "scanner.db"), research_db=str(tmp_path / "research.db"),
        decision_db=str(tmp_path / "decisions.db"), predictions_db=str(tmp_path / "predictions.db"),
    )


# A run of 10 consecutive WEEKDAYS (2026-09-03 is a Thursday), each driven
# through 6 ticks: pre_market, market_open, two intraday re-triggers 70
# minutes apart (past the 60-minute frequency gate), pre_close, post_market.
_FIRST_DAY = datetime(2026, 9, 3, tzinfo=IST).date()
_NUM_DAYS = 10


def _weekday_sequence(first_day, count: int) -> list:
    days = []
    cursor = first_day
    while len(days) < count:
        if cursor.weekday() < 5:  # Mon-Fri
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _day_ticks(day) -> list[datetime]:
    return [
        datetime.combine(day, dtime(8, 50), tzinfo=IST),   # pre_market
        datetime.combine(day, dtime(9, 20), tzinfo=IST),   # market_open
        datetime.combine(day, dtime(10, 0), tzinfo=IST),   # intraday #1
        datetime.combine(day, dtime(11, 10), tzinfo=IST),  # intraday #2 (70 min later -- past the 60min gate)
        datetime.combine(day, dtime(15, 20), tzinfo=IST),  # pre_close
        datetime.combine(day, dtime(16, 0), tzinfo=IST),   # post_market (evaluate_and_learn)
    ]


def test_scheduler_stays_correct_across_ten_simulated_trading_days(tmp_path, run_store):
    days = _weekday_sequence(_FIRST_DAY, _NUM_DAYS)
    schedule_config = ScheduleConfig()
    db_paths = _db_paths(tmp_path)

    ran_count = 0
    skipped_count = 0
    for day in days:
        for tick_time in _day_ticks(day):
            result = run_tick(schedule_config=schedule_config, run_store=run_store, symbols="AAPL", benchmark="", now=tick_time, **db_paths)
            if result.ran:
                ran_count += 1
            else:
                skipped_count += 1

    # Every day: pre_market, market_open, BOTH intraday ticks, pre_close, post_market all fire (6/6) --
    # nothing about day N's completions should block day N+1's ticks.
    assert ran_count == _NUM_DAYS * 6
    assert skipped_count == 0

    all_runs = run_store.list_runs(limit=10_000)
    assert len(all_runs) == _NUM_DAYS * 6
    assert all(r.status == RunStatus.COMPLETED for r in all_runs)

    # Exactly one COMPLETED run per (slot, day) pair for the four single-fire
    # slots, and exactly two for `intraday` (its frequency gate allows re-firing).
    from collections import Counter

    counts = Counter((r.slot_name, r.run_date) for r in all_runs)
    for day in days:
        run_date = day.isoformat()
        assert counts[("pre_market", run_date)] == 1
        assert counts[("market_open", run_date)] == 1
        assert counts[("intraday", run_date)] == 2
        assert counts[("pre_close", run_date)] == 1
        assert counts[("post_market", run_date)] == 1


def test_scheduler_reclaims_a_crash_mid_run_and_resumes_the_next_day(tmp_path, run_store):
    """Simulates a process crash: day 5's post_market run starts (a
    RUNNING lock is written) but the process is killed before it
    finishes -- no FAILED/COMPLETED row is ever written for it, exactly
    what a real crash looks like. Day 6's first tick must reclaim the
    stale lock and continue operating normally, not stay wedged forever."""
    days = _weekday_sequence(_FIRST_DAY, 6)
    schedule_config = ScheduleConfig()
    db_paths = _db_paths(tmp_path)

    for day in days[:4]:
        for tick_time in _day_ticks(day):
            run_tick(schedule_config=schedule_config, run_store=run_store, symbols="AAPL", benchmark="", now=tick_time, **db_paths)

    crash_day = days[4]
    crash_time = datetime.combine(crash_day, dtime(16, 0), tzinfo=IST)
    run_store.start_run(
        run_id="crashed-run", slot_name="post_market", run_date=crash_day.isoformat(),
        started_at=crash_time.astimezone(timezone.utc),
    )
    assert run_store.active_lock() is not None  # the crash left a lock held, same as a real killed process would

    recovery_day = days[5]
    first_tick_next_day = datetime.combine(recovery_day, dtime(8, 50), tzinfo=IST)
    result = run_tick(
        schedule_config=schedule_config, run_store=run_store, symbols="AAPL", benchmark="",
        now=first_tick_next_day, staleness_seconds=1800, **db_paths,
    )

    assert result.reclaimed_run_ids == ("crashed-run",)
    assert run_store.get_run("crashed-run").status == RunStatus.RECLAIMED
    assert result.ran is True  # pre_market ran normally once the stale lock was cleared
    assert result.slot_name == "pre_market"

    # Operation continues normally for the rest of the recovery day.
    for tick_time in _day_ticks(recovery_day)[1:]:
        r = run_tick(schedule_config=schedule_config, run_store=run_store, symbols="AAPL", benchmark="", now=tick_time, **db_paths)
        assert r.ran is True

    # The database is still fully queryable and consistent after the reclaim.
    all_runs = run_store.list_runs(limit=10_000)
    assert len(all_runs) == 4 * 6 + 1 + 6  # 4 full days + the crashed lock row + the full recovery day
    assert sum(1 for r in all_runs if r.status == RunStatus.RECLAIMED) == 1
