from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path


CRYPTPROTECT_UI_FORBIDDEN = 0x1
# Keep the original entropy so credentials saved by older BuZzbot versions
# remain readable after adding IGG Account support.
_ENTROPY = b"BuZzbot Google credentials v1"


class CredentialError(RuntimeError):
    """Raised when an encrypted credential cannot be stored or read."""


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _make_blob(payload):
    data = bytes(payload or b"")
    buffer = ctypes.create_string_buffer(data, max(1, len(data)))
    blob = _DataBlob(
        len(data),
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)),
    )
    return blob, buffer


def protect_with_dpapi(payload):
    if os.name != "nt" or not hasattr(ctypes, "windll"):
        raise CredentialError("Защищённое хранилище доступно только в Windows.")
    source, source_buffer = _make_blob(payload)
    entropy, entropy_buffer = _make_blob(_ENTROPY)
    protected = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    success = crypt32.CryptProtectData(
        ctypes.byref(source),
        "BuZzbot",
        ctypes.byref(entropy),
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(protected),
    )
    # Keep input buffers alive until CryptProtectData returns.
    _ = source_buffer, entropy_buffer
    if not success:
        raise CredentialError(f"Windows не смогла зашифровать пароль: {ctypes.get_last_error()}")
    try:
        return ctypes.string_at(protected.pbData, protected.cbData)
    finally:
        kernel32.LocalFree(protected.pbData)


def unprotect_with_dpapi(payload):
    if os.name != "nt" or not hasattr(ctypes, "windll"):
        raise CredentialError("Защищённое хранилище доступно только в Windows.")
    source, source_buffer = _make_blob(payload)
    entropy, entropy_buffer = _make_blob(_ENTROPY)
    plain = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    success = crypt32.CryptUnprotectData(
        ctypes.byref(source),
        None,
        ctypes.byref(entropy),
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(plain),
    )
    _ = source_buffer, entropy_buffer
    if not success:
        raise CredentialError(f"Windows не смогла расшифровать пароль: {ctypes.get_last_error()}")
    try:
        return ctypes.string_at(plain.pbData, plain.cbData)
    finally:
        kernel32.LocalFree(plain.pbData)


def default_credential_path():
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return base / "BuZzbot" / "credentials.json"


class CredentialStore:
    def __init__(self, path=None, protector=None, unprotector=None):
        self.path = Path(path) if path else default_credential_path()
        self._protect = protector or protect_with_dpapi
        self._unprotect = unprotector or unprotect_with_dpapi

    def _load(self):
        if not self.path.is_file():
            return {"version": 1, "credentials": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CredentialError(f"Не удалось прочитать хранилище паролей: {exc}") from exc
        credentials = payload.get("credentials", {}) if isinstance(payload, dict) else {}
        if not isinstance(credentials, dict):
            credentials = {}
        return {"version": 1, "credentials": credentials}

    def _save(self, payload):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
            temp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temp_path, self.path)
        except OSError as exc:
            raise CredentialError(f"Не удалось сохранить зашифрованный пароль: {exc}") from exc

    def has_password(self, account_id):
        account_key = str(account_id or "").strip()
        if not account_key:
            return False
        return bool(self._load()["credentials"].get(account_key))

    def list_keys(self):
        """Return credential identifiers without decrypting secret values."""
        return tuple(sorted(self._load()["credentials"]))

    def set_password(self, account_id, password):
        account_key = str(account_id or "").strip()
        value = str(password or "")
        if not account_key:
            raise CredentialError("Не указан профиль аккаунта.")
        if not value:
            raise CredentialError("Пароль не может быть пустым.")
        protected = self._protect(value.encode("utf-8"))
        payload = self._load()
        payload["credentials"][account_key] = base64.b64encode(protected).decode("ascii")
        self._save(payload)

    def get_password(self, account_id):
        account_key = str(account_id or "").strip()
        encoded = self._load()["credentials"].get(account_key)
        if not encoded:
            return None
        try:
            protected = base64.b64decode(encoded, validate=True)
            return self._unprotect(protected).decode("utf-8")
        except (ValueError, UnicodeDecodeError, OSError) as exc:
            raise CredentialError(f"Не удалось расшифровать пароль профиля: {exc}") from exc

    def delete_password(self, account_id):
        account_key = str(account_id or "").strip()
        payload = self._load()
        removed = payload["credentials"].pop(account_key, None) is not None
        if removed:
            self._save(payload)
        return removed
