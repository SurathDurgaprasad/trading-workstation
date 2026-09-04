"""Phase 28 -- scheduler/runner.py's `run_tick`. Reuses the exact same
fake-provider wiring tests/test_shadow_run.py established (no real
network/Ollama anywhere here) since `run_tick` reuses main.py's own
shadow-run/evaluate/learn command functions rather than duplicating
their logic.
"""

from datetime import datetime, time, timedelta, timezone

import pytest

from live.dhan.market_session import IST
from market.data_provider import OHLCV, MarketDataError, OHLCVBar
from scheduler.config import ScheduleConfig, ScheduleSlot
from scheduler.models import RunStatus, SlotAction
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


def _make_fake_get_market_context(*, price: float, atr_14: float, as_of: datetime):
    from market.context import MarketContext

    def _fn(symbol, **kwargs):
        return MarketContext(symbol=symbol, as_of=as_of, price=price, atr_14=atr_14)

    return _fn


@pytest.fixture(autouse=True)
def _wire_fakes(monkeypatch):
    import backtesting.cache as cache_module
    import market.data_provider as market_data_provider_module
    import research.news as research_news_module
    import research.sector as research_sector_module

    bars = _uptrend_bars()
    fake_provider = _FakeMarketDataProvider(bars)

    monkeypatch.setattr(market_data_provider_module, "get_market_data_provider", lambda: fake_provider)
    monkeypatch.setattr(cache_module, "CachedMarketDataProvider", lambda inner: inner)
    monkeypatch.setattr(research_news_module, "YahooNewsProvider", _FakeNewsProvider)
    monkeypatch.setattr(research_sector_module, "YahooSectorInfoProvider", _FakeSectorProvider)

    entry_as_of = _START + timedelta(days=80)
    monkeypatch.setattr(
        "market.context.get_market_context",
        _make_fake_get_market_context(price=260.0, atr_14=5.0, as_of=entry_as_of),
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


# A Thursday, well inside the 09:30-15:15 intraday window (IST).
_TRADING_TIME = datetime(2026, 9, 3, 11, 0, tzinfo=IST)
_WEEKEND_TIME = datetime(2026, 9, 5, 11, 0, tzinfo=IST)  # Saturday


def test_run_tick_executes_the_due_shadow_run_slot_and_persists_everything(tmp_path, run_store, capsys):
    result = run_tick(
        schedule_config=ScheduleConfig(), run_store=run_store, symbols="AAPL", benchmark="",
        now=_TRADING_TIME, **_db_paths(tmp_path),
    )

    assert result.ran is True
    assert result.slot_name == "intraday"
    assert result.run_id is not None

    record = run_store.get_run(result.run_id)
    assert record.status == RunStatus.COMPLETED
    assert record.slot_name == "intraday"

    from decision_engine.store import DecisionStore

    decision_store = DecisionStore(tmp_path / "decisions.db")
    decision = decision_store.latest_decision_for_symbol("AAPL")
    decision_store.close()
    assert decision is not None
    assert decision.label.value == "BUY"


def test_run_tick_skips_on_a_weekend(tmp_path, run_store):
    result = run_tick(schedule_config=ScheduleConfig(), run_store=run_store, symbols="AAPL", now=_WEEKEND_TIME, **_db_paths(tmp_path))
    assert result.ran is False
    assert "trading day" in result.reason
    assert run_store.list_runs() == []


def test_run_tick_skips_on_a_configured_holiday(tmp_path, run_store):
    config = ScheduleConfig(holidays=(_TRADING_TIME.date(),))
    result = run_tick(schedule_config=config, run_store=run_store, symbols="AAPL", now=_TRADING_TIME, **_db_paths(tmp_path))
    assert result.ran is False
    assert "holiday" in result.reason
    assert run_store.list_runs() == []


def test_run_tick_skips_when_another_run_is_already_in_progress(tmp_path, run_store):
    run_store.start_run(run_id="held", slot_name="intraday", run_date=_TRADING_TIME.date().isoformat(), started_at=datetime.now(timezone.utc))

    result = run_tick(schedule_config=ScheduleConfig(), run_store=run_store, symbols="AAPL", now=_TRADING_TIME, **_db_paths(tmp_path))

    assert result.ran is False
    assert "already in progress" in result.reason
    # No new run was started -- only the pre-seeded lock exists.
    assert [r.run_id for r in run_store.list_runs()] == ["held"]


def test_run_tick_reclaims_a_stale_lock_left_by_a_crashed_process_and_still_runs(tmp_path, run_store):
    """Restart recovery: a RUNNING record with no finished_at, started
    long enough ago, must not block the scheduler forever."""
    stale_started_at = _TRADING_TIME.astimezone(timezone.utc) - timedelta(hours=3)
    run_store.start_run(run_id="orphan", slot_name="intraday", run_date=_TRADING_TIME.date().isoformat(), started_at=stale_started_at)

    result = run_tick(
        schedule_config=ScheduleConfig(), run_store=run_store, symbols="AAPL", benchmark="",
        now=_TRADING_TIME, staleness_seconds=1800, **_db_paths(tmp_path),
    )

    assert result.reclaimed_run_ids == ("orphan",)
    assert run_store.get_run("orphan").status == RunStatus.RECLAIMED
    assert result.ran is True  # the lock being freed let a new run actually execute
    assert run_store.active_lock() is None or run_store.active_lock().run_id != "orphan"


def test_run_tick_does_not_reclaim_a_fresh_lock(tmp_path, run_store):
    run_store.start_run(run_id="fresh", slot_name="intraday", run_date=_TRADING_TIME.date().isoformat(), started_at=datetime.now(timezone.utc))

    result = run_tick(schedule_config=ScheduleConfig(), run_store=run_store, symbols="AAPL", now=_TRADING_TIME, staleness_seconds=1800, **_db_paths(tmp_path))

    assert result.reclaimed_run_ids == ()
    assert result.ran is False  # still held


def test_run_tick_records_a_failed_run_without_crashing_when_no_universe_is_given(tmp_path, run_store):
    """No --symbols/--watchlist-file for a shadow_run slot must fail ONE
    tick gracefully (FAILED RunRecord), never raise out of run_tick --
    a long-lived scheduler process must survive a misconfiguration."""
    result = run_tick(schedule_config=ScheduleConfig(), run_store=run_store, now=_TRADING_TIME, **_db_paths(tmp_path))

    assert result.ran is True
    assert "FAILED" in result.reason
    record = run_store.get_run(result.run_id)
    assert record.status == RunStatus.FAILED
    assert record.error is not None


def test_run_tick_does_not_crash_on_a_market_data_failure(tmp_path, run_store, monkeypatch):
    """A provider outage during one tick must degrade to a FAILED
    RunRecord, not propagate and kill a long-lived scheduler loop."""
    def _raise(*args, **kwargs):
        raise MarketDataError("simulated Yahoo outage")

    monkeypatch.setattr("market.data_provider.get_market_data_provider", _raise)

    result = run_tick(schedule_config=ScheduleConfig(), run_store=run_store, symbols="AAPL", now=_TRADING_TIME, **_db_paths(tmp_path))

    assert result.ran is True
    assert "FAILED" in result.reason
    assert run_store.get_run(result.run_id).status == RunStatus.FAILED


def test_run_tick_evaluate_and_learn_slot_runs_without_a_symbol(tmp_path, run_store):
    """The post_market slot's action is evaluate_and_learn -- it must
    not require --symbols at all (there is nothing new to scan)."""
    post_market_time = datetime(2026, 9, 3, 20, 0, tzinfo=IST)
    result = run_tick(schedule_config=ScheduleConfig(), run_store=run_store, now=post_market_time, **_db_paths(tmp_path))

    assert result.ran is True
    assert result.slot_name == "post_market"
    assert run_store.get_run(result.run_id).status == RunStatus.COMPLETED


def test_intraday_slot_does_not_rerun_within_the_frequency_window(tmp_path, run_store):
    first = run_tick(schedule_config=ScheduleConfig(), run_store=run_store, symbols="AAPL", benchmark="", now=_TRADING_TIME, **_db_paths(tmp_path))
    assert first.ran is True

    ten_minutes_later = _TRADING_TIME + timedelta(minutes=10)
    second = run_tick(schedule_config=ScheduleConfig(), run_store=run_store, symbols="AAPL", benchmark="", now=ten_minutes_later, **_db_paths(tmp_path))
    assert second.ran is False
    assert "No configured slot is due" in second.reason


def test_intraday_slot_reruns_after_the_frequency_window_elapses(tmp_path, run_store):
    first = run_tick(schedule_config=ScheduleConfig(), run_store=run_store, symbols="AAPL", benchmark="", now=_TRADING_TIME, **_db_paths(tmp_path))
    assert first.ran is True

    over_an_hour_later = _TRADING_TIME + timedelta(minutes=61)
    second = run_tick(schedule_config=ScheduleConfig(), run_store=run_store, symbols="AAPL", benchmark="", now=over_an_hour_later, **_db_paths(tmp_path))
    assert second.ran is True
    assert second.slot_name == "intraday"


def test_run_tick_accepts_a_naive_datetime_and_assumes_ist(tmp_path, run_store):
    naive_trading_time = datetime(2026, 9, 3, 11, 0)  # no tzinfo
    result = run_tick(schedule_config=ScheduleConfig(), run_store=run_store, symbols="AAPL", benchmark="", now=naive_trading_time, **_db_paths(tmp_path))
    assert result.ran is True
    assert result.slot_name == "intraday"


def test_finished_at_is_anchored_to_the_injected_now_not_real_wall_clock(tmp_path, run_store):
    """Regression: run_tick must pass `finished_at` explicitly rather
    than relying on SchedulerRunStore.finish_run's real-wall-clock
    default -- otherwise a caller-injected `now` (the CLI's `--now`
    dry-run flag, or a test) produces a self-inconsistent audit record
    whose finished_at silently disagrees with the represented time,
    and frequency-gated re-triggering becomes untestable/undependable."""
    result = run_tick(schedule_config=ScheduleConfig(), run_store=run_store, symbols="AAPL", benchmark="", now=_TRADING_TIME, **_db_paths(tmp_path))
    record = run_store.get_run(result.run_id)
    assert record.finished_at == _TRADING_TIME.astimezone(timezone.utc)


def test_resilient_flag_is_threaded_through_to_shadow_run(tmp_path, run_store, monkeypatch):
    """Phase 30: `run_tick(resilient=True)` must result in the SAME
    `--resilient` flag main.py's own `shadow-run` CLI accepts -- proves
    the scheduler doesn't silently drop it rather than actually asserting
    on printed metrics text (which test_cli_resilient.py already covers
    at the CLI layer)."""
    import main as main_module

    captured_args = {}
    real_run_shadow_run_command = main_module.run_shadow_run_command

    def _capture(args):
        captured_args["resilient"] = args.resilient
        return real_run_shadow_run_command(args)

    monkeypatch.setattr(main_module, "run_shadow_run_command", _capture)

    result = run_tick(schedule_config=ScheduleConfig(), run_store=run_store, symbols="AAPL", benchmark="", resilient=True, now=_TRADING_TIME, **_db_paths(tmp_path))

    assert result.ran is True
    assert captured_args.get("resilient") is True


def test_initial_capital_is_threaded_through_to_shadow_run(tmp_path, run_store, monkeypatch):
    """Mission auditability requirement: a scheduled shadow_run slot must
    be able to size its predictions against configured capital exactly
    like a manually-run `shadow-run --initial-capital ...` would -- the
    scheduler must not silently drop it."""
    import main as main_module

    captured_args = {}
    real_run_shadow_run_command = main_module.run_shadow_run_command

    def _capture(args):
        captured_args["initial_capital"] = args.initial_capital
        return real_run_shadow_run_command(args)

    monkeypatch.setattr(main_module, "run_shadow_run_command", _capture)

    result = run_tick(
        schedule_config=ScheduleConfig(), run_store=run_store, symbols="AAPL", benchmark="",
        initial_capital=20_000.0, now=_TRADING_TIME, **_db_paths(tmp_path),
    )

    assert result.ran is True
    assert captured_args.get("initial_capital") == 20_000.0

    from predictions.store import PredictionStore

    prediction_store = PredictionStore(tmp_path / "predictions.db")
    predictions = prediction_store.list_predictions()
    prediction_store.close()
    assert len(predictions) == 1
    assert predictions[0].risk_decision is not None
    assert predictions[0].risk_decision.account_equity == 20_000.0


def test_initial_capital_defaults_to_none_no_sizing_computed(tmp_path, run_store):
    """Backward compatibility: a scheduled slot with no --initial-capital
    behaves exactly as before this flag existed -- no risk_decision persisted."""
    result = run_tick(schedule_config=ScheduleConfig(), run_store=run_store, symbols="AAPL", benchmark="", now=_TRADING_TIME, **_db_paths(tmp_path))
    assert result.ran is True

    from predictions.store import PredictionStore

    prediction_store = PredictionStore(tmp_path / "predictions.db")
    predictions = prediction_store.list_predictions()
    prediction_store.close()
    assert len(predictions) == 1
    assert predictions[0].risk_decision is None


def test_custom_schedule_config_is_honored(tmp_path, run_store):
    """A YAML-configurable schedule must actually change what runs --
    not just parse without effect."""
    custom = ScheduleConfig(slots=(
        ScheduleSlot(name="only_slot", after=time(0, 0), before=None, frequency_minutes=None, action=SlotAction.SHADOW_RUN),
    ))
    result = run_tick(schedule_config=custom, run_store=run_store, symbols="AAPL", benchmark="", now=_TRADING_TIME, **_db_paths(tmp_path))
    assert result.ran is True
    assert result.slot_name == "only_slot"
