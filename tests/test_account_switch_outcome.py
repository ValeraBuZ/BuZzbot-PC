import threading
import unittest
from unittest.mock import patch

from buzzbot_app import ACCOUNT_SWITCH_TEMPLATE_GROUP, AutoClicker


class AccountSwitchOutcomeTests(unittest.TestCase):
    def make_bot(self, *, rotation=True, pass_completed=False):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "pyautogui"
        bot.account_profiles = [
            {"id": "source", "name": "Source"},
            {
                "id": "target",
                "name": "Target",
                "login_method": "igg",
                "auto_login": True,
                "verified_igg_id": "1234567890",
            },
        ]
        bot.current_account_id = "source"
        bot.current_routine_index = 6
        bot.current_routine_task_id = "research"
        bot.routine_pass_completed = pass_completed
        bot.routine_only_task_id = None
        bot.routine_mode = True
        bot.routine_tasks = []
        bot.routine_next_run = {"research": 42.0, "oil": 1234.0}
        bot.routine_forced_task_queue = []
        bot.routine_radar_return_hold = False
        bot.account_rotation_enabled = rotation
        bot.account_switch_failure_count = 0
        bot.account_switch_retry_at = 0.0
        bot.account_switch_candidates = []
        bot.search_images = [{"group": ACCOUNT_SWITCH_TEMPLATE_GROUP}]
        bot.account_has_saved_login = lambda _account_id: True
        bot.account_has_saved_password = lambda _account_id: True
        bot.stop_event = threading.Event()
        bot.set_status_message = lambda *_args, **_kwargs: None
        bot.saved_states = []
        bot.save_config = lambda: bot.saved_states.append(
            (bot.current_account_id, bot.current_routine_index, bot.routine_pass_completed)
        )
        bot._account_switch_main_screen_confirmed = lambda _task: False
        bot.selected_profiles = []

        def select_profile(account_id, **kwargs):
            bot.selected_profiles.append((account_id, kwargs))
            bot.current_account_id = account_id
            bot.current_routine_index = 0
            bot.routine_pass_completed = False
            bot.account_switch_failure_count = 0
            return True

        bot.select_account_profile = select_profile
        return bot

    def prepare_active_switch(self, bot):
        self.assertTrue(bot._prepare_account_switch(bot.account_profiles[1]))
        bot.current_routine_task_id = "__account_switch__"
        # The isolated switch occupies index zero while the saved queue is idle.
        bot.current_routine_index = 0
        bot.account_switch_selected_at = 10.0
        bot.account_switch_failure_count = 1
        return bot.account_switch_task

    def assert_stopped_at_original_queue(self, bot, pass_completed=False):
        self.assertEqual(bot.current_account_id, "source")
        self.assertEqual(bot.current_routine_index, 6)
        self.assertEqual(bot.routine_pass_completed, pass_completed)
        self.assertEqual(bot.routine_next_run, {"research": 42.0, "oil": 1234.0})
        self.assertEqual(bot.selected_profiles, [])
        self.assertFalse(bot.routine_mode)
        self.assertTrue(bot.stop_event.is_set())
        self.assertFalse(bot.account_switch_confirmed)
        self.assertEqual(bot.account_switch_retry_at, 0.0)
        self.assertTrue(bot.account_switch_last_result.startswith("Переключение не подтверждено:"))
        self.assertFalse(bot._account_rotation_switch_due(10000.0))

    def test_unverified_success_flag_stops_and_preserves_source_queue(self):
        for rotation in (False, True):
            for completed in (False, True):
                with self.subTest(rotation=rotation, completed=completed):
                    bot = self.make_bot(rotation=rotation, pass_completed=completed)
                    self.prepare_active_switch(bot)
                    bot.account_switch_confirmed = True

                    bot._finish_current_routine(100.0)

                    self.assert_stopped_at_original_queue(bot, completed)

    def test_completion_template_cannot_bypass_identity_verification(self):
        bot = self.make_bot()
        self.prepare_active_switch(bot)

        bot._finish_current_routine(100.0, completion_clicked=True)

        self.assert_stopped_at_original_queue(bot)

    def test_identity_error_stops_manual_switch_without_resuming_old_tasks(self):
        bot = self.make_bot()
        self.prepare_active_switch(bot)
        bot.account_switch_error = "Игра сохранила прежний IGG ID"

        bot._finish_current_routine(100.0)

        self.assert_stopped_at_original_queue(bot)
        self.assertIn("прежний IGG ID", bot.account_switch_last_result)

    def test_verified_identity_is_saved_before_target_profile_is_selected(self):
        bot = self.make_bot()
        task = self.prepare_active_switch(bot)
        task["settings"]["_verified_igg_id"] = "1234567890"
        bot.account_switch_confirmed = True

        def verify(active_task):
            self.assertIs(active_task, task)
            self.assertIs(bot.account_switch_task, task)
            self.assertEqual(bot.current_routine_task_id, "__account_switch__")
            self.assertEqual(bot.account_switch_selected_at, 10.0)
            return True

        bot._account_switch_main_screen_confirmed = verify
        bot.account_profiles[1].pop("verified_igg_id")
        select = bot.select_account_profile

        def select_after_binding(account_id, **kwargs):
            self.assertEqual(bot.account_profiles[1]["verified_igg_id"], "1234567890")
            return select(account_id, **kwargs)

        bot.select_account_profile = select_after_binding

        bot._finish_current_routine(100.0)

        self.assertEqual(bot.current_account_id, "target")
        self.assertTrue(bot.account_switch_confirmed)
        self.assertEqual(bot.account_switch_last_result, "Аккаунт переключён: Target")
        self.assertEqual(bot.selected_profiles, [("target", {"start_fresh_pass": True})])
        self.assertTrue(bot.routine_mode)
        self.assertFalse(bot.stop_event.is_set())

    def test_deleted_target_cannot_be_reported_as_successful_switch(self):
        bot = self.make_bot()
        task = self.prepare_active_switch(bot)
        task["settings"]["_verified_igg_id"] = "1234567890"
        bot.account_switch_confirmed = True
        bot._account_switch_main_screen_confirmed = lambda _task: True
        bot.account_profiles.pop()

        bot._finish_current_routine(100.0)

        self.assert_stopped_at_original_queue(bot)

    def test_prepare_preserves_bound_id_and_original_queue_position(self):
        bot = self.make_bot(pass_completed=True)

        self.assertTrue(bot._prepare_account_switch(bot.account_profiles[1]))

        settings = bot.account_switch_task["settings"]
        self.assertEqual(settings["_expected_igg_id"], "1234567890")
        self.assertEqual(settings["_return_routine_index"], 6)
        self.assertTrue(settings["_return_pass_completed"])
        self.assertEqual(bot.current_account_id, "source")

    def test_single_task_switch_runtime_keeps_saved_queue_slot_and_runs_with_latch(self):
        bot = self.make_bot()
        self.assertTrue(bot._prepare_account_switch(bot.account_profiles[1]))
        bot.account_switch_failure_count = 1
        bot.input_backend = "pyautogui"
        bot.lang = "ru"
        bot.groups = {}
        bot.routine_forced_task_active_id = None
        bot.routine_deployment_blocked_until = 0.0
        bot.routine_max_marches = 5
        bot.get_active_marches = lambda _now: 0
        bot._release_radar_return_hold = lambda *_args: False
        bot._try_return_camped_zombie_march = lambda *_args: False
        bot._clear_routine_coordinate_blocks = lambda _task: None
        bot.get_routine_templates = lambda *_args, **_kwargs: []

        task = bot._begin_due_routine(100.0)

        self.assertEqual(task["id"], "__account_switch__")
        self.assertEqual(bot.current_routine_task_id, "__account_switch__")
        self.assertEqual(bot.current_routine_index, 6)
        self.assertEqual(task["settings"]["_return_routine_index"], 6)
        self.assertTrue(bot.routine_mode)
        self.assertFalse(bot.stop_event.is_set())

    def test_resume_after_failed_switch_cannot_restart_ordinary_queue(self):
        bot = self.make_bot()
        bot.account_switch_failure_count = 1
        bot.get_active_marches = lambda _now: self.fail("Ordinary queue resumed before identity verification")

        self.assertIsNone(bot._begin_due_routine(10000.0))

        self.assertFalse(bot.routine_mode)
        self.assertTrue(bot.stop_event.is_set())
        self.assertEqual(bot.current_routine_index, 6)
        self.assertEqual(bot.current_account_id, "source")

    def test_unavailable_explicit_retry_does_not_clear_the_failed_switch_guard(self):
        bot = self.make_bot()
        bot.account_switch_failure_count = 1
        bot.account_profiles[1]["auto_login"] = False

        self.assertFalse(bot.start_account_switch("target"))

        self.assertEqual(bot.account_switch_failure_count, 1)
        self.assertEqual(bot.current_account_id, "source")
        self.assertEqual(bot.current_routine_index, 6)

    def test_failed_worker_start_restores_the_original_queue(self):
        bot = self.make_bot()
        bot.start = lambda: False

        self.assertFalse(bot.start_account_switch("target"))

        # The scheduler key does not alter any ordinary task's saved deadline.
        bot.routine_next_run.pop("__account_switch__", None)
        self.assert_stopped_at_original_queue(bot)

    def test_error_and_timeout_stop_before_repeating_priority_login_fallback(self):
        for existing_error in ("Неверный игровой ID", ""):
            with self.subTest(existing_error=existing_error):
                bot = self.make_bot()
                task = self.prepare_active_switch(bot)
                bot.account_switch_error = existing_error
                bot.routine_task_started_at = 10.0
                bot.routine_last_action_time = 10.0
                bot.stop_hotkey_pressed = False
                bot.is_paused = False
                bot.anti_loop_enabled = False
                bot.sleep_error = 0.0
                bot._research_watchdog_due = lambda _now: False
                bot._drain_expired_account_pass = lambda _now: False
                bot._begin_due_routine = lambda _now: task
                fallback_calls = []

                def priority_fallback(_task):
                    fallback_calls.append(True)
                    bot.stop_event.set()
                    return True

                bot._try_account_switch_igg_game_confirmation = priority_fallback

                with patch("buzzbot_app.time.time", return_value=1000.0):
                    bot._run_clicker_loop()

                self.assertEqual(fallback_calls, [])
                self.assert_stopped_at_original_queue(bot)
                if not existing_error:
                    self.assertIn("истекло время", bot.account_switch_last_result)

    def test_worker_exit_preserves_the_switch_failure_message(self):
        bot = self.make_bot()
        self.prepare_active_switch(bot)
        bot.account_switch_error = "Не совпал игровой ID"
        messages = []
        bot.set_status_message = lambda message, **_kwargs: messages.append(message)
        bot.root = None
        bot._set_state = lambda _state: None
        bot._run_clicker_loop = lambda: bot._finish_current_routine(100.0)

        bot._clicker_loop()

        self.assertEqual(messages[-1], bot.account_switch_last_result)
        self.assertIn("Не совпал игровой ID", messages[-1])


if __name__ == "__main__":
    unittest.main()
