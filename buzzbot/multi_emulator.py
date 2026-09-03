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
    assigned_profiles = [
        deepcopy(profile)
        for profile in source.get("account_profiles", [])
        if int(profile.get("ldplayer_index", -1)) == int(index)
    ]
    if assigned_profiles:
        for profile in assigned_profiles:
            profile["ldplayer_index"] = int(index)
            profile["adb_serial"] = str(serial)
            profile["routine_next_run"] = {task_id: 0.0 for task_id in enabled}
        configured_current = str(source.get("current_account_id") or "")
        current_profile = next(
            (
                profile
                for profile in assigned_profiles
                if profile.get("enabled", True)
                and profile.get("id") == configured_current
            ),
            None,
        )
        if current_profile is None:
            normalized_name = str(name or "").casefold()
            current_profile = next(
                (
                    profile
                    for profile in assigned_profiles
                    if profile.get("enabled", True)
                    and normalized_name
                    and normalized_name in {
                        str(profile.get("id") or "").casefold(),
                        str(profile.get("name") or "").casefold(),
                    }
                ),
                None,
            )
        if current_profile is None:
            current_profile = next(
                (profile for profile in assigned_profiles if profile.get("enabled", True)),
                assigned_profiles[0],
            )
        profile_id = str(current_profile.get("id") or "")
        selected_enabled = current_profile.get("task_enabled", {})
        selected_settings = current_profile.get("task_settings", {})
        for task in tasks:
            task_id = str(task.get("id") or "")
            if task_id in selected_enabled:
                task["enabled"] = bool(selected_enabled[task_id])
            if isinstance(selected_settings.get(task_id), dict):
                task.setdefault("settings", {}).update(deepcopy(selected_settings[task_id]))
        profiles = assigned_profiles
        rotation_enabled = bool(source.get("account_rotation_enabled", False)) and sum(
            1 for profile in profiles if profile.get("enabled", True)
        ) > 1
    else:
        safe_id = re.sub(r"[^a-z0-9_]+", "_", str(name or "").casefold()).strip("_")
        profile_id = safe_id or f"ldplayer_{int(index)}"
        profiles = [{
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
        }]
        rotation_enabled = False
    data.update(
        {
            "input_backend": "adb",
            "adb_serial": str(serial),
            "player_width": max(1, int(width or 1280)),
            "player_height": max(1, int(height or 720)),
            "account_profiles": profiles,
            "current_account_id": profile_id,
            "account_rotation_enabled": rotation_enabled,
            "routine_next_run": {task_id: 0.0 for task_id in enabled},
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
