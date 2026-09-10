from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import platform
import re
import shutil
import string
import uuid

from buzzbot.storage import atomic_write_json


REPORTS_FOLDER = "BuZzbot Reports"
INBOX_FOLDER = "Входящие"


def report_settings_path():
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "BuZzbot" / "report-cloud.json"


def _safe_device_name(value):
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(value or "").strip())
    return cleaned.strip(" .")[:80] or "Компьютер"


def detect_sync_folders():
    candidates = []
    for variable in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        value = os.environ.get(variable)
        if value:
            candidates.append(Path(value))
    home = Path.home()
    candidates.extend(
        (
            home / "YandexDisk",
            home / "Yandex.Disk",
            home / "OneDrive",
            home / "Google Drive",
        )
    )
    if os.name == "nt":
        # Google Drive for desktop exposes "My Drive" as a folder on a
        # mounted drive (for example G:\My Drive), not below the user profile.
        mounted_folder_names = ("My Drive", "Мой диск", "Google Drive")
        for letter in string.ascii_uppercase:
            drive_root = Path(f"{letter}:\\")
            try:
                available = drive_root.is_dir()
            except OSError:
                available = False
            if not available:
                continue
            candidates.extend(drive_root / name for name in mounted_folder_names)
    unique = []
    seen = set()
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
            available = resolved.is_dir()
        except OSError:
            continue
        key = os.path.normcase(str(resolved))
        if key in seen or not available:
            continue
        seen.add(key)
        unique.append(resolved)
    return unique


def sync_folder_provider(path, detected_roots=None):
    """Return the cloud client backing *path*, when it can be identified."""
    try:
        resolved = Path(path).expanduser().resolve()
    except (OSError, TypeError, ValueError):
        return None
    roots = detect_sync_folders() if detected_roots is None else detected_roots
    for root in roots:
        try:
            known_root = Path(root).expanduser().resolve()
            resolved.relative_to(known_root)
        except (OSError, TypeError, ValueError):
            continue
        normalized = str(known_root).casefold()
        if "yandex" in normalized:
            return "Yandex Disk"
        if "onedrive" in normalized:
            return "OneDrive"
        if "google" in normalized or known_root.name.casefold() in {"my drive", "мой диск"}:
            return "Google Drive"
        return "облачный клиент"
    return None


@dataclass(frozen=True)
class ReportCloudSettings:
    enabled: bool = False
    sync_folder: str = ""
    device_name: str = ""

    @property
    def configured(self):
        return bool(self.enabled and str(self.sync_folder).strip())


def default_report_cloud_settings():
    detected = detect_sync_folders()
    return ReportCloudSettings(
        enabled=False,
        sync_folder=str(detected[0]) if detected else "",
        device_name=_safe_device_name(platform.node()),
    )


def load_report_cloud_settings(path=None):
    settings_path = Path(path) if path else report_settings_path()
    defaults = default_report_cloud_settings()
    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return defaults
    if not isinstance(payload, dict):
        return defaults
    return ReportCloudSettings(
        enabled=bool(payload.get("enabled", defaults.enabled)),
        sync_folder=str(payload.get("sync_folder") or defaults.sync_folder).strip(),
        device_name=_safe_device_name(payload.get("device_name") or defaults.device_name),
    )


def save_report_cloud_settings(settings, path=None):
    settings_path = Path(path) if path else report_settings_path()
    normalized = ReportCloudSettings(
        enabled=bool(settings.enabled),
        sync_folder=str(settings.sync_folder or "").strip(),
        device_name=_safe_device_name(settings.device_name),
    )
    atomic_write_json(settings_path, asdict(normalized))
    return normalized


def report_inbox(settings):
    if not settings.configured:
        raise ValueError("Облачная папка отчётов не настроена.")
    root = Path(settings.sync_folder).expanduser()
    if not root.is_dir():
        raise FileNotFoundError(f"Облачная папка недоступна: {root}")
    return root / REPORTS_FOLDER / INBOX_FOLDER / _safe_device_name(settings.device_name)


def upload_report_to_sync_folder(report_path, settings):
    source = Path(report_path)
    if not source.is_file():
        raise FileNotFoundError(f"Отчёт не найден: {source}")
    inbox = report_inbox(settings)
    inbox.mkdir(parents=True, exist_ok=True)
    destination = inbox / source.name
    if destination.exists():
        destination = inbox / f"{source.stem}_{uuid.uuid4().hex[:8]}{source.suffix}"
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.uploading")
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    source.unlink()
    return destination


def delete_report_after_review(report_path, settings):
    target = Path(report_path).resolve()
    inbox_root = (Path(settings.sync_folder).expanduser() / REPORTS_FOLDER / INBOX_FOLDER).resolve()
    if not target.is_relative_to(inbox_root):
        raise ValueError("Удалять можно только отчёты из облачной папки BuZzbot.")
    target.unlink(missing_ok=True)
    return not target.exists()
