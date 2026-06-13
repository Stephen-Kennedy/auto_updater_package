"""Local diagnostics: `sysmaint status` — what's the box doing right now?

This is the "ssh in, type one command" tool. It prints to stdout and
does NOT touch SMTP. Safe to run as any user (some fields may be empty
when run unprivileged).
"""

from __future__ import annotations

import subprocess

from sysmaint.core import system
from sysmaint.core.config import DEFAULT_CONFIG_PATH, ConfigError, load_config

UPDATE_TIMER = "sysmaint-update.timer"
UPDATE_SERVICE = "sysmaint-update.service"


def execute() -> int:
    """Print a status report. Returns 0 always (informational command)."""
    print(_render())
    return 0


def _render() -> str:
    lines: list[str] = []
    host = system.get_host_info()
    lines.append(f"sysmaint status — {host.hostname} ({host.fqdn})")
    lines.append(f"{host.distro} — kernel {host.kernel} ({host.architecture})")
    lines.append("")

    # Config
    lines.append("--- Configuration ---")
    if DEFAULT_CONFIG_PATH.exists():
        lines.append(f"  config:        {DEFAULT_CONFIG_PATH}  (present)")
        try:
            cfg = load_config()
            lines.append(f"  notify to:     {cfg.email.to_addr}")
            lines.append(f"  smtp:          {cfg.email.smtp_server}:{cfg.email.smtp_port}")
            lines.append(f"  auto_reboot:   {cfg.update.auto_reboot}")
            lines.append(f"  dist_upgrade:  {cfg.update.include_dist_upgrade}")
            services_str = ", ".join(cfg.monitor.services) or "(none)"
            lines.append(f"  watch:         {services_str}")
        except ConfigError as exc:
            lines.append(f"  config error:  {exc}")
            cfg = None
    else:
        lines.append(f"  config:        {DEFAULT_CONFIG_PATH}  (MISSING — run `sudo sysmaint install`)")
        cfg = None
    lines.append("")

    # Timers
    lines.append("--- Scheduled timers ---")
    for timer in (UPDATE_TIMER, "sysmaint-pihole.timer"):
        lines.append(f"  {timer}")
        info = _timer_info(timer)
        for key, value in info.items():
            lines.append(f"    {key:14s} {value}")
    lines.append("")

    # Last run summary
    lines.append("--- Last run ---")
    last = _last_journal_line(UPDATE_SERVICE)
    lines.append(f"  {last}")
    lines.append("")

    # Disk
    lines.append("--- Disks ---")
    threshold = cfg.monitor.disk_threshold_percent if cfg else 85
    for disk in system.get_disk_usage():
        flag = "  ALERT" if disk.used_percent >= threshold else ""
        lines.append(
            f"  {disk.mountpoint:10s} {disk.used_percent:3d}% "
            f"({disk.used_gb:.1f} / {disk.total_gb:.1f} GB){flag}"
        )
    lines.append("")

    # Services
    if cfg:
        lines.append("--- Services ---")
        for svc in cfg.monitor.services:
            status = system.get_service_status(svc)
            marker = "OK" if status.active else "DOWN"
            lines.append(f"  [{marker}] {svc:20s} {status.state}")
        lines.append("")

    # Reboot
    if system.reboot_required():
        lines.append("*** REBOOT REQUIRED ***")
        pkgs = system.reboot_required_packages()
        if pkgs:
            lines.append("    Triggered by: " + ", ".join(pkgs))
    else:
        lines.append("Reboot: not required")
    return "\n".join(lines)


def _timer_info(timer: str) -> dict[str, str]:
    """Pull a few interesting fields from `systemctl show <timer>`."""
    try:
        proc = subprocess.run(
            [
                "systemctl",
                "show",
                timer,
                "--property=ActiveState,LoadState,NextElapseUSecRealtime,LastTriggerUSec,Result",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"state": "no-systemd"}

    info: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        info[key.lower()] = value or "(empty)"

    # Map to friendlier labels.
    summary: dict[str, str] = {}
    summary["state"] = info.get("activestate", "?")
    summary["loaded"] = info.get("loadstate", "?")
    summary["next"] = info.get("nextelapseusecrealtime", "(not scheduled)")
    summary["last"] = info.get("lasttriggerusec", "(never)")
    summary["result"] = info.get("result", "?")
    return summary


def _last_journal_line(unit: str) -> str:
    """Tail the most recent journal entries for a unit (best-effort)."""
    try:
        proc = subprocess.run(
            ["journalctl", "-u", unit, "-n", "1", "--no-pager", "-o", "short"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "(journalctl unavailable)"
    text = proc.stdout.strip()
    if not text:
        return f"(no entries yet — try `journalctl -u {unit}`)"
    return text.splitlines()[-1]
