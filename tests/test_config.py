"""Tests for sysmaint.core.config."""

from __future__ import annotations

from pathlib import Path

import pytest

from sysmaint.core.config import ConfigError, load_config


def _write_config(
    dir_path: Path, password_path: Path, *, extra: str = "", section_to_drop: str = ""
) -> Path:
    """Helper to materialize a config file with the common sections."""
    cfg_path = dir_path / "sysmaint.conf"
    sections = {
        "email": f"""[email]
from = box@example.com
to = ops@example.com
smtp_server = smtp.gmail.com
smtp_port = 587
password_file = {password_path}
""",
        "update": """[update]
auto_reboot = true
reboot_window_start = 02:30
reboot_window_end = 04:30
include_dist_upgrade = false
""",
        "notify": """[notify]
on_success = false
on_no_changes = true
""",
        "monitor": """[monitor]
disk_threshold_percent = 90
services = sshd, fail2ban, ufw
""",
    }
    sections.pop(section_to_drop, None)
    content = "\n".join(sections.values())
    if extra:
        content += "\n" + extra
    cfg_path.write_text(content)
    return cfg_path


class TestLoadConfigHappyPath:
    def test_loads_all_sections(self, tmp_path: Path, tmp_password_file: Path) -> None:
        cfg_path = _write_config(tmp_path, tmp_password_file)
        cfg = load_config(cfg_path)
        assert cfg.email.from_addr == "box@example.com"
        assert cfg.email.to_addr == "ops@example.com"
        assert cfg.email.smtp_port == 587
        assert cfg.email.password == "supersecret"
        assert cfg.update.auto_reboot is True
        assert cfg.update.include_dist_upgrade is False
        assert cfg.notify.on_success is False
        assert cfg.notify.on_no_changes is True
        assert cfg.monitor.disk_threshold_percent == 90
        assert cfg.monitor.services == ("sshd", "fail2ban", "ufw")

    def test_defaults_when_optional_sections_missing(
        self, tmp_path: Path, tmp_password_file: Path
    ) -> None:
        cfg_path = _write_config(
            tmp_path, tmp_password_file, section_to_drop="monitor"
        )
        cfg = load_config(cfg_path)
        # Default monitor section kicks in:
        assert cfg.monitor.disk_threshold_percent == 85
        assert cfg.monitor.services == ("sshd", "postfix")


class TestLoadConfigErrors:
    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="not found"):
            load_config(tmp_path / "nope.conf")

    def test_missing_email_section(
        self, tmp_path: Path, tmp_password_file: Path
    ) -> None:
        cfg_path = tmp_path / "sysmaint.conf"
        cfg_path.write_text("[update]\nauto_reboot=false\n")
        with pytest.raises(ConfigError, match=r"\[email\]"):
            load_config(cfg_path)

    def test_missing_required_email_key(
        self, tmp_path: Path, tmp_password_file: Path
    ) -> None:
        cfg_path = tmp_path / "sysmaint.conf"
        cfg_path.write_text(f"[email]\nfrom = a@b.com\npassword_file = {tmp_password_file}\n")
        with pytest.raises(ConfigError, match="Missing required key"):
            load_config(cfg_path)

    def test_blank_email_addr_rejected(
        self, tmp_path: Path, tmp_password_file: Path
    ) -> None:
        cfg_path = tmp_path / "sysmaint.conf"
        cfg_path.write_text(
            f"[email]\nfrom =\nto = b@b.com\npassword_file = {tmp_password_file}\n"
        )
        with pytest.raises(ConfigError, match="non-empty"):
            load_config(cfg_path)

    def test_missing_password_file(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "sysmaint.conf"
        cfg_path.write_text(
            "[email]\nfrom = a@b.com\nto = c@d.com\n"
            "password_file = /nonexistent/path\n"
        )
        with pytest.raises(ConfigError, match="Password file not found"):
            load_config(cfg_path)

    def test_password_file_with_loose_perms_rejected(
        self, tmp_path: Path
    ) -> None:
        password_path = tmp_path / "smtp_password"
        password_path.write_text("secret\n")
        password_path.chmod(0o644)  # world-readable — should be rejected
        cfg_path = _write_config(tmp_path, password_path)
        with pytest.raises(ConfigError, match="unsafe permissions"):
            load_config(cfg_path)

    def test_empty_password_file_rejected(self, tmp_path: Path) -> None:
        password_path = tmp_path / "smtp_password"
        password_path.write_text("")
        password_path.chmod(0o600)
        cfg_path = _write_config(tmp_path, password_path)
        with pytest.raises(ConfigError, match="empty"):
            load_config(cfg_path)

    def test_invalid_disk_threshold_rejected(
        self, tmp_path: Path, tmp_password_file: Path
    ) -> None:
        cfg_path = _write_config(
            tmp_path, tmp_password_file, section_to_drop="monitor"
        )
        cfg_path.write_text(
            cfg_path.read_text()
            + "\n[monitor]\ndisk_threshold_percent = 150\nservices = sshd\n"
        )
        with pytest.raises(ConfigError, match="disk_threshold_percent"):
            load_config(cfg_path)
