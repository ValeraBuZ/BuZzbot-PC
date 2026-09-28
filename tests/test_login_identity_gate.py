import threading
import unittest
from unittest.mock import Mock, patch

from buzzbot_app import ACCOUNT_SWITCH_TEMPLATE_GROUP, AutoClicker
from buzzbot.routines import pick_due_task_index
import test_queue_order_regressions as queue_fixture


class LoginIdentityGateTests(unittest.TestCase):
    def make_bot(self, *, bound=True, rotation=True):
        bot = AutoClicker.__new__(AutoClicker)
        profile = {
            "id": "current", "name": "Current", "login_method": "igg", "auto_login": True,
        }
        if bound:
            profile["verified_igg_id"] = "1234567890"
        bot.account_profiles = [profile]
        bot.current_account_id = "current"
        bot.current_routine_index = 2
        bot.current_routine_task_id = None
        bot.routine_only_task_id = None
        bot.routine_mode = True
        bot.routine_pass_completed = False
        bot.routine_tasks = [
            {"id": "game_login", "group": "login", "enabled": True, "settings": {}},
            {"id": "vip_rewards", "group": "vip", "enabled": True},
            {"id": "mysterious_merchant", "group": "merchant", "enabled": True},
            {"id": "trucks", "group": "trucks", "enabled": True},
        ]
        bot.groups = {}
        bot.routine_next_run = {
            "game_login": 0.0, "vip_rewards": 5000.0,
            "mysterious_merchant": 0.0, "trucks": 1200.0,
        }
        bot.routine_forced_task_queue = []
        bot.routine_forced_task_active_id = None
        bot.routine_forced_task_return_index = None
        bot.routine_completed_steps = set()
        bot.account_rotation_enabled = rotation
        bot.account_switch_failure_count = 0
        bot.search_images = [{"group": ACCOUNT_SWITCH_TEMPLATE_GROUP}]
        bot.account_has_saved_login = Mock(return_value=True)
        bot.account_has_saved_password = Mock(return_value=True)
        bot._is_game_home_visible = Mock(return_value=True)
        bot._return_to_main_screen = Mock(return_value=True)
        bot._interruptible_sleep = Mock()
        bot._invalidate_capture = Mock()
        bot._try_game_login_visual_fallback = Mock(return_value=False)
        bot._try_account_switch_connection_recovery = Mock(return_value=False)
        bot._recover_interrupted_routine_foreground = Mock(return_value=False)
        bot.get_routine_templates = Mock(return_value=[object()])
        bot.select_account_profile = Mock(side_effect=AssertionError("current pass must not be reselected"))
        bot._ensure_account_pass_clock = Mock()
        bot._reset_account_pass_clock = Mock()
        bot.save_config = Mock()
        bot.set_status_message = Mock()
        bot.start = Mock(return_value=True)
        bot.stop_event = threading.Event()
        return bot

    def activate(self, bot):
        bot.current_routine_task_id = "__account_switch__"
        return bot.account_switch_task

    @patch("buzzbot_app.time.time", return_value=100.0)
    def test_ordinary_start_and_resume_do_not_insert_identity_check(self, _clock):
        for resume in (False, True):
            for rotation in (False, True):
                with self.subTest(resume=resume, rotation=rotation):
                    bot = self.make_bot()
                    bot.account_rotation_enabled = rotation
                    bot._prepare_current_account_verification = Mock(side_effect=AssertionError("no transition"))
                    self.assertTrue(bot.start_routines(resume=resume))
                    self.assertIsNone(bot.routine_only_task_id)
                    self.assertEqual(bot.current_routine_index, 2 if resume else 0)
                    self.assertEqual(bot.account_switch_failure_count, 0)
                    bot.start.assert_called_once()
                    bot.account_has_saved_login.assert_not_called()
                    bot.account_has_saved_password.assert_not_called()

    def test_ordinary_start_needs_neither_bound_id_nor_saved_credentials(self):
        bot = self.make_bot(bound=False)
        bot.account_has_saved_login.return_value = False
        bot.account_has_saved_password.return_value = False
        self.assertTrue(bot.start_routines())
        self.assertIsNone(bot.routine_only_task_id)
        bot.start.assert_called_once()
        bot.account_has_saved_login.assert_not_called()
        bot.account_has_saved_password.assert_not_called()

    def test_failed_worker_start_is_not_reported_as_failed_account_verification(self):
        bot = self.make_bot()
        bot.start.return_value = False
        self.assertFalse(bot.start_routines())
        self.assertIsNone(bot.current_routine_task_id)
        self.assertEqual(bot.account_switch_failure_count, 0)

    def test_heal_runs_with_rotation_off_despite_cancelled_legacy_startup_check(self):
        helper = queue_fixture.QueueOrderRegressionTests()
        bot = helper.make_bot([helper.task("heal")], 0)
        bot.account_rotation_enabled = False
        bot.account_switch_failure_count = 1
        bot.account_switch_task = None
        bot.account_switch_confirmed = False
        bot.stop_event = threading.Event()
        bot.get_current_account = Mock(return_value=None)
        bot.get_routine_templates = Mock(return_value=[object()])
        bot.start = Mock(return_value=True)
        bot._recover_interrupted_routine_foreground = Mock(return_value=False)
        bot._prepare_current_account_verification = Mock(side_effect=AssertionError("ordinary healing must start directly"))
        self.assertTrue(bot.start_routines())
        task = bot._begin_due_routine(100.0)
        self.assertEqual(task["id"], "heal")
        self.assertFalse(bot.stop_event.is_set())
        self.assertTrue(bot.routine_mode)
        self.assertIsNone(bot.routine_only_task_id)
        # Allowing current-game work must not manufacture proof for rotation.
        self.assertEqual(bot.account_switch_failure_count, 1)
        self.assertFalse(bot.account_switch_confirmed)

    def test_reenabling_rotation_still_recovers_unverified_identity(self):
        bot = self.make_bot(rotation=False)
        bot.account_switch_failure_count = 1
        self.assertTrue(bot.start_routines())
        self.assertIsNone(bot.routine_only_task_id)
        bot.account_rotation_enabled = True
        self.assertTrue(bot.start_routines())
        self.assertEqual(bot.routine_only_task_id, "__account_switch__")
        self.assertEqual(bot.account_switch_task["settings"]["_return_routine_index"], 0)

    def test_rotation_off_skips_identity_and_credentials_for_bound_or_unbound_profile(self):
        for bound in (True, False):
            with self.subTest(bound=bound):
                bot = self.make_bot(bound=bound, rotation=False)
                bot.account_has_saved_login.return_value = False
                bot.account_has_saved_password.return_value = False
                deadlines = dict(bot.routine_next_run)
                with patch("buzzbot_app.read_game_igg_id") as reader:
                    self.assertTrue(bot._prepare_current_account_verification(2))
                reader.assert_not_called()
                bot.account_has_saved_login.assert_not_called()
                bot.account_has_saved_password.assert_not_called()
                self.assertIsNone(bot.account_switch_task)
                self.assertIsNone(bot.routine_only_task_id)
                self.assertEqual(bot.current_routine_index, 2)
                self.assertEqual(bot.routine_next_run, deadlines)
                self.assertFalse(bot.account_switch_confirmed)
                self.assertFalse(bot.stop_event.is_set())

    def test_rotation_off_relogin_resumes_interrupted_one_shot_and_forced_queue(self):
        bot = self.make_bot(rotation=False)
        bot.current_routine_task_id = "game_login"
        bot.current_routine_index = 0
        bot.routine_forced_task_active_id = "game_login"
        bot.routine_forced_task_return_index = 2
        context = {"queue": ["trucks"], "active_id": "mysterious_merchant", "return_index": 1}
        bot.routine_tasks[0]["settings"].update({
            "_foreground_resume_only_task_id": "mysterious_merchant",
            "_foreground_return_forced_context": context,
        })
        deadlines = dict(bot.routine_next_run)
        bot._finish_current_routine(100.0)
        self.assertIsNone(bot.account_switch_task)
        self.assertEqual(bot.current_routine_index, 2)
        self.assertEqual(bot.routine_only_task_id, "mysterious_merchant")
        self.assertEqual(bot.routine_forced_task_queue, ["trucks"])
        self.assertEqual(bot.routine_forced_task_active_id, "mysterious_merchant")
        self.assertEqual(bot.routine_forced_task_return_index, 1)
        self.assertEqual(bot.routine_next_run, deadlines)
        self.assertFalse(bot.routine_tasks[0]["enabled"])
        self.assertFalse(bot.stop_event.is_set())
        bot.select_account_profile.assert_not_called()

    def test_rotation_off_standalone_login_stops_without_account_check(self):
        bot = self.make_bot(rotation=False)
        bot.current_routine_task_id = "game_login"
        bot.routine_only_task_id = "game_login"
        bot.current_routine_index = 0
        bot._finish_current_routine(100.0)
        self.assertIsNone(bot.account_switch_task)
        self.assertEqual(bot.current_routine_index, 1)
        self.assertFalse(bot.routine_tasks[0]["enabled"])
        self.assertTrue(bot.stop_event.is_set())
        self.assertFalse(bot.routine_mode)
        self.assertFalse(bot.account_switch_confirmed)

    def test_disabling_rotation_cancels_pending_automatic_check_before_retry(self):
        bot = self.make_bot()
        bot._prepare_current_account_verification(2, after_login=True)
        bot.account_switch_task["settings"]["_transition_retry_at"] = 500.0
        bot.account_switch_retry_at = 500.0
        bot.routine_next_run["__account_switch__"] = 500.0
        bot.account_rotation_enabled = False
        bot._wait_or_restart_account_transition = Mock(side_effect=AssertionError("must cancel first"))
        self.assertIsNone(bot._begin_due_routine(100.0))
        self.assertIsNone(bot.account_switch_task)
        self.assertIsNone(bot.routine_only_task_id)
        self.assertEqual(bot.current_routine_index, 2)
        self.assertEqual(bot.account_switch_retry_at, 0.0)
        self.assertNotIn("__account_switch__", bot.routine_next_run)
        self.assertFalse(bot.account_switch_confirmed)
        self.assertFalse(bot.stop_event.is_set())
        bot._return_to_main_screen.assert_called_once()
        bot.account_rotation_enabled = True
        self.assertTrue(bot.start_routines(resume=True))
        self.assertEqual(bot.routine_only_task_id, "__account_switch__")

    def test_rotation_off_does_not_cancel_an_explicit_account_switch(self):
        bot = self.make_bot(rotation=False)
        self.assertTrue(bot._prepare_account_switch(bot.account_profiles[0]))
        task = bot.account_switch_task
        self.assertFalse(bot._cancel_disabled_current_account_verification())
        self.assertIs(bot.account_switch_task, task)
        self.assertEqual(bot.routine_only_task_id, "__account_switch__")
        self.assertFalse(bot.account_switch_confirmed)

    def test_rotation_off_restart_of_forced_login_does_not_insert_identity_check(self):
        bot = self.make_bot(rotation=False)
        bot.current_routine_index = 0
        bot.routine_forced_task_active_id = "game_login"
        bot.routine_forced_task_return_index = 2
        bot._prepare_current_account_verification = Mock(side_effect=AssertionError("rotation is off"))
        self.assertTrue(bot.start_routines())
        self.assertIsNone(bot.routine_only_task_id)
        self.assertEqual(bot.routine_forced_task_return_index, 2)
        bot.start.assert_called_once()

    def test_unbound_current_profile_uses_normal_authentication(self):
        bot = self.make_bot(bound=False)
        self.assertTrue(bot._prepare_current_account_verification(2))
        settings = bot.account_switch_task["settings"]
        self.assertFalse(settings["_verify_only"])
        self.assertNotIn("_expected_igg_id", settings)
        self.assertEqual(bot.account_switch_selected_at, 0.0)
        bot.account_has_saved_login.assert_called_once_with("current")
        bot.account_has_saved_password.assert_called_once_with("current")

    def test_explicit_start_can_retry_after_failure_and_switch_stays_a_barrier(self):
        bot = self.make_bot()
        bot.account_rotation_enabled = True
        bot.account_switch_failure_count = 1
        bot.account_switch_error = "Previous verification failed"
        bot.stop_event.set()
        bot.input_backend = "pyautogui"
        bot.lang = "ru"
        bot.routine_deployment_blocked_until = 0.0
        bot.routine_max_marches = 4
        bot._clear_routine_coordinate_blocks = Mock()
        bot._launch_game_for_login = Mock(return_value=True)
        bot.get_active_marches = Mock(side_effect=AssertionError("account not proved yet"))
        bot._release_radar_return_hold = Mock(side_effect=AssertionError("queue must remain held"))
        self.assertTrue(bot.start_routines(resume=True))
        task = bot._begin_due_routine(100.0)
        self.assertEqual(task["id"], "__account_switch__")
        self.assertEqual(task["settings"]["_return_routine_index"], 2)
        self.assertEqual(bot.current_routine_index, 2)
        self.assertEqual(bot.account_switch_error, "")
        bot._launch_game_for_login.assert_called_once()

    def test_explicit_verification_disables_login_then_selects_vip(self):
        bot = self.make_bot()
        bot.search_images.append({"group": "vip"})
        bot.routine_next_run["vip_rewards"] = 0.0
        self.assertTrue(bot._prepare_current_account_verification(0))
        task = self.activate(bot)
        self.assertEqual(task["settings"]["_return_routine_index"], 0)
        task["settings"]["_verified_igg_id"] = "1234567890"
        bot.routine_completed_steps.add("account_switch_igg_loaded_id_verified")
        bot.account_switch_confirmed = True
        bot._finish_current_routine(101.0)
        runtime_tasks = bot._scheduler_routine_tasks()
        index = pick_due_task_index(runtime_tasks, bot.routine_next_run, bot.current_routine_index, 102.0)
        self.assertFalse(runtime_tasks[0]["enabled"])
        self.assertEqual(runtime_tasks[index]["id"], "vip_rewards")
        self.assertFalse(bot.routine_pass_completed)

    def test_manual_restart_during_forced_login_captures_actual_return_slot(self):
        bot = self.make_bot()
        bot.current_routine_index = 0
        bot.routine_forced_task_active_id = "game_login"
        bot.routine_forced_task_return_index = 2
        bot.routine_next_run["mysterious_merchant"] = 99.0
        self.assertTrue(bot.start_routines())
        self.assertEqual(bot.account_switch_task["settings"]["_return_routine_index"], 2)
        self.assertEqual(bot.current_routine_index, 2)
        self.assertEqual(bot.routine_next_run["mysterious_merchant"], 99.0)

    def test_manual_restart_during_recovery_keeps_one_shot_merchant_scope(self):
        bot = self.make_bot()
        bot.current_routine_index = 0
        bot.routine_forced_task_active_id = "game_login"
        bot.routine_forced_task_return_index = 2
        bot.routine_tasks[0]["settings"]["_foreground_resume_only_task_id"] = "mysterious_merchant"
        self.assertTrue(bot.start_routines())
        task = self.activate(bot)
        self.assertEqual(task["settings"]["_return_only_task_id"], "mysterious_merchant")
        task["settings"]["_verified_igg_id"] = "1234567890"
        bot.routine_completed_steps.add("account_switch_igg_loaded_id_verified")
        bot.account_switch_confirmed = True
        bot._finish_current_routine(101.0)
        self.assertEqual(bot.routine_only_task_id, "mysterious_merchant")
        self.assertEqual(bot.current_routine_index, 2)

    def test_unbound_profile_without_credentials_stops_at_interrupted_slot(self):
        bot = self.make_bot(bound=False)
        bot.account_has_saved_password.return_value = False
        self.assertFalse(bot._prepare_current_account_verification(2))
        self.assertTrue(bot.stop_event.is_set())
        self.assertFalse(bot.routine_mode)
        self.assertEqual(bot.current_routine_index, 2)
        self.assertEqual(bot.current_account_id, "current")
        bot.start.assert_not_called()

    def test_relogin_waits_for_identity_and_retains_forced_merchant_slot(self):
        bot = self.make_bot()
        bot.current_routine_task_id = "game_login"
        bot.current_routine_index = 0
        bot.routine_forced_task_active_id = "game_login"
        bot.routine_forced_task_return_index = 2
        bot._finish_current_routine(100.0)
        self.assertEqual(bot.routine_only_task_id, "__account_switch__")
        self.assertEqual(bot.account_switch_task["settings"]["_return_routine_index"], 2)
        self.assertTrue(bot.account_switch_task["settings"]["_after_game_login"])
        self.assertEqual(bot.current_routine_index, 2)
        self.assertTrue(bot.routine_tasks[0]["enabled"])
        self.assertEqual(bot.routine_next_run["mysterious_merchant"], 0.0)

    def test_relogin_preserves_pending_forced_followups_after_success_or_error(self):
        for success in (False, True):
            with self.subTest(success=success):
                bot = self.make_bot()
                bot.routine_forced_task_queue = ["mysterious_merchant", "trucks"]
                bot.routine_forced_task_active_id = "mysterious_merchant"
                bot.routine_forced_task_return_index = 1
                context = {
                    "queue": ["mysterious_merchant", "trucks"],
                    "active_id": "mysterious_merchant", "return_index": 1,
                }
                bot._remember_interrupted_login_context()
                bot.current_routine_task_id = "game_login"
                bot.current_routine_index = 0
                bot.routine_forced_task_active_id = "game_login"
                bot.routine_forced_task_return_index = 2
                bot._finish_current_routine(100.0)
                task = self.activate(bot)
                self.assertEqual(task["settings"]["_return_forced_context"], context)
                if success:
                    task["settings"]["_verified_igg_id"] = "1234567890"
                    bot.routine_completed_steps.add("account_switch_igg_loaded_id_verified")
                    bot.account_switch_confirmed = True
                else:
                    bot.account_switch_error = "ID unreadable"
                bot._finish_current_routine(101.0)
                self.assertEqual(bot.current_routine_index, 2)
                self.assertEqual(bot.routine_forced_task_queue, context["queue"])
                self.assertEqual(bot.routine_forced_task_active_id, context["active_id"])
                self.assertEqual(bot.routine_forced_task_return_index, 1)

    @patch("buzzbot_app.time.time", return_value=100.0)
    @patch("buzzbot_app.read_game_igg_id", return_value="1234567890")
    def test_network_recovery_discards_partial_proof_and_requires_two_new_frames(self, reader, _clock):
        bot = self.make_bot()
        bot._prepare_current_account_verification(2)
        task = self.activate(bot)
        bot._try_account_switch_igg_game_confirmation(task, frame_bgr=object())
        self.assertIn("_identity_candidate", task["settings"])
        bot._try_account_switch_connection_recovery.return_value = True
        bot.account_switch_selected_at = 0.0
        bot._try_account_switch_igg_game_confirmation(task, frame_bgr=object())
        self.assertNotIn("_identity_candidate", task["settings"])
        self.assertEqual(bot.account_switch_selected_at, 100.0)
        bot._try_account_switch_connection_recovery.return_value = False
        for _ in range(2):
            bot._try_account_switch_igg_game_confirmation(task, frame_bgr=object())
        self.assertEqual(reader.call_count, 3)
        self.assertEqual(task["settings"]["_verified_igg_id"], "1234567890")
        self.assertEqual(bot.routine_only_task_id, "__account_switch__")

    @patch("buzzbot_app.time.time", return_value=100.0)
    @patch("buzzbot_app.read_game_igg_id", return_value="1234567890")
    def test_two_fresh_reads_and_home_resume_same_slot_without_reselect(self, reader, _clock):
        bot = self.make_bot()
        deadlines = dict(bot.routine_next_run)
        bot._prepare_current_account_verification(2)
        task = self.activate(bot)
        # No SDK selection is needed for the already bound, current profile.
        for reading in range(2):
            self.assertTrue(bot._try_account_switch_igg_game_confirmation(task, frame_bgr=object()))
            self.assertEqual(bot.routine_only_task_id, "__account_switch__")
            self.assertEqual(bot.current_routine_index, 2)
            if reading == 0:
                self.assertNotIn("_verified_igg_id", task["settings"])
        self.assertTrue(bot._try_account_switch_igg_game_confirmation(task, frame_bgr=object()))
        self.assertEqual(reader.call_count, 2)
        self.assertIsNone(bot.routine_only_task_id)
        self.assertIsNone(bot.current_routine_task_id)
        self.assertEqual(bot.current_routine_index, 2)
        self.assertEqual(bot.routine_next_run, deadlines)
        self.assertFalse(bot.routine_tasks[0]["enabled"])
        self.assertEqual(bot.account_switch_failure_count, 0)
        self.assertTrue(bot.routine_mode)
        self.assertFalse(bot.stop_event.is_set())
        bot.select_account_profile.assert_not_called()
        bot._try_game_login_visual_fallback.assert_not_called()

    @patch("buzzbot_app.time.time", return_value=100.0)
    @patch("buzzbot_app.read_game_igg_id", return_value="9999999999")
    def test_bound_mismatch_enters_one_real_authentication_then_fails_closed(self, _reader, _clock):
        bot = self.make_bot()
        bot._prepare_current_account_verification(2)
        task = self.activate(bot)
        for _ in range(2):
            bot._try_account_switch_igg_game_confirmation(task, frame_bgr=object())
        self.assertFalse(task["settings"]["_verify_only"])
        self.assertTrue(task["settings"]["_identity_retry"])
        self.assertEqual(task["settings"]["_expected_igg_id"], "1234567890")
        self.assertEqual(bot.account_switch_selected_at, 0.0)
        self.assertEqual(bot.current_routine_index, 2)
        bot.account_switch_selected_at = 1.0
        bot.routine_completed_steps.add("account_switch_igg_id_selected")
        for _ in range(2):
            bot._try_account_switch_verify_identity(task, None)
        self.assertIn("другой IGG ID", bot.account_switch_error)
        bot._finish_current_routine(100.0)
        self.assertFalse(bot.routine_mode)
        self.assertTrue(bot.stop_event.is_set())
        self.assertEqual(bot.current_routine_index, 2)

    @patch("buzzbot_app.time.time", return_value=100.0)
    @patch("buzzbot_app.read_game_igg_id", return_value="1234567890")
    def test_matching_id_cannot_release_gate_without_home_return(self, _reader, _clock):
        bot = self.make_bot()
        bot._prepare_current_account_verification(2)
        task = self.activate(bot)
        bot._return_to_main_screen.return_value = False
        for _ in range(3):
            bot._try_account_switch_igg_game_confirmation(task, frame_bgr=object())
        self.assertEqual(bot.routine_only_task_id, "__account_switch__")
        self.assertNotIn("_verified_igg_id", task["settings"])
        bot.account_switch_confirmed = True
        bot._finish_current_routine(100.0)
        self.assertFalse(bot.routine_mode)
        self.assertTrue(bot.stop_event.is_set())

    def test_recovered_one_shot_merchant_is_restored_only_after_proof(self):
        bot = self.make_bot()
        bot.current_routine_task_id = "game_login"
        bot.current_routine_index = 0
        bot.routine_forced_task_active_id = "game_login"
        bot.routine_forced_task_return_index = 2
        bot.routine_tasks[0]["settings"]["_foreground_resume_only_task_id"] = "mysterious_merchant"
        bot._finish_current_routine(100.0)
        task = self.activate(bot)
        self.assertEqual(task["settings"]["_return_only_task_id"], "mysterious_merchant")
        task["settings"]["_verified_igg_id"] = "1234567890"
        bot.routine_completed_steps.add("account_switch_igg_loaded_id_verified")
        bot.account_switch_confirmed = True
        bot._finish_current_routine(101.0)
        self.assertEqual(bot.routine_only_task_id, "mysterious_merchant")
        self.assertEqual(bot.current_routine_index, 2)
        self.assertTrue(bot.routine_mode)
        self.assertFalse(bot.stop_event.is_set())

    def test_standalone_login_stops_after_identity_is_proved(self):
        bot = self.make_bot()
        bot.current_routine_task_id = "game_login"
        bot.current_routine_index = 0
        bot.routine_only_task_id = "game_login"
        bot._finish_current_routine(100.0)
        task = self.activate(bot)
        task["settings"]["_verified_igg_id"] = "1234567890"
        bot.routine_completed_steps.add("account_switch_igg_loaded_id_verified")
        bot.account_switch_confirmed = True
        bot._finish_current_routine(101.0)
        self.assertFalse(bot.routine_mode)
        self.assertTrue(bot.stop_event.is_set())
        self.assertIn("Аккаунт проверен", bot.account_switch_last_result)


if __name__ == "__main__":
    unittest.main()
