import unittest
from types import SimpleNamespace

import numpy as np
from unittest.mock import patch

from buzzbot_app import AutoClicker


class RadarAutomationTests(unittest.TestCase):
    def test_start_routines_resets_only_selected_radar_deadlines(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_tasks = [
            {
                "id": "radar_rewards",
                "group": "Радар - награды",
                "enabled": True,
            },
            {
                "id": "radar_quick",
                "group": "Радар - быстрые задания",
                "enabled": True,
            },
            {
                "id": "radar_marches",
                "group": "Радар - задания с отрядом",
                "enabled": True,
            },
            {
                "id": "vip_rewards",
                "group": "VIP",
                "enabled": True,
            },
        ]
        bot.groups = {}
        bot.routine_next_run = {
            "radar_rewards": 1000.0,
            "radar_quick": 2000.0,
            "radar_marches": 3000.0,
            "vip_rewards": 4000.0,
        }
        bot.get_routine_templates = lambda _task, active_only=True: [object()]
        bot.get_current_account = lambda: None
        bot.start = lambda: True

        self.assertTrue(bot.start_routines())
        self.assertEqual(bot.routine_next_run["radar_rewards"], 0.0)
        self.assertEqual(bot.routine_next_run["radar_quick"], 0.0)
        self.assertEqual(bot.routine_next_run["radar_marches"], 0.0)
        self.assertEqual(bot.routine_next_run["vip_rewards"], 4000.0)

    def test_completed_radar_pass_aligns_the_next_cycle(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_tasks = [
            {"id": "radar_rewards", "enabled": True},
            {"id": "radar_quick", "enabled": True},
            {"id": "radar_marches", "enabled": True},
            {"id": "vip_rewards", "enabled": True},
        ]
        bot.routine_next_run = {
            "radar_rewards": 400.0,
            "radar_quick": 500.0,
            "radar_marches": 1000.0,
            "vip_rewards": 700.0,
        }

        bot._synchronize_radar_cycle_deadlines(now=100.0)

        self.assertEqual(bot.routine_next_run["radar_rewards"], 400.0)
        self.assertEqual(bot.routine_next_run["radar_quick"], 400.0)
        self.assertEqual(bot.routine_next_run["radar_marches"], 400.0)
        self.assertEqual(bot.routine_next_run["vip_rewards"], 700.0)

    def test_active_radar_pass_keeps_due_categories_unchanged(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_tasks = [
            {"id": "radar_rewards", "enabled": True},
            {"id": "radar_quick", "enabled": True},
            {"id": "radar_marches", "enabled": True},
        ]
        bot.routine_next_run = {
            "radar_rewards": 400.0,
            "radar_quick": 50.0,
            "radar_marches": 50.0,
        }

        bot._synchronize_radar_cycle_deadlines(now=100.0)

        self.assertEqual(bot.routine_next_run["radar_rewards"], 400.0)
        self.assertEqual(bot.routine_next_run["radar_quick"], 50.0)
        self.assertEqual(bot.routine_next_run["radar_marches"], 50.0)

    def test_radar_checkbox_opens_radar_from_settlement(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_completed_steps = set()
        bot._capture_screen_bgr = lambda force=False: (
            np.zeros((720, 1280, 3), dtype=np.uint8),
            (0, 0),
        )
        bot._template_uid_is_visible = lambda _uid: False
        bot._is_settlement_screen_visible = lambda: True
        bot._is_main_screen_visible = lambda: True
        calls = []

        def tap_radar(target, label, runtime_step, marker=False):
            calls.append((target, label, runtime_step, marker))
            return True

        bot._tap_radar_fallback = tap_radar
        task = {
            "id": "radar_quick",
            "settings": {"visual_fallback": True},
        }

        self.assertTrue(bot._try_radar_visual_fallback(task))
        self.assertEqual(calls[0][0], (110, 448))
        self.assertEqual(calls[0][2], "radar_open")
        self.assertFalse(calls[0][3])

    def test_radar_does_not_reopen_from_false_settlement_match(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_completed_steps = set()
        bot._capture_screen_bgr = lambda force=False: (
            np.zeros((720, 1280, 3), dtype=np.uint8),
            (0, 0),
        )
        bot._template_uid_is_visible = lambda _uid: False
        bot._is_settlement_screen_visible = lambda: True
        bot._is_main_screen_visible = lambda: False
        calls = []
        bot._tap_radar_fallback = (
            lambda *args, **kwargs: calls.append((args, kwargs)) or True
        )
        task = {
            "id": "radar_rewards",
            "settings": {"visual_fallback": True},
        }

        self.assertFalse(bot._try_radar_visual_fallback(task))
        self.assertEqual(calls, [])

    def test_radar_does_not_press_card_button_before_selecting_marker(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_completed_steps = {"radar_open"}
        bot._capture_screen_bgr = lambda force=False: (
            np.zeros((720, 1280, 3), dtype=np.uint8),
            (0, 0),
        )
        bot._template_uid_is_visible = lambda _uid: True
        bot._is_settlement_screen_visible = lambda: False
        calls = []
        bot._tap_radar_fallback = (
            lambda target, label, runtime_step, marker=False:
            calls.append((target, runtime_step, marker)) or True
        )
        task = {
            "id": "radar_quick",
            "settings": {"visual_fallback": True},
        }

        with patch(
            "buzzbot_app.detect_radar_deployment_prompt_target",
            return_value=None,
        ), patch(
            "buzzbot_app.detect_radar_card_action_target",
            return_value=(244, 621),
        ), patch(
            "buzzbot_app.detect_radar_notification_targets",
            return_value=[],
        ):
            self.assertFalse(bot._try_radar_visual_fallback(task))

        self.assertEqual(calls, [])

    def test_radar_cancels_pass_purchase_and_defers_all_radar_modes(self):
        bot = AutoClicker.__new__(AutoClicker)
        taps = []
        finishes = []
        statuses = []
        bot.input_backend = "adb"
        bot.adb_client = SimpleNamespace(tap=lambda *target: taps.append(target))
        bot._capture_screen_bgr = lambda force=False: (
            np.zeros((720, 1280, 3), dtype=np.uint8),
            (0, 0),
        )
        bot._invalidate_capture = lambda: None
        bot._interruptible_sleep = lambda _seconds: None
        bot.routine_completed_steps = {"radar_open"}
        bot.routine_radar_in_progress_seen = True
        bot.routine_tasks = [
            {"id": "radar_rewards", "enabled": True},
            {"id": "radar_quick", "enabled": True},
            {"id": "radar_marches", "enabled": True},
            {"id": "vip_rewards", "enabled": True},
        ]
        bot.routine_next_run = {
            "radar_rewards": 0.0,
            "radar_quick": 0.0,
            "radar_marches": 0.0,
            "vip_rewards": 900.0,
        }
        bot._finish_current_routine = lambda now=None: finishes.append(now)
        bot.save_config = lambda: None
        bot.set_status_message = lambda message, **_kwargs: statuses.append(message)
        task = {
            "id": "radar_quick",
            "enabled": True,
            "interval_minutes": 720.0,
            "settings": {"visual_fallback": True},
        }

        with patch(
            "buzzbot_app.detect_radar_pass_purchase_cancel_target",
            return_value=(496, 508),
        ), patch("buzzbot_app.time.time", return_value=100.0):
            self.assertTrue(bot._try_radar_visual_fallback(task))

        self.assertEqual(taps, [(496, 508)])
        self.assertEqual(finishes, [100.0])
        self.assertEqual(bot.routine_next_run["radar_rewards"], 43300.0)
        self.assertEqual(bot.routine_next_run["radar_quick"], 43300.0)
        self.assertEqual(bot.routine_next_run["radar_marches"], 43300.0)
        self.assertEqual(bot.routine_next_run["vip_rewards"], 900.0)
        self.assertIn("покупка пропуска отменена", statuses[-1])

    def test_radar_does_not_treat_an_unrelated_dialog_as_pass_purchase(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_completed_steps = set()
        bot._capture_screen_bgr = lambda force=False: (
            np.zeros((720, 1280, 3), dtype=np.uint8),
            (0, 0),
        )
        bot._template_uid_is_visible = lambda _uid: False
        bot._is_settlement_screen_visible = lambda: False
        bot._tap_radar_fallback = lambda *_args, **_kwargs: False
        task = {
            "id": "radar_marches",
            "settings": {"visual_fallback": True},
        }

        with patch(
            "buzzbot_app.detect_radar_pass_purchase_cancel_target",
            return_value=(496, 508),
        ) as detector, patch(
            "buzzbot_app.detect_radar_deployment_prompt_target",
            return_value=None,
        ), patch(
            "buzzbot_app.detect_radar_card_action_target",
            return_value=None,
        ):
            self.assertFalse(bot._try_radar_visual_fallback(task))

        detector.assert_not_called()

    def test_rewards_mode_returns_home_instead_of_deploying_squad(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_completed_steps = {
            "radar_open",
            "radar_marker",
            "radar_forward",
            "radar_action",
        }
        bot.routine_radar_pending_marker_key = ("radar_dynamic", 640, 360)
        bot.routine_radar_confirmed_marker_keys = set()
        bot.routine_radar_in_progress_seen = False
        bot.routine_idle_confirmation_count = 3
        bot.routine_current_had_action = False
        bot.routine_last_action_time = 0.0
        bot.anti_loop_enabled = True
        bot.blocked_coords = {}
        bot._capture_screen_bgr = lambda force=False: (
            np.zeros((720, 1280, 3), dtype=np.uint8),
            (0, 0),
        )
        bot._template_uid_is_visible = lambda _uid: False
        bot.set_status_message = lambda *_args, **_kwargs: None
        returned = []
        bot._return_to_main_screen = lambda **kwargs: returned.append(kwargs) or True

        task = {
            "id": "radar_rewards",
            "settings": {"visual_fallback": True},
        }
        with patch(
            "buzzbot_app.detect_radar_deployment_prompt_target",
            return_value=(970, 210),
        ):
            self.assertTrue(bot._try_radar_visual_fallback(task))

        self.assertEqual(bot.routine_completed_steps, set())
        self.assertTrue(bot.routine_current_had_action)
        self.assertEqual(returned[0]["require_settlement"], True)
        self.assertIn(("radar_dynamic", 640, 360), bot.routine_radar_confirmed_marker_keys)

    def test_marches_mode_creates_squad_from_deployment_prompt(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_completed_steps = {"radar_open", "radar_forward"}
        bot._capture_screen_bgr = lambda force=False: (
            np.zeros((720, 1280, 3), dtype=np.uint8),
            (0, 0),
        )
        bot._template_uid_is_visible = lambda _uid: False
        calls = []
        bot._tap_radar_fallback = (
            lambda target, label, runtime_step, marker=False:
            calls.append((target, runtime_step, marker)) or True
        )
        task = {
            "id": "radar_marches",
            "settings": {"visual_fallback": True},
        }

        with patch(
            "buzzbot_app.detect_radar_deployment_prompt_target",
            return_value=(970, 210),
        ):
            self.assertTrue(bot._try_radar_visual_fallback(task))

        self.assertIn("radar_action", bot.routine_completed_steps)
        self.assertEqual(calls, [((970, 210), "radar_squad", False)])

    def test_rewards_mode_defers_unfinished_card_without_pressing_forward(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_completed_steps = {"radar_open", "radar_marker"}
        marker_key = ("reward-marker", 765, 197)
        bot.routine_radar_pending_marker_key = marker_key
        bot.routine_radar_confirmed_marker_keys = set()
        bot.routine_radar_in_progress_seen = False
        bot.routine_idle_confirmation_count = 2
        bot.routine_current_had_action = False
        bot.routine_last_action_time = 0.0
        bot.anti_loop_enabled = True
        bot.blocked_coords = {}
        bot.input_backend = "adb"
        keyevents = []
        bot.adb_client = SimpleNamespace(keyevent=keyevents.append)
        bot._capture_screen_bgr = lambda force=False: (
            np.zeros((720, 1280, 3), dtype=np.uint8),
            (0, 0),
        )
        bot._template_uid_is_visible = lambda _uid: True
        bot._invalidate_capture = lambda: None
        bot._interruptible_sleep = lambda _seconds: None
        bot.set_status_message = lambda *_args, **_kwargs: None
        task = {
            "id": "radar_rewards",
            "settings": {"visual_fallback": True},
        }

        with patch(
            "buzzbot_app.detect_radar_deployment_prompt_target",
            return_value=None,
        ), patch(
            "buzzbot_app.detect_radar_card_action_target",
            return_value=(244, 621),
        ):
            self.assertTrue(bot._try_radar_visual_fallback(task))

        self.assertEqual(keyevents, [4])
        self.assertEqual(bot.routine_completed_steps, set())
        self.assertIn(marker_key, bot.routine_radar_confirmed_marker_keys)
        self.assertIsNone(bot.routine_radar_pending_marker_key)

    def test_radar_idle_recovery_forgets_the_stale_card(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_idle_recovery_attempted = False
        bot.routine_completed_steps = {
            "radar_open",
            "radar_category",
            "radar_marker",
            "radar_forward",
        }
        bot.routine_radar_pending_marker_key = ("marker", 640, 360)
        bot.routine_radar_marker_failure_counts = {}
        bot.routine_idle_guard_visible = False
        bot.routine_idle_outside_since = 20.0
        bot.routine_last_action_time = 0.0
        bot.blocked_coords = {("marker", 640, 360): 999.0}
        bot.set_status_message = lambda *_args, **_kwargs: None
        bot.get_routine_task_name = lambda _task: "Радар"
        bot._return_to_main_screen = lambda **_kwargs: True

        self.assertTrue(
            bot._try_recover_current_routine_idle_screen({"id": "radar_quick"})
        )
        self.assertEqual(bot.routine_completed_steps, set())
        self.assertIsNone(bot.routine_radar_pending_marker_key)
        self.assertEqual(bot.routine_radar_marker_failure_counts[(20, 11)], 1)
        self.assertEqual(bot.blocked_coords, {})

    def test_radar_idle_recovery_defers_a_marker_after_two_failed_attempts(self):
        bot = AutoClicker.__new__(AutoClicker)
        marker_key = ("marker", 640, 360)
        bot.routine_idle_recovery_attempted = False
        bot.routine_completed_steps = {"radar_open", "radar_marker", "radar_forward"}
        bot.routine_radar_pending_marker_key = marker_key
        bot.routine_radar_confirmed_marker_keys = set()
        bot.routine_radar_marker_failure_counts = {(20, 11): 1}
        bot.routine_idle_guard_visible = False
        bot.routine_idle_outside_since = 20.0
        bot.routine_last_action_time = 0.0
        bot.blocked_coords = {marker_key: 999.0}
        bot.anti_loop_enabled = True
        bot.set_status_message = lambda *_args, **_kwargs: None
        bot.get_routine_task_name = lambda _task: "Радар"
        bot._return_to_main_screen = lambda **_kwargs: True

        self.assertTrue(
            bot._try_recover_current_routine_idle_screen({"id": "radar_marches"})
        )

        self.assertIsNone(bot.routine_radar_pending_marker_key)
        self.assertIn(marker_key, bot.routine_radar_confirmed_marker_keys)
        self.assertIn(("*", 640, 360), bot.routine_radar_confirmed_marker_keys)
        self.assertNotIn((20, 11), bot.routine_radar_marker_failure_counts)
        self.assertEqual(bot.blocked_coords, {})

    def test_rejected_radar_marker_does_not_block_idle_completion(self):
        bot = AutoClicker.__new__(AutoClicker)
        guard = {"uid": "guard"}
        blocker = {
            "uid": "marker",
            "group": "Radar",
            "description": "False radar marker",
            "prevents_idle_completion": True,
        }
        bot.input_backend = "pyautogui"
        bot.search_images = [guard, blocker]
        bot.routine_idle_confirmation_count = 0
        bot.routine_idle_guard_visible = False
        bot.routine_radar_confirmed_marker_keys = set()
        bot._is_active = lambda _image: True
        bot._locate_image = lambda image: (
            SimpleNamespace(x=640, y=360),
            (620, 340, 40, 40),
            0.8,
        )
        bot._validate_detected_match = lambda _image, _bbox: (False, "color")

        task = {
            "id": "radar_rewards",
            "group": "Radar",
            "complete_when_idle": True,
            "idle_completion_guard_uid": "guard",
            "idle_confirmations": 1,
        }

        self.assertTrue(bot._routine_idle_completion_ready(task))
        self.assertTrue(bot.routine_idle_guard_visible)

    def test_return_shelter_rearms_idle_screen_recovery_for_next_card(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.player_width = 1280
        bot.player_height = 720
        bot.adb_client = SimpleNamespace(tap=lambda *_args: None)
        bot.routine_completed_steps = {"radar_action", "radar_march"}
        bot.routine_radar_pending_marker_key = None
        bot.routine_radar_confirmed_marker_keys = set()
        bot.routine_idle_outside_since = 25.0
        bot.routine_idle_recovery_attempted = True
        bot.routine_last_action_time = 0.0
        bot.routine_current_had_action = True
        bot.routine_idle_confirmation_count = 0
        bot.blocked_coords = {}
        bot.anti_loop_enabled = True
        bot._invalidate_capture = lambda: None
        bot._interruptible_sleep = lambda _seconds: None
        bot.set_status_message = lambda *_args, **_kwargs: None
        image = {
            "action": "radar_return_shelter",
            "last_used": 0.0,
            "delay": 0.0,
        }

        self.assertTrue(bot._execute_action(image, SimpleNamespace(x=100, y=100)))
        self.assertFalse(bot.routine_idle_recovery_attempted)
        self.assertEqual(bot.routine_idle_outside_since, 0.0)

    def test_opening_radar_rearms_idle_screen_recovery(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.player_width = 1280
        bot.player_height = 720
        bot.adb_client = SimpleNamespace(tap=lambda *_args: None)
        bot.current_routine_task_id = "radar_marches"
        bot.routine_idle_outside_since = 25.0
        bot.routine_idle_recovery_attempted = True
        bot.routine_action_failure_reason = ""
        bot.cycle_mode = False
        bot.sleep_found = 0.0
        bot._invalidate_capture = lambda: None
        bot.set_status_message = lambda *_args, **_kwargs: None
        image = {
            "action": "click",
            "description": "Открыть радарную станцию",
            "requires_settlement_screen": True,
            "last_used": 0.0,
            "delay": 0.0,
        }

        self.assertTrue(bot._execute_action(image, SimpleNamespace(x=110, y=448)))
        self.assertFalse(bot.routine_idle_recovery_attempted)
        self.assertEqual(bot.routine_idle_outside_since, 0.0)


if __name__ == "__main__":
    unittest.main()
