import threading
import unittest
from unittest.mock import patch

import numpy as np

from buzzbot_app import AutoClicker


class FakeAdbClient:
    def __init__(self):
        self.keyevents = []

    def keyevent(self, keycode):
        self.keyevents.append(int(keycode))


class TruckArrivalAutomationTests(unittest.TestCase):
    @staticmethod
    def make_bot():
        bot = AutoClicker.__new__(AutoClicker)
        bot.stop_event = threading.Event()
        bot.input_backend = "adb"
        bot.adb_client = FakeAdbClient()
        bot.click_count = 0
        bot.routine_completed_steps = {"trucks_open", "truck_detail_check_open"}
        bot.routine_action_counts = {}
        bot.routine_current_had_action = False
        bot.routine_last_action_time = 0.0
        bot.routine_idle_confirmation_count = 0
        bot.routine_truck_overview_confirmations = 0
        bot.routine_truck_current_slot = 0
        bot.routine_truck_checked_slots = set()
        bot._capture_screen_bgr = lambda force=False: (
            np.zeros((720, 1280, 3), dtype=np.uint8),
            (0, 0),
        )
        bot._invalidate_capture = lambda: None
        bot._interruptible_sleep = lambda _seconds: None
        bot.set_status_message = lambda _message, **_kwargs: None
        return bot

    def test_arrival_overlay_is_dismissed_inside_reward_panel(self):
        bot = self.make_bot()
        with patch("buzzbot_app.truck_arrival_reward_is_visible", return_value=True):
            self.assertTrue(
                bot._try_trucks_visual_fallback(
                    {"id": "trucks", "settings": {"max_collections": 8}}
                )
            )

        self.assertEqual(bot.adb_client.keyevents, [4])
        self.assertEqual(bot.routine_truck_arrival_dismiss_attempts, 1)
        self.assertIn(
            "truck_dispatch_pending_verification", bot.routine_completed_steps
        )

    def test_same_arrival_overlay_does_not_reset_pending_verification(self):
        bot = self.make_bot()
        bot.routine_completed_steps.add("truck_dispatch_pending_verification")
        bot.routine_truck_pending_kind = "occupied"
        bot.routine_truck_pending_started_at = 100.0
        bot.routine_truck_arrival_dismiss_attempts = 1

        with (
            patch("buzzbot_app.time.time", return_value=101.0),
            patch("buzzbot_app.truck_arrival_reward_is_visible", return_value=True),
            patch("buzzbot_app.truck_express_overview_is_visible", return_value=False),
        ):
            self.assertTrue(
                bot._try_trucks_visual_fallback(
                    {"id": "trucks", "settings": {"max_collections": 8}}
                )
            )

        self.assertEqual(bot.adb_client.keyevents, [4])
        self.assertEqual(bot.routine_truck_arrival_dismiss_attempts, 2)
        self.assertEqual(bot.routine_truck_pending_started_at, 100.0)

    def test_stubborn_arrival_overlay_has_a_bounded_dismissal_loop(self):
        bot = self.make_bot()
        bot.routine_completed_steps.add("truck_dispatch_pending_verification")
        bot.routine_truck_pending_kind = "occupied"
        bot.routine_truck_pending_started_at = 100.0
        bot.routine_truck_arrival_dismiss_attempts = 3

        with (
            patch("buzzbot_app.time.time", return_value=101.0),
            patch("buzzbot_app.truck_arrival_reward_is_visible", return_value=True),
            patch("buzzbot_app.truck_express_overview_is_visible", return_value=False),
        ):
            self.assertTrue(
                bot._try_trucks_visual_fallback(
                    {"id": "trucks", "settings": {"max_collections": 8}}
                )
            )

        self.assertEqual(bot.adb_client.keyevents, [])
        self.assertEqual(bot.routine_truck_pending_started_at, 100.0)


if __name__ == "__main__":
    unittest.main()
