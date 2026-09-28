import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2
import numpy as np

from buzzbot_app import AutoClicker, _BotActionInterrupted


class MarchCounterIdleTests(unittest.TestCase):
    def loop_bot(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.stop_event = threading.Event()
        bot.stop_hotkey_pressed = False
        bot.is_paused = False
        bot.anti_loop_enabled = False
        bot.routine_mode = True
        bot.current_routine_task_id = None
        bot.routine_last_action_time = 100
        bot.sleep_not_found = 0.1
        bot.sleep_error = 0
        bot._processing_factory_watchdog_due = Mock(return_value=False)
        bot._research_watchdog_due = Mock(return_value=False)
        bot._drain_expired_account_pass = Mock(return_value=False)
        bot._adb_capture_lock = threading.RLock()
        bot._adb_frame_cache = None
        bot._adb_frame_timestamp = 0
        bot._adb_iteration_frame = np.full((4, 4, 3), 5, np.uint8)
        bot._apply_player_resolution = Mock()
        bot.adb_client = Mock()
        return bot

    def test_idle_iterations_do_not_reuse_previously_full_counter_frame(self):
        bot = self.loop_bot()
        bot.adb_client.screenshot_bgr.side_effect = [np.zeros((4, 4, 3), np.uint8), np.ones((4, 4, 3), np.uint8)]
        observed = []

        def idle(_now):
            frame = bot._capture_adb_frame()
            observed.append(int(frame[0, 0, 0]))
            bot._adb_iteration_frame = frame
            if len(observed) == 2:
                bot.stop_event.set()
            return None

        bot._begin_due_routine = idle
        with patch("buzzbot_app.time.monotonic", side_effect=(100, 100, 101, 101)), \
                patch("buzzbot_app.time.sleep"), patch("buzzbot_app.logger.exception") as errors:
            bot._run_clicker_loop()
        errors.assert_not_called()
        self.assertEqual(observed, [0, 1])
        self.assertEqual(bot.adb_client.screenshot_bgr.call_count, 2)
        self.assertIsNone(bot._adb_iteration_frame)

    def test_interrupted_action_also_releases_iteration_snapshot(self):
        bot = self.loop_bot()

        def interrupted(_now):
            bot._adb_iteration_frame = np.ones((4, 4, 3), np.uint8)
            bot.stop_event.set()
            raise _BotActionInterrupted()

        bot._begin_due_routine = interrupted
        bot._run_clicker_loop()
        self.assertIsNone(bot._adb_iteration_frame)

    def waiting_bot(self, active=5, prior_deadline=0):
        bot = AutoClicker.__new__(AutoClicker)
        bot._scheduler_routine_tasks = lambda: [{"id": "zombie_hunt", "enabled": True, "uses_march": True}]
        bot.routine_next_run = {"zombie_hunt": max(160, prior_deadline)}
        bot.routine_last_outcome = {"task_id": "zombie_hunt", "outcome": "deferred_no_squad",
                                   "reason": "all_ordinary_marches_busy", "prior_deadline": prior_deadline}
        bot.get_active_marches = Mock(return_value=active)
        bot.routine_max_marches = 5
        bot.current_account_id = "current"
        bot.routine_pass_completed = True
        bot.get_routine_task_name = lambda task: task["id"]
        bot.set_status_message = Mock()
        bot.save_config = Mock()
        bot.lang = "ru"
        return bot

    def test_returned_squad_releases_only_the_busy_squad_delay(self):
        bot = self.waiting_bot(active=4)
        self.assertTrue(bot._resume_single_account_pass(110))
        self.assertEqual(bot.routine_next_run["zombie_hunt"], 110)
        self.assertFalse(bot.routine_pass_completed)

    def test_independent_long_cooldown_is_preserved_after_return(self):
        bot = self.waiting_bot(active=4, prior_deadline=3600)
        self.assertFalse(bot._resume_single_account_pass(110))
        self.assertEqual(bot.routine_next_run["zombie_hunt"], 3600)
        self.assertTrue(bot.routine_pass_completed)

    def test_full_squads_still_block_and_poll_at_most_once_per_second(self):
        bot = self.waiting_bot()
        for now in (110, 110.1, 110.5, 111):
            self.assertFalse(bot._resume_single_account_pass(now))
        self.assertEqual(bot.get_active_marches.call_count, 2)
        self.assertEqual(bot.routine_next_run["zombie_hunt"], 160)

    def test_stamina_failure_keeps_its_retry_even_when_squads_are_free(self):
        bot = self.waiting_bot(active=0)
        bot.routine_last_outcome = {"task_id": "zombie_hunt", "outcome": "deferred_unavailable", "reason": "stamina"}
        self.assertFalse(bot._resume_single_account_pass(110))
        self.assertEqual(bot.routine_next_run["zombie_hunt"], 160)

    def test_real_returned_world_frame_clears_all_five_local_reservations(self):
        bot = AutoClicker.__new__(AutoClicker)
        root = Path(__file__).resolve().parents[1]
        frame = cv2.imread(str(root / "tests/assets/marches/returned_no_panel.png"))
        observer_ids = ("8ec959ff-a8a3-5d5f-a6e1-7c424fe2fc2f", "c3472b7a-ea0d-5cf3-ac5e-c4cc133d1470",
                        "f6872405-6422-5d53-b942-0e5172674f65", "fccf6262-c737-58b5-8077-04d8437c386a",
                        "6bd93932-4c8d-5130-b66b-b139ca4e6ab6")
        bot.search_images = [{"path": str(root / f"img/system/{uid}.png"), "observer_only": True,
                              "march_count": i} for i, uid in enumerate(observer_ids, 1)]
        bot.template_cache = SimpleNamespace(get_gray=lambda path: cv2.imread(path, cv2.IMREAD_GRAYSCALE))
        bot._capture_screen_bgr = lambda **kw: (frame, (0, 0))
        bot._world_map_visible_in_frame = lambda _frame: True
        bot._ensure_routine_march_context = lambda: False
        bot.routine_display_active_marches = 5
        bot.routine_march_deadlines = [1000] * 5
        bot.routine_max_marches = 5
        bot.routine_confirmed_march_floor = 5
        bot.routine_march_observer_grace_until = 0
        bot.save_config = Mock()
        with patch("buzzbot_app.time.monotonic", side_effect=(100, 103, 107)):
            self.assertEqual([bot.get_active_marches(now=100) for _ in range(3)], [5, 5, 0])
        self.assertEqual(bot.routine_march_deadlines, [])
