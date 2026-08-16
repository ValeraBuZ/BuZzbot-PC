import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pyautogui
import cv2
import numpy as np

from buzzbot.routines import routine_march_context_key
from buzzbot_app import AutoClicker


class FakeAdbClient:
    def __init__(self):
        self.taps = []

    def tap(self, x, y):
        self.taps.append((int(x), int(y)))


class ZombieSearchTests(unittest.TestCase):
    def make_bot(self, fallback_levels=3):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_serial = "emulator-5564"
        bot.current_account_id = "account-a"
        bot.adb_client = FakeAdbClient()
        bot.stop_event = threading.Event()
        bot.stop_hotkey_pressed = False
        bot.sleep_found = 0.8
        bot.zombie_level_restore = {}
        bot.zombie_level_restore_pending = {}
        bot.get_display_profile = lambda: SimpleNamespace(
            width=1280,
            height=720,
            scale_x=1.0,
            scale_y=1.0,
        )
        bot._current_task_settings = lambda: {"fallback_levels": fallback_levels}
        bot._resource_result_level_rejected = lambda _image: False
        bot._interruptible_sleep = lambda _seconds: None
        bot._invalidate_capture = lambda: None
        bot.set_status_message = lambda *_args, **_kwargs: None
        bot.deferred_unavailable = []
        bot._defer_current_routine_unavailable = (
            lambda reason, now=None, retry_delay=None: bot.deferred_unavailable.append(
                (reason, retry_delay)
            )
        )
        bot.save_config = lambda: None
        return bot

    @staticmethod
    def search_image():
        return {
            "action": "zombie_search",
            "click_offset": (0, 0),
            "numbers": [],
            "delay": 0.0,
            "last_used": 0.0,
        }

    def test_tries_each_lower_level_until_zombie_is_found(self):
        bot = self.make_bot(fallback_levels=3)
        visible = iter((True, True, False))
        bot._locate_image = lambda _image: (
            (SimpleNamespace(x=640, y=620), None, 0.9)
            if next(visible)
            else (None, None, 0.0)
        )

        result = bot._execute_action(self.search_image(), SimpleNamespace(x=640, y=620))

        self.assertTrue(result)
        self.assertEqual(
            bot.adb_client.taps,
            [
                (640, 620),
                (494, 544),
                (640, 620),
                (494, 544),
                (640, 620),
                (640, 353),
            ],
        )
        context = routine_march_context_key("adb", "emulator-5564", "account-a")
        self.assertEqual(bot.zombie_level_restore[context], 2)

    def test_restores_starting_level_when_all_fallbacks_are_empty(self):
        bot = self.make_bot(fallback_levels=3)
        bot._locate_image = lambda _image: (SimpleNamespace(x=640, y=620), None, 0.9)

        result = bot._execute_action(self.search_image(), SimpleNamespace(x=640, y=620))

        self.assertFalse(result)
        self.assertEqual(bot.adb_client.taps.count((494, 544)), 3)
        self.assertEqual(bot.adb_client.taps.count((784, 544)), 3)
        self.assertNotIn((640, 353), bot.adb_client.taps)
        self.assertEqual(bot.zombie_level_restore, {})
        self.assertEqual(
            bot.deferred_unavailable,
            [("зомби подходящего уровня не найдены", 60)],
        )

    def test_rotates_to_the_next_lower_level_before_the_next_hunt(self):
        bot = self.make_bot(fallback_levels=3)
        context = routine_march_context_key("adb", "emulator-5564", "account-a")
        bot.zombie_level_restore[context] = 2
        bot._locate_image = lambda _image: (None, None, 0.0)

        result = bot._execute_action(self.search_image(), SimpleNamespace(x=640, y=620))

        self.assertTrue(result)
        self.assertEqual(
            bot.adb_client.taps,
            [(494, 544), (640, 620), (640, 353)],
        )
        self.assertEqual(bot.zombie_level_restore[context], 3)

    def test_restores_interrupted_offset_before_searching_starting_level(self):
        bot = self.make_bot(fallback_levels=3)
        context = routine_march_context_key("adb", "emulator-5564", "account-a")
        bot.zombie_level_restore_pending[context] = 3
        bot._locate_image = lambda _image: (None, None, 0.0)

        result = bot._execute_action(self.search_image(), SimpleNamespace(x=640, y=620))

        self.assertTrue(result)
        self.assertEqual(
            bot.adb_client.taps,
            [(784, 544), (784, 544), (784, 544), (640, 620), (640, 353)],
        )
        self.assertNotIn(context, bot.zombie_level_restore_pending)
        self.assertEqual(bot.zombie_level_restore[context], 0)

    def test_wraps_to_the_saved_starting_level_after_last_fallback(self):
        bot = self.make_bot(fallback_levels=3)
        context = routine_march_context_key("adb", "emulator-5564", "account-a")
        bot.zombie_level_restore[context] = 3
        bot._locate_image = lambda _image: (None, None, 0.0)

        result = bot._execute_action(self.search_image(), SimpleNamespace(x=640, y=620))

        self.assertTrue(result)
        self.assertEqual(
            bot.adb_client.taps,
            [(784, 544), (784, 544), (784, 544), (640, 620), (640, 353)],
        )
        self.assertEqual(bot.zombie_level_restore[context], 0)

    def test_screen_mode_clicks_the_ldplayer_client_center_after_search(self):
        bot = self.make_bot(fallback_levels=0)
        bot.input_backend = "screen"
        bot._screen_game_region = lambda: (84, 108, 1280, 720)
        bot._locate_image = lambda _image: (None, None, 0.0)

        with patch("buzzbot_app.pyautogui.click") as click:
            result = bot._execute_action(
                self.search_image(),
                SimpleNamespace(x=211, y=549),
            )

        self.assertTrue(result)
        self.assertEqual(
            [call.args for call in click.call_args_list],
            [(211, 549), (724, 461)],
        )

    def test_screen_region_excludes_the_ldplayer_custom_title_bar(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot._region = None
        bot.player_width = 1280
        bot.player_height = 720
        bot.player_name = ""
        bot.get_current_account = lambda: {"name": "Phoenix675"}

        with patch(
            "buzzbot_app.find_window_client_region",
            return_value=(84, 73, 1282, 755),
        ):
            region = bot._screen_game_region()

        self.assertEqual(region, (85, 108, 1280, 720))

    def test_screen_mode_treats_missing_template_as_normal_no_match(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "screen"
        bot.scale_enabled = False
        bot._screen_game_region = lambda: (84, 108, 1280, 720)

        with patch(
            "buzzbot_app.pyautogui.locateOnScreen",
            side_effect=pyautogui.ImageNotFoundException,
        ):
            result = bot._locate_image(
                {
                    "path": "missing.png",
                    "confidence": 0.88,
                    "grayscale": True,
                }
            )

        self.assertEqual(result, (None, None, 0))

    def test_march_uses_one_50_stamina_item_then_retries_and_confirms(self):
        bot = self.make_bot()
        bot.cycle_mode = False
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        cv2.rectangle(frame, (1030, 74), (1085, 120), (0, 150, 210), thickness=-1)
        cv2.rectangle(frame, (210, 160), (305, 245), (20, 180, 40), thickness=-1)
        for x1, y1, x2, y2 in (
            (868, 326, 1068, 370),
            (868, 433, 1068, 477),
            (868, 539, 1068, 581),
        ):
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 180, 255), thickness=-1)
        cv2.rectangle(frame, (210, 285), (305, 385), (20, 180, 40), thickness=-1)
        empty_frame = np.zeros_like(frame)
        bot._capture_screen_bgr = lambda force=False: (
            (frame if len(bot.adb_client.taps) < 3 else empty_frame),
            (0, 0),
        )
        locate_results = iter(
            (
                (SimpleNamespace(x=950, y=643), (839, 620, 223, 47), 0.99),
                (None, None, 0.0),
            )
        )
        bot._locate_image = lambda _image: next(locate_results)
        bot._current_task_settings = lambda: {
            "use_stamina_items": True,
            "stamina_item_amount": "auto",
        }
        image = {
            "description": "Отправить отряд на зомби",
            "action": "click",
            "click_offset": (0, 0),
            "numbers": [],
            "click_sequence": [],
            "delay": 0.0,
            "last_used": 0.0,
            "confirm_disappears": True,
        }

        result = bot._execute_action(image, SimpleNamespace(x=900, y=640))

        self.assertTrue(result)
        self.assertEqual(
            bot.adb_client.taps,
            [(900, 640), (968, 348), (1057, 97), (950, 643)],
        )

    def test_march_auto_skips_exhausted_50_and_uses_100_stamina(self):
        bot = self.make_bot()
        bot.cycle_mode = False
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        cv2.rectangle(frame, (1030, 74), (1085, 120), (0, 150, 210), thickness=-1)
        cv2.rectangle(frame, (210, 160), (305, 245), (20, 180, 40), thickness=-1)
        cv2.rectangle(frame, (868, 326), (1068, 370), (85, 85, 85), thickness=-1)
        for x1, y1, x2, y2 in (
            (868, 433, 1068, 477),
            (868, 539, 1068, 581),
        ):
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 180, 255), thickness=-1)
        cv2.rectangle(frame, (210, 285), (305, 385), (20, 180, 40), thickness=-1)
        empty_frame = np.zeros_like(frame)
        bot._capture_screen_bgr = lambda force=False: (
            (frame if len(bot.adb_client.taps) < 3 else empty_frame),
            (0, 0),
        )
        locate_results = iter(
            (
                (SimpleNamespace(x=950, y=643), (839, 620, 223, 47), 0.99),
                (None, None, 0.0),
            )
        )
        bot._locate_image = lambda _image: next(locate_results)
        bot._current_task_settings = lambda: {
            "use_stamina_items": True,
            "stamina_item_amount": "auto",
        }
        image = {
            "description": "Send squad to zombie",
            "action": "click",
            "click_offset": (0, 0),
            "numbers": [],
            "click_sequence": [],
            "delay": 0.0,
            "last_used": 0.0,
            "confirm_disappears": True,
        }

        result = bot._execute_action(image, SimpleNamespace(x=900, y=640))

        self.assertTrue(result)
        self.assertEqual(
            bot.adb_client.taps,
            [(900, 640), (968, 454), (1057, 97), (950, 643)],
        )

    def test_stamina_failure_is_not_reported_as_no_available_squad(self):
        bot = self.make_bot()
        bot.cycle_mode = False
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        cv2.rectangle(frame, (1030, 74), (1085, 120), (0, 150, 210), thickness=-1)
        cv2.rectangle(frame, (210, 160), (305, 245), (20, 180, 40), thickness=-1)
        cv2.rectangle(frame, (868, 326), (1068, 370), (0, 180, 255), thickness=-1)
        cv2.rectangle(frame, (210, 285), (305, 385), (20, 180, 40), thickness=-1)
        bot._capture_screen_bgr = lambda force=False: (frame, (0, 0))
        bot._current_task_settings = lambda: {
            "use_stamina_items": False,
            "stamina_item_amount": "auto",
        }
        image = {
            "description": "Send squad to zombie",
            "action": "click",
            "click_offset": (0, 0),
            "numbers": [],
            "click_sequence": [],
            "delay": 0.0,
            "last_used": 0.0,
            "confirm_disappears": True,
        }

        result = bot._execute_action(image, SimpleNamespace(x=900, y=640))

        self.assertFalse(result)
        self.assertEqual(bot.routine_action_failure_reason, "stamina")

    def test_march_repeats_50_stamina_until_attack_is_funded(self):
        bot = self.make_bot()
        bot.cycle_mode = False
        stamina_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        cv2.rectangle(stamina_frame, (1030, 74), (1085, 120), (0, 150, 210), thickness=-1)
        cv2.rectangle(stamina_frame, (210, 160), (305, 245), (20, 180, 40), thickness=-1)
        cv2.rectangle(stamina_frame, (868, 326), (1068, 370), (0, 180, 255), thickness=-1)
        cv2.rectangle(stamina_frame, (210, 285), (305, 385), (20, 180, 40), thickness=-1)
        empty_frame = np.zeros_like(stamina_frame)

        def capture(force=False):
            return (
                stamina_frame if len(bot.adb_client.taps) in {1, 2, 4, 5} else empty_frame,
                (0, 0),
            )

        bot._capture_screen_bgr = capture
        locate_results = iter(
            (
                (SimpleNamespace(x=950, y=643), (839, 620, 223, 47), 0.99),
                (SimpleNamespace(x=950, y=643), (839, 620, 223, 47), 0.99),
                (None, None, 0.0),
            )
        )
        bot._locate_image = lambda _image: next(locate_results)
        bot._current_task_settings = lambda: {
            "use_stamina_items": True,
            "stamina_item_amount": "auto",
        }
        image = {
            "description": "Send squad to zombie",
            "action": "click",
            "click_offset": (0, 0),
            "numbers": [],
            "click_sequence": [],
            "delay": 0.0,
            "last_used": 0.0,
            "confirm_disappears": True,
        }

        result = bot._execute_action(image, SimpleNamespace(x=900, y=640))

        self.assertTrue(result)
        self.assertEqual(
            bot.adb_client.taps,
            [
                (900, 640),
                (968, 348),
                (1057, 97),
                (950, 643),
                (968, 348),
                (1057, 97),
                (950, 643),
            ],
        )


if __name__ == "__main__":
    unittest.main()
