from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from buzzbot.matching import (
    detect_truck_occupied_slot_targets,
    detect_truck_personal_slot_target,
    detect_truck_start_dispatch_target,
    detect_truck_transporting_close_target,
    truck_express_overview_is_visible,
)
from buzzbot_app import AutoClicker


class TruckTransportingRegressionTests(unittest.TestCase):
    def frame(self, name):
        frame = cv2.imread(str(Path(__file__).parent / "assets/trucks" / name))
        self.assertIsNotNone(frame)
        return frame

    def bot(self, frame):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_completed_steps = {"trucks_open", "truck_personal_slot_open"}
        bot.routine_action_counts = {}
        bot.routine_truck_current_slot = 0
        bot.routine_truck_checked_slots = set()
        bot._capture_screen_bgr = Mock(return_value=(frame, (0, 0)))
        bot._tap_routine_fallback = Mock(return_value=True)
        bot._save_routine_calibration_frame = Mock()
        bot._defer_current_routine_unavailable = Mock()
        return bot

    def test_orange_neighbor_does_not_turn_timer_into_unsent_label(self):
        frame = self.frame("orange_truck_in_transit_overview.png")
        for size in ((1280, 720), (1920, 1080)):
            with self.subTest(size=size):
                scaled = cv2.resize(frame, size)
                sx, sy = size[0] / 1280, size[1] / 720
                self.assertEqual(detect_truck_personal_slot_target(scaled), (round(768*sx), round(410*sy)))
                self.assertIn((round(207*sx), round(410*sy)), detect_truck_occupied_slot_targets(scaled))

    def test_view_button_on_transporting_card_is_never_start_or_overview(self):
        frame = self.frame("personal_transporting_card.png")
        for size in ((1280, 720), (1920, 1080)):
            with self.subTest(size=size):
                scaled = cv2.resize(frame, size)
                self.assertIsNone(detect_truck_start_dispatch_target(scaled))
                self.assertFalse(truck_express_overview_is_visible(scaled))
                self.assertEqual(detect_truck_transporting_close_target(scaled),
                                 (round(1057*size[0]/1280), round(80*size[1]/720)))

    def test_transporting_detection_requires_both_title_and_status(self):
        frame = self.frame("personal_transporting_card.png")
        for box in ((510, 55, 770, 105), (495, 510, 785, 553)):
            modified = frame.copy()
            x1, y1, x2, y2 = box
            modified[y1:y2, x1:x2] = 0
            self.assertIsNone(detect_truck_transporting_close_target(modified))

    def test_card_recovery_precedes_stale_escort_state_and_confirms_return(self):
        bot = self.bot(self.frame("personal_transporting_card.png"))
        bot.routine_completed_steps.add("truck_escort_selection_requested")
        task = {"id": "trucks", "settings": {}}
        self.assertTrue(bot._try_trucks_visual_fallback(task))
        self.assertEqual(bot._tap_routine_fallback.call_args.args[0], (1057, 80))
        self.assertEqual(bot.routine_truck_checked_slots, set())
        self.assertNotIn("max_dispatches", bot.routine_action_counts)
        bot._capture_screen_bgr.return_value = (self.frame("orange_truck_in_transit_overview.png"), (0, 0))
        self.assertTrue(bot._try_trucks_visual_fallback(task))
        self.assertEqual(bot.routine_truck_checked_slots, {0})
        self.assertEqual(bot.routine_completed_steps, {"trucks_open"})
        self.assertNotIn("max_dispatches", bot.routine_action_counts)
        self.assertNotIn("max_collections", bot.routine_action_counts)
        self.assertEqual(bot._tap_routine_fallback.call_count, 1)

    def test_unchanged_transporting_modal_is_bounded(self):
        bot = self.bot(self.frame("personal_transporting_card.png"))
        for _ in range(4):
            self.assertTrue(bot._try_trucks_visual_fallback({"id": "trucks", "settings": {}}))
        self.assertEqual(bot._tap_routine_fallback.call_count, 3)
        bot._defer_current_routine_unavailable.assert_called_once()
        self.assertEqual(bot.routine_truck_checked_slots, set())

    def test_failed_close_does_not_mark_the_slot_checked(self):
        bot = self.bot(self.frame("personal_transporting_card.png"))
        bot._tap_routine_fallback.return_value = False
        self.assertFalse(bot._try_trucks_visual_fallback({"id": "trucks"}))
        self.assertEqual(bot.routine_truck_checked_slots, set())
        self.assertNotIn("truck_transporting_close_requested", bot.routine_completed_steps)

    @patch("buzzbot_app.detect_truck_start_dispatch_target", return_value=(640, 585))
    def test_unconfirmed_repeated_escort_open_is_bounded(self, _start):
        bot = self.bot(np.zeros((720, 1280, 3), dtype=np.uint8))
        for _ in range(7):
            bot.routine_completed_steps = {"trucks_open", "truck_personal_slot_open"}
            self.assertTrue(bot._try_trucks_visual_fallback({"id": "trucks"}))
        self.assertEqual(bot._tap_routine_fallback.call_count, 6)
        bot._defer_current_routine_unavailable.assert_called_once()


if __name__ == "__main__":
    unittest.main()
