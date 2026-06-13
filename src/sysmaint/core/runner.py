"""Subprocess runner with timeouts, structured results, and apt defaults.

Design notes:
- The runner never mutates the caller's command list — a past bug caused
  duplicate `sudo` prepends when the same list was reused.
- All commands carry an explicit timeout. Hanging apt/network calls were
  the second-most-common failure mode in the previous implementation.
- `apt_command()` enforces non-interactive defaults so package upgrades
  never block waiting for stdin during scheduled runs.
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    """Outcome of a single command execution."""

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    duration: float  # seconds, monotonic
    timed_out: bool = False

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def pretty_command(self) -> str:
        return shlex.join(self.command)


class CommandError(RuntimeError):
    """Raised when a command exits non-zero (and check=True) or times out."""

    def __init__(self, result: CommandResult) -> None:
        self.result = result
        if result.timed_out:
            msg = f"Command timed out after {result.duration:.1f}s: {result.pretty_command()}"
        else:
            msg = (
                f"Command failed (exit {result.returncode}): "
                f"{result.pretty_command()}\n{result.stderr.strip()[:500]}"
            )
        super().__init__(msg)


def run_command(
    command: list[str] | tuple[str, ...],
    *,
    timeout: int = 300,
    env: dict[str, str] | None = None,
    check: bool = True,
    logger: logging.Logger | None = None,
) -> CommandResult:
    """Run a command without invoking a shell. Returns a structured result.

    Args:
        command: Argv list. Never mutated — internally copied.
        timeout: Wall-clock seconds before the child is killed.
        env: Extra environment variables merged onto os.environ for the child.
        check: If True (default), raise CommandError on non-zero exit or timeout.
        logger: Optional logger; the runner logs invocation + outcome at INFO/ERROR.

    Raises:
        CommandError: On non-zero exit or timeout when check=True.
    """
    cmd = tuple(command)  # immutable copy — defensive against caller mutation
    if not cmd:
        raise ValueError("command must contain at least one argument")

    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    if logger:
        logger.info("Running: %s (timeout=%ds)", shlex.join(cmd), timeout)

    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            check=False,  # we raise our own typed exception
            capture_output=True,
            text=True,
            timeout=timeout,
            env=full_env,
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - start
        result = CommandResult(
            command=cmd,
            returncode=-1,
            stdout=(exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
            stderr=f"Command timed out after {timeout}s",
            duration=duration,
            timed_out=True,
        )
        if logger:
            logger.error("Timeout after %ds: %s", timeout, shlex.join(cmd))
        if check:
            raise CommandError(result) from exc
        return result

    duration = time.monotonic() - start
    result = CommandResult(
        command=cmd,
        returncode=proc.returncode,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        duration=duration,
    )

    if logger:
        if result.succeeded:
            logger.info("OK in %.1fs: %s", duration, shlex.join(cmd))
        else:
            # Truncate stderr in the log line; the full body is on the result object.
            logger.error(
                "Failed (exit %d) in %.1fs: %s\n%s",
                proc.returncode,
                duration,
                shlex.join(cmd),
                result.stderr.strip()[:500],
            )

    if check and not result.succeeded:
        raise CommandError(result)
    return result


# Non-interactive apt environment. Prevents debconf from blocking on stdin
# when a package upgrade wants to ask about modified config files.
APT_ENV: dict[str, str] = {
    "DEBIAN_FRONTEND": "noninteractive",
    "APT_LISTCHANGES_FRONTEND": "none",
}


def apt_command(args: list[str]) -> list[str]:
    """Build an apt-get argv with safe non-interactive defaults.

    `--force-confold` keeps the existing config file on package upgrades;
    `--force-confdef` accepts the package default when there is no existing
    user-modified version. Together they prevent the "are you sure?" stall.
    """
    return [
        "apt-get",
        "-y",
        "-o",
        "Dpkg::Options::=--force-confold",
        "-o",
        "Dpkg::Options::=--force-confdef",
        *args,
    ]
