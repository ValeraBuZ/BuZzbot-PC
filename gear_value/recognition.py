"""Local Windows OCR. Returns an editable draft, never a market observation."""
from __future__ import annotations

import asyncio
from collections import Counter
import colorsys
from difflib import SequenceMatcher
import io
import json
from pathlib import Path
import re
from statistics import median
import tempfile
import threading

from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError
from gear_value.catalog import GAME_STAT_LABELS

LOCK = threading.Lock()
MAX_BYTES = 15_000_000
MAX_PIXELS = 20_000_000
LABELS = {label: key for key, label in GAME_STAT_LABELS.items()}
for label in ['УРН базовой атаки на зомби', 'УРН от умений Зомби', 'Скорость сбора стали',
              'Скорость сбора нефти', 'Скорость сбора дерева', 'Скорость сбора еды']:
    LABELS[label] = 'custom'
TRAITS = ['Идеал', 'Удача', 'Простота', 'Изысканное', 'Ношеное', 'Яркость', 'Стрелки', 'Пехота', 'Всадники']


def normalized(text):
    return re.sub(r'[^а-яa-z0-9]', '', text.casefold().replace('ё', 'е').replace('0з', 'оз'))


def header(text):
    # The help icon next to a heading is sometimes read as a digit.
    key = re.sub(r'\d+$', '', normalized(text))
    return key if key in ('базовыехарактеристики', 'особыехарактеристики') else None


def percent(text):
    text = text.replace('0/0', '%').replace('О/О', '%').replace(',', '.')
    hits = re.findall(r'(?<![\d.])[-+−]?\s*(\d+(?:\s*\.\s*\d+)?)\s*%', text)
    if len(hits) != 1:
        return None
    value = float(hits[0].replace(' ', ''))
    return value if value <= 1000 else None


def enhancement_levels(rows):
    levels = []
    for row in rows:
        text = row['text'].strip()
        if re.fullmatch(r'\+\d{1,2}', text) or normalized(text).startswith('уровеньулучшения'):
            matches = re.findall(r'\+(\d{1,2})(?!\d)', text)
            if len(matches) == 1 and int(matches[0]) <= 20:
                levels.append(int(matches[0]))
    return levels


def decode_image(payload):
    if not payload or len(payload) > MAX_BYTES:
        raise ValueError('Выберите снимок до 15 МБ.')
    try:
        with Image.open(io.BytesIO(payload)) as image:
            if image.format not in ('PNG', 'JPEG', 'WEBP'):
                raise ValueError('Поддерживаются PNG, JPG и WebP.')
            if image.width * image.height > MAX_PIXELS or min(image.size) < 80:
                raise ValueError('Снимок должен быть не меньше 80 × 80 и не больше 20 мегапикселей.')
            image.load()
            image = ImageOps.exif_transpose(image).convert('RGB')
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError):
        raise ValueError('Не удалось открыть изображение. Выберите обычный PNG или JPG.') from None
    return image


def grouped_rows(lines, min_x=0):
    words = [w for line in lines for w in line['words'] if w['x'] >= min_x]
    groups = []
    for w in sorted(words, key=lambda w: w['y'] + w['h'] / 2):
        cy = w['y'] + w['h'] / 2
        if groups and abs(cy - median(v['y'] + v['h'] / 2 for v in groups[-1])) < max(9, w['h'] * .48):
            groups[-1].append(w)
        else:
            groups.append([w])
    result = []
    for group in groups:
        group.sort(key=lambda w: w['x'])
        result.append({'text': ' '.join(w['text'] for w in group), 'words': group,
                       'x': min(w['x'] for w in group), 'y': median(w['y'] + w['h'] / 2 for w in group),
                       'h': median(w['h'] for w in group)})
    return result


def match_label(text):
    # Exact label prefixes take precedence over fuzzy recognition.
    text = re.sub(r'^[О0][З3]\s+', 'ОЗ ', text.lstrip('• '))
    plain = re.sub(r'[-+−]?\d.*$', '', text).strip()
    key = normalized(plain)
    # Never silently drop a troop qualifier and turn a troop-only bonus into a squad bonus.
    qualifier = re.search(r'\(([^)]+)\)', plain)
    candidates = [label for label in LABELS if not qualifier or
                  ('(' in label and normalized(qualifier[1]) == normalized(label.split('(')[1]))]
    candidates.sort(key=lambda t: SequenceMatcher(None, key, normalized(t)).ratio(), reverse=True)
    if candidates and SequenceMatcher(None, key, normalized(candidates[0])).ratio() >= .88:
        return candidates[0]
    return None


def text_color(image, row, edge):
    box = (max(0, int(row['x'])), max(0, int(row['y'] - row['h'] / 2)),
           min(image.width, int(edge)), min(image.height, int(row['y'] + row['h'] / 2)))
    colors = []
    for r, g, b in image.crop(box).getdata():
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s > .30 and v > .52:
            h *= 180
            colors.append('red' if h < 10 else 'gold' if h < 35 else 'green' if h < 85
                          else 'blue' if h < 120 else 'purple' if h < 170 else 'red')
    return Counter(colors).most_common(1)[0][0] if colors else 'unknown'


def golden_banner(image, title_row):
    """Only infer the compact card's gold rarity from a large colored background."""
    h = title_row['h']
    box = (max(0, int(title_row['x'])), max(0, int(title_row['y'] - h)),
           image.width, min(image.height, int(title_row['y'] + h * 2.5)))
    patch = image.crop(box)
    if not patch.width or not patch.height:
        return False
    patch.thumbnail((120, 60))
    golden = 0
    for r, g, b in patch.getdata():
        hue, saturation, value = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if 10 <= hue * 180 < 35 and saturation > .45 and value > .3:
            golden += 1
    return golden / (patch.width * patch.height) > .55


def title_candidates(top):
    """Read wrapped titles while keeping the power line and lock icon out of the name."""
    for index, row in enumerate(top):
        raw = row['text'].strip()
        prefix = re.match(r'^\+\s*(\d{1,2})(?:\s+|$)', raw)
        title = raw[prefix.end():] if prefix else raw
        level = int(prefix[1]) if prefix and int(prefix[1]) <= 20 else None
        # Windows OCR can read the lock at the end of the title as a single letter.
        variants = {title, re.sub(r'\s+[а-яa-z]$', '', title, flags=re.I)}
        for text in variants:
            yield row, text, level
        if index + 1 < len(top):
            next_row = top[index + 1]
            height = max(row['h'], next_row['h'])
            if (0 < next_row['y'] - row['y'] < height * 2.1
                    and abs(next_row['x'] - row['x']) < height * 1.5
                    and not re.search(r'[:\d+]', next_row['text'])):
                for text in variants:
                    yield row, text + ' ' + next_row['text'], level


def parse_card(lines, image, models):
    rows = grouped_rows(lines)
    headers = [r for r in rows if header(r['text'])]
    if not headers:
        raise ValueError('Карточка вещи не найдена. Откройте её целиком, чтобы были видны название и характеристики, и сделайте снимок.')
    left = min(r['x'] for r in headers)
    rows = grouped_rows(lines, left - 30)
    base_y = next((r['y'] for r in rows if header(r['text']) == 'базовыехарактеристики'), None)
    special_y = next((r['y'] for r in rows if header(r['text']) == 'особыехарактеристики'), None)
    if special_y is None:
        raise ValueError('На снимке не видно раздела особых характеристик. Сделайте снимок полной карточки.')
    attempts_row = next((r for r in rows if 'попыткиторговли' in normalized(r['text'])), None)
    end_y = attempts_row['y'] if attempts_row else image.height
    item = dict(name='', slot='', rarity='', level=None, attempts=None, trait='', base_stats=[], stats=[], market='Текущий аукцион')
    warnings = []
    title_levels, title_row = [], None
    top = [r for r in rows if r['y'] < min(y for y in (base_y, special_y) if y is not None)]
    for row, title, level in title_candidates(top):
        text = normalized(title)
        if level is not None:
            title_levels.append(level)
            title_row = title_row or row
        for name, slot in models.items():
            variants = {normalized(name), normalized(name).replace('p', 'р').replace('x', 'х').replace('m', 'м')}
            if normalized(name) == 'p90':
                variants.update(('р9о', 'p9o'))
            if name == 'Барретт':
                variants.add('барреп')
            if text in variants:
                item.update(name=name, slot=slot)
                title_row = row
    for row in top:
        text = normalized(row['text'])
        for key, ru in [('legendary', 'легендарный'), ('elite', 'элитный'), ('uncommon', 'необычный'), ('common', 'обычный')]:
            if ru in text:
                item['rarity'] = key
                break
        for trait in TRAITS:
            if normalized(re.sub(r'^[IiIl1|]\s+', '', row['text'])) == normalized(trait):
                item['trait'] = trait
    if attempts_row:
        m = re.search(r'торговли\s*:\s*([0-9З]+)', attempts_row['text'], re.I)
        if m:
            item['attempts'] = int(m[1].replace('З', '3'))
    heights = [r['h'] for r in rows if special_y < r['y'] < end_y]
    height = median(heights) if heights else 30
    endpoints = [w['x'] + w['w'] for r in rows if (base_y or special_y) < r['y'] < end_y
                 for w in r['words'] if '%' in w['text'] or '0/0' in w['text']]
    edge = median(endpoints) if endpoints else image.width - height
    recognized = []
    for row in rows:
        if not (min(y for y in (base_y, special_y) if y is not None) < row['y'] < end_y):
            continue
        label = match_label(row['text'])
        if not label:
            continue
        field = 'stats' if row['y'] > special_y else 'base_stats'
        stat = {'key': LABELS[label], 'custom': label if LABELS[label] == 'custom' else '',
                'value': percent(row['text']), 'color': text_color(image, row, edge) if field == 'stats' else 'unknown'}
        item[field].append(stat)
        recognized.append((row, stat))
    if not item['stats']:
        raise ValueError('Не удалось прочитать особые характеристики. Нужен более чёткий снимок открытой карточки на русском языке.')
    # Only explicit +N labels count as enhancement. Missing or cropped labels stay unknown.
    levels = enhancement_levels(top) + title_levels
    if len(set(levels)) == 1:
        item['level'] = levels[0]
    if not item['rarity'] and title_row and len(item['stats']) == 3 and golden_banner(image, title_row):
        item['rarity'] = 'legendary'
        warnings.append('Редкость «Легендарный» определена по золотому фону карточки; проверьте её.')
    return item, warnings, recognized, edge, height


def numeric_strip(image, recognized, edge, height):
    """Keep isolated percentages on the same baseline and close to contextual text."""
    sheet = Image.new('RGB', (500, 100 * len(recognized)), 'white')
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(str(Path(__import__('os').environ.get('WINDIR', 'C:/Windows')) / 'Fonts/arial.ttf'), 32)
    for i, (row, _) in enumerate(recognized):
        h = max(height, row['h'])
        box = (max(0, int(edge - 5.5 * h)), max(0, int(row['y'] - h * .7)),
               min(image.width, int(edge + h * .35)), min(image.height, int(row['y'] + h * .7)))
        crop = image.crop(box).convert('L').point(lambda x: 0 if x > 120 else 255)
        ink = ImageOps.invert(crop).getbbox()
        if ink:
            crop = crop.crop(ink)
            crop = crop.resize((max(1, round(crop.width * 30 / crop.height)), 30), Image.Resampling.LANCZOS)
            crop.thumbnail((250, 30))
        else:
            crop = Image.new('L', (1, 30), 255)
        center = i * 100 + 50
        sheet.paste(crop, (105, center - crop.height // 2))
        for x, text in [(10, 'Value'), (115 + crop.width, 'end')]:
            bounds = draw.textbbox((0, 0), text, font=font)
            draw.text((x, center - (bounds[1] + bounds[3]) / 2), text, fill='black', font=font)
    return sheet


async def read_ocr(image, engine, directory, index):
    from winrt.windows.storage import StorageFile, FileAccessMode
    from winrt.windows.graphics.imaging import BitmapDecoder
    path = directory / f'ocr-{index}.png'
    image.save(path)
    file = await StorageFile.get_file_from_path_async(str(path))
    stream = await file.open_async(FileAccessMode.READ)
    bitmap = None
    try:
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        result = await engine.recognize_async(bitmap)
        return [{'text': line.text, 'words': [{'text': w.text, 'x': w.bounding_rect.x, 'y': w.bounding_rect.y,
                                             'w': w.bounding_rect.width, 'h': w.bounding_rect.height} for w in line.words]}
                for line in result.lines]
    finally:
        if bitmap is not None:
            bitmap.close()
        stream.close()


async def recognize(image, models, directory):
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.globalization import Language
    engine = OcrEngine.try_create_from_language(Language('ru-RU'))
    if engine is None:
        raise ValueError('Для распознавания нужен русский язык распознавания текста Windows. Его можно добавить в параметрах языка Windows.')
    working = image.copy()
    working.thumbnail((2600, 2600))
    if max(working.size) < 1400:
        working = working.resize((working.width * 2, working.height * 2))
    lines = await read_ocr(working, engine, directory, 0)
    full_rows = grouped_rows(lines)
    market_image = working
    # Inventory grids contain other items' +N badges; only a labelled auction field
    # outside the selected card can provide a fallback enhancement level.
    levels = enhancement_levels([r for r in full_rows if normalized(r['text']).startswith('уровеньулучшения')])
    anchors = [r for r in full_rows if header(r['text'])]
    if anchors and min(r['x'] for r in anchors) > working.width * .25:
        # Read the card separately from the game UI; use text anchors, not a fixed screen size.
        working = working.crop((max(0, int(min(r['x'] for r in anchors) - 45)), 0, working.width, working.height))
        lines = await read_ocr(working, engine, directory, 'card')
    item, warnings, recognized, edge, height = parse_card(lines, working, models)
    if item['level'] is None and len(set(levels)) == 1:
        item['level'] = levels[0]
    for row, stat in recognized:
        # Preserve a clearly read original percentage when the focused pass misses it.
        original = [r for r in full_rows if abs(r['y'] - row['y']) < max(12, row['h'] / 2)
                    and match_label(r['text']) == match_label(row['text'])]
        values = {percent(r['text']) for r in original} - {None}
        if stat['value'] is None and len(values) == 1:
            stat['value'] = values.pop()
    # A labelled strip gives Windows OCR enough context to read short percentages.
    english = OcrEngine.try_create_from_language(Language('en-US')) or engine
    sheet = numeric_strip(working, recognized, edge, height)
    numeric_lines = await read_ocr(sheet, english, directory, 1)
    numeric_rows = grouped_rows(numeric_lines)
    for i, (row, stat) in enumerate(recognized):
        text = ' '.join(r['text'] for r in numeric_rows if i * 100 <= r['y'] < (i + 1) * 100)
        value = percent(text)
        if value is None:
            body = re.sub(r'\s+', '', re.sub(r'\b(Value|end)\b', '', text, flags=re.I)).replace(',', '.')
            if re.fullmatch(r'[-+−]?\d+(?:\.\d+)?', body):
                candidate = abs(float(body.replace('−', '-')))
                if candidate <= 1000:
                    value = candidate
        if value is not None:
            if stat['value'] is not None and abs(stat['value'] - value) > .001:
                warnings.append(f'Перепроверьте число в строке «{row["text"]}»: распознавание расходится.')
                stat['value'] = None
            else:
                stat['value'] = value
        if stat['value'] is None:
            warnings.append(f'Впишите число: {row["text"]}.')
    for field, label in [('slot', 'категорию'), ('rarity', 'редкость'), ('level', 'усиление'), ('attempts', 'попытки торговли')]:
        if item[field] in (None, ''):
            warnings.append(f'Проверьте и укажите {label}.')
    expected = 3 if item['rarity'] == 'legendary' else 1 if item['rarity'] == 'elite' else None
    if expected is not None and len(item['stats']) != expected:
        warnings.append('Прочитаны не все особые характеристики. Сверьте количество строк со снимком.')
    if len(item['base_stats']) != 2:
        warnings.append('Базовые характеристики прочитаны не полностью.')
    from gear_value.auction_ocr import read_observation
    observation = await read_observation(market_image, full_rows, english, directory)
    return {'item': item, 'warnings': warnings, 'auction': observation,
            'raw_text': '\n'.join(r['text'] for r in full_rows),
            'message': 'Проверьте заполненные поля по снимку, затем нажмите «Рассчитать стоимость».'}


def recognize_upload(payload, folder, models, *, save_image=True):
    if not LOCK.acquire(blocking=False):
        raise ValueError('Предыдущий снимок ещё распознаётся. Подождите несколько секунд.')
    try:
        image = decode_image(payload)
        try:
            from winrt.runtime import init_apartment, uninit_apartment, ApartmentType
            init_apartment(ApartmentType.MULTI_THREADED)
        except ImportError:
            raise ValueError('В этой сборке нет распознавания. Запустите обновлённый DoomsdayGearValue.exe.') from None
        try:
            with tempfile.TemporaryDirectory(prefix='gear-ocr-') as temporary:
                result = asyncio.run(asyncio.wait_for(recognize(image, models, Path(temporary)), timeout=50))
        except TimeoutError:
            raise ValueError('Распознавание заняло слишком долго. Попробуйте снимок только карточки вещи.') from None
        finally:
            uninit_apartment()
        result['evidence'] = ''
        if save_image:
            folder = Path(folder)
            folder.mkdir(exist_ok=True)
            from uuid import uuid4
            name = 'pasted-' + uuid4().hex + '.png'
            image.save(folder / name)
            result['evidence'] = name
        return result
    finally:
        LOCK.release()
