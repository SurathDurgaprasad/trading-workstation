"""Phase 28 -- one scheduler tick: decide whether ANY configured slot is
due right now, and if so, execute it exactly once.

Deliberately reuses main.py's existing, already-tested command functions
(`run_shadow_run_command`, `run_evaluate_command`, `run_learn_command`)
rather than reimplementing the scan->research->decide->predict->evaluate->
learn wiring a second time -- the same "orchestration only, reuses each
stage's own existing function" posture `shadow-run` itself documents.
Imported deferred inside `_execute_slot`, matching this project's
established import-cost discipline (main.py pulls in `graph`/`agents.*`
lazily for the same reason).

`run_tick` never raises for an ordinary operational failure (a bad
symbol, Yahoo being unreachable, a stale lock) -- those become a FAILED
RunRecord and a `TickResult` the caller can log and move past. It DOES
propagate a genuine programming error (e.g. an unrecognized SlotAction)
since that is not something retrying the next tick can fix.
"""

import contextlib
import io
from datetime import datetime, timezone

from live.dhan.market_session import IST, current_market_session
from scheduler.config import ScheduleConfig, ScheduleSlot
from scheduler.errors import SchedulerConfigurationError
from scheduler.models import RunRecord, RunStatus, SlotAction, TickResult
from scheduler.store import SchedulerRunStore


def _run_and_capture(command_fn, args) -> str:
    """Runs an existing main.py command function, tees its stdout to the
    real stdout (so an operator/external log still sees everything the
    equivalent standalone CLI invocation would print), and returns the
    last non-blank printed line as a short audit `detail` string -- the
    full text is never lost, just not duplicated into scheduler_runs.db
    verbatim (that db's `data_json` is for run bookkeeping, not a second
    copy of the scan/research/decision databases the command already
    persists to)."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        command_fn(args)
    output = buffer.getvalue()
    print(output, end="")
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        return "(no output)"
    # `shadow-run`'s own footer ("Run summary: N candidate(s) scanned; ...")
    # is purpose-built as a one-line summary -- prefer it when present
    # over whatever happens to be the LAST printed line (e.g. `learn`'s
    # trailing notes bullets, which are informative but not a summary).
    for line in reversed(lines):
        if line.startswith("Run summary:"):
            return line
    return lines[-1]


def _execute_slot(
    slot: ScheduleSlot, *,
    symbols: str | None, watchlist_file: str | None,
    period: str, interval: str, benchmark: str, news_limit: int, horizon_bars: int,
    paper_db: str | None, with_ai: bool, resilient: bool, live_source: str | None,
    scanner_db: str | None, research_db: str | None, decision_db: str | None, predictions_db: str | None,
    initial_capital: float | None = None,
    paper_execute: bool = False,
    state_db: str | None = None,
    max_holding_bars: int | None = None,
) -> str:
    from main import parse_args, run_evaluate_command, run_learn_command, run_shadow_run_command

    if slot.action == SlotAction.SHADOW_RUN:
        if not symbols and not watchlist_file:
            raise SchedulerConfigurationError(
                f"Slot {slot.name!r} needs a market universe -- pass --symbols or --watchlist-file to `schedule tick`/`schedule loop`."
            )
        argv = ["shadow-run"]
        argv += ["--watchlist-file", watchlist_file] if watchlist_file else ["--symbols", symbols]
        argv += ["--period", period, "--interval", interval, "--benchmark", benchmark,
                 "--news-limit", str(news_limit), "--horizon-bars", str(horizon_bars)]
        if paper_db:
            argv += ["--paper-db", paper_db]
        if with_ai:
            argv += ["--with-ai"]
        if resilient:
            argv += ["--resilient"]
        if live_source:
            argv += ["--live-source", live_source]
        if scanner_db:
            argv += ["--scanner-db", scanner_db]
        if research_db:
            argv += ["--research-db", research_db]
        if decision_db:
            argv += ["--decision-db", decision_db]
        if predictions_db:
            argv += ["--predictions-db", predictions_db]
        if initial_capital is not None:
            argv += ["--initial-capital", str(initial_capital)]
        # Explicit opt-in, default OFF: unattended paper execution (submitting
        # real PENDING paper orders AND advancing existing ones with fresh
        # data via paper/advance.py, both already wired into
        # run_shadow_run_command itself) only happens when the operator
        # passes --paper-execute to `schedule tick`/`schedule loop` -- never
        # implicitly just because a slot happens to be a shadow_run slot.
        # main.py's own --paper-execute validation (requires --initial-capital,
        # --paper-db, --state-db all given) applies unchanged here since this
        # still goes through the real `shadow-run` argument parser.
        if paper_execute:
            argv += ["--paper-execute"]
        if state_db:
            argv += ["--state-db", state_db]
        if max_holding_bars is not None:
            argv += ["--max-holding-bars", str(max_holding_bars)]
        return _run_and_capture(run_shadow_run_command, parse_args(argv))

    if slot.action == SlotAction.EVALUATE_AND_LEARN:
        eval_argv = ["evaluate", "--period", period]
        if predictions_db:
            eval_argv += ["--db", predictions_db]
        if resilient:
            eval_argv += ["--resilient"]
        eval_detail = _run_and_capture(run_evaluate_command, parse_args(eval_argv))

        learn_argv = ["learn"]
        if resilient:
            learn_argv += ["--resilient"]
        if predictions_db:
            learn_argv += ["--predictions-db", predictions_db]
        if decision_db:
            learn_argv += ["--decision-db", decision_db]
        learn_detail = _run_and_capture(run_learn_command, parse_args(learn_argv))
        return f"evaluate: {eval_detail} | learn: {learn_detail}"

    raise ValueError(f"Unknown SlotAction: {slot.action!r} -- this is a scheduler bug, not an operational failure.")


def run_tick(
    *,
    schedule_config: ScheduleConfig,
    run_store: SchedulerRunStore,
    symbols: str | None = None,
    watchlist_file: str | None = None,
    period: str = "1y",
    interval: str = "1d",
    benchmark: str = "^NSEI",
    news_limit: int = 10,
    horizon_bars: int = 20,
    paper_db: str | None = None,
    with_ai: bool = False,
    resilient: bool = False,
    live_source: str | None = None,
    scanner_db: str | None = None,
    research_db: str | None = None,
    decision_db: str | None = None,
    predictions_db: str | None = None,
    initial_capital: float | None = None,
    paper_execute: bool = False,
    state_db: str | None = None,
    max_holding_bars: int | None = None,
    staleness_seconds: float = 1800.0,
    now: datetime | None = None,
) -> TickResult:
    now_ist = now or datetime.now(IST)
    now_ist = now_ist.replace(tzinfo=IST) if now_ist.tzinfo is None else now_ist.astimezone(IST)
    now_utc = now_ist.astimezone(timezone.utc)
    run_date = now_ist.date().isoformat()

    reclaimed = run_store.reclaim_stale_locks(staleness_seconds=staleness_seconds, now=now_utc)
    reclaimed_ids = tuple(r.run_id for r in reclaimed)

    if schedule_config.is_holiday(now_ist.date()):
        return TickResult(ran=False, reason=f"{run_date} is a configured exchange holiday -- no slot will run.", reclaimed_run_ids=reclaimed_ids)

    active = run_store.active_lock()
    if active is not None:
        return TickResult(
            ran=False,
            reason=(
                f"Another run is already in progress (run_id={active.run_id[:12]}, slot={active.slot_name!r}, "
                f"started {active.started_at.isoformat()}) -- skipping this tick to avoid an overlapping run."
            ),
            reclaimed_run_ids=reclaimed_ids,
        )

    session = current_market_session(now_ist)
    if not session.is_weekday:
        return TickResult(ran=False, reason=f"{now_ist.strftime('%A')} is not a trading day.", reclaimed_run_ids=reclaimed_ids)

    due = schedule_config.due_slot(now=now_ist, run_store=run_store, run_date=run_date)
    if due is None:
        return TickResult(ran=False, reason="No configured slot is due at this time.", reclaimed_run_ids=reclaimed_ids)

    run_id = RunRecord.new_id()
    started = run_store.try_start_run(run_id=run_id, slot_name=due.name, run_date=run_date, started_at=now_utc)
    if started is None:
        # Lost a race against another process that started a run between
        # this tick's earlier `active_lock()` check and now -- see
        # `SchedulerRunStore.try_start_run`'s docstring. Correctness does
        # not depend on this branch being reached often; it exists so a
        # genuine race never silently produces two overlapping runs.
        active = run_store.active_lock()
        detail = f"run_id={active.run_id[:12]}, slot={active.slot_name!r}" if active is not None else "lock contention"
        return TickResult(ran=False, reason=f"Another run started concurrently ({detail}) -- skipping this tick to avoid an overlapping run.", reclaimed_run_ids=reclaimed_ids)

    try:
        detail = _execute_slot(
            due, symbols=symbols, watchlist_file=watchlist_file, period=period, interval=interval,
            benchmark=benchmark, news_limit=news_limit, horizon_bars=horizon_bars, paper_db=paper_db,
            with_ai=with_ai, resilient=resilient, live_source=live_source, scanner_db=scanner_db,
            research_db=research_db, decision_db=decision_db, predictions_db=predictions_db,
            initial_capital=initial_capital, paper_execute=paper_execute, state_db=state_db,
            max_holding_bars=max_holding_bars,
        )
    except Exception as exc:  # noqa: BLE001 -- a failed tick must never crash a long-lived scheduler process
        # `finished_at=now_utc`, not the default real wall-clock: this tick's
        # OWN clock reading is what every later is_due/frequency comparison
        # must be anchored to, so a caller-injected `now` (the `--now`
        # dry-run flag, or a test) stays internally consistent end-to-end.
        # In real production use `now` is freshly read at tick-start anyway,
        # so this is at most a few seconds "early" relative to actual
        # completion -- an accepted, documented tradeoff for determinism.
        run_store.finish_run(run_id=run_id, status=RunStatus.FAILED, detail=f"{type(exc).__name__}: {exc}", error=str(exc), finished_at=now_utc)
        return TickResult(ran=True, reason=f"Slot {due.name!r} FAILED: {exc}", slot_name=due.name, run_id=run_id, reclaimed_run_ids=reclaimed_ids)

    run_store.finish_run(run_id=run_id, status=RunStatus.COMPLETED, detail=detail, finished_at=now_utc)
    return TickResult(ran=True, reason=f"Slot {due.name!r} completed: {detail}", slot_name=due.name, run_id=run_id, reclaimed_run_ids=reclaimed_ids)
