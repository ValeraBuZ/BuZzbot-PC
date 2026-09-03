import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

from buzzbot_app import AutoClicker


class ResearchAutomationTests(unittest.TestCase):
    @staticmethod
    def make_action_bot(frames):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = SimpleNamespace(taps=[])
        bot.adb_client.tap = lambda x, y: bot.adb_client.taps.append((x, y))
        bot.adb_client.swipes = []
        bot.adb_client.swipe = (
            lambda *args: bot.adb_client.swipes.append(tuple(args))
        )
        bot.adb_client.keyevents = []
        bot.adb_client.keyevent = (
            lambda key: bot.adb_client.keyevents.append(key)
        )
        bot.sleep_found = 0.1
        bot.get_display_profile = lambda: SimpleNamespace(
            width=1280,
            height=720,
            scale_x=1.0,
            scale_y=1.0,
        )
        bot._resolve_action_numbers = lambda _image: []
        bot._resource_result_level_rejected = lambda _image: False
        bot._invalidate_capture = lambda: None
        bot._interruptible_sleep = lambda _seconds: None
        bot._capture_screen_bgr = lambda **_kwargs: (next(frames), (0, 0))
        bot.set_status_message = lambda *_args, **_kwargs: None
        return bot

    def test_research_queue_opens_centred_lab_before_radial_action(self):
        selected = np.full((720, 1280, 3), (85, 115, 90), dtype=np.uint8)
        radial = selected.copy()
        radial[365:450, 745:835] = (25, 170, 220)
        research = np.full_like(selected, (90, 110, 120))
        research[90:650, 120:1160] = (35, 38, 42)
        research[100:610, 35:110] = (30, 33, 36)
        bot = self.make_action_bot(iter((selected, radial, research)))
        image = {
            "action": "select_research_queue",
            "click_offset": (0, 0),
            "last_used": 0.0,
        }

        result = bot._execute_action(image, SimpleNamespace(x=12, y=218))

        self.assertIsNone(result)
        self.assertEqual(
            bot.adb_client.taps,
            [(12, 218), (620, 320), (755, 475)],
        )
        self.assertGreater(image["last_used"], 0.0)

    def test_research_queue_holds_when_lab_menu_does_not_open(self):
        unchanged = np.zeros((72, 128, 3), dtype=np.uint8)
        bot = self.make_action_bot(iter((unchanged,) * 4))
        image = {
            "action": "select_research_queue",
            "click_offset": (0, 0),
            "last_used": 0.0,
        }

        result = bot._execute_action(image, SimpleNamespace(x=12, y=218))

        self.assertFalse(result)
        self.assertEqual(
            bot.adb_client.taps,
            [(12, 218), (620, 320), (640, 300), (600, 340)],
        )
        self.assertEqual(image["last_used"], 0.0)

    def test_active_research_timer_completes_without_opening_radial_menu(self):
        active = np.zeros((720, 1280, 3), dtype=np.uint8)
        active[406:414, 579:636] = (40, 210, 70)
        active[406:414, 636:730] = (5, 5, 5)
        bot = self.make_action_bot(iter((active,)))
        bot.routine_completed_steps = set()
        bot.routine_action_completes_task = False
        image = {
            "action": "select_research_queue",
            "click_offset": (0, 0),
            "last_used": 0.0,
        }

        result = bot._execute_action(image, SimpleNamespace(x=12, y=218))

        self.assertIsNone(result)
        self.assertEqual(bot.adb_client.taps, [(12, 218)])
        self.assertEqual(bot.routine_completed_steps, {"confirm"})
        self.assertTrue(bot.routine_action_completes_task)

    def test_unconfirmed_research_holds_the_ordered_queue(self):
        bot = AutoClicker.__new__(AutoClicker)
        task = {"id": "research", "interval_minutes": 5.0}
        bot.current_routine_task_id = "research"
        bot.get_routine_task = lambda _task_id: task
        bot.routine_next_run = {}
        bot.routine_task_started_at = 90.0
        bot.routine_research_budget_started_at = 90.0
        bot.routine_completed_steps = {"lab", "select"}
        bot.routine_current_action_count = 1
        bot.routine_current_had_action = True
        bot.routine_action_counts = {"selection": 1}
        bot.routine_idle_confirmation_count = 1
        bot.routine_home_recovery_attempted = True
        bot.routine_idle_guard_visible = True
        bot.routine_idle_outside_since = 50.0
        bot.routine_idle_recovery_attempted = True
        returned = []
        bot._return_to_main_screen = lambda **kwargs: returned.append(kwargs) or True
        bot.set_status_message = lambda *_args, **_kwargs: None
        bot.save_config = lambda: None
        sleeps = []
        bot._interruptible_sleep = lambda seconds: sleeps.append(seconds)
        advanced = []
        bot._advance_routine_after_outcome = (
            lambda *_args, **_kwargs: advanced.append(True)
        )

        with patch("buzzbot_app.time.time", return_value=101.0):
            bot._defer_current_routine_no_action(now=100.0)

        self.assertEqual(bot.current_routine_task_id, "research")
        self.assertEqual(bot.routine_next_run["research"], 130.0)
        self.assertEqual(bot.routine_completed_steps, set())
        self.assertEqual(bot.routine_task_started_at, 90.0)
        self.assertEqual(bot.routine_research_budget_started_at, 90.0)
        self.assertEqual(advanced, [])
        self.assertEqual(returned, [{"max_back_steps": 5, "require_settlement": True}])
        self.assertEqual(sleeps, [30.0])

    def test_unconfirmed_research_is_deferred_after_cumulative_budget(self):
        bot = AutoClicker.__new__(AutoClicker)
        task = {"id": "research", "interval_minutes": 5.0}
        bot.current_routine_task_id = "research"
        bot.get_routine_task = lambda _task_id: task
        bot.routine_next_run = {}
        bot.routine_task_started_at = 100.0
        bot.routine_research_budget_started_at = 100.0
        bot.routine_completed_steps = {"lab", "select"}
        bot.routine_current_action_count = 3
        bot.routine_current_had_action = True
        bot.routine_action_counts = {"selection": 3}
        bot.routine_action_failure_reason = ""
        bot.routine_idle_confirmation_count = 1
        bot.routine_home_recovery_attempted = True
        bot.routine_idle_guard_visible = True
        bot.routine_idle_outside_since = 50.0
        bot.routine_idle_recovery_attempted = True
        bot.account_pass_started_at = 100.0
        bot.account_pass_account_id = "a"
        bot.current_account_id = "a"
        bot._return_to_main_screen = lambda **_kwargs: True
        bot.set_status_message = lambda *_args, **_kwargs: None
        bot.save_config = lambda: None
        bot._interruptible_sleep = lambda _seconds: self.fail(
            "expired research budget must not sleep for another retry"
        )
        advanced = []
        bot._advance_routine_after_outcome = (
            lambda task_arg, now_arg: advanced.append((task_arg["id"], now_arg))
        )

        bot._defer_current_routine_no_action(now=191.0)

        self.assertIsNone(bot.current_routine_task_id)
        self.assertEqual(bot.routine_next_run["research"], 251.0)
        self.assertEqual(bot.routine_last_outcome["outcome"], "deferred_stalled")
        self.assertEqual(
            bot.routine_last_outcome["reason"],
            "unconfirmed_research_budget",
        )
        self.assertEqual(advanced, [("research", 191.0)])

    def test_collected_result_is_not_clicked_twice_before_selection(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_completed_steps = {"lab", "collect"}
        captures = []
        frame = np.full((720, 1280, 3), (85, 115, 90), dtype=np.uint8)
        bot._capture_screen_bgr = (
            lambda **_kwargs: (captures.append(True) and None) or (frame, (0, 0))
        )

        self.assertFalse(bot._try_research_visual_fallback({"id": "research"}))
        self.assertEqual(captures, [True])

    def test_active_tree_countdown_finishes_research_without_scanning_nodes(self):
        tree = np.full((720, 1280, 3), (90, 110, 120), dtype=np.uint8)
        tree[90:650, 120:1160] = (35, 38, 42)
        tree[100:610, 35:110] = (30, 33, 36)
        cv2.rectangle(tree, (430, 85), (790, 102), (5, 5, 5), thickness=-1)
        cv2.rectangle(tree, (432, 87), (485, 100), (35, 180, 235), thickness=-1)
        cv2.rectangle(tree, (800, 70), (944, 110), (35, 180, 235), thickness=-1)
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_completed_steps = {"lab"}
        bot.routine_current_had_action = False
        bot.routine_last_action_time = 0.0
        bot.routine_idle_confirmation_count = 2
        bot.routine_action_completes_task = False
        bot._capture_screen_bgr = lambda **_kwargs: (tree, (0, 0))
        bot.set_status_message = lambda *_args, **_kwargs: None
        finished = []
        bot._finish_current_routine = lambda *args, **kwargs: finished.append(
            (args, kwargs)
        )

        self.assertTrue(bot._try_research_visual_fallback({"id": "research"}))
        self.assertEqual(bot.routine_completed_steps, {"lab", "confirm"})
        self.assertTrue(bot.routine_action_completes_task)
        self.assertEqual(len(finished), 1)

    def test_full_research_node_returns_to_tree_before_next_row(self):
        initial = np.zeros((720, 1280, 3), dtype=np.uint8)
        recentered = initial.copy()
        recentered[0, 0, 0] = 1
        full_detail = initial.copy()
        full_detail[0, 0, 0] = 2
        restored = initial.copy()
        restored[0, 0, 0] = 3
        bot = self.make_action_bot(iter((recentered, full_detail, restored)))

        def candidates(frame):
            marker = int(frame[0, 0, 0])
            return {
                0: [(900, 300)],
                1: [(700, 300)],
                2: [],
                3: [(880, 440)],
            }[marker]

        bot._research_tree_candidates = candidates
        found, returned_frame = bot._try_research_tree_row(
            initial,
            300,
            bot.get_display_profile(),
            "economy",
            0,
        )

        self.assertFalse(found)
        self.assertEqual(bot.adb_client.taps, [(900, 300), (700, 300)])
        self.assertEqual(bot.adb_client.keyevents, [4])
        self.assertEqual(int(returned_frame[0, 0, 0]), 3)

    def test_detail_card_circle_is_not_treated_as_research_tree_node(self):
        bot = AutoClicker.__new__(AutoClicker)
        frame = np.full((720, 1280, 3), (20, 120, 220), dtype=np.uint8)
        circles = np.array([[[334.0, 296.0, 44.0], [661.0, 370.0, 44.0]]])

        with (
            patch("buzzbot_app.research_tree_is_visible", return_value=True),
            patch("buzzbot_app.cv2.HoughCircles", return_value=circles),
        ):
            candidates = bot._research_tree_candidates(frame)

        self.assertEqual(candidates, [(661, 370)])

    def test_any_research_setting_checks_second_branch(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot._current_task_settings = lambda: {"branch": "any"}
        bot.get_display_profile = lambda: SimpleNamespace(
            width=1280,
            height=720,
            scale_x=1.0,
            scale_y=1.0,
        )
        bot.set_status_message = lambda *_args, **_kwargs: None
        checked = []
        bot._scan_research_branch = (
            lambda branch, _display: checked.append(branch) or branch == "war"
        )

        self.assertEqual(bot._select_available_research(), "war")
        self.assertEqual(checked, ["economy", "war"])

    def test_unconfirmed_branch_switch_is_not_scanned_under_wrong_name(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        bot = self.make_action_bot(iter((frame, frame, frame, frame)))

        with patch("buzzbot_app.research_branch_is_selected", return_value=False):
            result = bot._reset_research_branch("war", bot.get_display_profile())

        self.assertIsNone(result)
        self.assertEqual(bot.adb_client.taps, [(70, 300), (70, 300)])
        self.assertEqual(bot.adb_client.swipes, [])

    def test_tree_scan_does_not_require_language_specific_header_template(self):
        bot = AutoClicker.__new__(AutoClicker)
        tree = np.full((720, 1280, 3), (90, 110, 120), dtype=np.uint8)
        tree[90:650, 120:1160] = (35, 38, 42)
        tree[100:610, 35:110] = (30, 33, 36)
        bot.routine_completed_steps = {"lab"}
        bot._capture_screen_bgr = lambda **_kwargs: (tree, (0, 0))
        bot._select_available_research = lambda: "war"
        bot.routine_current_had_action = False
        bot.routine_last_action_time = 0.0
        bot.routine_idle_confirmation_count = 2
        bot.set_status_message = lambda *_args, **_kwargs: None
        saved = []
        bot.save_config = lambda: saved.append(True)

        self.assertTrue(bot._try_research_visual_fallback({"id": "research"}))
        self.assertEqual(bot.routine_completed_steps, {"lab", "select"})
        self.assertTrue(bot.routine_current_had_action)
        self.assertEqual(saved, [True])


if __name__ == "__main__":
    unittest.main()
