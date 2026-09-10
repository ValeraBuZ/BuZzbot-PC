from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from buzzbot.display import make_display_profile
from buzzbot.matching import alliance_donation_attempts_exhausted, imread_unicode
from buzzbot.routines import donation_exhaustion_is_complete
from buzzbot_app import AutoClicker


ASSETS = Path(__file__).parent / "assets" / "alliance_donations"


def captured_counter(name):
    # These are unaltered counter crops from the live pass, before a donation
    # (1/30), after it (0/30), and from the unrelated home screen.
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[490:525, 1040:1140] = imread_unicode(ASSETS / f"counter_{name}.png")
    return frame


class DonationCounterTests(unittest.TestCase):
    def test_live_zero_counter_confirms_exhaustion(self):
        self.assertTrue(alliance_donation_attempts_exhausted(captured_counter("zero")))

    def test_one_remaining_attempt_does_not_confirm_exhaustion(self):
        self.assertFalse(alliance_donation_attempts_exhausted(captured_counter("one")))

    def test_home_and_unreadable_frames_do_not_confirm_exhaustion(self):
        for frame in (captured_counter("home"), None, np.zeros((720, 1280, 3), dtype=np.uint8)):
            with self.subTest(frame_type=type(frame).__name__):
                self.assertFalse(alliance_donation_attempts_exhausted(frame))

    def test_positive_count_ending_in_zero_is_not_zero_attempts(self):
        frame = captured_counter("zero")
        one = captured_counter("one")
        # Construct 10/30 with the actual captured 1 and 0 glyphs, keeping
        # the zero at its real position and moving the colon before the 1.
        colon = frame[501:515, 1077:1080].copy()
        frame[498:517, 1060:1085] = (35, 35, 35)
        frame[501:515, 1066:1069] = colon
        frame[501:514, 1076:1083] = one[501:514, 1085:1092]
        self.assertFalse(alliance_donation_attempts_exhausted(frame))

    def test_counter_is_normalized_for_display_scale(self):
        frame = captured_counter("zero")
        for size in ((1920, 1080), (960, 540)):
            with self.subTest(size=size):
                self.assertTrue(alliance_donation_attempts_exhausted(cv2.resize(frame, size)))

    def make_bot(self, frame):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = Mock()
        bot._check_worker_interrupted = Mock()
        bot.get_display_profile = Mock(return_value=make_display_profile(1280, 720))
        bot._resolve_action_numbers = Mock(return_value=[])
        bot._resource_result_level_rejected = Mock(return_value=False)
        bot._capture_screen_bgr = Mock(return_value=(frame, (0, 0)))
        bot._invalidate_capture = Mock()
        bot.set_status_message = Mock()
        bot._interruptible_sleep = Mock()
        bot.current_routine_task_id = "alliance_donations"
        bot.routine_completed_steps = {"project_closed"}
        bot.cycle_mode = False
        bot.sleep_found = 0
        return bot

    def close_project(self, bot, **overrides):
        image = {
            "action": "click", "runtime_step": "project_closed",
            "description": "Close donation project", "delay": 0,
        }
        image.update(overrides)
        with patch("buzzbot_app.logger"):
            return bot._execute_action(image, SimpleNamespace(x=1122, y=72))

    def test_project_close_sets_explicit_step_only_for_confirmed_zero(self):
        for name, exhausted in (("zero", True), ("one", False), ("home", False)):
            with self.subTest(counter=name):
                bot = self.make_bot(captured_counter(name))
                self.assertTrue(self.close_project(bot))
                bot.adb_client.tap.assert_called_once_with(1122, 72)
                self.assertEqual("donations_exhausted" in bot.routine_completed_steps, exhausted)
                self.assertEqual(donation_exhaustion_is_complete(
                    {"id": "alliance_donations", "exhaustion_idle_seconds": 15},
                    bot.routine_completed_steps, 15,
                ), exhausted)

    def test_read_failure_keeps_normal_close_without_claiming_exhaustion(self):
        bot = self.make_bot(None)
        bot._capture_screen_bgr.side_effect = OSError("frame unavailable")
        self.assertTrue(self.close_project(bot))
        bot.adb_client.tap.assert_called_once_with(1122, 72)
        self.assertNotIn("donations_exhausted", bot.routine_completed_steps)

    def test_other_tasks_and_other_donation_steps_do_not_set_terminal_flag(self):
        for task, step in (("vip_rewards", "project_closed"), ("alliance_donations", "donate_resources")):
            with self.subTest(task=task, step=step):
                bot = self.make_bot(captured_counter("zero"))
                bot.current_routine_task_id = task
                self.assertTrue(self.close_project(bot, runtime_step=step))
                bot._capture_screen_bgr.assert_not_called()
                self.assertNotIn("donations_exhausted", bot.routine_completed_steps)


if __name__ == "__main__":
    unittest.main()
