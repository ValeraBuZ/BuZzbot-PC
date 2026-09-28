import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error

from gear_value.app import ASSETS, Server
from gear_value.make_seed import records
from gear_value.storage import DataDirectoryLock, Store


SEED_COUNT = len(json.loads((ASSETS/'seed.json').read_text(encoding='utf-8'))['records'])


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store=Store(self.temp.name,ASSETS/'seed.json')

    def test_edit_survives_restart_and_backup_exists(self):
        item=self.store.read()[0];item['price']=750
        self.store.save(item)
        restored=Store(self.temp.name,ASSETS/'seed.json')
        self.assertEqual(restored.read()[0]['price'],750)
        self.assertTrue((Path(self.temp.name)/'market.json.bak').is_file())

    def test_invalid_import_is_atomic(self):
        before=self.store.read()
        valid=copy.deepcopy(before[0]);valid.update(id='unique',price=555)
        invalid=copy.deepcopy(valid);invalid['price']='NaN'
        with self.assertRaises(ValueError):self.store.import_data({'schema_version':1,'records':[valid,invalid]})
        self.assertEqual(self.store.read(),before)

    def test_repeated_import_deduplicates(self):
        self.assertEqual(self.store.import_data({'schema_version':1,'records':self.store.read()}),{'added':0,'skipped':SEED_COUNT})
        item=copy.deepcopy(self.store.read()[0]);item.update(id='new-id',price=800)
        self.assertEqual(self.store.import_data({'schema_version':1,'records':[item]})['added'],1)
        self.assertEqual(len(self.store.read()),SEED_COUNT+1)

    def test_delete_does_not_reseed(self):
        for row in self.store.read(): self.store.delete(row['id'])
        self.assertEqual(Store(self.temp.name,ASSETS/'seed.json').read(),[])

    def test_corrupt_data_not_overwritten(self):
        self.store.path.write_text('broken',encoding='utf-8')
        with self.assertRaises(ValueError): Store(self.temp.name,ASSETS/'seed.json')
        self.assertEqual(self.store.path.read_text(encoding='utf-8'),'broken')

    def test_second_process_lock_rejected_and_released_after_close(self):
        lock=DataDirectoryLock(self.temp.name)
        try:
            with self.assertRaises(ValueError):DataDirectoryLock(self.temp.name)
        finally:
            lock.close()
        DataDirectoryLock(self.temp.name).close()


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.server=Server(('127.0.0.1',0),self.temp.name)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()

    def request(self,path,payload=None,token=True,origin=None):
        headers={}
        if payload is not None:
            headers={'Content-Type':'application/json'}
            if token:headers['X-App-Token']=self.server.token
        if origin:headers['Origin']=origin
        request=urllib.request.Request(self.url+path, data=None if payload is None else json.dumps(payload).encode(),headers=headers)
        with urllib.request.urlopen(request) as response: return response.read()

    def test_http_pricing_and_persistence(self):
        state=json.loads(self.request('/api/state'))
        self.assertEqual(len(state['records']),SEED_COUNT)
        result=json.loads(self.request('/api/estimate',{'item':state['records'][0]}))
        self.assertEqual(result['headline']['median'],299)
        row=copy.deepcopy(state['records'][0]);row.update(id='',price=850)
        saved=json.loads(self.request('/api/save',row))
        self.assertTrue(saved['id'])
        self.assertEqual(len(json.loads(self.request('/api/export'))['records']),SEED_COUNT+1)
        self.assertTrue(self.request('/images/lot01.png').startswith(b'\x89PNG'))

    def test_cross_origin_and_no_token_mutations_rejected(self):
        for kwargs in [{'token':False},{'origin':'https://example.com'}]:
            with self.assertRaises(urllib.error.HTTPError) as caught:self.request('/api/delete',{'id':records[0]['id']},**kwargs)
            self.assertEqual(caught.exception.code,403)
            caught.exception.close()
        self.assertEqual(len(self.server.store.read()),SEED_COUNT)

    def test_invalid_requests_return_controlled_error(self):
        for path,payload in [('/api/save',{}),('/api/estimate',{}),('/api/save',[]),('/images/../../README.md',None)]:
            with self.assertRaises(urllib.error.HTTPError) as caught:self.request(path,payload)
            self.assertEqual(caught.exception.code,400)
            caught.exception.close()


if __name__ == '__main__': unittest.main()
