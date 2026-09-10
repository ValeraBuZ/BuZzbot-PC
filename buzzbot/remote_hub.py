from __future__ import annotations

from copy import deepcopy
import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import re
import threading
import time
from urllib.parse import unquote, urlparse

from buzzbot.remote_control import remote_data_dir
from buzzbot.storage import atomic_write_json


LOGGER = logging.getLogger("BuZzbot.Hub")
ALLOWED_COMMANDS = frozenset({"start", "pause", "resume", "stop", "update"})
DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
MAX_BODY_SIZE = 128 * 1024


def default_hub_state_path():
    return remote_data_dir() / "remote_hub_state.json"


def _atomic_write_json(path, payload):
    atomic_write_json(path, payload)


def _clean_text(value, limit=500):
    return " ".join(str(value or "").split())[:limit]


class RemoteHubStore:
    def __init__(self, path=None, *, online_timeout=35.0, time_fn=None):
        self.path = Path(path) if path else default_hub_state_path()
        self.online_timeout = max(15.0, float(online_timeout))
        self.time_fn = time_fn or time.time
        self._lock = threading.RLock()
        self._devices = {}
        self._load()

    def _load(self):
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return
        devices = payload.get("devices", {}) if isinstance(payload, dict) else {}
        if not isinstance(devices, dict):
            return
        for device_id, record in devices.items():
            if DEVICE_ID_RE.fullmatch(str(device_id)) and isinstance(record, dict):
                self._devices[str(device_id)] = record

    def _save_locked(self):
        _atomic_write_json(
            self.path,
            {"version": 1, "devices": self._devices},
        )

    def _commit_record_locked(self, device_id, record):
        # Do not publish a failed command/access update to later requests.
        previous = self._devices.get(device_id)
        self._devices[device_id] = record
        try:
            self._save_locked()
        except Exception:
            if previous is None:
                del self._devices[device_id]
            else:
                self._devices[device_id] = previous
            raise

    def checkin(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Некорректный запрос устройства.")
        device_id = str(payload.get("device_id") or "").strip()
        if not DEVICE_ID_RE.fullmatch(device_id):
            raise ValueError("Некорректный ID устройства.")
        device_name = _clean_text(payload.get("device_name"), 80) or device_id
        status = payload.get("status", {})
        if not isinstance(status, dict):
            status = {}
        safe_status = {
            "app_version": _clean_text(status.get("app_version"), 40),
            "state": _clean_text(status.get("state"), 30),
            "status": _clean_text(status.get("status"), 500),
            "account": _clean_text(status.get("account"), 100),
            "current_task": _clean_text(status.get("current_task"), 120),
            "adb_serial": _clean_text(status.get("adb_serial"), 80),
        }
        try:
            ack_command_id = max(0, int(payload.get("ack_command_id", 0) or 0))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Некорректный номер подтверждённой команды.") from exc
        now = float(self.time_fn())
        with self._lock:
            record = deepcopy(self._devices.get(
                device_id,
                {
                    "device_id": device_id,
                    "device_name": device_name,
                    "access_allowed": True,
                    "command_seq": 0,
                    "command": None,
                    "last_seen": 0.0,
                    "status": {},
                },
            ))
            record["device_name"] = device_name
            record["last_seen"] = now
            record["status"] = safe_status
            command = record.get("command")
            if isinstance(command, dict) and ack_command_id >= int(command.get("id", 0) or 0):
                record["command"] = None
                command = None
            self._commit_record_locked(device_id, record)
            return {
                "ok": True,
                "server_time": now,
                "access_allowed": bool(record.get("access_allowed", True)),
                "command": deepcopy(command),
            }

    def list_devices(self):
        now = float(self.time_fn())
        with self._lock:
            result = []
            for device_id, source in self._devices.items():
                record = deepcopy(source)
                record["device_id"] = device_id
                last_seen = float(record.get("last_seen", 0.0) or 0.0)
                record["online"] = bool(last_seen and now - last_seen <= self.online_timeout)
                result.append(record)
        return sorted(
            result,
            key=lambda item: (
                not item.get("online", False),
                str(item.get("device_name") or "").lower(),
            ),
        )

    def _get_locked(self, device_id):
        try:
            return self._devices[str(device_id)]
        except KeyError as exc:
            raise KeyError("Устройство не найдено.") from exc

    def set_command(self, device_id, action):
        action = str(action or "").strip().lower()
        if action not in ALLOWED_COMMANDS:
            raise ValueError("Недопустимая команда.")
        with self._lock:
            device_id = str(device_id)
            record = deepcopy(self._get_locked(device_id))
            command_id = int(record.get("command_seq", 0) or 0) + 1
            record["command_seq"] = command_id
            record["command"] = {
                "id": command_id,
                "action": action,
                "created_at": float(self.time_fn()),
            }
            self._commit_record_locked(device_id, record)
            return deepcopy(record["command"])

    def set_access(self, device_id, allowed):
        with self._lock:
            device_id = str(device_id)
            record = deepcopy(self._get_locked(device_id))
            record["access_allowed"] = bool(allowed)
            if not allowed:
                command_id = int(record.get("command_seq", 0) or 0) + 1
                record["command_seq"] = command_id
                record["command"] = {
                    "id": command_id,
                    "action": "stop",
                    "created_at": float(self.time_fn()),
                }
            self._commit_record_locked(device_id, record)
            return bool(record["access_allowed"])


DASHBOARD_HTML = r"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BuZzbot Remote Hub</title>
  <style>
    :root { --ink:#16252e; --panel:#f4f8fa; --line:#cad7dd; --orange:#e46922; --green:#477b57; --red:#a64c40; --muted:#70818a; }
    * { box-sizing:border-box; }
    body { margin:0; background:linear-gradient(145deg,#13242d,#263e49); color:var(--ink); font:14px "Segoe UI",sans-serif; min-height:100vh; }
    header { color:white; max-width:1180px; margin:auto; padding:30px 24px 18px; display:flex; align-items:end; justify-content:space-between; }
    h1 { margin:0; font:700 27px Bahnschrift,"Segoe UI",sans-serif; letter-spacing:.5px; }
    header p { margin:6px 0 0; color:#aebdc4; }
    #auth { display:flex; gap:8px; }
    input { border:1px solid #637983; border-radius:7px; padding:9px 11px; min-width:280px; background:#edf3f5; }
    button { border:0; border-radius:7px; padding:8px 11px; cursor:pointer; font-weight:650; background:#dce7eb; color:#243740; }
    button:hover { filter:brightness(.96); }
    main { max-width:1180px; margin:auto; padding:0 24px 40px; }
    #message { color:#dce7eb; padding:8px 0 14px; min-height:38px; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(330px,1fr)); gap:14px; }
    .device { background:var(--panel); border:1px solid var(--line); border-radius:12px; box-shadow:0 12px 28px #07111644; overflow:hidden; }
    .device.denied { border-color:#c98980; }
    .head { padding:16px 17px 12px; display:flex; justify-content:space-between; gap:12px; border-bottom:1px solid var(--line); }
    .name { font:700 17px Bahnschrift,"Segoe UI",sans-serif; }
    .badge { border-radius:999px; padding:5px 9px; font-size:11px; color:white; background:var(--muted); height:max-content; }
    .badge.online { background:var(--green); }
    .body { padding:14px 17px 16px; }
    dl { display:grid; grid-template-columns:105px 1fr; gap:7px; margin:0 0 15px; }
    dt { color:var(--muted); }
    dd { margin:0; overflow-wrap:anywhere; }
    .status { min-height:39px; }
    .actions { display:flex; gap:7px; flex-wrap:wrap; }
    .start { background:#cfe1d4; color:#244f30; }
    .stop,.deny { background:#ead0cc; color:#7e3027; }
    .update { background:#f0dcc9; color:#78461f; }
    .allow { background:#cfe1d4; color:#244f30; }
    .empty { background:#f4f8fa; border-radius:12px; padding:40px; text-align:center; color:var(--muted); }
    @media(max-width:720px){ header{align-items:flex-start;flex-direction:column;gap:15px} #auth{width:100%} input{min-width:0;flex:1} }
  </style>
</head>
<body>
  <header>
    <div><h1>BuZzbot Remote Hub</h1><p>Состояние приложений и управление доступом</p></div>
    <div id="auth"><input id="token" type="password" placeholder="Секрет Hub"><button id="saveToken">Подключиться</button></div>
  </header>
  <main><div id="message">Введите секрет Hub.</div><div id="devices" class="grid"></div></main>
  <script>
    const tokenInput=document.getElementById('token'), list=document.getElementById('devices'), message=document.getElementById('message');
    const fragment=new URLSearchParams(location.hash.slice(1));
    tokenInput.value=fragment.get('token') || localStorage.getItem('buzzbotHubToken') || '';
    if(fragment.get('token')) history.replaceState(null,'',location.pathname);
    document.getElementById('saveToken').onclick=()=>{localStorage.setItem('buzzbotHubToken',tokenInput.value.trim()); refresh();};
    const headers=()=>({'Authorization':'Bearer '+tokenInput.value.trim(),'Content-Type':'application/json'});
    const text=(node,value)=>{node.textContent=value ?? ''; return node;};
    const field=(dl,label,value)=>{dl.append(text(document.createElement('dt'),label),text(document.createElement('dd'),value||'—'));};
    async function api(path,body){const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:headers(),body:body===undefined?undefined:JSON.stringify(body)}); if(!response.ok) throw new Error(response.status===401?'Неверный секрет Hub':'HTTP '+response.status); return response.json();}
    async function send(id,path,body){try{await api('/api/v1/devices/'+encodeURIComponent(id)+'/'+path,body); await refresh();}catch(e){message.textContent=e.message;}}
    function button(label,cls,fn){const b=text(document.createElement('button'),label); b.className=cls; b.onclick=fn; return b;}
    function renderDevice(device){const card=document.createElement('section'); card.className='device'+(device.access_allowed?'':' denied'); const head=document.createElement('div'); head.className='head'; const title=document.createElement('div'); title.append(text(document.createElement('div'),device.device_name)); title.firstChild.className='name'; title.append(text(document.createElement('small'),device.device_id)); const badge=text(document.createElement('span'),device.online?'ОНЛАЙН':'ОФЛАЙН'); badge.className='badge'+(device.online?' online':''); head.append(title,badge); const body=document.createElement('div'); body.className='body'; const dl=document.createElement('dl'), s=device.status||{}; field(dl,'Доступ',device.access_allowed?'Разрешён':'ЗАКРЫТ'); field(dl,'Версия',s.app_version); field(dl,'Состояние',s.state); field(dl,'Аккаунт',s.account); field(dl,'Задача',s.current_task); field(dl,'Статус',s.status); field(dl,'Последняя связь',device.last_seen?new Date(device.last_seen*1000).toLocaleString():'—'); const actions=document.createElement('div'); actions.className='actions'; actions.append(button('Старт','start',()=>send(device.device_id,'command',{action:'start'})),button('Пауза','',()=>send(device.device_id,'command',{action:'pause'})),button('Продолжить','',()=>send(device.device_id,'command',{action:'resume'})),button('Стоп','stop',()=>send(device.device_id,'command',{action:'stop'})),button('Обновить','update',()=>send(device.device_id,'command',{action:'update'})),device.access_allowed?button('Закрыть доступ','deny',()=>send(device.device_id,'access',{allowed:false})):button('Открыть доступ','allow',()=>send(device.device_id,'access',{allowed:true}))); body.append(dl,actions); card.append(head,body); return card;}
    async function refresh(){if(!tokenInput.value.trim()) return; try{const data=await api('/api/v1/devices'); list.replaceChildren(); if(!data.devices.length){const empty=text(document.createElement('div'),'Устройства ещё не подключались.'); empty.className='empty'; list.append(empty);} else data.devices.forEach(d=>list.append(renderDevice(d))); message.textContent='Обновлено: '+new Date().toLocaleTimeString();}catch(e){message.textContent=e.message;}}
    refresh(); setInterval(refresh,5000);
  </script>
</body>
</html>"""


class RemoteHubRequestHandler(BaseHTTPRequestHandler):
    server_version = "BuZzbotHub/1"

    def log_message(self, format_string, *args):
        LOGGER.debug("Hub HTTP: " + format_string, *args)

    def _send_json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self):
        data = DASHBOARD_HTML.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'",
        )
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self):
        header = str(self.headers.get("Authorization") or "")
        prefix = "Bearer "
        supplied = header[len(prefix):] if header.startswith(prefix) else ""
        return bool(supplied) and hmac.compare_digest(
            supplied.encode("utf-8"), self.server.auth_token.encode("utf-8")
        )

    def _require_auth(self):
        if self._authorized():
            return True
        self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
        return False

    def _read_json(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Некорректный размер запроса.") from exc
        if size <= 0 or size > MAX_BODY_SIZE:
            raise ValueError("Некорректный размер запроса.")
        try:
            payload = json.loads(self.rfile.read(size).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Некорректный JSON.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Ожидался JSON-объект.")
        return payload

    def do_GET(self):
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            self._send_html()
            return
        if path == "/health":
            self._send_json(HTTPStatus.OK, {"ok": True})
            return
        if path == "/api/v1/devices":
            if not self._require_auth():
                return
            self._send_json(
                HTTPStatus.OK,
                {"ok": True, "devices": self.server.store.list_devices()},
            )
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if not self._require_auth():
            return
        try:
            payload = self._read_json()
            if path == "/api/v1/checkin":
                self._send_json(HTTPStatus.OK, self.server.store.checkin(payload))
                return
            match = re.fullmatch(r"/api/v1/devices/([^/]+)/(command|access)", path)
            if not match:
                self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
                return
            device_id = unquote(match.group(1))
            if match.group(2) == "command":
                command = self.server.store.set_command(device_id, payload.get("action"))
                self._send_json(HTTPStatus.OK, {"ok": True, "command": command})
            else:
                if not isinstance(payload.get("allowed"), bool):
                    raise ValueError("Поле allowed должно быть true или false.")
                allowed = self.server.store.set_access(device_id, payload["allowed"])
                self._send_json(HTTPStatus.OK, {"ok": True, "access_allowed": allowed})
        except KeyError as exc:
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": str(exc)})
        except (TypeError, ValueError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except Exception:
            LOGGER.exception("Remote Hub request failed")
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": "internal error"},
            )


class RemoteHubServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, store, auth_token):
        token = str(auth_token or "").strip()
        if len(token) < 24:
            raise ValueError("Секрет Hub должен содержать не менее 24 символов.")
        self.store = store
        self.auth_token = token
        super().__init__(address, RemoteHubRequestHandler)


class RemoteHubRunner:
    def __init__(self, host, port, token, store=None):
        self.server = RemoteHubServer(
            (str(host), int(port)),
            store or RemoteHubStore(),
            token,
        )
        self._thread = None

    @property
    def address(self):
        return self.server.server_address

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self.server.serve_forever,
            name="BuZzbotRemoteHub",
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        # shutdown() blocks forever when serve_forever() was never started.
        if self._thread is not None and self._thread.is_alive():
            self.server.shutdown()
        self.server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        self._thread = None
