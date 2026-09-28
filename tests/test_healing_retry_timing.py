from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import cv2

import test_healing as healing_fixture


class HealingRetryTimingTests(unittest.TestCase):
    def frame(self, name):
        frame = cv2.imread(str(Path(__file__).parent / "assets/healing" / name))
        self.assertIsNotNone(frame)
        return frame

    def make_bot(self):
        bot = healing_fixture.HealingTests().make_bot(iter(()))
        task = {
            "id": "heal", "group": "Лечение войск",
            "settings": {
                "collection_delay_seconds": 2, "_collection_pending": True,
                "_last_heal_started_at": 90.0, "_hospital_target": [1170, 178],
            },
        }
        bot._healing_settings = task["settings"]
        bot.current_routine_task_id = "heal"
        bot.current_routine_index = 25
        bot.routine_completed_steps = {"open_wounded", "start_healing"}
        bot.routine_next_run = {}
        bot.routine_action_counts = {"start_healing": 1}
        bot._is_main_screen_visible = Mock(return_value=True)
        bot._is_settlement_screen_visible = Mock(return_value=True)
        bot._tap_routine_fallback = Mock(return_value=True)
        bot._healing_start_control_visible = Mock(return_value=False)
        bot._defer_current_routine_unavailable = Mock(side_effect=AssertionError("normal collection must not enter failure cooldown"))
        bot._interruptible_sleep = Mock()
        bot._return_to_main_screen = Mock()
        bot.stats = {}
        bot.click_count = 0
        return bot, task

    def test_two_second_collection_delay_preserves_progress_and_does_not_tap_early(self):
        bot, task = self.make_bot()
        task["settings"]["_last_heal_started_at"] = 99.0
        bot._capture_screen_bgr = Mock(return_value=(self.frame("after_collection.png"), (0, 0)))
        with patch("buzzbot_app.time.time", return_value=100.0):
            self.assertTrue(bot._try_healing_visual_fallback(task, remembered_only=True))
        bot._interruptible_sleep.assert_called_once_with(1.0)
        bot._tap_routine_fallback.assert_not_called()
        bot._return_to_main_screen.assert_not_called()
        self.assertEqual(bot.routine_next_run["heal"], 101.0)
        self.assertEqual(bot.routine_completed_steps, {"open_wounded", "start_healing"})
        self.assertEqual(bot.current_routine_index, 25)
        self.assertTrue(task["settings"]["_collection_pending"])

    def test_collection_on_map_reopens_same_hospital_after_two_seconds_before_claiming_success(self):
        bot, task = self.make_bot()
        before = self.frame("ready_collection.png")
        after = self.frame("after_collection.png")
        bot._capture_screen_bgr = Mock(side_effect=[(before, (0, 0)), (after, (0, 0))])
        with patch("buzzbot_app.time.time", return_value=100.0):
            self.assertTrue(bot._try_healing_visual_fallback(task, remembered_only=True))
        bot._interruptible_sleep.assert_called_once_with(2.0)
        self.assertTrue(task["settings"]["_collection_pending"])
        self.assertEqual(task["settings"]["_hospital_target"], [1170, 178])
        self.assertEqual(bot.routine_completed_steps, {"open_wounded", "start_healing"})

        bot.search_images = [{"enabled": True, "action": "heal_troops", "group": task["group"], "runtime_step": "start_healing"}]
        bot._capture_screen_bgr.side_effect = [(after, (0, 0)), (healing_fixture.HealingTests.healing_form(selected=True), (0, 0))]
        bot._healing_start_control_visible.return_value = True
        def execute_after_collection(_image, _location):
            self.assertFalse(task["settings"]["_collection_pending"])
            return True
        bot._execute_action = Mock(side_effect=execute_after_collection)
        with patch("buzzbot_app.time.time", return_value=102.0):
            self.assertTrue(bot._try_healing_visual_fallback(task, remembered_only=True))
        self.assertEqual([c.args[0] for c in bot._tap_routine_fallback.call_args_list], [(1170, 178), (1170, 178)])
        bot._execute_action.assert_called_once()
        bot._return_to_main_screen.assert_not_called()
        self.assertEqual(bot.current_routine_index, 25)

    def test_recent_hospital_click_waits_only_for_remaining_delay(self):
        bot, task = self.make_bot()
        task["settings"]["_last_saved_hospital_attempt_at"] = 99.0
        bot._capture_screen_bgr = Mock(return_value=(self.frame("after_collection.png"), (0, 0)))
        with patch("buzzbot_app.time.time", return_value=100.0):
            self.assertTrue(bot._try_healing_visual_fallback(task, remembered_only=True))
        bot._interruptible_sleep.assert_called_once_with(1.0)
        bot._tap_routine_fallback.assert_not_called()
        self.assertTrue(task["settings"]["_collection_pending"])


if __name__ == "__main__":
    unittest.main()
