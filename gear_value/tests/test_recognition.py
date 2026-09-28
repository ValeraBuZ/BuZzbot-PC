import io
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from gear_value.recognition import decode_image, parse_card, percent, recognize_upload, enhancement_levels, match_label


def line(text, y):
    return {'text': text, 'words': [{'text': text, 'x': 20, 'y': y, 'w': 300, 'h': 20}]}


class RecognitionTests(unittest.TestCase):
    def test_wrapped_title_ignores_lock_and_does_not_need_model_to_read_level(self):
        lines = [line('+20 Противотанковая а', 10), line('мина', 40), line('Сила: 583,480', 80),
                 line('Базовые характеристики', 130), line('Нанесен. УРН навыка(Пехота) 2%', 165),
                 line('Полученный УРН контратаки(Пехота) -4.5%', 200),
                 line('Особые характеристики', 240), line('ЗАЩ отряда всадников 1.6%', 280),
                 line('СНИЖ УРН пехотного отряда 2.3%', 320), line('АТК пехотного отряда 4.8%', 360),
                 line('Попытки торговли: 1', 400)]
        item, *_ = parse_card(lines, Image.new('RGB', (600, 500)), {'Противотанковая мина': 'tactical'})
        self.assertEqual((item['name'], item['slot'], item['level']), ('Противотанковая мина', 'tactical', 20))
        self.assertEqual([s['key'] for s in item['base_stats']], ['infantry.skill_damage', 'infantry.counter_reduction'])
        unknown, *_ = parse_card(lines, Image.new('RGB', (600, 500)), {})
        self.assertEqual(unknown['level'], 20)
        self.assertEqual(unknown['slot'], '')

    def test_troop_qualifier_is_never_silently_changed_to_whole_squad(self):
        self.assertEqual(match_label('Полученный УРН контратаки(Пехота) -4.5%'),
                         'Полученный УРН контратаки(Пехота)')
        self.assertIsNone(match_label('Полученный УРН контратаки(Неизвестно) -4.5%'))

    @unittest.skipUnless(os.name == 'nt' and importlib.util.find_spec('winrt'), 'Windows OCR only')
    def test_real_full_inventory_mine_screenshot(self):
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.globalization import Language
        if not OcrEngine.is_language_supported(Language('ru-RU')):
            self.skipTest('Russian OCR language is not installed')
        payload = (Path(__file__).parent / 'assets' / 'inventory-mine.png').read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            result = recognize_upload(payload, Path(folder) / 'images', {'Противотанковая мина':'tactical'}, save_image=False)
            self.assertFalse((Path(folder) / 'images').exists())
        item = result['item']
        self.assertEqual((item['name'], item['slot'], item['rarity'], item['level'], item['attempts']),
                         ('Противотанковая мина', 'tactical', 'legendary', 20, 1))
        self.assertEqual([(s['key'], s['value']) for s in item['base_stats']],
                         [('infantry.skill_damage', 2), ('infantry.counter_reduction', 4.5)])
        self.assertEqual([(s['key'], s['value'], s['color']) for s in item['stats']],
                         [('rider.defense', 1.6, 'blue'), ('infantry.reduction', 2.3, 'purple'), ('infantry.attack', 4.8, 'gold')])
        self.assertIsNone(result['auction'])

    def test_enhancement_prefixed_title_and_missing_rarity_label(self):
        lines = [line('+1 Личный РПГ', 10), line('Базовые характеристики', 70),
                 line('АТК отряда 0.9%', 110), line('Полученный УРН контратаки -1.2%', 145),
                 line('Особые характеристики', 190), line('УРН пехотного отряда 1.6%', 230),
                 line('Грузоподъемность отряда 4.8%', 265), line('АТК пехотного отряда 2.4%', 300),
                 line('Попытки торговли: 3', 340)]
        item, *_ = parse_card(lines, Image.new('RGB', (600, 400)), {'Личный РПГ': 'tactical'})
        self.assertEqual((item['name'], item['slot'], item['level'], item['attempts']), ('Личный РПГ', 'tactical', 1, 3))
        # Three rows alone do not invent a rarity when no gold banner is visible.
        self.assertEqual(item['rarity'], '')
        self.assertEqual([s['value'] for s in item['base_stats']], [.9, 1.2])

    @unittest.skipUnless(os.name == 'nt' and importlib.util.find_spec('winrt'), 'Windows OCR only')
    def test_real_compact_rpg_screenshot_ocr(self):
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.globalization import Language
        if not OcrEngine.is_language_supported(Language('ru-RU')):
            self.skipTest('Russian OCR language is not installed')
        with tempfile.TemporaryDirectory() as folder:
            result = recognize_upload((Path(__file__).parent/'assets'/'compact-rpg.png').read_bytes(), folder, {'Личный РПГ': 'tactical'})
        item = result['item']
        self.assertEqual((item['name'], item['slot'], item['rarity'], item['level'], item['attempts']),
                         ('Личный РПГ', 'tactical', 'legendary', 1, 3))
        self.assertEqual([(s['key'], s['value']) for s in item['base_stats']],
                         [('squad.attack', .9), ('squad.counter_reduction', 1.2)])
        self.assertEqual([(s['key'], s['value'], s['color']) for s in item['stats']],
                         [('infantry.damage', 1.6, 'blue'), ('squad.load', 4.8, 'blue'), ('infantry.attack', 2.4, 'purple')])

    def test_enhancement_on_auction_hall_label_is_not_confused_with_stat_bonus(self):
        self.assertEqual(enhancement_levels([{'text': 'Уровень улучшения: +20'}]), [20])
        self.assertEqual(enhancement_levels([{'text': '+7'}]), [7])
        self.assertEqual(enhancement_levels([{'text': 'АТК отряда +20%'}]), [])

    def test_trait_description_is_not_a_section_heading_and_duplicate_rolls_survive(self):
        lines = [line('Экзоскелет', 10), line('Легендарный', 40), line('Идеал', 70),
                 line('Увеличивает все особые характеристики до лимита', 100),
                 line('Базовые характеристики 9', 140), line('ЗАЩ отряда 1.6%', 180),
                 line('Нанесен. УРН навыка 1.1%', 210), line('Особые характеристики', 250),
                 line('Базов. УРН атаки отряда 3.6%', 290), line('Базов. УРН атаки отряда 4.1%', 330),
                 line('АТК стрелкового отряда', 370), line('Попытки торговли: 4', 410)]
        item, *_ = parse_card(lines, Image.new('RGB', (600, 500)), {'Экзоскелет': 'vest'})
        self.assertEqual(len(item['base_stats']), 2)
        self.assertEqual([s['value'] for s in item['stats']], [3.6, 4.1, None])
        self.assertEqual(item['trait'], 'Идеал')
        self.assertIsNone(item['level'])

    def test_bad_image_rejected_and_jpeg_accepted(self):
        with self.assertRaises(ValueError): decode_image(b'not a screenshot')
        out = io.BytesIO(); Image.new('RGB', (200, 100)).save(out, 'JPEG')
        self.assertEqual(decode_image(out.getvalue()).size, (200, 100))
        with self.assertRaises(ValueError): decode_image(b'x' * 15_000_001)

    def test_missing_card_never_fills_a_fake_item(self):
        with self.assertRaises(ValueError):
            parse_card([line('Обычный экран игры', 20)], Image.new('RGB', (600, 500)), {})

    def test_percent_units_and_ambiguous_values(self):
        self.assertEqual(percent('-2%'), 2)
        self.assertEqual(percent('3,2%'), 3.2)
        self.assertEqual(percent('60/0'), 6)
        self.assertIsNone(percent('2% 3%'))
        self.assertIsNone(percent('Цена 20000'))


if __name__ == '__main__': unittest.main()
