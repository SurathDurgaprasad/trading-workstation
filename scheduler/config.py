"""Phase 28 -- configurable schedule definition.

Roadmap's own wording: "The scheduler must be configurable. Do not
hardcode exact times as immutable business logic." The five slot
concepts it names (pre-market / market-open / periodic intraday /
pre-close / post-market evaluation) are DEFAULTS on `ScheduleConfig`,
not hardcoded logic -- every field is overridable via
`ScheduleConfig.from_yaml_file`, matching `market_data.universe.
MarketUniverse.from_yaml_file`'s own config-file convention.

Holiday awareness ("where feasible", per the roadmap): this project
integrates no NSE/BSE holiday-calendar API (none was integrated in any
prior phase, and fetching one is out of this phase's scope -- see
live/dhan/market_session.py's own identical, already-documented
limitation). Holidays are therefore a plain user-supplied date list,
default empty, never a hardcoded guess at "this year's" holidays --
the same "recognized, never silently faked" posture
market_data.universe.py already applies to unimplemented NIFTY modes.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path

import yaml

from scheduler.models import SlotAction
from scheduler.store import SchedulerRunStore

_TIME_FMT = "%H:%M"


def _parse_time(value: str | time) -> time:
    if isinstance(value, time):
        return value
    return datetime.strptime(value, _TIME_FMT).time()


def _parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


@dataclass(frozen=True)
class ScheduleSlot:
    name: str
    after: time
    """Eligible from this IST time-of-day (inclusive)."""
    before: time | None
    """Eligible until this IST time-of-day (exclusive). None = no upper
    bound (eligible through end of day)."""
    frequency_minutes: int | None
    """None = at most once per trading day. An integer = re-eligible
    every N minutes within [after, before) -- e.g. an intraday scan
    slot re-triggering hourly during market hours."""
    action: SlotAction
    enabled: bool = True

    def is_within_window(self, local_time: time) -> bool:
        if local_time < self.after:
            return False
        if self.before is not None and local_time >= self.before:
            return False
        return True

    def is_due(self, *, now: datetime, run_store: SchedulerRunStore, run_date: str) -> bool:
        if not self.enabled:
            return False
        if not self.is_within_window(now.time()):
            return False
        if self.frequency_minutes is None:
            return not run_store.has_completed_today(slot_name=self.name, run_date=run_date)
        latest = run_store.latest_run_for_slot_today(slot_name=self.name, run_date=run_date)
        if latest is None:
            return True
        reference = latest.finished_at or latest.started_at
        elapsed_minutes = (now - reference).total_seconds() / 60.0
        return elapsed_minutes >= self.frequency_minutes


def _default_slots() -> tuple[ScheduleSlot, ...]:
    """Matches the roadmap's own five named concepts exactly. Every time
    boundary here doubles as a sane default AND a documented example of
    what a `--config` YAML file can override -- none of it is meant to
    be the one true schedule."""
    return (
        ScheduleSlot(name="pre_market", after=time(8, 45), before=time(9, 15), frequency_minutes=None, action=SlotAction.SHADOW_RUN),
        ScheduleSlot(name="market_open", after=time(9, 15), before=time(9, 30), frequency_minutes=None, action=SlotAction.SHADOW_RUN),
        ScheduleSlot(name="intraday", after=time(9, 30), before=time(15, 15), frequency_minutes=60, action=SlotAction.SHADOW_RUN),
        ScheduleSlot(name="pre_close", after=time(15, 15), before=time(15, 30), frequency_minutes=None, action=SlotAction.SHADOW_RUN),
        ScheduleSlot(name="post_market", after=time(15, 30), before=None, frequency_minutes=None, action=SlotAction.EVALUATE_AND_LEARN),
    )


@dataclass(frozen=True)
class ScheduleConfig:
    slots: tuple[ScheduleSlot, ...] = field(default_factory=_default_slots)
    holidays: tuple[date, ...] = ()
    """User-supplied exchange holiday dates. Empty by default -- see
    module docstring. A date in this list is treated as CLOSED
    regardless of what live.dhan.market_session.current_market_session
    would otherwise report for that weekday/time."""

    def is_holiday(self, day: date) -> bool:
        return day in self.holidays

    def due_slot(self, *, now: datetime, run_store: SchedulerRunStore, run_date: str) -> ScheduleSlot | None:
        """First due slot in configured order -- stable, deterministic;
        never more than one slot's worth of work per tick. A second due
        slot at the same tick is simply picked up on the NEXT tick, same
        posture as `shadow-run` itself being "one pass, not a loop"."""
        for slot in self.slots:
            if slot.is_due(now=now, run_store=run_store, run_date=run_date):
                return slot
        return None

    @classmethod
    def from_yaml_file(cls, path: Path | str) -> "ScheduleConfig":
        with open(path) as handle:
            raw = yaml.safe_load(handle) or {}

        holidays = tuple(_parse_date(d) for d in raw.get("holidays") or ())

        raw_slots = raw.get("slots")
        if not raw_slots:
            return cls(holidays=holidays)

        slots = tuple(
            ScheduleSlot(
                name=item["name"],
                after=_parse_time(item["after"]),
                before=_parse_time(item["before"]) if item.get("before") is not None else None,
                frequency_minutes=item.get("frequency_minutes"),
                action=SlotAction(item.get("action", SlotAction.SHADOW_RUN.value)),
                enabled=item.get("enabled", True),
            )
            for item in raw_slots
        )
        return cls(slots=slots, holidays=holidays)
