"""Phase 39 -- core.logging.add_rotating_file_handler: an optional,
size-bounded file handler for long-run unattended operation (`schedule
loop`). Every test removes and closes any handler it adds -- the root
logger is process-global, and an unclosed file handler would leak into
other tests' output and (on Windows) block tmp_path cleanup with a
locked-file error."""

import logging
import logging.handlers

import pytest

from core.logging import add_rotating_file_handler


@pytest.fixture
def clean_root_handlers():
    root = logging.getLogger()
    before = list(root.handlers)
    yield root
    for handler in list(root.handlers):
        if handler not in before:
            root.removeHandler(handler)
            handler.close()


def test_add_rotating_file_handler_creates_the_file_and_writes_to_it(tmp_path, clean_root_handlers):
    log_path = tmp_path / "scheduler.log"
    add_rotating_file_handler(log_path)

    logging.getLogger("test_core_logging").warning("hello from a test")
    for handler in clean_root_handlers.handlers:
        handler.flush()

    assert log_path.exists()
    assert "hello from a test" in log_path.read_text()


def test_add_rotating_file_handler_is_a_rotating_file_handler_with_the_given_bounds(tmp_path, clean_root_handlers):
    log_path = tmp_path / "scheduler.log"
    add_rotating_file_handler(log_path, max_bytes=1234, backup_count=2)

    handlers = [h for h in clean_root_handlers.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(handlers) == 1
    assert handlers[0].maxBytes == 1234
    assert handlers[0].backupCount == 2


def test_add_rotating_file_handler_never_replaces_the_existing_stdout_handler(tmp_path, clean_root_handlers):
    from core.logging import setup_logging

    setup_logging()  # a no-op if a handler already exists from an earlier test/process, which is fine here
    before_non_file_handlers = [h for h in clean_root_handlers.handlers if not isinstance(h, logging.handlers.RotatingFileHandler)]

    add_rotating_file_handler(tmp_path / "scheduler.log")

    after_non_file_handlers = [h for h in clean_root_handlers.handlers if not isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(after_non_file_handlers) == len(before_non_file_handlers)


def test_add_rotating_file_handler_is_idempotent_for_the_same_path(tmp_path, clean_root_handlers):
    log_path = tmp_path / "scheduler.log"
    add_rotating_file_handler(log_path)
    add_rotating_file_handler(log_path)
    add_rotating_file_handler(str(log_path))  # same path, different string identity -- must resolve equal

    handlers = [h for h in clean_root_handlers.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(handlers) == 1


def test_add_rotating_file_handler_different_paths_get_separate_handlers(tmp_path, clean_root_handlers):
    add_rotating_file_handler(tmp_path / "a.log")
    add_rotating_file_handler(tmp_path / "b.log")

    handlers = [h for h in clean_root_handlers.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(handlers) == 2


def test_add_rotating_file_handler_creates_parent_directories(tmp_path, clean_root_handlers):
    log_path = tmp_path / "nested" / "dir" / "scheduler.log"
    add_rotating_file_handler(log_path)
    assert log_path.parent.exists()
