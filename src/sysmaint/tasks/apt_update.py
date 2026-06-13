"""Weekly apt maintenance: update, upgrade, autoremove, autoclean.

Produces a human-readable summary email containing:
- Host header (hostname/FQDN/distro/kernel)
- Per-command exit status and duration
- Packages upgraded (parsed from apt output)
- Disk usage per mount + over-threshold flags
- Configured service health
- Reboot-required indicator
- Optional auto-reboot when configured

The "no-changes" case is reported separately because a quiet "nothing to do"
week is information too — silence would be ambiguous between "all is well"
and "the timer didn't fire."
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from dataclasses import dataclass, field

from sysmaint.core import email as email_mod
from sysmaint.core import system
from sysmaint.core.config import Config
from sysmaint.core.runner import (
    APT_ENV,
    CommandError,
    CommandResult,
    apt_command,
    run_command,
)

# 30 minutes per apt command — enough for a long dist-upgrade on a slow
# Pi, short enough to bail out if a mirror is wedged.
_APT_TIMEOUT_SEC = 30 * 60

# Matches the "X upgraded, Y newly installed, Z to remove" summary line
# that apt prints near the end of `apt-get upgrade`.
_APT_SUMMARY_RE = re.compile(
    r"^(\d+)\s+upgraded,\s+(\d+)\s+newly installed,\s+(\d+)\s+to remove",
    re.MULTILINE,
)
# Lines that announce a package upgrade in `apt-get upgrade` output.
_APT_INST_RE = re.compile(r"^(?:Inst|Setting up)\s+(\S+)", re.MULTILINE)


@dataclass
class UpdateOutcome:
    """Aggregated result of the weekly run, used to render the summary email."""

    results: list[CommandResult] = field(default_factory=list)
    packages_upgraded: int = 0
    packages_installed: int = 0
    packages_removed: int = 0
    upgraded_names: list[str] = field(default_factory=list)

    @property
    def any_changes(self) -> bool:
        return (
            self.packages_upgraded > 0
            or self.packages_installed > 0
            or self.packages_removed > 0
        )

    @property
    def any_failures(self) -> bool:
        return any(not r.succeeded for r in self.results)

    @property
    def total_duration(self) -> float:
        return sum(r.duration for r in self.results)


def run_apt_maintenance(
    config: Config,
    logger: logging.Logger,
    *,
    security_only: bool = False,
) -> UpdateOutcome:
    """Run the apt sequence and return a structured outcome.

    Each command is run with check=False so a failure mid-sequence still
    runs the cleanup steps and still produces a summary email.
    """
    outcome = UpdateOutcome()

    commands: list[list[str]] = [apt_command(["update"])]
    if security_only:
        # Unattended-upgrades handles this on most boxes; this path exists for
        # operators who want sysmaint to own daily security patching too.
        commands.append(apt_command(["upgrade", "--with-new-pkgs"]))
    elif config.update.include_dist_upgrade:
        # dist-upgrade is a superset of upgrade; no need to run both.
        commands.append(apt_command(["dist-upgrade"]))
    else:
        commands.append(apt_command(["upgrade"]))
    commands.extend(
        [
            apt_command(["autoremove"]),
            apt_command(["autoclean"]),
        ]
    )

    for cmd in commands:
        try:
            result = run_command(
                cmd,
                timeout=_APT_TIMEOUT_SEC,
                env=APT_ENV,
                check=False,
                logger=logger,
            )
        except CommandError as exc:
            # check=False shouldn't reach here, but guard for robustness.
            result = exc.result
        outcome.results.append(result)

        # Parse upgrade output for human-readable counts.
        if "upgrade" in cmd[-1] or cmd[-1] == "dist-upgrade":
            _parse_apt_summary(result.stdout, outcome)

    return outcome


def _parse_apt_summary(stdout: str, outcome: UpdateOutcome) -> None:
    match = _APT_SUMMARY_RE.search(stdout)
    if match:
        outcome.packages_upgraded = int(match.group(1))
        outcome.packages_installed = int(match.group(2))
        outcome.packages_removed = int(match.group(3))
    # Best-effort list of package names (helps the operator see *what* changed).
    names = sorted(set(_APT_INST_RE.findall(stdout)))
    if names:
        outcome.upgraded_names = names


def render_email(
    config: Config, outcome: UpdateOutcome, host: system.HostInfo
) -> tuple[str, str]:
    """Build (subject, body) for the summary email."""
    reboot_needed = system.reboot_required()
    over_threshold = system.disks_over_threshold(
        system.get_disk_usage(), config.monitor.disk_threshold_percent
    )

    # Subject is the at-a-glance signal: failures > reboot > package count > quiet.
    if outcome.any_failures:
        subject_state = "FAILED"
    elif reboot_needed:
        subject_state = f"{outcome.packages_upgraded} upgraded, REBOOT REQUIRED"
    elif outcome.any_changes:
        subject_state = f"{outcome.packages_upgraded} upgraded"
    else:
        subject_state = "no changes"
    subject = f"sysmaint weekly: {subject_state}"

    body = _render_body(
        config=config,
        outcome=outcome,
        host=host,
        reboot_needed=reboot_needed,
        disks_over=over_threshold,
    )
    return subject, body


def _render_body(
    *,
    config: Config,
    outcome: UpdateOutcome,
    host: system.HostInfo,
    reboot_needed: bool,
    disks_over: list[system.DiskUsage],
) -> str:
    lines: list[str] = []
    lines.append("=== sysmaint weekly run ===")
    lines.append(f"Host:     {host.hostname} ({host.fqdn})")
    lines.append(f"OS:      {host.distro} — kernel {host.kernel} ({host.architecture})")
    lines.append(f"Run:     {dt.datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"Duration: {outcome.total_duration:.0f}s total")
    lines.append("")

    lines.append("--- Commands ---")
    for r in outcome.results:
        status = "OK" if r.succeeded else f"FAIL exit={r.returncode}"
        lines.append(f"  [{status}] {r.duration:5.1f}s  {r.pretty_command()}")
        if not r.succeeded:
            err = r.stderr.strip()
            if err:
                # Truncate verbose stderr — full output is in /var/log/sysmaint.log.
                lines.append("        " + err[:400].replace("\n", "\n        "))
    lines.append("")

    lines.append("--- Package changes ---")
    lines.append(
        f"  upgraded:  {outcome.packages_upgraded}"
        f"   installed: {outcome.packages_installed}"
        f"   removed: {outcome.packages_removed}"
    )
    if outcome.upgraded_names:
        # Cap at 50 names so a big upgrade doesn't produce a wall of text.
        shown = outcome.upgraded_names[:50]
        lines.append("  packages:  " + ", ".join(shown))
        if len(outcome.upgraded_names) > 50:
            lines.append(
                f"  (+{len(outcome.upgraded_names) - 50} more — see /var/log/sysmaint.log)"
            )
    lines.append("")

    lines.append("--- Disk usage ---")
    for disk in system.get_disk_usage():
        flag = "  ALERT" if disk.used_percent >= config.monitor.disk_threshold_percent else ""
        lines.append(
            f"  {disk.mountpoint:10s} {disk.used_percent:3d}% "
            f"({disk.used_gb:.1f} / {disk.total_gb:.1f} GB){flag}"
        )
    if disks_over:
        lines.append("")
        lines.append(
            f"  WARNING: {len(disks_over)} mount(s) at or above "
            f"{config.monitor.disk_threshold_percent}% threshold"
        )
    lines.append("")

    lines.append("--- Service health ---")
    for service in config.monitor.services:
        status = system.get_service_status(service)
        marker = "OK" if status.active else "DOWN"
        lines.append(f"  [{marker}] {service:20s} {status.state}")
    lines.append("")

    if reboot_needed:
        lines.append("--- REBOOT REQUIRED ---")
        pkgs = system.reboot_required_packages()
        if pkgs:
            lines.append("  Triggered by: " + ", ".join(pkgs))
        if config.update.auto_reboot:
            lines.append(
                f"  auto_reboot=true — will reboot during "
                f"{config.update.reboot_window_start}-"
                f"{config.update.reboot_window_end} window"
            )
        else:
            lines.append("  auto_reboot=false — reboot manually with `sudo reboot`")
        lines.append("")

    lines.append("Full log: /var/log/sysmaint.log")
    lines.append("Inspect:  journalctl -u sysmaint-update.service")
    return "\n".join(lines)


def maybe_reboot(config: Config, logger: logging.Logger, *, now: dt.datetime | None = None) -> bool:
    """Reboot if all conditions are met: reboot needed, auto_reboot on, in window.

    Returns True if a reboot was triggered (the process will not return),
    False otherwise. Caller is responsible for sending the email *before*
    invoking this — once we reboot, the SMTP send is moot.
    """
    if not system.reboot_required():
        return False
    if not config.update.auto_reboot:
        logger.info("Reboot required but auto_reboot=false; skipping")
        return False

    now = now or dt.datetime.now()
    now_hhmm = now.strftime("%H:%M")
    if not system.is_within_window(
        now_hhmm,
        config.update.reboot_window_start,
        config.update.reboot_window_end,
    ):
        logger.info(
            "Reboot required but outside window %s-%s (now %s); skipping",
            config.update.reboot_window_start,
            config.update.reboot_window_end,
            now_hhmm,
        )
        return False

    logger.warning("Triggering auto-reboot now (window=%s-%s)",
                   config.update.reboot_window_start,
                   config.update.reboot_window_end)
    run_command(["systemctl", "reboot"], timeout=10, check=False, logger=logger)
    return True


def should_send_email(config: Config, outcome: UpdateOutcome) -> bool:
    """Apply the notify policy (on_success / on_no_changes) to decide if we email."""
    if outcome.any_failures:
        return True  # Failures always notify regardless of flags.
    if system.reboot_required():
        return True  # Reboot pending is important to surface.
    if outcome.any_changes:
        return config.notify.on_success
    return config.notify.on_no_changes


def execute(
    config: Config,
    logger: logging.Logger,
    *,
    security_only: bool = False,
) -> UpdateOutcome:
    """Top-level entry point used by the CLI.

    Runs maintenance, sends the email (if policy allows), and optionally
    reboots. Returns the outcome so the CLI can set an exit code.
    """
    logger.info("Starting sysmaint apt run (security_only=%s)", security_only)
    outcome = run_apt_maintenance(config, logger, security_only=security_only)
    host = system.get_host_info()

    if should_send_email(config, outcome):
        subject, body = render_email(config, outcome, host)
        try:
            email_mod.send_email(
                from_addr=config.email.from_addr,
                to_addr=config.email.to_addr,
                smtp_server=config.email.smtp_server,
                smtp_port=config.email.smtp_port,
                password=config.email.password,
                subject=subject,
                body=body,
                logger=logger,
            )
        except email_mod.EmailError as exc:
            # Don't let an email failure mask the apt outcome — log and continue.
            logger.error("Failed to send summary email: %s", exc)
    else:
        logger.info("Notify policy skipped email (no changes, on_no_changes=false)")

    maybe_reboot(config, logger)
    logger.info(
        "Run complete: %d upgraded, %d failures, duration=%.0fs",
        outcome.packages_upgraded,
        sum(1 for r in outcome.results if not r.succeeded),
        outcome.total_duration,
    )
    return outcome
