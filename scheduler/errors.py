class SchedulerConfigurationError(Exception):
    """Raised for a scheduler misconfiguration that must never reach
    main.py's `run_shadow_run_command`/etc. as a bare `sys.exit()` --
    those functions are written for a one-shot CLI invocation where
    exiting the process is fine; the scheduler is a long-lived process
    where the same condition must instead fail ONE tick, gracefully."""


class InvalidRunTransitionError(Exception):
    """Autonomous hardening cycle 8 -- found via a real state-machine
    attack, not theoretical: SchedulerRunStore.finish_run() previously
    had NO terminal-state guard, unlike every other state machine in
    this project (Position, PaperOrder). A "zombie" process that took
    longer than the staleness window to notice its own run had already
    been RECLAIMED by a newer process could still call finish_run(...,
    COMPLETED) and silently overwrite RECLAIMED back to COMPLETED --
    corrupting the audit trail (an operator reading `schedule status`
    would see a clean "completed" run with no trace it was actually
    orphaned and superseded). Raised when a caller tries to finish a
    run that is no longer RUNNING -- RECLAIMED, COMPLETED, and FAILED
    are all terminal, exactly like CLOSED/FILLED elsewhere in this
    project."""

    def __init__(self, *, run_id: str, attempted_status: str):
        self.run_id = run_id
        self.attempted_status = attempted_status
        super().__init__(
            f"Cannot finish run {run_id!r} as {attempted_status!r} -- it is no longer RUNNING "
            "(already terminal, e.g. reclaimed by another process as stale). This run's audit "
            "trail is left as-is rather than silently overwritten."
        )
