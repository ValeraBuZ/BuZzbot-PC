import threading
import unittest
from unittest.mock import Mock, patch

from buzzbot.adb import AdbError
from buzzbot_app import AutoClicker, ACCOUNT_SWITCH_TIMEOUT_SECONDS, GAME_PACKAGE


class AccountTransitionRecoveryTests(unittest.TestCase):
    def bot(self, *, resume=False):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = Mock()
        bot.account_profiles = [{"id": "target", "name": "Target", "auto_login": True}]
        bot.account_has_saved_login = Mock(return_value=True)
        bot.account_has_saved_password = Mock(return_value=True)
        bot.stop_event = threading.Event()
        bot.stop_hotkey_pressed = False
        bot.routine_mode = True
        bot.current_account_id = "source"
        bot.current_routine_index = 6
        bot.routine_pass_completed = True
        bot.current_routine_task_id = "__account_switch__"
        bot.routine_only_task_id = "__account_switch__"
        bot.routine_next_run = {"research": 900.0}
        bot.routine_forced_task_queue = ["heal", "train_infantry"]
        bot.routine_forced_task_return_index = 6
        bot.routine_forced_task_active_id = "heal"
        bot.routine_completed_steps = {"account_switch_igg_id_selected"}
        bot.account_switch_error = "Переключение не подтверждено: после повторного входа открыт другой IGG ID"
        bot.account_switch_selected_at = 30.0
        bot.account_switch_confirmed = False
        bot.account_switch_auto_login_attempted = True
        bot.account_switch_failure_count = 1
        bot.blocked_coords = {("old", 1, 2): 800.0}
        bot.save_config = Mock()
        bot.set_status_message = Mock()
        bot._interruptible_sleep = Mock()
        bot._invalidate_capture = Mock()
        bot._recover_interrupted_routine_foreground = Mock(return_value=False)
        task = {"id": "__account_switch__", "timeout_seconds": 800, "settings": {
            "target_account_id": "target", "login_method": "igg",
            "_expected_igg_id": "1234567890", "_verified_igg_id": "0000000000",
            "_identity_retry": True, "_identity_candidate": "0000000000",
            "_identity_check_started": True, "_identity_check_started_at": 10,
            "_return_routine_index": 6, "_return_pass_completed": True,
            "_resume_current_pass": resume, "_verify_only": resume,
            "_return_forced_context": {"queue": ["heal", "train_infantry"],
                                       "active_id": "heal", "return_index": 6},
        }}
        bot.account_switch_task = task
        bot.get_routine_task = lambda task_id: task if task_id == "__account_switch__" else None
        return bot, task

    def test_second_mismatch_retries_same_target_without_stopping_or_advancing(self):
        for resume in (False, True):
            with self.subTest(resume=resume):
                bot, task = self.bot(resume=resume)
                bot._finish_current_routine(100)
                self.assertFalse(bot.stop_event.is_set())
                self.assertTrue(bot.routine_mode)
                self.assertIs(bot.account_switch_task, task)
                self.assertEqual(bot.current_account_id, "source")
                self.assertEqual(bot.current_routine_index, 6)
                self.assertTrue(bot.routine_pass_completed)
                self.assertEqual(bot.routine_next_run, {"research": 900, "__account_switch__": 160})
                self.assertEqual(bot.routine_only_task_id, "__account_switch__")
                self.assertFalse(bot.account_switch_confirmed)
                self.assertEqual(bot.routine_completed_steps, set())
                self.assertEqual(task["settings"]["_expected_igg_id"], "1234567890")
                self.assertNotIn("_verified_igg_id", task["settings"])
                self.assertNotIn("_identity_retry", task["settings"])
                self.assertFalse(task["settings"]["_verify_only"])
                self.assertEqual(bot.routine_forced_task_queue, ["heal", "train_infantry"])
                self.assertEqual(task["timeout_seconds"], ACCOUNT_SWITCH_TIMEOUT_SECONDS)

    def test_cooldown_blocks_every_queue_action_and_input(self):
        bot, task = self.bot()
        bot._finish_current_routine(100)
        bot.get_active_marches = Mock(side_effect=AssertionError("Ordinary tasks must stay blocked"))
        self.assertIsNone(bot._begin_due_routine(159.9))
        self.assertEqual(bot.adb_client.mock_calls, [])
        self.assertFalse(bot.stop_event.is_set())

    def test_retry_restarts_only_game_and_invalidates_old_identity(self):
        bot, task = self.bot()
        bot._finish_current_routine(100)
        with patch("buzzbot_app.time.time", return_value=160):
            self.assertFalse(bot._wait_or_restart_account_transition(160))
        bot.adb_client.force_stop_package.assert_called_once_with(GAME_PACKAGE)
        bot.adb_client.launch_package.assert_called_once_with(GAME_PACKAGE)
        self.assertNotIn("_transition_retry_at", task["settings"])
        self.assertEqual(task["settings"]["target_account_id"], "target")
        self.assertIsNone(bot.current_routine_task_id)
        self.assertEqual(bot.routine_next_run["__account_switch__"], 0)

    def test_repeated_failures_back_off_without_changing_target(self):
        bot, task = self.bot()
        for delay in (60, 120, 300, 300):
            self.assertTrue(bot._schedule_account_transition_retry(task, "Не совпал игровой ID", 100))
            self.assertEqual(task["settings"]["_transition_retry_at"], 100 + delay)
            self.assertEqual(task["settings"]["target_account_id"], "target")
        self.assertFalse(bot.stop_event.is_set())

    def test_failed_game_restart_schedules_next_attempt_without_queue_escape(self):
        bot, task = self.bot()
        bot._finish_current_routine(100)
        bot.adb_client.force_stop_package.side_effect = AdbError("offline")
        with patch("buzzbot_app.time.time", return_value=160):
            self.assertTrue(bot._wait_or_restart_account_transition(160))
        self.assertEqual(task["settings"]["_transition_retry_at"], 280)
        bot.adb_client.launch_package.assert_not_called()
        self.assertFalse(bot.stop_event.is_set())

    def test_manual_stop_prevents_any_automatic_restart(self):
        for before_schedule in (False, True):
            bot, task = self.bot()
            if before_schedule:
                bot.stop_event.set()
                self.assertFalse(bot._schedule_account_transition_retry(task, "Не совпал игровой ID", 100))
            else:
                bot._finish_current_routine(100)
                bot.stop_event.set()
                self.assertTrue(bot._wait_or_restart_account_transition(160))
            self.assertEqual(bot.adb_client.mock_calls, [])

    def test_manual_stop_during_restart_does_not_relaunch_game(self):
        bot, task = self.bot()
        bot._finish_current_routine(100)
        bot._interruptible_sleep.side_effect = lambda _: bot.stop_event.set()
        self.assertTrue(bot._wait_or_restart_account_transition(160))
        bot.adb_client.launch_package.assert_not_called()

    def test_permanent_authentication_or_profile_errors_are_not_retried(self):
        bot, task = self.bot()
        for reason in ("IGG отклонил логин: адрес не зарегистрирован", "целевой профиль больше не доступен",
                       "Выбранная строка IGG не соответствует сохранённому ID профиля"):
            self.assertFalse(bot._schedule_account_transition_retry(task, reason, 100))
        bot.account_has_saved_password.return_value = False
        self.assertFalse(bot._schedule_account_transition_retry(task, "Не совпал игровой ID", 100))

    def test_adb_recovery_restarts_target_transition_without_stale_selected_flag(self):
        bot, task = self.bot()
        bot._adb_last_recovery_attempt = -100
        bot._adb_recovery_lock = threading.Lock()
        bot.adb_serial = "emulator-5556"
        bot.get_current_account = Mock(return_value={"ldplayer_index": 1})
        bot.repair_adb_connection = Mock(return_value=True)
        bot._refresh_adb_client = Mock()
        self.assertTrue(bot._recover_runtime_adb_connection())
        self.assertEqual(bot.account_switch_selected_at, 0)
        self.assertFalse(task["settings"]["_transition_restart_game"])
        self.assertEqual(task["settings"]["target_account_id"], "target")
        self.assertNotIn("_identity_candidate", task["settings"])
        self.assertFalse(bot.stop_event.is_set())
        self.assertFalse(bot._adb_recovery_lock.locked())


if __name__ == "__main__":
    unittest.main()
