"""Standalone Windows interface. OCR and pricing call Python directly, without HTTP."""
from __future__ import annotations

from datetime import date
import hashlib
import io
import json
import os
from pathlib import Path
import queue
import sys
import threading
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import webbrowser

from PIL import Image, ImageTk, ImageGrab

from gear_value import catalog
from gear_value.app import ASSETS, default_data_dir
from gear_value.storage import Store, DataDirectoryLock, AlreadyRunningError
from gear_value.recognition import recognize_upload, MAX_BYTES, decode_image
from gear_value.auto_import import AutoImporter
from gear_value.valuation import estimate, validate_item, stat_label
from gear_value.presentation import result_text, displayed_value, entered_value, stat_text


def money(n):
    return f'{n:,}'.replace(',', ' ') + ' G'


def details_text(result):
    headings = {'sold': 'Ориентир по завершённым сделкам',
                'ask': 'Запрашивают продавцы · продажа не подтверждена',
                'insufficient': 'Недостаточно близких аналогов'}
    lines = []
    signals = result.get('market_signals')
    if signals:
        lines += ['Примеры по отдельным характеристикам', 'Цены относятся к целым вещам. Отличия показаны рядом.', '']
        for criterion in signals.get('criteria', []):
            lines.append(stat_text(criterion['stat']))
            for reference in criterion['references'][:3] + criterion.get('donor_references', [])[:3]:
                row = reference['record']
                relation = reference['base_relation']
                lines.append('  ' + {'close':'База близкая', 'values':'База того же типа, другие проценты',
                                     'different':'Для переплавки: другая база', 'missing':'Для переплавки: база не прочитана'}[relation])
                lines += [f"  {stat_text(reference['stat'])} · {money(row['price'])} · {catalog.STATUSES[row['status']]}",
                          f"  {row['name']} +{row['level']} · {row['observed']} · {row['source']}",
                          '  База: ' + '; '.join(stat_text(s) for s in row['base_stats'])]
                if reference['factors']:
                    lines.append('  На той вещи ещё: ' + '; '.join(reference['factors']))
            if not criterion['references'] and not criterion.get('donor_references'):
                lines.append('Примеров в этой категории пока нет.')
            lines.append('')
        lines += ['За что могут заплатить', ''] + signals['notes'] + ['']
        for group in signals['groups']:
            lines += [group['title']]
            observed = False
            for key, label in [('ask', 'Продавцы просят'), ('bid', 'Показанные лучшие ставки'), ('sold', 'Подтверждённые сделки')]:
                prices = group['summary'][key]
                if prices:
                    observed = True
                    lines += [f"{label}: {money(prices['low'])} — {money(prices['high'])} · {prices['count']} наблюдений · медиана {money(prices['median'])}"]
            if not observed: lines.append('Для близких значений пока нет цен в базе.')
            lines += [group['explanation']]
            for row in sorted(group['matches'], key=lambda r:r['price'])[:5]:
                lines += [f"  {row['name']} +{row['level']} · {money(row['price'])} · {catalog.STATUSES[row['status']]} · {row['source']}"]
            if group['context']:
                lines += ['Та же связка, другие значения или основа — справочно:' if group['mode'] == 'combo' else 'Та же строка с другими значениями или цветом — справочно:']
                for row in group['context'][:5]:
                    lines += [f"  {row['name']} +{row['level']} · {money(row['price'])} · {catalog.STATUSES[row['status']]}", '  ' + '; '.join(stat_text(s) for s in row['stats'])]
            lines += [group['source']['title'], group['source']['url'], '']
    lines += ['Сравнение всей вещи', headings[result['basis']], '']
    price = result['headline']
    if price:
        lines += [money(price['median']), f"Разброс: {money(price['low'])} — {money(price['high'])} · наблюдений: {price['count']}"]
    else:
        lines.append('Цена предмета пока не определена.')
    lines += [result['confidence'], ''] + result['warnings']
    if result['bids']:
        b = result['bids']
        lines += ['', f"Показанная лучшая ставка: {money(b['low'])} — {money(b['high'])} ({b['count']}). Торги не завершены; наличие покупателя не подтверждено."]
    lines += ['', 'Сопоставимые лоты']
    for r in result['matches']:
        lines += [f"{r['name']} +{r['level']} · {money(r['price'])} · {catalog.STATUSES[r['status']]}",
                  f"{r['observed']} · {r['source']}"]
    if not result['matches']:
        lines.append('Полных аналогов нет. Другая комбинация характеристик не даёт цену всей вещи.')
    if result['related']:
        lines += ['', 'Совпадают отдельные характеристики — справочно']
        for r in result['related'][:12]:
            lines += [f"{r['name']} +{r['level']} · {money(r['price'])} · {catalog.STATUSES[r['status']]}",
                      '; '.join(stat_text(s) for s in r['stats']), '']
    lines += ['', 'Что говорят игроки', result['demand_context']['summary'],
              result['demand_context']['limitation']]
    return '\n'.join(lines)


class ScrollFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        canvas = tk.Canvas(self, highlightthickness=0, bg='#f4f6f8')
        scroll = ttk.Scrollbar(self, orient='vertical', command=canvas.yview)
        self.body = ttk.Frame(canvas, padding=12)
        slot = canvas.create_window((0, 0), window=self.body, anchor='nw')
        self.body.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(slot, width=e.width))
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y'); canvas.pack(side='left', fill='both', expand=True)
        def wheel(event):
            target = event.widget
            while target is not None:
                if target == self:
                    canvas.yview_scroll(-int(event.delta / 120), 'units')
                    return 'break'
                target = getattr(target, 'master', None)
        self.bind_all('<MouseWheel>', wheel, add='+')


class DesktopApp:
    def __init__(self, root, store, inbox=None):
        self.root, self.store = root, store
        self.records = store.read()
        self.evidence, self.excluded_id = '', None
        self.busy = False
        self.last_result = None
        self.preview_image = None
        self.active_import = None
        self.importer = AutoImporter(store, inbox or store.root / 'Новые скриншоты')
        self.jobs = queue.Queue()
        self.stat_rows = {'stats': [], 'base_stats': []}
        self.fields = {}
        root.title('Оценка снаряжения · Doomsday')
        root.geometry('1280x880'); root.minsize(960, 660)
        root.configure(bg='#f4f6f8')
        style = ttk.Style(root); style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10), background='#f4f6f8', foreground='#192d35')
        style.configure('TButton', padding=(12, 8))
        style.configure('TEntry', padding=5, fieldbackground='white')
        style.configure('TCombobox', padding=4, fieldbackground='white')
        style.configure('Title.TLabel', font=('Segoe UI', 22, 'bold'))
        style.configure('Sub.TLabel', font=('Segoe UI', 12, 'bold'))
        style.configure('Accent.TButton', background='#166855', foreground='white')
        style.map('Accent.TButton', background=[('active', '#21846d'), ('disabled', '#96b2ab')])
        style.configure('Treeview', rowheight=30, background='white', fieldbackground='white')
        top = ttk.Frame(root, padding=(20, 12)); top.pack(fill='x')
        ttk.Label(top, text='Оценка снаряжения', style='Title.TLabel').pack(side='left')
        ttk.Label(top, text='DOOMSDAY · 0.6').pack(side='right')
        self.tabs = ttk.Notebook(root); self.tabs.pack(fill='both', expand=True, padx=16, pady=(0, 8))
        self.estimate_tab = ttk.Frame(self.tabs)
        self.market_tab = ttk.Frame(self.tabs, padding=12)
        self.research_tab = ttk.Frame(self.tabs, padding=16)
        self.import_tab = ttk.Frame(self.tabs, padding=16)
        for frame, label in [(self.estimate_tab, 'Оценить предмет'), (self.market_tab, 'База аукциона'), (self.import_tab, 'Автопополнение'), (self.research_tab, 'Исследование рынка')]:
            self.tabs.add(frame, text=label, padding=10)
        self.status = tk.StringVar(value='Вставьте скриншот или выберите файл. Данные хранятся на вашем компьютере.')
        ttk.Label(root, textvariable=self.status, wraplength=1200, padding=(18, 8)).pack(fill='x')
        self.build_estimator(); self.build_market(); self.build_research(); self.build_import()
        root.bind_all('<Control-v>', self.paste_image, add='+')
        root.bind_all('<Control-V>', self.paste_image, add='+')
        root.after(100, self.poll_jobs)
        root.after(1500, self.poll_inbox)
        root.report_callback_exception = self.callback_error

    def callback_error(self, kind, value, tb):
        log = ''.join(traceback.format_exception(kind, value, tb))
        (self.store.root / 'error.log').write_text(log, encoding='utf-8')
        self.status.set(f'Не удалось выполнить действие: {value}')
        messagebox.showerror('Оценка снаряжения', str(value), parent=self.root)

    def build_estimator(self):
        bar = ttk.Frame(self.estimate_tab, padding=12); bar.pack(fill='x')
        self.file_button = ttk.Button(bar, text='Выбрать скриншот', command=self.choose_image, style='Accent.TButton')
        self.file_button.pack(side='left', padx=(0, 8))
        self.paste_button = ttk.Button(bar, text='Вставить скриншот · Ctrl+V', command=self.paste_image)
        self.paste_button.pack(side='left')
        ttk.Button(bar, text='Новый предмет', command=lambda: self.fill_item({})).pack(side='right')
        ttk.Label(self.estimate_tab, text='Золотые вещи · 2 базовые и 3 особые характеристики. Можно вставить весь экран.', padding=(14, 0)).pack(anchor='w')
        panes = ttk.Panedwindow(self.estimate_tab, orient='horizontal'); panes.pack(fill='both', expand=True, pady=8)
        left = ScrollFrame(panes); right = ttk.Frame(panes, padding=12)
        panes.add(left, weight=1); panes.add(right, weight=1)
        form = left.body
        for key, label, values in [('name', 'Название (необязательно)', None), ('slot', 'Категория', catalog.SLOTS),
                                   ('rarity', 'Редкость', catalog.RARITIES), ('level', 'Усиление (+0…20)', None),
                                   ('attempts', 'Попытки торговли', None), ('trait', 'Особая метка', None),
                                   ('market', 'Рынок / группа аукциона', None)]:
            row = ttk.Frame(form); row.pack(fill='x', pady=3)
            ttk.Label(row, text=label, width=25).pack(side='left')
            var = tk.StringVar()
            if key == 'rarity':
                widget = ttk.Label(row, textvariable=var)
            else:
                widget = ttk.Combobox(row, textvariable=var, values=list(values.values()), state='readonly') if values else ttk.Entry(row, textvariable=var)
            widget.pack(side='left', fill='x', expand=True)
            self.fields[key] = (var, values)
        self.stat_frames = {}
        for key, label in [('base_stats', 'Базовые характеристики · 2'), ('stats', 'Особые характеристики · 3')]:
            title = ttk.Frame(form); title.pack(fill='x', pady=(15, 4))
            ttk.Label(title, text=label, style='Sub.TLabel').pack(side='left')
            self.stat_frames[key] = ttk.Frame(form); self.stat_frames[key].pack(fill='x')
        controls = ttk.Frame(self.estimate_tab, padding=(12, 0, 12, 10)); controls.pack(fill='x')
        self.calc_button = ttk.Button(controls, text='Рассчитать стоимость', style='Accent.TButton', command=self.calculate)
        self.calc_button.pack(side='left', fill='x', expand=True)
        ttk.Button(controls, text='Сохранить наблюдение цены', command=self.save_dialog).pack(side='right', padx=(8, 0))
        ttk.Label(right, text='Оценка', style='Sub.TLabel').pack(anchor='w', pady=(0, 8))
        self.output = self.text_box(right)
        self.output.tag_configure('headline', font=('Segoe UI', 18, 'bold'), foreground='#166855', spacing3=8)
        self.output.tag_configure('section', font=('Segoe UI', 11, 'bold'), spacing1=8)
        self.details_button = ttk.Button(right, text='Показать сравнения и источники', command=self.show_details, state='disabled')
        self.details_button.pack(fill='x', pady=8)
        self.preview = ttk.Label(right, text='Здесь появится ваш снимок', anchor='center')
        self.preview.pack(fill='x', pady=8); self.preview.bind('<Button-1>', lambda e: self.show_evidence(self.evidence, current=True))
        self.fill_item({})

    def text_box(self, parent):
        frame = ttk.Frame(parent); frame.pack(fill='both', expand=True)
        text = tk.Text(frame, wrap='word', height=10, font=('Segoe UI', 10), bg='white', fg='#192d35', relief='flat', padx=14, pady=12)
        scroll = ttk.Scrollbar(frame, command=text.yview); text.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y'); text.pack(side='left', fill='both', expand=True)
        text.configure(state='disabled'); return text

    def set_text(self, text, value):
        text.configure(state='normal'); text.delete('1.0', 'end'); text.insert('1.0', value); text.configure(state='disabled')

    def add_stat(self, key, stat=None):
        if len(self.stat_rows[key]) >= (2 if key == 'base_stats' else 3): return
        stat = stat or {'key': '', 'color': 'unknown'}
        frame = ttk.Frame(self.stat_frames[key], padding=(0, 3)); frame.pack(fill='x')
        label = tk.StringVar(value=catalog.STAT_LABELS.get(stat.get('key'), ''))
        value = tk.StringVar(value=displayed_value(stat))
        color = tk.StringVar(value=catalog.STAT_COLORS.get(stat.get('color'), 'Не указан'))
        custom = tk.StringVar(value=stat.get('custom', ''))
        combo = ttk.Combobox(frame, textvariable=label, values=list(catalog.STAT_LABELS.values()), state='readonly')
        combo.pack(fill='x')
        line = ttk.Frame(frame); line.pack(fill='x', pady=3)
        ttk.Entry(line, textvariable=value, width=10).pack(side='left')
        ttk.Label(line, text=' %  ').pack(side='left')
        if key == 'stats':
            ttk.Combobox(line, textvariable=color, values=list(catalog.STAT_COLORS.values()), width=14, state='readonly').pack(side='left', fill='x', expand=True)
        entry = ttk.Entry(frame, textvariable=custom)
        def show_custom(*_):
            if label.get() == catalog.STAT_LABELS['custom']: entry.pack(fill='x')
            else: entry.pack_forget()
        combo.bind('<<ComboboxSelected>>', show_custom); show_custom()
        row = (frame, label, value, color, custom)
        self.stat_rows[key].append(row)

    def fill_item(self, item):
        if self.busy: return
        self.preview_image = None
        self.active_import = None
        defaults = {'slot': 'firearm', 'rarity': 'legendary', 'level': '0', 'market': 'Текущий аукцион'}
        for key, (var, mapping) in self.fields.items():
            value = item.get(key, defaults.get(key, ''))
            if key == 'rarity' and not value:
                value = 'legendary'
            var.set(mapping.get(value, '') if mapping else ('' if value is None else str(value)))
        for key, rows in self.stat_rows.items():
            for row in rows: row[0].destroy()
            rows.clear()
            for stat in item.get(key, []): self.add_stat(key, stat)
            while len(rows) < (2 if key == 'base_stats' else 3): self.add_stat(key)
        self.evidence = item.get('evidence', '')
        self.excluded_id = item.get('id')
        self.last_result = None
        self.details_button.configure(state='disabled')
        self.set_text(self.output, 'Проверьте поля слева.\nНажмите «Рассчитать стоимость».')
        self.update_preview(); self.tabs.select(self.estimate_tab)

    def get_item(self):
        result = {}
        for key, (var, mapping) in self.fields.items():
            result[key] = {v: k for k, v in mapping.items()}.get(var.get(), '') if mapping else var.get()
        if result['rarity'] != 'legendary':
            raise ValueError('Оцениваем только золотые (легендарные) вещи. Выберите другую карточку.')
        stat_keys = {v: k for k, v in catalog.STAT_LABELS.items()}
        colors = {v: k for k, v in catalog.STAT_COLORS.items()}
        for key, rows in self.stat_rows.items():
            for index, (_, label, value, _, _) in enumerate(rows, 1):
                if not label.get() or not value.get().strip():
                    section = 'базовую' if key == 'base_stats' else 'особую'
                    raise ValueError(f'Заполните {section} характеристику №{index}: название и процент.')
            result[key] = [{'key': stat_keys.get(label.get()), 'value': entered_value(stat_keys.get(label.get()), value.get()), 'color': colors.get(color.get(), 'unknown'), 'custom': custom.get()} for _, label, value, color, custom in rows]
        return validate_item(result)

    def choose_image(self):
        if self.busy: return
        path = filedialog.askopenfilename(parent=self.root, title='Скриншот карточки вещи', filetypes=[('Изображения', '*.png *.jpg *.jpeg *.webp')])
        if path: self.load_path(path)

    def load_path(self, path):
        try:
            path = Path(path)
            if path.stat().st_size > MAX_BYTES: raise ValueError('Выберите снимок до 15 МБ.')
            self.start_recognition(path.read_bytes())
        except Exception as exc: self.status.set(str(exc))

    def paste_image(self, event=None):
        if self.busy: return 'break'
        try:
            content = ImageGrab.grabclipboard()
            if isinstance(content, Image.Image):
                blob = io.BytesIO(); content.save(blob, format='PNG'); self.start_recognition(blob.getvalue()); return 'break'
            if isinstance(content, list):
                path = next((p for p in content if Path(p).suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp')), None)
                if path: self.load_path(path); return 'break'
            if event is None:
                self.status.set('В буфере нет изображения. Сделайте снимок Win+Shift+S или скопируйте файл и нажмите «Вставить скриншот».')
        except Exception as exc: self.status.set(f'Не удалось прочитать буфер обмена: {exc}')
        return None

    def start_recognition(self, payload):
        if self.busy: return
        self.busy = True
        self.status.set('Читаю название и характеристики…')
        self.file_button.configure(state='disabled'); self.paste_button.configure(state='disabled'); self.calc_button.configure(state='disabled')
        self.tabs.select(self.estimate_tab)
        known = json.loads((ASSETS / 'seed.json').read_text(encoding='utf-8'))['records']
        models = {r['name']: r['slot'] for r in known + self.records}
        def work():
            try:
                result = recognize_upload(payload, None, models, save_image=False)
                result['_preview'] = decode_image(payload)
                self.jobs.put(('recognized', result))
            except Exception as exc:
                (self.store.root / 'error.log').write_text(traceback.format_exc(), encoding='utf-8')
                self.jobs.put(('error', str(exc) or 'Не удалось прочитать снимок. Попробуйте другой файл.'))
        threading.Thread(target=work, daemon=True).start()

    def poll_jobs(self):
        try:
            while True:
                kind, result = self.jobs.get_nowait()
                self.busy = False
                self.file_button.configure(state='normal'); self.paste_button.configure(state='normal'); self.calc_button.configure(state='normal')
                if kind == 'recognized':
                    self.fill_item({**result['item'], 'evidence': result['evidence']})
                    self.preview_image = result.pop('_preview')
                    self.update_preview()
                    self.status.set('Снимок прочитан. Проверьте цифры и нажмите «Рассчитать стоимость».')
                    warnings = result['warnings']
                    self.set_text(self.output, 'Карточка прочитана.\nПроверьте поля слева и нажмите «Рассчитать стоимость».' + ('\n\n' + '\n'.join(warnings[:3]) if warnings else ''))
                elif kind == 'imported':
                    self.refresh_market(); self.refresh_import()
                    label = {'saved':'Добавлено в базу', 'duplicate':'Повтор пропущен', 'review':'Нужна проверка', 'delete_failed':'Данные сохранены; снимок не удалён'}[result['status']]
                    self.status.set(f"{label}: {result['filename']}")
                elif kind == 'import_error':
                    self.status.set('Автопополнение: ' + result)
                else: self.status.set(result); self.set_text(self.output, 'Снимок не удалось прочитать.\n\n' + result)
        except queue.Empty: pass
        self.root.after(100, self.poll_jobs)

    def calculate(self):
        if self.busy: return
        try:
            item = self.get_item()
            result = estimate(item, self.store.read(), exclude_id=self.excluded_id)
            self.set_text(self.output, result_text(result, item))
            self.output.tag_add('headline', '1.0', '1.end')
            for heading in ('База и связка', 'По отдельным характеристикам', 'Для переплавки'):
                start = self.output.search(heading, '1.0', 'end')
                if start: self.output.tag_add('section', start, f'{start} lineend')
            self.last_result = result
            self.details_button.configure(state='normal')
            self.status.set('Готово. Подробности — по кнопке «Показать сравнения и источники».')
        except ValueError as exc: self.status.set(str(exc)); messagebox.showinfo('Проверьте поля', str(exc), parent=self.root)

    def show_details(self):
        if self.last_result is None: return
        win = tk.Toplevel(self.root); win.title('Сравнения и источники'); win.geometry('850x650')
        self.set_text(self.text_box(win), details_text(self.last_result))

    def evidence_path(self, name):
        if not name: return None
        path = self.store.root / 'screenshots' / name
        return path if path.is_file() else ASSETS / 'evidence' / name

    def update_preview(self):
        path = self.evidence_path(self.evidence)
        if self.preview_image is not None or (path and path.is_file()):
            if self.preview_image is not None:
                image = self.preview_image.copy()
            else:
                with Image.open(path) as source: image = source.copy()
            image.thumbnail((520, 210))
            self.photo = ImageTk.PhotoImage(image)
            self.preview.configure(image=self.photo, text='')
        else: self.preview.configure(image='', text='Снимок · нажмите на изображение для увеличения')

    def show_evidence(self, name, current=False):
        path = self.evidence_path(name)
        memory = self.preview_image if current else None
        if memory is None and (not path or not path.is_file()): return
        win = tk.Toplevel(self.root); win.title('Снимок предмета')
        if memory is not None:
            image = memory.copy()
        else:
            with Image.open(path) as source: image = source.copy()
        image.thumbnail((self.root.winfo_screenwidth() - 120, self.root.winfo_screenheight() - 140))
        photo = ImageTk.PhotoImage(image)
        label = ttk.Label(win, image=photo); label.image = photo; label.pack()

    def build_market(self):
        bar = ttk.Frame(self.market_tab); bar.pack(fill='x', pady=(0, 10))
        self.search = tk.StringVar(); ttk.Entry(bar, textvariable=self.search).pack(side='left', fill='x', expand=True)
        self.search.trace_add('write', lambda *_: self.refresh_market())
        ttk.Button(bar, text='Импорт базы', command=self.import_data).pack(side='left', padx=8)
        ttk.Button(bar, text='Экспорт', command=self.export_data).pack(side='left')
        self.count = tk.StringVar(); ttk.Label(self.market_tab, textvariable=self.count).pack(anchor='w', pady=(0, 8))
        wrap = ttk.Frame(self.market_tab); wrap.pack(fill='both', expand=True)
        self.table = ttk.Treeview(wrap, columns=('name', 'price', 'status', 'date', 'stats'), show='headings', selectmode='browse')
        for key, text, width in [('name', 'Предмет', 250), ('price', 'Цена', 100), ('status', 'Наблюдение', 150), ('date', 'Дата', 100), ('stats', 'Характеристики', 520)]:
            self.table.heading(key, text=text); self.table.column(key, width=width, minwidth=80)
        scroll = ttk.Scrollbar(wrap, command=self.table.yview); self.table.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y'); self.table.pack(fill='both', expand=True)
        self.table.bind('<Double-1>', lambda e: self.use_selected())
        actions = ttk.Frame(self.market_tab); actions.pack(fill='x', pady=10)
        ttk.Button(actions, text='Оценить выбранный предмет', command=self.use_selected).pack(side='left')
        ttk.Button(actions, text='Показать снимок', command=lambda: self.selected_action(lambda r: self.show_evidence(r['evidence']))).pack(side='left', padx=8)
        ttk.Button(actions, text='Удалить наблюдение', command=self.delete_selected).pack(side='right')
        self.refresh_market()

    def refresh_market(self):
        self.records = self.store.read()
        self.table.delete(*self.table.get_children())
        term = self.search.get().casefold()
        for r in sorted(self.records, key=lambda r: (r['observed'], -r['price']), reverse=True):
            stats = '; '.join(stat_text(s) for s in r['stats'])
            if term not in (r['name'] + ' ' + stats).casefold(): continue
            self.table.insert('', 'end', iid=r['id'], values=(f"{r['name']} +{r['level']}" + (f" · {r['trait']}" if r['trait'] else ''), money(r['price']), catalog.STATUSES[r['status']], r['observed'], stats))
        self.count.set(f"Наблюдений: {len(self.records)} · цены продавцов: {sum(r['status']=='ask' for r in self.records)} · ставки: {sum(r['status']=='bid' for r in self.records)} · подтверждённые продажи: {sum(r['status']=='sold' for r in self.records)}")

    def selected_action(self, action):
        ids = self.table.selection()
        if ids: action(next(r for r in self.records if r['id'] == ids[0]))

    def use_selected(self):
        self.selected_action(self.fill_item)

    def delete_selected(self):
        def remove(r):
            if messagebox.askyesno('Удалить наблюдение', f"Удалить «{r['name']}»? Предыдущая база останется в резервной копии.", parent=self.root):
                self.store.delete(r['id']); self.refresh_market()
        self.selected_action(remove)

    def save_dialog(self):
        if self.busy: return
        try: item = self.get_item()
        except ValueError as exc:
            messagebox.showinfo('Проверьте поля', str(exc), parent=self.root); return
        win = tk.Toplevel(self.root); win.title('Наблюдение цены'); win.transient(self.root); win.grab_set()
        frame = ttk.Frame(win, padding=20); frame.pack(fill='both', expand=True)
        values = {}
        pending = next((e for e in self.importer.snapshot() if e['id'] == self.active_import), None)
        auction = ((pending or {}).get('draft') or {}).get('auction') or {}
        for key, label, default in [('price', 'Цена в золоте', auction.get('price') or ''), ('observed', 'Дата (ГГГГ-ММ-ДД)', pending['observed'] if pending else date.today().isoformat()), ('source', 'Источник', f"Снимок: {pending['filename']}" if pending else 'Карточка лота в игре'), ('notes', 'Заметка', 'Проверено вручную после распознавания.' if pending else '')]:
            ttk.Label(frame, text=label).pack(anchor='w'); values[key] = tk.StringVar(value=default)
            ttk.Entry(frame, textvariable=values[key], width=55).pack(fill='x', pady=(3, 10))
        ttk.Label(frame, text='Что показывает снимок').pack(anchor='w')
        status = tk.StringVar(value=catalog.STATUSES[auction.get('status', 'ask')])
        ttk.Combobox(frame, textvariable=status, values=list(catalog.STATUSES.values()), state='readonly').pack(fill='x', pady=5)
        confirmed = tk.BooleanVar()
        ttk.Checkbutton(frame, text='Продажа подтверждена журналом торговли', variable=confirmed).pack(anchor='w', pady=10)
        def save():
            try:
                raw = {**item, **{k: v.get() for k, v in values.items()}, 'status': {v:k for k,v in catalog.STATUSES.items()}[status.get()], 'sale_confirmed': confirmed.get(), 'evidence': self.evidence, 'id': ''}
                row = self.importer.complete(pending['id'], raw) if pending else self.store.save(raw)
                self.active_import = None
                self.excluded_id = row['id']; self.refresh_market(); self.refresh_import(); win.destroy(); self.status.set('Наблюдение сохранено.')
            except (ValueError, OSError) as exc: messagebox.showerror('Проверьте данные', str(exc), parent=win)
        ttk.Button(frame, text='Сохранить', command=save, style='Accent.TButton').pack(fill='x')

    def build_import(self):
        settings = self.store.root / 'import_settings.json'
        enabled = json.loads(settings.read_text(encoding='utf-8')).get('enabled', True) if settings.exists() else True
        self.import_enabled = tk.BooleanVar(value=enabled)
        def toggle():
            settings.write_text(json.dumps({'enabled':self.import_enabled.get()}), encoding='utf-8')
        bar = ttk.Frame(self.import_tab); bar.pack(fill='x')
        ttk.Checkbutton(bar, text='Автоматически читать новые снимки', variable=self.import_enabled, command=toggle).pack(side='left')
        ttk.Button(bar, text='Открыть папку', command=lambda: os.startfile(self.importer.inbox)).pack(side='right')
        ttk.Label(self.import_tab, text=str(self.importer.inbox), wraplength=1000).pack(anchor='w', pady=(12, 4))
        ttk.Label(self.import_tab, text='Сохраняйте сюда снимки аукциона с ценой. После записи в базу снимок удаляется.\nНеразборчивые снимки остаются на проверку. Работает, пока открыто приложение.').pack(anchor='w', pady=(0, 14))
        self.import_count = tk.StringVar()
        ttk.Label(self.import_tab, textvariable=self.import_count).pack(anchor='w', pady=(0, 8))
        self.import_table = ttk.Treeview(self.import_tab, columns=('file','status','reason'), show='headings', selectmode='browse')
        for key, label, width in [('file','Снимок',250),('status','Результат',180),('reason','Что проверить',500)]:
            self.import_table.heading(key,text=label); self.import_table.column(key,width=width)
        self.import_table.pack(fill='both',expand=True)
        self.import_table.bind('<Double-1>',lambda e:self.review_import())
        ttk.Button(self.import_tab,text='Проверить выбранный снимок',command=self.review_import).pack(anchor='w',pady=10)
        self.refresh_import()

    def refresh_import(self):
        entries = self.importer.snapshot()
        self.import_table.delete(*self.import_table.get_children())
        names = {'saved':'Добавлено', 'duplicate':'Повтор пропущен', 'review':'Проверить', 'delete_failed':'Снимок не удалён'}
        for entry in entries[:500]:
            self.import_table.insert('', 'end', iid=entry['id'], values=(entry['filename'], names[entry['status']], entry['reason']))
        self.import_count.set(f"Добавлено: {sum(e['status']=='saved' for e in entries)} · повторов: {sum(e['status']=='duplicate' for e in entries)} · проверить: {sum(e['status'] in ('review','delete_failed') for e in entries)}")

    def poll_inbox(self):
        try:
            if self.import_enabled.get() and not self.busy:
                filename = self.importer.next_file()
                if filename:
                    self.busy = True
                    self.file_button.configure(state='disabled'); self.paste_button.configure(state='disabled'); self.calc_button.configure(state='disabled')
                    self.status.set('Добавляю из папки: ' + filename)
                    def work():
                        try: self.jobs.put(('imported', self.importer.process(filename)))
                        except Exception as exc: self.jobs.put(('import_error', str(exc)))
                    threading.Thread(target=work, daemon=True).start()
        except OSError as exc: self.status.set('Папка автопополнения недоступна: ' + str(exc))
        self.root.after(1500, self.poll_inbox)

    def review_import(self):
        if self.busy: return
        ids = self.import_table.selection()
        if not ids: return
        entry = next(e for e in self.importer.snapshot() if e['id'] == ids[0])
        path = self.importer.inbox / entry['filename']
        if entry['status'] in ('review','delete_failed') and path.is_file():
            self.fill_item((entry.get('draft') or {}).get('item', {}))
            self.active_import = entry['id']
            self.preview_image = decode_image(path.read_bytes()); self.update_preview()
            self.status.set('Проверьте поля и нажмите «Сохранить наблюдение цены».')
        elif entry.get('record'):
            self.fill_item(entry['record']); self.calculate()

    def import_data(self):
        path = filedialog.askopenfilename(parent=self.root, filetypes=[('База JSON', '*.json')])
        if not path: return
        try:
            result = self.store.import_data(json.loads(Path(path).read_text(encoding='utf-8-sig')))
            self.refresh_market(); self.status.set(f"Добавлено: {result['added']}. Повторов: {result['skipped']}.")
        except (ValueError, OSError) as exc: messagebox.showerror('Импорт', str(exc), parent=self.root)

    def export_data(self):
        path = filedialog.asksaveasfilename(parent=self.root, initialfile=f'DoomsdayGearValue-{date.today()}.json', defaultextension='.json', filetypes=[('База JSON', '*.json')])
        if path:
            Path(path).write_text(json.dumps({'schema_version': 1, 'records': self.store.read()}, ensure_ascii=False, indent=2), encoding='utf-8')
            self.status.set('База экспортирована. Изображения хранятся отдельно в приложении.')

    def build_research(self):
        research = json.loads((ASSETS / 'research.json').read_text(encoding='utf-8'))
        text = self.text_box(self.research_tab)
        sections = [f"Проверено: {research['checked']}", research['coverage'], '']
        if research.get('sample'): sections += [research['sample']['summary'], '']
        for finding in research['findings']:
            sections += [finding['title'], finding['summary'], finding['limitation'], finding['url'], '']
        self.set_text(text, '\n\n'.join(sections))
        links = ttk.Frame(self.research_tab); links.pack(fill='x', pady=10)
        for index, finding in enumerate(research['findings']):
            ttk.Button(links, text=f"{index + 1}. {finding['region']}", command=lambda url=finding['url']: webbrowser.open(url)).grid(row=index // 4, column=index % 4, padx=3, pady=3, sticky='ew')


def run(data_dir=None, image_path=None):
    root = tk.Tk(); root.withdraw()
    data_dir = Path(data_dir or default_data_dir())
    event = None
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateEventW.restype = wintypes.HANDLE
        kernel.SetEvent.argtypes = [wintypes.HANDLE]
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        name = 'Local\\DoomsdayGearValue-' + hashlib.sha256(str(data_dir.resolve()).casefold().encode()).hexdigest()[:20]
        event = kernel.CreateEventW(None, False, False, name)
        if event and ctypes.get_last_error() == 183:
            kernel.SetEvent(event); kernel.CloseHandle(event); root.destroy(); return
    lock = None
    try:
        lock = DataDirectoryLock(data_dir)
        store = Store(data_dir, ASSETS / 'seed.json')
        inbox = Path(sys.executable).parent / 'Новые скриншоты' if getattr(sys, 'frozen', False) else data_dir / 'Новые скриншоты'
        app = DesktopApp(root, store, inbox)
        if event:
            def activate():
                if kernel.WaitForSingleObject(event, 0) == 0:
                    root.deiconify(); root.lift(); root.focus_force()
                root.after(250, activate)
            root.after(250, activate)
        if image_path:
            root.after(200, lambda: app.load_path(image_path))
        root.deiconify(); root.mainloop()
    except Exception as exc:
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / 'error.log').write_text(traceback.format_exc(), encoding='utf-8')
        messagebox.showerror('Оценка снаряжения', str(exc), parent=root)
    finally:
        if lock: lock.close()
        if event: kernel.CloseHandle(event)


if __name__ == '__main__':
    run()
