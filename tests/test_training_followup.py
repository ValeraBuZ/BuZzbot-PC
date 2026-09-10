import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np

from buzzbot_app import AutoClicker


class TrainingEventPanelRegressionTests(unittest.TestCase):
    def make_bot(self, expanded=True):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = Mock()
        bot._training_step_visible = Mock(return_value=None)
        bot._is_settlement_screen_visible = Mock(return_value=True)
        bot._return_to_main_screen = Mock(return_value=True)
        bot._tap_routine_fallback = Mock(return_value=True)
        bot._defer_current_routine_unavailable = Mock()
        bot._invalidate_capture = Mock()
        bot._interruptible_sleep = Mock()
        bot.get_display_profile = Mock(return_value=SimpleNamespace(scale_x=1, scale_y=1))
        bot.get_routine_task_name = Mock(return_value="Training")
        bot.set_status_message = Mock()
        bot.routine_action_counts = {}
        bot.routine_completed_steps = set()
        bot.click_count = 0
        frame = np.full((720, 1280, 3), (70, 80, 85), dtype=np.uint8)
        cv2.rectangle(frame, (451, 58), (474, 107), (25, 28, 30), thickness=-1)
        points = ((458, 74), (468, 82), (458, 90)) if expanded else ((468, 74), (458, 82), (468, 90))
        cv2.line(frame, points[0], points[1], (185, 190, 195), thickness=4)
        cv2.line(frame, points[1], points[2], (185, 190, 195), thickness=4)
        bot._capture_screen_bgr = Mock(return_value=(frame, (0, 0)))
        return bot

    def test_hidden_barracks_title_collapses_ribbon_before_spending_queue_checks(self):
        for task_id in ("train_infantry", "train_riders", "train_shooters", "train_vehicles"):
            with self.subTest(task_id=task_id):
                bot = self.make_bot()
                bot.routine_action_counts["training_queue_fallback_checks"] = 4
                self.assertTrue(bot._try_training_catalogue_fallback({"id": task_id}))
                self.assertEqual(bot._tap_routine_fallback.call_args.args[0], (463, 83))
                bot.adb_client.tap.assert_not_called()
                bot._defer_current_routine_unavailable.assert_not_called()
                self.assertEqual(bot.routine_action_counts["training_queue_fallback_checks"], 4)
                self.assertEqual(bot.routine_completed_steps, set())

    def test_collapsed_ribbon_keeps_existing_queue_navigation(self):
        bot = self.make_bot(expanded=False)
        self.assertTrue(bot._try_training_catalogue_fallback({"id": "train_infantry"}))
        bot._tap_routine_fallback.assert_not_called()
        bot.adb_client.tap.assert_called_once_with(42, 330)
        self.assertEqual(bot.routine_action_counts["training_queue_fallback_checks"], 1)
        self.assertEqual(bot.routine_completed_steps, set())

    def test_confirmed_requested_barracks_opens_before_repeatable_overview(self):
        bot = self.make_bot()
        bot._training_step_visible.side_effect = [None, (Mock(), Mock(), Mock(), 0.95)]
        bot._open_training_from_barracks = Mock(return_value=True)
        self.assertTrue(bot._try_training_catalogue_fallback({"id": "train_infantry"}))
        bot._open_training_from_barracks.assert_called_once()
        bot._capture_screen_bgr.assert_not_called()
        bot.adb_client.tap.assert_not_called()

    def test_failed_ribbon_click_does_not_advance_or_click_queue(self):
        bot = self.make_bot()
        bot._tap_routine_fallback.return_value = False
        self.assertFalse(bot._try_training_catalogue_fallback({"id": "train_infantry"}))
        bot.adb_client.tap.assert_not_called()
        self.assertEqual(bot.routine_action_counts, {})

    def test_wrong_screen_is_recovered_before_ribbon_or_queue_clicks(self):
        bot = self.make_bot()
        bot._is_settlement_screen_visible.return_value = False
        self.assertTrue(bot._try_training_catalogue_fallback({"id": "train_infantry"}))
        bot._return_to_main_screen.assert_called_once_with(max_back_steps=4, require_settlement=True)
        bot._capture_screen_bgr.assert_not_called()
        bot.adb_client.tap.assert_not_called()

    def test_unrecognized_barracks_is_not_reported_as_confirmed_busy_queue(self):
        bot = self.make_bot(expanded=False)
        bot.routine_action_counts["training_queue_fallback_checks"] = 5
        self.assertTrue(bot._try_training_catalogue_fallback({"id": "train_infantry"}))
        self.assertEqual(bot._defer_current_routine_unavailable.call_args.args[0], "не удалось подтвердить нужные казармы")
        bot.adb_client.tap.assert_not_called()


if __name__ == "__main__":
    unittest.main()
