"""Non-blocking file lock so two timer fires can't trample each other.

A weekly timer with `Persistent=true` can fire late (e.g. just after boot)
right as a manual `sysmaint update` is running. The flock prevents
concurrent apt operations, which would otherwise deadlock on /var/lib/dpkg/lock.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
from collections.abc import Iterator
from pathlib import Path

DEFAULT_LOCK_PATH = Path("/run/sysmaint.lock")


class AlreadyRunning(RuntimeError):
    """Raised when another sysmaint process holds the lock."""


@contextlib.contextmanager
def acquire_lock(path: Path | str = DEFAULT_LOCK_PATH) -> Iterator[None]:
    """Context manager that holds an exclusive non-blocking flock.

    Raises:
        AlreadyRunning: If another process already holds the lock.
        OSError: If the lock file can't be created (e.g. permissions).
    """
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    # O_CREAT | O_RDWR — we need write access for flock to be meaningful
    # and read so we can record the holder's PID for debugging.
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            # Someone else owns the lock. Read their PID (best-effort) for the message.
            holder = _read_holder_pid(fd)
            os.close(fd)
            raise AlreadyRunning(
                f"sysmaint is already running (pid {holder or '?'}); "
                f"lock at {lock_path}"
            ) from exc

        # Record our PID so the next caller can see who's holding the lock.
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
        os.fsync(fd)
        try:
            yield
        finally:
            # flock is released automatically when fd closes, but be explicit.
            with contextlib.suppress(OSError):
                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        with contextlib.suppress(OSError):
            os.close(fd)


def _read_holder_pid(fd: int) -> str | None:
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        data = os.read(fd, 32).decode(errors="replace").strip()
        return data or None
    except OSError:
        return None
