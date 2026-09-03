import logging
import logging.handlers
import sys
from pathlib import Path

from core.config import get_settings


def setup_logging(level: str | None = None) -> None:
    settings = get_settings()
    log_level = getattr(logging, (level or settings.log_level).upper(), logging.INFO)

    root = logging.getLogger()
    if root.handlers:
        root.setLevel(log_level)
        return

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def add_rotating_file_handler(path: str | Path, *, max_bytes: int = 10 * 1024 * 1024, backup_count: int = 5, level: str | None = None) -> None:
    """Phase 39 -- long-run operations: `schedule loop` is the one command
    meant to run unattended for days, but setup_logging() only ever
    writes to stdout -- lost the moment the terminal/process that
    started it closes. This attaches a SEPARATE, size-bounded
    RotatingFileHandler to the same root logger, alongside (never
    replacing) the existing stdout handler, so console behavior is
    unchanged whether or not this is called.

    Idempotent by resolved path: calling this again for a path that
    already has a handler attached (e.g. a caller invoked more than
    once against the same --log-file) is a no-op, so it can never
    silently accumulate duplicate handlers and double-log every line.
    """
    settings = get_settings()
    log_level = getattr(logging, (level or settings.log_level).upper(), logging.INFO)
    resolved = str(Path(path).resolve())

    root = logging.getLogger()
    for existing in root.handlers:
        if isinstance(existing, logging.handlers.RotatingFileHandler) and getattr(existing, "baseFilename", None) == resolved:
            return

    Path(resolved).parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(resolved, maxBytes=max_bytes, backupCount=backup_count)
    handler.setLevel(log_level)
    handler.setFormatter(logging.Formatter(fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    root.addHandler(handler)
    if root.level == 0 or log_level < root.level:
        root.setLevel(log_level)
