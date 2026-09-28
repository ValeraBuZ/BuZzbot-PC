import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from buzzbot_app import AutoClicker


class FakeAdbClient:
    def __init__(self):
        self.taps = []
        self.keyevents = []

    def tap(self, x, y):
        self.taps.append((int(x), int(y)))

    def keyevent(self, keycode):
        self.keyevents.append(int(keycode))


class ProcessingFactoryTests(unittest.TestCase):
    @staticmethod
    def make_bot():
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.player_width = 1280
        bot.player_height = 720
        bot.adb_client = FakeAdbClient()
        bot.stop_event = threading.Event()
        bot.routine_completed_steps = {"select_refinery"}
        bot._invalidate_capture = lambda: None
        bot._interruptible_sleep = lambda _seconds: None
        bot.set_status_message = lambda _message, **_kwargs: None
        return bot

    def test_open_refinery_returns_true_only_after_header_confirmation(self):
        bot = self.make_bot()
        guard = {"uid": "factory-guard"}
        bot.search_images = [guard]
        bot._locate_image = lambda image: (
            SimpleNamespace(x=220, y=40),
            (80, 18, 307, 44),
            0.91,
        )
        bot._validate_detected_match = lambda image, bbox: (True, "")
        image = {
            "action": "open_processing_factory",
            "confirmation_uid": "factory-guard",
            "click_offset": [0, 0],
        }

        result = bot._execute_action(image, SimpleNamespace(x=821, y=331))

        self.assertTrue(result)
        self.assertEqual(bot.adb_client.taps, [(821, 331)])
        self.assertEqual(bot.adb_client.keyevents, [])

    def test_open_refinery_rejects_unconfirmed_screen_and_retries_selection(self):
        bot = self.make_bot()
        guard = {"uid": "factory-guard"}
        bot.search_images = [guard]
        bot._locate_image = lambda image: (None, None, 0.0)
        bot._validate_detected_match = lambda image, bbox: (False, "missing")
        image = {
            "action": "open_processing_factory",
            "confirmation_uid": "factory-guard",
            "click_offset": [0, 0],
        }

        with patch("buzzbot_app.time.monotonic", side_effect=[0.0, 5.0]):
            result = bot._execute_action(image, SimpleNamespace(x=821, y=331))

        self.assertFalse(result)
        self.assertEqual(bot.adb_client.taps, [(821, 331)])
        self.assertEqual(bot.adb_client.keyevents, [4])
        self.assertNotIn("select_refinery", bot.routine_completed_steps)

    def test_collect_reward_closes_result_overlay_and_restores_factory(self):
        bot = self.make_bot()
        guard = {"uid": "factory-guard"}
        bot.search_images = [guard]
        locations = iter(
            [
                (None, None, 0.0),
                (SimpleNamespace(x=220, y=40), (80, 18, 307, 44), 0.91),
            ]
        )
        bot._locate_image = lambda image: next(locations)
        bot._validate_detected_match = lambda image, bbox: (True, "")
        image = {
            "action": "collect_processing_factory_reward",
            "confirmation_uid": "factory-guard",
            "click_offset": [0, -135],
            "delay": 0.8,
        }

        result = bot._execute_action(image, SimpleNamespace(x=651, y=492))

        self.assertTrue(result)
        self.assertEqual(bot.adb_client.taps, [(651, 357)])
        self.assertEqual(bot.adb_client.keyevents, [4])

    def test_late_factory_header_restores_entry_after_failed_open(self):
        bot = self.make_bot()
        bot.routine_completed_steps.add("pan_north")
        guard = {"uid": "152e2db2-317c-53cf-91a1-eb1dca8f3f30"}
        bot.search_images = [guard]
        bot._locate_image = lambda image: (None, None, 0.0)
        bot._validate_detected_match = lambda image, bbox: (True, "")
        bot.routine_processing_factory_dynamic_selected_at = 100.0
        bot.routine_processing_factory_dynamic_target = (796, 589)
        image = {
            "action": "open_processing_factory",
            "confirmation_uid": guard["uid"],
            "click_offset": [0, 0],
        }
        with patch("buzzbot_app.time.monotonic", side_effect=[0.0, 5.0]):
            self.assertFalse(bot._execute_action(image, SimpleNamespace(x=821, y=331)))
        self.assertTrue(bot.routine_processing_factory_recovery_required)
        self.assertNotIn("select_refinery", bot.routine_completed_steps)
        self.assertIsNone(bot.routine_processing_factory_dynamic_target)

        # Replay the live failure: the header is now visible but selection was cleared.
        bot._locate_image = lambda image: (SimpleNamespace(x=220, y=40), (80, 18, 307, 44), 0.91)
        self.assertTrue(bot._try_processing_factory_visual_fallback({"id": "processing_factory"}))
        self.assertIn("open_refinery", bot.routine_completed_steps)
        self.assertFalse(bot.routine_processing_factory_recovery_required)
        self.assertEqual(bot.adb_client.taps, [(821, 331)])
        self.assertEqual(bot.adb_client.keyevents, [4])

    def test_stop_during_open_confirmation_does_not_press_back(self):
        bot = self.make_bot()
        bot.search_images = [{"uid": "factory-guard"}]
        bot._locate_image = lambda image: (None, None, 0.0)
        bot._interruptible_sleep = lambda _seconds: bot.stop_event.set()
        image = {
            "action": "open_processing_factory",
            "confirmation_uid": "factory-guard",
            "click_offset": [0, 0],
        }
        self.assertFalse(bot._execute_action(image, SimpleNamespace(x=821, y=331)))
        self.assertEqual(bot.adb_client.keyevents, [])

    def test_factory_budget_defers_before_matching_despite_recent_idle_probe(self):
        for task_id in ("processing_factory", "processing_contest"):
            with self.subTest(task_id=task_id):
                bot = self.make_bot()
                bot.current_routine_task_id = task_id
                bot.routine_task_started_at = 100.0
                bot.routine_last_action_time = 279.0
                bot.routine_mode = True
                bot.stop_hotkey_pressed = False
                bot.is_paused = False
                bot.anti_loop_enabled = False
                bot._begin_due_routine = Mock()
                bot._defer_current_routine_unavailable = Mock(side_effect=lambda *args, **kwargs: bot.stop_event.set())
                with patch("buzzbot_app.time.time", return_value=280.0):
                    bot._run_clicker_loop()
                bot._begin_due_routine.assert_not_called()
                bot._defer_current_routine_unavailable.assert_called_once_with(
                    "проверка завода не завершилась за 3 минуты", 280.0, retry_delay=60.0,
                )
                bot.current_routine_task_id = "radar_quick"
                self.assertFalse(bot._processing_factory_watchdog_due(999.0))

    def test_failed_home_recovery_defers_without_resuming_camera(self):
        bot = self.make_bot()
        bot.routine_completed_steps.update({"pan_north", "open_refinery", "open_slot"})
        bot.routine_processing_factory_recovery_required = True
        bot.routine_processing_factory_scan_index = 7
        bot.routine_task_started_at = 100.0
        bot.search_images = []
        bot._return_to_main_screen = Mock(return_value=False)
        bot._defer_current_routine_unavailable = Mock()
        self.assertTrue(bot._try_processing_factory_visual_fallback({"id": "processing_factory"}))
        bot._return_to_main_screen.assert_called_once_with(max_back_steps=3, require_settlement=True)
        bot._defer_current_routine_unavailable.assert_called_once()
        self.assertEqual(bot.routine_processing_factory_scan_index, 7)
        self.assertEqual(bot.routine_task_started_at, 100.0)
        self.assertEqual(bot.adb_client.taps, [])

    def test_rejected_idle_header_resets_confirmation_without_claiming_screen(self):
        bot = self.make_bot()
        bot.input_backend = "pyautogui"
        bot.search_images = [{"uid": "guard"}]
        bot.routine_idle_confirmation_count = 3
        bot._locate_image = lambda image: (SimpleNamespace(x=220, y=40), (80, 18, 307, 44), 0.91)
        bot._validate_detected_match = lambda image, bbox: (False, "wrong colour")
        task = {"id": "processing_factory", "complete_when_idle": True, "idle_completion_guard_uid": "guard"}
        self.assertFalse(bot._routine_idle_completion_ready(task))
        self.assertFalse(bot.routine_idle_guard_visible)
        self.assertEqual(bot.routine_idle_confirmation_count, 0)

    def test_collect_reward_does_not_close_factory_when_no_overlay_appears(self):
        bot = self.make_bot()
        guard = {"uid": "factory-guard"}
        bot.search_images = [guard]
        bot._locate_image = lambda image: (
            SimpleNamespace(x=220, y=40),
            (80, 18, 307, 44),
            0.91,
        )
        bot._validate_detected_match = lambda image, bbox: (True, "")
        image = {
            "action": "collect_processing_factory_reward",
            "confirmation_uid": "factory-guard",
            "click_offset": [0, -135],
        }

        result = bot._execute_action(image, SimpleNamespace(x=651, y=492))

        self.assertTrue(result)
        self.assertEqual(bot.adb_client.taps, [(651, 357)])
        self.assertEqual(bot.adb_client.keyevents, [])


if __name__ == "__main__":
    unittest.main()
