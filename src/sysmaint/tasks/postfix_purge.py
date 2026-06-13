"""Remove Postfix and the sysmaint-managed config files.

Idempotent: safe to run on a box where Postfix is already gone — apt
will just no-op, and the file removals are guarded by existence checks.
"""

from __future__ import annotations

import glob
import logging
from pathlib import Path

from sysmaint.core.config import require_root
from sysmaint.core.runner import APT_ENV, CommandError, apt_command, run_command


def execute(logger: logging.Logger) -> None:
    """Purge Postfix and clean up its config files."""
    require_root()
    logger.info("Purging Postfix")

    # Each step is tolerant of failure — a missing apt package or a
    # already-deleted file shouldn't abort the cleanup.
    _run_tolerant(apt_command(["remove", "--purge", "postfix"]), logger, env=APT_ENV)
    _run_tolerant(apt_command(["autoremove"]), logger, env=APT_ENV)
    _run_tolerant(["apt-get", "clean"], logger, env=APT_ENV)

    _remove_path(Path("/etc/postfix"), logger, recursive=True)
    _remove_path(Path("/etc/aliases.db"), logger)

    # Previous version used `rm -f /var/log/mail.*` which doesn't glob through
    # subprocess. Use Python's glob to expand correctly.
    for path_str in glob.glob("/var/log/mail.*"):
        _remove_path(Path(path_str), logger)

    logger.info("Postfix purge complete")


def _run_tolerant(cmd: list[str], logger: logging.Logger, **kwargs: object) -> None:
    """Run a command but downgrade failures to warnings."""
    try:
        run_command(cmd, timeout=600, check=True, logger=logger, **kwargs)  # type: ignore[arg-type]
    except CommandError as exc:
        logger.warning("Tolerated failure: %s", exc)


def _remove_path(path: Path, logger: logging.Logger, *, recursive: bool = False) -> None:
    if not path.exists() and not path.is_symlink():
        return
    try:
        if recursive and path.is_dir():
            import shutil

            shutil.rmtree(path)
        else:
            path.unlink()
        logger.info("Removed %s", path)
    except OSError as exc:
        logger.warning("Could not remove %s: %s", path, exc)
