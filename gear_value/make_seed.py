"""Transcription of five inspected auction cards, 2026-09-26. Not a scraper."""
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent


def stat(key, value, color='unknown'):
    return {'key': key, 'value': value, 'color': color, 'custom': ''}


def record(index, name, slot, price, attempts, base, stats, level=0, trait=''):
    return {'id': f'live-20260926-{index:02}', 'name': name, 'slot': slot, 'rarity': 'legendary',
            'price': price, 'attempts': attempts, 'base_stats': [stat(*s) for s in base],
            'stats': [stat(*s) for s in stats], 'level': level, 'trait': trait,
            'market': 'Текущий аукцион', 'status': 'ask', 'observed': '2026-09-26',
            'source': 'Открытая карточка аукциона, LDPlayer, 26.09.2026',
            'notes': 'Цена продавца. Завершение продажи не проверено. Значения переписаны с изображения.',
            'evidence': f'lot{index:02}.png', 'sale_confirmed': False}


records = [
    record(1, 'P90', 'firearm', 299, 3,
           [('squad.attack', .8), ('squad.skill_damage', .5)],
           [('ranged.reduction', 2.5, 'purple'), ('squad.gathering', 14.2, 'gold'), ('rider.defense', 1.5, 'blue')]),
    record(2, 'Противотанковая мина', 'tactical', 250, 2,
           [('squad.skill_damage', .7), ('squad.counter_reduction', 1.7)],
           [('ranged.defense', 3.6, 'gold'), ('ranged.defense', 3.8, 'gold'), ('squad.zombie_damage', 6.7, 'purple')], level=5),
    record(3, 'Дрон-камикадзе', 'tactical', 200, 3,
           [('squad.basic_damage', 1.2), ('squad.skill_reduction', .5)],
           [('ranged.attack', 2, 'blue'), ('infantry.attack', 5.3, 'gold'), ('rider.attack', 2.3, 'blue')]),
    record(4, 'Утяжеленный бронежилет', 'vest', 999, 8,
           [('squad.defense', .8), ('squad.skill_reduction', .5)],
           [('rider.defense', 2.9, 'purple'), ('infantry.reduction', 2.5, 'purple'), ('rider.attack', 1.5, 'blue')], trait='Ношеное'),
    record(5, 'Осколочная граната', 'tactical', 200, 3,
           [('squad.attack', .8), ('squad.skill_reduction', .5)],
           [('ranged.defense', 3.5, 'purple'), ('infantry.attack', 1.9, 'blue'), ('rider.defense', 5.8, 'gold')]),
]

if __name__ == '__main__':
    (ROOT / 'seed.json').write_text(json.dumps({'schema_version': 1, 'records': records}, ensure_ascii=False, indent=2), encoding='utf-8')
    (ROOT / 'evidence').mkdir(exist_ok=True)
    for row in records:
        shutil.copy2(ROOT.parent / 'tmp' / 'gear_auction_research' / row['evidence'], ROOT / 'evidence' / row['evidence'])
