from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np


class AdbError(RuntimeError):
    """Raised when an ADB command cannot be completed."""


def find_adb_executable(preferred=None):
    candidates = [preferred, os.environ.get("ADB_PATH")]
    local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates.extend([
        Path(r"C:\LDPlayer\LDPlayer9\adb.exe"),
        Path(r"C:\LDPlayer\LDPlayer4.0\adb.exe"),
        local_app_data / "Android" / "Sdk" / "platform-tools" / "adb.exe",
        shutil.which("adb"),
    ])
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file():
            return path.resolve()
    return None


class AdbClient:
    def __init__(self, adb_path=None, serial="emulator-5556", runner=None):
        self.adb_path = find_adb_executable(adb_path)
        self.serial = str(serial or "").strip()
        self._runner = runner or subprocess.run

    def _run(self, args, *, binary=False, timeout=10):
        if self.adb_path is None:
            raise AdbError("ADB не найден. Укажите путь к adb.exe.")

        command = [str(self.adb_path)]
        if self.serial:
            command.extend(["-s", self.serial])
        command.extend(str(arg) for arg in args)

        kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "timeout": timeout,
            "check": False,
        }
        if not binary:
            kwargs.update({"text": True, "encoding": "utf-8", "errors": "replace"})
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            result = self._runner(command, **kwargs)
        except (OSError, subprocess.SubprocessError) as exc:
            raise AdbError(f"Не удалось запустить ADB: {exc}") from exc

        if result.returncode != 0:
            stderr = result.stderr
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            raise AdbError((stderr or "Команда ADB завершилась с ошибкой.").strip())
        return result.stdout

    def is_available(self):
        if self.adb_path is None or not self.serial:
            return False
        try:
            output = self._run(["get-state"], timeout=4)
        except AdbError:
            return False
        return str(output).strip() == "device"

    def is_responsive(self):
        """Return True only when the device accepts real shell commands."""
        if not self.is_available():
            return False
        marker = "buzzbot_ready"
        try:
            output = self._run(["shell", "echo", marker], timeout=4)
        except AdbError:
            return False
        return marker in str(output or "")

    def screenshot_bgr(self):
        payload = self._run(["exec-out", "screencap", "-p"], binary=True, timeout=12)
        if not payload:
            raise AdbError("ADB вернул пустой снимок экрана.")
        encoded = np.frombuffer(payload, dtype=np.uint8)
        frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if frame is None:
            raise AdbError("Не удалось декодировать снимок экрана ADB.")
        return frame

    def tap(self, x, y):
        self._run(["shell", "input", "tap", int(x), int(y)], timeout=5)

    def double_tap(self, x, y, interval=0.12):
        self.tap(x, y)
        import time
        time.sleep(max(0.02, float(interval)))
        self.tap(x, y)

    def long_press(self, x, y, duration_ms=700):
        self._run([
            "shell", "input", "swipe",
            int(x), int(y), int(x), int(y), int(duration_ms),
        ], timeout=5)

    def swipe(self, x1, y1, x2, y2, duration_ms=500):
        self._run([
            "shell", "input", "swipe",
            int(x1), int(y1), int(x2), int(y2), int(duration_ms),
        ], timeout=5)

    def input_text(self, value):
        escaped = str(value).replace("%", "\\%").replace(" ", "%s")
        self._run(["shell", "input", "text", escaped], timeout=5)

    def input_private_text(self, value):
        """Enter sensitive text without placing it in the host process command line."""
        secret = str(value or "")
        if not secret:
            raise AdbError("Нельзя ввести пустое значение.")
        if any(char in secret for char in ("\x00", "\r", "\n")):
            raise AdbError("Секрет содержит неподдерживаемый перевод строки.")
        if not secret.isascii():
            raise AdbError("Безопасный ввод поддерживает только латинские символы и цифры.")
        if self.adb_path is None or not self.serial:
            raise AdbError("ADB не подключён к выбранному LDPlayer.")

        encoded = base64.b64encode(secret.encode("utf-8")).decode("ascii")
        script = (
            f"value=$(printf %s {encoded} | base64 -d); "
            'input text "$value"; unset value; exit\n'
        ).encode("ascii")
        command = [str(self.adb_path), "-s", self.serial, "shell"]
        kwargs = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            process = subprocess.Popen(command, **kwargs)
            _stdout, stderr = process.communicate(script, timeout=10)
        except (OSError, subprocess.SubprocessError) as exc:
            raise AdbError(f"Не удалось выполнить безопасный ввод ADB: {exc}") from exc
        if process.returncode != 0:
            message = (stderr or b"").decode("utf-8", errors="replace").strip()
            raise AdbError(message or "Безопасный ввод ADB завершился с ошибкой.")

    def keyevent(self, key_code):
        self._run(["shell", "input", "keyevent", int(key_code)], timeout=5)

    def clear_focused_text(self, max_characters=128):
        count = min(512, max(1, int(max_characters)))
        self._run(
            ["shell", "input", "keyevent", "KEYCODE_MOVE_END", *("KEYCODE_DEL",) * count],
            timeout=10,
        )

    def focused_edit_text_value(self):
        """Read the focused Android EditText value for input verification."""
        try:
            root = ET.fromstring(self.ui_xml())
        except (AdbError, ET.ParseError, TypeError, ValueError):
            return None
        for node in root.iter("node"):
            if (
                node.attrib.get("class") == "android.widget.EditText"
                and node.attrib.get("focused") == "true"
            ):
                return str(node.attrib.get("text", ""))
        return None

    def current_foreground_package(self):
        """Return the package owning the focused Android window, if available."""
        outputs = []
        for command in (
            ["shell", "dumpsys", "window", "windows"],
            ["shell", "dumpsys", "activity", "activities"],
        ):
            try:
                outputs.append(str(self._run(command, timeout=8) or ""))
            except AdbError:
                continue

        patterns = (
            r"mCurrentFocus=.*?\s([A-Za-z0-9_.]+)/",
            r"mFocusedApp=.*?\s([A-Za-z0-9_.]+)/",
            r"topResumedActivity=.*?\s([A-Za-z0-9_.]+)/",
            r"mResumedActivity=.*?\s([A-Za-z0-9_.]+)/",
        )
        for output in outputs:
            for pattern in patterns:
                match = re.search(pattern, output)
                if match:
                    return match.group(1)
        return None

    def force_stop_package(self, package_name):
        package = str(package_name or "").strip()
        if not package:
            raise AdbError("Не указано имя пакета Android.")
        self._run(["shell", "am", "force-stop", package], timeout=10)

    def launch_package(self, package_name):
        package = str(package_name or "").strip()
        if not package:
            raise AdbError("Не указано имя пакета Android.")
        output = self._run(
            [
                "shell",
                "monkey",
                "-p",
                package,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ],
            timeout=15,
        )
        if "No activities found" in str(output or ""):
            raise AdbError(f"Приложение {package} не найдено на устройстве.")
        return output

    def list_devices(self):
        original_serial = self.serial
        self.serial = ""
        try:
            output = self._run(["devices", "-l"], timeout=6)
        finally:
            self.serial = original_serial
        devices = []
        for line in str(output or "").splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
        return devices

    def connect(self, address):
        target = str(address or "").strip()
        if not target:
            raise AdbError("Не указан адрес ADB-устройства.")
        original_serial = self.serial
        self.serial = ""
        try:
            output = self._run(["connect", target], timeout=10)
        finally:
            self.serial = original_serial
        message = str(output or "").strip()
        if "failed" in message.lower() or "unable" in message.lower():
            raise AdbError(message)
        return message

    def restart_server(self):
        original_serial = self.serial
        self.serial = ""
        try:
            try:
                self._run(["kill-server"], timeout=10)
            except AdbError:
                pass
            try:
                self._run(["start-server"], timeout=10)
            except AdbError:
                if not self._terminate_stale_adb_processes():
                    raise
                self._run(["start-server"], timeout=10)
        finally:
            self.serial = original_serial

    def _terminate_stale_adb_processes(self):
        if os.name != "nt" or self.adb_path is None:
            return False
        try:
            import psutil
        except ImportError:
            return False

        target = os.path.normcase(os.path.realpath(str(self.adb_path)))
        stale = []
        for process in psutil.process_iter(("pid", "exe")):
            try:
                executable = process.info.get("exe")
                if executable and os.path.normcase(os.path.realpath(executable)) == target:
                    process.terminate()
                    stale.append(process)
            except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
                continue
        if not stale:
            return False
        _gone, alive = psutil.wait_procs(stale, timeout=2.0)
        for process in alive:
            try:
                process.kill()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
        return True

    def ui_xml(self):
        """Return the current Android accessibility tree without leaving files behind."""
        remote_path = "/sdcard/buzzbot_ui.xml"
        self._run(["shell", "uiautomator", "dump", remote_path], timeout=12)
        try:
            return self._run(["shell", "cat", remote_path], timeout=5)
        finally:
            try:
                self._run(["shell", "rm", "-f", remote_path], timeout=5)
            except AdbError:
                pass
