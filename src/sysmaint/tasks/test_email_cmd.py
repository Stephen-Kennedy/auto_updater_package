"""`sysmaint test-email` — send a test message using the current config."""

from __future__ import annotations

import datetime as dt
import logging

from sysmaint.core import email as email_mod
from sysmaint.core import system
from sysmaint.core.config import Config


def execute(config: Config, logger: logging.Logger) -> int:
    """Send a test email. Returns 0 on success, 1 on failure."""
    host = system.get_host_info()
    body = (
        f"This is a sysmaint test email.\n\n"
        f"Host:   {host.hostname} ({host.fqdn})\n"
        f"OS:     {host.distro}\n"
        f"Kernel: {host.kernel}\n"
        f"Time:   {dt.datetime.now().isoformat(timespec='seconds')}\n\n"
        f"If you got this, the SMTP relay is working."
    )
    try:
        email_mod.send_email(
            from_addr=config.email.from_addr,
            to_addr=config.email.to_addr,
            smtp_server=config.email.smtp_server,
            smtp_port=config.email.smtp_port,
            password=config.email.password,
            subject="sysmaint test email",
            body=body,
            logger=logger,
        )
    except email_mod.EmailError as exc:
        print(f"Failed: {exc}")
        return 1
    print(f"Sent test email to {config.email.to_addr}")
    return 0
