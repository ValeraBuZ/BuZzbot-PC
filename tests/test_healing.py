import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from buzzbot_app import AutoClicker


class FakeAdbClient:
    def __init__(self):
        self.taps = []
        self.swipes = []
        self.serial = "emulator-5554"

    def tap(self, x, y):
        self.taps.append((int(x), int(y)))

    def swipe(self, x1, y1, x2, y2, duration_ms):
        self.swipes.append(
            (int(x1), int(y1), int(x2), int(y2), int(duration_ms))
        )


class HealingTests(unittest.TestCase):
    def make_bot(self, locate_results):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = FakeAdbClient()
        bot.stop_event = threading.Event()
        bot.stop_hotkey_pressed = False
        bot.sleep_found = 0.8
        bot.get_display_profile = lambda: SimpleNamespace(
            width=1280,
            height=720,
            scale_x=1.0,
            scale_y=1.0,
        )
        bot._resolve_action_numbers = lambda _image: []
        bot._resource_result_level_rejected = lambda _image: False
        bot._interruptible_sleep = lambda _seconds: None
        bot._invalidate_capture = lambda: None
        bot._validate_detected_match = lambda _image, _bbox: (True, None)
        bot.set_status_message = lambda *_args, **_kwargs: None
        bot._locate_image = lambda _image: next(locate_results)
        bot.search_images = []
        bot._healing_settings = {}
        bot._current_task_settings = lambda: bot._healing_settings
        bot.save_config = lambda: None
        return bot

    @staticmethod
    def collect_image():
        return {
            "action": "collect_healed_troops",
            "click_offset": (0, 0),
            "last_used": 0.0,
        }

    def test_collects_finished_troops_when_marker_disappears(self):
        bot = self.make_bot(iter(((None, None, 0.0),)))

        result = bot._execute_action(
            self.collect_image(),
            SimpleNamespace(x=1070, y=160),
        )

        self.assertTrue(result)
        self.assertEqual(bot.adb_client.taps, [(1070, 160)])

    def test_retries_finished_troops_when_marker_remains(self):
        marker = (
            SimpleNamespace(x=1072, y=162),
            (1049, 141, 46, 43),
            0.85,
        )
        bot = self.make_bot(iter((marker, marker, marker, marker, (None, None, 0.0))))

        with patch(
            "buzzbot_app.time.monotonic",
            side_effect=(0.0, 0.5, 1.0, 1.5, 2.1, 3.0, 3.5),
        ):
            result = bot._execute_action(
                self.collect_image(),
                SimpleNamespace(x=1070, y=160),
            )

        self.assertTrue(result)
        self.assertEqual(bot.adb_client.taps, [(1070, 160), (1072, 162)])

    def test_opens_healing_screen_without_troop_specific_collection_template(self):
        bot = self.make_bot(iter(()))
        start_image = {
            "group": "Лечение войск",
            "enabled": True,
            "runtime_step": "start_healing",
        }
        bot.search_images = [start_image]
        bot._healing_settings["_collection_pending"] = True
        bot._locate_image = lambda image: (
            (
                SimpleNamespace(x=640, y=650),
                (515, 625, 250, 50),
                0.95,
            )
            if image is start_image
            else (None, None, 0.0)
        )
        image = {
            "action": "open_healing_hospital",
            "group": "Лечение войск",
            "last_used": 0.0,
        }

        result = bot._execute_action(image, SimpleNamespace(x=1170, y=178))

        self.assertTrue(result)
        self.assertEqual(bot.adb_client.taps, [(1170, 178)])
        self.assertFalse(bot._healing_settings["_collection_pending"])

    def test_taps_healing_row_again_after_collecting_finished_batch(self):
        bot = self.make_bot(iter(()))
        start_image = {
            "group": "Лечение войск",
            "enabled": True,
            "runtime_step": "start_healing",
        }
        open_image = {
            "action": "open_healing_hospital",
            "group": "Лечение войск",
            "last_used": 0.0,
        }
        bot.search_images = [start_image]
        start_checks = iter(
            [
                (None, None, 0.0),
                (None, None, 0.0),
                (None, None, 0.0),
                (None, None, 0.0),
                (
                    SimpleNamespace(x=640, y=650),
                    (515, 625, 250, 50),
                    0.95,
                ),
            ]
        )

        def locate(image):
            if image is start_image:
                return next(start_checks)
            return (
                SimpleNamespace(x=1172, y=180),
                (1145, 155, 50, 45),
                0.92,
            )

        bot._locate_image = locate

        result = bot._execute_action(
            open_image,
            SimpleNamespace(x=1170, y=178),
        )

        self.assertTrue(result)
        self.assertEqual(bot.adb_client.taps, [(1170, 178), (1172, 180)])

    def test_starts_camera_search_with_collection_marker_active(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_completed_steps = set()
        bot.routine_healing_search_started = False
        bot.routine_last_action_time = 0.0
        bot._is_main_screen_visible = lambda: True
        bot._capture_screen_bgr = lambda force=False: (
            np.zeros((1080, 1920, 3), dtype=np.uint8),
            (0, 0),
        )
        taps = []
        bot._tap_routine_fallback = (
            lambda target, coord_key, status_message: taps.append(
                (target, coord_key, status_message)
            )
            or True
        )
        bot.save_config = lambda: None
        bot.set_status_message = lambda *_args, **_kwargs: None

        result = bot._try_healing_visual_fallback(
            {"id": "heal", "settings": {"_overview_enabled": True}}
        )

        self.assertTrue(result)
        self.assertEqual(taps, [])
        self.assertNotIn("healing_overview", bot.routine_completed_steps)
        self.assertTrue(bot.routine_healing_search_started)

    def test_does_not_use_healing_fallback_outside_main_screen(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_completed_steps = set()
        bot._is_main_screen_visible = lambda: False

        self.assertFalse(bot._try_healing_visual_fallback({"id": "heal"}))

    def test_pending_healing_throttles_camera_scan_after_recent_check(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = FakeAdbClient()
        bot.routine_completed_steps = set()
        bot._is_main_screen_visible = lambda: True
        bot._capture_screen_bgr = lambda force=False: (
            np.zeros((720, 1280, 3), dtype=np.uint8),
            (0, 0),
        )
        deferred = []
        bot._defer_current_routine_unavailable = (
            lambda reason, now=None: deferred.append(reason)
        )
        task = {
            "id": "heal",
            "settings": {
                "_collection_pending": True,
                "_last_heal_started_at": time.time(),
                "_last_pending_camera_scan_at": time.time(),
            },
        }

        result = bot._try_healing_visual_fallback(task)

        self.assertTrue(result)
        self.assertEqual(deferred, ["текущее лечение ещё не завершено"])
        self.assertEqual(bot.adb_client.swipes, [])

    def test_collects_generic_portrait_marker_without_pending_state(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = FakeAdbClient()
        bot.routine_completed_steps = set()
        bot.routine_current_had_action = False
        bot.routine_last_action_time = 0.0
        bot.routine_idle_confirmation_count = 0
        bot.click_count = 0
        bot.blocked_coords = {}
        bot.stop_event = threading.Event()
        bot._is_main_screen_visible = lambda: True
        marker_frame = np.full((720, 1280, 3), (55, 70, 75), dtype=np.uint8)
        for left in (238, 262, 286):
            import cv2

            cv2.rectangle(
                marker_frame,
                (left, 192),
                (left + 23, 231),
                (15, 25, 220),
                thickness=3,
            )
        frames = iter(
            (
                (marker_frame, (0, 0)),
                (np.zeros((720, 1280, 3), dtype=np.uint8), (0, 0)),
            )
        )
        bot._capture_screen_bgr = lambda force=False: next(frames)
        bot._invalidate_capture = lambda: None
        bot._interruptible_sleep = lambda _seconds: None
        bot.set_status_message = lambda *_args, **_kwargs: None
        saves = []
        bot.save_config = lambda: saves.append(True)
        task = {
            "id": "heal",
            "settings": {
                "collect_finished": True,
                "_collection_pending": False,
            },
        }

        result = bot._try_healing_visual_fallback(task)

        self.assertTrue(result)
        self.assertEqual(bot.adb_client.taps, [(274, 212)])
        self.assertFalse(task["settings"]["_collection_pending"])
        self.assertEqual(saves, [True])

    def test_replays_saved_healing_camera_route(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = FakeAdbClient()
        bot.current_account_id = "main"
        bot.routine_completed_steps = {"healing_overview"}
        bot.routine_healing_pan_route = []
        bot.routine_healing_replay_index = 0
        bot.routine_healing_scan_index = 0
        bot.routine_healing_search_started = True
        bot.routine_current_had_action = False
        bot.routine_last_action_time = 0.0
        bot.routine_idle_confirmation_count = 3
        bot.click_count = 0
        bot._is_main_screen_visible = lambda: True
        bot._capture_screen_bgr = lambda force=False: (
            np.zeros((1080, 1920, 3), dtype=np.uint8),
            (0, 0),
        )
        bot._invalidate_capture = lambda: None
        bot._interruptible_sleep = lambda _seconds: None
        bot.set_status_message = lambda *_args, **_kwargs: None
        task = {
            "id": "heal",
            "settings": {
                "_camera_routes": {
                    "emulator-5554:main": ["left"],
                }
            },
        }

        result = bot._try_healing_visual_fallback(task)

        self.assertTrue(result)
        self.assertEqual(
            bot.adb_client.swipes,
            [(1470, 630, 540, 630, 400)],
        )
        self.assertEqual(bot.routine_healing_pan_route, ["left"])
        self.assertEqual(bot.routine_healing_replay_index, 1)

    def test_rejects_stale_route_before_systematic_scan(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = FakeAdbClient()
        bot.current_account_id = "main"
        bot.routine_completed_steps = {"healing_overview"}
        bot.routine_healing_pan_route = ["left"]
        bot.routine_healing_replay_index = 1
        bot.routine_healing_scan_index = 0
        bot.routine_healing_saved_route_rejected = False
        bot.routine_healing_search_started = True
        bot.routine_current_had_action = False
        bot.routine_last_action_time = 0.0
        bot.routine_idle_confirmation_count = 0
        bot.click_count = 0
        bot._is_main_screen_visible = lambda: True
        bot._capture_screen_bgr = lambda force=False: (
            np.zeros((720, 1280, 3), dtype=np.uint8),
            (0, 0),
        )
        bot._invalidate_capture = lambda: None
        bot._interruptible_sleep = lambda _seconds: None
        bot.set_status_message = lambda *_args, **_kwargs: None
        saves = []
        bot.save_config = lambda: saves.append(True)
        task = {
            "id": "heal",
            "settings": {
                "_camera_routes": {
                    "emulator-5554:main": ["left"],
                }
            },
        }

        result = bot._try_healing_visual_fallback(task)

        self.assertTrue(result)
        self.assertNotIn(
            "emulator-5554:main",
            task["settings"]["_camera_routes"],
        )
        self.assertEqual(
            bot.adb_client.swipes,
            [(980, 420, 360, 420, 400)],
        )
        self.assertEqual(saves, [True])

    def test_defers_healing_after_full_camera_scan(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = FakeAdbClient()
        bot.current_account_id = "main"
        bot.routine_completed_steps = {"healing_overview"}
        bot.routine_healing_pan_route = ["left"] * 51
        bot.routine_healing_replay_index = 0
        bot.routine_healing_scan_index = 51
        bot.routine_healing_saved_route_rejected = False
        bot.routine_healing_search_started = True
        bot._is_main_screen_visible = lambda: True
        bot._capture_screen_bgr = lambda force=False: (
            np.zeros((720, 1280, 3), dtype=np.uint8),
            (0, 0),
        )
        deferred = []
        bot._defer_current_routine_unavailable = (
            lambda reason, now=None: deferred.append(reason)
        )
        task = {"id": "heal", "settings": {}}

        result = bot._try_healing_visual_fallback(task)

        self.assertTrue(result)
        self.assertEqual(
            deferred,
            ["госпиталь не найден после полного обхода карты"],
        )
        self.assertEqual(bot.adb_client.swipes, [])

    def test_remembers_successful_healing_camera_route_per_account(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = FakeAdbClient()
        bot.current_account_id = "farm"
        bot.routine_healing_pan_route = ["left", "up"]
        settings = {}
        bot._current_task_settings = lambda: settings
        saves = []
        bot.save_config = lambda: saves.append(True)

        bot._remember_healing_camera_route()

        self.assertEqual(
            settings["_camera_routes"]["emulator-5554:farm"],
            ["left", "up"],
        )
        self.assertEqual(saves, [True])


if __name__ == "__main__":
    unittest.main()
