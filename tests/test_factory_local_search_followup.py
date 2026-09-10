from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from buzzbot.matching import detect_processing_factory_target
from buzzbot_app import AutoClicker, PROCESSING_FACTORY_LOCAL_SCAN_PATTERN, PROCESSING_FACTORY_SCAN_PATTERN


class FactoryLocalSearchTests(unittest.TestCase):
    def make_bot(self, frame=None):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = Mock()
        bot.routine_completed_steps = {"pan_north"}
        bot.routine_processing_factory_recenter_attempted = True
        bot.routine_processing_factory_scan_index = 0
        bot.routine_processing_factory_dynamic_selected_at = 0.0
        bot.routine_processing_factory_dynamic_target = None
        bot.routine_processing_factory_radial_attempted = False
        bot.routine_processing_factory_force_scan = False
        bot.search_images = []
        bot._capture_screen_bgr = Mock(return_value=(frame if frame is not None else np.zeros((720, 1280, 3), np.uint8), (0, 0)))
        bot._is_settlement_screen_visible = Mock(return_value=True)
        bot._locate_image = Mock(return_value=(None, None, 0.0))
        bot._validate_detected_match = Mock(return_value=(True, ""))
        bot._execute_action = Mock(return_value=True)
        bot._tap_routine_fallback = Mock(return_value=True)
        bot._save_routine_calibration_frame = Mock()
        bot._invalidate_capture = Mock()
        bot._interruptible_sleep = Mock()
        bot.set_status_message = Mock()
        bot.click_count = 0
        return bot

    def tick(self, bot, now=100.0, task_id="processing_factory"):
        with patch("buzzbot_app.logger"), patch("buzzbot_app.time.time", return_value=now), patch("buzzbot_app.detect_back_confirmation_cancel_target", return_value=None):
            return bot._try_processing_factory_visual_fallback({"id": task_id})

    def test_original_wide_route_remains_exactly_after_eight_local_steps(self):
        original = (("left",) * 12 + ("up",) * 10 + ("right",) * 12
                    + ("down",) * 3 + ("left",) * 12 + ("down",) * 3
                    + ("right",) * 12 + ("down",) * 3 + ("left",) * 12
                    + ("down",) * 3 + ("right",) * 12)
        self.assertEqual(len(original), 94)
        self.assertEqual(len(PROCESSING_FACTORY_LOCAL_SCAN_PATTERN), 8)
        self.assertEqual(PROCESSING_FACTORY_SCAN_PATTERN[8:], original)

    def test_recenter_rejects_unchanged_settlement_with_shared_home_markers(self):
        for task_id in ("processing_factory", "processing_contest"):
            with self.subTest(task_id=task_id):
                bot = self.make_bot()
                bot.routine_processing_factory_recenter_attempted = False
                bot.routine_processing_factory_scan_index = 17
                bot._is_main_screen_visible = Mock(return_value=True)
                bot._switch_to_settlement_screen = Mock(return_value=True)
                bot.routine_completed_steps.add("processing_factory_event_panel_checked")

                self.assertFalse(self.tick(bot, task_id=task_id))

                self.assertFalse(bot.routine_processing_factory_recenter_attempted)
                self.assertEqual(bot.routine_processing_factory_scan_index, 17)
                self.assertEqual(bot.routine_completed_steps, {"pan_north", "processing_factory_event_panel_checked"})
                bot.adb_client.tap.assert_called_once_with(65, 655)
                self.assertEqual(bot._interruptible_sleep.call_count, 5)
                bot._switch_to_settlement_screen.assert_not_called()
                bot.adb_client.swipe.assert_not_called()

    def test_recenter_waits_for_settlement_marker_to_disappear(self):
        bot = self.make_bot()
        bot.routine_processing_factory_recenter_attempted = False
        # First call is the starting settlement; the first post-tap frame still
        # shows it. Only the second post-tap frame confirms the world surface.
        bot._is_settlement_screen_visible.side_effect = [True, True, False]
        bot._is_main_screen_visible = Mock(return_value=True)
        bot._switch_to_settlement_screen = Mock(return_value=True)
        bot.routine_completed_steps.add("processing_factory_event_panel_checked")

        self.assertTrue(self.tick(bot))

        self.assertEqual(bot._interruptible_sleep.call_count, 2)
        bot._switch_to_settlement_screen.assert_called_once()
        self.assertTrue(bot.routine_processing_factory_recenter_attempted)
        bot.adb_client.tap.assert_called_once_with(65, 655)
        bot.adb_client.swipe.assert_not_called()

    def test_recenter_does_not_complete_when_return_to_settlement_fails(self):
        bot = self.make_bot()
        bot.routine_processing_factory_recenter_attempted = False
        bot.routine_processing_factory_scan_index = 17
        bot._is_settlement_screen_visible.side_effect = [True, False]
        bot._is_main_screen_visible = Mock(return_value=True)
        bot._switch_to_settlement_screen = Mock(return_value=False)
        bot.routine_completed_steps.add("processing_factory_event_panel_checked")

        self.assertFalse(self.tick(bot))

        self.assertFalse(bot.routine_processing_factory_recenter_attempted)
        self.assertEqual(bot.routine_processing_factory_scan_index, 17)
        self.assertEqual(bot.routine_completed_steps, {"pan_north", "processing_factory_event_panel_checked"})
        bot._switch_to_settlement_screen.assert_called_once()
        bot.adb_client.swipe.assert_not_called()

    def test_each_local_step_checks_frame_then_performs_paired_slow_gesture(self):
        expected = [(640, 450, 640, 330, 600), (640, 330, 640, 450, 600),
                    (640, 330, 640, 450, 600), (640, 450, 640, 330, 600),
                    (790, 400, 490, 400, 600), (490, 400, 790, 400, 600),
                    (490, 400, 790, 400, 600), (790, 400, 490, 400, 600)]
        for task_id in ("processing_factory", "processing_contest"):
            bot = self.make_bot()
            with patch("buzzbot_app.detect_processing_factory_target", return_value=None) as detector:
                for index, gesture in enumerate(expected):
                    self.assertTrue(self.tick(bot, task_id=task_id))
                    bot.adb_client.swipe.assert_called_with(*gesture)
                    self.assertEqual(bot.routine_processing_factory_scan_index, index + 1)
                    self.assertEqual(detector.call_count, index + 1)
                    self.assertEqual(bot._save_routine_calibration_frame.call_count, index + 1)
            self.tick(bot, task_id=task_id)
            bot.adb_client.swipe.assert_called_with(980, 420, 360, 420, 300)

    def test_real_local_candidate_is_captured_and_selected_without_extra_camera_move(self):
        frame = cv2.imread(str(Path(__file__).parent / "assets/processing_factory/local_north_furnaces.png"))
        self.assertIsNotNone(frame)
        self.assertEqual(detect_processing_factory_target(frame), (831, 189))
        bot = self.make_bot(frame)
        bot.routine_processing_factory_scan_index = 3
        self.assertTrue(self.tick(bot))
        self.assertIn("select_refinery", bot.routine_completed_steps)
        self.assertNotIn("open_refinery", bot.routine_completed_steps)
        self.assertEqual(bot.routine_processing_factory_scan_index, 3)
        self.assertEqual(bot._tap_routine_fallback.call_args.args[0], (831, 189))
        bot._save_routine_calibration_frame.assert_called_once()
        bot.adb_client.swipe.assert_not_called()
        bot._execute_action.assert_not_called()

    def test_rejected_local_selection_keeps_pending_return_gesture(self):
        bot = self.make_bot()
        bot.routine_processing_factory_scan_index = 3
        with patch("buzzbot_app.detect_processing_factory_target", return_value=(831, 189)):
            self.tick(bot)
            self.tick(bot, 105.0)
            self.assertNotIn("select_refinery", bot.routine_completed_steps)
            self.assertTrue(bot.routine_processing_factory_force_scan)
            self.tick(bot, 106.0)
        bot._tap_routine_fallback.assert_called_once()
        bot.adb_client.keyevent.assert_called_once_with(4)
        bot.adb_client.swipe.assert_called_once_with(640, 450, 640, 330, 600)
        self.assertEqual(bot.routine_processing_factory_scan_index, 4)

    def test_scaled_local_swipe_preserves_duration(self):
        bot = self.make_bot(np.zeros((1080, 1920, 3), np.uint8))
        self.tick(bot)
        bot.adb_client.swipe.assert_called_once_with(960, 675, 960, 495, 600)

    def test_non_settlement_never_starts_local_camera_gesture(self):
        bot = self.make_bot()
        bot._is_settlement_screen_visible.return_value = False
        self.assertFalse(self.tick(bot))
        bot.adb_client.swipe.assert_not_called()
        self.assertEqual(bot.routine_processing_factory_scan_index, 0)

    def test_local_candidate_still_requires_recognized_radial_and_header_guard(self):
        bot = self.make_bot()
        bot.routine_completed_steps.add("select_refinery")
        bot.routine_processing_factory_dynamic_selected_at = 100.0
        bot.routine_processing_factory_dynamic_target = (831, 189)
        image = {"enabled": True, "action": "open_processing_factory"}
        bot.search_images = [image]
        location = SimpleNamespace(x=822, y=330)
        bot._locate_image.return_value = (location, (780, 300, 60, 50), .95)
        bot._execute_action.return_value = False
        self.assertTrue(self.tick(bot, 102.0))
        bot._execute_action.assert_called_once_with(image, location)
        self.assertNotIn("open_refinery", bot.routine_completed_steps)
        self.assertNotIn("select_refinery", bot.routine_completed_steps)
        self.assertTrue(bot.routine_processing_factory_force_scan)


if __name__ == "__main__":
    unittest.main()
