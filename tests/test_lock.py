"""Tests for sysmaint.core.lock — concurrent-run prevention."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sysmaint.core.lock import AlreadyRunning, acquire_lock


def test_lock_can_be_acquired_and_released(tmp_path: Path) -> None:
    lock_path = tmp_path / "sysmaint.lock"
    with acquire_lock(lock_path):
        assert lock_path.exists()
        # PID should be recorded in the lock file.
        assert lock_path.read_text().strip() == str(os.getpid())
    # After release, another acquisition should succeed.
    with acquire_lock(lock_path):
        pass


def test_second_acquisition_raises(tmp_path: Path) -> None:
    """Inside an active lock context, a nested acquisition fails fast."""
    lock_path = tmp_path / "busy.lock"
    with acquire_lock(lock_path), pytest.raises(AlreadyRunning), acquire_lock(lock_path):
        pytest.fail("Should not have acquired the lock twice")


def test_lock_creates_parent_directory(tmp_path: Path) -> None:
    lock_path = tmp_path / "subdir" / "sysmaint.lock"
    with acquire_lock(lock_path):
        assert lock_path.parent.is_dir()
