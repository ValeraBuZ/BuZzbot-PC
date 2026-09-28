from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from buzzbot.matching import (
    detect_truck_active_detail_back_target,
    detect_truck_ready_collection_target,
    truck_alliance_escort_is_visible,
)
from buzzbot_app import AutoClicker


class TruckStagingRegressionTests(unittest.TestCase):
    def staging_frame(self):
        frame = cv2.imread(str(Path(__file__).parent / "assets/trucks/alliance_staging.png"))
        self.assertIsNotNone(frame)
        return frame

    def make_bot(self, frame):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_completed_steps = {"trucks_open"}
        bot.routine_action_counts = {}
        bot._capture_screen_bgr = Mock(return_value=(frame, (0, 0)))
        bot._tap_routine_fallback = Mock(return_value=True)
        bot._is_settlement_screen_visible = Mock(return_value=True)
        bot._save_routine_calibration_frame = Mock()
        bot._defer_current_routine_unavailable = Mock()
        return bot

    def test_real_alliance_staging_is_not_a_personal_truck_detail_or_collection(self):
        frame = self.staging_frame()
        for size in ((1280, 720), (1920, 1080)):
            with self.subTest(size=size):
                scaled = cv2.resize(frame, size)
                self.assertTrue(truck_alliance_escort_is_visible(scaled))
                self.assertIsNone(detect_truck_active_detail_back_target(scaled))
                self.assertIsNone(detect_truck_ready_collection_target(scaled))

    def test_staging_uses_actual_back_arrow_then_defers_without_claiming_dispatch(self):
        bot = self.make_bot(self.staging_frame())
        self.assertTrue(bot._try_trucks_visual_fallback({"id": "trucks", "settings": {}}))
        self.assertEqual(bot._tap_routine_fallback.call_args.args[0], (42, 42))
        bot._defer_current_routine_unavailable.assert_called_once()
        self.assertEqual(bot.routine_action_counts, {})
        self.assertNotIn("truck_dispatch_pending_verification", bot.routine_completed_steps)

    @patch("buzzbot_app.detect_truck_active_detail_back_target", return_value=(1143, 181))
    @patch("buzzbot_app.truck_formation_is_visible", return_value=False)
    @patch("buzzbot_app.truck_alliance_escort_is_visible", return_value=False)
    @patch("buzzbot_app.truck_express_overview_is_visible", return_value=False)
    def test_unrecognized_unchanged_detail_has_a_bounded_close_loop(self, *mocks):
        bot = self.make_bot(np.zeros((720, 1280, 3), dtype=np.uint8))
        task = {"id": "trucks", "settings": {}}
        for _ in range(4):
            self.assertTrue(bot._try_trucks_visual_fallback(task))
        self.assertEqual(bot._tap_routine_fallback.call_count, 3)
        bot._defer_current_routine_unavailable.assert_called_once()
        self.assertEqual(bot.routine_action_counts, {"truck_unexpected_detail_closes": 3})
        self.assertNotIn("trucks_complete", bot.routine_completed_steps)

    @patch("buzzbot_app.detect_truck_active_detail_back_target", return_value=(1143, 181))
    @patch("buzzbot_app.truck_formation_is_visible", return_value=False)
    @patch("buzzbot_app.truck_alliance_escort_is_visible", return_value=False)
    @patch("buzzbot_app.truck_express_overview_is_visible", return_value=False)
    def test_failed_close_input_does_not_claim_a_successful_action(self, *mocks):
        bot = self.make_bot(np.zeros((720, 1280, 3), dtype=np.uint8))
        bot._tap_routine_fallback.return_value = False
        self.assertFalse(bot._try_trucks_visual_fallback({"id": "trucks", "settings": {}}))
        self.assertEqual(bot.routine_action_counts, {})


if __name__ == "__main__":
    unittest.main()
