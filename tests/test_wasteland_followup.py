from pathlib import Path
import unittest
from unittest.mock import Mock

import cv2
import numpy as np

from buzzbot.matching import (
    detect_settlement_event_panel_collapse_target,
    detect_settlement_event_panel_expand_target,
    imread_unicode,
)
from buzzbot.routines import routine_missing_followup_is_unavailable
from buzzbot_app import AutoClicker, _BotActionInterrupted


def captured_panel(state):
    # Unaltered 24x50 control crops from pass1/game_login.png (expanded)
    # and pass1/wasteland_exploration.png (collapsed), September 8-9, 2026.
    # The crops contain no account, chat, login or password information.
    crop = imread_unicode(Path(__file__).parent / "assets/wasteland_event_panel" / f"{state}.png")
    frame = np.full((720, 1280, 3), (70, 80, 85), dtype=np.uint8)
    frame[58:108, 451:475] = crop
    return frame


class WastelandEventPanelTests(unittest.TestCase):
    def make_bot(self, panel="collapsed"):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = Mock()
        bot.current_account_id = "account"
        bot.routine_task_started_at = 100.0
        bot.routine_completed_steps = set()
        bot.get_routine_templates = Mock(return_value=[{"runtime_step": "event_entry"}])
        bot._is_settlement_screen_visible = Mock(return_value=True)
        bot._locate_image = Mock(return_value=(None, None, 0.36))
        bot._capture_screen_bgr = Mock(return_value=(captured_panel(panel), (0, 0)))
        bot._check_worker_interrupted = Mock()
        bot._tap_routine_fallback = Mock(return_value=True)
        return bot

    def task(self):
        return {"id": "wasteland_exploration", "timeout_seconds": 120.0}

    def test_captured_collapsed_control_is_detected_and_expanded_control_rejected(self):
        self.assertEqual(detect_settlement_event_panel_expand_target(captured_panel("collapsed")), (463, 83))
        self.assertIsNone(detect_settlement_event_panel_expand_target(captured_panel("expanded")))
        self.assertIsNone(detect_settlement_event_panel_expand_target(np.zeros((720, 1280, 3), dtype=np.uint8)))
        self.assertIsNone(detect_settlement_event_panel_expand_target(None))

    def test_existing_collapse_detector_keeps_opposite_direction(self):
        self.assertEqual(detect_settlement_event_panel_collapse_target(captured_panel("expanded")), (463, 83))
        self.assertIsNone(detect_settlement_event_panel_collapse_target(captured_panel("collapsed")))

    def test_captured_control_scales_to_android_display(self):
        frame = cv2.resize(captured_panel("collapsed"), (640, 360))
        self.assertEqual(detect_settlement_event_panel_expand_target(frame), (232, 42))

    def test_missing_entry_opens_confirmed_collapsed_panel_only_once_per_run(self):
        bot = self.make_bot()
        self.assertTrue(bot._try_wasteland_event_panel_fallback(self.task()))
        self.assertFalse(bot._try_wasteland_event_panel_fallback(self.task()))
        bot._tap_routine_fallback.assert_called_once_with(
            (463, 83), ("wasteland_event_panel_expand", 463, 83),
            "Исследование пустоши: раскрываю панель событий",
        )
        self.assertEqual(bot.routine_completed_steps, set())
        self.assertTrue(routine_missing_followup_is_unavailable(self.task(), {"event_entry"}, 20.0))
        bot.adb_client.tap.assert_not_called()

    def test_new_run_gets_one_new_attempt_without_changing_schedule(self):
        bot = self.make_bot()
        bot.routine_next_run = {"wasteland_exploration": 12345.0}
        self.assertTrue(bot._try_wasteland_event_panel_fallback(self.task()))
        bot.routine_task_started_at = 200.0
        self.assertTrue(bot._try_wasteland_event_panel_fallback(self.task()))
        self.assertEqual(bot._tap_routine_fallback.call_count, 2)
        self.assertEqual(bot.routine_next_run, {"wasteland_exploration": 12345.0})

    def test_visible_event_entry_does_not_toggle_its_panel(self):
        bot = self.make_bot()
        bot._locate_image.return_value = ((500, 100), (455, 55, 90, 90), 0.93)
        self.assertFalse(bot._try_wasteland_event_panel_fallback(self.task()))
        bot._capture_screen_bgr.assert_not_called()
        bot._tap_routine_fallback.assert_not_called()

    def test_expanded_panel_is_not_toggled_even_when_event_is_absent(self):
        bot = self.make_bot(panel="expanded")
        self.assertFalse(bot._try_wasteland_event_panel_fallback(self.task()))
        bot._tap_routine_fallback.assert_not_called()

    def test_missing_settlement_or_missing_enabled_entry_prevents_input(self):
        for absent in ("settlement", "entry"):
            with self.subTest(absent=absent):
                bot = self.make_bot()
                if absent == "settlement":
                    bot._is_settlement_screen_visible.return_value = False
                else:
                    bot.get_routine_templates.return_value = []
                self.assertFalse(bot._try_wasteland_event_panel_fallback(self.task()))
                bot._tap_routine_fallback.assert_not_called()

    def test_running_event_and_unrelated_tasks_are_left_untouched(self):
        for progress in ({"event_entry"}, {"explore"}):
            with self.subTest(progress=progress):
                bot = self.make_bot()
                bot.routine_completed_steps = progress
                self.assertFalse(bot._try_wasteland_event_panel_fallback(self.task()))
                bot._tap_routine_fallback.assert_not_called()
        bot = self.make_bot()
        self.assertFalse(bot._try_wasteland_event_panel_fallback({"id": "research"}))
        bot._tap_routine_fallback.assert_not_called()

    def test_failed_tap_is_bounded_and_adds_no_progress(self):
        bot = self.make_bot()
        bot._tap_routine_fallback.return_value = False
        self.assertFalse(bot._try_wasteland_event_panel_fallback(self.task()))
        self.assertFalse(bot._try_wasteland_event_panel_fallback(self.task()))
        bot._tap_routine_fallback.assert_called_once()
        self.assertEqual(bot.routine_completed_steps, set())

    def test_worker_cancellation_is_checked_before_toggle(self):
        bot = self.make_bot()
        bot._check_worker_interrupted.side_effect = _BotActionInterrupted
        with self.assertRaises(_BotActionInterrupted):
            bot._try_wasteland_event_panel_fallback(self.task())
        bot._tap_routine_fallback.assert_not_called()
        self.assertFalse(hasattr(bot, "_wasteland_event_panel_attempt_key"))


if __name__ == "__main__":
    unittest.main()
