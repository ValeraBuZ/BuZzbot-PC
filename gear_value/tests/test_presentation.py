from datetime import date
import unittest

from gear_value.catalog import STAT_LABELS, GAME_STAT_LABELS
from gear_value.make_seed import stat, record
from gear_value.presentation import result_text, displayed_value, entered_value
from gear_value.recognition import LABELS
from gear_value.valuation import estimate, validate_item


def rpg():
    return record(100, 'Личный РПГ', 'tactical', 300, 3,
                  [('squad.attack', .9), ('squad.counter_reduction', 1.2)],
                  [('infantry.damage', 1.6, 'blue'), ('squad.load', 4.8, 'blue'),
                   ('infantry.attack', 2.4, 'purple')], level=1)


class PresentationTests(unittest.TestCase):
    def test_game_names_are_shared_by_ocr_and_all_display_surfaces(self):
        self.assertEqual(STAT_LABELS['infantry.damage'], 'УРН пехотного отряда')
        self.assertEqual(STAT_LABELS['infantry.attack'], 'АТК пехотного отряда')
        self.assertEqual(STAT_LABELS['squad.load'], 'Грузоподъемность отряда')
        for key, text in GAME_STAT_LABELS.items():
            self.assertEqual(LABELS[text], key)
            self.assertEqual(STAT_LABELS[key], text)
        self.assertEqual(len(set(STAT_LABELS.values())), len(STAT_LABELS))

    def test_reduction_sign_matches_card_but_preserves_stored_meaning(self):
        target = rpg()
        reduction = target['base_stats'][1]
        self.assertEqual(displayed_value(reduction), '-1.2')
        reduction['value'] = entered_value(reduction['key'], '-1.2')
        self.assertEqual(validate_item(target)['base_stats'][1]['value'], 1.2)
        self.assertEqual(entered_value('squad.attack', '-1.2'), '-1.2')
        self.assertEqual(displayed_value({'key':'infantry.reduction', 'value':2.3}), '2.3')
        self.assertEqual(displayed_value({'key':'infantry.counter_reduction', 'value':4.5}), '-4.5')

    def test_unknown_price_is_short_and_identifies_the_actual_combo(self):
        item = rpg()
        text = result_text(estimate(item, [], today=date(2026, 9, 27)), item)
        self.assertTrue(text.startswith('Цена пока неизвестна'))
        self.assertIn('УРН пехотного отряда 1.6%', text)
        self.assertIn('АТК пехотного отряда 2.4%', text)
        self.assertIn('Грузоподъемность отряда 4.8%', text)
        self.assertIn('По отдельным характеристикам', text)
        self.assertIn('Связка', text)
        self.assertNotIn('http', text)
        self.assertLess(len(text), 600)

    def test_ask_is_not_presented_as_completed_sale(self):
        item = rpg()
        text = result_text(estimate(item, [item], today=date(2026, 9, 27)), item)
        self.assertTrue(text.startswith('Продавцы просят: 300 G'))
        self.assertIn('Цена продажи пока не подтверждена.', text)
        self.assertNotIn('Ориентир:', text)

    def test_bid_is_not_presented_as_asking_or_sale_price(self):
        item = rpg()
        bid = {**item, 'status':'bid', 'price': 9999}
        text = result_text(estimate(item, [bid], today=date(2026, 9, 27)), item)
        self.assertTrue(text.startswith('В торгах указано: 9 999 G'))
        self.assertIn('Это ещё не цена продажи.', text)

    def test_real_mine_shows_useful_examples_for_every_roll(self):
        import json
        from pathlib import Path
        rows = json.loads((Path(__file__).parents[1] / 'seed.json').read_text(encoding='utf-8'))['records']
        target = record(0, 'Противотанковая мина', 'tactical', 1, 1,
                        [('infantry.skill_damage', 2), ('infantry.counter_reduction', 4.5)],
                        [('rider.defense', 1.6, 'blue'), ('infantry.reduction', 2.3, 'purple'),
                         ('infantry.attack', 4.8, 'gold')], level=20)
        result = estimate(target, rows, today=date(2026, 9, 27))
        text = result_text(result, target)
        self.assertIsNone(result['headline'])
        self.assertTrue(text.startswith('Цена готовой вещи пока неизвестна'))
        self.assertIn('Для переплавки · другая база', text)
        self.assertIn('База примера — с бонусами против зомби.', text)
        self.assertTrue(all(not c['references'] for c in result['market_signals']['criteria']))
        self.assertIn('Пример с 5.3%: продавец просит 200 G.', text)
        self.assertIn('Пример с 2.4%: продавец просит 300 G.', text)
        self.assertIn('Пример с 1.5%: в торгах указано 2 800 G.', text)
        self.assertIn('На той вещи ещё: СНИЖ УРН отряда стрелков 4.5%', text)
        self.assertIn('Цены строк не складываются', text)
        self.assertLess(len(text), 1400)

    def test_nearby_example_remains_visible_even_with_whole_item_price(self):
        target = rpg()
        other = rpg(); other.update(id='other', price=700, base_stats=[])
        text = result_text(estimate(target, [target, other], today=date(2026, 9, 27)), target)
        self.assertTrue(text.startswith('Продавцы просят: 300 G'))
        self.assertIn('По отдельным характеристикам', text)
        self.assertIn('Пример с', text)


if __name__ == '__main__':
    unittest.main()
