from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import cv2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from buzzbot_app import AutoClicker, CONFIG_FILE, GAME_PACKAGE, logger
from buzzbot.adb import AdbClient, AdbError
from buzzbot.ldplayer import (
    find_ldconsole,
    index_from_serial,
    list_instances,
    serial_for_index,
    tcp_serial_for_index,
)
from buzzbot.routines import effective_task_group


DEFAULT_INDEXES = (1, 2, 3, 4, 5, 7)
LIVE_STATE_FILE = PROJECT_ROOT / "test_runs" / "live_runtime_state.json"
DEFAULT_TASKS = (
    "vip_rewards",
    "mail_rewards",
    "research",
    "train_infantry",
    "train_riders",
    "train_shooters",
    "train_vehicles",
    "processing_factory",
    "completed_tasks",
    "gathering_boost",
    "food",
    "wood",
    "metal",
    "oil",
)
TASK_TIMEOUTS = {
    "game_login": 600.0,
    "vip_rewards": 60.0,
    "alliance_donations": 160.0,
    "radar_rewards": 180.0,
    "radar_quick": 360.0,
    "radar_marches": 420.0,
    "mail_rewards": 75.0,
    "research": 90.0,
    "train_infantry": 65.0,
    "train_riders": 65.0,
    "train_shooters": 65.0,
    "train_vehicles": 65.0,
    "processing_factory": 100.0,
    "completed_tasks": 100.0,
    "gathering_boost": 60.0,
    "food": 75.0,
    "wood": 75.0,
    "metal": 75.0,
    "oil": 75.0,
    "collective_mind": 100.0,
    "prize_hunt": 300.0,
    "wasteland_exploration": 480.0,
}


def _run_hidden(command, timeout=30):
    kwargs = {
        "cwd": PROJECT_ROOT,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
        "check": False,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run([str(part) for part in command], **kwargs)


def _safe_name(value):
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "")).strip("_")
    return cleaned or "account"


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_live_state():
    try:
        return json.loads(LIVE_STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"accounts": {}}


def _active_boost_result(active_until):
    deadline = datetime.fromtimestamp(float(active_until)).isoformat(timespec="minutes")
    return {
        "task": "gathering_boost",
        "started": False,
        "settled": True,
        "actions": 0,
        "completed_steps": ["active_timer_guard"],
        "status": f"Усиление уже активно до {deadline}",
        "duration_seconds": 0.0,
        "screenshot": "",
        "error": "",
        "effect_until": float(active_until),
    }


def _task_blocked_by_march_capacity(task, active_marches, max_marches):
    """Treat a full march queue as a safe skip instead of a test timeout."""
    return bool(
        task.get("uses_march", False)
        and int(active_marches) >= int(max_marches)
    )


def _task_reached_live_checkpoint(task_id, completed_steps):
    """Return whether an intentionally repeating task proved its first cycle."""
    checkpoints = {
        "prize_hunt": {"again", "match", "confirm"},
    }
    expected = checkpoints.get(str(task_id), set())
    return bool(expected.intersection({str(step) for step in completed_steps}))


def _routine_outcome_is_success(task_id, outcome):
    """Accept completion or a task-specific, positively identified busy state."""
    if not isinstance(outcome, dict):
        return False
    normalized_task_id = str(task_id or "")
    if str(outcome.get("task_id") or "") != normalized_task_id:
        return False
    if outcome.get("outcome") == "completed":
        return True
    if outcome.get("outcome") != "deferred_unavailable":
        return False
    reason = str(outcome.get("reason") or "")
    return bool(
        (normalized_task_id.startswith("train_") and reason == "max_queue_checks")
        or (normalized_task_id == "research" and reason == "max_lab_checks")
    )


def _game_is_foreground(client):
    try:
        return client.current_foreground_package() == GAME_PACKAGE
    except AdbError:
        return False


@contextmanager
def _task_log(path):
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)
    try:
        yield
    finally:
        logger.removeHandler(handler)
        handler.close()


def _expected_adb_serials(configured_serial, instance_index=None):
    expected_index = instance_index
    if expected_index is None:
        expected_index = index_from_serial(configured_serial)
    if expected_index is None:
        configured = str(configured_serial or "").strip()
        return (configured,) if configured else ()
    aliases = (
        serial_for_index(expected_index),
        tcp_serial_for_index(expected_index),
    )
    configured = str(configured_serial or "").strip()
    if configured in aliases:
        return (configured, *tuple(item for item in aliases if item != configured))
    return aliases


def _wait_for_adb(client, instance_index=None, timeout_seconds=150.0):
    configured_serial = client.serial
    candidates = _expected_adb_serials(configured_serial, instance_index)
    tcp_serial = next((item for item in candidates if item.startswith("127.0.0.1:")), None)
    deadline = time.monotonic() + timeout_seconds
    next_connect_at = 0.0
    while time.monotonic() < deadline:
        for serial in candidates:
            client.serial = serial
            if not client.is_available():
                continue
            try:
                boot_completed = client._run(
                    ["shell", "getprop", "sys.boot_completed"],
                    timeout=5,
                )
                if str(boot_completed).strip() == "1":
                    return serial
            except Exception:
                pass
        now = time.monotonic()
        if tcp_serial and now >= next_connect_at:
            try:
                AdbClient(client.adb_path, "").connect(tcp_serial)
            except AdbError:
                pass
            next_connect_at = now + 8.0
        time.sleep(2.0)
    client.serial = candidates[0] if candidates else configured_serial
    return None


def _capture(client, path):
    try:
        frame = client.screenshot_bgr()
        return bool(cv2.imwrite(str(path), frame))
    except Exception:
        logger.exception("Live matrix screenshot failed: %s", path)
        return False


def _task_settings(task_id, research_branch, resource_level, collective_level):
    if task_id == "research":
        return {"branch": research_branch, "use_speedups": False}
    if task_id == "gathering_boost":
        return {"boost_hours": 8}
    if task_id in {"food", "wood", "metal", "oil"}:
        return {"resource_level": resource_level}
    if task_id == "collective_mind":
        return {"level": collective_level}
    if task_id.startswith("train_"):
        return {"highest_tier": True, "collect_finished": True}
    return {}


def _activate_account_profile(bot, account_key):
    """Apply per-account task state without persisting live-test changes."""
    if bot.select_account_profile(account_key, save=False):
        return True
    bot.current_account_id = account_key
    return False


def run_task(
    serial,
    account_key,
    task_id,
    output_dir,
    research_branch,
    resource_level,
    collective_level,
):
    started_at = time.time()
    log_path = output_dir / f"{task_id}.log"
    screenshot_path = output_dir / f"{task_id}.png"
    result = {
        "task": task_id,
        "started": False,
        "settled": False,
        "actions": 0,
        "completed_steps": [],
        "status": "",
        "duration_seconds": 0.0,
        "screenshot": screenshot_path.name,
        "error": "",
        "effect_until": 0.0,
    }
    observed_steps = set()

    with _task_log(log_path):
        bot = AutoClicker(root=None)
        bot.stop_schedule_thread()
        # Live tests must never alter task checkboxes or account settings.
        bot.save_config = lambda: None
        try:
            bot.minimize_on_start = False
            bot.input_backend = "adb"
            bot.adb_serial = serial
            _activate_account_profile(bot, account_key)
            bot.routine_march_context = f"adb:{serial}:{account_key}"
            bot.routine_march_deadlines = []
            bot._refresh_adb_client()
            for task in bot.routine_tasks:
                enabled = task.get("id") == task_id
                task["enabled"] = enabled
                bot.groups[effective_task_group(task)] = enabled

            selected = bot.get_routine_task(task_id)
            if selected is None:
                result["error"] = "unknown task"
                return result
            selected.setdefault("settings", {}).update(
                _task_settings(task_id, research_branch, resource_level, collective_level)
            )
            minimum_timeout = 330.0 if task_id == "game_login" else 20.0
            if task_id == "heal":
                minimum_timeout = 8.0
            selected["timeout_seconds"] = max(
                float(selected.get("timeout_seconds", 0.0) or 0.0),
                minimum_timeout,
            )

            group = effective_task_group(selected)
            tracked_paths = {image["path"] for image in bot.search_images}
            initial_stats = {path: int(bot.stats.get(path, 0)) for path in tracked_paths}
            bot.routine_last_outcome = {}
            bot.routine_next_run[task_id] = 0.0
            result["started"] = bool(bot.start_task_only(task_id))
            if not result["started"]:
                result["status"] = bot.status_message
                result["error"] = "task did not start"
                return result

            timeout_seconds = TASK_TIMEOUTS.get(task_id, 75.0)
            deadline = time.time() + timeout_seconds
            while time.time() < deadline and bot.is_running:
                observed_steps.update(bot.routine_completed_steps)
                if _task_reached_live_checkpoint(task_id, observed_steps):
                    result["settled"] = True
                    break
                if (
                    bot.current_routine_task_id is None
                    and _task_blocked_by_march_capacity(
                        selected,
                        bot.get_active_marches(),
                        bot.routine_max_marches,
                    )
                ):
                    result["settled"] = True
                    break
                next_run = float(bot.routine_next_run.get(task_id, 0.0) or 0.0)
                if bot.current_routine_task_id is None and next_run > time.time() + 1.0:
                    outcome = dict(getattr(bot, "routine_last_outcome", {}) or {})
                    observed_steps.update(outcome.get("completed_steps", ()))
                    if task_id == "game_login":
                        result["settled"] = bool(bot._is_main_screen_visible())
                        if not result["settled"]:
                            result["error"] = "main screen was not detected"
                    elif _routine_outcome_is_success(task_id, outcome):
                        result["settled"] = True
                    else:
                        outcome_name = str(outcome.get("outcome") or "missing_outcome")
                        reason = str(outcome.get("reason") or "").strip()
                        result["error"] = f"routine ended with {outcome_name}"
                        if reason:
                            result["error"] += f": {reason}"
                    break
                time.sleep(1.0)

            result["actions"] = sum(
                max(0, int(bot.stats.get(path, 0)) - initial_stats[path])
                for path in tracked_paths
            )
            observed_steps.update(bot.routine_completed_steps)
            result["completed_steps"] = sorted(observed_steps)
            result["status"] = bot.status_message
            result["effect_until"] = float(
                selected.get("settings", {}).get("active_until", 0.0) or 0.0
            )
            if not result["settled"] and not result["error"]:
                result["error"] = "timeout"
        except Exception as exc:
            logger.exception("Live matrix task failed: account=%s task=%s", account_key, task_id)
            result["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            result["status"] = result["status"] or bot.status_message
            observed_steps.update(bot.routine_completed_steps)
            result["completed_steps"] = sorted(observed_steps)
            if bot.adb_client:
                _capture(bot.adb_client, screenshot_path)
            bot.stop()
            if bot._thread:
                bot._thread.join(timeout=5.0)
            bot.stop_schedule_thread()
            result["duration_seconds"] = round(time.time() - started_at, 2)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--indexes", default=",".join(map(str, DEFAULT_INDEXES)))
    parser.add_argument("--tasks", default=",".join(DEFAULT_TASKS))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--research-branch", choices=("economy", "war"), default="economy")
    parser.add_argument("--resource-level", type=int, default=7)
    parser.add_argument("--collective-level", type=int, choices=(6, 7), default=6)
    parser.add_argument("--startup-settle-seconds", type=float, default=15.0)
    parser.add_argument("--keep-running", action="store_true")
    args = parser.parse_args()

    indexes = [int(value.strip()) for value in args.indexes.split(",") if value.strip()]
    tasks = [value.strip() for value in args.tasks.split(",") if value.strip()]
    output_root = args.output or (
        PROJECT_ROOT / "test_runs" / f"matrix_{datetime.now():%Y%m%d_%H%M%S}"
    )
    output_root.mkdir(parents=True, exist_ok=True)

    ldconsole = find_ldconsole()
    if ldconsole is None:
        raise SystemExit("LDPlayer console not found")
    instances = {instance.index: instance for instance in list_instances(ldconsole)}
    original_config = CONFIG_FILE.read_bytes()
    (output_root / "config.before.json").write_bytes(original_config)
    summary = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "game_package": GAME_PACKAGE,
        "indexes": indexes,
        "tasks": tasks,
        "accounts": [],
    }
    live_state = _load_live_state()
    live_accounts = live_state.setdefault("accounts", {})

    try:
        for index in indexes:
            instance = instances.get(index)
            if instance is None:
                summary["accounts"].append({"index": index, "error": "LDPlayer instance not found"})
                continue
            account_key = f"ld{index}_{_safe_name(instance.name)}"
            account_dir = output_root / account_key
            account_dir.mkdir(parents=True, exist_ok=True)
            account_result = {
                "index": index,
                "name": instance.name,
                "serial": instance.adb_serial,
                "resolution": f"{instance.width}x{instance.height}",
                "tasks": [],
                "error": "",
            }
            summary["accounts"].append(account_result)
            _write_json(output_root / "summary.json", summary)

            try:
                launch = _run_hidden([ldconsole, "launch", "--index", index], timeout=30)
                if launch.returncode != 0:
                    raise RuntimeError(launch.stderr.strip() or "LDPlayer launch failed")
                client = AdbClient(serial=instance.adb_serial)
                connected_serial = _wait_for_adb(client, instance.index)
                if not connected_serial:
                    raise RuntimeError(f"ADB did not become ready: {instance.adb_serial}")
                account_result["configured_serial"] = instance.adb_serial
                account_result["serial"] = connected_serial
                time.sleep(max(0.0, args.startup_settle_seconds))

                login_result = run_task(
                    connected_serial,
                    account_key,
                    "game_login",
                    account_dir,
                    args.research_branch,
                    min(7, max(1, args.resource_level)),
                    args.collective_level,
                )
                account_result["tasks"].append(login_result)
                _write_json(output_root / "summary.json", summary)
                if not login_result["settled"]:
                    account_result["error"] = "game login did not reach a stable main screen"
                    continue

                for task_id in tasks:
                    recovery_result = None
                    if not _game_is_foreground(client):
                        logger.warning(
                            "Doomsday left foreground before %s on %s; running login recovery",
                            task_id,
                            account_key,
                        )
                        recovery_result = run_task(
                            connected_serial,
                            account_key,
                            "game_login",
                            account_dir,
                            args.research_branch,
                            min(7, max(1, args.resource_level)),
                            args.collective_level,
                        )
                        if not recovery_result["settled"]:
                            task_result = {
                                "task": task_id,
                                "started": False,
                                "settled": False,
                                "actions": 0,
                                "completed_steps": [],
                                "status": recovery_result.get("status", ""),
                                "duration_seconds": recovery_result.get("duration_seconds", 0.0),
                                "screenshot": recovery_result.get("screenshot", ""),
                                "error": "game login recovery did not reach a stable main screen",
                                "effect_until": 0.0,
                                "foreground_recovered": False,
                            }
                            account_result["tasks"].append(task_result)
                            _write_json(output_root / "summary.json", summary)
                            continue

                    account_state = live_accounts.setdefault(instance.adb_serial, {})
                    active_until = float(
                        account_state.get("gathering_boost_active_until", 0.0) or 0.0
                    )
                    if task_id == "gathering_boost" and active_until > time.time():
                        task_result = _active_boost_result(active_until)
                    else:
                        task_result = run_task(
                            connected_serial,
                            account_key,
                            task_id,
                            account_dir,
                            args.research_branch,
                            min(7, max(1, args.resource_level)),
                            args.collective_level,
                        )
                        effect_until = float(task_result.get("effect_until", 0.0) or 0.0)
                        if task_id == "gathering_boost" and effect_until > time.time():
                            account_state["gathering_boost_active_until"] = effect_until
                            account_state["updated_at"] = datetime.now().isoformat(timespec="seconds")
                            _write_json(LIVE_STATE_FILE, live_state)
                    if recovery_result is not None:
                        task_result["foreground_recovered"] = True
                    account_result["tasks"].append(task_result)
                    _write_json(output_root / "summary.json", summary)
            except Exception as exc:
                account_result["error"] = f"{type(exc).__name__}: {exc}"
                _write_json(output_root / "summary.json", summary)
            finally:
                if not args.keep_running:
                    _run_hidden([ldconsole, "quit", "--index", index], timeout=30)
                    time.sleep(3.0)
    finally:
        CONFIG_FILE.write_bytes(original_config)
        summary["finished_at"] = datetime.now().isoformat(timespec="seconds")
        _write_json(output_root / "summary.json", summary)

    print(output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
