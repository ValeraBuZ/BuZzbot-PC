"""Source-backed buying motives; observed prices, never invented gold weights."""
from collections import Counter
from datetime import date

from gear_value.catalog import TROOPS
from gear_value.valuation import normalize, stat_key, stat_label, fingerprint, price_summary, base_relation

SOURCES = {
    'single': {'title': 'Игроки о покупке одной строки для переплавки', 'url': 'https://www.reddit.com/r/DoomsdayLastSurvivors/comments/1w55p5l/troop_equipments/'},
    'smelting': {'title': 'Япония: одинаковые слот, редкость и тип показателя', 'url': 'https://doomsday-diary.com/アップデート（9月23日版）解説（第２回）/'},
    'combo': {'title': 'Япония: торговля парой DMG+/DMG− · 30.08.2026', 'url': 'https://note.com/modern_orca2742/n/n5b3c89dca11c'},
    'mixed': {'title': 'Японский форум: урон + атака/защита · 27.10.2025', 'url': 'https://n2ch.net/r/Ft0/gamesm/1759895819/1-?guid=ON&rc=886'},
}
TROOP_KEYS = {f'{troop}.{kind}' for troop in ('infantry', 'rider', 'ranged') for kind in ('attack', 'defense', 'damage', 'reduction')}
SUPPORTED = TROOP_KEYS | {'squad.attack', 'squad.defense'}
QUALITY = {'red': 5, 'gold': 4, 'purple': 3, 'blue': 2, 'green': 1, 'unknown': 0}


def is_damage(stat):
    return stat['key'] in TROOP_KEYS and stat['key'].endswith(('.damage', '.reduction'))


def patterns(item):
    """Keep duplicate rolls distinct and never pair different troop types."""
    found = []
    for troop in ('infantry', 'rider', 'ranged'):
        stats = [s for s in item['stats'] if s['key'] in SUPPORTED and s['key'].startswith(troop + '.')]
        damage = [s for s in stats if is_damage(s)]
        if len(damage) >= 2:
            found.append({'kind': 'double', 'troop': troop, 'stats': stats, 'title': f'Две строки урона / снижения · {TROOPS[troop]}', 'source': SOURCES['combo']})
        elif damage and len(stats) >= 2:
            found.append({'kind': 'mixed', 'troop': troop, 'stats': stats, 'title': f'Урон + атака / защита · {TROOPS[troop]}', 'source': SOURCES['mixed']})
    return found


def same_roll(left, right):
    if stat_key(left) != stat_key(right): return False
    if left['color'] == 'unknown' or right['color'] == 'unknown': return False
    if left['color'] != right['color']: return False
    if is_damage(left) and (left['value'] >= 4.5) != (right['value'] >= 4.5): return False
    # Small matching tolerance, not a price multiplier. Near maximum, tenths matter.
    return abs(left['value'] - right['value']) <= .100001


def match_rolls(left, right):
    if Counter(map(stat_key, left)) != Counter(map(stat_key, right)): return False
    for key in set(map(stat_key, left)):
        a = sorted((s for s in left if stat_key(s) == key), key=lambda s: s['value'])
        b = sorted((s for s in right if stat_key(s) == key), key=lambda s: s['value'])
        if not all(same_roll(x, y) for x, y in zip(a, b)): return False
    return True


def summary(rows):
    return {status: price_summary([r for r in rows if r['status'] == status]) for status in ('ask', 'bid', 'sold')}


def singles(item):
    return sorted((s for s in item['stats'] if s['key'] in SUPPORTED), key=lambda s: (is_damage(s), QUALITY[s['color']], s['value']), reverse=True)


def is_zombie(stat):
    return stat['key'].endswith(('.zombie_damage', '.zombie_exp')) or (
        stat['key'] == 'custom' and any(word in normalize(stat.get('custom', '')) for word in ('зомби', 'zombie')))


def base_context(item):
    base = item['base_stats']
    zombies = [stat for stat in base if is_zombie(stat)]
    return {'stats': base, 'complete': len(base) == 2, 'zombie_stats': zombies}


def criterion_references(item, stat, pool):
    """Keep useful observed listings visible without attributing their whole price to one roll."""
    references = []
    for row in pool:
        candidates = [s for s in row['stats'] if stat_key(s) == stat_key(stat)]
        if not candidates:
            continue
        matched = min(candidates, key=lambda s: (s['color'] != stat['color'], abs(s['value'] - stat['value'])))
        factors = []
        if len(candidates) > 1:
            factors.append('эта характеристика повторяется')
        if row['trait']:
            factors.append(f'метка «{row["trait"]}»')
        combinations = patterns(row)
        for pattern in combinations:
            factors.append('связка: ' + ' + '.join(f'{stat_label(s)} {s["value"]:g}%' for s in pattern['stats']))
        if not combinations:
            for other in singles(row):
                if stat_key(other) != stat_key(stat) and other['color'] in ('gold', 'red'):
                    factors.append(f'{stat_label(other)} {other["value"]:g}%')
        references.append({'record': row, 'stat': matched, 'factors': factors,
                           'base_relation': base_relation(item['base_stats'], row['base_stats']),
                           'zombie_base': any(is_zombie(s) for s in row['base_stats'])})
    # Prefer the same color and listings without an obvious separate premium.
    # Values outside the strict matching tolerance remain examples, never a price estimate.
    references.sort(key=lambda ref: ({'close':0, 'values':1, 'different':2, 'missing':3}[ref['base_relation']],
                                    ref['stat']['color'] != stat['color'], bool(ref['factors']),
                                    abs(ref['stat']['value'] - stat['value']), -date.fromisoformat(ref['record']['observed']).toordinal(),
                                    ref['record']['id']))
    return references


def analyze(item, records, today, max_age, exclude_id=None):
    pool, seen = [], set()
    for row in sorted(records, key=lambda r: r['observed'], reverse=True):
        if row['id'] == exclude_id or row['status'] not in ('ask', 'bid', 'sold') or row['attempts'] == 0: continue
        if not 0 <= (today - date.fromisoformat(row['observed'])).days <= max_age: continue
        if normalize(row['market']) != normalize(item['market']) or row['slot'] != item['slot'] or row['rarity'] != item['rarity']: continue
        identity = fingerprint(row, include_date=False)
        if identity in seen: continue
        seen.add(identity); pool.append(row)
    groups, notes = [], []
    combo_patterns = patterns(item)
    if combo_patterns:
        notes.append('Есть связка, спрос на которую описывают игроки. Её потенциал зависит от значений и основы. Проверьте цену целой вещи, прежде чем оценивать её только как материал для одной строки.')
    for pattern in combo_patterns:
        close, context = [], []
        signature = Counter(map(stat_key, pattern['stats']))
        for row in pool:
            candidates = [p for p in patterns(row) if p['troop'] == pattern['troop'] and Counter(map(stat_key, p['stats'])) == signature]
            if not candidates: continue
            same_values = match_rolls(pattern['stats'], candidates[0]['stats'])
            same_base = (row['level'] == item['level']
                         and normalize(row['trait']) == normalize(item['trait']) and item['attempts'] is not None and row['attempts'] == item['attempts']
                         and base_relation(item['base_stats'], row['base_stats']) == 'close')
            # Another high combat roll can carry its own premium, even for a different troop.
            extra_item = [s for s in singles(item) if s not in pattern['stats'] and s['color'] in ('gold', 'red')]
            extra_row = [s for s in singles(row) if s not in candidates[0]['stats'] and s['color'] in ('gold', 'red')]
            if same_values and same_base and match_rolls(extra_item, extra_row): close.append(row)
            else: context.append(row)
        groups.append({'mode': 'combo', 'title': pattern['title'], 'stats': pattern['stats'], 'base_stats': item['base_stats'], 'summary': summary(close),
                       'matches': close, 'context': sorted(context, key=lambda r: r['price'])[:10], 'source': pattern['source'],
                       'explanation': 'Сравниваются связки внутри одной категории. Название вещи не влияет на отбор. Для близких цен сохранены усиление, базовые характеристики, метка, попытки торговли и значения главных строк; фоновые строки могут отличаться.'})
    seen_stats = set()
    for stat in singles(item):
        identity = (stat_key(stat), stat['value'], stat['color'])
        if identity in seen_stats: continue
        seen_stats.add(identity)
        close, context = [], []
        for row in pool:
            # Valuable combinations and unique labels carry their own premiums.
            if patterns(row) or row['trait']: continue
            candidates = [s for s in row['stats'] if stat_key(s) == stat_key(stat)]
            if len(candidates) != 1: continue
            strong = [s for s in singles(row) if s['color'] in ('gold', 'red')]
            if any(stat_key(s) != stat_key(stat) for s in strong): continue
            if same_roll(stat, candidates[0]): close.append(row)
            else: context.append(row)
        context.sort(key=lambda r: min(abs(s['value'] - stat['value']) for s in r['stats'] if stat_key(s) == stat_key(stat)))
        groups.append({'mode': 'single', 'title': f'Одна строка: {stat_label(stat)} {stat["value"]:g}%', 'stats': [stat],
                       'summary': summary(close), 'matches': close, 'context': context[:10],
                       'source': SOURCES['single'] if is_damage(stat) else SOURCES['smelting'],
                       'explanation': 'Подборка возможных доноров: одинаковые слот, редкость, показатель, цвет и близкое значение (±0,1 п.п.). Модель и фоновые характеристики могут отличаться; связки и вещи с особыми метками исключены. Это цены целых предметов, не цена одного процента.'})
    if any(s['color'] in ('gold', 'red') and s['key'] not in SUPPORTED for s in item['stats']):
        notes.append('Золотой или красный цвет сам по себе не доказывает дороговизну. Для сбора, грузоподъёмности и зомби в прочитанных обсуждениях не подтверждён такой же спрос, как на боевые показатели.')
    if item['trait']:
        notes.append(f'Метка «{item["trait"]}» сохранена в сравнении связки; автоматическая наценка за неё не назначается без аналогов.')
    if any(s['key'] in ('squad.attack', 'squad.defense') for s in item['stats']):
        notes.append('Общая атака и защита показаны в подборках по одной строке. Надёжного текущего тарифа или доказательства особой наценки за них в изученных обсуждениях нет.')
    if not groups:
        notes.append('В этом наборе нет показателей, для которых в прочитанных обсуждениях найдено подтверждение повышенного спроса. Это не означает, что предмет ничего не стоит.')
    notes.append('Строки и связки — разные причины покупки. Их цены не складываются. Разброс показанных ставок не является диапазоном завершённых продаж.')
    criteria = []
    for stat in item['stats']:
        single = next((g for g in groups if g['mode'] == 'single' and g['stats'][0] == stat), None)
        references = criterion_references(item, stat, pool)
        close = [r for r in single['matches'] if base_relation(item['base_stats'], r['base_stats']) == 'close'] if single else []
        criteria.append({'stat': stat, 'summary': summary(close),
                         'references': [r for r in references if r['base_relation'] in ('close', 'values')][:10],
                         'donor_summary': single['summary'] if single else summary([]),
                         'donor_references': [r for r in references if r['base_relation'] in ('different', 'missing')][:10]})
    notes.insert(0, 'База и особые характеристики оцениваются вместе. Совпадение одной особой строки при другой базе используется только как справка для переплавки, не как цена готовой вещи.')
    return {'groups': groups, 'criteria': criteria, 'base': base_context(item), 'notes': notes, 'sources': list(SOURCES.values())}
