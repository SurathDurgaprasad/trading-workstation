import tempfile
from datetime import date, datetime, time
from pathlib import Path

import pytest

from scheduler.config import ScheduleConfig, ScheduleSlot, _default_slots
from scheduler.models import RunStatus, SlotAction
from scheduler.store import SchedulerRunStore


@pytest.fixture
def store(tmp_path):
    s = SchedulerRunStore(tmp_path / "runs.db")
    yield s
    s.close()


def test_default_slots_match_roadmap_five_concepts():
    names = [s.name for s in _default_slots()]
    assert names == ["pre_market", "market_open", "intraday", "pre_close", "post_market"]


def test_is_within_window_respects_after_and_before():
    slot = ScheduleSlot(name="x", after=time(9, 0), before=time(9, 15), frequency_minutes=None, action=SlotAction.SHADOW_RUN)
    assert slot.is_within_window(time(9, 0)) is True
    assert slot.is_within_window(time(9, 14, 59)) is True
    assert slot.is_within_window(time(9, 15)) is False  # exclusive upper bound
    assert slot.is_within_window(time(8, 59, 59)) is False


def test_is_within_window_with_no_upper_bound():
    slot = ScheduleSlot(name="x", after=time(15, 30), before=None, frequency_minutes=None, action=SlotAction.EVALUATE_AND_LEARN)
    assert slot.is_within_window(time(23, 59)) is True
    assert slot.is_within_window(time(0, 0)) is False  # before `after`


def test_once_per_day_slot_is_due_only_before_first_completion(store):
    slot = ScheduleSlot(name="pre_market", after=time(8, 45), before=time(9, 15), frequency_minutes=None, action=SlotAction.SHADOW_RUN)
    now = datetime(2026, 9, 3, 9, 0)
    assert slot.is_due(now=now, run_store=store, run_date="2026-09-03") is True

    store.start_run(run_id="r1", slot_name="pre_market", run_date="2026-09-03", started_at=datetime(2026, 9, 3, 3, 30))
    store.finish_run(run_id="r1", status=RunStatus.COMPLETED)
    assert slot.is_due(now=now, run_store=store, run_date="2026-09-03") is False
    # A different day is unaffected.
    assert slot.is_due(now=now, run_store=store, run_date="2026-09-04") is True


def test_frequency_gated_slot_is_due_again_only_after_elapsed_minutes(store):
    from scheduler.models import RunStatus

    slot = ScheduleSlot(name="intraday", after=time(9, 30), before=time(15, 15), frequency_minutes=60, action=SlotAction.SHADOW_RUN)
    run_date = "2026-09-03"

    # Never run yet today -- due.
    assert slot.is_due(now=datetime(2026, 9, 3, 10, 0), run_store=store, run_date=run_date) is True

    store.start_run(run_id="r1", slot_name="intraday", run_date=run_date, started_at=datetime(2026, 9, 3, 10, 0))
    store.finish_run(run_id="r1", status=RunStatus.COMPLETED, finished_at=datetime(2026, 9, 3, 10, 0))

    # 30 minutes later -- not due yet (frequency is 60).
    assert slot.is_due(now=datetime(2026, 9, 3, 10, 30), run_store=store, run_date=run_date) is False
    # 61 minutes later -- due again.
    assert slot.is_due(now=datetime(2026, 9, 3, 11, 1), run_store=store, run_date=run_date) is True


def test_disabled_slot_is_never_due(store):
    slot = ScheduleSlot(name="x", after=time(0, 0), before=None, frequency_minutes=None, action=SlotAction.SHADOW_RUN, enabled=False)
    assert slot.is_due(now=datetime(2026, 9, 3, 12, 0), run_store=store, run_date="2026-09-03") is False


def test_due_slot_returns_first_due_in_configured_order(store):
    a = ScheduleSlot(name="a", after=time(0, 0), before=None, frequency_minutes=None, action=SlotAction.SHADOW_RUN)
    b = ScheduleSlot(name="b", after=time(0, 0), before=None, frequency_minutes=None, action=SlotAction.SHADOW_RUN)
    config = ScheduleConfig(slots=(a, b))
    due = config.due_slot(now=datetime(2026, 9, 3, 12, 0), run_store=store, run_date="2026-09-03")
    assert due is not None and due.name == "a"


def test_due_slot_returns_none_when_nothing_is_due(store):
    config = ScheduleConfig(slots=())
    assert config.due_slot(now=datetime(2026, 9, 3, 12, 0), run_store=store, run_date="2026-09-03") is None


def test_is_holiday():
    config = ScheduleConfig(holidays=(date(2026, 10, 20),))
    assert config.is_holiday(date(2026, 10, 20)) is True
    assert config.is_holiday(date(2026, 10, 21)) is False


def test_default_config_has_no_holidays():
    assert ScheduleConfig().holidays == ()


def test_from_yaml_file_parses_slots_and_holidays():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "schedule.yaml"
        path.write_text(
            """
holidays:
  - 2026-10-20
  - 2026-01-26
slots:
  - name: custom_scan
    after: "10:00"
    before: "10:30"
    frequency_minutes: 15
    action: shadow_run
  - name: custom_eval
    after: "16:00"
    action: evaluate_and_learn
    enabled: false
"""
        )
        config = ScheduleConfig.from_yaml_file(path)

    assert config.holidays == (date(2026, 10, 20), date(2026, 1, 26))
    assert len(config.slots) == 2
    assert config.slots[0].name == "custom_scan"
    assert config.slots[0].after == time(10, 0)
    assert config.slots[0].before == time(10, 30)
    assert config.slots[0].frequency_minutes == 15
    assert config.slots[0].action == SlotAction.SHADOW_RUN
    assert config.slots[1].name == "custom_eval"
    assert config.slots[1].before is None
    assert config.slots[1].action == SlotAction.EVALUATE_AND_LEARN
    assert config.slots[1].enabled is False


def test_from_yaml_file_with_no_slots_key_falls_back_to_defaults():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "schedule.yaml"
        path.write_text("holidays:\n  - 2026-10-20\n")
        config = ScheduleConfig.from_yaml_file(path)

    assert config.holidays == (date(2026, 10, 20),)
    assert [s.name for s in config.slots] == [s.name for s in _default_slots()]
