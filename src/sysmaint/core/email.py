"""SMTP email delivery with STARTTLS, retry, and per-host subject prefixing.

Design notes:
- STARTTLS uses an explicit `ssl.create_default_context()` so cert
  verification is unambiguous regardless of Python version.
- Three attempts with exponential-ish backoff (5s, 25s). Authentication
  failures are NOT retried — credentials are wrong, retrying won't help.
- Subject is always prefixed with `[hostname]` so a flood of fleet emails
  in your inbox is visually scannable.
"""

from __future__ import annotations

import logging
import smtplib
import socket
import ssl
import time
from email.mime.text import MIMEText

_BACKOFF_SECONDS = (5, 25)  # delay before retry 2 and retry 3
_DEFAULT_TIMEOUT = 30
_MAX_ATTEMPTS = 3


class EmailError(Exception):
    """Raised when an email send ultimately fails."""


def send_email(
    *,
    from_addr: str,
    to_addr: str,
    smtp_server: str,
    smtp_port: int,
    password: str,
    subject: str,
    body: str,
    timeout: int = _DEFAULT_TIMEOUT,
    max_attempts: int = _MAX_ATTEMPTS,
    logger: logging.Logger | None = None,
) -> None:
    """Send a plain-text email via SMTP+STARTTLS.

    Adds `[hostname]` to the subject and a `Sent from <fqdn>` footer to the
    body so the recipient can identify the source box across a fleet.

    Raises:
        EmailError: After exhausting retries on transient SMTP/network errors,
            or immediately on authentication failure.
    """
    hostname = socket.gethostname()
    fqdn = socket.getfqdn()
    full_subject = f"[{hostname}] {subject}"
    full_body = f"{body}\n\n-- \nSent from {fqdn}"

    msg = MIMEText(full_body)
    msg["Subject"] = full_subject
    msg["From"] = from_addr
    msg["To"] = to_addr

    context = ssl.create_default_context()
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            with smtplib.SMTP(smtp_server, smtp_port, timeout=timeout) as server:
                server.starttls(context=context)
                server.login(from_addr, password)
                server.sendmail(from_addr, [to_addr], msg.as_string())
            if logger:
                logger.info("Email sent to %s (subject=%r)", to_addr, full_subject)
            return

        except smtplib.SMTPAuthenticationError as exc:
            # Bad credentials — don't waste attempts. Surface clearly so
            # operators check the Gmail app password / 2FA setup.
            if logger:
                logger.error("SMTP authentication failed: %s", exc)
            raise EmailError(
                "SMTP authentication failed — verify the Gmail app password "
                "and that 2FA is enabled on the account"
            ) from exc

        except (smtplib.SMTPException, OSError) as exc:
            last_error = exc
            if logger:
                logger.warning(
                    "SMTP attempt %d/%d failed: %s", attempt, max_attempts, exc
                )
            if attempt < max_attempts:
                # Index 0 → wait before attempt 2, index 1 → wait before attempt 3.
                delay = _BACKOFF_SECONDS[min(attempt - 1, len(_BACKOFF_SECONDS) - 1)]
                time.sleep(delay)

    raise EmailError(
        f"SMTP send failed after {max_attempts} attempts: {last_error}"
    ) from last_error
