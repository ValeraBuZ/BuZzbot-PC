from pathlib import Path
import unittest
from unittest.mock import Mock

import cv2

import test_queue_order_regressions as queue_fixture


class TruckTaskStateTests(unittest.TestCase):
    def make_bot(self):
        helper = queue_fixture.QueueOrderRegressionTests()
        task = helper.task("trucks")
        bot = helper.make_bot([task], 0)
        bot.current_account_id = "zzub1"
        bot.routine_truck_checked_slots = {0, 1}
        bot.routine_truck_current_slot = 1
        bot.routine_truck_detail_opened_at = 42.0
        bot.routine_truck_pending_kind = "dispatch"
        bot.routine_truck_pending_started_at = 45.0
        bot.routine_truck_overview_confirmations = 1
        bot.routine_truck_arrival_dismiss_attempts = 3
        bot.routine_truck_formation_index = 2
        bot.routine_truck_daily_limit_exhausted = True
        bot.routine_truck_slot_requested_at = 99.0
        return bot, task

    def test_new_account_task_rechecks_ready_slots_from_real_frame(self):
        bot, task = self.make_bot()
        self.assertEqual(bot._begin_due_routine(100.0), task)
        self.assertEqual(bot.routine_truck_checked_slots, set())
        self.assertEqual(bot.routine_truck_current_slot, -1)
        self.assertEqual(bot.routine_truck_formation_index, 1)
        self.assertEqual(bot.routine_truck_pending_kind, "")
        self.assertEqual(bot.routine_truck_pending_started_at, 0.0)
        self.assertEqual(bot.routine_truck_overview_confirmations, 0)
        self.assertEqual(bot.routine_truck_arrival_dismiss_attempts, 0)
        self.assertFalse(bot.routine_truck_daily_limit_exhausted)
        self.assertEqual(bot.routine_truck_slot_requested_at, 0.0)
        frame = cv2.imread(str(Path(__file__).parent / "assets/trucks/two_ready_rewards.png"))
        self.assertIsNotNone(frame)
        bot.routine_completed_steps.add("trucks_open")
        bot._capture_screen_bgr = Mock(return_value=(frame, (0, 0)))
        bot._tap_routine_fallback = Mock(return_value=True)
        bot._save_routine_calibration_frame = Mock()
        bot._defer_current_routine_unavailable = Mock()
        self.assertTrue(bot._try_trucks_visual_fallback(task))
        self.assertEqual(bot._tap_routine_fallback.call_args.args[0], (207, 410))
        self.assertIn("truck_detail_check_open", bot.routine_completed_steps)
        bot._defer_current_routine_unavailable.assert_not_called()

    def test_later_pass_on_same_account_rechecks_previously_seen_slots(self):
        bot, task = self.make_bot()
        self.assertEqual(bot._begin_due_routine(100.0), task)
        bot.routine_truck_checked_slots = {0, 1}
        bot.current_routine_task_id = None
        bot.current_routine_index = 0
        self.assertEqual(bot._begin_due_routine(200.0), task)
        self.assertEqual(bot.current_account_id, "zzub1")
        self.assertEqual(bot.routine_truck_checked_slots, set())

    def test_active_task_keeps_checked_slots_between_iterations(self):
        bot, task = self.make_bot()
        self.assertEqual(bot._begin_due_routine(100.0), task)
        bot.routine_truck_checked_slots = {0}
        bot.routine_truck_arrival_dismiss_attempts = 2
        self.assertEqual(bot._begin_due_routine(101.0), task)
        self.assertEqual(bot.routine_truck_checked_slots, {0})
        self.assertEqual(bot.routine_truck_arrival_dismiss_attempts, 2)


if __name__ == "__main__":
    unittest.main()
