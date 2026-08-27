import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cv2
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
    @staticmethod
    def healing_form(selected=False):
        frame = np.full((720, 1280, 3), (35, 45, 55), dtype=np.uint8)
        cv2.rectangle(
            frame,
            (230, 140),
            (630, 380),
            (20, 30, 220),
            thickness=-1,
        )
        cv2.circle(
            frame,
            (275, 570),
            52,
            (30, 180, 240) if selected else (20, 30, 220),
            thickness=-1,
        )
        frame[592:642, 900:1155] = (
            (30, 180, 240) if selected else (70, 70, 70)
        )
        return frame

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

    def test_opening_idle_healing_screen_finishes_pending_collection(self):
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

    def test_does_not_start_healing_while_previous_batch_is_pending(self):
        bot = self.make_bot(iter(()))
        bot._healing_settings["_collection_pending"] = True
        image = {
            "action": "heal_troops",
            "last_used": 0.0,
        }

        result = bot._execute_action(
            image,
            SimpleNamespace(x=640, y=650),
        )

        self.assertFalse(result)
        self.assertEqual(bot.adb_client.taps, [])

    def test_idle_troop_form_finishes_stale_pending_collection(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_healing_pan_route = ["left"]
        bot.routine_healing_replay_index = 1
        bot.routine_healing_scan_index = 3
        bot.routine_healing_settle_checks = 1
        bot.routine_healing_search_started = True
        bot.routine_healing_saved_route_rejected = True
        bot._capture_screen_bgr = lambda force=False: (
            self.healing_form(selected=False),
            (0, 0),
        )
        bot._is_main_screen_visible = lambda: self.fail(
            "The already-open hospital form must be handled before main-screen checks"
        )
        bot.set_status_message = lambda *_args, **_kwargs: None
        bot.save_config = lambda: None
        task = {
            "id": "heal",
            "group": "Лечение войск",
            "settings": {
                "_collection_pending": True,
                "_pending_heal_count": 3050,
            },
        }

        result = bot._try_healing_visual_fallback(task)

        self.assertTrue(result)
        self.assertFalse(task["settings"]["_collection_pending"])
        self.assertNotIn("_pending_heal_count", task["settings"])
        self.assertEqual(bot.routine_healing_pan_route, [])
        self.assertFalse(bot.routine_healing_search_started)

    def test_open_idle_troop_form_starts_healing_without_button_template(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.search_images = [
            {
                "enabled": True,
                "action": "heal_troops",
                "group": "Лечение войск",
                "runtime_step": "start_healing",
                "path": "heal.png",
            }
        ]
        bot.stats = {}
        bot.click_count = 0
        bot.routine_current_had_action = False
        bot.routine_last_action_time = 0.0
        bot.routine_idle_confirmation_count = 2
        bot.routine_completed_steps = set()
        actions = []
        bot._execute_action = (
            lambda image, location: actions.append(
                (image["action"], location.x, location.y)
            )
            or True
        )
        task = {
            "id": "heal",
            "group": "Лечение войск",
            "settings": {"_collection_pending": False},
        }

        result = bot._try_healing_troop_form(
            task,
            self.healing_form(selected=False),
        )

        self.assertTrue(result)
        self.assertEqual(actions, [("heal_troops", 1028, 617)])
        self.assertEqual(bot.stats, {"heal.png": 1})
        self.assertEqual(bot.click_count, 1)
        self.assertIn("start_healing", bot.routine_completed_steps)

    def test_pending_auto_filled_idle_form_clears_stale_batch_and_enters_amount(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_healing_pan_route = ["left"]
        bot.routine_healing_replay_index = 1
        bot.routine_healing_scan_index = 3
        bot.routine_healing_settle_checks = 1
        bot.routine_healing_search_started = True
        bot.routine_healing_saved_route_rejected = True
        start_image = {
            "enabled": True,
            "action": "heal_troops",
            "group": "Р›РµС‡РµРЅРёРµ РІРѕР№СЃРє",
            "runtime_step": "start_healing",
            "path": "heal.png",
        }
        bot.search_images = [start_image]
        bot.stats = {}
        bot.click_count = 0
        bot.routine_current_had_action = False
        bot.routine_last_action_time = 0.0
        bot.routine_idle_confirmation_count = 2
        bot.routine_completed_steps = set()
        bot._healing_start_control_visible = lambda: True
        bot.save_config = lambda: None
        bot.set_status_message = lambda *_args, **_kwargs: None
        actions = []
        bot._execute_action = (
            lambda image, location: actions.append(
                (image["action"], location.x, location.y)
            )
            or True
        )
        task = {
            "id": "heal",
            "group": "Р›РµС‡РµРЅРёРµ РІРѕР№СЃРє",
            "settings": {
                "_collection_pending": True,
                "_pending_heal_count": 3050,
            },
        }

        result = bot._try_healing_troop_form(
            task,
            self.healing_form(selected=True),
        )

        self.assertTrue(result)
        self.assertFalse(task["settings"]["_collection_pending"])
        self.assertNotIn("_pending_heal_count", task["settings"])
        self.assertEqual(actions, [("heal_troops", 1028, 617)])

    def test_healing_uses_fixed_right_hand_standard_button(self):
        bot = self.make_bot(iter(((None, None, 0.0),)))
        bot._healing_settings = {
            "_collection_pending": False,
            "troop_count": 3050,
        }
        bot._configure_healing_troop_count = lambda count, frame: (
            count == 3050 and frame.shape == (720, 1280, 3)
        )
        frames = iter(
            (
                (self.healing_form(selected=False), (0, 0)),
                (self.healing_form(selected=True), (0, 0)),
                (np.zeros((720, 1280, 3), dtype=np.uint8), (0, 0)),
            )
        )
        bot._capture_screen_bgr = lambda force=False: next(frames)
        image = {
            "action": "heal_troops",
            "delay": 0.8,
            "last_used": 0.0,
        }

        result = bot._execute_action(
            image,
            SimpleNamespace(x=760, y=617),
        )

        self.assertTrue(result)
        self.assertEqual(bot.adb_client.taps, [(1028, 617)])
        self.assertTrue(bot._healing_settings["_collection_pending"])
        self.assertEqual(bot._healing_settings["_pending_heal_count"], 3050)

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
        bot._is_settlement_screen_visible = lambda: True
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
        bot._capture_screen_bgr = lambda force=False: (
            np.zeros((720, 1280, 3), dtype=np.uint8),
            (0, 0),
        )

        self.assertFalse(bot._try_healing_visual_fallback({"id": "heal"}))

    def test_returns_to_settlement_before_searching_for_hospital(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_healing_pan_route = ["left", "up"]
        bot.routine_healing_replay_index = 2
        bot.routine_healing_scan_index = 7
        bot.routine_healing_search_started = True
        bot._is_main_screen_visible = lambda: True
        bot._is_settlement_screen_visible = lambda: False
        switched = []
        bot._switch_to_settlement_screen = lambda: switched.append(True) or True
        bot.set_status_message = lambda *_args, **_kwargs: None
        bot._capture_screen_bgr = lambda force=False: (
            np.zeros((720, 1280, 3), dtype=np.uint8),
            (0, 0),
        )

        result = bot._try_healing_visual_fallback(
            {"id": "heal", "settings": {"_collection_pending": True}}
        )

        self.assertTrue(result)
        self.assertEqual(switched, [True])
        self.assertEqual(bot.routine_healing_pan_route, [])
        self.assertEqual(bot.routine_healing_replay_index, 0)
        self.assertEqual(bot.routine_healing_scan_index, 0)
        self.assertFalse(bot.routine_healing_search_started)

    def test_pending_healing_throttles_camera_scan_after_recent_check(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = FakeAdbClient()
        bot.routine_completed_steps = set()
        bot._is_main_screen_visible = lambda: True
        bot._is_settlement_screen_visible = lambda: True
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
                "_last_heal_started_at": time.time() - 3.0,
                "_last_pending_camera_scan_at": time.time(),
            },
        }

        result = bot._try_healing_visual_fallback(task)

        self.assertTrue(result)
        self.assertEqual(deferred, ["текущее лечение ещё не завершено"])
        self.assertEqual(bot.adb_client.swipes, [])

    def test_pending_healing_waits_for_configured_collection_delay(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = FakeAdbClient()
        bot.routine_completed_steps = set()
        bot._is_main_screen_visible = lambda: True
        bot._is_settlement_screen_visible = lambda: True
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
        bot._capture_screen_bgr = lambda force=False: (marker_frame, (0, 0))
        deferred = []
        bot._defer_current_routine_unavailable = (
            lambda reason, now=None, retry_delay=None: deferred.append(
                (reason, retry_delay)
            )
        )
        task = {
            "id": "heal",
            "settings": {
                "collect_finished": True,
                "collection_delay_seconds": 30,
                "_collection_pending": True,
                "_last_heal_started_at": time.time(),
            },
        }

        result = bot._try_healing_visual_fallback(task)

        self.assertTrue(result)
        self.assertEqual(deferred[0][0], "сбор вылеченных через 30 сек")
        self.assertGreater(deferred[0][1], 29.0)
        self.assertLessEqual(deferred[0][1], 30.0)
        self.assertEqual(bot.adb_client.taps, [])

    def test_early_collection_marker_keeps_batch_pending(self):
        import cv2

        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_completed_steps = set()
        bot._is_settlement_screen_visible = lambda: True
        screen_checks = iter((True, False))
        bot._is_main_screen_visible = lambda: next(screen_checks)
        marker_frame = np.full((720, 1280, 3), (70, 70, 70), dtype=np.uint8)
        cv2.rectangle(
            marker_frame,
            (572, 276),
            (614, 316),
            (15, 25, 220),
            thickness=-1,
        )
        cv2.rectangle(
            marker_frame,
            (578, 282),
            (608, 310),
            (45, 55, 65),
            thickness=-1,
        )
        frames = iter(
            (
                (marker_frame, (0, 0)),
                (np.zeros((720, 1280, 3), dtype=np.uint8), (0, 0)),
            )
        )
        bot._capture_screen_bgr = lambda force=False: next(frames)
        bot._tap_routine_fallback = lambda *_args: True
        bot.save_config = lambda: None
        deferred = []
        bot._defer_current_routine_unavailable = (
            lambda reason, now=None, retry_delay=None: deferred.append(
                (reason, retry_delay)
            )
        )
        task = {
            "id": "heal",
            "settings": {
                "collect_finished": True,
                "collection_delay_seconds": 2,
                "_collection_pending": True,
                "_last_heal_started_at": time.time() - 10.0,
            },
        }

        result = bot._try_healing_visual_fallback(task)

        self.assertTrue(result)
        self.assertTrue(task["settings"]["_collection_pending"])
        self.assertEqual(
            deferred,
            [("текущее лечение ещё не завершено", 2.0)],
        )

    def test_collection_candidate_can_open_hospital_without_pending_batch(self):
        import cv2

        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_completed_steps = set()
        bot._is_settlement_screen_visible = lambda: True
        screen_checks = iter((True, False))
        bot._is_main_screen_visible = lambda: next(screen_checks)
        marker_frame = np.full((720, 1280, 3), (70, 70, 70), dtype=np.uint8)
        cv2.rectangle(
            marker_frame,
            (572, 276),
            (614, 316),
            (15, 25, 220),
            thickness=-1,
        )
        cv2.rectangle(
            marker_frame,
            (578, 282),
            (608, 310),
            (45, 55, 65),
            thickness=-1,
        )
        frames = iter(
            (
                (marker_frame, (0, 0)),
                (np.zeros((720, 1280, 3), dtype=np.uint8), (0, 0)),
            )
        )
        bot._capture_screen_bgr = lambda force=False: next(frames)
        bot._tap_routine_fallback = lambda *_args: True
        bot.save_config = lambda: None
        deferred = []
        bot._defer_current_routine_unavailable = (
            lambda reason, now=None, retry_delay=None: deferred.append(
                (reason, retry_delay)
            )
        )
        task = {
            "id": "heal",
            "settings": {
                "collect_finished": True,
                "collection_delay_seconds": 2,
                "_collection_pending": False,
            },
        }

        result = bot._try_healing_visual_fallback(task)

        self.assertTrue(result)
        self.assertFalse(task["settings"]["_collection_pending"])
        self.assertEqual(deferred, [])

    def test_pending_collection_finishes_when_idle_hospital_opens(self):
        import cv2

        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_completed_steps = set()
        bot.routine_healing_pan_route = ["left", "up"]
        bot.routine_healing_replay_index = 2
        bot.routine_healing_scan_index = 4
        bot.routine_healing_settle_checks = 1
        bot.routine_healing_search_started = True
        bot.routine_healing_saved_route_rejected = True
        bot.search_images = [
            {
                "enabled": True,
                "runtime_step": "start_healing",
            }
        ]
        bot._is_settlement_screen_visible = lambda: True
        screen_checks = iter((True, False))
        bot._is_main_screen_visible = lambda: next(screen_checks)
        marker_frame = np.full(
            (720, 1280, 3),
            (70, 70, 70),
            dtype=np.uint8,
        )
        cv2.rectangle(
            marker_frame,
            (572, 276),
            (614, 316),
            (15, 25, 220),
            thickness=-1,
        )
        cv2.rectangle(
            marker_frame,
            (578, 282),
            (608, 310),
            (45, 55, 65),
            thickness=-1,
        )
        frames = iter(
            (
                (marker_frame, (0, 0)),
                (np.zeros((720, 1280, 3), dtype=np.uint8), (0, 0)),
            )
        )
        bot._capture_screen_bgr = lambda force=False: next(frames)
        bot._tap_routine_fallback = lambda *_args: True
        bot._locate_image = lambda _image: (
            SimpleNamespace(x=1008, y=607),
            (890, 584, 236, 47),
            0.96,
        )
        statuses = []
        bot.set_status_message = (
            lambda message, **_kwargs: statuses.append(message)
        )
        saves = []
        bot.save_config = lambda: saves.append(True)
        deferred = []
        bot._defer_current_routine_unavailable = (
            lambda reason, now=None, retry_delay=None: deferred.append(
                (reason, retry_delay)
            )
        )
        task = {
            "id": "heal",
            "settings": {
                "collect_finished": True,
                "collection_delay_seconds": 1,
                "_collection_pending": True,
                "_pending_heal_count": 2850,
                "_last_heal_started_at": time.time() - 120.0,
            },
        }

        result = bot._try_healing_visual_fallback(task)

        self.assertTrue(result)
        self.assertFalse(task["settings"]["_collection_pending"])
        self.assertNotIn("_pending_heal_count", task["settings"])
        self.assertEqual(bot.routine_healing_pan_route, [])
        self.assertEqual(bot.routine_healing_replay_index, 0)
        self.assertEqual(bot.routine_healing_scan_index, 0)
        self.assertFalse(bot.routine_healing_search_started)
        self.assertEqual(statuses, ["Вылеченные войска собраны"])
        self.assertEqual(deferred, [])
        self.assertEqual(saves, [True])

    def test_pending_collection_reuses_remembered_hospital_target(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_healing_pan_route = ["right", "left"]
        bot.routine_healing_replay_index = 2
        bot.routine_healing_scan_index = 8
        bot.routine_healing_settle_checks = 1
        bot.routine_healing_search_started = True
        bot.routine_healing_saved_route_rejected = True
        bot._is_main_screen_visible = lambda: True
        bot._is_settlement_screen_visible = lambda: True
        bot._capture_screen_bgr = lambda force=False: (
            np.zeros((720, 1280, 3), dtype=np.uint8),
            (0, 0),
        )
        taps = []
        bot._tap_routine_fallback = (
            lambda target, *_args: taps.append(target) or True
        )
        bot._healing_start_control_visible = lambda: True
        statuses = []
        bot.set_status_message = (
            lambda message, **_kwargs: statuses.append(message)
        )
        bot.save_config = lambda: None
        task = {
            "id": "heal",
            "settings": {
                "collect_finished": True,
                "collection_delay_seconds": 1,
                "_collection_pending": True,
                "_last_heal_started_at": time.time() - 10.0,
                "_hospital_target": [620, 365],
            },
        }

        result = bot._try_healing_visual_fallback(task)

        self.assertTrue(result)
        self.assertEqual(taps, [(620, 365)])
        self.assertFalse(task["settings"]["_collection_pending"])
        self.assertEqual(task["settings"]["_hospital_target"], [620, 365])
        self.assertEqual(bot.routine_healing_pan_route, [])
        self.assertFalse(bot.routine_healing_search_started)
        self.assertIn("Вылеченные войска собраны", statuses)

    def test_shifted_map_discards_stale_hospital_target_after_two_attempts(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot._is_main_screen_visible = lambda: True
        bot._is_settlement_screen_visible = lambda: True
        bot._capture_screen_bgr = lambda force=False: (
            np.zeros((720, 1280, 3), dtype=np.uint8),
            (0, 0),
        )
        taps = []
        bot._tap_routine_fallback = (
            lambda target, *_args: taps.append(target) or True
        )
        bot._healing_start_control_visible = lambda: False
        statuses = []
        bot.set_status_message = (
            lambda message, **_kwargs: statuses.append(message)
        )
        bot.save_config = lambda: None
        bot._defer_current_routine_unavailable = lambda *_args, **_kwargs: None
        task = {
            "id": "heal",
            "settings": {
                "collection_delay_seconds": 1,
                "_collection_pending": True,
                "_last_heal_started_at": time.time() - 10.0,
                "_hospital_target": [620, 365],
            },
        }

        first_result = bot._try_healing_visual_fallback(
            task,
            remembered_only=True,
        )
        task["settings"]["_last_saved_hospital_attempt_at"] = 0.0
        second_result = bot._try_healing_visual_fallback(
            task,
            remembered_only=True,
        )

        self.assertTrue(first_result)
        self.assertFalse(second_result)
        self.assertEqual(taps, [(620, 365), (620, 365)])
        self.assertNotIn("_hospital_target", task["settings"])
        self.assertIn("Госпиталь сместился: ищу новое положение", statuses)

    def test_collects_finished_marker_after_restart_without_pending_state(self):
        import cv2

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
        bot._is_settlement_screen_visible = lambda: True
        marker_frame = np.full((720, 1280, 3), (70, 70, 70), dtype=np.uint8)
        cv2.rectangle(
            marker_frame,
            (572, 276),
            (614, 316),
            (15, 25, 220),
            thickness=-1,
        )
        cv2.rectangle(
            marker_frame,
            (578, 282),
            (608, 310),
            (45, 55, 65),
            thickness=-1,
        )
        frames = iter(
            (
                (marker_frame, (0, 0)),
                (np.zeros((720, 1280, 3), dtype=np.uint8), (0, 0)),
            )
        )
        bot._capture_screen_bgr = lambda force=False: next(frames)
        taps = []
        bot._tap_routine_fallback = (
            lambda target, *_args: taps.append(target) or True
        )
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
        self.assertEqual(taps, [(594, 296)])
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
        bot._is_settlement_screen_visible = lambda: True
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
                "_camera_route_version": 2,
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

    def test_continues_confirmed_scan_when_settlement_marker_is_covered(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = FakeAdbClient()
        bot.current_account_id = "main"
        bot.routine_completed_steps = {"healing_overview"}
        bot.routine_healing_pan_route = ["down"]
        bot.routine_healing_replay_index = 0
        bot.routine_healing_scan_index = 1
        bot.routine_healing_search_started = True
        bot.routine_current_had_action = False
        bot.routine_last_action_time = 0.0
        bot.routine_idle_confirmation_count = 0
        bot.click_count = 0
        bot._is_main_screen_visible = lambda: True
        bot._is_settlement_screen_visible = lambda: False
        bot._capture_screen_bgr = lambda force=False: (
            np.zeros((720, 1280, 3), dtype=np.uint8),
            (0, 0),
        )
        bot._invalidate_capture = lambda: None
        bot._interruptible_sleep = lambda _seconds: None
        bot.set_status_message = lambda *_args, **_kwargs: None
        task = {
            "id": "heal",
            "settings": {
                "_camera_route_version": 2,
                "_camera_routes": {},
            },
        }

        result = bot._try_healing_visual_fallback(task)

        self.assertTrue(result)
        self.assertEqual(
            bot.adb_client.swipes,
            [(640, 570, 640, 250, 400)],
        )
        self.assertEqual(bot.routine_healing_pan_route, ["down", "up"])
        self.assertEqual(bot.routine_healing_scan_index, 2)

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
        bot._is_settlement_screen_visible = lambda: True
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
                "_camera_route_version": 2,
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
            [(640, 250, 640, 570, 400)],
        )
        self.assertEqual(saves, [True])

    def test_defers_healing_after_full_camera_scan(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = FakeAdbClient()
        bot.current_account_id = "main"
        bot.routine_completed_steps = {"healing_overview"}
        bot.routine_healing_pan_route = ["left"] * 40
        bot.routine_healing_replay_index = 0
        bot.routine_healing_scan_index = 40
        bot.routine_healing_settle_checks = 2
        bot.routine_healing_saved_route_rejected = False
        bot.routine_healing_search_started = True
        bot._is_main_screen_visible = lambda: True
        bot._is_settlement_screen_visible = lambda: True
        bot._capture_screen_bgr = lambda force=False: (
            np.zeros((720, 1280, 3), dtype=np.uint8),
            (0, 0),
        )
        deferred = []
        bot._defer_current_routine_unavailable = (
            lambda reason, now=None, retry_delay=None: deferred.append(
                (reason, retry_delay)
            )
        )
        task = {
            "id": "heal",
            "settings": {"_camera_route_version": 2},
        }

        result = bot._try_healing_visual_fallback(task)

        self.assertTrue(result)
        self.assertEqual(
            deferred,
            [("госпиталь не найден после полного обхода карты", 300.0)],
        )
        self.assertEqual(bot.adb_client.swipes, [])

    def test_waits_for_final_healing_markers_before_deferring(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = FakeAdbClient()
        bot.current_account_id = "main"
        bot.routine_completed_steps = {"healing_overview"}
        bot.routine_healing_pan_route = ["left"] * 40
        bot.routine_healing_replay_index = 0
        bot.routine_healing_scan_index = 40
        bot.routine_healing_settle_checks = 0
        bot.routine_healing_saved_route_rejected = False
        bot.routine_healing_search_started = True
        bot._is_main_screen_visible = lambda: True
        bot._is_settlement_screen_visible = lambda: True
        bot._capture_screen_bgr = lambda force=False: (
            np.zeros((720, 1280, 3), dtype=np.uint8),
            (0, 0),
        )
        invalidations = []
        sleeps = []
        deferred = []
        bot._invalidate_capture = lambda: invalidations.append(True)
        bot._interruptible_sleep = lambda seconds: sleeps.append(seconds)
        bot.set_status_message = lambda *_args, **_kwargs: None
        bot._defer_current_routine_unavailable = (
            lambda reason, now=None: deferred.append(reason)
        )
        task = {
            "id": "heal",
            "settings": {"_camera_route_version": 2},
        }

        result = bot._try_healing_visual_fallback(task)

        self.assertTrue(result)
        self.assertEqual(bot.routine_healing_settle_checks, 1)
        self.assertEqual(invalidations, [True])
        self.assertEqual(sleeps, [1.5])
        self.assertEqual(deferred, [])

    def test_remembers_successful_healing_camera_route_per_account(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = FakeAdbClient()
        bot.current_account_id = "farm"
        full_route = ["left"] * 5 + ["up"] * 4 + ["right"] * 12
        bot.routine_healing_pan_route = full_route
        settings = {}
        bot._current_task_settings = lambda: settings
        saves = []
        bot.save_config = lambda: saves.append(True)

        bot._remember_healing_camera_route()

        self.assertEqual(
            settings["_camera_routes"]["emulator-5554:farm"],
            full_route,
        )
        self.assertEqual(settings["_camera_route_version"], 2)
        self.assertEqual(saves, [True])


if __name__ == "__main__":
    unittest.main()
