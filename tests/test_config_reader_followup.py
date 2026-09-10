import builtins
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from buzzbot.routines import normalize_routine_tasks
from buzzbot_app import AutoClicker


class ConfigReaderTests(unittest.TestCase):
    def make_bot(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.adb_serial = ""
        bot.adb_path = ""
        bot.player_width = 1280
        bot.player_height = 720
        bot.is_multi_worker = True
        # This test uses no private store, emulator, GUI, or worker.
        bot._migrate_account_logins_to_credential_store = Mock()
        return bot

    def test_real_load_closes_reader_before_normalization_and_atomic_save(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            original = json.dumps({"images": [], "groups": {"keep": True}, "sleep_found": 3.25})
            path.write_text(original, encoding="utf-8-sig")
            original_bytes = path.read_bytes()
            bot = self.make_bot()
            readers = []
            stages = []
            def tracked_open(*args, **kwargs):
                handle = builtins.open(*args, **kwargs)
                readers.append(handle)
                return handle
            def normalize(tasks):
                self.assertTrue(readers[-1].closed, "reader still open during normalization")
                stages.append("normalize")
                return normalize_routine_tasks(tasks)
            def save():
                self.assertTrue(readers[-1].closed, "reader still open during atomic save")
                stages.append("save")
                AutoClicker.save_config(bot)
            bot.save_config = save
            with (
                patch("buzzbot_app.CONFIG_FILE", path),
                patch("buzzbot_app.CONFIG_BACKUP_DIR", Path(directory) / "backups"),
                patch("buzzbot_app.open", side_effect=tracked_open, create=True),
                patch("buzzbot_app.normalize_routine_tasks", side_effect=normalize),
                patch("buzzbot.storage.os.replace", wraps=os.replace) as replace,
                patch("buzzbot.storage.time.sleep") as sleep,
                self.assertNoLogs("BuZzbot", level="ERROR"),
            ):
                bot.load_config()
            self.assertEqual(stages, ["normalize", "save"])
            self.assertEqual(len(readers), 1)
            self.assertTrue(readers[0].closed)
            replace.assert_called_once()
            sleep.assert_not_called()
            saved = json.loads(path.read_text(encoding="utf-8-sig"))
            self.assertEqual(saved["sleep_found"], 3.25)
            self.assertTrue(saved["groups"]["keep"])
            backups = list((Path(directory) / "backups").glob("*.json"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original_bytes)

    def test_invalid_json_closes_reader_and_preserves_original_without_save(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            original = b'{"unfinished":'
            path.write_bytes(original)
            bot = self.make_bot()
            bot.save_config = Mock()
            readers = []
            def tracked_open(*args, **kwargs):
                handle = builtins.open(*args, **kwargs)
                readers.append(handle)
                return handle
            with (
                patch("buzzbot_app.CONFIG_FILE", path),
                patch("buzzbot_app.open", side_effect=tracked_open, create=True),
                self.assertLogs("BuZzbot", level="ERROR"),
                self.assertRaises(ValueError),
            ):
                bot.load_config()
            bot.save_config.assert_not_called()
            bot._migrate_account_logins_to_credential_store.assert_not_called()
            self.assertTrue(readers[0].closed)
            self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
