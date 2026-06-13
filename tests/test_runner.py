"""Tests for sysmaint.core.runner."""

from __future__ import annotations

import os

import pytest

from sysmaint.core.runner import (
    APT_ENV,
    CommandError,
    apt_command,
    run_command,
)


class TestRunCommand:
    def test_success_returns_structured_result(self) -> None:
        result = run_command(["echo", "hello"], timeout=5)
        assert result.succeeded
        assert result.returncode == 0
        assert result.stdout.strip() == "hello"
        assert result.duration >= 0
        assert not result.timed_out

    def test_nonzero_exit_raises_command_error(self) -> None:
        with pytest.raises(CommandError) as exc_info:
            run_command(["false"], timeout=5)
        assert exc_info.value.result.returncode != 0
        assert not exc_info.value.result.succeeded

    def test_nonzero_exit_with_check_false_does_not_raise(self) -> None:
        result = run_command(["false"], timeout=5, check=False)
        assert not result.succeeded
        assert result.returncode != 0

    def test_timeout_raises_command_error_with_timed_out_flag(self) -> None:
        with pytest.raises(CommandError) as exc_info:
            # `sleep 5` should be killed by our 1s timeout.
            run_command(["sleep", "5"], timeout=1)
        assert exc_info.value.result.timed_out

    def test_timeout_with_check_false_returns_result(self) -> None:
        result = run_command(["sleep", "5"], timeout=1, check=False)
        assert result.timed_out
        assert not result.succeeded

    def test_empty_command_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            run_command([], timeout=5)

    def test_does_not_mutate_caller_command_list(self) -> None:
        """Regression: the legacy runner did `command.insert(0, 'sudo')`,
        mutating the caller's list. A second use produced `['sudo', 'sudo', ...]`.
        """
        cmd = ["echo", "x"]
        original = list(cmd)
        run_command(cmd, timeout=5)
        run_command(cmd, timeout=5)
        assert cmd == original, "run_command must not mutate its argument"

    def test_env_is_merged_onto_os_environ(self) -> None:
        """Custom env vars should be visible to the child, AND existing
        os.environ should still be present (we merge, not replace)."""
        marker_key = "SYSMAINT_TEST_MARKER"
        os.environ.setdefault("PATH", "/usr/bin:/bin")
        result = run_command(
            ["sh", "-c", f'echo "$PATH:::${marker_key}"'],
            env={marker_key: "set-by-test"},
            timeout=5,
        )
        assert ":::set-by-test" in result.stdout
        # PATH from parent env survived.
        assert "/usr/bin" in result.stdout or "/bin" in result.stdout


class TestAptCommand:
    def test_includes_force_confold_and_yes(self) -> None:
        cmd = apt_command(["dist-upgrade"])
        assert cmd[0] == "apt-get"
        assert "-y" in cmd
        joined = " ".join(cmd)
        assert "Dpkg::Options::=--force-confold" in joined
        assert "Dpkg::Options::=--force-confdef" in joined
        assert cmd[-1] == "dist-upgrade"

    def test_passes_through_multiple_args(self) -> None:
        cmd = apt_command(["install", "postfix"])
        assert cmd[-2:] == ["install", "postfix"]


class TestAptEnv:
    def test_disables_interactive_frontends(self) -> None:
        assert APT_ENV["DEBIAN_FRONTEND"] == "noninteractive"
        assert APT_ENV["APT_LISTCHANGES_FRONTEND"] == "none"
