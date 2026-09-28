"""Short, readable explanations of existing price comparisons. No pricing rules here."""
from gear_value.valuation import stat_label
from gear_value.catalog import STAT_COLORS


def money(value):
    return f'{value:,}'.replace(',', ' ') + ' G'


def displayed_value(stat):
    value = stat.get('value')
    if value is None:
        return ''
    sign = '-' if value and stat['key'].endswith(('.basic_reduction', '.skill_reduction', '.counter_reduction')) else ''
    return sign + f'{value:g}'


def entered_value(key, value):
    """Game damage reductions have a minus sign; the pricing model stores magnitude."""
    if key and key.endswith('reduction'):
        return value.strip().removeprefix('-').removeprefix('−')
    return value


def stat_text(stat):
    return f'{stat_label(stat)} {displayed_value(stat)}%'


def price_range(prices):
    if prices['low'] == prices['high']:
        return money(prices['low'])
    return f"{prices['low']:,}–{prices['high']:,} G".replace(',', ' ')


def select_observation(summary):
    sold = summary.get('sold')
    if sold and sold['count'] >= 3:
        return 'sold', sold
    if summary.get('ask'):
        return 'ask', summary['ask']
    if summary.get('bid'):
        return 'bid', summary['bid']
    return None, None


def reference_lines(reference, stat):
    row, matched = reference['record'], reference['stat']
    color = f" ({STAT_COLORS[matched['color']].lower()}, другой цвет)" if matched['color'] != stat['color'] else ''
    label = {'ask':'продавец просит', 'bid':'в торгах указано', 'sold':'продано за'}[row['status']]
    lines = [f"Пример с {displayed_value(matched)}%{color}: {label} {money(row['price'])}."]
    if reference['base_relation'] == 'values':
        lines.append('Типы базы совпадают, проценты другие: ' + '; '.join(stat_text(s) for s in row['base_stats']) + '.')
    elif reference['base_relation'] == 'missing':
        lines.append('База примера не прочитана полностью.')
    elif reference['zombie_base'] and reference['base_relation'] == 'different':
        lines.append('База примера — с бонусами против зомби.')
    if reference['factors']:
        lines.append('На той вещи ещё: ' + '; '.join(reference['factors']) + '.')
    return lines


def result_text(result, item):
    signals = result.get('market_signals', {})
    groups = signals.get('groups', [])
    criteria = signals.get('criteria', [])
    combos = [g for g in groups if g['mode'] == 'combo']
    status, prices = select_observation({'ask': result['asks'], 'bid': result['bids'], 'sold': result['sold']})
    scope = 'похожих вещей'
    if not prices:
        for group in combos:
            status, prices = select_observation(group['summary'])
            if prices:
                scope = 'похожих сочетаний'
                break
    lines = []
    if prices:
        if status == 'sold':
            lines += [f"Ориентир: {money(prices['median'])}", f"Продажи {scope}: {prices['count']}. Разброс: {price_range(prices)}."]
            if prices['high'] > 2 * prices['low']:
                lines.append('Уверенность низкая: большой разброс цен.')
        elif status == 'ask':
            lines += [f"Продавцы просят: {price_range(prices)}", f"Объявлений {scope}: {prices['count']}. Уверенность низкая.", 'Цена продажи пока не подтверждена.']
        else:
            lines += [f"В торгах указано: {price_range(prices)}", f"Лотов {scope}: {prices['count']}. Это ещё не цена продажи."]
    else:
        if any(c['references'] for c in criteria):
            lines += ['Есть сравнения по характеристикам', 'Для вещи целиком близких цен пока нет.']
        elif any(c['donor_references'] for c in criteria):
            lines += ['Цена готовой вещи пока неизвестна', 'Есть только сравнения по строкам с другой базой.']
        else:
            lines += ['Цена пока неизвестна', 'В базе нет достаточно похожих вещей.']
    if item['attempts'] == 0:
        lines.append('У вещи 0 попыток торговли — проверьте возможность продажи.')

    lines += ['', 'База и связка', 'База: ' + ('; '.join(stat_text(s) for s in item['base_stats']) or 'не заполнена')]
    if signals.get('base', {}).get('zombie_stats'):
        lines.append('В базе есть бонусы против зомби. Аналоги с другой базой исключены из цены готовой вещи.')
    if combos:
        lines.append('Связка: ' + ' + '.join(stat_text(s) for s in combos[0]['stats']))
    lines += ['', 'По отдельным характеристикам · с учётом базы']
    if any(c['references'] for c in criteria):
        for criterion in criteria:
            stat = criterion['stat']
            lines += ['', stat_text(stat)]
            status, observed = select_observation(criterion['summary'])
            if observed:
                label = {'ask':'продавцы просят', 'bid':'в торгах указано', 'sold':'продажи'}[status]
                lines.append(f"С близкой базой и строкой: {label} {price_range(observed)}. Лотов: {observed['count']}.")
            elif criterion['references']:
                lines.extend(reference_lines(criterion['references'][0], stat))
            else:
                lines.append('С такой базой примеров пока нет.')
    else:
        if not any(c['donor_references'] for c in criteria):
            lines.append('; '.join(stat_text(c['stat']) for c in criteria))
        lines.append('С такой базой и особыми строками примеров пока нет.')

    donors = [c for c in criteria if not c['references'] and c['donor_references']]
    if donors:
        lines += ['', 'Для переплавки · другая база', 'Только справочные примеры, не цена готовой вещи.']
        for criterion in donors:
            lines += ['', stat_text(criterion['stat'])]
            lines.extend(reference_lines(criterion['donor_references'][0], criterion['stat']))
    if any(c['references'] or c['donor_references'] for c in criteria):
        lines += ['', 'Цены строк не складываются. Объявления и торги не подтверждают продажу.']
    return '\n'.join(lines)
