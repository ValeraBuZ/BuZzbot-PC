from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import logging
import math
import os
from pathlib import Path
import socket
import threading
import time
from urllib import error, request
import uuid

from buzzbot.storage import atomic_write_json


LOGGER = logging.getLogger("BuZzbot.Remote")
REMOTE_CREDENTIAL_KEY = "remote-control-token"


def remote_data_dir():
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return base / "BuZzbot"


def default_remote_settings_path():
    return remote_data_dir() / "remote_settings.json"


def default_remote_state_path():
    return remote_data_dir() / "remote_device_state.json"


def _atomic_write_json(path, payload):
    atomic_write_json(path, payload)


def _read_json(path, default):
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return dict(default)
    return payload if isinstance(payload, dict) else dict(default)


@dataclass
class RemoteSettings:
    enabled: bool = False
    hub_url: str = ""
    device_id: str = ""
    device_name: str = ""
    heartbeat_seconds: float = 10.0

    def normalized(self):
        device_id = str(self.device_id or "").strip() or str(uuid.uuid4())
        device_name = str(self.device_name or "").strip() or socket.gethostname() or "BuZzbot PC"
        hub_url = str(self.hub_url or "").strip().rstrip("/")
        try:
            heartbeat = float(self.heartbeat_seconds or 10.0)
        except (TypeError, ValueError):
            heartbeat = 10.0
        if not math.isfinite(heartbeat):
            heartbeat = 10.0
        heartbeat = min(60.0, max(5.0, heartbeat))
        return RemoteSettings(
            enabled=bool(self.enabled),
            hub_url=hub_url,
            device_id=device_id,
            device_name=device_name[:80],
            heartbeat_seconds=heartbeat,
        )


def load_remote_settings(path=None):
    path = Path(path) if path else default_remote_settings_path()
    payload = _read_json(path, {})
    settings = RemoteSettings(
        enabled=bool(payload.get("enabled", False)),
        hub_url=str(payload.get("hub_url") or ""),
        device_id=str(payload.get("device_id") or ""),
        device_name=str(payload.get("device_name") or ""),
        heartbeat_seconds=payload.get("heartbeat_seconds", 10.0),
    ).normalized()
    if payload != asdict(settings):
        save_remote_settings(settings, path)
    return settings


def save_remote_settings(settings, path=None):
    path = Path(path) if path else default_remote_settings_path()
    normalized = settings.normalized()
    _atomic_write_json(path, asdict(normalized))
    return normalized


class RemoteControlError(RuntimeError):
    pass


class RemoteControlClient:
    def __init__(
        self,
        settings,
        token,
        status_provider,
        command_handler,
        access_handler,
        *,
        state_path=None,
        urlopen=None,
        logger=None,
    ):
        self.settings = settings.normalized()
        self.token = str(token or "").strip()
        self.status_provider = status_provider
        self.command_handler = command_handler
        self.access_handler = access_handler
        self.state_path = Path(state_path) if state_path else default_remote_state_path()
        self._urlopen = urlopen or request.urlopen
        self.logger = logger or LOGGER
        state = _read_json(
            self.state_path,
            {"access_allowed": True, "last_command_id": 0},
        )
        self.access_allowed = bool(state.get("access_allowed", True))
        try:
            self.last_command_id = max(0, int(state.get("last_command_id", 0) or 0))
        except (TypeError, ValueError, OverflowError):
            self.last_command_id = 0
        self.connected = False
        self.last_error = ""
        self.last_checkin_at = 0.0
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread = None
        self._lock = threading.RLock()
        self._checkin_lock = threading.Lock()
        self._generation = 0
        self._state_dirty = False

    @property
    def configured(self):
        return bool(
            self.settings.enabled
            and self.settings.hub_url
            and self.token
        )

    def _save_state(self):
        # Keep an unsuccessful write pending, especially before acknowledging
        # a command to the Hub on the next request.
        self._state_dirty = True
        _atomic_write_json(
            self.state_path,
            {
                "access_allowed": bool(self.access_allowed),
                "last_command_id": int(self.last_command_id),
            },
        )
        self._state_dirty = False

    def start(self):
        with self._lock:
            return self._start_locked()

    def _start_locked(self):
        if not self.configured:
            return False
        if self._thread is not None and self._thread.is_alive():
            if self._stop_event.is_set():
                return False
            self._wake_event.set()
            return True
        self._stop_event.clear()
        self._wake_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="BuZzbotRemoteControl",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self, timeout=3.0):
        with self._lock:
            self._generation += 1
            self._stop_event.set()
            self._wake_event.set()
            thread = self._thread
            self.connected = False
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(0.0, float(timeout)))
        with self._lock:
            if thread is self._thread and thread is not None and not thread.is_alive():
                self._thread = None

    def wake(self):
        self._wake_event.set()

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self.checkin_once()
            except Exception as exc:
                with self._lock:
                    self.connected = False
                    self.last_error = str(exc)
                self.logger.warning("Remote check-in failed: %s", exc)
            self._wake_event.wait(self.settings.heartbeat_seconds)
            self._wake_event.clear()

    def _build_payload(self):
        status = self.status_provider() or {}
        if not isinstance(status, dict):
            status = {"status": str(status)}
        return {
            "device_id": self.settings.device_id,
            "device_name": self.settings.device_name,
            "ack_command_id": self.last_command_id,
            "status": status,
        }

    def checkin_once(self, timeout=7.0):
        # Manual connection checks and the heartbeat must not execute one
        # command twice or acknowledge an older reply after a newer one.
        with self._checkin_lock:
            if self._stop_event.is_set():
                return None
            return self._checkin_once(timeout)

    def _checkin_once(self, timeout):
        with self._lock:
            if self._stop_event.is_set():
                return None
            generation = self._generation
            if self._state_dirty:
                self._save_state()
        if not self.configured:
            raise RemoteControlError("Удалённое управление не настроено.")
        endpoint = f"{self.settings.hub_url}/api/v1/checkin"
        payload = json.dumps(self._build_payload(), ensure_ascii=False).encode("utf-8")
        http_request = request.Request(
            endpoint,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "BuZzbot-Remote/1",
            },
        )
        try:
            with self._urlopen(http_request, timeout=timeout) as response:
                response_data = response.read(128 * 1024)
        except error.HTTPError as exc:
            status_code = exc.code
            exc.close()
            if status_code in {401, 403}:
                raise RemoteControlError("Hub отклонил секрет доступа.") from exc
            raise RemoteControlError(f"Hub вернул HTTP {status_code}.") from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise RemoteControlError(f"Hub недоступен: {reason}") from exc
        try:
            result = json.loads(response_data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RemoteControlError("Hub вернул некорректный ответ.") from exc
        if not isinstance(result, dict):
            raise RemoteControlError("Hub вернул некорректный ответ.")
        if not result.get("ok"):
            raise RemoteControlError(str(result.get("error") or "Hub отклонил запрос."))

        # stop() can return before a slow HTTP request finishes. Such a reply
        # belongs to the stopped client and must not enqueue new actions.
        with self._lock:
            if self._stop_event.is_set() or generation != self._generation:
                return None
            return self._apply_checkin_result(result)

    def _apply_checkin_result(self, result):
        access_allowed = result.get("access_allowed", True)
        if not isinstance(access_allowed, bool):
            raise RemoteControlError("Hub вернул некорректный признак доступа.")
        if access_allowed != self.access_allowed:
            previous_access = self.access_allowed
            self.access_allowed = access_allowed
            try:
                # A full or unavailable disk must not suppress a denial.
                self.access_handler(access_allowed)
            except Exception:
                self.access_allowed = previous_access
                raise
            self._save_state()

        if self._stop_event.is_set():
            return None

        command = result.get("command")
        if isinstance(command, dict):
            try:
                command_id = max(0, int(command.get("id", 0) or 0))
            except (TypeError, ValueError, OverflowError) as exc:
                raise RemoteControlError("Hub вернул некорректный номер команды.") from exc
            action = str(command.get("action") or "").strip().lower()
            if command_id > self.last_command_id and action:
                handled = self.command_handler(action)
                if handled is not False:
                    self.last_command_id = command_id
                    self._save_state()

        with self._lock:
            self.connected = not self._stop_event.is_set()
            self.last_error = ""
            self.last_checkin_at = time.time()
        return result

    def snapshot(self):
        with self._lock:
            return {
                "configured": self.configured,
                "connected": bool(self.connected),
                "last_error": self.last_error,
                "last_checkin_at": float(self.last_checkin_at),
                "access_allowed": bool(self.access_allowed),
                "device_id": self.settings.device_id,
                "device_name": self.settings.device_name,
                "hub_url": self.settings.hub_url,
            }
