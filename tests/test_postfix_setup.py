"""Tests for sysmaint.tasks.postfix_setup.

Focused on the pure render_main_cf() function — the install flow itself
involves apt and systemctl, which aren't worth mocking exhaustively when
the meaningful logic (templating the relayhost from config) is isolatable.
"""

from __future__ import annotations

from sysmaint.tasks.postfix_setup import render_main_cf


class TestRenderMainCf:
    def test_relayhost_uses_configured_gmail_defaults(self) -> None:
        out = render_main_cf("smtp.gmail.com", 587)
        assert "relayhost = [smtp.gmail.com]:587" in out

    def test_relayhost_honors_non_gmail_config(self) -> None:
        """Regression: previous implementation hardcoded Gmail in main.cf
        while writing non-Gmail credentials to sasl_passwd, producing a
        mismatched config that silently broke mail delivery."""
        out = render_main_cf("smtp.mailgun.org", 2525)
        assert "relayhost = [smtp.mailgun.org]:2525" in out
        assert "smtp.gmail.com" not in out

    def test_includes_sasl_and_tls_settings(self) -> None:
        out = render_main_cf("smtp.example.com", 587)
        assert "smtp_sasl_auth_enable = yes" in out
        assert "smtp_sasl_password_maps = hash:/etc/postfix/sasl_passwd" in out
        assert "smtp_tls_security_level = encrypt" in out
        assert "smtp_tls_CAfile = /etc/ssl/certs/ca-certificates.crt" in out

    def test_only_listens_on_loopback(self) -> None:
        """Postfix should never accept inbound from anywhere but localhost.
        A misconfigured relay accepting WAN traffic is an open relay."""
        out = render_main_cf("smtp.example.com", 587)
        assert "inet_interfaces = loopback-only" in out
