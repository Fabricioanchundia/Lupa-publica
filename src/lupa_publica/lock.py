"""Prevent two pipeline runs from writing the same data at the same time.

Two concurrent backfills once wrote into the same ``.part`` file and produced a
ZIP with a bad CRC. An exclusive lock makes that impossible.

The lock uses ``flock``: the operating system releases it automatically when
the process ends, even after a crash, so a stale lock can never block future
runs. Linux and macOS only (WSL and GitHub Actions runners are Linux).
"""

from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class AlreadyRunningError(RuntimeError):
    """Another pipeline run currently holds the lock."""


@contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    """Hold an exclusive, non-blocking lock on ``path`` for the duration of the block."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AlreadyRunningError(f"another pipeline run is already running ({path})") from exc
        fh.seek(0)
        fh.truncate()
        fh.write(f"{os.getpid()}\n")
        fh.flush()
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
