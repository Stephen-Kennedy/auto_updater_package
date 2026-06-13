"""Tests for sysmaint.tasks.apt_update.

We exercise:
- The four summary-email quadrants (success-no-failures, success-with-failures,
  total failure, no-changes).
- Auto-reboot decision logic across (reboot_required, auto_reboot, in-window).
- The notify policy (should_send_email).
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import replace
from unittest.mock import patch

from sysmaint.core.runner import CommandResult
from sysmaint.core.system import HostInfo
from sysmaint.tasks.apt_update import (
    UpdateOutcome,
    _parse_apt_summary,
    maybe_reboot,
    render_email,
    should_send_email,
)

_HOST = HostInfo(
    hostname="testbox",
    fqdn="testbox.lan",
    distro="Ubuntu 24.04 LTS",
    kernel="6.5.0-42-generic",
    architecture="x86_64",
)


def _result(cmd: tuple[str, ...], rc: int = 0, stdout: str = "", duration: float = 1.0) -> CommandResult:
    return CommandResult(command=cmd, returncode=rc, stdout=stdout, stderr="", duration=duration)


class TestParseAptSummary:
    def test_extracts_upgrade_counts(self) -> None:
        out = UpdateOutcome()
        stdout = (
            "Reading state...\n"
            "5 upgraded, 1 newly installed, 0 to remove and 0 not upgraded.\n"
        )
        _parse_apt_summary(stdout, out)
        assert out.packages_upgraded == 5
        assert out.packages_installed == 1
        assert out.packages_removed == 0

    def test_extracts_package_names(self) -> None:
        out = UpdateOutcome()
        stdout = (
            "Inst libssl3 [3.0.10-1ubuntu2]\n"
            "Inst openssl [3.0.10-1ubuntu2]\n"
            "Setting up libssl3 (3.0.10-1ubuntu2) ...\n"
        )
        _parse_apt_summary(stdout, out)
        assert "libssl3" in out.upgraded_names
        assert "openssl" in out.upgraded_names

    def test_no_summary_line_leaves_counts_zero(self) -> None:
        out = UpdateOutcome()
        _parse_apt_summary("nothing interesting here", out)
        assert out.packages_upgraded == 0


class TestRenderEmailQuadrants:
    """The summary email has four meaningfully different shapes."""

    def _outcome(self, *, fails: bool = False, changes: int = 0) -> UpdateOutcome:
        results = [
            _result(("apt-get", "update")),
            _result(
                ("apt-get", "dist-upgrade"),
                rc=1 if fails else 0,
                stdout=(
                    f"{changes} upgraded, 0 newly installed, 0 to remove\n"
                    if changes
                    else ""
                ),
            ),
            _result(("apt-get", "autoremove")),
            _result(("apt-get", "autoclean")),
        ]
        outcome = UpdateOutcome(results=results, packages_upgraded=changes)
        return outcome

    def test_all_success_with_changes(self, example_config) -> None:
        with patch("sysmaint.tasks.apt_update.system.reboot_required", return_value=False), patch(
            "sysmaint.tasks.apt_update.system.get_disk_usage", return_value=[]
        ), patch(
            "sysmaint.tasks.apt_update.system.get_service_status"
        ) as mock_svc:
            mock_svc.return_value.active = True
            mock_svc.return_value.state = "active"
            subject, body = render_email(example_config, self._outcome(changes=12), _HOST)
        assert "12 upgraded" in subject
        assert "FAIL" not in body  # all commands succeeded
        assert "testbox" in body

    def test_success_with_one_failure(self, example_config) -> None:
        with patch("sysmaint.tasks.apt_update.system.reboot_required", return_value=False), patch(
            "sysmaint.tasks.apt_update.system.get_disk_usage", return_value=[]
        ), patch("sysmaint.tasks.apt_update.system.get_service_status"):
            subject, body = render_email(example_config, self._outcome(fails=True, changes=3), _HOST)
        assert "FAILED" in subject
        assert "FAIL exit=1" in body

    def test_total_failure_no_changes(self, example_config) -> None:
        outcome = UpdateOutcome(
            results=[_result(("apt-get", "update"), rc=1)],
        )
        with patch("sysmaint.tasks.apt_update.system.reboot_required", return_value=False), patch(
            "sysmaint.tasks.apt_update.system.get_disk_usage", return_value=[]
        ), patch("sysmaint.tasks.apt_update.system.get_service_status"):
            subject, _ = render_email(example_config, outcome, _HOST)
        assert "FAILED" in subject

    def test_no_changes(self, example_config) -> None:
        outcome = UpdateOutcome(results=[_result(("apt-get", "update"))])
        with patch("sysmaint.tasks.apt_update.system.reboot_required", return_value=False), patch(
            "sysmaint.tasks.apt_update.system.get_disk_usage", return_value=[]
        ), patch("sysmaint.tasks.apt_update.system.get_service_status"):
            subject, _ = render_email(example_config, outcome, _HOST)
        assert "no changes" in subject

    def test_reboot_required_in_subject(self, example_config) -> None:
        with patch("sysmaint.tasks.apt_update.system.reboot_required", return_value=True), patch(
            "sysmaint.tasks.apt_update.system.reboot_required_packages", return_value=["linux-image"]
        ), patch("sysmaint.tasks.apt_update.system.get_disk_usage", return_value=[]), patch(
            "sysmaint.tasks.apt_update.system.get_service_status"
        ):
            subject, body = render_email(example_config, self._outcome(changes=4), _HOST)
        assert "REBOOT REQUIRED" in subject
        assert "linux-image" in body


class TestShouldSendEmail:
    def test_failures_always_send(self, example_config) -> None:
        outcome = UpdateOutcome(results=[_result(("x",), rc=1)])
        cfg = replace(example_config, notify=example_config.notify)
        with patch("sysmaint.tasks.apt_update.system.reboot_required", return_value=False):
            assert should_send_email(cfg, outcome) is True

    def test_reboot_required_always_sends(self, example_config) -> None:
        outcome = UpdateOutcome(results=[_result(("x",), rc=0)])
        with patch("sysmaint.tasks.apt_update.system.reboot_required", return_value=True):
            assert should_send_email(example_config, outcome) is True

    def test_changes_with_on_success_true(self, example_config) -> None:
        outcome = UpdateOutcome(
            results=[_result(("x",))], packages_upgraded=2
        )
        with patch("sysmaint.tasks.apt_update.system.reboot_required", return_value=False):
            assert should_send_email(example_config, outcome) is True

    def test_no_changes_with_on_no_changes_false_skips(self, example_config) -> None:
        outcome = UpdateOutcome(results=[_result(("x",))])
        with patch("sysmaint.tasks.apt_update.system.reboot_required", return_value=False):
            assert should_send_email(example_config, outcome) is False


class TestMaybeReboot:
    def test_no_reboot_required_does_nothing(
        self, example_config, silent_logger: logging.Logger
    ) -> None:
        with patch("sysmaint.tasks.apt_update.system.reboot_required", return_value=False):
            assert maybe_reboot(example_config, silent_logger) is False

    def test_reboot_required_but_disabled(
        self, example_config, silent_logger: logging.Logger
    ) -> None:
        cfg = replace(
            example_config, update=replace(example_config.update, auto_reboot=False)
        )
        with patch("sysmaint.tasks.apt_update.system.reboot_required", return_value=True):
            assert maybe_reboot(cfg, silent_logger) is False

    def test_reboot_required_outside_window(
        self, example_config, silent_logger: logging.Logger
    ) -> None:
        cfg = replace(
            example_config,
            update=replace(
                example_config.update,
                auto_reboot=True,
                reboot_window_start="03:00",
                reboot_window_end="05:00",
            ),
        )
        outside = dt.datetime(2025, 1, 1, 12, 0, 0)
        with patch("sysmaint.tasks.apt_update.system.reboot_required", return_value=True):
            assert maybe_reboot(cfg, silent_logger, now=outside) is False

    def test_reboot_inside_window_triggers(
        self, example_config, silent_logger: logging.Logger
    ) -> None:
        cfg = replace(
            example_config,
            update=replace(
                example_config.update,
                auto_reboot=True,
                reboot_window_start="03:00",
                reboot_window_end="05:00",
            ),
        )
        inside = dt.datetime(2025, 1, 1, 3, 30, 0)
        with patch(
            "sysmaint.tasks.apt_update.system.reboot_required", return_value=True
        ), patch("sysmaint.tasks.apt_update.run_command") as mock_run:
            assert maybe_reboot(cfg, silent_logger, now=inside) is True
            mock_run.assert_called_once()
            assert "reboot" in mock_run.call_args[0][0]
