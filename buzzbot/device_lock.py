from __future__ import annotations

import os
from pathlib import Path
import re
import tempfile


class DeviceLease:
    """Hold an OS-level lock while one process controls an ADB device."""

    def __init__(self, serial, lock_root=None):
        safe_serial = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(serial or "adb"))
        root = Path(lock_root or Path(tempfile.gettempdir()) / "BuZzbot" / "device-locks")
        self.path = root / f"{safe_serial}.lock"
        self._handle = None

    @property
    def acquired(self):
        return self._handle is not None

    def acquire(self):
        if self.acquired:
            return True

        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)

        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False

        self._handle = handle
        return True

    def release(self):
        handle = self._handle
        if handle is None:
            return
        self._handle = None
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError(f"ADB device is already locked: {self.path.stem}")
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        self.release()
