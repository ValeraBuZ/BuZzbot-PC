from __future__ import annotations

import argparse
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import threading
import urllib.request
import time
from urllib.parse import urlsplit
import webbrowser

from gear_value import catalog
from gear_value.storage import AlreadyRunningError, DataDirectoryLock, Store, safe_image_name
from gear_value.valuation import estimate

ASSETS = Path(__file__).resolve().parent


def default_data_dir():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'DoomsdayGearValue'


def adb_path():
    candidates = [os.environ.get('ADB_PATH'), r'C:\LDPlayer\LDPlayer9\adb.exe',
                  r'C:\LDPlayer\LDPlayer4.0\adb.exe', shutil.which('adb')]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise ValueError('ADB не найден. Запустите LDPlayer или задайте ADB_PATH перед запуском приложения.')


def run_adb(*args):
    result = subprocess.run([adb_path(), *args], capture_output=True, timeout=15,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise ValueError('Эмулятор не ответил. Проверьте подключение LDPlayer.')
    return result.stdout


def devices():
    lines = run_adb('devices').decode('utf-8', 'replace').splitlines()
    return [parts[0] for line in lines if len(parts := line.split()) == 2 and parts[1] == 'device']


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, data_dir):
        self.process_lock = DataDirectoryLock(data_dir)
        try:
            self.store = Store(data_dir, ASSETS / 'seed.json')
            self.token = secrets.token_urlsafe(32)
            self.instance_id = secrets.token_hex(16)
            super().__init__(address, Handler)
            self.runtime_path = self.store.root / 'running.json'
            self.runtime_path.write_text(json.dumps({'port': self.server_port, 'instance_id': self.instance_id}), encoding='utf-8')
        except Exception:
            self.process_lock.close()
            raise

    def server_close(self):
        super().server_close()
        if hasattr(self, 'runtime_path'):
            self.runtime_path.unlink(missing_ok=True)
        self.process_lock.close()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send(self, data, content_type='application/json; charset=utf-8', status=200):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(data)

    def allowed(self, mutation=False):
        host = f'127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host') != host:
            self.send({'error': 'Неверный адрес приложения.'}, status=403)
            return False
        if mutation and (self.headers.get('X-App-Token') != self.server.token or
                         self.headers.get('Origin') not in (None, f'http://{host}')):
            self.send({'error': 'Обновите страницу приложения.'}, status=403)
            return False
        return True

    def do_GET(self):
        if not self.allowed():
            return
        path = urlsplit(self.path).path
        try:
            if path == '/api/state':
                self.send({'records': self.server.store.read(), 'token': self.server.token, 'instance_id': self.server.instance_id,
                           'today': date.today().isoformat(), 'data_dir': str(self.server.store.root),
                           'catalog': {name: getattr(catalog, name) for name in
                                       ('SLOTS', 'RARITIES', 'STAT_LABELS', 'STAT_COLORS', 'STATUSES')},
                           'research': json.loads((ASSETS / 'research.json').read_text(encoding='utf-8'))})
            elif path == '/api/export':
                self.send({'schema_version': 1, 'records': self.server.store.read()})
            elif path == '/api/devices':
                self.send({'devices': devices()})
            elif path.startswith('/images/'):
                name = safe_image_name(path.removeprefix('/images/'))
                target = self.server.store.root / 'screenshots' / name
                if not target.is_file():
                    target = ASSETS / 'evidence' / name
                if not target.is_file():
                    raise ValueError('Снимок отсутствует на этом компьютере.')
                self.send(target.read_bytes(), 'image/png')
            elif path in ('/', '/app.js', '/style.css'):
                file = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}[path]
                mime = {'/': 'text/html; charset=utf-8', '/app.js': 'text/javascript; charset=utf-8',
                        '/style.css': 'text/css; charset=utf-8'}[path]
                self.send((ASSETS / 'web' / file).read_bytes(), mime)
            elif path == '/favicon.ico':
                self.send(b'', 'image/x-icon', 204)
            else:
                self.send({'error': 'Не найдено.'}, status=404)
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            self.send({'error': str(exc)}, status=400)

    def do_POST(self):
        if not self.allowed(mutation=True):
            return
        try:
            length = int(self.headers.get('Content-Length', 0))
            path = urlsplit(self.path).path
            if path == '/api/recognize':
                from gear_value.recognition import recognize_upload, MAX_BYTES
                if not 0 < length <= MAX_BYTES:
                    raise ValueError('Выберите снимок до 15 МБ.')
                if self.headers.get('Content-Type', '').split(';')[0] not in ('image/png', 'image/jpeg', 'image/webp'):
                    raise ValueError('Поддерживаются PNG, JPG и WebP.')
                models = {r['name']: r['slot'] for r in json.loads((ASSETS / 'seed.json').read_text(encoding='utf-8'))['records']}
                self.send(recognize_upload(self.rfile.read(length), self.server.store.root / 'screenshots', models))
                return
            if not 0 < length <= 8_000_000:
                raise ValueError('Недопустимый размер данных (до 8 МБ).')
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('Нужны данные JSON.')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Ожидается объект JSON.')
            path = urlsplit(self.path).path
            if path == '/api/estimate':
                result = estimate(data['item'], self.server.store.read(), max_age=data.get('max_age', 30),
                                  exclude_id=data.get('exclude_id'))
            elif path == '/api/save':
                result = self.server.store.save(data)
            elif path == '/api/delete':
                self.server.store.delete(data['id'])
                result = {'ok': True}
            elif path == '/api/import':
                result = self.server.store.import_data(data)
            elif path == '/api/capture':
                serial = data.get('serial')
                if serial not in devices():
                    raise ValueError('Выберите подключённый эмулятор.')
                payload = run_adb('-s', serial, 'exec-out', 'screencap', '-p')
                if not payload.startswith(b'\x89PNG\r\n\x1a\n'):
                    raise ValueError('Не удалось получить снимок.')
                folder = self.server.store.root / 'screenshots'
                folder.mkdir(exist_ok=True)
                name = f'capture-{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(4)}.png'
                (folder / name).write_bytes(payload)
                result = {'evidence': name}
            elif path == '/api/shutdown':
                self.send({'ok': True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            else:
                self.send({'error': 'Не найдено.'}, status=404)
                return
            self.send(result)
        except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as exc:
            self.send({'error': str(exc)}, status=400)


def existing_instance(data_dir):
    try:
        info = json.loads((Path(data_dir) / 'running.json').read_text(encoding='utf-8'))
        port = info['port']
        if not isinstance(port, int) or not 1 <= port <= 65535:
            return None
        url = f'http://127.0.0.1:{port}'
        with urllib.request.urlopen(url + '/api/state', timeout=2) as response:
            state = json.load(response)
        return url if state.get('instance_id') == info.get('instance_id') and info.get('instance_id') else None
    except (OSError, ValueError, KeyError):
        return None


def main():
    parser = argparse.ArgumentParser(description='Отдельная оценка снаряжения Doomsday')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--data-dir', type=Path, default=default_data_dir())
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    try:
        try:
            server = Server(('127.0.0.1', args.port), args.data_dir)
        except AlreadyRunningError:
            url = existing_instance(args.data_dir)
            if not url:
                time.sleep(.3)
                url = existing_instance(args.data_dir)
            if not url:
                raise
            if not args.no_browser:
                webbrowser.open(url)
            return
        url = f'http://127.0.0.1:{server.server_port}'
        if sys.stdout:
            print(url, flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        server.serve_forever()
        server.server_close()
    except Exception as exc:
        if getattr(sys, 'frozen', False):
            import tkinter.messagebox
            tkinter.messagebox.showerror('Оценка снаряжения', str(exc))
        else:
            raise


if __name__ == '__main__':
    main()
