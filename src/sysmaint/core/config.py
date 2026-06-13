"""Configuration loader for sysmaint.

Config lives in /etc/sysmaint/sysmaint.conf (INI format) with the SMTP
password in a separate /etc/sysmaint/smtp_password file (0600). Splitting
the password out lets you grep the main config without leaking secrets,
and lets us refuse to load if the password file has loose permissions.
"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("/etc/sysmaint/sysmaint.conf")
DEFAULT_PASSWORD_PATH = Path("/etc/sysmaint/smtp_password")


class ConfigError(Exception):
    """Raised when the config file is missing, malformed, or insecure."""


@dataclass(frozen=True)
class EmailConfig:
    from_addr: str
    to_addr: str
    smtp_server: str
    smtp_port: int
    password: str


@dataclass(frozen=True)
class UpdateConfig:
    auto_reboot: bool
    reboot_window_start: str  # "HH:MM"
    reboot_window_end: str
    include_dist_upgrade: bool


@dataclass(frozen=True)
class NotifyConfig:
    on_success: bool
    on_no_changes: bool


@dataclass(frozen=True)
class MonitorConfig:
    disk_threshold_percent: int
    services: tuple[str, ...]


@dataclass(frozen=True)
class Config:
    email: EmailConfig
    update: UpdateConfig
    notify: NotifyConfig
    monitor: MonitorConfig


def load_config(
    config_path: Path | str = DEFAULT_CONFIG_PATH,
    password_path: Path | str | None = None,
) -> Config:
    """Load and validate the sysmaint config.

    Args:
        config_path: Path to the main INI config file.
        password_path: Override for the password file location. If None,
            uses the path declared in `[email] password_file`, falling
            back to DEFAULT_PASSWORD_PATH.

    Raises:
        ConfigError: For any missing required key, unreadable file,
            malformed value, or insecure password file permissions.
    """
    cfg_path = Path(config_path)
    if not cfg_path.exists():
        raise ConfigError(f"Config file not found: {cfg_path}")

    parser = configparser.ConfigParser()
    try:
        parser.read(cfg_path)
    except configparser.Error as exc:
        raise ConfigError(f"Failed to parse {cfg_path}: {exc}") from exc

    if "email" not in parser:
        raise ConfigError(f"Missing required [email] section in {cfg_path}")

    email_section = parser["email"]
    try:
        from_addr = email_section["from"].strip()
        to_addr = email_section["to"].strip()
    except KeyError as exc:
        raise ConfigError(f"Missing required key in [email]: {exc}") from exc

    if not from_addr or not to_addr:
        raise ConfigError("[email] 'from' and 'to' must be non-empty")

    smtp_server = email_section.get("smtp_server", "smtp.gmail.com").strip()
    smtp_port = email_section.getint("smtp_port", 587)

    pw_path = Path(
        password_path
        if password_path is not None
        else email_section.get("password_file", str(DEFAULT_PASSWORD_PATH))
    )
    password = _read_password_file(pw_path)

    email = EmailConfig(
        from_addr=from_addr,
        to_addr=to_addr,
        smtp_server=smtp_server,
        smtp_port=smtp_port,
        password=password,
    )

    # Optional sections — use defaults if absent.
    update = _load_update_section(parser)
    notify = _load_notify_section(parser)
    monitor = _load_monitor_section(parser)

    return Config(email=email, update=update, notify=notify, monitor=monitor)


def _read_password_file(path: Path) -> str:
    if not path.exists():
        raise ConfigError(f"Password file not found: {path}")

    # Refuse to load a password file readable by group or other.
    st = path.stat()
    mode = st.st_mode & 0o777
    if mode & 0o077:
        raise ConfigError(
            f"Password file {path} has unsafe permissions {oct(mode)}; "
            f"run: chmod 600 {path}"
        )

    password = path.read_text().strip()
    if not password:
        raise ConfigError(f"Password file {path} is empty")
    return password


def _load_update_section(parser: configparser.ConfigParser) -> UpdateConfig:
    if "update" not in parser:
        return UpdateConfig(
            auto_reboot=False,
            reboot_window_start="03:00",
            reboot_window_end="05:00",
            include_dist_upgrade=True,
        )
    section = parser["update"]
    return UpdateConfig(
        auto_reboot=section.getboolean("auto_reboot", False),
        reboot_window_start=section.get("reboot_window_start", "03:00").strip(),
        reboot_window_end=section.get("reboot_window_end", "05:00").strip(),
        include_dist_upgrade=section.getboolean("include_dist_upgrade", True),
    )


def _load_notify_section(parser: configparser.ConfigParser) -> NotifyConfig:
    if "notify" not in parser:
        return NotifyConfig(on_success=True, on_no_changes=False)
    section = parser["notify"]
    return NotifyConfig(
        on_success=section.getboolean("on_success", True),
        on_no_changes=section.getboolean("on_no_changes", False),
    )


def _load_monitor_section(parser: configparser.ConfigParser) -> MonitorConfig:
    if "monitor" not in parser:
        return MonitorConfig(
            disk_threshold_percent=85,
            services=("sshd", "postfix"),
        )
    section = parser["monitor"]
    threshold = section.getint("disk_threshold_percent", 85)
    if not 1 <= threshold <= 99:
        raise ConfigError(
            f"[monitor] disk_threshold_percent must be 1-99, got {threshold}"
        )
    services_raw = section.get("services", "sshd,postfix")
    services = tuple(s.strip() for s in services_raw.split(",") if s.strip())
    return MonitorConfig(
        disk_threshold_percent=threshold,
        services=services,
    )


def require_root() -> None:
    """Refuse to run unprivileged. Call early in any task that touches /etc."""
    if os.geteuid() != 0:
        raise PermissionError(
            "sysmaint must be run as root for this operation "
            "(use sudo or run from the systemd timer)"
        )
