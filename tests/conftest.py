"""Shared pytest fixtures."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from sysmaint.core.config import (
    Config,
    EmailConfig,
    MonitorConfig,
    NotifyConfig,
    UpdateConfig,
)


@pytest.fixture
def silent_logger() -> logging.Logger:
    """A logger that has a handler but writes to nowhere visible to tests."""
    logger = logging.getLogger("test-silent")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


@pytest.fixture
def example_config() -> Config:
    """A fully-populated Config object for tasks tests that don't touch disk."""
    return Config(
        email=EmailConfig(
            from_addr="from@example.com",
            to_addr="to@example.com",
            smtp_server="smtp.example.com",
            smtp_port=587,
            password="hunter2",
        ),
        update=UpdateConfig(
            auto_reboot=False,
            reboot_window_start="03:00",
            reboot_window_end="05:00",
            include_dist_upgrade=True,
        ),
        notify=NotifyConfig(on_success=True, on_no_changes=False),
        monitor=MonitorConfig(
            disk_threshold_percent=85,
            services=("sshd", "postfix"),
        ),
    )


@pytest.fixture
def tmp_password_file(tmp_path: Path) -> Path:
    """A 0600 password file for config-loader tests."""
    p = tmp_path / "smtp_password"
    p.write_text("supersecret\n")
    p.chmod(0o600)
    return p
