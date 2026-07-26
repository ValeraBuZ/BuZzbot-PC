from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path


SENSITIVE_KEY = re.compile(
    r"password|passwd|token|secret|credential|authorization|cookie|email|login|username",
    re.I,
)
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")


def redact_text(value):
    text = str(value or "")
    home = str(Path.home())
    if home:
        text = text.replace(home, "%USERPROFILE%").replace(home.lower(), "%USERPROFILE%")
    return EMAIL.sub("<email>", text)


def redact_config(value, key=""):
    if SENSITIVE_KEY.search(str(key)):
        return "<redacted>"
    if isinstance(value, dict):
        return {str(item_key): redact_config(item_value, item_key) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact_config(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def _run_capture(command, timeout=10):
    kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
        "check": False,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run([str(part) for part in command], **kwargs)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"Не удалось выполнить команду: {exc}"
    return redact_text(result.stdout or "")


def create_diagnostic_report(
    app_dir,
    *,
    app_version,
    config_path,
    runtime_state,
    adb_path=None,
    adb_devices_text=None,
    ldconsole_path=None,
    output_dir=None,
    log_paths=None,
    screenshot_png=None,
):
    app_dir = Path(app_dir).resolve()
    config_path = Path(config_path)
    output_dir = Path(output_dir) if output_dir else app_dir / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"BuZzbot_report_{stamp}.zip"

    config = {}
    if config_path.is_file():
        with config_path.open("r", encoding="utf-8-sig") as handle:
            config = json.load(handle)
    images = config.get("images", []) if isinstance(config, dict) else []
    tasks = config.get("routine_tasks", []) if isinstance(config, dict) else []
    missing = []
    for item in images:
        stored_path = item.get("path", "")
        if not stored_path:
            continue
        resolved_path = Path(stored_path)
        if not resolved_path.is_absolute():
            resolved_path = app_dir / resolved_path
        if not resolved_path.is_file():
            missing.append(stored_path)

    if adb_devices_text is not None:
        adb_devices = str(adb_devices_text)
    else:
        adb_devices = _run_capture([adb_path, "devices", "-l"]) if adb_path else "ADB не найден"
    ldplayer_list = _run_capture([ldconsole_path, "list2"]) if ldconsole_path else "ldconsole.exe не найден"
    state = redact_config(runtime_state or {})
    lines = [
        "BuZzbot - ДИАГНОСТИЧЕСКИЙ ОТЧЁТ",
        f"Создан: {datetime.now().isoformat(timespec='seconds')}",
        f"Версия: {app_version}",
        f"Windows: {platform.platform()}",
        f"Python: {platform.python_version()} (frozen={bool(getattr(sys, 'frozen', False))})",
        f"Папка программы: {redact_text(app_dir)}",
        f"Шаблонов: {len(images)}",
        f"Задач: {len(tasks)}",
        f"Отсутствующих файлов шаблонов: {len(missing)}",
        "",
        "СОСТОЯНИЕ ПРОГРАММЫ",
        json.dumps(state, ensure_ascii=False, indent=2),
        "",
        "ADB DEVICES",
        adb_devices.strip(),
        "",
        "LDPLAYER LIST",
        ldplayer_list.strip(),
    ]
    checklist = (
        "УСТАНОВКА НА ДРУГОЙ МАШИНЕ\n\n"
        "1. Распакуйте всю папку portable, не отделяя _internal от EXE.\n"
        "2. Запустите LDPlayer 9. Бот сам проверит живое разрешение и подстроит шаблоны; 1280x720, 240 DPI остаётся рекомендуемым режимом.\n"
        "3. Запустите нужный экземпляр и игру.\n"
        "4. В программе нажмите «Восстановить ADB»; экземпляр может перезапуститься.\n"
        "5. Нажмите «Проверить» и убедитесь, что показано «подключено».\n"
        "6. Для переноса обучения используйте ZIP-профиль с шаблонами.\n"
    )

    log_candidates = list(app_dir.glob("bot.log*"))
    log_candidates.extend(Path(path) for path in (log_paths or ()) if path)
    log_chunks = []
    seen_logs = set()
    for log_path in sorted(log_candidates, key=lambda path: str(path).lower()):
        try:
            resolved_log = log_path.resolve()
        except OSError:
            resolved_log = log_path
        if resolved_log in seen_logs:
            continue
        seen_logs.add(resolved_log)
        if not log_path.is_file():
            continue
        try:
            content = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        sanitized = redact_text(content)
        log_chunks.append((log_path.name + ".txt", sanitized))
    error_lines = []
    for _name, content in log_chunks:
        error_lines.extend(
            line for line in content.splitlines()
            if " - ERROR - " in line or " - CRITICAL - " in line or "Traceback" in line
        )

    with zipfile.ZipFile(report_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("report.txt", "\n".join(lines))
        archive.writestr("installation_checklist.txt", checklist)
        archive.writestr(
            "config_sanitized.json",
            json.dumps(redact_config(config), ensure_ascii=False, indent=2),
        )
        archive.writestr(
            "missing_templates.txt",
            "\n".join(redact_text(path) for path in missing) or "Отсутствующих шаблонов нет.",
        )
        archive.writestr("errors_only.txt", "\n".join(error_lines[-1000:]) or "Ошибок в логах не найдено.")
        if screenshot_png:
            archive.writestr("current_screen.png", screenshot_png)
        for name, content in log_chunks:
            archive.writestr(f"logs/{name}", content)
    return report_path
