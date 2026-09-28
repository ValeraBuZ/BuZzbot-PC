"""Conservative comparable pricing: never turn gameplay scores into gold."""
from __future__ import annotations

from collections import Counter
from datetime import date
from math import isfinite
from statistics import median
import unicodedata

from gear_value.catalog import SLOTS, RARITIES, STAT_LABELS, STAT_COLORS, STATUSES


def number(value, label, low, high, integer=False):
    if isinstance(value, bool):
        raise ValueError(f'{label}: требуется число.')
    try:
        result = float(str(value).replace(',', '.').replace(' ', '').replace('\u00a0', ''))
    except (TypeError, ValueError):
        raise ValueError(f'{label}: требуется число.') from None
    if not isfinite(result) or not low <= result <= high or (integer and result != int(result)):
        raise ValueError(f'{label}: допустимо от {low} до {high}.')
    return int(result) if integer else result


def clean_text(value, label, limit=160, required=False):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f'{label}: некорректный текст (до {limit} символов).')
    value = value.strip()
    if required and not value:
        raise ValueError(f'Заполните поле «{label}».')
    return value


def normalize(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().replace('ё', 'е').split())


def validate_item(raw):
    if not isinstance(raw, dict):
        raise ValueError('Предмет должен быть объектом.')
    result = {}
    for field, allowed, label in [('slot', SLOTS, 'Тип'), ('rarity', RARITIES, 'Редкость')]:
        if raw.get(field) not in allowed:
            raise ValueError(f'{label}: выберите значение из списка.')
        result[field] = raw[field]
    result['name'] = clean_text(raw.get('name', ''), 'Название') or 'Без названия'
    result['market'] = clean_text(raw.get('market', ''), 'Рынок', required=True)
    result['trait'] = clean_text(raw.get('trait', ''), 'Особая метка')
    result['level'] = number(raw.get('level', 0), 'Усиление', 0, 20, True)
    attempts = raw.get('attempts')
    result['attempts'] = None if attempts in (None, '') else number(attempts, 'Попытки торговли', 0, 99, True)
    for field in ('stats', 'base_stats'):
        stats = raw.get(field, [])
        if not isinstance(stats, list) or not 0 <= len(stats) <= 8:
            raise ValueError('Допустимо до 8 характеристик каждого вида.')
        result[field] = []
        for stat in stats:
            if not isinstance(stat, dict) or stat.get('key') not in STAT_LABELS:
                raise ValueError('Неизвестная характеристика.')
            color = stat.get('color', 'unknown')
            if color not in STAT_COLORS:
                raise ValueError('Неизвестный цвет характеристики.')
            custom = clean_text(stat.get('custom', ''), 'Название характеристики', required=stat['key'] == 'custom')
            result[field].append({'key': stat['key'], 'value': number(stat.get('value'), 'Значение %', 0, 1000),
                                  'color': color, 'custom': custom})
    if not result['stats']:
        raise ValueError('Добавьте хотя бы одну особую характеристику.')
    return result


def stat_key(stat):
    return stat['key'], normalize(stat.get('custom', '')) if stat['key'] == 'custom' else ''


def stat_label(stat):
    return stat.get('custom') if stat['key'] == 'custom' else STAT_LABELS[stat['key']]


def validate_record(raw, today=None):
    today = today or date.today()
    item = validate_item(raw)
    if raw.get('status') not in STATUSES:
        raise ValueError('Укажите статус наблюдения.')
    item.update(status=raw['status'], price=number(raw.get('price'), 'Цена в золоте', 1, 1_000_000_000, True))
    try:
        observed = date.fromisoformat(raw.get('observed', ''))
    except (ValueError, TypeError):
        raise ValueError('Дата: используйте ГГГГ-ММ-ДД.') from None
    if observed > today:
        raise ValueError('Дата наблюдения не может быть в будущем.')
    item['observed'] = observed.isoformat()
    item['source'] = clean_text(raw.get('source', ''), 'Источник', 500, True)
    item['notes'] = clean_text(raw.get('notes', ''), 'Заметка', 2000)
    item['evidence'] = clean_text(raw.get('evidence', ''), 'Снимок', 160)
    item['id'] = clean_text(raw.get('id', ''), 'Идентификатор', 100)
    if item['status'] == 'sold' and raw.get('sale_confirmed') is not True:
        raise ValueError('Продажу нужно подтвердить по журналу торговли; исчезновение лота не считается продажей.')
    item['sale_confirmed'] = item['status'] == 'sold'
    return item


def compare_stats(left, right):
    """Match duplicates as separate rolls; compare every roll, including secondary ones."""
    if Counter(map(stat_key, left)) != Counter(map(stat_key, right)):
        return None
    gaps = []
    for key in set(map(stat_key, left)):
        a = sorted((s for s in left if stat_key(s) == key), key=lambda s: s['value'])
        b = sorted((s for s in right if stat_key(s) == key), key=lambda s: s['value'])
        for x, y in zip(a, b):
            # Relative tolerance is a matching rule, not a price multiplier.
            tolerance = max(0.15, max(x['value'], y['value']) * 0.12)
            delta = abs(x['value'] - y['value'])
            if delta > tolerance:
                return None
            if x['color'] != 'unknown' and y['color'] != 'unknown' and x['color'] != y['color']:
                return None
            # Keep known auction-entry bands separate.
            if x['key'].endswith(('.damage', '.reduction')) and (x['value'] >= 4.5) != (y['value'] >= 4.5):
                return None
            gaps.append(delta / tolerance)
    return sum(gaps) / len(gaps) if gaps else 0.0


def fingerprint(record, include_date=True):
    def signature(stats):
        return tuple(sorted((stat_key(s), s['value'], s['color']) for s in stats))
    return (normalize(record['market']), normalize(record['name']), record['slot'], record['rarity'],
            record['level'], record['attempts'], normalize(record['trait']), signature(record['stats']), signature(record['base_stats']),
            record['status'], record['price'], record['observed'] if include_date else '')


def base_relation(left, right):
    """Two base rolls are part of the item, never interchangeable with a special roll."""
    if len(left) != 2 or len(right) != 2:
        return 'missing'
    if Counter(map(stat_key, left)) != Counter(map(stat_key, right)):
        return 'different'
    return 'close' if compare_stats(left, right) is not None else 'values'


def price_summary(rows):
    if not rows:
        return None
    values = sorted(r['price'] for r in rows)
    return {'median': round(median(values)), 'low': values[0], 'high': values[-1], 'count': len(values)}


def demand_context(item):
    """Qualitative source context only. Never maps a stat or forum quote to gold."""
    relevant = [s for s in item['stats'] if s['key'].split('.')[0] in ('infantry', 'rider', 'ranged')
                and s['key'].endswith(('.damage', '.reduction'))]
    if relevant:
        labels = '; '.join(f'{stat_label(s)} {s["value"]:g}%' for s in relevant)
        summary = f'Есть характеристики, для которых игроки описывают спрос, включая покупки ради переплавки: {labels}. Конкретная цена и факт покупки по этому сообщению не определяются.'
    else:
        summary = 'Форумные сообщения о дорогих строках урона и снижения урона не дают цены этому набору. Для оценки нужны сделки с похожими характеристиками, усилением и меткой.'
    return {'summary': summary,
            'source': 'Обсуждение спроса и переплавки · Reddit',
            'url': 'https://www.reddit.com/r/DoomsdayLastSurvivors/comments/1w55p5l/troop_equipments/',
            'limitation': 'Качественная подсказка по спросу. Форумные суммы не участвуют в расчёте и не подтверждают цену объявления.'}


def estimate(item, records, *, today=None, max_age=30, exclude_id=None):
    today = today or date.today()
    max_age = number(max_age, 'Период сравнения', 1, 365, True)
    item = validate_item(item)
    matches, related, seen = [], [], set()
    excluded = {'stale': 0, 'market': 0, 'duplicate': 0}
    for record in sorted(records, key=lambda r: r['observed'], reverse=True):
        if record['id'] == exclude_id:
            continue
        age = (today - date.fromisoformat(record['observed'])).days
        if age < 0 or age > max_age:
            excluded['stale'] += 1
            continue
        if normalize(record['market']) != normalize(item['market']):
            excluded['market'] += 1
            continue
        identity = fingerprint(record, include_date=False)
        if identity in seen:
            excluded['duplicate'] += 1
            continue
        seen.add(identity)
        if record['slot'] != item['slot'] or record['rarity'] != item['rarity']:
            continue
        gap = compare_stats(item['stats'], record['stats'])
        base_gap = compare_stats(item['base_stats'], record['base_stats'])
        attempts_known = item['attempts'] is not None and record['attempts'] is not None
        strict = (record['level'] == item['level']
                  and normalize(record['trait']) == normalize(item['trait'])
                  and attempts_known and record['attempts'] == item['attempts'] and gap is not None
                  and base_relation(item['base_stats'], record['base_stats']) == 'close')
        if strict:
            matches.append({**record, 'similarity': round(100 - 15 * (gap + base_gap)), 'age': age})
        else:
            common = []
            for left in item['stats']:
                if any(stat_key(left) == stat_key(right) and compare_stats([left], [right]) is not None
                       for right in record['stats']):
                    common.append(stat_label(left))
            if common:
                related.append({**record, 'common': sorted(set(common)), 'age': age})
    matches.sort(key=lambda r: (-r['similarity'], r['age'], r['price']))
    groups = {key: [r for r in matches if r['status'] == key] for key in STATUSES}
    sold = price_summary(groups['sold'])
    asks = price_summary(groups['ask'])
    bids = price_summary(groups['bid'])
    basis = 'sold' if sold and sold['count'] >= 3 else ('ask' if asks else 'insufficient')
    headline = sold if basis == 'sold' else (asks if basis == 'ask' else None)
    confidence = 'Недостаточно данных'
    if basis == 'ask':
        confidence = 'Низкая: цены продавцов'
    elif basis == 'sold':
        confidence = 'Средняя: от 3 подтверждённых продаж'
        if sold['high'] > 2 * sold['low']:
            confidence = 'Низкая: большой разброс цен'
    warnings = []
    if basis != 'sold':
        warnings.append('Цена продажи не подтверждена: нужны хотя бы 3 сопоставимые завершённые сделки.')
    if asks and asks['count'] == 1:
        warnings.append('Найдено только одно сопоставимое предложение. Это цена одного продавца, не рыночный диапазон.')
    if item['attempts'] is None or len(item['base_stats']) != 2:
        warnings.append('Для точного сравнения заполните обе базовые характеристики и оставшиеся попытки торговли.')
    if item['attempts'] == 0:
        warnings.append('Указано 0 попыток торговли. Проверьте, допускается ли продажа этой вещи в игре.')
    if related:
        warnings.append('Совпадение одной характеристики показано отдельно: цену такого предмета нельзя переносить на всю вашу вещь.')
    if headline and headline['high'] > 2 * headline['low']:
        warnings.append('Цены близких лотов различаются более чем вдвое; проверьте крайние значения по снимкам.')
    from gear_value.market_signals import analyze
    return {'basis': basis, 'headline': headline, 'confidence': confidence, 'sold': sold, 'asks': asks,
            'bids': bids, 'unsold_count': len(groups['unsold']), 'matches': matches,
            'related': sorted(related, key=lambda r: (r['age'], r['price']))[:30],
            'warnings': warnings, 'excluded': excluded, 'max_age': max_age,
            'demand_context': demand_context(item),
            'market_signals': analyze(item, records, today, max_age, exclude_id)}
