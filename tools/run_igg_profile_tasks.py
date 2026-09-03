from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from buzzbot.adb import AdbClient
from buzzbot.ldplayer import find_ldconsole, list_instances
from tools.register_wasteland_solo import _switch_account, _wait_for_main_screen
from tools.run_all_accounts_matrix import (
    _new_read_only_bot,
    _run_hidden,
    _wait_for_adb,
    run_task,
)


DEFAULT_ACCOUNTS = ("zzub1", "igg_3", "igg_4", "igg_5", "igg_6", "igg_7")
DEFAULT_TASKS = (
    "processing_factory",
    "vip_rewards",
    "radar_rewards",
    "radar_quick",
    "radar_marches",
    "radar_rewards",
    "completed_tasks",
    "gathering_boost",
    "food",
    "wood",
    "metal",
    "oil",
)
PROTECTED_ACCOUNT_IDS = {"buzz"}


def _configured_igg_account_ids(bot):
    """Return enabled IGG profiles that have a complete local credential pair."""
    configured = [
        str(profile.get("id") or "")
        for profile in bot.account_profiles
        if profile.get("enabled", True)
        and str(profile.get("login_method") or "igg").strip().lower() == "igg"
        and bot.account_has_saved_login(profile.get("id"))
        and bot.account_has_saved_password(profile.get("id"))
    ]
    configured_set = set(configured)
    preferred = [account_id for account_id in DEFAULT_ACCOUNTS if account_id in configured_set]
    return preferred + [account_id for account_id in configured if account_id not in preferred]


def _requested_account_ids(value, bot):
    requested = [item.strip() for item in str(value or "").split(",") if item.strip()]
    if len(requested) == 1 and requested[0].casefold() == "all":
        return _configured_igg_account_ids(bot)
    return requested


def _task_result_allows_next(task_result):
    """A strict pass advances only after a confirmed, error-free task result."""
    return bool(task_result.get("settled") and not task_result.get("error"))


def main():
    parser = argparse.ArgumentParser(
        description="Safely switch local IGG profiles and run selected BuZzbot tasks"
    )
    parser.add_argument("--serial", default="emulator-5564")
    parser.add_argument("--ldplayer-index", type=int, default=5)
    parser.add_argument(
        "--accounts",
        default="all",
        help="Comma-separated IGG profile IDs, or 'all' for every configured IGG profile",
    )
    parser.add_argument("--tasks", default=",".join(DEFAULT_TASKS))
    parser.add_argument("--resource-level", type=int, default=7)
    parser.add_argument("--research-branch", choices=("economy", "war"), default="economy")
    parser.add_argument("--collective-level", type=int, default=7)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--keep-running",
        action="store_true",
        help="Leave LDPlayer running when this command launched it",
    )
    args = parser.parse_args()

    task_ids = [value.strip() for value in args.tasks.split(",") if value.strip()]

    output_dir = args.output or (
        PROJECT_ROOT / "test_runs" / f"igg_profiles_{datetime.now():%Y%m%d_%H%M%S}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.json"
    results = []

    ldconsole = find_ldconsole()
    if ldconsole is None:
        parser.error("LDPlayer console not found")
    instance = next(
        (item for item in list_instances(ldconsole) if item.index == args.ldplayer_index),
        None,
    )
    if instance is None:
        parser.error(f"LDPlayer index {args.ldplayer_index} not found")
    launched_here = not instance.running
    if launched_here:
        launch = _run_hidden(
            [ldconsole, "launch", "--index", args.ldplayer_index], timeout=30
        )
        if launch.returncode != 0:
            parser.error(launch.stderr.strip() or "LDPlayer launch failed")

    client = AdbClient(serial=args.serial)
    connected_serial = _wait_for_adb(
        client,
        instance_index=args.ldplayer_index,
        timeout_seconds=180.0,
    )
    if not connected_serial:
        if launched_here and not args.keep_running:
            _run_hidden([ldconsole, "quit", "--index", args.ldplayer_index], timeout=30)
        parser.error(f"ADB did not become ready for LDPlayer index {args.ldplayer_index}")

    switcher = _new_read_only_bot()
    switcher.stop_schedule_thread()
    switcher.minimize_on_start = False
    switcher.input_backend = "adb"
    switcher.adb_serial = connected_serial
    switcher.account_rotation_enabled = False
    switcher._refresh_adb_client()
    account_ids = _requested_account_ids(args.accounts, switcher)
    if not account_ids:
        parser.error("No fully configured IGG profiles were found")
    if any(account_id.lower() in PROTECTED_ACCOUNT_IDS for account_id in account_ids):
        parser.error("The protected BuZz profile cannot be used by this runner")
    for profile in switcher.account_profiles:
        profile["adb_serial"] = connected_serial
        profile["ldplayer_index"] = args.ldplayer_index

    pass_blocked = False
    try:
        for account_id in account_ids:
            profile = next(
                (item for item in switcher.account_profiles if item.get("id") == account_id),
                None,
            )
            account_result = {
                "account_id": account_id,
                "name": profile.get("name") if profile else account_id,
                "switched": False,
                "switch_detail": "",
                "tasks": [],
            }
            results.append(account_result)
            if profile is None or profile.get("login_method") != "igg":
                account_result["switch_detail"] = "profile is missing or is not IGG"
                summary_path.write_text(
                    json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                pass_blocked = True
                continue

            # An explicit live-test invocation authorizes switching the listed
            # local profiles. Enable it only in this in-memory runner; the
            # user's saved auto-login preference is never overwritten.
            profile["auto_login"] = True

            switched, detail = _switch_account(switcher, account_id, timeout_seconds=300.0)
            account_result["switch_detail"] = detail
            account_result["switched"] = bool(
                switched and _wait_for_main_screen(switcher, connected_serial, 120.0)
            )
            summary_path.write_text(
                json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            if not account_result["switched"]:
                pass_blocked = True
                continue

            account_dir = output_dir / account_id
            account_dir.mkdir(parents=True, exist_ok=True)
            for task_id in task_ids:
                task_result = run_task(
                    connected_serial,
                    account_id,
                    task_id,
                    account_dir,
                    args.research_branch,
                    args.resource_level,
                    args.collective_level,
                )
                account_result["tasks"].append(task_result)
                summary_path.write_text(
                    json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(
                    json.dumps(
                        {"account_id": account_id, "result": task_result},
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                if not _task_result_allows_next(task_result):
                    if not _wait_for_main_screen(switcher, connected_serial, 2.0):
                        recovered = switcher._return_to_main_screen(
                            max_back_steps=6,
                            require_settlement=True,
                        )
                        if not recovered:
                            account_result["switch_detail"] = (
                                f"{account_result['switch_detail']}; "
                                f"recovery failed after {task_id}"
                            ).strip("; ")
                    account_result["switch_detail"] = (
                        f"{account_result['switch_detail']}; "
                        f"strict pass stopped after {task_id}"
                    ).strip("; ")
                    pass_blocked = True
                    break
    finally:
        switcher.stop()
        if switcher._thread:
            switcher._thread.join(timeout=5.0)
        switcher.stop_schedule_thread()
        summary_path.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if launched_here and not args.keep_running:
            _run_hidden([ldconsole, "quit", "--index", args.ldplayer_index], timeout=30)

    print(output_dir)
    all_ok = not pass_blocked and bool(results) and len(results) == len(account_ids) and all(
        account.get("switched")
        and all(task.get("settled") and not task.get("error") for task in account["tasks"])
        for account in results
    )
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
