"""Validate imported profiles before changing settings or writing templates."""
from __future__ import annotations

import json
import math
from pathlib import PurePosixPath
import re


MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_TEMPLATE_BYTES = 32 * 1024 * 1024
MAX_PROFILE_BYTES = 256 * 1024 * 1024


def safe_profile_component(value):
    name = str(value or "")
    if (
        not name or name in {".", ".."} or name.endswith((".", " "))
        or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
        or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?", name)
    ):
        raise ValueError("Профиль содержит небезопасное имя файла или задачи.")
    return name


def read_training_profile(archive):
    try:
        info = archive.getinfo("profile.json")
        if info.file_size > MAX_MANIFEST_BYTES:
            raise ValueError("Описание профиля превышает допустимый размер.")
        manifest = json.loads(archive.read(info).decode("utf-8-sig"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Некорректное описание профиля.") from exc
    if not isinstance(manifest, dict) or manifest.get("format") != "doomsday-training-profile":
        raise ValueError("Некорректный формат профиля.")
    for key in ("images", "routine_tasks"):
        if not isinstance(manifest.get(key, []), list):
            raise ValueError(f"Некорректное поле профиля: {key}.")
    for key in ("groups", "matching", "source_screen"):
        if not isinstance(manifest.get(key, {}), dict):
            raise ValueError(f"Некорректное поле профиля: {key}.")
    for group in manifest.get("groups", {}):
        if str(group).strip() in {".", ".."}:
            raise ValueError("Профиль содержит недопустимое имя группы.")
    for task in manifest.get("routine_tasks", []):
        if not isinstance(task, dict):
            raise ValueError("Некорректная задача профиля.")
        safe_profile_component(task.get("id"))
    try:
        int(manifest.get("routine_max_marches", 5))
        for key in ("scale_min", "scale_max"):
            value = float(manifest.get("matching", {}).get(key, 1.0))
            if not math.isfinite(value) or value <= 0:
                raise ValueError("Некорректный масштаб профиля.")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Некорректные числовые настройки профиля.") from exc
    total = 0
    for image in manifest.get("images", []):
        if not isinstance(image, dict):
            raise ValueError("Некорректный шаблон профиля.")
        if image.get("uid"):
            safe_profile_component(image["uid"])
        if str(image.get("group") or "").strip() in {".", ".."}:
            raise ValueError("Профиль содержит недопустимое имя группы.")
        entry = str(image.get("path") or "")
        path = PurePosixPath(entry)
        if (
            "\\" in entry or not entry.startswith("templates/")
            or ".." in path.parts or path.is_absolute()
        ):
            raise ValueError("Профиль содержит небезопасный путь шаблона.")
        # The GUI importer appends this extension to a local filename. In
        # particular, ':' would create an NTFS alternate data stream on Windows.
        safe_profile_component("template" + path.suffix)
        try:
            info = archive.getinfo(entry)
        except KeyError as exc:
            raise ValueError("В архиве отсутствует указанный шаблон.") from exc
        total += info.file_size
        if info.is_dir() or info.file_size > MAX_TEMPLATE_BYTES or total > MAX_PROFILE_BYTES:
            raise ValueError("Шаблоны профиля превышают допустимый размер.")
        # Check CRC/decompression before the caller changes any application state.
        archive.read(info)
    return manifest
