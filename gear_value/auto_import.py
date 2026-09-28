"""Folder ingestion: persist verified text first, then remove only that unchanged input file."""
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid

from gear_value.recognition import recognize_upload, MAX_BYTES
from gear_value.valuation import fingerprint, validate_record

EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}


class AutoImporter:
    def __init__(self, store, inbox):
        self.store = store
        self.inbox = Path(inbox).resolve()
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.path = store.root / 'import_log.json'
        self.lock = threading.RLock()
        self.entries = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
        self.seen = {}

    def _persist(self):
        temp = self.path.with_name('import-' + uuid.uuid4().hex + '.tmp')
        try:
            with temp.open('w', encoding='utf-8') as stream:
                json.dump(self.entries, stream, ensure_ascii=False, indent=2)
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temp, self.path)
        finally:
            temp.unlink(missing_ok=True)

    def snapshot(self):
        with self.lock:
            return [dict(entry) for entry in sorted(self.entries.values(), key=lambda e:e['updated'], reverse=True)]

    def _input(self, filename):
        path = self.inbox / filename
        if Path(filename).name != filename or path.is_symlink() or path.resolve().parent != self.inbox:
            raise ValueError('Файл должен находиться непосредственно в папке новых снимков.')
        if path.suffix.lower() not in EXTENSIONS:
            raise ValueError('Нужен PNG, JPG или WebP.')
        return path

    def next_file(self):
        with self.lock:
            for path in sorted(self.inbox.iterdir(), key=lambda p:p.name):
                if not path.is_file() or path.is_symlink() or path.suffix.lower() not in EXTENSIONS:
                    continue
                info = path.stat(); signature = (info.st_size, info.st_mtime_ns)
                stable = self.seen.get(path.name) == signature
                self.seen[path.name] = signature
                if not stable or time.time()-info.st_mtime < .5:
                    continue
                if any(e['filename'] == path.name and (e['size'], e['mtime_ns']) == signature
                       and e['status'] in ('review', 'delete_failed') for e in self.entries.values()):
                    continue
                return path.name
        return None

    def _write_record(self, raw):
        row = validate_record(raw)
        if row['rarity'] != 'legendary':
            raise ValueError('В базу добавляем только золотые (легендарные) вещи.')
        with self.store.lock:
            existing = next((r for r in self.store.read() if fingerprint(r, include_date=False) == fingerprint(row, include_date=False)), None)
            if existing:
                return existing, True
            row['id'] = ''
            return self.store.save(row), False

    def _finish(self, entry, raw):
        path = self._input(entry['filename'])
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('Снимок изменился после чтения. Обработайте его заново.')
        row, duplicate = self._write_record(raw)
        entry.update(status='duplicate' if duplicate else 'saved', record_id=row['id'], reason='', record=row,
                     updated=datetime.now().isoformat(timespec='seconds'))
        # A crash before this point or a failed journal write must leave the image intact.
        self.entries[entry['id']] = entry
        self._persist()
        # Verify both persistence and file identity immediately before deletion.
        if not any(r['id'] == row['id'] for r in self.store.read()):
            raise ValueError('Запись в базе не подтверждена. Снимок сохранён.')
        try:
            path = self._input(entry['filename'])
            if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
                raise ValueError('Снимок изменился после сохранения данных.')
            path.unlink()
        except (OSError, ValueError) as exc:
            entry.update(status='delete_failed', reason=f'Данные сохранены, но снимок не удалён: {exc}')
            self._persist()
        return row

    def process(self, filename, recognize=recognize_upload):
        path = self._input(filename)
        info = path.stat()
        payload = path.read_bytes() if info.st_size <= MAX_BYTES else b''
        digest = hashlib.sha256(payload).hexdigest()
        key = hashlib.sha256((filename + digest).encode()).hexdigest()[:32]
        entry = {'id':key, 'filename':filename, 'sha256':digest, 'size':info.st_size, 'mtime_ns':info.st_mtime_ns,
                 'observed':datetime.fromtimestamp(info.st_mtime).date().isoformat(),
                 'updated':datetime.now().isoformat(timespec='seconds'), 'status':'review', 'reason':'', 'draft':None}
        known = json.loads(self.store.seed.read_text(encoding='utf-8'))['records']
        models = {r['name']:r['slot'] for r in known + self.store.read()}
        try:
            if info.st_size > MAX_BYTES:
                raise ValueError('Снимок больше 15 МБ. Уменьшите его и сохраните заново.')
            result = recognize(payload, None, models, save_image=False)
            entry['draft'] = result
            auction = result.get('auction')
            if not auction or not auction.get('price'):
                raise ValueError('Нет уверенно прочитанной цены аукциона. Проверьте цену и поля вручную.')
            if result['warnings']:
                raise ValueError('Есть неуверенно прочитанные поля. Проверьте карточку.')
            raw = {**result['item'], 'id':'', 'price':auction['price'], 'status':auction['status'],
                   'observed':entry['observed'], 'source':f'Автоимпорт: {filename}', 'evidence':'',
                   'notes':'Распознано автоматически. Дата по времени файла. Объявление или показанная ставка, не подтверждённая продажа.',
                   'sale_confirmed':False}
            if raw['status'] not in ('ask', 'bid'):
                raise ValueError('Продажи требуют ручного подтверждения.')
            with self.lock:
                self._finish(entry, raw)
        except Exception as exc:
            with self.lock:
                entry.update(status='review', reason=str(exc), updated=datetime.now().isoformat(timespec='seconds'))
                self.entries[key] = entry
                self._persist()
        return dict(entry)

    def complete(self, entry_id, raw):
        with self.lock:
            entry = self.entries[entry_id]
            return self._finish(entry, {**raw, 'evidence':''})
