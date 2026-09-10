from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path


_SAVE_LOCK = threading.RLock()


def _replace_with_windows_retry(source, destination):
    """Briefly retry a Windows sharing/access denial, retaining atomic replace."""
    delays = (0.05, 0.10, 0.20)
    for attempt in range(len(delays) + 1):
        try:
            os.replace(source, destination)
            return
        except PermissionError as exc:
            if (
                sys.platform != "win32"
                or getattr(exc, "winerror", None) not in {5, 32, 33}
                or attempt == len(delays)
            ):
                raise
            time.sleep(delays[attempt])


def atomic_write_json(path, data):
    """Replace a complete JSON document without truncating the previous file."""
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    path = Path(path)
    ensure_directory(path.parent)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_windows_retry(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return path


def ensure_directory(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _trim_old_files(directory, pattern, keep_last):
    files = sorted(Path(directory).glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
    for old_file in files[keep_last:]:
        if old_file.is_file():
            old_file.unlink(missing_ok=True)


def save_json_with_backup(path, data, backup_dir=None, keep_backups=10):
    # Validate before changing backups or touching an existing document.
    json.dumps(data, ensure_ascii=False)
    keep_backups = max(0, int(keep_backups))
    path = Path(path)
    ensure_directory(path.parent)

    if backup_dir is None:
        backup_dir = path.parent / "backups" / path.stem
    backup_dir = ensure_directory(backup_dir)

    with _SAVE_LOCK:
        if path.exists():
            backup_path = backup_dir / f"{path.stem}_{_timestamp()}{path.suffix}"
            shutil.copy2(path, backup_path)
        atomic_write_json(path, data)
        _trim_old_files(backup_dir, f"{path.stem}_*{path.suffix}", keep_backups)
    return path


def move_file_to_trash(source_path, trash_root):
    source_path = Path(source_path)
    if not source_path.exists():
        return None

    trash_root = ensure_directory(trash_root)
    source_parent = source_path.parent.name
    destination_name = f"{source_parent}__{source_path.stem}__{_timestamp()}{source_path.suffix}"
    destination = trash_root / destination_name
    shutil.move(str(source_path), str(destination))
    _trim_old_files(trash_root, "*", 500)
    return destination
