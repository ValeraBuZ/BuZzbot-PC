import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pyautogui
import cv2
import numpy as np
from pathlib import Path
from buzzbot.matching import zombie_camp_checkbox_is_checked, stamina_dialog_is_visible

from buzzbot.routines import routine_march_context_key
from buzzbot_app import AutoClicker


class FakeAdbClient:
    def __init__(self):
        self.taps = []

    def tap(self, x, y):
        self.taps.append((int(x), int(y)))


class ZombieSearchTests(unittest.TestCase):
    def test_stamina_dialog_requires_real_header_not_world_or_shop_colors(self):
        assets = Path(__file__).parent / "assets/zombie"
        for name, expected in (("stamina_dialog.png", True), ("march_dispatched.jpg", False),
                               ("shop_false_positive.jpg", False), ("left_card.jpg", False)):
            frame = cv2.imread(str(assets / name))
            for scale in (1, 0.75):
                with self.subTest(name=name, scale=scale):
                    self.assertEqual(stamina_dialog_is_visible(cv2.resize(frame,None,fx=scale,fy=scale)), expected)

    @staticmethod
    def stamp_stamina_title(frame):
        title = cv2.imread(str(Path(__file__).resolve().parents[1] / "buzzbot/assets/stamina/dialog_title.png"))
        frame[83:110, 529:748] = title
        return frame
    def test_attack_uses_checkbox_on_same_side_as_detected_card(self):
        for attack_x in (321, 966):
            for checked in (False, True):
                with self.subTest(attack_x=attack_x, checked=checked):
                    bot = self.make_bot()
                    bot.cycle_mode = False
                    frame = np.full((720, 1280, 3), (35, 45, 55), np.uint8)
                    # Bright map decoration at the old fixed checkbox location.
                    if attack_x == 321:
                        frame[506:530, 809:831] = (20, 210, 80)
                    if checked:
                        x = attack_x - 146
                        cv2.line(frame, (x-8, 514), (x-2, 523), (20, 210, 80), 3)
                        cv2.line(frame, (x-2, 523), (x+8, 509), (20, 210, 80), 3)
                    bot._capture_screen_bgr = lambda **kw: (frame, (0, 0))
                    image = dict(self.search_image(), action="zombie_attack", description="Attack")
                    bot._execute_action(image, SimpleNamespace(x=attack_x, y=561))
                    expected = [(attack_x-146, 518), (attack_x, 561)] if checked else [(attack_x, 561)]
                    self.assertEqual(bot.adb_client.taps, expected)

    def test_real_left_card_does_not_mistake_world_map_for_checked_option(self):
        frame = cv2.imread(str(Path(__file__).parent / "assets/zombie/left_card.jpg"))
        self.assertIsNotNone(frame)
        for scale in (1.0, 0.75):
            resized = cv2.resize(frame, None, fx=scale, fy=scale)
            self.assertFalse(zombie_camp_checkbox_is_checked(resized, (321*scale, 561*scale)))

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
        bot._confirm_zombie_search_result = Mock(return_value=True)
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

    def test_raises_one_level_only_after_confirmed_dispatch(self):
        bot = self.make_bot(fallback_levels=3)
        context = routine_march_context_key("adb", "emulator-5564", "account-a")
        bot.zombie_level_restore[context] = 2
        bot.hunt_found_levels = {f"{context}|zombie_hunt": 2}
        bot._remember_hunt_dispatch({"id": "zombie_hunt", "settings": {"fallback_levels": 3}})
        bot._locate_image = lambda _image: (None, None, 0.0)

        result = bot._execute_action(self.search_image(), SimpleNamespace(x=640, y=620))

        self.assertTrue(result)
        self.assertEqual(
            bot.adb_client.taps,
            [(784, 544), (640, 620)],
        )
        self.assertEqual(bot.zombie_level_restore[context], 1)

    def test_restores_interrupted_offset_before_searching_starting_level(self):
        bot = self.make_bot(fallback_levels=3)
        context = routine_march_context_key("adb", "emulator-5564", "account-a")
        bot.zombie_level_restore_pending[context] = 3
        bot._locate_image = lambda _image: (None, None, 0.0)

        result = bot._execute_action(self.search_image(), SimpleNamespace(x=640, y=620))

        self.assertTrue(result)
        self.assertEqual(
            bot.adb_client.taps,
            [(784, 544), (784, 544), (784, 544), (640, 620)],
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
            [(784, 544), (784, 544), (784, 544), (640, 620)],
        )
        self.assertEqual(bot.zombie_level_restore[context], 0)

    def test_ten_level_fallback_then_climbs_one_step_per_success(self):
        bot = self.make_bot(fallback_levels=10)
        context = routine_march_context_key("adb", "emulator-5564", "account-a")
        visible = iter([True] * 10 + [False])
        bot._locate_image = lambda _image: ((SimpleNamespace(x=640, y=620), None, 0.9)
                                          if next(visible) else (None, None, 0.0))
        self.assertTrue(bot._execute_action(self.search_image(), SimpleNamespace(x=640, y=620)))
        self.assertEqual(bot.zombie_level_restore[context], 10)
        bot._locate_image = lambda _image: (None, None, 0.0)
        for expected_offset in (*range(9, -1, -1), 0):
            bot._remember_hunt_dispatch({"id": "zombie_hunt", "settings": {"fallback_levels": 10}})
            self.assertTrue(bot._execute_action(self.search_image(), SimpleNamespace(x=640, y=620)))
            self.assertEqual(bot.zombie_level_restore[context], expected_offset)
        self.assertEqual(bot.adb_client.taps.count((494, 544)), 10)
        self.assertEqual(bot.adb_client.taps.count((784, 544)), 10)

    def test_ten_level_offset_is_restored_after_restart(self):
        bot = self.make_bot(fallback_levels=10)
        context = routine_march_context_key("adb", "emulator-5564", "account-a")
        bot.zombie_level_restore_pending[context] = 10
        bot._locate_image = lambda _image: (None, None, 0.0)
        self.assertTrue(bot._execute_action(self.search_image(), SimpleNamespace(x=640, y=620)))
        self.assertEqual(bot.adb_client.taps[:10], [(784, 544)] * 10)
        self.assertEqual(bot.zombie_level_restore[context], 0)
        self.assertNotIn(context, bot.zombie_level_restore_pending)

    def test_interrupted_raise_preserves_remaining_offset_even_after_limit_reduced(self):
        bot = self.make_bot(fallback_levels=3)
        context, key = bot._hunt_context("zombie_hunt")
        bot.zombie_level_restore_pending[context] = 10
        bot._interruptible_sleep = lambda seconds: bot.stop_event.set()
        self.assertFalse(bot._execute_action(self.search_image(), SimpleNamespace(x=640, y=620)))
        self.assertEqual(bot.zombie_level_restore[context], 9)
        self.assertNotIn(context, bot.zombie_level_restore_pending)
        bot.stop_event.clear()
        bot._interruptible_sleep = lambda seconds: None
        bot._locate_image = lambda image: (None, None, 0.0)
        self.assertTrue(bot._execute_action(self.search_image(), SimpleNamespace(x=640, y=620)))
        self.assertEqual(bot.zombie_level_restore[context], 0)
        self.assertEqual(bot.adb_client.taps.count((784, 544)), 10)

    def test_screen_mode_does_not_click_again_after_target_card_is_confirmed(self):
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
            [(211, 549)],
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
        frame = self.stamp_stamina_title(np.zeros((720, 1280, 3), dtype=np.uint8))
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
        frame = self.stamp_stamina_title(np.zeros((720, 1280, 3), dtype=np.uint8))
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
        frame = self.stamp_stamina_title(np.zeros((720, 1280, 3), dtype=np.uint8))
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
        stamina_frame = self.stamp_stamina_title(np.zeros((720, 1280, 3), dtype=np.uint8))
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
