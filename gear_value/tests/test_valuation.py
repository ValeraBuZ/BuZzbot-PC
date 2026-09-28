import copy
from datetime import date
import unittest

from gear_value.make_seed import records
from gear_value.valuation import estimate, validate_item, validate_record

TODAY = date(2026, 9, 26)


def row(price=300, status='ask', id='a', **changes):
    result = copy.deepcopy(records[0])
    result.update(id=id, price=price, status=status, sale_confirmed=status == 'sold', **changes)
    return validate_record(result, TODAY)


class PricingTests(unittest.TestCase):
    def test_empty_market_has_no_made_up_price(self):
        result = estimate(row(), [], today=TODAY)
        self.assertIsNone(result['headline'])
        self.assertEqual(result['basis'], 'insufficient')

    def test_single_ask_is_labelled_not_sold(self):
        result = estimate(row(), [row(299)], today=TODAY)
        self.assertEqual(result['headline']['median'], 299)
        self.assertEqual(result['basis'], 'ask')
        self.assertIsNone(result['sold'])
        self.assertTrue(any('одно' in s for s in result['warnings']))

    def test_bids_and_unsold_cannot_inflate_price(self):
        result = estimate(row(), [row(100000,'bid'), row(999999,'unsold',id='b')], today=TODAY)
        self.assertIsNone(result['headline'])
        self.assertEqual(result['bids']['median'], 100000)
        self.assertEqual(result['unsold_count'], 1)

    def test_three_sales_use_median_without_asking_price_contamination(self):
        result = estimate(row(), [row(300,'sold',id='a'),row(500,'sold',id='b'),
                                 row(700,'sold',id='c'),row(100000,'ask',id='d')], today=TODAY)
        self.assertEqual(result['basis'], 'sold')
        self.assertEqual(result['headline'], {'median':500,'low':300,'high':700,'count':3})

    def test_two_sales_do_not_claim_market_estimate(self):
        result = estimate(row(), [row(300,'sold',id='a'),row(500,'sold',id='b')], today=TODAY)
        self.assertEqual(result['basis'], 'insufficient')
        self.assertEqual(result['sold']['count'], 2)

    def test_filter_market_age_self_and_duplicates(self):
        result = estimate(row(), [row(id='self'),row(id='a'),row(id='duplicate'),
                                 row(id='old',observed='2025-12-01'),row(id='foreign',market='Другой рынок')],
                          today=TODAY, exclude_id='self')
        self.assertEqual(result['headline']['count'], 1)
        self.assertEqual(result['excluded'], {'market':1,'stale':1,'duplicate':1})

    def test_repeated_observations_on_different_days_are_not_three_sales(self):
        result = estimate(row(), [row(300,'sold',id='a',observed='2026-09-24'),
                                 row(300,'sold',id='b',observed='2026-09-25'),
                                 row(300,'sold',id='c',observed='2026-09-26')],today=TODAY)
        self.assertEqual(result['sold']['count'],1)
        self.assertEqual(result['basis'],'insufficient')
        self.assertEqual(result['matches'][0]['observed'],'2026-09-26')

    def test_different_base_level_trait_attempts_not_full_analogs(self):
        for field,value in [('level',1),('trait','Ношеное'),('attempts',2),('attempts',None),
                            ('base_stats',[])]:
            with self.subTest(field=field):
                result = estimate(row(), [row(**{field:value})], today=TODAY)
                self.assertIsNone(result['headline'])
                self.assertEqual(len(result['related']), 1)

    def test_item_name_does_not_change_price_within_category(self):
        for name in ('P90', '', 'Другое оружие'):
            result = estimate(row(name=name), [row(name='M4', price=500)], today=TODAY)
            self.assertEqual(result['headline']['median'], 500)

    def test_missing_own_base_not_full_analog(self):
        result=estimate(row(base_stats=[]),[row()],today=TODAY)
        self.assertIsNone(result['headline'])

    def test_no_cross_slot_donor(self):
        result=estimate(row(),[row(slot='mask')],today=TODAY)
        self.assertEqual(result['related'],[])

    def test_roll_threshold_and_color(self):
        target=row(); target['stats'][0].update(value=4.5,color='gold')
        lower=copy.deepcopy(target); lower['stats'][0]['value']=4.49
        wrong_color=copy.deepcopy(target);wrong_color['stats'][0]['color']='purple'
        for sample in [lower,wrong_color]:
            self.assertIsNone(estimate(target,[sample],today=TODAY)['headline'])

    def test_duplicate_attribute_rows_not_collapsed(self):
        target=validate_record(records[1],TODAY)
        wrong=copy.deepcopy(target);wrong['stats'][1]['value']=10
        self.assertIsNone(estimate(target,[wrong],today=TODAY)['headline'])
        swapped=copy.deepcopy(target);swapped['stats'].reverse()
        self.assertEqual(estimate(target,[swapped],today=TODAY)['headline']['median'],250)

    def test_all_secondary_attributes_must_match(self):
        changed=row();changed['stats'][2]['key']='infantry.defense'
        result=estimate(row(),[changed],today=TODAY)
        self.assertIsNone(result['headline'])
        self.assertEqual(len(result['related']),1)

    def test_unsafe_numeric_and_future_date_rejected(self):
        for value in ['NaN','Infinity',-1,True,1.1]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                row(price=value)
        with self.assertRaises(ValueError): row(observed='2026-09-27')
        with self.assertRaises(ValueError): validate_record({**row(), 'status':'sold','sale_confirmed':False},TODAY)
        with self.assertRaises(ValueError): validate_item({**row(),'stats':[]})


if __name__ == '__main__': unittest.main()
