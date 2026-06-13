"""Tests for sysmaint.core.email.

We mock smtplib.SMTP to avoid real network traffic. Each test verifies a
specific failure mode and the corresponding retry / raise behavior.
"""

from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch

import pytest

from sysmaint.core.email import EmailError, send_email


def _kwargs(**overrides):
    base = dict(
        from_addr="from@example.com",
        to_addr="to@example.com",
        smtp_server="smtp.example.com",
        smtp_port=587,
        password="hunter2",
        subject="Hi",
        body="Body text",
        # Speed tests up — we don't actually want 5+25 = 30s of sleep.
        max_attempts=3,
    )
    base.update(overrides)
    return base


@pytest.fixture
def no_sleep():
    """Replace time.sleep with a no-op so retry tests don't actually wait."""
    with patch("sysmaint.core.email.time.sleep") as m:
        yield m


class TestSendEmailSuccess:
    def test_happy_path_sends_once(self, no_sleep) -> None:
        smtp_instance = MagicMock()
        with patch("sysmaint.core.email.smtplib.SMTP") as smtp_cls:
            smtp_cls.return_value.__enter__.return_value = smtp_instance
            send_email(**_kwargs())

        smtp_instance.starttls.assert_called_once()
        smtp_instance.login.assert_called_once_with("from@example.com", "hunter2")
        smtp_instance.sendmail.assert_called_once()
        # No retries needed — sleep was never invoked.
        assert no_sleep.call_count == 0

    def test_subject_prefixed_with_hostname(self, no_sleep) -> None:
        smtp_instance = MagicMock()
        with patch("sysmaint.core.email.smtplib.SMTP") as smtp_cls, patch(
            "sysmaint.core.email.socket.gethostname", return_value="testbox"
        ), patch("sysmaint.core.email.socket.getfqdn", return_value="testbox.lan"):
            smtp_cls.return_value.__enter__.return_value = smtp_instance
            send_email(**_kwargs(subject="status update"))

        sent_args = smtp_instance.sendmail.call_args
        message_text = sent_args[0][2]
        assert "[testbox] status update" in message_text
        assert "Sent from testbox.lan" in message_text


class TestSendEmailRetry:
    def test_transient_failure_then_success(self, no_sleep) -> None:
        """First two attempts fail with SMTPException, third succeeds."""
        call_count = {"n": 0}
        ok_instance = MagicMock()

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            cm = MagicMock()
            if call_count["n"] < 3:
                cm.__enter__.return_value.starttls.side_effect = smtplib.SMTPException(
                    "transient"
                )
            else:
                cm.__enter__.return_value = ok_instance
            return cm

        with patch(
            "sysmaint.core.email.smtplib.SMTP", side_effect=side_effect
        ):
            send_email(**_kwargs())

        assert call_count["n"] == 3
        # Slept twice — between attempt 1→2 and 2→3.
        assert no_sleep.call_count == 2

    def test_all_attempts_fail_raises_email_error(self, no_sleep) -> None:
        with patch("sysmaint.core.email.smtplib.SMTP") as smtp_cls:
            smtp_cls.return_value.__enter__.return_value.starttls.side_effect = (
                smtplib.SMTPException("down")
            )
            with pytest.raises(EmailError, match="after 3 attempts"):
                send_email(**_kwargs())
        # 2 retries → 2 sleeps.
        assert no_sleep.call_count == 2

    def test_auth_failure_does_not_retry(self, no_sleep) -> None:
        """Bad credentials are a permanent error — wasting retries doesn't help."""
        with patch("sysmaint.core.email.smtplib.SMTP") as smtp_cls:
            smtp_cls.return_value.__enter__.return_value.login.side_effect = (
                smtplib.SMTPAuthenticationError(535, b"Bad password")
            )
            with pytest.raises(EmailError, match="authentication failed"):
                send_email(**_kwargs())
        assert no_sleep.call_count == 0  # no retries

    def test_network_error_retries(self, no_sleep) -> None:
        with patch("sysmaint.core.email.smtplib.SMTP") as smtp_cls:
            smtp_cls.side_effect = OSError("network down")
            with pytest.raises(EmailError, match="after 3 attempts"):
                send_email(**_kwargs())
        assert no_sleep.call_count == 2
