import logging

_logger = logging.getLogger("trading.events")


def log_event(event: str, **fields: object) -> None:
    """Emit one structured log line: `event=<name> key=value key=value ...`.

    Deliberately built on stdlib logging rather than a new dependency —
    the pipeline events listed below are checkpoints for reading logs, not
    a metrics/tracing system.
    """
    rendered = " ".join(f"{key}={value!r}" for key, value in fields.items())
    _logger.info("event=%s %s", event, rendered)
