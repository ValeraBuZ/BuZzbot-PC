from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from buzzbot.routines import (
    upgrade_mysterious_merchant_metadata,
    upgrade_processing_runtime_metadata,
    upgrade_radar_runtime_metadata,
    upgrade_repeatable_claim_metadata,
    upgrade_resource_runtime_metadata,
    upgrade_strict_runtime_metadata,
)
from buzzbot.version import APP_VERSION


def upgrade_profile(profile_path: Path) -> None:
    profile_path = profile_path.resolve()
    temporary_path = profile_path.with_suffix(profile_path.suffix + ".upgraded.tmp")
    with zipfile.ZipFile(profile_path, "r") as source:
        manifest = json.loads(source.read("profile.json").decode("utf-8"))
        images = manifest.get("images", [])
        tasks = manifest.get("routine_tasks", [])
        upgrade_strict_runtime_metadata(images, tasks)
        upgrade_resource_runtime_metadata(images, tasks)
        upgrade_radar_runtime_metadata(images, tasks)
        upgrade_repeatable_claim_metadata(images, tasks)
        upgrade_processing_runtime_metadata(images, tasks)
        upgrade_mysterious_merchant_metadata(images, tasks)
        manifest["app_version"] = APP_VERSION

        with zipfile.ZipFile(
            temporary_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as target:
            for info in source.infolist():
                if info.filename == "profile.json":
                    payload = json.dumps(
                        manifest,
                        ensure_ascii=False,
                        indent=2,
                    ).encode("utf-8")
                else:
                    payload = source.read(info.filename)
                target.writestr(info, payload)
    os.replace(temporary_path, profile_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("profile", type=Path)
    args = parser.parse_args()
    upgrade_profile(args.profile)
    print(f"Upgraded profile metadata to {APP_VERSION}: {args.profile}")


if __name__ == "__main__":
    main()
