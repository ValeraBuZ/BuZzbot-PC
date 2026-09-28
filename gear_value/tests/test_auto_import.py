import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gear_value.auto_import import AutoImporter
from gear_value.auction_ocr import gold_number, selected_price
from gear_value.make_seed import records
from gear_value.storage import Store


class AutoImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        seed = self.root/'seed.json'
        seed.write_text('{"schema_version":1,"records":[]}', encoding='utf-8')
        self.store = Store(self.root/'data', seed)
        self.importer = AutoImporter(self.store, self.root/'inbox')

    def tearDown(self):
        self.temp.cleanup()

    def shot(self, name='new.png', payload=b'example image'):
        path = self.importer.inbox/name
        path.write_bytes(payload)
        return path

    def recognized(self, *args, **kwargs):
        self.assertFalse(kwargs['save_image'])
        return {'item':copy.deepcopy(records[0]), 'auction':{'status':'ask','price':299},
                'warnings':[], 'raw_text':'АТК отряда 0.8%\nЦена 299', 'evidence':''}

    def test_save_text_then_delete_only_processed_input(self):
        image = self.shot()
        untouched = self.shot('unprocessed.png', b'other')
        result = self.importer.process(image.name, self.recognized)
        self.assertEqual(result['status'], 'saved')
        self.assertFalse(image.exists())
        self.assertTrue(untouched.exists())
        row = self.store.read()[0]
        self.assertEqual(row['price'], 299)
        self.assertEqual(row['evidence'], '')
        log = json.loads(self.importer.path.read_text(encoding='utf-8'))
        self.assertIn('АТК отряда', log[result['id']]['draft']['raw_text'])

    def test_different_filename_duplicate_is_not_counted_again(self):
        self.importer.process(self.shot().name, self.recognized)
        image = self.shot('copy.png')
        result = self.importer.process(image.name, self.recognized)
        self.assertEqual(result['status'], 'duplicate')
        self.assertEqual(len(self.store.read()), 1)
        self.assertFalse(image.exists())

    def test_read_or_storage_failure_keeps_original(self):
        image = self.shot()
        with patch.object(self.store, 'save', side_effect=OSError('disk full')):
            result = self.importer.process(image.name, self.recognized)
        self.assertEqual(result['status'], 'review')
        self.assertTrue(image.exists())
        self.assertEqual(self.store.read(), [])

    def test_journal_failure_never_deletes_and_retry_is_idempotent(self):
        image = self.shot()
        with patch.object(self.importer, '_persist', side_effect=OSError('journal failed')):
            with self.assertRaises(OSError):
                self.importer.process(image.name, self.recognized)
        self.assertTrue(image.exists())
        self.assertEqual(len(self.store.read()), 1)
        self.importer.process(image.name, self.recognized)
        self.assertEqual(len(self.store.read()), 1)
        self.assertFalse(image.exists())

    def test_uncertain_or_unpriced_card_remains_for_review(self):
        for change in [{'auction':None}, {'warnings':['Проверьте число']}, {'auction':{'status':'sold','price':299}}]:
            with self.subTest(change=change):
                image = self.shot()
                def uncertain(*a, **k):
                    return {**self.recognized(*a,**k), **change}
                result = self.importer.process(image.name, uncertain)
                self.assertEqual(result['status'], 'review')
                self.assertTrue(image.exists())
                self.assertEqual(self.store.read(), [])

    def test_file_replaced_during_recognition_is_never_deleted(self):
        image = self.shot()
        def changed(*a, **k):
            image.write_bytes(b'another screenshot')
            return self.recognized(*a,**k)
        result = self.importer.process(image.name, changed)
        self.assertEqual(result['status'], 'review')
        self.assertEqual(image.read_bytes(), b'another screenshot')
        self.assertEqual(self.store.read(), [])

    def test_non_gold_item_is_not_added_or_deleted(self):
        image = self.shot()
        def elite(*args, **kwargs):
            result = self.recognized(*args, **kwargs)
            result['item']['rarity'] = 'elite'
            return result
        result = self.importer.process(image.name, elite)
        self.assertEqual(result['status'], 'review')
        self.assertIn('только золотые', result['reason'])
        self.assertTrue(image.exists())
        self.assertEqual(self.store.read(), [])

    def test_outside_folder_is_rejected(self):
        outside = self.root/'outside.png'; outside.write_bytes(b'do not touch')
        with self.assertRaises(ValueError):
            self.importer.process('../outside.png', self.recognized)
        self.assertTrue(outside.exists())

    def test_manual_review_saves_corrected_text_then_removes_image(self):
        image = self.shot()
        result = self.importer.process(image.name, lambda *a,**k:{**self.recognized(*a,**k),'auction':None})
        raw = {**records[0], 'id':'', 'source':'Проверено', 'price':400}
        row = self.importer.complete(result['id'], raw)
        self.assertEqual(row['price'], 400)
        self.assertFalse(image.exists())

    def test_price_parser_does_not_strip_arbitrary_digits_from_text(self):
        self.assertEqual(gold_number('99,000'), 99000)
        self.assertEqual(gold_number('1 200'), 1200)
        for text in ['0288', 'Сила 99,000', '2.4%', '23:58:04', '1,20', '0']:
            self.assertIsNone(gold_number(text))

    def test_price_selection_ignores_balance_and_other_listings(self):
        def row(text,x,y):
            return {'text':text,'x':x,'y':y,'h':20,'words':[{'text':text,'x':x,'y':y-10,'w':80,'h':20}]}
        rows = [row('99',900,50), row('88000',50,800), row('Лучшая ставка',650,800),row('1200',850,800)]
        status, price = selected_price(rows,1000,1000)
        self.assertEqual(status,'bid')
        self.assertEqual(gold_number(price['text']),1200)
        self.assertIsNone(selected_price(rows[:2],1000,1000))


if __name__ == '__main__': unittest.main()
