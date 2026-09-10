import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from buzzbot.storage import save_json_with_backup
from buzzbot.credentials import CredentialError, CredentialStore
from buzzbot.report_cloud import detect_sync_folders


class StorageRegressionTests(unittest.TestCase):
    def test_replace_failure_keeps_original_and_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            original = b'{"valuable": "original"}'
            path.write_bytes(original)
            with patch("buzzbot.storage.os.replace", side_effect=PermissionError("locked")):
                with self.assertRaises(PermissionError):
                    save_json_with_backup(path, {"valuable": "new"})
            self.assertEqual(path.read_bytes(), original)
            backups = list((path.parent / "backups/config").glob("*.json"))
            self.assertEqual([backup.read_bytes() for backup in backups], [original])
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_unserializable_data_does_not_touch_original(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{"saved": 1}', encoding="utf-8")
            with self.assertRaises(TypeError):
                save_json_with_backup(path, {"broken": object()})
            self.assertEqual(path.read_text(), '{"saved": 1}')

    def test_concurrent_saves_leave_complete_json_and_bounded_backups(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            def save(index):
                return save_json_with_backup(path, {"index": index, "text": str(index) * 2000}, keep_backups=3)
            with ThreadPoolExecutor(max_workers=8) as workers:
                list(workers.map(save, range(40)))
            payload = json.loads(path.read_text())
            self.assertEqual(payload["text"], str(payload["index"]) * 2000)
            self.assertEqual(len(list((path.parent / "backups/config").glob("*.json"))), 3)
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_corrupt_credential_encoding_has_domain_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.json"
            path.write_bytes(b"\xff\xfeinvalid")
            with self.assertRaises(CredentialError):
                CredentialStore(path).get_password("account")

    def test_bad_credential_structure_cannot_be_overwritten_by_new_password(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.json"
            original = '{"credentials": ["recoverable data"]}'
            path.write_text(original, encoding="utf-8")
            store = CredentialStore(path, protector=lambda data: data)
            with self.assertRaises(CredentialError):
                store.set_password("account", "example")
            self.assertEqual(path.read_text(), original)

    def test_parallel_credential_edits_preserve_every_account(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.json"
            def save(index):
                CredentialStore(path, protector=lambda data: data).set_password(str(index), "test-value")
            with ThreadPoolExecutor(max_workers=8) as workers:
                list(workers.map(save, range(25)))
            self.assertEqual(set(CredentialStore(path).list_keys()), {str(index) for index in range(25)})

    def test_inaccessible_sync_drives_do_not_break_loading_settings(self):
        with patch.object(Path, "is_dir", side_effect=PermissionError("unavailable drive")):
            self.assertEqual(detect_sync_folders(), [])


if __name__ == "__main__":
    unittest.main()
