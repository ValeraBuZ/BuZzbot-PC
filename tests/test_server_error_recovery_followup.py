import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from buzzbot.adb import AdbError
from buzzbot.matching import imread_unicode
from buzzbot_app import (
    ACCOUNT_SWITCH_RETRY_SECONDS,
    AutoClicker,
    GAME_LOGIN_RESTART_SECONDS,
    GAME_PACKAGE,
    GAME_SERVER_RETRY_SECONDS,
    _BotActionInterrupted,
)


class ServerErrorRecoveryTests(unittest.TestCase):
    def make_bot(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_serial = "mock-device"
        bot.adb_client = SimpleNamespace(
            current_foreground_package=Mock(return_value=GAME_PACKAGE),
            force_stop_package=Mock(),
            launch_package=Mock(),
            ui_xml=Mock(return_value='<node content-desc="Game view" />'),
        )
        bot.search_images = []
        bot.routine_task_started_at = 1000.0
        bot.routine_last_action_time = 1000.0
        bot.routine_home_recovery_attempted = False
        bot.routine_login_home_recovery_at = 0.0
        bot.routine_login_restart_count = 0
        bot.routine_login_server_retry_at = 0.0
        bot.routine_login_server_error_active = False
        bot.routine_current_had_action = False
        bot.routine_completed_steps = set()
        bot.routine_idle_confirmation_count = 0
        bot.blocked_coords = {}
        bot._invalidate_capture = Mock()
        bot._interruptible_sleep = Mock()
        bot._is_game_home_visible = Mock(return_value=False)
        bot._try_equipment_report_overlay = Mock(return_value=False)
        bot._return_to_main_screen = Mock(return_value=False)
        bot.set_status_message = Mock()
        bot.save_config = Mock()
        bot._defer_current_routine_no_action = Mock()
        bot.routine_tasks = [
            {"id": "game_login", "enabled": True},
            {"id": "vip_rewards", "enabled": True},
            {"id": "mysterious_merchant", "enabled": True},
            {"id": "trucks", "enabled": True},
        ]
        bot.current_routine_task_id = "game_login"
        bot.current_routine_index = 0
        bot.routine_next_run = {}
        bot.routine_forced_task_active_id = None
        bot.routine_forced_task_return_index = None
        bot.current_account_id = "old-profile"
        bot.routine_pass_completed = True
        bot.account_rotation_enabled = True
        bot.account_switch_failure_count = 0
        bot.account_switch_selected_at = 0.0
        bot.account_switch_confirmed = False
        bot.account_switch_probe_ready = False
        bot.account_switch_auto_login_attempted = False
        bot.account_switch_error = ""
        bot.select_account_profile = Mock()
        bot.stop_event = threading.Event()
        bot.stop_hotkey_pressed = False
        bot.is_paused = False
        bot._frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        bot._capture_screen_bgr = Mock(return_value=(bot._frame, (0, 0)))
        return bot

    def switch_task(self, bot, *, auto_login=True):
        task = {
            "id": "__account_switch__",
            "timeout_seconds": 300.0,
            "settings": {
                "target_account_id": "target-profile",
                "login_method": "igg",
                "auto_login": auto_login,
            },
        }
        bot.account_switch_task = task
        bot.current_routine_task_id = task["id"]
        bot.routine_only_task_id = task["id"]
        bot.get_routine_task = Mock(return_value=task)
        bot.account_switch_selected_at = 1050.0
        bot.account_switch_confirmed = True
        bot.account_switch_probe_ready = True
        bot.account_switch_auto_login_attempted = True
        bot.routine_completed_steps = {
            "account_switch_igg_login_submitted",
            "account_switch_igg_id_selected",
            "account_switch_igg_game_confirmed",
            "unrelated_step",
        }
        return task

    def test_failed_back_recovery_preserves_progress_and_reaches_restart_deadline(self):
        bot = self.make_bot()
        now = [1000.0]
        with ExitStack() as stack:
            stack.enter_context(patch("buzzbot_app.time.time", side_effect=lambda: now[0]))
            for detector in (
                "detect_login_session_expired_ok_target",
                "detect_login_saved_account_continue_target",
                "detect_game_event_overlay_close_target",
                "detect_blank_webview_close_target",
            ):
                stack.enter_context(patch("buzzbot_app." + detector, return_value=None))
            for elapsed in range(0, 151, 5):
                now[0] = 1000.0 + elapsed
                self.assertFalse(bot._try_game_login_visual_fallback({"id": "game_login"}))
        self.assertEqual(bot._return_to_main_screen.call_count, 6)
        self.assertEqual(bot.routine_login_home_recovery_at, 1145.0)
        self.assertEqual(bot.routine_last_action_time, 1000.0)
        self.assertGreaterEqual(now[0] - bot.routine_last_action_time, GAME_LOGIN_RESTART_SECONDS)

    @patch("buzzbot_app.detect_game_server_connection_error", return_value=True)
    def test_login_has_two_restarts_then_quiet_cooldown_and_a_new_bounded_pair(self, _detect):
        bot = self.make_bot()
        task = {"id": "game_login"}
        with patch("buzzbot_app.time.time", return_value=1100.0):
            for _attempt in range(3):
                self.assertTrue(bot._try_global_login_connection_recovery(task))
        self.assertEqual(bot.adb_client.force_stop_package.call_count, 2)
        self.assertEqual(bot.adb_client.launch_package.call_count, 2)
        self.assertEqual(bot.routine_login_restart_count, 2)
        self.assertEqual(bot.routine_login_server_retry_at, 1100.0 + GAME_SERVER_RETRY_SECONDS)
        started_at = bot.routine_task_started_at
        with patch("buzzbot_app.time.time", return_value=1300.0):
            self.assertTrue(bot._try_global_login_connection_recovery(task))
        self.assertEqual(bot.adb_client.force_stop_package.call_count, 2)
        self.assertEqual(bot.routine_task_started_at, started_at)
        self.assertEqual(bot.current_routine_task_id, "game_login")
        self.assertEqual(bot.current_routine_index, 0)
        bot._defer_current_routine_no_action.assert_not_called()
        bot.select_account_profile.assert_not_called()
        with patch("buzzbot_app.time.time", return_value=1400.0):
            self.assertTrue(bot._try_global_login_connection_recovery(task))
        self.assertEqual(bot.adb_client.force_stop_package.call_count, 3)
        self.assertEqual(bot.routine_login_restart_count, 1)
        self.assertEqual(bot.routine_login_server_retry_at, 0.0)

    @patch("buzzbot_app.detect_game_server_connection_error", return_value=False)
    @patch("buzzbot_app.time.time", return_value=1100.0)
    def test_loading_does_not_reset_cooldown_but_confirmed_home_does(self, _time, _detect):
        bot = self.make_bot()
        bot.routine_login_server_error_active = True
        bot.routine_login_server_retry_at = 1400.0
        bot.routine_login_restart_count = 2
        self.assertTrue(bot._try_global_login_connection_recovery({"id": "game_login"}))
        self.assertEqual(bot.routine_login_restart_count, 2)
        bot.adb_client.force_stop_package.assert_not_called()
        bot._is_game_home_visible.return_value = True
        self.assertFalse(bot._try_global_login_connection_recovery({"id": "game_login"}))
        self.assertFalse(bot.routine_login_server_error_active)
        self.assertEqual(bot.routine_login_server_retry_at, 0.0)
        self.assertEqual(bot.routine_login_restart_count, 0)

    @patch("buzzbot_app.detect_game_server_connection_error", return_value=False)
    @patch("buzzbot_app.time.time", return_value=1100.0)
    def test_loader_after_second_restart_enters_cooldown_without_advancing_task(self, _time, _detect):
        bot = self.make_bot()
        bot.routine_login_server_error_active = True
        bot.routine_login_restart_count = 2
        self.assertTrue(bot._try_global_login_connection_recovery({"id": "game_login"}))
        self.assertEqual(bot.routine_login_server_retry_at, 1400.0)
        self.assertEqual(bot.current_routine_task_id, "game_login")
        bot._defer_current_routine_no_action.assert_not_called()
        bot.adb_client.force_stop_package.assert_not_called()

    @patch("buzzbot_app.detect_game_server_connection_error", return_value=True)
    @patch("buzzbot_app.time.time", return_value=1100.0)
    def test_stop_and_pause_interrupt_cooldown_without_input(self, _time, _detect):
        for control in ("stop", "pause"):
            with self.subTest(control=control):
                bot = self.make_bot()
                bot.routine_login_server_error_active = True
                bot.routine_login_server_retry_at = 1400.0
                bot.routine_login_restart_count = 2
                bot._thread = threading.current_thread()
                bot._interruptible_sleep = AutoClicker._interruptible_sleep.__get__(bot)
                if control == "stop":
                    bot.stop_event.set()
                else:
                    bot.is_paused = True
                with self.assertRaises(_BotActionInterrupted):
                    bot._try_global_login_connection_recovery({"id": "game_login"})
                bot.adb_client.force_stop_package.assert_not_called()
                bot.adb_client.launch_package.assert_not_called()
                self.assertEqual(bot.current_routine_index, 0)

    @patch("buzzbot_app.detect_game_server_connection_error", return_value=True)
    def test_ordinary_task_queues_login_and_preserves_interrupted_slot(self, _detect):
        bot = self.make_bot()
        bot.current_routine_task_id = "trucks"
        bot.current_routine_index = 3
        self.assertTrue(bot._try_global_login_connection_recovery({"id": "trucks"}))
        self.assertEqual(bot.routine_forced_task_active_id, "game_login")
        self.assertEqual(bot.routine_forced_task_return_index, 3)
        self.assertEqual(bot.current_routine_index, 0)
        self.assertIsNone(bot.current_routine_task_id)
        self.assertEqual(bot.routine_next_run["game_login"], 0.0)
        bot.adb_client.force_stop_package.assert_not_called()
        bot.save_config.assert_called_once_with()

    @patch("buzzbot_app.detect_game_server_connection_error", return_value=True)
    @patch("buzzbot_app.time.time", return_value=1100.0)
    def test_disabled_login_is_not_enabled_and_ordinary_task_does_not_advance(self, _time, _detect):
        bot = self.make_bot()
        bot.routine_tasks[0]["enabled"] = False
        bot.current_routine_task_id = "trucks"
        bot.current_routine_index = 3
        self.assertTrue(bot._try_global_login_connection_recovery({"id": "trucks"}))
        self.assertFalse(bot.routine_tasks[0]["enabled"])
        self.assertEqual(bot.current_routine_task_id, "trucks")
        self.assertEqual(bot.current_routine_index, 3)
        bot.adb_client.force_stop_package.assert_not_called()
        bot.adb_client.launch_package.assert_not_called()

    @patch("buzzbot_app.detect_game_server_connection_error", return_value=True)
    @patch("buzzbot_app.time.time", return_value=1100.0)
    def test_switch_restarts_once_without_extending_deadline_or_accepting_old_home(self, _time, _detect):
        bot = self.make_bot()
        task = self.switch_task(bot)
        self.assertTrue(bot._try_global_login_connection_recovery(task))
        self.assertEqual(bot.routine_task_started_at, 1000.0)
        self.assertEqual(bot.account_switch_selected_at, 0.0)
        self.assertFalse(bot.account_switch_confirmed)
        self.assertFalse(bot.account_switch_probe_ready)
        self.assertFalse(bot.account_switch_auto_login_attempted)
        self.assertEqual(bot.routine_completed_steps, {"unrelated_step"})
        self.assertEqual(task["settings"]["target_account_id"], "target-profile")
        self.assertTrue(bot._try_global_login_connection_recovery(task))
        self.assertEqual(bot.adb_client.force_stop_package.call_count, 1)
        self.assertEqual(bot.adb_client.launch_package.call_count, 1)
        self.assertIn("ErrCode:0x2", bot.account_switch_error)
        self.assertEqual(bot.current_account_id, "old-profile")
        bot.select_account_profile.assert_not_called()
        self.assertEqual(bot.account_switch_retry_at, 1100.0 + ACCOUNT_SWITCH_RETRY_SECONDS)
        self.assertIsNone(bot.current_routine_task_id)
        self.assertFalse(bot.stop_event.is_set())

    @patch("buzzbot_app.detect_game_server_connection_error", return_value=True)
    @patch("buzzbot_app.time.time", return_value=1100.0)
    def test_switch_restart_failure_cannot_confirm_previous_account(self, _time, _detect):
        bot = self.make_bot()
        task = self.switch_task(bot)
        bot.adb_client.force_stop_package.side_effect = AdbError("mock failure")
        self.assertTrue(bot._try_global_login_connection_recovery(task))
        self.assertTrue(bot.account_switch_error)
        self.assertFalse(bot.account_switch_confirmed)
        self.assertEqual(bot.current_account_id, "old-profile")
        self.assertEqual(bot.routine_task_started_at, 1000.0)
        bot.adb_client.launch_package.assert_not_called()
        bot.select_account_profile.assert_not_called()

    @patch("buzzbot_app.detect_game_server_connection_error", return_value=True)
    @patch("buzzbot_app.time.time", return_value=1400.0)
    def test_expired_switch_gets_no_additional_restart(self, _time, _detect):
        bot = self.make_bot()
        task = self.switch_task(bot)
        self.assertTrue(bot._try_global_login_connection_recovery(task))
        bot.adb_client.force_stop_package.assert_not_called()
        bot.adb_client.launch_package.assert_not_called()
        bot.select_account_profile.assert_not_called()
        self.assertTrue(bot.account_switch_error)

    @patch("buzzbot_app.detect_game_server_connection_error", return_value=True)
    @patch("buzzbot_app.time.time", return_value=1100.0)
    def test_manual_igg_is_not_bypassed_by_server_recovery(self, _time, _detect):
        bot = self.make_bot()
        task = self.switch_task(bot, auto_login=False)
        self.assertTrue(bot._try_global_login_connection_recovery(task))
        bot.adb_client.force_stop_package.assert_not_called()
        bot.adb_client.launch_package.assert_not_called()
        bot.select_account_profile.assert_not_called()
        self.assertTrue(bot.account_switch_error)

    @patch("buzzbot_app.detect_game_server_connection_error", return_value=False)
    def test_unrecognized_screen_does_not_enter_new_recovery(self, _detect):
        bot = self.make_bot()
        self.assertFalse(bot._try_game_server_connection_recovery({"id": "game_login"}, bot._frame))
        bot.adb_client.current_foreground_package.assert_not_called()
        bot.adb_client.force_stop_package.assert_not_called()
        self.assertFalse(bot.routine_login_server_error_active)

    @patch("buzzbot_app.detect_game_server_connection_error", return_value=True)
    def test_wrong_foreground_package_is_not_restarted(self, _detect):
        bot = self.make_bot()
        bot.adb_client.current_foreground_package.return_value = "other.package"
        self.assertFalse(bot._try_game_server_connection_recovery({"id": "game_login"}, bot._frame))
        bot.adb_client.force_stop_package.assert_not_called()
        bot.adb_client.launch_package.assert_not_called()

    @patch("buzzbot_app.time.time", return_value=1100.0)
    def test_real_error_frame_enters_each_scoped_recovery_branch(self, _time):
        frame = imread_unicode(Path(__file__).parent / "assets/accounts/server_connection_error.png")
        self.assertIsNotNone(frame)
        for task_id in ("game_login", "trucks", "__account_switch__"):
            with self.subTest(task_id=task_id):
                bot = self.make_bot()
                bot._capture_screen_bgr.return_value = (frame, (0, 0))
                if task_id == "__account_switch__":
                    task = self.switch_task(bot)
                else:
                    task = {"id": task_id}
                    bot.current_routine_task_id = task_id
                self.assertTrue(bot._try_global_login_connection_recovery(task))
                if task_id == "trucks":
                    self.assertEqual(bot.routine_forced_task_active_id, "game_login")
                    bot.adb_client.force_stop_package.assert_not_called()
                else:
                    bot.adb_client.force_stop_package.assert_called_once_with(GAME_PACKAGE)
                bot.select_account_profile.assert_not_called()


if __name__ == "__main__":
    unittest.main()
