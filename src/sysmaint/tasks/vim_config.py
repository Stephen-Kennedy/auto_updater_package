"""Append a standard vim configuration to /etc/vim/vimrc.

Backs up the existing vimrc with a date-stamped suffix so the operator
can roll back if the additions cause an issue.
"""

from __future__ import annotations

import datetime as dt
import logging
import shutil
from importlib import resources
from pathlib import Path

from sysmaint.core.config import require_root

VIMRC_PATH = Path("/etc/vim/vimrc")
MARKER = "# === sysmaint vim_config block ==="


def execute(logger: logging.Logger) -> None:
    """Append the bundled vim snippet to /etc/vim/vimrc (idempotent)."""
    require_root()

    if not VIMRC_PATH.exists():
        logger.warning("No %s on this system; skipping vim config", VIMRC_PATH)
        return

    current = VIMRC_PATH.read_text()
    if MARKER in current:
        logger.info("Vim config already present in %s; skipping", VIMRC_PATH)
        return

    backup_path = VIMRC_PATH.with_suffix(
        VIMRC_PATH.suffix + ".bak_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    shutil.copy2(VIMRC_PATH, backup_path)
    logger.info("Backed up %s -> %s", VIMRC_PATH, backup_path)

    snippet = _load_snippet()
    block = f"\n{MARKER}\n{snippet.rstrip()}\n# === end sysmaint vim_config block ===\n"
    with VIMRC_PATH.open("a") as handle:
        handle.write(block)
    logger.info("Appended sysmaint vim config to %s", VIMRC_PATH)


def _load_snippet() -> str:
    """Read the bundled vim_utils.txt via importlib.resources.

    importlib.resources is the modern, stdlib-blessed way to ship data
    files inside a package — works whether the package is installed via
    pip, pipx, or zipped in an egg.
    """
    return resources.files("sysmaint.data").joinpath("vim_utils.txt").read_text()
