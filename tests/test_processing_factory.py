import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

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
