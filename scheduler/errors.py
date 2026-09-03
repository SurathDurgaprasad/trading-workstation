class SchedulerConfigurationError(Exception):
    """Raised for a scheduler misconfiguration that must never reach
    main.py's `run_shadow_run_command`/etc. as a bare `sys.exit()` --
    those functions are written for a one-shot CLI invocation where
    exiting the process is fine; the scheduler is a long-lived process
    where the same condition must instead fail ONE tick, gracefully."""
