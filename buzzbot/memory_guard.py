"""Bound LDPlayer memory growth before Windows runs out of commit space."""
from __future__ import annotations

import ctypes
import json
import os
from dataclasses import dataclass

import psutil

from buzzbot.ldplayer import instance_config_path

GIB = 1024 ** 3


@dataclass(frozen=True)
class CommitMemory:
    total: int
    available: int

    @property
    def low(self):
        return self.available < max(2 * GIB, self.total * 0.05)


def system_commit_memory():
    if os.name != "nt":
        return None

    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_uint32), ("load", ctypes.c_uint32)] + [
            (name, ctypes.c_uint64) for name in (
                "physical", "available_physical", "commit", "available_commit",
                "virtual", "available_virtual", "extended_virtual",
            )
        ]

    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return CommitMemory(status.commit, status.available_commit)


def instance_memory_limit(ldconsole, index):
    try:
        data = json.loads(instance_config_path(ldconsole, index).read_text(encoding="utf-8"))
        assigned = max(0, int(data.get("advancedSettings.memorySize", 0))) * 1024 ** 2
    except (OSError, ValueError, TypeError):
        assigned = 0
    # Guest RAM plus graphics/host overhead; never depend on growing page files.
    return max(8 * GIB, assigned * 2 + 2 * GIB)


def instance_private_memory(instance):
    if not instance.running or instance.box_pid <= 0:
        return None
    try:
        process = psutil.Process(instance.box_pid)
        if process.name().lower() != "ld9boxheadless.exe":
            return None
        # A cached PID may have been reused. Verify the VM before acting on it.
        args = process.cmdline()
        comment = args.index("--comment")
        if args[comment + 1] != f"leidian{instance.index}":
            return None
        memory = process.memory_info()
        return getattr(memory, "private", None)
    except (psutil.Error, OSError, ValueError, IndexError):
        return None


def restart_needed(private_bytes, limit, commit):
    if private_bytes is None:
        return False
    return private_bytes >= limit or (
        commit is not None and commit.low and private_bytes >= max(4 * GIB, limit / 2)
    )
