import copy
from datetime import date
import unittest

from gear_value.make_seed import records, stat
from gear_value.valuation import estimate, validate_record


TODAY = date(2026, 9, 27)


def item(**changes):
    row = copy.deepcopy(records[0])
    row.update(stats=[stat('ranged.damage', 4.5, 'gold'), stat('squad.load', 10, 'gold'),
                      stat('infantry.defense', .5, 'green')], **changes)
    return validate_record(row, TODAY)


def groups(target, rows, **kwargs):
    return estimate(target, rows, today=TODAY, **kwargs)['market_signals']['groups']


class BuyingMotiveTests(unittest.TestCase):
    def test_one_valuable_roll_ignores_model_and_economy_background(self):
        target = item()
        donor = item(name='Другая модель', level=20, attempts=1, price=4000)
        donor['stats'][1] = stat('squad.gathering', 8, 'blue')
        result = estimate(target, [donor], today=TODAY)
        self.assertIsNone(result['headline'])
        self.assertEqual(result['market_signals']['groups'][0]['summary']['ask']['median'], 4000)

    def test_single_roll_does_not_inherit_combo_or_other_gold_combat_price(self):
        combo = item(id='combo', price=90000)
        combo['stats'][1] = stat('ranged.reduction', 4.5, 'gold')
        other = item(id='other', price=70000)
        other['stats'][1] = stat('infantry.attack', 5.5, 'gold')
        marked = item(id='marked', price=99000, trait='Идеал')
        self.assertIsNone(groups(item(), [combo, other, marked])[0]['summary']['ask'])

    def test_color_and_auction_threshold_are_separate_price_bands(self):
        target = item()
        below = item(id='below'); below['stats'][0]['value'] = 4.4
        other_color = item(id='color'); other_color['stats'][0]['color'] = 'purple'
        unknown = item(id='unknown'); unknown['stats'][0]['color'] = 'unknown'
        result = groups(target, [below, other_color, unknown])[0]
        self.assertIsNone(result['summary']['ask'])
        self.assertEqual(len(result['context']), 3)

    def test_statuses_stay_separate_and_self_duplicates_filtered(self):
        a = item(id='a', price=4000)
        duplicate = item(id='duplicate', price=4000, observed='2026-09-25')
        b = item(id='b', price=9000, status='bid')
        c = item(id='c', price=3000, status='sold', sale_confirmed=True)
        result = groups(item(), [a, duplicate, b, c, item(id='self')], exclude_id='self')[0]
        self.assertEqual(result['summary']['ask']['count'], 1)
        self.assertEqual(result['summary']['bid']['median'], 9000)
        self.assertEqual(result['summary']['sold']['median'], 3000)

    def test_no_cross_slot_rarity_market_old_or_nontradeable_donor(self):
        bad = [item(id='slot', slot='vest'), item(id='rarity', rarity='elite'),
               item(id='market', market='Другой'), item(id='old', observed='2025-09-26'),
               item(id='zero', attempts=0), item(id='unsold', status='unsold')]
        result = groups(item(), bad)[0]
        self.assertEqual(result['matches'], [])
        self.assertEqual(result['context'], [])

    def test_combo_compares_as_whole_and_allows_economy_background_difference(self):
        target = item()
        target['stats'][1] = stat('ranged.reduction', 4.5, 'gold')
        candidate = copy.deepcopy(target); candidate['id'] = 'pair'; candidate['price'] = 50000
        candidate['stats'][2] = stat('squad.load', 7, 'blue')
        result = groups(target, [candidate])
        self.assertEqual(result[0]['mode'], 'combo')
        self.assertEqual(result[0]['summary']['ask']['median'], 50000)
        self.assertTrue(all(g['summary']['ask'] is None for g in result[1:]))

    def test_combo_preserves_base_trade_count_and_other_valuable_rolls(self):
        target = item(); target['stats'][1] = stat('ranged.reduction', 4.5, 'gold')
        for field, value in [('level', 10), ('attempts', None), ('trait', 'Идеал'), ('base_stats', [])]:
            with self.subTest(field=field):
                other = copy.deepcopy(target); other[field] = value
                result = groups(target, [other])[0]
                self.assertIsNone(result['summary']['ask'])
                self.assertEqual(len(result['context']), 1)
        other = copy.deepcopy(target); other['stats'][2] = stat('infantry.attack', 5.5, 'gold')
        self.assertIsNone(groups(target, [other])[0]['summary']['ask'])

    def test_combo_accepts_different_names_within_same_category(self):
        target = item(); target['stats'][1] = stat('ranged.reduction', 4.5, 'gold')
        other = copy.deepcopy(target); other.update(name='Другое оружие', price=45000)
        self.assertEqual(groups(target, [other])[0]['summary']['ask']['median'], 45000)

    def test_different_troop_lines_are_not_a_supported_combo(self):
        target = item(); target['stats'][1] = stat('rider.reduction', 4.5, 'gold')
        self.assertFalse(any(g['mode'] == 'combo' for g in groups(target, [])))

    def test_damage_attack_combo_includes_small_roll_as_foundation(self):
        target = item(); target['stats'][1] = stat('ranged.attack', .8, 'green')
        self.assertEqual(groups(target, [])[0]['mode'], 'combo')

    def test_duplicate_damage_rows_never_collapsed(self):
        target = item(); target['stats'][1] = stat('ranged.damage', 4.6, 'gold')
        single = item(price=2000)
        result = groups(target, [single])[0]
        self.assertEqual(len(result['stats']), 2)
        self.assertIsNone(result['summary']['ask'])

    def test_unknown_attempts_cannot_be_full_combo_analog(self):
        target = item(attempts=None); target['stats'][1] = stat('ranged.reduction', 4.5, 'gold')
        self.assertIsNone(groups(target, [target])[0]['summary']['ask'])

    def test_nearby_percent_visible_without_inventing_a_price_for_target(self):
        target = item()
        candidate = item(price=700)
        candidate['stats'][0]['value'] = 5.2
        result = estimate(target, [candidate], today=TODAY)
        criterion = result['market_signals']['criteria'][0]
        self.assertIsNone(result['headline'])
        self.assertIsNone(criterion['summary']['ask'])
        self.assertEqual(criterion['references'][0]['stat']['value'], 5.2)
        self.assertEqual(criterion['references'][0]['record']['price'], 700)

    def test_excluded_premium_visible_with_reasons_and_never_counted_as_single_price(self):
        target = item()
        premium = item(price=90000)
        premium['stats'][1] = stat('infantry.attack', 6, 'gold')
        criterion = estimate(target, [premium], today=TODAY)['market_signals']['criteria'][0]
        self.assertIsNone(criterion['summary']['ask'])
        self.assertIn('АТК пехотного отряда 6%', criterion['references'][0]['factors'])

    def test_criterion_examples_keep_color_and_favor_unconfounded_listings(self):
        target = item()
        premium = item(id='premium', price=90000)
        premium['stats'][1] = stat('infantry.attack', 6, 'gold')
        clearer = item(id='clearer', price=700)
        clearer['stats'][0]['value'] = 5.2
        other_color = item(id='purple', price=200)
        other_color['stats'][0]['color'] = 'purple'
        refs = estimate(target, [premium, clearer, other_color], today=TODAY)['market_signals']['criteria'][0]['references']
        self.assertEqual([r['record']['id'] for r in refs], ['clearer', 'premium', 'purple'])

    def test_all_special_criteria_get_references_without_assuming_forum_demand(self):
        target = item()
        candidate = item(price=700)
        result = estimate(target, [candidate], today=TODAY)['market_signals']['criteria']
        self.assertEqual([c['stat'] for c in result], target['stats'])
        self.assertIsNone(result[1]['summary']['ask'])
        self.assertEqual(result[1]['references'][0]['stat']['key'], 'squad.load')

    def test_references_do_not_bypass_market_category_date_self_and_tradeability(self):
        bad = [item(id='slot', slot='vest'), item(id='rarity', rarity='elite'),
               item(id='market', market='Другой'), item(id='old', observed='2025-09-26'),
               item(id='zero', attempts=0), item(id='unsold', status='unsold'), item(id='self')]
        criteria = estimate(item(), bad, today=TODAY, exclude_id='self')['market_signals']['criteria']
        self.assertTrue(all(not c['references'] for c in criteria))

    def test_zombie_base_cannot_inherit_combat_base_price(self):
        target = item()
        target['stats'][1] = stat('ranged.reduction', 4.5, 'gold')
        zombie = copy.deepcopy(target)
        zombie['base_stats'] = [stat('squad.zombie_damage', 5, 'unknown'), stat('squad.zombie_exp', 3, 'unknown')]
        result = estimate(zombie, [target], today=TODAY)
        self.assertIsNone(result['headline'])
        signals = result['market_signals']
        self.assertEqual(len(signals['base']['zombie_stats']), 2)
        self.assertIsNone(signals['groups'][0]['summary']['ask'])
        self.assertFalse(signals['criteria'][0]['references'])
        self.assertEqual(signals['criteria'][0]['donor_references'][0]['base_relation'], 'different')

    def test_two_base_types_and_values_are_required_but_name_is_not(self):
        target = item()
        cases = [('one', target['base_stats'][:1], 'missing'),
                 ('different', [stat('squad.zombie_damage', 5, 'unknown'), stat('squad.zombie_exp', 3, 'unknown')], 'different')]
        larger = copy.deepcopy(target['base_stats']); larger[0]['value'] += 5
        cases.append(('larger', larger, 'values'))
        for name, base, relation in cases:
            with self.subTest(name=name):
                other = item(name=name, base_stats=base)
                result = estimate(target, [other], today=TODAY)
                self.assertIsNone(result['headline'])
                criterion = result['market_signals']['criteria'][0]
                self.assertIsNone(criterion['summary']['ask'])
                refs = criterion['references'] + criterion['donor_references']
                self.assertEqual(refs[0]['base_relation'], relation)
        same = item(name='Совсем другая модель', price=987)
        result = estimate(target, [same], today=TODAY)
        self.assertEqual(result['asks']['median'], 987)
        self.assertEqual(result['market_signals']['criteria'][0]['summary']['ask']['median'], 987)

    def test_donor_value_survives_base_mismatch_without_becoming_whole_price(self):
        target = item()
        donor = item(base_stats=[stat('squad.zombie_damage', 5, 'unknown'), stat('squad.zombie_exp', 3, 'unknown')], price=321)
        result = estimate(target, [donor], today=TODAY)
        criterion = result['market_signals']['criteria'][0]
        self.assertIsNone(result['headline'])
        self.assertIsNone(criterion['summary']['ask'])
        self.assertFalse(criterion['references'])
        self.assertEqual(criterion['donor_summary']['ask']['median'], 321)
        self.assertTrue(criterion['donor_references'][0]['zombie_base'])

    def test_one_base_on_both_cards_never_counts_as_complete(self):
        target = item(); target['base_stats'] = target['base_stats'][:1]
        result = estimate(target, [target], today=TODAY)
        self.assertIsNone(result['headline'])
        self.assertFalse(result['market_signals']['base']['complete'])
        self.assertTrue(any('обе базовые' in warning for warning in result['warnings']))


if __name__ == '__main__':
    unittest.main()
