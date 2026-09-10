from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

from buzzbot_app import AutoClicker


class FactoryLoopFollowupTests(unittest.TestCase):
    def setUp(self):
        logger_patch = patch("buzzbot_app.logger")
        logger_patch.start()
        self.addCleanup(logger_patch.stop)

    def make_bot(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = Mock()
        bot.routine_completed_steps = {"pan_north", "select_refinery"}
        bot.routine_processing_factory_dynamic_selected_at = 100.0
        bot.routine_processing_factory_dynamic_target = (705, 285)
        bot.routine_processing_factory_radial_attempted = False
        bot.routine_processing_factory_recenter_attempted = True
        bot.routine_processing_factory_scan_index = 7
        bot.search_images = [
            {"uid": "152e2db2-317c-53cf-91a1-eb1dca8f3f30"},
            {"uid": "radial", "action": "open_processing_factory", "enabled": True},
        ]
        bot._locate_image = Mock(return_value=(None, None, 0.0))
        bot._validate_detected_match = Mock(return_value=(True, None))
        bot._execute_action = Mock(return_value=True)
        bot._tap_routine_fallback = Mock(return_value=True)
        bot._interruptible_sleep = Mock()
        bot._invalidate_capture = Mock()
        bot._capture_screen_bgr = Mock(return_value=(np.zeros((720, 1280, 3), dtype=np.uint8), (0, 0)))
        bot._is_settlement_screen_visible = Mock(return_value=True)
        bot._save_routine_calibration_frame = Mock()
        bot.set_status_message = Mock()
        bot.click_count = 0
        return bot

    def tick(self, bot, now):
        with patch("buzzbot_app.time.time", return_value=now):
            return bot._try_processing_factory_visual_fallback({"id": "processing_factory"})

    def test_unrecognised_escort_radial_menu_does_not_receive_inferred_click(self):
        bot = self.make_bot()
        self.assertFalse(self.tick(bot, 102.0))
        bot._execute_action.assert_not_called()
        bot._tap_routine_fallback.assert_not_called()
        bot.adb_client.tap.assert_not_called()
        self.assertNotIn("open_refinery", bot.routine_completed_steps)

    def test_rejected_building_advances_camera_instead_of_selecting_it_again(self):
        bot = self.make_bot()
        self.assertTrue(self.tick(bot, 105.0))
        bot.adb_client.keyevent.assert_called_once_with(4)
        self.assertNotIn("select_refinery", bot.routine_completed_steps)

        with patch("buzzbot_app.detect_back_confirmation_cancel_target", return_value=None), patch(
            "buzzbot_app.detect_processing_factory_target", return_value=(705, 285)
        ) as detect:
            self.assertTrue(self.tick(bot, 106.0))

        detect.assert_not_called()
        bot._tap_routine_fallback.assert_not_called()
        bot.adb_client.swipe.assert_called_once()
        self.assertEqual(bot.routine_processing_factory_scan_index, 8)
        self.assertFalse(bot.routine_processing_factory_force_scan)

    def test_late_header_confirmation_does_not_close_an_open_factory(self):
        bot = self.make_bot()
        location = SimpleNamespace(x=250, y=40)
        bot._locate_image.return_value = (location, (80, 18, 307, 44), 0.95)

        self.assertTrue(self.tick(bot, 106.0))

        self.assertIn("open_refinery", bot.routine_completed_steps)
        bot.adb_client.keyevent.assert_not_called()
        bot._execute_action.assert_not_called()
        bot._tap_routine_fallback.assert_not_called()

    def test_recognised_radial_uses_real_location_and_existing_header_verifier(self):
        bot = self.make_bot()
        location = SimpleNamespace(x=714, y=518)
        bot._locate_image.side_effect = [
            (None, None, 0.0), (location, (680, 490, 60, 60), 0.95),
        ]

        self.assertTrue(self.tick(bot, 102.0))

        bot._execute_action.assert_called_once_with(bot.search_images[1], location)
        self.assertIn("open_refinery", bot.routine_completed_steps)
        self.assertEqual(bot.click_count, 1)
        bot._tap_routine_fallback.assert_not_called()

    def test_rejected_radial_visual_validation_does_not_open_factory(self):
        bot = self.make_bot()
        location = SimpleNamespace(x=714, y=518)
        bot._locate_image.side_effect = [
            (None, None, 0.0), (location, (680, 490, 60, 60), 0.95),
        ]
        bot._validate_detected_match.return_value = (False, "COLOR")

        self.assertFalse(self.tick(bot, 102.0))

        bot._execute_action.assert_not_called()
        self.assertNotIn("open_refinery", bot.routine_completed_steps)

    def test_unconfirmed_opening_schedules_camera_scan_and_does_not_mark_success(self):
        bot = self.make_bot()
        location = SimpleNamespace(x=714, y=518)
        bot._locate_image.side_effect = [
            (None, None, 0.0), (location, (680, 490, 60, 60), 0.95),
        ]
        bot._execute_action.return_value = False

        self.assertTrue(self.tick(bot, 102.0))

        self.assertNotIn("select_refinery", bot.routine_completed_steps)
        self.assertNotIn("open_refinery", bot.routine_completed_steps)
        self.assertTrue(bot.routine_processing_factory_force_scan)

    def test_failed_camera_move_retains_scan_requirement(self):
        bot = self.make_bot()
        bot.routine_completed_steps.discard("select_refinery")
        bot.routine_processing_factory_force_scan = True
        bot.adb_client.swipe.side_effect = OSError("test swipe failed")
        with patch("buzzbot_app.detect_back_confirmation_cancel_target", return_value=None), patch(
            "buzzbot_app.detect_processing_factory_target", return_value=(705, 285)
        ):
            self.assertFalse(self.tick(bot, 106.0))
        self.assertTrue(bot.routine_processing_factory_force_scan)
        self.assertEqual(bot.routine_processing_factory_scan_index, 7)
        bot._tap_routine_fallback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
