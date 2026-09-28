from copy import deepcopy
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from buzzbot.matching import detect_offline_resources_confirm_target
from buzzbot_app import ACCOUNT_SWITCH_TEMPLATE_GROUP, AutoClicker
import test_account_navigation_retry as navigation_fixture


ASSETS = Path(__file__).parent / "assets/accounts"


class AccountSwitchLatencyTests(unittest.TestCase):
    def make_bot(self):
        bot = navigation_fixture.AccountNavigationRetryTests().make_bot()
        bot.account_switch_selected_at = 100.0
        bot.routine_completed_steps = {
            "account_switch_igg_id_selected", "account_switch_igg_game_confirmed",
        }
        task = {"id": "__account_switch__", "enabled": True,
                "group": ACCOUNT_SWITCH_TEMPLATE_GROUP,
                "settings": {"login_method": "igg", "_expected_igg_id": "1234567890"}}
        return bot, task

    def test_resource_report_recognition_includes_toasts_and_scaled_frames(self):
        for name in ("offline_resources.png", "offline_resources_toast.png"):
            frame = cv2.imread(str(ASSETS / name))
            for scale in (1, 0.75):
                with self.subTest(name=name, scale=scale):
                    scaled = cv2.resize(frame, None, fx=scale, fy=scale)
                    self.assertEqual(detect_offline_resources_confirm_target(scaled),
                                     (round(824 * scale), round(644 * scale)))
            for region in ((slice(148, 193), slice(510, 920)),
                           (slice(616, 674), slice(670, 980))):
                partial = frame.copy()
                partial[region] = 0
                self.assertIsNone(detect_offline_resources_confirm_target(partial))
        self.assertIsNone(detect_offline_resources_confirm_target(
            cv2.imread(str(ASSETS / "loaded_settlement.png"))))
        self.assertIsNone(detect_offline_resources_confirm_target(np.zeros((720, 1280, 3), np.uint8)))

    def test_loaded_report_ends_wait_but_does_not_establish_identity(self):
        bot, task = self.make_bot()
        frame = cv2.imread(str(ASSETS / "offline_resources.png"))
        with patch("buzzbot_app.time.time", return_value=115):
            self.assertTrue(bot._wait_for_account_switch_game_load(task, frame))
            self.assertFalse(bot._wait_for_account_switch_game_load(task, frame))
        bot._tap_routine_fallback.assert_called_once()
        self.assertEqual(bot.account_switch_selected_at, 100)
        self.assertFalse(bot._account_switch_main_screen_confirmed(task))

    def test_bright_map_confirmation_is_accepted_without_restart_or_skipping_identity(self):
        bot, task = self.make_bot()
        bot.routine_completed_steps.discard('account_switch_igg_game_confirmed')
        frame = cv2.imread(str(ASSETS / 'igg_confirmation_bright_map.png'))
        with patch('buzzbot_app.time.time', return_value=105):
            self.assertTrue(bot._try_account_switch_igg_game_confirmation(task,frame))
        bot._tap_routine_fallback.assert_called_once_with(
            (784,508),('account_switch_igg_game_confirm',784,508),
            'IGG ID выбран: подтверждаю вход в игру')
        self.assertIn('account_switch_igg_game_confirmed',bot.routine_completed_steps)
        self.assertFalse(bot._account_switch_main_screen_confirmed(task))
        bot._return_to_main_screen.assert_not_called()

    def test_failed_report_tap_keeps_loading_gate(self):
        bot, task = self.make_bot()
        bot._tap_routine_fallback.return_value = False
        frame = cv2.imread(str(ASSETS / "offline_resources.png"))
        with patch("buzzbot_app.time.time", return_value=115):
            self.assertTrue(bot._wait_for_account_switch_game_load(task, frame))
        self.assertNotIn("account_switch_game_load_observed", bot.routine_completed_steps)

    def test_back_recovery_cannot_restart_the_loading_deadline(self):
        bot, task = self.make_bot()
        bot._is_game_home_visible.return_value = False
        with patch("buzzbot_app.time.time", return_value=165):
            self.assertTrue(bot._try_account_switch_return_to_main(task))
            self.assertFalse(bot._wait_for_account_switch_game_load(task, None))
        self.assertEqual(bot.account_switch_selected_at, 100)
        self.assertNotIn("_verified_igg_id", task["settings"])

    def test_observed_loaded_report_allows_early_panel_recovery_without_accepting_identity(self):
        bot, task = self.make_bot()
        bot._is_game_home_visible.return_value = False
        with patch("buzzbot_app.time.time", return_value=120):
            self.assertFalse(bot._try_account_switch_return_to_main(task))
            bot.routine_completed_steps.add("account_switch_game_load_observed")
            self.assertTrue(bot._try_account_switch_return_to_main(task))
        bot._return_to_main_screen.assert_called_once()
        self.assertEqual(bot.account_switch_selected_at,100)
        self.assertFalse(bot._account_switch_main_screen_confirmed(task))

    def test_verified_account_finishes_before_sdk_inspection_or_navigation(self):
        bot, task = self.make_bot()
        task["settings"]["_verified_igg_id"] = "1234567890"
        bot.routine_completed_steps.add("account_switch_igg_loaded_id_verified")
        bot._finish_current_routine = Mock()
        with patch("buzzbot_app.detect_igg_game_login_ok_target", return_value=None):
            self.assertTrue(bot._try_account_switch_igg_game_confirmation(task))
        bot._finish_current_routine.assert_called_once()
        self.assertTrue(bot.account_switch_confirmed)
        bot.adb_client.ui_xml.assert_not_called()

    def test_group_toggle_cannot_restart_active_transition_or_clear_its_id_steps(self):
        bot, task = self.make_bot()
        bot.account_switch_task = task
        bot.routine_only_task_id = "__account_switch__"
        bot.current_routine_task_id = "__account_switch__"
        bot.get_routine_task = lambda _: task
        bot.groups = {ACCOUNT_SWITCH_TEMPLATE_GROUP: False}
        before = set(bot.routine_completed_steps)
        self.assertIs(bot._begin_due_routine(120), task)
        self.assertEqual(bot.routine_completed_steps, before)
        self.assertEqual(bot.routine_task_started_at, 100)

    def test_profile_selection_during_transition_preserves_settings_and_state(self):
        for selected in ("source", "target"):
            bot, task = self.make_bot()
            bot.is_running = True
            bot.account_switch_task = task
            bot.current_account_id = "source"
            bot.current_routine_task_id = "__account_switch__"
            bot.account_profiles = [{"id": name, "task_settings": {"heal": {"troop_count": 500}}}
                                    for name in ("source", "target")]
            before = deepcopy(bot.account_profiles)
            self.assertEqual(bot.select_account_profile(selected), selected == "source")
            self.assertEqual(bot.current_account_id, "source")
            self.assertEqual(bot.current_routine_task_id, "__account_switch__")
            self.assertEqual(bot.account_profiles, before)

    def test_sdk_checks_share_inspection_until_input_invalidates_it(self):
        bot, task = self.make_bot()
        bot.adb_client.ui_xml.return_value = "<hierarchy/>"
        bot._adb_capture_lock = threading.Lock()
        for _ in range(4):
            self.assertEqual(bot._account_switch_ui_xml(task), "<hierarchy/>")
        bot.adb_client.ui_xml.assert_called_once()
        AutoClicker._invalidate_capture(bot)
        bot.adb_client.ui_xml.return_value = "<hierarchy><node/></hierarchy>"
        self.assertEqual(bot._account_switch_ui_xml(task), "<hierarchy><node/></hierarchy>")
        self.assertEqual(bot.adb_client.ui_xml.call_count, 2)


if __name__ == "__main__":
    unittest.main()
