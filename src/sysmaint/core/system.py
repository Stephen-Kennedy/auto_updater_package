"""Host-level information gathering for the weekly status email.

Everything here is read-only and safe to call without privileges. The
data populates the email header (hostname/distro/kernel) and the body
sections (disk usage, service health, reboot-required flag).
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path

REBOOT_REQUIRED_FLAG = Path("/var/run/reboot-required")
REBOOT_REQUIRED_PACKAGES = Path("/var/run/reboot-required.pkgs")


@dataclass(frozen=True)
class HostInfo:
    hostname: str
    fqdn: str
    distro: str
    kernel: str
    architecture: str


@dataclass(frozen=True)
class DiskUsage:
    mountpoint: str
    total_gb: float
    used_gb: float
    used_percent: int


@dataclass(frozen=True)
class ServiceStatus:
    name: str
    active: bool
    state: str  # "active", "inactive", "failed", "not-installed", ...


def get_host_info() -> HostInfo:
    """Snapshot of hostname + OS version for the email header."""
    return HostInfo(
        hostname=socket.gethostname(),
        fqdn=socket.getfqdn(),
        distro=_read_distro(),
        kernel=platform.release(),
        architecture=platform.machine(),
    )


def _read_distro() -> str:
    """Read PRETTY_NAME from /etc/os-release. Falls back to platform.platform()."""
    os_release = Path("/etc/os-release")
    if os_release.exists():
        try:
            for line in os_release.read_text().splitlines():
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
        except OSError:
            pass
    return platform.platform()


def get_disk_usage(
    mountpoints: list[str] | None = None,
) -> list[DiskUsage]:
    """Disk usage for the given mountpoints (default: /, /home, /var if they exist)."""
    if mountpoints is None:
        candidates = ["/", "/home", "/var", "/boot"]
        mountpoints = [m for m in candidates if Path(m).is_mount() or m == "/"]

    results: list[DiskUsage] = []
    for mp in mountpoints:
        try:
            usage = shutil.disk_usage(mp)
        except (FileNotFoundError, PermissionError):
            continue
        total_gb = usage.total / (1024**3)
        used_gb = usage.used / (1024**3)
        used_pct = round((usage.used / usage.total) * 100) if usage.total else 0
        results.append(
            DiskUsage(
                mountpoint=mp,
                total_gb=round(total_gb, 1),
                used_gb=round(used_gb, 1),
                used_percent=used_pct,
            )
        )
    return results


def disks_over_threshold(
    disks: list[DiskUsage], threshold_percent: int
) -> list[DiskUsage]:
    """Filter to disks at or above the alarm threshold."""
    return [d for d in disks if d.used_percent >= threshold_percent]


def get_service_status(service_name: str) -> ServiceStatus:
    """Query systemd for the active state of a service.

    Uses `systemctl is-active` which prints one of: active, inactive, failed,
    activating, deactivating, reloading, or 'unknown'. We treat 'unknown'
    paired with a non-zero exit as "not-installed" for friendlier reporting.
    """
    try:
        proc = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except FileNotFoundError:
        # systemd not present at all (e.g. running in a container during tests).
        return ServiceStatus(name=service_name, active=False, state="no-systemd")
    except subprocess.TimeoutExpired:
        return ServiceStatus(name=service_name, active=False, state="timeout")

    state = proc.stdout.strip() or "unknown"
    # Distinguish "service not installed" from "service known but stopped".
    # `systemctl list-unit-files` confirms when the state is ambiguous and
    # systemctl returned non-zero, which usually means the unit isn't known.
    if (
        proc.returncode != 0
        and state in ("unknown", "inactive")
        and not _unit_exists(service_name)
    ):
        state = "not-installed"
    return ServiceStatus(
        name=service_name,
        active=(state == "active"),
        state=state,
    )


def _unit_exists(service_name: str) -> bool:
    try:
        proc = subprocess.run(
            ["systemctl", "list-unit-files", f"{service_name}.service"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    # Output contains the unit name if it exists at all (enabled, disabled, or static).
    return service_name in proc.stdout


def reboot_required() -> bool:
    """True when the kernel/glibc/etc has been upgraded and a reboot is pending."""
    return REBOOT_REQUIRED_FLAG.exists()


def reboot_required_packages() -> list[str]:
    """List of packages that triggered the reboot-required flag, if recorded."""
    if not REBOOT_REQUIRED_PACKAGES.exists():
        return []
    try:
        return [
            line.strip()
            for line in REBOOT_REQUIRED_PACKAGES.read_text().splitlines()
            if line.strip()
        ]
    except OSError:
        return []


def is_within_window(now_hhmm: str, start_hhmm: str, end_hhmm: str) -> bool:
    """True when `now_hhmm` falls within [start_hhmm, end_hhmm).

    Handles windows that cross midnight (e.g. 23:00-02:00). All inputs are
    "HH:MM" strings; invalid input raises ValueError.
    """
    now = _parse_hhmm(now_hhmm)
    start = _parse_hhmm(start_hhmm)
    end = _parse_hhmm(end_hhmm)
    if start <= end:
        return start <= now < end
    # Window wraps past midnight.
    return now >= start or now < end


def _parse_hhmm(value: str) -> int:
    hh, mm = value.split(":")
    h, m = int(hh), int(mm)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(f"Invalid HH:MM value: {value!r}")
    return h * 60 + m


def is_root() -> bool:
    return os.geteuid() == 0
