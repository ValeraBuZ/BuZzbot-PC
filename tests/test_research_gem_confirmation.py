from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

import cv2
import numpy as np

from buzzbot.matching import detect_gem_confirmation_cancel_target
from buzzbot_app import AutoClicker, BotState


class ResearchGemConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.frame = cv2.imread(str(Path(__file__).parent / "assets/research/gem_confirmation.png"))
        self.assertIsNotNone(self.frame)
        self.clear = np.zeros_like(self.frame)

    def bot(self, frames):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.player_width = 1280
        bot.player_height = 720
        bot.adb_client = Mock()
        bot.routine_completed_steps = {"lab", "select"}
        bot._capture_screen_bgr = Mock(side_effect=[(frame, (0, 0)) for frame in frames])
        bot._save_routine_calibration_frame = Mock()
        bot._invalidate_capture = Mock()
        bot._interruptible_sleep = Mock()
        bot._defer_current_routine_unavailable = Mock()
        bot._finish_current_routine = Mock()
        bot._set_state = Mock()
        bot.set_status_message = Mock()
        bot.save_config = Mock()
        bot.stop_event = threading.Event()
        return bot

    def test_real_paid_modal_only_returns_the_no_button_at_supported_sizes(self):
        for w, h in ((1280, 720), (1920, 1080)):
            with self.subTest(size=(w, h)):
                self.assertEqual(
                    detect_gem_confirmation_cancel_target(cv2.resize(self.frame, (w, h))),
                    (round(495*w/1280), round(509*h/720)),
                )

    def test_other_confirmation_dialogs_require_every_paid_modal_guard(self):
        for x1, y1, x2, y2 in (
            (555, 170, 720, 220), (450, 480, 540, 537),
            (730, 440, 790, 488), (655, 488, 908, 529),
        ):
            modified = self.frame.copy()
            modified[y1:y2, x1:x2] = 0
            self.assertIsNone(detect_gem_confirmation_cancel_target(modified))
        self.assertIsNone(detect_gem_confirmation_cancel_target(self.clear))

    def test_variable_price_does_not_affect_cancellation(self):
        modified = self.frame.copy()
        modified[303:337, 640:850] = 100
        modified[453:481, 777:835] = 100
        self.assertEqual(detect_gem_confirmation_cancel_target(modified), (495, 509))

    def test_existing_modal_is_cancelled_even_after_resume_without_lab_step(self):
        bot = self.bot([self.frame, self.clear])
        bot.routine_completed_steps = set()
        self.assertTrue(bot._try_research_visual_fallback({"id": "research"}))
        bot.adb_client.tap.assert_called_once_with(495, 509)
        bot._defer_current_routine_unavailable.assert_called_once()
        bot._finish_current_routine.assert_not_called()
        self.assertFalse(bot.stop_event.is_set())

    def test_modal_opened_by_research_action_is_not_treated_as_started(self):
        before = self.clear.copy()
        bot = self.bot([before, self.frame, self.clear])
        with patch("buzzbot_app.detect_research_action_target", return_value=(980, 590)):
            self.assertTrue(bot._try_research_visual_fallback({"id": "research"}))
        self.assertEqual([call.args for call in bot.adb_client.tap.call_args_list],
                         [(980, 590), (495, 509)])
        bot._defer_current_routine_unavailable.assert_called_once()
        bot._finish_current_routine.assert_not_called()
        self.assertNotIn("confirm", bot.routine_completed_steps)

    def test_undismissable_modal_stops_with_current_queue_preserved(self):
        bot = self.bot([self.frame, self.frame, self.frame])
        self.assertTrue(bot._try_research_visual_fallback({"id": "research"}))
        self.assertEqual([call.args for call in bot.adb_client.tap.call_args_list],
                         [(495, 509), (495, 509)])
        self.assertTrue(bot.stop_event.is_set())
        bot._set_state.assert_called_once_with(BotState.STOPPED)
        bot._defer_current_routine_unavailable.assert_not_called()
        bot._finish_current_routine.assert_not_called()
        bot.save_config.assert_called_once()

    def test_template_confirmation_never_clicks_an_existing_paid_modal(self):
        bot = self.bot([self.frame])
        bot._resolve_action_numbers = Mock(return_value=[])
        bot._resource_result_level_rejected = Mock(return_value=False)
        self.assertFalse(bot._execute_action(
            {"action": "research_confirm", "click_offset": (0, 0), "last_used": 0},
            SimpleNamespace(x=782, y=509),
        ))
        bot.adb_client.tap.assert_not_called()


if __name__ == "__main__":
    unittest.main()
