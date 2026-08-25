import random
import unittest

from tools.run_all_accounts_matrix import (
    _activate_account_profile,
    _expected_adb_serials,
    _game_is_foreground,
    _routine_outcome_is_success,
    _task_blocked_by_march_capacity,
    _task_reached_live_checkpoint,
)
from tools.run_random_program import (
    MARCH_TASKS,
    _busy_tasks_from_log,
    _capacity_blocked_march_tasks,
    _march_tasks_for_account,
    _random_program,
    _task_failures_from_log,
)


class RandomProgramTests(unittest.TestCase):
    def test_live_runner_applies_account_specific_task_state(self):
        class Bot:
            def __init__(self, selected):
                self.selected = selected
                self.calls = []
                self.current_account_id = "old"

            def select_account_profile(self, account_id, save=True):
                self.calls.append((account_id, save))
                if self.selected:
                    self.current_account_id = account_id
                return self.selected

        known = Bot(selected=True)
        self.assertTrue(_activate_account_profile(known, "igg_3"))
        self.assertEqual(known.calls, [("igg_3", False)])
        self.assertEqual(known.current_account_id, "igg_3")

        fallback = Bot(selected=False)
        self.assertFalse(_activate_account_profile(fallback, "matrix_slot"))
        self.assertEqual(fallback.current_account_id, "matrix_slot")

    def test_adb_wait_never_substitutes_a_neighboring_ldplayer(self):
        self.assertEqual(
            _expected_adb_serials("emulator-5562", instance_index=7),
            ("emulator-5568", "127.0.0.1:5569"),
        )
        self.assertEqual(
            _expected_adb_serials("127.0.0.1:5569", instance_index=7),
            ("127.0.0.1:5569", "emulator-5568"),
        )

    def test_matrix_checks_game_foreground_before_each_task(self):
        class Client:
            def __init__(self, package):
                self.package = package

            def current_foreground_package(self):
                return self.package

        self.assertTrue(
            _game_is_foreground(Client("com.igg.android.doomsdaylastsurvivors"))
        )
        self.assertFalse(_game_is_foreground(Client("com.android.launcher3")))

    def test_repeating_prize_hunt_settles_after_first_confirmed_cycle(self):
        self.assertFalse(_task_reached_live_checkpoint("prize_hunt", {"enter", "deploy"}))
        self.assertTrue(_task_reached_live_checkpoint("prize_hunt", {"deploy", "again"}))
        self.assertFalse(_task_reached_live_checkpoint("food", {"deploy"}))

    def test_full_march_queue_is_a_safe_skip_for_march_tasks_only(self):
        self.assertTrue(
            _task_blocked_by_march_capacity(
                {"uses_march": True},
                active_marches=5,
                max_marches=5,
            )
        )
        self.assertFalse(
            _task_blocked_by_march_capacity(
                {"uses_march": True},
                active_marches=4,
                max_marches=5,
            )
        )

    def test_random_program_treats_unvisited_full_queue_task_as_processed(self):
        tasks = [
            {"id": "food", "uses_march": True},
            {"id": "mail_rewards", "uses_march": False},
        ]
        self.assertEqual(
            _capacity_blocked_march_tasks(
                ["food", "mail_rewards"],
                tasks,
                active_marches=5,
                max_marches=5,
            ),
            {"food"},
        )
        self.assertEqual(
            _capacity_blocked_march_tasks(
                ["food", "mail_rewards"],
                tasks,
                active_marches=4,
                max_marches=5,
            ),
            set(),
        )
        self.assertFalse(
            _task_blocked_by_march_capacity(
                {"uses_march": False},
                active_marches=5,
                max_marches=5,
            )
        )

    def test_matrix_rejects_deferred_routine_as_success(self):
        self.assertTrue(
            _routine_outcome_is_success(
                "research",
                {"task_id": "research", "outcome": "completed"},
            )
        )
        self.assertFalse(
            _routine_outcome_is_success(
                "research",
                {"task_id": "research", "outcome": "deferred_unavailable"},
            )
        )
        self.assertFalse(
            _routine_outcome_is_success(
                "train_vehicles",
                {"task_id": "research", "outcome": "completed"},
            )
        )

    def test_matrix_accepts_only_matching_busy_queue_outcomes(self):
        self.assertTrue(
            _routine_outcome_is_success(
                "train_riders",
                {
                    "task_id": "train_riders",
                    "outcome": "deferred_unavailable",
                    "reason": "max_queue_checks",
                },
            )
        )
        self.assertTrue(
            _routine_outcome_is_success(
                "radar_marches",
                {
                    "task_id": "radar_marches",
                    "outcome": "deferred_unavailable",
                    "reason": "нет доступного отряда",
                },
            )
        )
        self.assertTrue(
            _routine_outcome_is_success(
                "research",
                {
                    "task_id": "research",
                    "outcome": "deferred_unavailable",
                    "reason": "max_lab_checks",
                },
            )
        )
        self.assertFalse(
            _routine_outcome_is_success(
                "train_riders",
                {
                    "task_id": "train_riders",
                    "outcome": "deferred_unavailable",
                    "reason": "boost_item_unavailable",
                },
            )
        )

    def test_program_is_reproducible_and_has_one_march_task(self):
        first = _random_program(random.Random(12345), 4)
        second = _random_program(random.Random(12345), 4)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 4)
        self.assertEqual(sum(task in MARCH_TASKS for task in first), 1)

    def test_zombie_hunt_is_only_generated_for_main_account(self):
        main_tasks = _march_tasks_for_account("Phoenix675")
        farm_tasks = _march_tasks_for_account("FocusFarm")

        self.assertIn("zombie_hunt", main_tasks)
        self.assertNotIn("zombie_hunt", farm_tasks)
        for seed in range(50):
            program = _random_program(random.Random(seed), 4, farm_tasks)
            self.assertNotIn("zombie_hunt", program)

    def test_report_detects_incomplete_tasks(self):
        log_text = "\n".join(
            (
                "Routine food timed out without actions; retrying",
                "Routine oil reached the squad screen without an available squad; retrying",
                "Routine train_shooters is temporarily unavailable (max_queue_checks); retrying",
                "Routine research is temporarily unavailable (max_lab_checks); retrying",
                "Routine gathering_boost is temporarily unavailable (boost_item_unavailable); retrying",
                "Routine radar_quick is temporarily unavailable (сначала откройте радарную станцию); retrying",
            )
        )

        self.assertEqual(_task_failures_from_log(log_text), ["food", "radar_quick"])
        self.assertEqual(
            _busy_tasks_from_log(log_text),
            ["gathering_boost", "oil", "research", "train_shooters"],
        )


if __name__ == "__main__":
    unittest.main()
