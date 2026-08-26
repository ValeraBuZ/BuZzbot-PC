from __future__ import annotations

import os
from pathlib import Path
import re
import tempfile


def canonical_device_key(serial, ldplayer_index=None):
    """Return one lock identity for every ADB alias of an LDPlayer instance."""
    index = None
    value = str(serial or "").strip().lower()
    match = re.fullmatch(r"emulator-(\d+)", value)
    if match:
        port = int(match.group(1))
        offset = port - 5554
        if offset >= 0 and offset % 2 == 0:
            index = offset // 2
    else:
        match = re.fullmatch(r"127\.0\.0\.1:(\d+)", value)
        if match:
            port = int(match.group(1))
            offset = port - 5555
            if offset >= 0 and offset % 2 == 0:
                index = offset // 2
    if index is None:
        index = ldplayer_index
    if index is not None:
        try:
            normalized_index = int(index)
        except (TypeError, ValueError):
            normalized_index = -1
        if normalized_index >= 0:
            return f"ldplayer_{normalized_index}"
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(serial or "adb"))


class DeviceLease:
    """Hold an OS-level lock while one process controls an ADB device."""

    def __init__(self, serial, lock_root=None, *, ldplayer_index=None):
        safe_serial = canonical_device_key(serial, ldplayer_index)
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
