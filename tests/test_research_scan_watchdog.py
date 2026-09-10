from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

from buzzbot_app import AutoClicker, RESEARCH_UNCONFIRMED_BUDGET_SECONDS


class ResearchScanWatchdogTests(unittest.TestCase):
    def setUp(self):
        self.now = 189.0
        clock_patch = patch("buzzbot_app.time.time", side_effect=lambda: self.now)
        clock_patch.start()
        self.addCleanup(clock_patch.stop)
        logger_patch = patch("buzzbot_app.logger")
        self.logger = logger_patch.start()
        self.addCleanup(logger_patch.stop)

    def make_bot(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.current_routine_task_id = "research"
        bot.routine_research_budget_started_at = 100.0
        bot.routine_task_started_at = 100.0
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        bot._reset_research_branch = Mock(return_value=frame)
        bot._research_tree_candidates = Mock(return_value=[(900, 350), (900, 450)])
        bot._swipe_research_reference = Mock()
        bot._interruptible_sleep = Mock()
        bot._capture_screen_bgr = Mock(return_value=(frame, (0, 0)))
        bot._try_research_tree_row = Mock(return_value=(False, frame))
        bot._current_task_settings = Mock(return_value={"branch": "any"})
        bot.get_display_profile = Mock(return_value=SimpleNamespace(scale_x=1, scale_y=1))
        bot.set_status_message = Mock()
        return bot, frame

    def test_existing_ninety_second_budget_is_unchanged(self):
        self.assertEqual(RESEARCH_UNCONFIRMED_BUDGET_SECONDS, 90.0)
        bot, _frame = self.make_bot()
        self.assertFalse(bot._research_watchdog_due(189.999))
        self.assertTrue(bot._research_watchdog_due(190.0))

    def test_expired_budget_does_not_reopen_or_scan_a_branch(self):
        bot, _frame = self.make_bot()
        self.now = 190.0
        self.assertFalse(bot._scan_research_branch("economy", bot.get_display_profile()))
        bot._reset_research_branch.assert_not_called()
        bot._try_research_tree_row.assert_not_called()
        bot._swipe_research_reference.assert_not_called()

    def test_budget_expiring_during_row_stops_before_the_next_node(self):
        bot, frame = self.make_bot()

        def visit_row(*_args):
            self.now = 191.0
            return False, frame

        bot._try_research_tree_row.side_effect = visit_row
        self.assertFalse(bot._scan_research_branch("economy", bot.get_display_profile()))
        bot._try_research_tree_row.assert_called_once()
        self.assertEqual(bot._try_research_tree_row.call_args.args[1], 350)
        bot._swipe_research_reference.assert_not_called()

    def test_budget_expiring_during_page_transition_stops_before_next_page_nodes(self):
        bot, frame = self.make_bot()
        bot._research_tree_candidates.return_value = []
        bot._capture_screen_bgr.return_value = (np.full_like(frame, 100), (0, 0))
        bot._swipe_research_reference.side_effect = lambda *_args: setattr(self, "now", 191.0)

        self.assertFalse(bot._scan_research_branch("economy", bot.get_display_profile()))

        bot._research_tree_candidates.assert_called_once()
        bot._swipe_research_reference.assert_called_once()
        bot._try_research_tree_row.assert_not_called()

    def test_budget_expiring_in_first_branch_does_not_select_second_branch(self):
        bot, _frame = self.make_bot()

        def scan(_branch, _display):
            self.now = 191.0
            return False

        bot._scan_research_branch = Mock(side_effect=scan)
        self.assertIsNone(bot._select_available_research())
        bot._scan_research_branch.assert_called_once_with("economy", bot.get_display_profile())

    def test_confirmed_action_before_budget_still_returns_the_selected_branch(self):
        bot, _frame = self.make_bot()
        bot._scan_research_branch = Mock(return_value=True)
        self.assertEqual(bot._select_available_research(), "economy")
        bot._scan_research_branch.assert_called_once()

    def test_interrupted_scan_uses_existing_stalled_deferral_and_permits_recovery(self):
        bot, frame = self.make_bot()
        task = {"id": "research", "interval_minutes": 5.0, "settings": {"branch": "any"}}
        bot.get_routine_task = Mock(return_value=task)
        bot.routine_next_run = {}
        bot.routine_completed_steps = {"lab"}
        bot.routine_current_action_count = 1
        bot.routine_action_counts = {"max_lab_checks": 1}
        bot._return_to_main_screen = Mock(return_value=True)
        bot._save_routine_calibration_frame = Mock()
        bot._advance_routine_after_outcome = Mock()
        bot._finish_current_routine = Mock()
        bot.save_config = Mock()

        def visit_row(*_args):
            self.now = 191.0
            return False, frame

        bot._try_research_tree_row.side_effect = visit_row
        with patch("buzzbot_app.research_tree_is_visible", return_value=True), patch(
            "buzzbot_app.research_tree_progress_is_active", return_value=False
        ):
            self.assertTrue(bot._try_research_visual_fallback(task))

        bot._try_research_tree_row.assert_called_once()
        bot._reset_research_branch.assert_called_once_with("economy", bot.get_display_profile())
        bot._return_to_main_screen.assert_called_once_with(max_back_steps=5, require_settlement=True)
        bot._finish_current_routine.assert_not_called()
        bot._interruptible_sleep.assert_not_called()
        self.assertEqual(bot.routine_last_outcome["outcome"], "deferred_stalled")
        self.assertEqual(bot.routine_last_outcome["reason"], "unconfirmed_research_budget")
        self.assertEqual(bot.routine_last_outcome["completed_steps"], ["lab"])
        self.assertIsNone(bot.current_routine_task_id)
        bot._advance_routine_after_outcome.assert_called_once_with(task, 191.0)
        warning_messages = [call.args[0] for call in self.logger.warning.call_args_list]
        self.assertTrue(any("search is incomplete" in message for message in warning_messages))
        self.assertFalse(any("after scanning all" in message for message in warning_messages))


if __name__ == "__main__":
    unittest.main()
