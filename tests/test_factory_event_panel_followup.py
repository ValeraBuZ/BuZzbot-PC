from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from buzzbot.matching import detect_settlement_event_panel_collapse_target
from buzzbot_app import AutoClicker


FIXTURE = Path(__file__).parent / "assets/processing_factory/expanded_event_ribbon.png"
CHECKED = "processing_factory_event_panel_checked"


class FactoryEventPanelTests(unittest.TestCase):
    def make_bot(self, frame=None):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = Mock()
        bot.routine_completed_steps = {"pan_north"}
        bot.routine_processing_factory_recenter_attempted = False
        bot.routine_processing_factory_scan_index = 17
        bot.routine_processing_factory_dynamic_selected_at = 0.0
        bot._is_settlement_screen_visible = Mock(return_value=True)
        bot._is_main_screen_visible = Mock(return_value=True)
        bot._switch_to_settlement_screen = Mock(return_value=True)
        bot._capture_screen_bgr = Mock(return_value=(cv2.imread(str(FIXTURE)) if frame is None else frame, (0, 0)))
        bot._tap_routine_fallback = Mock(return_value=True)
        bot._save_routine_calibration_frame = Mock()
        bot._invalidate_capture = Mock()
        bot._interruptible_sleep = Mock()
        bot.set_status_message = Mock()
        bot.click_count = 0
        bot.search_images = []
        return bot

    @staticmethod
    def tick(bot, task_id="processing_factory"):
        with patch("buzzbot_app.logger"), patch("buzzbot_app.detect_processing_factory_target", return_value=None), patch("buzzbot_app.detect_back_confirmation_cancel_target", return_value=None):
            return bot._try_processing_factory_visual_fallback({"id": task_id})

    def test_real_two_row_ribbon_collapses_before_recenter_for_both_tasks(self):
        self.assertEqual(detect_settlement_event_panel_collapse_target(cv2.imread(str(FIXTURE))), (463, 83))
        for task_id in ("processing_factory", "processing_contest"):
            with self.subTest(task_id=task_id):
                bot = self.make_bot()
                self.assertTrue(self.tick(bot, task_id))
                bot._tap_routine_fallback.assert_called_once()
                self.assertEqual(bot._tap_routine_fallback.call_args.args[0], (463, 83))
                self.assertEqual(bot._tap_routine_fallback.call_args.args[1][0], "processing_factory_event_panel_collapse")
                self.assertIn(CHECKED, bot.routine_completed_steps)
                self.assertFalse(bot.routine_processing_factory_recenter_attempted)
                self.assertEqual(bot.routine_processing_factory_scan_index, 17)
                bot._interruptible_sleep.assert_called_once_with(0.6)
                bot.adb_client.tap.assert_not_called()
                bot.adb_client.swipe.assert_not_called()

    def test_recognized_ribbon_outside_settlement_does_not_cause_input(self):
        bot = self.make_bot()
        bot._is_settlement_screen_visible.return_value = False
        self.assertFalse(self.tick(bot))
        self.assertNotIn(CHECKED, bot.routine_completed_steps)
        bot._tap_routine_fallback.assert_not_called()
        bot._capture_screen_bgr.assert_not_called()
        bot.adb_client.tap.assert_not_called()
        bot.adb_client.swipe.assert_not_called()

    def test_no_ribbon_keeps_existing_scan_route(self):
        bot = self.make_bot(np.zeros((720, 1280, 3), np.uint8))
        bot.routine_processing_factory_recenter_attempted = True
        self.assertTrue(self.tick(bot))
        self.assertIn(CHECKED, bot.routine_completed_steps)
        bot._tap_routine_fallback.assert_not_called()
        bot.adb_client.swipe.assert_called_once()
        self.assertEqual(bot.routine_processing_factory_scan_index, 18)

    def test_ribbon_is_not_toggled_again_during_same_routine(self):
        bot = self.make_bot()
        self.assertTrue(self.tick(bot))
        bot.routine_processing_factory_recenter_attempted = True
        self.assertTrue(self.tick(bot))
        bot._tap_routine_fallback.assert_called_once()
        bot.adb_client.swipe.assert_called_once()

    def test_rejected_collapse_does_not_mark_checked_or_start_navigation(self):
        bot = self.make_bot()
        bot._tap_routine_fallback.return_value = False
        self.assertFalse(self.tick(bot))
        self.assertNotIn(CHECKED, bot.routine_completed_steps)
        self.assertFalse(bot.routine_processing_factory_recenter_attempted)
        self.assertEqual(bot.routine_processing_factory_scan_index, 17)
        bot.adb_client.tap.assert_not_called()
        bot.adb_client.swipe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
