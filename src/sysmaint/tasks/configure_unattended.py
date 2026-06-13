"""Configure unattended-upgrades to email through our Gmail relay.

The daily security-patch story is owned by `unattended-upgrades` (the
Debian/Ubuntu standard). This task wires it up so its notifications come
through the same Postfix relay sysmaint already configured, with the same
[hostname] subject prefix.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sysmaint.core.config import Config, require_root
from sysmaint.core.runner import APT_ENV, apt_command, run_command

CONFIG_PATH = Path("/etc/apt/apt.conf.d/50sysmaint-unattended-upgrades")


def execute(config: Config, logger: logging.Logger) -> None:
    """Install unattended-upgrades and configure email notifications."""
    require_root()
    logger.info("Configuring unattended-upgrades")

    run_command(
        apt_command(["install", "unattended-upgrades"]),
        timeout=600,
        env=APT_ENV,
        logger=logger,
    )

    # 50sysmaint-* sorts after Debian's own 50unattended-upgrades so our
    # overrides win without us having to edit a vendor file.
    content = _build_unattended_config(config)
    CONFIG_PATH.write_text(content)
    CONFIG_PATH.chmod(0o644)
    logger.info("Wrote %s", CONFIG_PATH)

    # Make sure the timer is running.
    run_command(
        ["systemctl", "enable", "--now", "unattended-upgrades.service"],
        timeout=30,
        logger=logger,
    )


def _build_unattended_config(config: Config) -> str:
    """Build the apt.conf.d snippet that points notifications at our relay.

    Note: unattended-upgrades sends mail via the local MTA (Postfix), so
    these settings tell U-U to compose the message and hand it to Postfix,
    which then relays through Gmail using the credentials we already set
    up. We don't pass the password here — that's already in /etc/postfix/sasl_passwd.
    """
    return f"""\
// Managed by sysmaint. Edit /etc/sysmaint/sysmaint.conf and re-run
// `sudo sysmaint configure-unattended` instead of editing this file.

Unattended-Upgrade::Mail "{config.email.to_addr}";
Unattended-Upgrade::MailReport "on-change";
Unattended-Upgrade::Sender "{config.email.from_addr}";

// Reboot policy mirrors sysmaint's, so weekly-and-daily don't disagree.
Unattended-Upgrade::Automatic-Reboot "{ 'true' if config.update.auto_reboot else 'false' }";
Unattended-Upgrade::Automatic-Reboot-Time "{config.update.reboot_window_start}";

// Daily security patches are what U-U is for. Sysmaint owns the weekly
// full upgrade. Don't change this without thinking about that split.
Unattended-Upgrade::Allowed-Origins {{
    "${{distro_id}}:${{distro_codename}}-security";
    "${{distro_id}}ESMApps:${{distro_codename}}-apps-security";
    "${{distro_id}}ESM:${{distro_codename}}-infra-security";
}};

APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
"""
