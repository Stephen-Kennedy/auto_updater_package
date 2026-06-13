"""Logger factory with rotation and idempotent handler attachment.

A previous bug: calling setup_logger() twice with the same name attached
duplicate handlers, so every line got logged twice. This factory checks
for existing handlers before adding.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logger(
    name: str,
    log_file: Path | str,
    *,
    level: int = logging.INFO,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
    console: bool = False,
) -> logging.Logger:
    """Return a logger configured with a rotating file handler.

    Safe to call multiple times with the same name — handlers are only
    added once per (name, log_file) pair.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    log_path = Path(log_file)
    # Identify our handlers by an attribute we set, so a second call doesn't
    # re-add them even if other code has touched this logger.
    tag_file = f"sysmaint-file::{log_path}"
    tag_console = "sysmaint-console"

    if not any(getattr(h, "_sysmaint_tag", None) == tag_file for h in logger.handlers):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path, maxBytes=max_bytes, backupCount=backup_count
        )
        file_handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
        file_handler._sysmaint_tag = tag_file  # type: ignore[attr-defined]
        logger.addHandler(file_handler)

    if console and not any(
        getattr(h, "_sysmaint_tag", None) == tag_console for h in logger.handlers
    ):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        console_handler._sysmaint_tag = tag_console  # type: ignore[attr-defined]
        logger.addHandler(console_handler)

    # Don't bubble up to the root logger — avoids double output if root
    # has its own handlers configured by other code.
    logger.propagate = False
    return logger
