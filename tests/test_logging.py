"""Tests for sysmaint.core.logging_utils — handler dedup regression."""

from __future__ import annotations

import logging
from pathlib import Path

from sysmaint.core.logging_utils import setup_logger


def test_repeated_setup_does_not_duplicate_handlers(tmp_path: Path) -> None:
    """Regression: the legacy logger added a new file handler every time
    setup_logger was called with the same name, causing every line to be
    written 2x, 3x, etc."""
    log_path = tmp_path / "x.log"
    log_name = "sysmaint.test.dedup"

    logger1 = setup_logger(log_name, log_path)
    logger2 = setup_logger(log_name, log_path)
    logger3 = setup_logger(log_name, log_path)

    assert logger1 is logger2 is logger3
    # Exactly one file handler regardless of how many times we set up.
    file_handlers = [
        h for h in logger1.handlers if getattr(h, "_sysmaint_tag", "").startswith("sysmaint-file::")
    ]
    assert len(file_handlers) == 1


def test_console_handler_only_added_once(tmp_path: Path) -> None:
    log_path = tmp_path / "y.log"
    log_name = "sysmaint.test.console-dedup"

    setup_logger(log_name, log_path, console=True)
    logger = setup_logger(log_name, log_path, console=True)

    console_handlers = [
        h for h in logger.handlers if getattr(h, "_sysmaint_tag", None) == "sysmaint-console"
    ]
    assert len(console_handlers) == 1


def test_log_messages_appear_in_file(tmp_path: Path) -> None:
    log_path = tmp_path / "z.log"
    logger = setup_logger("sysmaint.test.write", log_path, level=logging.DEBUG)
    logger.info("hello world")
    for handler in logger.handlers:
        handler.flush()
    contents = log_path.read_text()
    assert "hello world" in contents
