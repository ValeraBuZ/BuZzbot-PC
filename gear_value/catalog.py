SLOTS = {'firearm': 'Оружие', 'tactical': 'Устройство',
         'vest': 'Жилет', 'mask': 'Шлем'}
RARITIES = {'legendary': 'Легендарный', 'elite': 'Элитный', 'uncommon': 'Необычный', 'common': 'Обычный'}
STAT_KINDS = {
    'damage': 'Наносимый урон', 'reduction': 'Снижение урона',
    'attack': 'Атака', 'defense': 'Защита', 'health': 'Здоровье',
    'skill_damage': 'Урон навыка', 'skill_reduction': 'Снижение урона навыка',
    'basic_damage': 'Урон базовой атаки', 'basic_reduction': 'Снижение урона базовой атаки',
    'counter_damage': 'Урон контратаки', 'counter_reduction': 'Снижение урона контратаки',
    'speed': 'Скорость передвижения', 'gathering': 'Скорость сбора',
    'resource_bonus': 'Бонус ресурсов', 'load': 'Грузоподъёмность',
    'zombie_damage': 'Урон по зомби', 'zombie_exp': 'Опыт за зомби',
}
TROOPS = {'squad': 'Отряд (общая)', 'infantry': 'Пехота', 'rider': 'Всадники',
          'ranged': 'Стрелки', 'engine': 'Транспорт'}
STAT_LABELS = {f'{troop}.{kind}': f'{label} · {name}'
               for troop, name in TROOPS.items() for kind, label in STAT_KINDS.items()}
# Labels transcribed from the Russian equipment cards. OCR and the interface share them.
GAME_STAT_LABELS = {
    'squad.attack': 'АТК отряда', 'squad.defense': 'ЗАЩ отряда', 'squad.health': 'ОЗ отряда',
    'squad.skill_damage': 'Нанесен. УРН навыка',
    'squad.skill_reduction': 'УРН от навыка, полученный войском',
    'squad.basic_damage': 'Базов. УРН атаки отряда',
    'squad.basic_reduction': 'УРН, полученный от базовой атаки',
    'squad.counter_damage': 'УРН контратаки отряда',
    'squad.counter_reduction': 'Полученный УРН контратаки',
    'squad.resource_bonus': 'Бонус за сбор', 'squad.gathering': 'Скорость сбора',
    'squad.load': 'Грузоподъемность отряда', 'squad.zombie_exp': 'Опыт убийства зомби',
    'squad.zombie_damage': 'УРН, наносимый зомби',
    'infantry.skill_damage': 'Нанесен. УРН навыка(Пехота)',
    'infantry.counter_reduction': 'Полученный УРН контратаки(Пехота)',
}
for ending, troop in [('отряда всадников', 'rider'), ('пехотного отряда', 'infantry'), ('стрелкового отряда', 'ranged')]:
    for prefix, kind in [('АТК', 'attack'), ('ЗАЩ', 'defense'), ('ОЗ', 'health')]:
        GAME_STAT_LABELS[troop + '.' + kind] = prefix + ' ' + ending
for ending, troop in [('отряда всадников', 'rider'), ('пехотного отряда', 'infantry'), ('отряда стрелков', 'ranged')]:
    for prefix, kind in [('УРН', 'damage'), ('СНИЖ УРН', 'reduction')]:
        GAME_STAT_LABELS[troop + '.' + kind] = prefix + ' ' + ending
STAT_LABELS = {**GAME_STAT_LABELS, **{key: label for key, label in STAT_LABELS.items() if key not in GAME_STAT_LABELS}}
STAT_LABELS['custom'] = 'Другая характеристика'
STAT_COLORS = {'green': 'Зелёный', 'blue': 'Синий', 'purple': 'Фиолетовый', 'gold': 'Золотой', 'red': 'Красный', 'unknown': 'Не указан'}
STATUSES = {'ask': 'Выставлено', 'bid': 'Текущая ставка', 'sold': 'Продано', 'unsold': 'Не продалось'}
