from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.run_all_accounts_matrix import run_task


DEFAULT_TASKS = (
    "vip_rewards",
    "radar_rewards",
    "radar_quick",
    "radar_marches",
    "gathering_boost",
    "food",
    "wood",
    "metal",
    "oil",
)


def main():
    parser = argparse.ArgumentParser(description="Run selected BuZzbot tasks on the current account")
    parser.add_argument("--serial", default="emulator-5564")
    parser.add_argument("--account", required=True)
    parser.add_argument("--tasks", default=",".join(DEFAULT_TASKS))
    parser.add_argument("--resource-level", type=int, default=7)
    parser.add_argument("--research-branch", choices=("economy", "war"), default="economy")
    parser.add_argument("--collective-level", type=int, default=7)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    output_dir = args.output or (
        PROJECT_ROOT
        / "test_runs"
        / f"current_account_{args.account}_{datetime.now():%Y%m%d_%H%M%S}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.json"
    results = []

    for task_id in (item.strip() for item in args.tasks.split(",") if item.strip()):
        result = run_task(
            args.serial,
            args.account,
            task_id,
            output_dir,
            args.research_branch,
            args.resource_level,
            args.collective_level,
        )
        results.append(result)
        summary_path.write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(result, ensure_ascii=False), flush=True)

    print(output_dir)
    return 0 if results and all(item.get("settled") and not item.get("error") for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
