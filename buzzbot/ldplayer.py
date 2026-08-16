from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LDPlayerInstance:
    index: int
    name: str
    running: bool
    pid: int
    box_pid: int
    width: int
    height: int
    dpi: int

    @property
    def adb_serial(self):
        return serial_for_index(self.index)


def serial_for_index(index):
    return f"emulator-{5554 + max(0, int(index)) * 2}"


def tcp_serial_for_index(index):
    return f"127.0.0.1:{5555 + max(0, int(index)) * 2}"


def bridged_adb_serial_for_index(index, log_root=None):
    """Return the current guest ADB address when LDPlayer uses bridged networking."""
    root = Path(log_root) if log_root else Path(os.environ.get("APPDATA", "")) / "XuanZhi9" / "log"
    log_path = root / f"leidian{int(index)}_vbox.log"
    if not log_path.is_file():
        return None
    try:
        contents = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    matches = re.findall(
        r"initADB\s+\(\d+\):emulator adbmode:\s*\d+,\s*((?:\d{1,3}\.){3}\d{1,3})",
        contents,
    )
    if not matches:
        return None
    address = matches[-1]
    try:
        octets = [int(part) for part in address.split(".")]
    except ValueError:
        return None
    if len(octets) != 4 or any(part < 0 or part > 255 for part in octets) or address == "0.0.0.0":
        return None
    return f"{address}:5555"


def index_from_serial(serial):
    value = str(serial or "").strip().lower()
    if value.startswith("127.0.0.1:"):
        try:
            port = int(value.rsplit(":", 1)[1])
        except ValueError:
            return None
        offset = port - 5555
        return offset // 2 if offset >= 0 and offset % 2 == 0 else None
    if not value.startswith("emulator-"):
        return None
    try:
        port = int(value.split("-", 1)[1])
    except ValueError:
        return None
    offset = port - 5554
    return offset // 2 if offset >= 0 and offset % 2 == 0 else None


def find_ldconsole(adb_path=None):
    candidates = []
    if adb_path:
        candidates.append(Path(adb_path).expanduser().resolve().parent / "ldconsole.exe")
    candidates.extend(
        [
            Path(r"C:\LDPlayer\LDPlayer9\ldconsole.exe"),
            Path(r"C:\LDPlayer\LDPlayer4.0\ldconsole.exe"),
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _decode_output(payload):
    if isinstance(payload, str):
        return payload
    for encoding in ("utf-8", "cp866", "cp1251"):
        try:
            return (payload or b"").decode(encoding)
        except UnicodeDecodeError:
            continue
    return (payload or b"").decode("utf-8", errors="replace")


def _run_ldconsole(ldconsole_path, args, timeout=15):
    command = [str(ldconsole_path), *[str(arg) for arg in args]]
    kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "timeout": timeout,
        "check": False,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(command, **kwargs)
    if result.returncode != 0:
        message = _decode_output(result.stderr).strip() or "Команда LDPlayer завершилась с ошибкой."
        raise RuntimeError(message)
    return _decode_output(result.stdout)


def parse_list2(output):
    instances = []
    for row in csv.reader(str(output or "").splitlines()):
        if len(row) < 10:
            continue
        try:
            instances.append(
                LDPlayerInstance(
                    index=int(row[0]),
                    name=row[1].strip() or f"LDPlayer {row[0]}",
                    running=bool(int(row[4])),
                    pid=int(row[5]),
                    box_pid=int(row[6]),
                    width=int(row[7]),
                    height=int(row[8]),
                    dpi=int(row[9]),
                )
            )
        except (TypeError, ValueError):
            continue
    return instances


def list_instances(ldconsole_path):
    if not ldconsole_path:
        return []
    return parse_list2(_run_ldconsole(ldconsole_path, ["list2"]))


def instance_config_path(ldconsole_path, index):
    return Path(ldconsole_path).resolve().parent / "vms" / "config" / f"leidian{int(index)}.config"


def adb_debug_enabled(ldconsole_path, index):
    path = instance_config_path(ldconsole_path, index)
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return bool(data.get("basicSettings.adbDebug", 0))


def enable_adb_debug(ldconsole_path, index):
    path = instance_config_path(ldconsole_path, index)
    if not path.is_file():
        raise FileNotFoundError(f"Не найден конфиг LDPlayer: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if int(data.get("basicSettings.adbDebug", 0)) == 1:
        return False

    backup = path.with_suffix(path.suffix + ".buzzbot.bak")
    if not backup.exists():
        shutil.copy2(path, backup)
    data["basicSettings.adbDebug"] = 1
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=4)
        handle.write("\n")
    os.replace(temp_path, path)
    return True


def reboot_instance(ldconsole_path, index):
    _run_ldconsole(ldconsole_path, ["reboot", "--index", int(index)], timeout=20)


def launch_instance(ldconsole_path, index):
    _run_ldconsole(ldconsole_path, ["launch", "--index", int(index)], timeout=20)
