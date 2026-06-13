"""`sysmaint migrate-from-legacy` — move boxes off the old auto_updater_package.

The legacy install pattern was: clone the repo, run python main_*.py from
cron. There was no pip install. This task:
1. Finds and rewrites cron jobs that point at the old main_*.py paths.
2. Migrates /etc/postfix/env_variables.env → /etc/sysmaint/sysmaint.conf
   (preserving the credentials so the operator doesn't re-enter them).
3. Installs systemd unit files and enables the weekly timer.
4. Sends a test email.

Designed to be idempotent — safe to re-run if a step fails partway.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path

from sysmaint.core.config import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_PASSWORD_PATH,
    require_root,
)

LEGACY_ENV_FILE = Path("/etc/postfix/env_variables.env")
LEGACY_SCRIPT_NAMES = (
    "main_apt_update.py",
    "main_pihole_update.py",
    "main_postfix_setup.py",
    "main_postfix_purge.py",
)


def execute(logger: logging.Logger) -> int:
    """Migrate a legacy install to the new sysmaint layout."""
    require_root()
    print("=" * 60)
    print("  sysmaint migrate-from-legacy")
    print("=" * 60)
    print()

    migrated_creds = _migrate_env_file(logger)
    disabled_crons = _disable_legacy_cron(logger)
    _install_systemd_units(logger)

    print()
    print("Migration summary:")
    print(f"  credentials migrated: {migrated_creds}")
    print(f"  legacy cron entries disabled: {disabled_crons}")
    print()
    if migrated_creds:
        print(
            "Test the new wiring:\n"
            "  sudo sysmaint test-email\n"
            "  sudo sysmaint status\n"
        )
    else:
        print(
            "No legacy credentials found — run `sudo sysmaint install` to\n"
            "set up config from scratch.\n"
        )
    return 0


def _migrate_env_file(logger: logging.Logger) -> bool:
    """Translate the legacy /etc/postfix/env_variables.env to sysmaint config."""
    if not LEGACY_ENV_FILE.exists():
        logger.info("No legacy env file at %s; skipping credential migration", LEGACY_ENV_FILE)
        return False
    if DEFAULT_CONFIG_PATH.exists():
        logger.info(
            "%s already exists — leaving it alone (re-run install to overwrite)",
            DEFAULT_CONFIG_PATH,
        )
        return False

    env: dict[str, str] = {}
    for line in LEGACY_ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip("'").strip('"')

    required = ("FROM_EMAIL", "TO_EMAIL", "SMTP_SERVER", "EMAIL_PASSWORD")
    missing = [k for k in required if not env.get(k)]
    if missing:
        logger.warning(
            "Legacy env file is missing required keys %s; cannot migrate",
            ", ".join(missing),
        )
        return False

    DEFAULT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_CONFIG_PATH.parent.chmod(0o755)

    DEFAULT_PASSWORD_PATH.write_text(env["EMAIL_PASSWORD"] + "\n")
    DEFAULT_PASSWORD_PATH.chmod(0o600)
    os.chown(DEFAULT_PASSWORD_PATH, 0, 0)
    logger.info("Wrote %s (mode=0600)", DEFAULT_PASSWORD_PATH)

    DEFAULT_CONFIG_PATH.write_text(
        _build_config_from_env(env)
    )
    DEFAULT_CONFIG_PATH.chmod(0o640)
    os.chown(DEFAULT_CONFIG_PATH, 0, 0)
    logger.info("Wrote %s (mode=0640)", DEFAULT_CONFIG_PATH)
    return True


def _build_config_from_env(env: dict[str, str]) -> str:
    """Render sysmaint.conf using values lifted from the legacy env file."""
    return f"""\
# /etc/sysmaint/sysmaint.conf — migrated by `sysmaint migrate-from-legacy`
# from {LEGACY_ENV_FILE}.

[email]
from = {env['FROM_EMAIL']}
to = {env['TO_EMAIL']}
smtp_server = {env['SMTP_SERVER']}
smtp_port = 587
password_file = {DEFAULT_PASSWORD_PATH}

[update]
auto_reboot = false
reboot_window_start = 03:00
reboot_window_end = 05:00
include_dist_upgrade = true

[notify]
on_success = true
on_no_changes = false

[monitor]
disk_threshold_percent = 85
services = sshd,postfix
"""


def _disable_legacy_cron(logger: logging.Logger) -> int:
    """Comment out cron lines that mention the legacy main_*.py scripts.

    We comment rather than delete so the operator can audit what was
    changed (with `git diff` on /etc tracked in etckeeper, or by eye).
    """
    pattern = re.compile(r"|".join(re.escape(name) for name in LEGACY_SCRIPT_NAMES))
    count = 0
    cron_files: list[Path] = [Path("/etc/crontab")]
    cron_d = Path("/etc/cron.d")
    if cron_d.is_dir():
        cron_files.extend(p for p in cron_d.iterdir() if p.is_file())
    for cron_file in cron_files:
        if not cron_file.is_file():
            continue
        try:
            original = cron_file.read_text()
        except OSError as exc:
            logger.warning("Could not read %s: %s", cron_file, exc)
            continue
        new_lines: list[str] = []
        changed = False
        for line in original.splitlines():
            if pattern.search(line) and not line.lstrip().startswith("#"):
                new_lines.append(f"# disabled by sysmaint migrate-from-legacy: {line}")
                changed = True
                count += 1
            else:
                new_lines.append(line)
        if changed:
            backup = cron_file.with_suffix(cron_file.suffix + ".sysmaint.bak")
            shutil.copy2(cron_file, backup)
            cron_file.write_text("\n".join(new_lines) + ("\n" if original.endswith("\n") else ""))
            logger.info("Disabled legacy entries in %s (backup: %s)", cron_file, backup)
    return count


def _install_systemd_units(logger: logging.Logger) -> None:
    """Reuse the install task's unit deployment + timer enable."""
    from sysmaint.tasks.install import _enable_default_timers, _install_systemd_units

    _install_systemd_units(logger)
    _enable_default_timers(logger)
