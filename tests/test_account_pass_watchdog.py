import threading
import unittest
from unittest.mock import patch

from buzzbot_app import (
    ACCOUNT_PASS_TASK_HARD_SECONDS,
    ACCOUNT_SWITCH_TIMEOUT_SECONDS,
    AutoClicker,
)


class AccountPassWatchdogTests(unittest.TestCase):
    def test_resume_preserves_original_account_pass_deadline(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_tasks = [
            {"id": "game_login", "group": "login", "enabled": True}
        ]
        bot.groups = {}
        bot.routine_next_run = {"game_login": 0.0}
        bot.current_routine_index = 0
        bot.routine_pass_completed = False
        bot.routine_forced_task_queue = []
        bot.routine_forced_task_active_id = None
        bot.routine_forced_task_return_index = None
        bot.routine_radar_dispatched_this_pass = False
        bot.routine_radar_return_hold = False
        bot.routine_radar_return_active_seen = False
        bot.current_account_id = "account-a"
        bot.account_pass_account_id = "account-a"
        bot.account_pass_started_at = 100.0
        bot.account_session_deadline = 0.0
        bot.routine_research_budget_started_at = 0.0
        bot.get_routine_templates = lambda _task, active_only=True: [object()]
        bot.get_current_account = lambda: {"id": "account-a"}
        bot.save_config = lambda: None
        bot.start = lambda: True

        with patch("buzzbot_app.time.time", return_value=600.0):
            self.assertTrue(bot.start_routines(resume=True))

        self.assertEqual(bot.account_pass_started_at, 100.0)
        self.assertEqual(
            bot.account_session_deadline,
            100.0 + ACCOUNT_PASS_TASK_HARD_SECONDS,
        )

    def test_fresh_pass_resets_clock(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.current_account_id = "account-b"
        bot.account_pass_account_id = "account-a"
        bot.account_pass_started_at = 100.0
        bot.account_session_deadline = 0.0
        bot.routine_research_budget_started_at = 75.0

        deadline = bot._reset_account_pass_clock(500.0)

        self.assertEqual(bot.account_pass_account_id, "account-b")
        self.assertEqual(bot.account_pass_started_at, 500.0)
        self.assertEqual(
            deadline,
            500.0 + ACCOUNT_PASS_TASK_HARD_SECONDS,
        )
        self.assertEqual(bot.routine_research_budget_started_at, 0.0)

    def test_research_watchdog_ignores_repeated_click_activity(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.current_routine_task_id = "research"
        bot.routine_research_budget_started_at = 100.0
        bot.routine_last_action_time = 189.0
        bot.current_account_id = "account-a"
        bot.account_pass_account_id = "account-a"
        bot.account_pass_started_at = 100.0

        self.assertTrue(bot._research_watchdog_due(191.0))

    def test_hard_deadline_does_not_skip_remaining_ordered_tasks(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_mode = True
        bot.account_rotation_enabled = True
        bot.routine_only_task_id = None
        bot.routine_pass_completed = False
        bot.routine_radar_return_hold = False
        bot.current_account_id = "account-a"
        bot.account_pass_account_id = "account-a"
        bot.account_pass_started_at = 100.0
        bot.current_routine_index = 1
        bot.current_routine_task_id = "research"
        bot.routine_tasks = [
            {"id": "game_login", "group": "login", "enabled": True},
            {
                "id": "research",
                "group": "research",
                "enabled": True,
                "settings": {"branch": "economy"},
            },
            {"id": "train_infantry", "group": "infantry", "enabled": True},
            {"id": "oil", "group": "oil", "enabled": True},
        ]
        bot.groups = {
            "login": True,
            "research": True,
            "infantry": True,
            "oil": True,
        }
        bot.routine_next_run = {}
        bot.routine_current_had_action = True
        bot.routine_current_action_count = 4
        bot.routine_action_counts = {"selection": 4}
        bot.routine_completed_steps = {"lab"}
        bot.routine_action_failure_reason = ""
        bot.routine_idle_confirmation_count = 1
        bot.routine_home_recovery_attempted = True
        bot.routine_idle_guard_visible = True
        bot.routine_idle_outside_since = 50.0
        bot.routine_idle_recovery_attempted = True
        bot.routine_research_budget_started_at = 900.0
        bot.routine_forced_task_queue = []
        bot.routine_forced_task_active_id = None
        bot.routine_forced_task_return_index = None
        bot.set_status_message = lambda *_args, **_kwargs: None
        bot.save_config = lambda: None

        expired_at = 100.0 + ACCOUNT_PASS_TASK_HARD_SECONDS
        self.assertFalse(bot._drain_expired_account_pass(expired_at))

        self.assertFalse(bot.routine_pass_completed)
        self.assertEqual(bot.current_routine_index, 1)
        self.assertEqual(bot.current_routine_task_id, "research")
        self.assertEqual(bot.routine_next_run, {})
        self.assertEqual(bot.routine_completed_steps, {"lab"})

    def test_hard_deadline_does_not_cut_active_radar_hold(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_mode = True
        bot.account_rotation_enabled = True
        bot.routine_only_task_id = None
        bot.routine_pass_completed = False
        bot.routine_radar_return_hold = True
        bot.current_account_id = "account-a"
        bot.account_pass_account_id = "account-a"
        bot.account_pass_started_at = 100.0
        bot.current_routine_index = 0
        bot.current_routine_task_id = None
        bot.routine_tasks = [
            {"id": "radar_marches", "group": "radar", "enabled": True}
        ]
        bot.groups = {"radar": True}

        self.assertFalse(
            bot._drain_expired_account_pass(
                100.0 + ACCOUNT_PASS_TASK_HARD_SECONDS
            )
        )
        self.assertFalse(bot.routine_pass_completed)

    def test_radar_is_deferred_when_return_guard_would_consume_switch_reserve(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.current_routine_task_id = None
        bot.account_rotation_enabled = True
        bot.account_switch_failure_count = 0
        bot.account_switch_retry_at = 0.0
        bot.routine_only_task_id = None
        bot.routine_forced_task_queue = []
        bot.routine_forced_task_active_id = None
        bot.routine_forced_task_return_index = None
        bot.routine_pass_completed = False
        bot.routine_radar_return_hold = False
        bot.routine_radar_dispatched_this_pass = False
        bot.routine_deployment_blocked_until = 0.0
        bot.routine_max_marches = 5
        bot.current_routine_index = 0
        bot.current_account_id = "account-a"
        bot.account_pass_account_id = "account-a"
        bot.account_pass_started_at = 100.0
        bot.routine_next_run = {"radar_marches": 0.0, "radar_rewards": 0.0}
        bot.routine_tasks = [
            {
                "id": "radar_marches",
                "group": "radar",
                "enabled": True,
                "uses_march": True,
            },
            {
                "id": "radar_rewards",
                "group": "rewards",
                "enabled": True,
                "uses_march": False,
            },
        ]
        bot.groups = {"radar": True, "rewards": True}
        bot.input_backend = "screen"
        bot.search_images = [
            {"group": "radar", "enabled": True},
            {"group": "rewards", "enabled": True},
        ]
        bot.get_active_marches = lambda _now: 0
        bot._release_radar_return_hold = lambda *_args: False
        bot._try_return_camped_zombie_march = lambda *_args: False
        bot.set_status_message = lambda *_args, **_kwargs: None
        bot.save_config = lambda: None

        now = 100.0 + ACCOUNT_PASS_TASK_HARD_SECONDS - 300.0
        self.assertIsNone(bot._begin_due_routine(now))

        self.assertEqual(bot.current_routine_index, 1)
        self.assertEqual(
            bot.routine_last_outcome["reason"],
            "insufficient_radar_return_budget",
        )
        self.assertFalse(bot.routine_radar_dispatched_this_pass)

    def test_switch_failure_blocks_unattended_repeat(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.account_rotation_enabled = True
        bot.account_switch_failure_count = 1
        bot.account_switch_retry_at = 0.0
        bot.routine_only_task_id = None
        bot.routine_forced_task_queue = []
        bot.routine_pass_completed = True
        bot.current_routine_task_id = None
        bot.routine_radar_return_hold = False

        self.assertFalse(bot._account_rotation_switch_due(1000.0))
        self.assertEqual(ACCOUNT_SWITCH_TIMEOUT_SECONDS, 300.0)

    def test_restart_after_switch_attempt_does_not_repeat_completed_account(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.current_routine_task_id = None
        bot.account_rotation_enabled = True
        bot.routine_pass_completed = True
        bot.routine_only_task_id = None
        bot.account_switch_failure_count = 1
        bot.routine_mode = True
        bot.stop_event = threading.Event()
        messages = []
        bot.set_status_message = (
            lambda message, **_kwargs: messages.append(message)
        )

        self.assertIsNone(bot._begin_due_routine(1000.0))

        self.assertFalse(bot.routine_mode)
        self.assertTrue(bot.stop_event.is_set())
        self.assertEqual(len(messages), 1)

    def test_explicit_switch_latches_attempt_before_start(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.account_profiles = [{"id": "account-b"}]
        bot.account_switch_failure_count = 1
        bot.routine_next_run = {}
        bot._prepare_account_switch = lambda _profile: True
        saves = []
        bot.save_config = lambda: saves.append(bot.account_switch_failure_count)
        bot.start = lambda: True

        self.assertTrue(bot.start_account_switch("account-b"))

        self.assertEqual(bot.account_switch_failure_count, 1)
        self.assertEqual(saves, [1])
        self.assertEqual(bot.routine_next_run["__account_switch__"], 0.0)

    def test_failed_switch_stops_after_one_bounded_attempt(self):
        bot = AutoClicker.__new__(AutoClicker)
        task = {
            "id": "__account_switch__",
            "settings": {"target_account_id": "account-b"},
        }
        bot.current_routine_task_id = "__account_switch__"
        bot.get_routine_task = lambda _task_id: task
        bot.account_switch_error = "switch failed"
        bot.account_switch_confirmed = False
        bot.account_switch_selected_at = 5.0
        bot.account_switch_probe_ready = False
        bot.account_switch_auto_login_attempted = True
        bot.account_switch_task = task
        bot.account_switch_candidates = []
        bot.account_switch_failure_count = 0
        bot.routine_current_had_action = True
        bot.routine_only_task_id = "__account_switch__"
        bot.account_rotation_enabled = True
        bot.routine_mode = True
        bot.stop_event = threading.Event()
        bot.set_status_message = lambda *_args, **_kwargs: None
        saved = []
        bot.save_config = lambda: saved.append(True)

        bot._finish_current_routine(now=100.0)

        self.assertEqual(bot.account_switch_failure_count, 1)
        self.assertFalse(bot.routine_mode)
        self.assertTrue(bot.stop_event.is_set())
        self.assertEqual(saved, [True])


if __name__ == "__main__":
    unittest.main()
