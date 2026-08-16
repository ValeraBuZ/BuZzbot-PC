from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import sys


def runtime_dir_for_instance(app_dir, index):
    return Path(app_dir) / "workers" / f"ldplayer_{int(index)}"


def prepare_worker_config(source, *, serial, index, name, width=1280, height=720):
    """Create an isolated config that runs the same selected tasks on one player."""
    data = deepcopy(source)
    tasks = data.get("routine_tasks", [])
    enabled = {
        str(task.get("id") or ""): bool(task.get("enabled", False))
        for task in tasks
        if task.get("id")
    }
    settings = {
        str(task.get("id") or ""): deepcopy(task.get("settings", {}))
        for task in tasks
        if task.get("id")
    }
    safe_id = re.sub(r"[^a-z0-9_]+", "_", str(name or "").casefold()).strip("_")
    profile_id = safe_id or f"ldplayer_{int(index)}"
    profile = {
        "id": profile_id,
        "name": str(name or f"LDPlayer {int(index)}"),
        "enabled": True,
        "ldplayer_index": int(index),
        "adb_serial": str(serial),
        "session_minutes": 1440.0,
        "login_method": "igg",
        "chooser_index": 1,
        "google_login": "",
        "igg_login": "",
        "auto_login": False,
        "switch_group": f"Аккаунт: {name or f'LDPlayer {int(index)}'}",
        "switch_completion_uid": "",
        "task_enabled": enabled,
        "task_settings": settings,
        "routine_next_run": {task_id: 0.0 for task_id in enabled},
    }
    data.update(
        {
            "input_backend": "adb",
            "adb_serial": str(serial),
            "player_width": max(1, int(width or 1280)),
            "player_height": max(1, int(height or 720)),
            "account_profiles": [profile],
            "current_account_id": profile_id,
            "account_rotation_enabled": False,
            "routine_next_run": dict(profile["routine_next_run"]),
            "routine_march_context": "",
            "zombie_level_restore": {},
            "minimize_on_start": False,
        }
    )
    return data


def worker_launch_command(app_file=None):
    if getattr(sys, "frozen", False):
        return [sys.executable, "--worker", "--autostart"]
    script = Path(app_file or sys.argv[0]).resolve()
    return [sys.executable, str(script), "--worker", "--autostart"]


def write_worker_command(runtime_dir, command, sequence):
    path = Path(runtime_dir) / "control.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(
        json.dumps(
            {"command": str(command), "sequence": int(sequence)},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    os.replace(temp_path, path)
    return path
