from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tools import run_all_accounts_matrix as runner


class LiveRunnerFollowupTests(unittest.TestCase):
    def run_simulated(self, task_id="vip_rewards", *, outcome=None, finish="immediate", home=True):
        task = {"id": task_id, "group": "test", "enabled": True, "settings": {}}
        bot = SimpleNamespace(
            routine_tasks=[task], groups={}, search_images=[{"path": "template.png"}],
            stats={"template.png": 0}, routine_next_run={}, routine_last_outcome={},
            routine_completed_steps=set(), current_routine_task_id=task_id,
            routine_max_marches=5, status_message="simulated status", is_running=False,
            _thread=None, adb_client=None, stop_schedule_thread=Mock(), stop=Mock(),
            _refresh_adb_client=Mock(), get_routine_task=Mock(return_value=task),
            get_active_marches=Mock(return_value=0), _is_game_home_visible=Mock(return_value=home),
        )
        clock = [1000.0]

        def complete():
            bot.is_running = False
            bot.current_routine_task_id = None
            bot.routine_last_outcome = outcome or {}
            if outcome:
                bot.routine_next_run[task_id] = clock[0] + 1000.0
            # Completion clears live step state; the outcome retains its proof.
            bot.routine_completed_steps = set()

        def start(_task_id):
            bot.is_running = True
            if finish == "immediate":
                complete()
            elif finish == "scheduled":
                complete()
                bot.is_running = True
            elif finish == "checkpoint":
                bot.routine_completed_steps = {"match"}
            return True

        def sleep(_seconds):
            clock[0] += 1.0
            if finish == "between_polls":
                complete()

        bot.start_task_only = Mock(side_effect=start)
        with (
            patch.object(runner, "_new_read_only_bot", return_value=bot),
            patch.object(runner, "_activate_account_profile", return_value=True),
            patch.object(runner, "_task_log", return_value=nullcontext()),
            patch.object(runner, "_capture") as capture,
            patch.object(runner.time, "time", side_effect=lambda: clock[0]),
            patch.object(runner.time, "sleep", side_effect=sleep),
            patch.dict(runner.TASK_TIMEOUTS, {task_id: 2.0}),
        ):
            result = runner.run_task("mock-device", "mock-account", task_id, Path("unused"), "economy", 7, 6)
        capture.assert_not_called()
        bot.stop.assert_called_once_with()
        return result, bot

    def test_successful_one_shot_stop_before_first_poll_is_recorded(self):
        for task_id in ("game_login", "vip_rewards", "alliance_gifts", "processing_contest"):
            with self.subTest(task_id=task_id):
                result, bot = self.run_simulated(task_id, outcome={
                    "task_id": task_id, "outcome": "completed", "completed_steps": ["confirmed_reward"],
                })
                self.assertTrue(result["started"])
                self.assertTrue(result["settled"])
                self.assertEqual(result["error"], "")
                self.assertEqual(result["completed_steps"], ["confirmed_reward"])
                if task_id == "game_login":
                    bot._is_game_home_visible.assert_called_once_with()

    def test_successful_stop_between_polls_is_not_timeout(self):
        result, _ = self.run_simulated(finish="between_polls", outcome={
            "task_id": "vip_rewards", "outcome": "completed", "completed_steps": ["claim"],
        })
        self.assertTrue(result["settled"])
        self.assertEqual(result["completed_steps"], ["claim"])
        self.assertEqual(result["error"], "")

    def test_still_running_task_at_deadline_is_timeout(self):
        result, _ = self.run_simulated(finish="timeout")
        self.assertFalse(result["settled"])
        self.assertEqual(result["error"], "timeout")
        self.assertEqual(result["duration_seconds"], 2.0)

    def test_stop_without_matching_outcome_is_aborted(self):
        for outcome in (None, {"task_id": "research", "outcome": "completed", "completed_steps": ["unrelated"]}):
            with self.subTest(outcome=outcome):
                result, _ = self.run_simulated(outcome=outcome)
                self.assertFalse(result["settled"])
                self.assertEqual(result["error"], "aborted")
                self.assertEqual(result["completed_steps"], [])

    def test_login_requires_both_completed_outcome_and_visible_home(self):
        cases = (
            ({"task_id": "game_login", "outcome": "completed"}, False, "playable home screen was not detected"),
            (None, True, "aborted"),
            ({"task_id": "game_login", "outcome": "deferred_no_action"}, True, "routine ended with deferred_no_action"),
        )
        for outcome, home, error in cases:
            with self.subTest(outcome=outcome, home=home):
                result, _ = self.run_simulated("game_login", outcome=outcome, home=home)
                self.assertFalse(result["settled"])
                self.assertEqual(result["error"], error)

    def test_failed_outcome_preserves_its_reason(self):
        result, _ = self.run_simulated(outcome={
            "task_id": "vip_rewards", "outcome": "deferred_stalled", "reason": "unexpected_screen",
        })
        self.assertFalse(result["settled"])
        self.assertEqual(result["error"], "routine ended with deferred_stalled: unexpected_screen")

    def test_scheduled_completion_while_worker_remains_running_is_supported(self):
        result, _ = self.run_simulated(finish="scheduled", outcome={
            "task_id": "vip_rewards", "outcome": "completed",
        })
        self.assertTrue(result["settled"])
        self.assertEqual(result["error"], "")

    def test_navigation_limit_does_not_prove_a_busy_queue(self):
        for task_id, reason in (
            ("train_infantry", "max_queue_checks"),
            ("train_riders", "max_queue_checks"),
            ("train_shooters", "max_queue_checks"),
            ("train_vehicles", "max_queue_checks"),
            ("research", "max_lab_checks"),
        ):
            with self.subTest(task_id=task_id):
                result, _ = self.run_simulated(task_id, outcome={
                    "task_id": task_id, "outcome": "deferred_unavailable", "reason": reason,
                })
                self.assertFalse(result["settled"])
                self.assertEqual(result["error"], f"routine ended with deferred_unavailable: {reason}")

    def test_positive_no_squad_outcome_remains_a_successful_availability_check(self):
        result, _ = self.run_simulated("radar_marches", outcome={
            "task_id": "radar_marches", "outcome": "deferred_no_squad", "reason": "no_squad",
        })
        self.assertTrue(result["settled"])
        self.assertEqual(result["error"], "")

    def test_repeating_task_checkpoint_is_preserved(self):
        result, _ = self.run_simulated("prize_hunt", finish="checkpoint")
        self.assertTrue(result["settled"])
        self.assertEqual(result["completed_steps"], ["match"])
        self.assertEqual(result["error"], "")


if __name__ == "__main__":
    unittest.main()
