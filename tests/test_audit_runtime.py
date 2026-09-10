import queue
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import numpy as np

from buzzbot.accounts import normalize_account_profiles
from buzzbot.routines import normalize_routine_tasks
from buzzbot.state import BotState
from buzzbot_app import AutoClicker, _BotActionInterrupted


class RuntimeRegressionTests(unittest.TestCase):
    def make_schedule_bot(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.group_schedules = {"night": {"auto": True, "type": "duration", "on_time": "23:30", "duration": 120}}
        bot.groups = {"night": False}
        bot.save_config = Mock()
        bot.root = None
        return bot

    def test_duration_schedule_spans_midnight_and_excludes_end(self):
        for hour, minute, expected in ((23, 29, False), (23, 30, True), (0, 30, True), (1, 29, True), (1, 30, False)):
            with self.subTest(hour=hour, minute=minute):
                bot = self.make_schedule_bot()
                current = time.struct_time((2026, 9, 8, hour, minute, 0, 1, 251, -1))
                with patch("buzzbot_app.time.localtime", return_value=current):
                    bot.check_group_schedules()
                self.assertEqual(bot.groups["night"], expected)

    def test_schedule_gui_event_is_queued(self):
        bot = self.make_schedule_bot()
        bot.root = Mock()
        bot.gui_queue = queue.Queue()
        current = time.struct_time((2026, 9, 8, 23, 45, 0, 1, 251, -1))
        with patch("buzzbot_app.time.localtime", return_value=current):
            bot.check_group_schedules()
        bot.root.event_generate.assert_not_called()
        callback, args, kwargs = bot.gui_queue.get_nowait()
        callback(*args, **kwargs)
        bot.root.event_generate.assert_called_once_with("<<GroupsChanged>>")

    def test_corrupt_config_is_not_reconstructed_or_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            original = b'{"images": [broken'
            path.write_bytes(original)
            bot = AutoClicker.__new__(AutoClicker)
            bot._load_existing_images = Mock()
            bot.save_config = Mock()
            with patch("buzzbot_app.CONFIG_FILE", path), self.assertRaises(ValueError):
                bot.load_config()
            self.assertEqual(path.read_bytes(), original)
            bot._load_existing_images.assert_not_called()
            bot.save_config.assert_not_called()

    def test_worker_sleep_unwinds_on_stop_or_pause(self):
        for paused in (False, True):
            with self.subTest(paused=paused):
                bot = AutoClicker.__new__(AutoClicker)
                bot._thread = threading.current_thread()
                bot.stop_event = threading.Event()
                bot.stop_hotkey_pressed = False
                bot.is_paused = paused
                if not paused:
                    bot.stop_event.set()
                with self.assertRaises(_BotActionInterrupted):
                    bot._interruptible_sleep(0)

    def test_worker_failure_releases_device_and_resets_state(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot._run_clicker_loop = Mock(side_effect=RuntimeError("unexpected"))
        bot.stop_event = threading.Event()
        lease = bot.device_lease = Mock()
        bot.root = None
        bot.tr = lambda key: key
        bot.set_status_message = Mock()
        with self.assertRaises(RuntimeError):
            bot._clicker_loop()
        self.assertTrue(bot.stop_event.is_set())
        self.assertEqual(bot.state, BotState.STOPPED)
        self.assertIsNone(bot.device_lease)
        lease.release.assert_called_once()

    def test_duplicate_account_suffix_cannot_create_duplicate_ids(self):
        profiles = normalize_account_profiles([{"id": "a"}, {"id": "a_3"}, {"id": "a"}])
        ids = [profile["id"] for profile in profiles]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids[:2], ["a", "a_3"])

    def test_nonfinite_task_numbers_use_defaults(self):
        for number in (float("inf"), float("-inf"), float("nan")):
            with self.subTest(number=number):
                tasks = normalize_routine_tasks([{"id": "food", "priority": number, "interval_minutes": number}])
                food = next(task for task in tasks if task["id"] == "food")
                self.assertGreater(food["priority"], 0)
                self.assertLess(food["interval_minutes"], float("inf"))

    def test_settlement_click_in_offset_window_uses_screen_origin(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "screen"
        bot._is_settlement_screen_visible = Mock(side_effect=[False, True])
        bot._is_main_screen_visible = lambda: True
        bot._capture_screen_bgr = lambda **kwargs: (np.zeros((720, 1280, 3), dtype=np.uint8), (400, 200))
        bot._invalidate_capture = Mock()
        bot._interruptible_sleep = Mock()
        bot.set_status_message = Mock()
        with patch("buzzbot_app.pyautogui.click") as click:
            self.assertTrue(bot._switch_to_settlement_screen())
        click.assert_called_once_with(465, 855)

    def test_partial_multi_start_failure_stops_previously_started_workers(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot._start_all_emulators = Mock(side_effect=OSError("process creation failed"))
        bot.stop = Mock()
        bot._stop_multi_workers = Mock()
        bot.set_status_message = Mock()
        self.assertFalse(bot.start_all_emulators())
        bot.stop.assert_called_once()
        bot._stop_multi_workers.assert_called_once()

    def test_remote_stop_and_denial_cover_background_workers(self):
        for action in ("stop", "deny"):
            with self.subTest(action=action):
                bot = AutoClicker.__new__(AutoClicker)
                bot.is_running = False
                bot.multi_emulator_workers = {1: {"process": Mock()}}
                bot.stop_all_emulators = Mock()
                bot.set_status_message = Mock()
                self.assertTrue(bot._execute_remote_command(action))
                bot.stop_all_emulators.assert_called_once()


if __name__ == "__main__":
    unittest.main()
