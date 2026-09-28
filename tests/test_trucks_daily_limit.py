from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch

import cv2

from buzzbot.matching import truck_daily_dispatch_limit_is_visible, truck_personal_dispatch_card_is_visible
from buzzbot_app import AutoClicker
import test_queue_order_regressions as queue_fixture


class TruckDailyLimitTests(unittest.TestCase):
    def frame(self, name):
        frame = cv2.imread(str(Path(__file__).parent / "assets/trucks" / name))
        self.assertIsNotNone(frame)
        return frame

    def bot(self, frame):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_completed_steps = {"trucks_open"}
        bot.routine_action_counts = {}
        bot.routine_truck_checked_slots = set()
        bot._capture_screen_bgr = Mock(return_value=(frame, (0, 0)))
        bot._tap_routine_fallback = Mock(return_value=True)
        bot._save_routine_calibration_frame = Mock()
        bot._defer_current_routine_unavailable = Mock()
        bot._finish_current_routine = Mock()
        bot._interruptible_sleep = Mock()
        bot._invalidate_capture = Mock()
        return bot

    def test_live_zero_counter_survives_disappearing_toast_and_scaling(self):
        frame = self.frame("daily_limit_exhausted.png")
        for with_toast in (True, False):
            if not with_toast:
                frame[110:165, 300:990] = 0
            for size in ((1280, 720), (1920, 1080)):
                self.assertTrue(truck_daily_dispatch_limit_is_visible(cv2.resize(frame, size)))

    def test_live_toast_is_independent_of_counter_but_not_overview_identity(self):
        frame = self.frame("daily_limit_exhausted.png")
        frame[660:710, :330] = 0
        self.assertTrue(truck_daily_dispatch_limit_is_visible(frame))
        frame[0:75] = 0
        self.assertFalse(truck_daily_dispatch_limit_is_visible(frame))

    def test_available_counter_and_other_truck_screens_are_not_exhaustion(self):
        for name in ("third_slot.png", "two_ready_rewards.png", "orange_truck_in_transit_overview.png",
                     "personal_dispatch_card.png", "personal_transporting_card.png", "alliance_staging.png"):
            self.assertFalse(truck_daily_dispatch_limit_is_visible(self.frame(name)), name)

    def test_exhaustion_defers_without_clicking_plus_or_claiming_dispatch(self):
        bot = self.bot(self.frame("daily_limit_exhausted.png"))
        bot.routine_truck_checked_slots = {0, 1}
        bot.routine_completed_steps.add("truck_personal_slot_requested")
        self.assertTrue(bot._try_trucks_visual_fallback({"id": "trucks"}))
        bot._tap_routine_fallback.assert_not_called()
        bot._defer_current_routine_unavailable.assert_called_once()
        self.assertEqual(bot._defer_current_routine_unavailable.call_args.kwargs["retry_delay"], 3600)
        bot._finish_current_routine.assert_not_called()
        self.assertNotIn("max_dispatches", bot.routine_action_counts)

    def test_exhausted_dispatches_do_not_hide_occupied_truck_collection_checks(self):
        bot = self.bot(self.frame("daily_limit_exhausted.png"))
        self.assertTrue(bot._try_trucks_visual_fallback({"id": "trucks"}))
        self.assertEqual(bot._tap_routine_fallback.call_args.args[0], (207, 410))
        self.assertIn("truck_detail_check_open", bot.routine_completed_steps)
        bot._defer_current_routine_unavailable.assert_not_called()

    def test_unchanged_slot_never_repeats_more_than_twice_without_toast(self):
        bot = self.bot(self.frame("third_slot.png"))
        for now in (100, 105, 110):
            with patch("buzzbot_app.time.time", return_value=now):
                self.assertTrue(bot._try_trucks_visual_fallback({"id": "trucks"}))
        self.assertEqual(bot._tap_routine_fallback.call_count, 2)
        bot._defer_current_routine_unavailable.assert_called_once()
        self.assertNotIn("truck_personal_slot_open", bot.routine_completed_steps)
        self.assertNotIn("max_dispatches", bot.routine_action_counts)

    def test_slot_waits_for_card_instead_of_claiming_open_from_tap(self):
        bot = self.bot(self.frame("third_slot.png"))
        with patch("buzzbot_app.time.time", return_value=100):
            self.assertTrue(bot._try_trucks_visual_fallback({"id": "trucks"}))
        self.assertNotIn("truck_personal_slot_open", bot.routine_completed_steps)
        with patch("buzzbot_app.time.time", return_value=101):
            self.assertTrue(bot._try_trucks_visual_fallback({"id": "trucks"}))
        self.assertEqual(bot._tap_routine_fallback.call_count, 1)
        card = self.frame("personal_dispatch_card.png")
        self.assertTrue(truck_personal_dispatch_card_is_visible(card))
        bot._capture_screen_bgr.return_value = (card, (0, 0))
        self.assertTrue(bot._try_trucks_visual_fallback({"id": "trucks"}))
        self.assertIn("truck_personal_slot_open", bot.routine_completed_steps)
        self.assertNotIn("truck_personal_slot_requested", bot.routine_completed_steps)
        self.assertEqual(bot._tap_routine_fallback.call_count, 1)

    def test_daily_limit_advances_exactly_one_ordered_slot_without_stopping_bot(self):
        helper = queue_fixture.QueueOrderRegressionTests()
        task = helper.task("trucks")
        bot = helper.make_bot([task, helper.task("alliance_help")], 0)
        bot.stop_event = threading.Event()
        bot.routine_mode = True
        bot._return_to_main_screen = Mock(return_value=True)
        bot._recover_interrupted_routine_foreground = Mock(return_value=False)
        self.assertEqual(bot._begin_due_routine(100), task)
        bot.routine_completed_steps.add("trucks_open")
        bot.routine_truck_checked_slots = {0, 1}
        bot._capture_screen_bgr = Mock(return_value=(self.frame("daily_limit_exhausted.png"), (0, 0)))
        bot._tap_routine_fallback = Mock(return_value=True)
        bot._save_routine_calibration_frame = Mock()
        with patch("buzzbot_app.time.time", return_value=101):
            self.assertTrue(bot._try_trucks_visual_fallback(task))
        self.assertEqual(bot.current_routine_index, 1)
        self.assertIsNone(bot.current_routine_task_id)
        self.assertFalse(bot.stop_event.is_set())
        self.assertTrue(bot.routine_mode)
        self.assertEqual(bot.routine_last_outcome["outcome"], "deferred_unavailable")
        self.assertEqual(bot.routine_next_run["trucks"], 3701)


if __name__ == "__main__":
    unittest.main()
