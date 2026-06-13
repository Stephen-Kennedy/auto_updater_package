"""Pi-hole update task — optional, only enabled on DNS boxes.

This is shipped in the package so a Pi-hole box can install the same
sysmaint distribution and just enable the extra timer. It is NOT in the
default weekly run.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sysmaint.core import email as email_mod
from sysmaint.core.config import Config
from sysmaint.core.runner import CommandError, run_command

PIHOLE_BINARY = Path("/usr/local/bin/pihole")
_PIHOLE_TIMEOUT_SEC = 15 * 60


def execute(config: Config, logger: logging.Logger) -> bool:
    """Run `pihole -up` and email the result. Returns True on success."""
    if not PIHOLE_BINARY.exists():
        logger.warning("Pi-hole not installed at %s; skipping", PIHOLE_BINARY)
        return True  # Not a failure — just nothing to do.

    logger.info("Starting Pi-hole update")
    try:
        result = run_command(
            [str(PIHOLE_BINARY), "-up"],
            timeout=_PIHOLE_TIMEOUT_SEC,
            check=False,
            logger=logger,
        )
    except CommandError as exc:
        result = exc.result

    if result.succeeded:
        subject = "Pi-hole update succeeded"
        body = f"Pi-hole updated successfully in {result.duration:.0f}s.\n\n{result.stdout[-2000:]}"
    else:
        subject = "Pi-hole update FAILED"
        body = (
            f"Pi-hole update failed (exit {result.returncode}) after {result.duration:.0f}s.\n\n"
            f"stderr:\n{result.stderr[-2000:]}\n\n"
            f"stdout:\n{result.stdout[-1000:]}"
        )

    try:
        email_mod.send_email(
            from_addr=config.email.from_addr,
            to_addr=config.email.to_addr,
            smtp_server=config.email.smtp_server,
            smtp_port=config.email.smtp_port,
            password=config.email.password,
            subject=subject,
            body=body,
            logger=logger,
        )
    except email_mod.EmailError as exc:
        logger.error("Failed to send Pi-hole notification: %s", exc)

    return result.succeeded
