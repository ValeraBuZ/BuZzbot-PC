from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from buzzbot_app import AutoClicker
from tools.register_wasteland_solo import _switch_account, _wait_for_main_screen
from tools.run_all_accounts_matrix import run_task


DEFAULT_ACCOUNTS = ("zzub1", "igg_3", "igg_4", "igg_6", "igg_7")
DEFAULT_TASKS = (
    "vip_rewards",
    "radar_rewards",
    "radar_quick",
    "radar_marches",
    "radar_rewards",
    "gathering_boost",
    "food",
    "wood",
    "metal",
    "oil",
)
PROTECTED_ACCOUNT_IDS = {"buzz"}


def main():
    parser = argparse.ArgumentParser(
        description="Safely switch local IGG profiles and run selected BuZzbot tasks"
    )
    parser.add_argument("--serial", default="emulator-5564")
    parser.add_argument("--accounts", default=",".join(DEFAULT_ACCOUNTS))
    parser.add_argument("--tasks", default=",".join(DEFAULT_TASKS))
    parser.add_argument("--resource-level", type=int, default=7)
    parser.add_argument("--research-branch", choices=("economy", "war"), default="economy")
    parser.add_argument("--collective-level", type=int, default=7)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    account_ids = [value.strip() for value in args.accounts.split(",") if value.strip()]
    task_ids = [value.strip() for value in args.tasks.split(",") if value.strip()]
    if any(account_id.lower() in PROTECTED_ACCOUNT_IDS for account_id in account_ids):
        parser.error("The protected BuZz profile cannot be used by this runner")

    output_dir = args.output or (
        PROJECT_ROOT / "test_runs" / f"igg_profiles_{datetime.now():%Y%m%d_%H%M%S}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.json"
    results = []

    switcher = AutoClicker(root=None)
    switcher.stop_schedule_thread()
    switcher.save_config = lambda: None
    switcher.minimize_on_start = False
    switcher.input_backend = "adb"
    switcher.adb_serial = args.serial
    switcher.account_rotation_enabled = False
    switcher._refresh_adb_client()
    for profile in switcher.account_profiles:
        profile["adb_serial"] = args.serial
        profile["ldplayer_index"] = 5

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
                continue

            switched, detail = _switch_account(switcher, account_id, timeout_seconds=300.0)
            account_result["switch_detail"] = detail
            account_result["switched"] = bool(
                switched and _wait_for_main_screen(switcher, args.serial, 120.0)
            )
            summary_path.write_text(
                json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            if not account_result["switched"]:
                continue

            account_dir = output_dir / account_id
            account_dir.mkdir(parents=True, exist_ok=True)
            for task_id in task_ids:
                task_result = run_task(
                    args.serial,
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
    finally:
        switcher.stop()
        if switcher._thread:
            switcher._thread.join(timeout=5.0)
        switcher.stop_schedule_thread()
        summary_path.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(output_dir)
    all_ok = bool(results) and all(
        account.get("switched")
        and all(task.get("settled") and not task.get("error") for task in account["tasks"])
        for account in results
    )
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
