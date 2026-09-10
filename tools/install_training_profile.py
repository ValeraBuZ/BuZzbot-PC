from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from buzzbot.routines import LEGACY_RADAR_TEMPLATE_UIDS
from buzzbot.storage import save_json_with_backup
from buzzbot.training_profiles import read_training_profile, safe_profile_component


def _prepare_installation(manifest, config, install_root):
    """Resolve and validate every destination before changing existing files."""
    for key in ("groups", "images", "routine_tasks", "routine_max_marches"):
        if key not in manifest:
            raise ValueError(f"В профиле отсутствует обязательное поле: {key}.")
    if not isinstance(config, dict):
        raise ValueError("Конфигурация должна быть JSON-объектом.")
    for key in ("groups", "group_schedules", "group_execution"):
        if not isinstance(config.get(key, {}), dict):
            raise ValueError(f"Некорректное поле конфигурации: {key}.")
    images = config.get("images", [])
    if not isinstance(images, list) or any(
        not isinstance(image, dict)
        or not isinstance(image.get("group"), (str, type(None)))
        for image in images
    ):
        raise ValueError("Некорректный список шаблонов конфигурации.")

    task_by_group = {}
    for task in manifest["routine_tasks"]:
        if not isinstance(task.get("group"), str):
            raise ValueError("В задаче профиля отсутствует корректная группа.")
        task_by_group.setdefault(task["group"], safe_profile_component(task["id"]))

    managed_root = (install_root / "img").resolve()
    destinations = set()
    prepared = []
    for image in manifest["images"]:
        uid = safe_profile_component(image.get("uid"))
        group = image.get("group")
        if "group" not in image or not isinstance(group, (str, type(None))):
            raise ValueError("В шаблоне профиля отсутствует корректная группа.")
        target_path = install_root / "img" / task_by_group.get(group, "system") / f"{uid}.png"
        resolved = target_path.resolve()
        if not resolved.is_relative_to(managed_root):
            raise ValueError("Путь шаблона выходит за пределы папки img.")
        if resolved in destinations:
            raise ValueError("Несколько шаблонов профиля используют один файл.")
        destinations.add(resolved)
        prepared.append((image, target_path))
    return managed_root, prepared


def install_profile(profile_path, install_root):
    install_root = Path(install_root)
    config_path = install_root / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))

    with zipfile.ZipFile(profile_path, "r") as archive:
        manifest = read_training_profile(archive)
        managed_root, prepared = _prepare_installation(manifest, config, install_root)
        routine_groups = set(manifest["groups"])
        legacy_paths = []
        for image in config.get("images", []):
            if str(image.get("uid") or "") not in LEGACY_RADAR_TEMPLATE_UIDS:
                continue
            try:
                source = Path(image.get("path", ""))
                source = source if source.is_absolute() else install_root / source
                source = source.resolve()
                if source.is_relative_to(managed_root) and source.exists():
                    legacy_paths.append(source)
            except (OSError, TypeError, ValueError):
                pass
        config["images"] = [
            image for image in config.get("images", [])
            if (
                image.get("group") not in routine_groups
                and str(image.get("uid") or "") not in LEGACY_RADAR_TEMPLATE_UIDS
            )
        ]
        for image, target_path in prepared:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(archive.read(image["path"]))
            installed = deepcopy(image)
            installed["path"] = str(target_path.relative_to(install_root))
            config["images"].append(installed)

    config["routine_tasks"] = manifest["routine_tasks"]
    config["routine_max_marches"] = manifest["routine_max_marches"]
    config["routine_march_deadlines"] = []
    config["routine_next_run"] = {}
    config.setdefault("groups", {}).update(manifest["groups"])
    config["groups"].pop("Радарная станция", None)
    config.setdefault("group_schedules", {}).pop("Радарная станция", None)
    config.setdefault("group_execution", {}).pop("Радарная станция", None)
    config["scale_enabled"] = False
    config["input_backend"] = "adb"
    save_json_with_backup(config_path, config)
    installed_paths = {target.resolve() for _, target in prepared}
    for source in legacy_paths:
        if source not in installed_paths:
            try:
                source.unlink(missing_ok=True)
            except OSError:
                # Cleanup failure must not invalidate the saved configuration.
                pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--install-root", type=Path, required=True)
    args = parser.parse_args()
    install_profile(args.profile, args.install_root)
    print(f"Installed profile: {args.profile}")


if __name__ == "__main__":
    main()
