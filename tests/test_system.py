"""Tests for sysmaint.core.system."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from sysmaint.core.system import (
    DiskUsage,
    disks_over_threshold,
    get_disk_usage,
    get_host_info,
    is_within_window,
    reboot_required,
    reboot_required_packages,
)


class TestHostInfo:
    def test_returns_populated_fields(self) -> None:
        info = get_host_info()
        assert info.hostname
        assert info.fqdn
        assert info.kernel
        assert info.architecture


class TestDiskUsage:
    def test_root_mount_always_reportable(self) -> None:
        disks = get_disk_usage(["/"])
        assert len(disks) == 1
        assert disks[0].mountpoint == "/"
        assert disks[0].total_gb > 0
        assert 0 <= disks[0].used_percent <= 100

    def test_nonexistent_mount_skipped_silently(self) -> None:
        disks = get_disk_usage(["/nonexistent/path/here"])
        assert disks == []


class TestDisksOverThreshold:
    def test_filters_above_threshold(self) -> None:
        disks = [
            DiskUsage("/", 100.0, 90.0, 90),
            DiskUsage("/home", 200.0, 50.0, 25),
            DiskUsage("/var", 50.0, 45.0, 90),
        ]
        over = disks_over_threshold(disks, 85)
        assert len(over) == 2
        assert all(d.used_percent >= 85 for d in over)


class TestWindow:
    @pytest.mark.parametrize(
        "now, start, end, expected",
        [
            # Same-day windows
            ("03:30", "03:00", "05:00", True),
            ("02:59", "03:00", "05:00", False),
            ("05:00", "03:00", "05:00", False),  # end is exclusive
            ("12:00", "03:00", "05:00", False),
            # Windows crossing midnight
            ("23:30", "23:00", "02:00", True),
            ("01:30", "23:00", "02:00", True),
            ("02:00", "23:00", "02:00", False),  # end exclusive
            ("12:00", "23:00", "02:00", False),
        ],
    )
    def test_window_logic(self, now: str, start: str, end: str, expected: bool) -> None:
        assert is_within_window(now, start, end) is expected

    def test_invalid_hhmm_raises(self) -> None:
        with pytest.raises(ValueError):
            is_within_window("99:99", "00:00", "01:00")


class TestRebootRequired:
    def test_detects_flag_file(self, tmp_path: Path) -> None:
        flag = tmp_path / "reboot-required"
        flag.write_text("")
        pkgs_file = tmp_path / "reboot-required.pkgs"
        pkgs_file.write_text("linux-image-generic\nlibc6\n")

        with patch("sysmaint.core.system.REBOOT_REQUIRED_FLAG", flag), patch(
            "sysmaint.core.system.REBOOT_REQUIRED_PACKAGES", pkgs_file
        ):
            assert reboot_required() is True
            assert reboot_required_packages() == ["linux-image-generic", "libc6"]

    def test_no_flag_means_no_reboot(self, tmp_path: Path) -> None:
        absent = tmp_path / "nope"
        with patch("sysmaint.core.system.REBOOT_REQUIRED_FLAG", absent):
            assert reboot_required() is False
