import threading
import unittest
from unittest.mock import Mock, patch

import numpy as np

from buzzbot_app import AutoClicker, GAME_PACKAGE


class AccountNavigationRetryTests(unittest.TestCase):
    def make_bot(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = Mock()
        bot.adb_client.current_foreground_package.return_value = GAME_PACKAGE
        bot.account_switch_selected_at = 0.0
        bot.account_switch_error = ""
        bot.routine_completed_steps = set()
        bot.routine_task_started_at = 100.0
        bot.search_images = []
        bot._capture_screen_bgr = Mock(return_value=(np.zeros((720, 1280, 3), dtype=np.uint8), (0, 0)))
        bot._try_equipment_report_overlay = Mock(return_value=False)
        bot._is_main_screen_visible = Mock(return_value=True)
        bot._is_settlement_screen_visible = Mock(return_value=True)
        bot._is_game_home_visible = Mock(return_value=True)
        bot._return_to_main_screen = Mock(return_value=True)
        bot._tap_routine_fallback = Mock(return_value=True)
        bot._invalidate_capture = Mock()
        bot._interruptible_sleep = Mock()
        bot._save_routine_calibration_frame = Mock()
        bot.set_status_message = Mock()
        bot.stop_event = threading.Event()
        return bot

    @patch("buzzbot_app.detect_game_event_overlay_close_target", return_value=None)
    def test_profile_open_is_not_undone_when_settings_template_misses_a_frame(self, _overlay):
        bot = self.make_bot()
        task = {"id": "__account_switch__", "settings": {"login_method": "igg"}}
        self.assertTrue(bot._try_account_switch_visual_fallback(task))
        self.assertIn("account_switch_navigation_started", bot.routine_completed_steps)
        bot._is_main_screen_visible.return_value = False
        self.assertFalse(bot._try_account_switch_visual_fallback(task))
        bot._return_to_main_screen.assert_not_called()
        self.assertEqual(bot._tap_routine_fallback.call_count, 1)
        self.assertFalse(bot._account_switch_main_screen_confirmed(task))

    @patch("buzzbot_app.detect_game_event_overlay_close_target", return_value=None)
    def test_failed_profile_tap_does_not_claim_navigation_or_identity(self, _overlay):
        bot = self.make_bot()
        bot._tap_routine_fallback.return_value = False
        self.assertFalse(bot._try_account_switch_visual_fallback({"id": "__account_switch__", "settings": {}}))
        self.assertEqual(bot.routine_completed_steps, set())

    def test_late_mismatch_has_one_bounded_retry_without_moving_original_start(self):
        bot = self.make_bot()
        bot.account_switch_selected_at = 300.0
        bot.routine_completed_steps = {"account_switch_igg_id_selected"}
        task = {"id": "__account_switch__", "timeout_seconds": 300.0, "settings": {
            "login_method": "igg", "_expected_igg_id": "1234567890",
            "_identity_check_started": True, "_identity_check_started_at": 380.0,
        }}
        with patch("buzzbot_app.time.time", return_value=390.0), patch("buzzbot_app.read_game_igg_id", return_value="9999999999"):
            self.assertTrue(bot._try_account_switch_verify_identity(task, None))
            self.assertTrue(bot._try_account_switch_verify_identity(task, None))
        self.assertEqual(task["timeout_seconds"], 470.0)
        self.assertEqual(bot.routine_task_started_at, 100.0)
        self.assertEqual(bot.account_switch_selected_at, 0.0)
        self.assertFalse(bot._account_switch_main_screen_confirmed(task))
        bot.account_switch_selected_at = 460.0
        bot.routine_completed_steps = {"account_switch_igg_id_selected"}
        task["settings"].update({"_identity_check_started": True, "_identity_check_started_at": 480.0})
        with patch("buzzbot_app.time.time", return_value=490.0), patch("buzzbot_app.read_game_igg_id", return_value="9999999999"):
            bot._try_account_switch_verify_identity(task, None)
            bot._try_account_switch_verify_identity(task, None)
        self.assertEqual(task["timeout_seconds"], 470.0)
        self.assertIn("после повторного входа", bot.account_switch_error)

    @patch("buzzbot_app.detect_igg_game_login_ok_target", return_value=None)
    def test_previous_home_during_pending_confirmation_cannot_start_id_navigation(self, _detect):
        bot = self.make_bot()
        bot.account_switch_selected_at = 100.0
        bot.routine_completed_steps = {"account_switch_igg_id_selected"}
        bot._try_account_switch_verify_identity = Mock(return_value=True)
        task = {"id": "__account_switch__", "settings": {"login_method": "igg"}}
        for now in (112.0, 120.0, 129.9):
            with patch("buzzbot_app.time.time", return_value=now):
                self.assertTrue(bot._try_account_switch_igg_game_confirmation(task))
        bot._try_account_switch_verify_identity.assert_not_called()
        bot._tap_routine_fallback.assert_not_called()
        self.assertFalse(bot._account_switch_main_screen_confirmed(task))
        with patch("buzzbot_app.time.time", return_value=130.0):
            self.assertTrue(bot._try_account_switch_igg_game_confirmation(task))
        bot._try_account_switch_verify_identity.assert_called_once()

    @patch("buzzbot_app.detect_igg_game_login_ok_target", return_value=(784, 508))
    def test_late_final_confirmation_is_accepted_inside_grace_without_claiming_identity(self, _detect):
        bot = self.make_bot()
        bot.account_switch_selected_at = 100.0
        bot.routine_completed_steps = {"account_switch_igg_id_selected"}
        bot._try_account_switch_verify_identity = Mock()
        task = {"id": "__account_switch__", "settings": {"login_method": "igg"}}
        with patch("buzzbot_app.time.time", return_value=125.0):
            self.assertTrue(bot._try_account_switch_igg_game_confirmation(task))
        bot._tap_routine_fallback.assert_called_once()
        bot._try_account_switch_verify_identity.assert_not_called()
        self.assertIn("account_switch_igg_game_confirmed", bot.routine_completed_steps)
        self.assertFalse(bot._account_switch_main_screen_confirmed(task))

    @patch("buzzbot_app.detect_igg_game_login_ok_target", return_value=None)
    def test_confirmed_button_does_not_allow_navigation_during_game_load(self, _detect):
        bot = self.make_bot()
        bot.account_switch_selected_at = 100.0
        bot.routine_completed_steps = {"account_switch_igg_id_selected", "account_switch_igg_game_confirmed"}
        bot._try_account_switch_verify_identity = Mock(return_value=True)
        task = {"id": "__account_switch__", "settings": {"login_method": "igg"}}
        for now in (112.0, 115.0, 130.0, 159.9):
            with patch("buzzbot_app.time.time", return_value=now):
                self.assertTrue(bot._try_account_switch_igg_game_confirmation(task))
        bot._try_account_switch_verify_identity.assert_not_called()
        bot._tap_routine_fallback.assert_not_called()
        with patch("buzzbot_app.time.time", return_value=160.0):
            self.assertTrue(bot._try_account_switch_igg_game_confirmation(task))
        bot._try_account_switch_verify_identity.assert_called_once()

    def test_direct_id_verification_cannot_reject_previous_id_during_load(self):
        bot = self.make_bot()
        bot.account_switch_selected_at = 100.0
        bot.routine_completed_steps = {"account_switch_igg_id_selected", "account_switch_igg_game_confirmed"}
        task = {"id": "__account_switch__", "settings": {"login_method": "igg", "_expected_igg_id": "1234567890"}}
        with patch("buzzbot_app.time.time", return_value=120.0), patch("buzzbot_app.read_game_igg_id") as read_id:
            self.assertTrue(bot._try_account_switch_verify_identity(task, None))
        read_id.assert_not_called()
        self.assertNotIn("_identity_retry", task["settings"])
        self.assertEqual(bot.account_switch_error, "")

    def test_verify_only_resume_does_not_wait_for_a_login_that_was_not_started(self):
        bot = self.make_bot()
        bot.account_switch_selected_at = 100.0
        bot.routine_completed_steps = {"account_switch_igg_game_confirmed"}
        task = {"id": "__account_switch__", "settings": {"login_method": "igg", "_verify_only": True}}
        with patch("buzzbot_app.time.time", return_value=110.0):
            self.assertFalse(bot._wait_for_account_switch_game_load(task, None))

    def test_loading_diagnostics_are_bounded_and_do_not_extend_the_deadline(self):
        bot = self.make_bot()
        bot.account_switch_selected_at = 100.0
        bot.routine_completed_steps = {"account_switch_igg_game_confirmed"}
        task = {"id": "__account_switch__", "settings": {"login_method": "igg"}}
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        for now in (109.0, 110.0, 115.0, 130.0, 145.0, 159.0):
            with patch("buzzbot_app.time.time", return_value=now):
                self.assertTrue(bot._wait_for_account_switch_game_load(task, frame))
        self.assertEqual(bot._save_routine_calibration_frame.call_count, 4)
        self.assertEqual(bot.account_switch_selected_at, 100.0)
        with patch("buzzbot_app.time.time", return_value=160.0):
            self.assertFalse(bot._wait_for_account_switch_game_load(task, frame))


if __name__ == "__main__":
    unittest.main()
