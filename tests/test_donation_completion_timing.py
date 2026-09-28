import threading
import unittest
from unittest.mock import Mock, patch

from buzzbot.routines import donation_exhaustion_is_complete
from buzzbot_app import AutoClicker


class DonationCompletionTimingTests(unittest.TestCase):
    def test_explicit_zero_finishes_at_its_own_deadline_before_more_matching(self):
        task = {
            "id": "alliance_donations", "timeout_seconds": 45.0,
            "exhaustion_idle_seconds": 15.0,
        }
        bot = AutoClicker.__new__(AutoClicker)
        bot.stop_event = threading.Event()
        bot.stop_hotkey_pressed = False
        bot.is_paused = False
        bot.anti_loop_enabled = False
        bot.routine_mode = True
        bot.current_routine_task_id = task["id"]
        bot.routine_last_action_time = 100.0
        bot.routine_completed_steps = {"donations_exhausted", "project_closed"}
        bot._begin_due_routine = Mock(return_value=task)
        bot._recover_interrupted_routine_foreground = Mock(return_value=False)
        bot._finish_current_routine = Mock(side_effect=lambda _now: bot.stop_event.set())
        bot._locate_image = Mock()
        bot.set_status_message = Mock()
        with patch("buzzbot_app.time.time", return_value=115.0), patch("buzzbot_app.logger.exception") as errors:
            bot._run_clicker_loop()
        errors.assert_not_called()
        bot._finish_current_routine.assert_called_once_with(115.0)
        bot._locate_image.assert_not_called()

    def test_closing_a_project_without_zero_never_finishes_by_this_deadline(self):
        task = {"id": "alliance_donations", "timeout_seconds": 45.0, "exhaustion_idle_seconds": 15.0}
        self.assertFalse(donation_exhaustion_is_complete(task, {"project_closed"}, 60.0))
        self.assertFalse(donation_exhaustion_is_complete(task, {"donations_exhausted"}, 14.99))
        self.assertTrue(donation_exhaustion_is_complete(task, {"donations_exhausted"}, 15.0))


if __name__ == "__main__":
    unittest.main()
