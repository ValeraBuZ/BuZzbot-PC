from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import threading
import uuid

from gear_value.valuation import fingerprint, validate_record


class AlreadyRunningError(ValueError):
    pass


class DataDirectoryLock:
    """Prevent two application processes from overwriting the same local database."""
    def __init__(self, root):
        Path(root).mkdir(parents=True, exist_ok=True)
        self.stream = (Path(root) / 'application.lock').open('a+b')
        self.stream.seek(0, 2)
        if self.stream.tell() == 0:
            self.stream.write(b'0')
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise AlreadyRunningError('Приложение с этой базой уже запущено. Откройте его вкладку или завершите работу в его меню.') from None

    def close(self):
        self.stream.close()


class Store:
    def __init__(self, root, seed):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'market.json'
        self.lock = threading.RLock()
        self.seed = Path(seed)
        with self.lock:
            if not self.path.exists():
                data = json.loads(self.seed.read_text(encoding='utf-8'))
                self._write([validate_record(row) for row in data['records']])
            self.read()  # Fail visibly on corruption; never silently erase observations.

    def read(self):
        with self.lock:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if data.get('schema_version') != 1 or not isinstance(data.get('records'), list):
                raise ValueError('Неизвестный формат базы. Восстановите market.json из резервной копии.')
            return [validate_record(row) for row in data['records']]

    def _write(self, rows):
        if self.path.exists():
            shutil.copy2(self.path, self.path.with_suffix('.json.bak'))
        temp = self.path.with_name(f'market-{uuid.uuid4().hex}.tmp')
        try:
            with temp.open('w', encoding='utf-8') as stream:
                json.dump({'schema_version': 1, 'records': rows}, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.path)
        finally:
            temp.unlink(missing_ok=True)

    def save(self, raw):
        row = validate_record(raw)
        with self.lock:
            rows = self.read()
            if row['id']:
                indexes = [i for i, old in enumerate(rows) if old['id'] == row['id']]
                if not indexes:
                    raise ValueError('Запись не найдена. Обновите список.')
                rows[indexes[0]] = row
            else:
                if any(fingerprint(old) == fingerprint(row) for old in rows):
                    raise ValueError('Такое наблюдение уже есть в базе.')
                row['id'] = uuid.uuid4().hex
                rows.append(row)
            self._write(rows)
        return row

    def delete(self, record_id):
        with self.lock:
            rows = self.read()
            filtered = [r for r in rows if r['id'] != record_id]
            if len(filtered) == len(rows):
                raise ValueError('Запись не найдена.')
            self._write(filtered)

    def import_data(self, data):
        if not isinstance(data, dict) or data.get('schema_version') != 1 or not isinstance(data.get('records'), list):
            raise ValueError('Нужен файл экспорта этого приложения (версия 1).')
        if len(data['records']) > 20000:
            raise ValueError('Слишком много записей: максимум 20 000 за один импорт.')
        incoming = [validate_record(r) for r in data['records']]
        with self.lock:
            rows = self.read()
            ids = {r['id'] for r in rows}
            prints = {fingerprint(r) for r in rows}
            added = 0
            for row in incoming:
                identity = fingerprint(row)
                if (row['id'] and row['id'] in ids) or identity in prints:
                    continue
                row['id'] = row['id'] or uuid.uuid4().hex
                rows.append(row)
                ids.add(row['id'])
                prints.add(identity)
                added += 1
            if added:
                self._write(rows)
        return {'added': added, 'skipped': len(incoming) - added}


def safe_image_name(name):
    if not re.fullmatch(r'[a-zA-Z0-9_-]+\.png', name):
        raise ValueError('Некорректное имя снимка.')
    return name
