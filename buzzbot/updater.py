from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
from urllib import error, request
import zipfile

from buzzbot.remote_control import remote_data_dir


DEFAULT_MANIFEST_URL = (
    "https://github.com/ValeraBuZ/BuZzbot-PC/releases/download/latest/update-manifest.json"
)
DEFAULT_ARCHIVE_URL = (
    "https://github.com/ValeraBuZ/BuZzbot-PC/releases/download/latest/BuZzbotPortable.zip"
)
MAX_MANIFEST_SIZE = 64 * 1024
MAX_ARCHIVE_SIZE = 700 * 1024 * 1024
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$")
SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpdateManifest:
    version: str
    sha256: str


@dataclass(frozen=True)
class StagedUpdate:
    version: str
    source_dir: Path
    archive_path: Path


def _version_key(value):
    core = str(value or "0.0.0").split("-", 1)[0].split("+", 1)[0]
    parts = core.split(".")
    result = []
    for part in parts[:3]:
        try:
            result.append(int(part))
        except ValueError:
            result.append(0)
    return tuple((result + [0, 0, 0])[:3])


def is_newer_version(candidate, current):
    return _version_key(candidate) > _version_key(current)


def _open(opener, http_request, timeout):
    return (opener or request.urlopen)(http_request, timeout=timeout)


def fetch_update_manifest(url=DEFAULT_MANIFEST_URL, *, opener=None):
    http_request = request.Request(
        str(url),
        headers={"User-Agent": "BuZzbot-Updater/1", "Accept": "application/json"},
    )
    try:
        with _open(opener, http_request, 15.0) as response:
            data = response.read(MAX_MANIFEST_SIZE + 1)
    except (error.URLError, error.HTTPError, TimeoutError, OSError) as exc:
        raise UpdateError(f"Не удалось получить описание обновления: {exc}") from exc
    if len(data) > MAX_MANIFEST_SIZE:
        raise UpdateError("Описание обновления слишком большое.")
    try:
        payload = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError("Некорректное описание обновления.") from exc
    if not isinstance(payload, dict):
        raise UpdateError("Некорректное описание обновления: ожидался JSON-объект.")
    version = str(payload.get("version") or "").strip()
    checksum = str(payload.get("sha256") or "").strip().lower()
    if not VERSION_RE.fullmatch(version):
        raise UpdateError("В описании обновления указана некорректная версия.")
    if not SHA256_RE.fullmatch(checksum):
        raise UpdateError("В описании обновления отсутствует корректный SHA-256.")
    return UpdateManifest(version=version, sha256=checksum)


def _download_archive(url, destination, expected_sha256, *, opener=None):
    http_request = request.Request(
        str(url),
        headers={"User-Agent": "BuZzbot-Updater/1", "Accept": "application/zip"},
    )
    digest = hashlib.sha256()
    total = 0
    try:
        with _open(opener, http_request, 60.0) as response, destination.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ARCHIVE_SIZE:
                    raise UpdateError("Архив обновления превышает допустимый размер.")
                digest.update(chunk)
                output.write(chunk)
    except UpdateError:
        destination.unlink(missing_ok=True)
        raise
    except (error.URLError, error.HTTPError, TimeoutError, OSError) as exc:
        destination.unlink(missing_ok=True)
        raise UpdateError(f"Не удалось скачать обновление: {exc}") from exc
    if total == 0:
        destination.unlink(missing_ok=True)
        raise UpdateError("Получен пустой архив обновления.")
    actual = digest.hexdigest()
    if not hmac.compare_digest(actual, expected_sha256):
        destination.unlink(missing_ok=True)
        raise UpdateError("SHA-256 архива не совпадает. Обновление отменено.")


def _safe_extract(archive_path, destination):
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            member_path = PurePosixPath(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise UpdateError("Архив обновления содержит небезопасный путь.")
            unix_mode = (member.external_attr >> 16) & 0o170000
            if unix_mode == 0o120000:
                raise UpdateError("Архив обновления содержит недопустимую ссылку.")
        archive.extractall(destination)


def download_and_stage_update(
    current_version,
    *,
    manifest_url=DEFAULT_MANIFEST_URL,
    archive_url=DEFAULT_ARCHIVE_URL,
    update_root=None,
    opener=None,
):
    manifest = fetch_update_manifest(manifest_url, opener=opener)
    if not is_newer_version(manifest.version, current_version):
        return None
    root = Path(update_root) if update_root else remote_data_dir() / "updates"
    version_root = root / manifest.version
    archive_path = version_root / "BuZzbotPortable.zip"
    extracted_root = version_root / "extracted"
    if version_root.exists():
        shutil.rmtree(version_root, ignore_errors=True)
    version_root.mkdir(parents=True, exist_ok=True)
    _download_archive(
        archive_url,
        archive_path,
        manifest.sha256,
        opener=opener,
    )
    try:
        _safe_extract(archive_path, extracted_root)
    except (OSError, zipfile.BadZipFile) as exc:
        raise UpdateError(f"Не удалось распаковать обновление: {exc}") from exc
    source_dir = extracted_root / "BuZzbotPortable"
    if not (source_dir / "BuZzbot.exe").is_file():
        raise UpdateError("В архиве обновления не найден BuZzbot.exe.")
    return StagedUpdate(
        version=manifest.version,
        source_dir=source_dir,
        archive_path=archive_path,
    )


UPDATE_SCRIPT = r'''param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Target,
    [Parameter(Mandatory=$true)][int]$ProcessId
)
$ErrorActionPreference = "Stop"
Wait-Process -Id $ProcessId -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 700

$internalSource = Join-Path $Source "_internal"
$internalTarget = Join-Path $Target "_internal"
if (Test-Path -LiteralPath $internalSource) {
    New-Item -ItemType Directory -Path $internalTarget -Force | Out-Null
    & robocopy $internalSource $internalTarget /MIR /R:3 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "robocopy _internal failed: $LASTEXITCODE" }
}

foreach ($name in @("BuZzbot.exe")) {
    $sourceFile = Join-Path $Source $name
    if (Test-Path -LiteralPath $sourceFile) {
        Copy-Item -LiteralPath $sourceFile -Destination (Join-Path $Target $name) -Force
    }
}

$imageSource = Join-Path $Source "img"
$imageTarget = Join-Path $Target "img"
if (Test-Path -LiteralPath $imageSource) {
    New-Item -ItemType Directory -Path $imageTarget -Force | Out-Null
    & robocopy $imageSource $imageTarget /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "robocopy img failed: $LASTEXITCODE" }
}

$executable = Join-Path $Target "BuZzbot.exe"
Start-Process -FilePath $executable -WorkingDirectory $Target
Remove-Item -LiteralPath (Split-Path -Parent $Source) -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
'''


def launch_staged_update(staged_update, target_dir, *, process_id=None):
    if not getattr(sys, "frozen", False):
        raise UpdateError("Автоматическая установка доступна только в portable-сборке.")
    source_dir = Path(staged_update.source_dir).resolve()
    target_dir = Path(target_dir).resolve()
    if not (source_dir / "BuZzbot.exe").is_file():
        raise UpdateError("Подготовленное обновление повреждено.")
    script_path = remote_data_dir() / "install_buzzbot_update.ps1"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(UPDATE_SCRIPT, encoding="utf-8-sig")
    command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-WindowStyle",
        "Hidden",
        "-File",
        str(script_path),
        "-Source",
        str(source_dir),
        "-Target",
        str(target_dir),
        "-ProcessId",
        str(int(process_id or os.getpid())),
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        subprocess.Popen(
            command,
            cwd=target_dir,
            creationflags=creationflags,
            close_fds=True,
        )
    except OSError as exc:
        raise UpdateError(f"Не удалось запустить установщик обновления: {exc}") from exc
    return script_path
