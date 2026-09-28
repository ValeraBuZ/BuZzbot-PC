"""A closed March panel is not proof that the selected mission was sent."""

import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import cv2
import numpy as np

from buzzbot.matching import imread_unicode
from buzzbot_app import AutoClicker


class RadarDispatchVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.available = imread_unicode(root / "tests/assets/radar/available_event_expiry.png")
        label = imread_unicode(root / "buzzbot/assets/radar/in_progress_label.png")
        if cls.available is None or label is None:
            raise AssertionError("Required captured radar fixtures are unavailable")
        # Composite: the real available-card capture with a captured running
        # label. Its event identity stays identical to the original card.
        cls.in_progress = cls.available.copy()
        height, width = label.shape[:2]
        cls.in_progress[595:595 + height, 180:180 + width] = label

    def make_bot(self, frame=None):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = Mock()
        bot.stop_event = threading.Event()
        bot.stop_hotkey_pressed = False
        bot.is_paused = False
        bot.anti_loop_enabled = False
        bot.blocked_coords = {}
        bot.routine_radar_pending_marker_key = ("marker", 640, 360)
        bot.routine_radar_confirmed_marker_keys = set()
        bot.routine_radar_marker_failure_counts = {}
        bot.routine_radar_card_identity = cv2.resize(self.available, (1280, 720))[160:335, 70:420].copy()
        bot.routine_radar_dispatch_candidate = None
        bot.routine_radar_dispatched_this_pass = False
        bot.routine_radar_in_progress_seen = False
        bot.routine_action_counts = {}
        bot.routine_completed_steps = {"radar_open", "radar_marker", "radar_forward", "radar_action", "radar_squad"}
        bot.routine_current_had_action = False
        bot.routine_last_action_time = 90.0
        bot._capture_screen_bgr = Mock(return_value=(self.available if frame is None else frame, (0, 0)))
        bot._check_worker_interrupted = Mock()
        bot._world_map_visible_in_frame = Mock(return_value=False)
        bot._is_main_screen_visible = Mock(return_value=False)
        bot._is_settlement_screen_visible = Mock(return_value=False)
        bot._return_to_main_screen = Mock(return_value=True)
        bot._tap_radar_fallback = Mock(return_value=True)
        bot._tap_routine_fallback = Mock(return_value=True)
        bot._invalidate_capture = Mock()
        bot._interruptible_sleep = Mock()
        bot._save_routine_calibration_frame = Mock()
        bot._defer_current_routine_unavailable = Mock()
        bot._finish_current_routine = Mock()
        bot.set_status_message = Mock()
        bot.save_config = Mock()
        task = {"id": "radar_marches", "settings": {"visual_fallback": True}}
        return bot, task

    def make_candidate(self, bot, *, opened=True, attempts=1, started_at=95.0):
        bot.routine_radar_dispatch_candidate = {
            "marker": bot.routine_radar_pending_marker_key,
            "identity": bot.routine_radar_card_identity.copy(),
            "started_at": started_at, "opened": opened, "attempts": attempts,
        }

    def assert_no_dispatch(self, bot):
        self.assertFalse(bot.routine_radar_dispatched_this_pass)
        self.assertFalse(bot.routine_radar_in_progress_seen)
        self.assertEqual(bot.routine_action_counts.get("radar_dispatches", 0), 0)
        self.assertEqual(bot.routine_radar_confirmed_marker_keys, set())
        bot._finish_current_routine.assert_not_called()

    @patch("buzzbot_app.time.time", return_value=100.0)
    @patch("buzzbot_app.radar_task_card_is_visible", return_value=False)
    @patch("buzzbot_app.detect_radar_deployment_prompt_target", return_value=None)
    @patch("buzzbot_app.detect_radar_squad_march_target", return_value=None)
    def test_two_world_frames_create_only_a_candidate_without_counting_dispatch(self, *_mocks):
        bot, _task = self.make_bot(np.zeros((720, 1280, 3), dtype=np.uint8))
        bot._world_map_visible_in_frame.return_value = True
        bot._confirm_radar_squad_dispatch()
        self.assertEqual(bot._capture_screen_bgr.call_count, 2)
        self.assert_no_dispatch(bot)
        candidate = bot.routine_radar_dispatch_candidate
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["marker"], ("marker", 640, 360))
        self.assertEqual(candidate["started_at"], 100.0)
        self.assertFalse(candidate["opened"])
        self.assertEqual(candidate["attempts"], 0)
        np.testing.assert_array_equal(candidate["identity"], bot.routine_radar_card_identity)

    @patch("buzzbot_app.time.time", return_value=100.0)
    @patch("buzzbot_app.radar_task_card_is_visible", return_value=False)
    @patch("buzzbot_app.detect_radar_deployment_prompt_target", return_value=None)
    @patch("buzzbot_app.detect_radar_squad_march_target", return_value=None)
    def test_one_transient_world_frame_keeps_attempt_unconfirmed_and_locked(self, *_mocks):
        bot, _task = self.make_bot(np.zeros((720, 1280, 3), dtype=np.uint8))
        bot._world_map_visible_in_frame.side_effect = [True] + [False] * 11
        self.assertFalse(bot._confirm_radar_squad_dispatch())
        self.assertIsNotNone(bot.routine_radar_dispatch_candidate)
        self.assert_no_dispatch(bot)
        self.assertLessEqual(bot._capture_screen_bgr.call_count, 12)
        # Another visual fallback must reconcile this attempt rather than
        # interpreting the same March screen as permission to send again.
        captures = bot._capture_screen_bgr.call_count
        self.assertFalse(bot._confirm_radar_squad_dispatch())
        self.assertEqual(bot._capture_screen_bgr.call_count, captures)

    @patch("buzzbot_app.time.time", return_value=100.0)
    def test_same_card_with_captured_in_progress_label_confirms_once(self, _clock):
        bot, task = self.make_bot(self.in_progress)
        self.make_candidate(bot)
        self.assertTrue(bot._try_confirm_pending_radar_dispatch(task))
        self.assertTrue(bot.routine_radar_dispatched_this_pass)
        self.assertTrue(bot.routine_radar_in_progress_seen)
        self.assertEqual(bot.routine_action_counts["radar_dispatches"], 1)
        self.assertIn(("marker", 640, 360), bot.routine_radar_confirmed_marker_keys)
        self.assertIsNone(bot.routine_radar_dispatch_candidate)
        self.assertNotIn("radar_forward", bot.routine_completed_steps)
        bot._return_to_main_screen.assert_called()
        self.assertFalse(bot._try_confirm_pending_radar_dispatch(task))
        self.assertEqual(bot.routine_action_counts["radar_dispatches"], 1)

    @patch("buzzbot_app.time.time", return_value=100.0)
    def test_real_available_event_expiry_cannot_confirm_a_dispatch(self, _clock):
        bot, task = self.make_bot(self.available)
        self.make_candidate(bot)
        self.assertTrue(bot._try_confirm_pending_radar_dispatch(task))
        self.assert_no_dispatch(bot)

    @patch("buzzbot_app.time.time", return_value=100.0)
    def test_other_card_with_running_label_cannot_confirm_the_selected_mission(self, _clock):
        frame = self.in_progress.copy()
        frame[160:335, 70:420] = 255 - frame[160:335, 70:420]
        bot, task = self.make_bot(frame)
        self.make_candidate(bot)
        self.assertTrue(bot._try_confirm_pending_radar_dispatch(task))
        self.assert_no_dispatch(bot)

    @patch("buzzbot_app.time.time", return_value=150.0)
    def test_unproved_candidate_expires_without_repeating_march(self, _clock):
        bot, task = self.make_bot(self.available)
        self.make_candidate(bot, opened=False, attempts=0, started_at=100.0)
        self.assertTrue(bot._try_confirm_pending_radar_dispatch(task))
        self.assert_no_dispatch(bot)
        bot._defer_current_routine_unavailable.assert_called_once()
        bot._tap_radar_fallback.assert_not_called()

    @patch("buzzbot_app.time.time", return_value=100.0)
    @patch("buzzbot_app.radar_task_card_is_visible", return_value=False)
    @patch("buzzbot_app.radar_overview_is_visible", return_value=True)
    def test_card_reopens_at_most_twice_before_explicit_deferral(self, *_mocks):
        bot, task = self.make_bot(np.zeros((720, 1280, 3), dtype=np.uint8))
        self.make_candidate(bot, opened=False, attempts=0)
        for current_time in (100.0, 100.5, 103.0, 106.0, 106.1):
            _mocks[-1].return_value = current_time
            self.assertTrue(bot._try_confirm_pending_radar_dispatch(task))
            if current_time == 100.5:
                self.assertEqual(bot.adb_client.tap.call_count, 1)
        self.assertEqual(bot.adb_client.tap.call_count, 2)
        self.assertEqual(bot.adb_client.tap.call_args_list[0].args, (640, 360))
        bot._defer_current_routine_unavailable.assert_called_once()
        self.assertIsNone(bot.routine_radar_dispatch_candidate)
        self.assert_no_dispatch(bot)

    def test_unrelated_in_progress_guard_cannot_consume_pending_dispatch(self):
        bot, task = self.make_bot(self.in_progress)
        self.make_candidate(bot)
        self.assertFalse(bot._try_radar_in_progress_card_fallback(task))
        bot._capture_screen_bgr.assert_not_called()
        self.assert_no_dispatch(bot)

    def test_other_account_cannot_reuse_pending_march_proof(self):
        bot, task = self.make_bot(self.in_progress)
        self.make_candidate(bot)
        bot.routine_radar_dispatch_candidate["account_id"] = "previous"
        bot.current_account_id = "current"
        self.assertFalse(bot._try_confirm_pending_radar_dispatch(task))
        bot._capture_screen_bgr.assert_not_called()
        self.assertIsNone(bot.routine_radar_dispatch_candidate)
        self.assert_no_dispatch(bot)

    @patch("buzzbot_app.time.time", return_value=100.0)
    def test_pending_candidate_owns_radar_fallback_before_another_march(self, _clock):
        bot, task = self.make_bot(self.available)
        self.make_candidate(bot)
        bot._try_radar_visual_fallback = Mock(side_effect=AssertionError("unproved March repeated"))
        self.assertTrue(bot._try_radar_pending_card_fallback(task))
        bot._try_radar_visual_fallback.assert_not_called()
        bot._tap_radar_fallback.assert_not_called()
        self.assert_no_dispatch(bot)


if __name__ == "__main__":
    unittest.main()
