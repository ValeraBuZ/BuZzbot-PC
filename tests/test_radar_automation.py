import unittest
from types import SimpleNamespace
import uuid

import numpy as np
from unittest.mock import patch

from buzzbot_app import AutoClicker, FENCE_SURVIVOR_SCAN_PATTERN
from buzzbot.routines import PROFILE_NAMESPACE


class RadarAutomationTests(unittest.TestCase):
    def test_radar_template_matching_can_skip_a_confirmed_occurrence(self):
        bot = AutoClicker.__new__(AutoClicker)
        rng = np.random.default_rng(42)
        template = rng.integers(0, 255, size=(10, 10), dtype=np.uint8)
        screen_gray = np.zeros((60, 120), dtype=np.uint8)
        screen_gray[20:30, 10:20] = template
        screen_gray[20:30, 80:90] = template
        screen_bgr = np.repeat(screen_gray[:, :, None], 3, axis=2)
        bot._capture_screen_bgr = lambda region=None: (screen_bgr, (0, 0))
        bot.template_cache = SimpleNamespace(
            get_gray=lambda _path: template,
            get_color=lambda _path: None,
        )

        first, _bbox, _confidence = bot._find_template_opencv(
            "marker.png", None, 0.8, True, [1.0]
        )
        second, _bbox, _confidence = bot._find_template_opencv(
            "marker.png", None, 0.8, True, [1.0], excluded_centers=[(15, 25)]
        )

        self.assertEqual((first.x, first.y), (15, 25))
        self.assertEqual((second.x, second.y), (85, 25))

    def test_fence_survivors_scans_before_confirming_no_rewards(self):
        bot = AutoClicker.__new__(AutoClicker)
        swipes = []
        finished = []
        bot.routine_fence_survivor_scan_index = 0
        bot.input_backend = "adb"
        bot.adb_client = SimpleNamespace(
            swipe=lambda *args: swipes.append(args)
        )
        bot._is_settlement_screen_visible = lambda: True
        bot._capture_screen_bgr = lambda **_kwargs: (
            np.zeros((720, 1280, 3), dtype=np.uint8),
            (0, 0),
        )
        bot._invalidate_capture = lambda: None
        bot._interruptible_sleep = lambda _seconds: None
        bot.set_status_message = lambda *_args, **_kwargs: None
        bot._finish_current_routine = lambda now: finished.append(now)
        bot.routine_current_had_action = False
        bot.routine_last_action_time = 0.0
        bot.routine_idle_confirmation_count = 2
        bot.click_count = 0
        task = {"id": "fence_survivors"}

        for _step in FENCE_SURVIVOR_SCAN_PATTERN:
            self.assertTrue(bot._try_fence_survivors_visual_fallback(task))
        self.assertEqual(len(swipes), len(FENCE_SURVIVOR_SCAN_PATTERN))
        self.assertEqual(finished, [])

        self.assertTrue(bot._try_fence_survivors_visual_fallback(task))
        self.assertEqual(len(finished), 1)

    def test_merchant_templates_never_include_gem_offers_in_safe_mode(self):
        bot = AutoClicker.__new__(AutoClicker)
        task = {
            "id": "mysterious_merchant",
            "group": "Таинственный торговец",
            "settings": {
                "buy_free": True,
                "buy_resources": True,
                "avoid_gems": True,
            },
        }
        bot.groups = {"Таинственный торговец": True}
        bot.search_images = [
            {"uid": "open", "group": "Таинственный торговец", "enabled": True},
            {
                "uid": "free",
                "group": "Таинственный торговец",
                "merchant_currency": "free",
                "enabled": True,
            },
            {
                "uid": "resources",
                "group": "Таинственный торговец",
                "merchant_currency": "resources",
                "enabled": True,
            },
            {
                "uid": "gems",
                "group": "Таинственный торговец",
                "merchant_currency": "gems",
                "enabled": True,
            },
        ]

        allowed = bot.get_routine_templates(task, active_only=True)

        self.assertEqual([image["uid"] for image in allowed], ["open", "free", "resources"])

    def test_missing_merchant_is_deferred_without_blocking_next_saved_task(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.current_routine_task_id = None
        bot.account_rotation_enabled = False
        bot.routine_only_task_id = None
        bot.routine_forced_task_queue = []
        bot.routine_forced_task_active_id = None
        bot.routine_forced_task_return_index = None
        bot.routine_radar_return_hold = False
        bot.routine_deployment_blocked_until = 0.0
        bot.routine_max_marches = 5
        bot.current_routine_index = 0
        bot.routine_next_run = {}
        bot.routine_tasks = [
            {
                "id": "mysterious_merchant",
                "name": "Покупка у Таинственного торговца",
                "group": "merchant",
                "enabled": True,
                "uses_march": False,
                "settings": {"arrival_retry_minutes": 60},
            },
            {
                "id": "alliance_help",
                "name": "Помощь",
                "group": "help",
                "enabled": True,
                "uses_march": False,
            },
        ]
        bot.groups = {"merchant": True, "help": True}
        bot.search_images = [{"group": "help", "enabled": True}]
        bot.get_active_marches = lambda _now: 0
        bot._release_radar_return_hold = lambda *_args: False
        bot._try_return_camped_zombie_march = lambda *_args: False
        bot.set_status_message = lambda *_args, **_kwargs: None
        bot.save_config = lambda: None

        result = bot._begin_due_routine(100.0)

        self.assertIsNone(result)
        self.assertEqual(bot.current_routine_index, 1)
        self.assertEqual(bot.routine_next_run["mysterious_merchant"], 3700.0)
        self.assertEqual(bot.routine_last_outcome["reason"], "merchant_not_arrived")

    def _game_login_recovery_bot(self, *, last_action_time):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = SimpleNamespace(
            ui_xml=lambda: '<node content-desc="Game view" />'
        )
        bot.search_images = []
        bot.routine_task_started_at = 0.0
        bot.routine_last_action_time = last_action_time
        bot.routine_home_recovery_attempted = True
        bot._capture_screen_bgr = lambda **_kwargs: (
            np.zeros((720, 1280, 3), dtype=np.uint8),
            (0, 0),
        )
        bot._is_main_screen_visible = lambda: False
        bot._is_settlement_screen_visible = lambda: False
        bot.set_status_message = lambda *_args, **_kwargs: None
        return bot

    @patch(
        "buzzbot_app.detect_game_event_overlay_close_target",
        return_value=(1051, 109),
    )
    def test_game_login_does_not_click_false_event_target_on_main_screen(
        self,
        overlay_detector,
    ):
        bot = self._game_login_recovery_bot(last_action_time=90.0)
        bot._is_main_screen_visible = lambda: True
        bot._is_settlement_screen_visible = lambda: False
        taps = []
        bot._tap_routine_fallback = (
            lambda *args, **kwargs: taps.append((args, kwargs)) or True
        )

        acted = bot._try_game_login_visual_fallback({"id": "game_login"})

        self.assertFalse(acted)
        self.assertEqual(taps, [])
        overlay_detector.assert_not_called()

    @patch(
        "buzzbot_app.detect_game_event_overlay_close_target",
        return_value=(1051, 109),
    )
    def test_game_login_does_not_click_false_event_target_in_settlement(
        self,
        overlay_detector,
    ):
        bot = self._game_login_recovery_bot(last_action_time=90.0)
        bot._is_settlement_screen_visible = lambda: True
        taps = []
        bot._tap_routine_fallback = (
            lambda *args, **kwargs: taps.append((args, kwargs)) or True
        )

        acted = bot._try_game_login_visual_fallback({"id": "game_login"})

        self.assertFalse(acted)
        self.assertEqual(taps, [])
        overlay_detector.assert_not_called()

    @patch("buzzbot_app.time.time", return_value=100.0)
    def test_game_login_retries_home_recovery_after_another_inner_screen(self, _time):
        bot = self._game_login_recovery_bot(last_action_time=70.0)
        recoveries = []
        bot._return_to_main_screen = lambda **kwargs: recoveries.append(kwargs) or True

        acted = bot._try_game_login_visual_fallback({"id": "game_login"})

        self.assertTrue(acted)
        self.assertEqual(recoveries, [{"max_back_steps": 5}])
        self.assertEqual(bot.routine_last_action_time, 100.0)

    @patch("buzzbot_app.time.time", return_value=100.0)
    def test_game_login_throttles_repeated_home_recovery(self, _time):
        bot = self._game_login_recovery_bot(last_action_time=90.0)
        recoveries = []
        bot._return_to_main_screen = lambda **kwargs: recoveries.append(kwargs) or True

        acted = bot._try_game_login_visual_fallback({"id": "game_login"})

        self.assertFalse(acted)
        self.assertEqual(recoveries, [])

    def test_scheduler_checks_radar_marches_even_when_world_marches_are_full(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_only_task_id = None
        bot.account_switch_task = None
        bot.routine_tasks = [
            {
                "id": "radar_marches",
                "group": "Радар - задания с отрядом",
                "enabled": True,
                "uses_march": True,
            }
        ]
        bot.groups = {"Радар - задания с отрядом": True}
        bot.search_images = [
            {"group": "Радар - задания с отрядом", "enabled": True}
        ]

        runtime_task = bot._scheduler_routine_tasks()[0]

        self.assertTrue(runtime_task["enabled"])
        self.assertFalse(runtime_task["uses_march"])

    def test_radar_followups_stay_due_without_overtaking_saved_order(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_tasks = [
            {"id": "radar_marches", "group": "marches", "enabled": True},
            {"id": "radar_rewards", "group": "rewards", "enabled": True},
            {"id": "research", "group": "research", "enabled": True},
            {"id": "completed_tasks", "group": "completed", "enabled": True},
        ]
        bot.groups = {
            "rewards": True,
            "marches": True,
            "completed": True,
            "research": True,
        }
        bot.routine_next_run = {}
        bot.routine_only_task_id = None
        bot.current_routine_index = 0
        bot.routine_forced_task_queue = []
        bot.routine_forced_task_active_id = None
        bot.routine_forced_task_return_index = None

        bot._advance_routine_after_outcome(bot.routine_tasks[0], 100.0)

        self.assertEqual(bot.routine_forced_task_queue, [])
        self.assertEqual(bot.current_routine_index, 1)
        self.assertIsNone(bot.routine_forced_task_return_index)
        self.assertEqual(bot.routine_next_run["radar_rewards"], 100.0)
        self.assertEqual(bot.routine_next_run["completed_tasks"], 100.0)

        bot._advance_routine_after_outcome(bot.routine_tasks[1], 101.0)
        self.assertEqual(bot.current_routine_index, 2)

    def test_active_or_returning_radar_march_holds_the_task_order(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_tasks = [
            {"id": "radar_marches", "group": "marches", "enabled": True},
            {"id": "gathering_boost", "group": "gathering", "enabled": True},
        ]
        bot.groups = {"marches": True, "gathering": True}
        bot.routine_next_run = {"radar_marches": 400.0}
        bot.routine_only_task_id = None
        bot.current_routine_index = 0
        bot.routine_radar_in_progress_seen = True
        bot.routine_forced_task_queue = []
        bot.routine_forced_task_active_id = None
        bot.routine_forced_task_return_index = None
        bot.routine_radar_return_hold = False

        bot._advance_routine_after_outcome(bot.routine_tasks[0], 100.0)

        self.assertEqual(bot.current_routine_index, 0)
        self.assertEqual(bot.routine_forced_task_queue, [])
        self.assertTrue(bot.routine_radar_return_hold)

    def test_radar_return_hold_waits_for_the_guarded_retry_interval(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_tasks = [
            {"id": "radar_marches", "group": "marches", "enabled": True},
            {"id": "radar_rewards", "group": "rewards", "enabled": True},
        ]
        bot.routine_next_run = {"radar_marches": 400.0}
        bot.routine_radar_return_hold = True

        self.assertFalse(bot._release_radar_return_hold(active_marches=0, now=150.0))

        self.assertTrue(bot.routine_radar_return_hold)
        self.assertEqual(bot.routine_next_run["radar_marches"], 400.0)

        self.assertTrue(bot._release_radar_return_hold(active_marches=0, now=400.0))

        self.assertFalse(bot.routine_radar_return_hold)
        self.assertEqual(bot.routine_next_run["radar_marches"], 400.0)

    def test_ordinary_active_march_does_not_extend_elapsed_radar_hold(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_tasks = [
            {"id": "radar_marches", "group": "marches", "enabled": True},
        ]
        bot.routine_next_run = {"radar_marches": 400.0}
        bot.routine_radar_return_hold = True

        self.assertTrue(bot._release_radar_return_hold(active_marches=1, now=450.0))

        self.assertFalse(bot.routine_radar_return_hold)
        self.assertEqual(bot.routine_next_run["radar_marches"], 450.0)

    def test_confirmed_zero_marches_releases_radar_before_fallback_interval(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_tasks = [
            {"id": "radar_marches", "group": "marches", "enabled": True},
        ]
        bot.routine_next_run = {"radar_marches": 400.0}
        bot.routine_radar_return_hold = True
        bot.routine_radar_return_active_seen = True

        self.assertTrue(bot._release_radar_return_hold(active_marches=0, now=200.0))

        self.assertFalse(bot.routine_radar_return_hold)
        self.assertFalse(bot.routine_radar_return_active_seen)
        self.assertEqual(bot.routine_next_run["radar_marches"], 200.0)

    def test_confirmed_counter_decrease_finishes_single_radar_dispatch(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_tasks = [
            {
                "id": "radar_marches",
                "group": "marches",
                "enabled": True,
                "settings": {"fixed_utc_hours": [0, 12]},
            },
            {"id": "radar_rewards", "group": "rewards", "enabled": True},
            {"id": "completed_tasks", "group": "completed", "enabled": True},
        ]
        bot.groups = {"marches": True, "rewards": True, "completed": True}
        bot.routine_next_run = {"radar_marches": 400.0}
        bot.routine_radar_return_hold = True
        bot.routine_radar_return_active_seen = False
        bot.routine_radar_return_observed_peak = 0
        bot.routine_radar_dispatched_this_pass = True
        bot.routine_only_task_id = None
        bot.current_routine_index = 0
        bot.routine_pass_completed = False
        bot.routine_forced_task_queue = []
        bot.routine_forced_task_active_id = None
        bot.routine_forced_task_return_index = None
        saved_peaks = []
        bot.save_config = lambda: saved_peaks.append(
            bot.routine_radar_return_observed_peak
        )

        self.assertFalse(
            bot._release_radar_return_hold(active_marches=4, now=100.0)
        )
        self.assertFalse(
            bot._release_radar_return_hold(active_marches=4, now=105.0)
        )
        self.assertEqual(saved_peaks, [4])
        self.assertTrue(bot.routine_radar_return_hold)

        # The boolean observation flag is process-local.  A resumed autostart
        # must recover the proof from the persisted peak alone.
        bot.routine_radar_return_active_seen = False
        self.assertTrue(
            bot._release_radar_return_hold(active_marches=3, now=110.0)
        )

        self.assertFalse(bot.routine_radar_return_hold)
        self.assertFalse(bot.routine_radar_dispatched_this_pass)
        self.assertEqual(bot.routine_radar_return_observed_peak, 0)
        self.assertEqual(bot.current_routine_index, 1)
        self.assertEqual(bot.routine_next_run["radar_rewards"], 110.0)
        self.assertEqual(bot.routine_next_run["completed_tasks"], 110.0)
        self.assertGreater(bot.routine_next_run["radar_marches"], 110.0)

    def test_dispatched_radar_march_advances_without_opening_second_card(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_tasks = [
            {
                "id": "radar_marches",
                "group": "marches",
                "enabled": True,
                "settings": {"fixed_utc_hours": [0, 12]},
            },
            {"id": "radar_rewards", "group": "rewards", "enabled": True},
            {"id": "completed_tasks", "group": "completed", "enabled": True},
        ]
        bot.groups = {"marches": True, "rewards": True, "completed": True}
        bot.routine_next_run = {"radar_marches": 400.0}
        bot.routine_radar_return_hold = True
        bot.routine_radar_return_active_seen = True
        bot.routine_radar_dispatched_this_pass = True
        bot.routine_only_task_id = None
        bot.current_routine_index = 0
        bot.routine_pass_completed = False
        bot.routine_forced_task_queue = []
        bot.routine_forced_task_active_id = None
        bot.routine_forced_task_return_index = None
        bot.save_config = lambda: None

        self.assertTrue(bot._release_radar_return_hold(active_marches=0, now=200.0))

        self.assertFalse(bot.routine_radar_return_hold)
        self.assertFalse(bot.routine_radar_dispatched_this_pass)
        self.assertEqual(bot.current_routine_index, 1)
        self.assertEqual(bot.routine_next_run["radar_rewards"], 200.0)
        self.assertEqual(bot.routine_next_run["completed_tasks"], 200.0)
        self.assertGreater(bot.routine_next_run["radar_marches"], 200.0)

    def test_account_rotation_waits_for_the_saved_order_to_wrap(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.current_routine_index = 8
        bot.routine_pass_completed = False
        bot.current_routine_task_id = None
        bot.routine_radar_return_hold = False
        bot.routine_forced_task_queue = []

        self.assertFalse(bot._account_rotation_cycle_ready())

        bot.current_routine_index = 0
        bot.routine_radar_return_hold = True
        bot.routine_pass_completed = True
        self.assertFalse(bot._account_rotation_cycle_ready())

        bot.routine_radar_return_hold = False
        self.assertTrue(bot._account_rotation_cycle_ready())

    def test_account_rotation_starts_immediately_after_wrap_even_with_future_session_deadline(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.account_rotation_enabled = True
        bot.account_session_deadline = 999999.0
        bot.account_switch_retry_at = 0.0
        bot.routine_only_task_id = None
        bot.routine_forced_task_queue = []
        bot.current_routine_index = 0
        bot.routine_pass_completed = True
        bot.current_routine_task_id = None
        bot.routine_radar_return_hold = False

        self.assertTrue(bot._account_rotation_switch_due(100.0))

        bot.routine_pass_completed = False
        self.assertFalse(bot._account_rotation_switch_due(100.0))

        bot.routine_pass_completed = True
        bot.account_switch_retry_at = 160.0
        self.assertFalse(bot._account_rotation_switch_due(100.0))

    def test_active_gathering_boost_does_not_block_resource_queue(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_tasks = [
            {"id": "mail_rewards", "group": "mail", "enabled": False},
            {"id": "gathering_boost", "group": "boost", "enabled": True},
            {"id": "food", "group": "food", "enabled": True},
        ]
        bot.groups = {"mail": False, "boost": True, "food": True}
        bot.current_routine_index = 0
        bot.routine_only_task_id = None
        bot.routine_forced_task_queue = []
        bot.routine_radar_return_hold = False
        statuses = []
        bot.set_status_message = lambda message, **_kwargs: statuses.append(message)

        self.assertTrue(bot._skip_satisfied_gathering_boost(500.0, 100.0))

        self.assertEqual(bot.current_routine_index, 2)
        self.assertIn("продолжаю очередь ресурсов", statuses[-1])

    def test_active_gathering_boost_never_overtakes_an_enabled_prior_task(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_tasks = [
            {"id": "mail_rewards", "group": "mail", "enabled": True},
            {"id": "gathering_boost", "group": "boost", "enabled": True},
            {"id": "food", "group": "food", "enabled": True},
        ]
        bot.groups = {"mail": True, "boost": True, "food": True}
        bot.current_routine_index = 0
        bot.routine_only_task_id = None
        bot.routine_forced_task_queue = []
        bot.routine_radar_return_hold = False
        bot.set_status_message = lambda *_args, **_kwargs: None

        self.assertFalse(bot._skip_satisfied_gathering_boost(500.0, 100.0))

        self.assertEqual(bot.current_routine_index, 0)

    def test_completed_tasks_remains_due_at_its_saved_position_after_radar(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_tasks = [
            {"id": "radar_marches", "group": "marches", "enabled": True},
            {"id": "radar_rewards", "group": "rewards", "enabled": True},
            {"id": "research", "group": "research", "enabled": True},
            {"id": "completed_tasks", "group": "completed", "enabled": True},
            {"id": "mail_rewards", "group": "mail", "enabled": True},
        ]
        bot.current_routine_index = 0
        bot.routine_next_run = {"completed_tasks": 1900.0}
        bot.routine_radar_in_progress_seen = False
        bot.routine_only_task_id = None
        bot.routine_forced_task_queue = []
        bot.routine_forced_task_active_id = None
        bot.routine_forced_task_return_index = None
        bot.groups = {
            "marches": True,
            "rewards": True,
            "research": True,
            "completed": True,
            "mail": True,
        }

        bot._advance_routine_after_outcome(bot.routine_tasks[0], 100.0)

        self.assertEqual(bot.routine_next_run["completed_tasks"], 100.0)
        self.assertEqual(bot.current_routine_index, 1)
        self.assertEqual(bot.routine_forced_task_queue, [])

    def test_busy_squad_does_not_skip_the_remaining_resource_tasks(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_tasks = [
            {"id": "food", "group": "food", "enabled": True},
            {"id": "wood", "group": "wood", "enabled": True},
            {"id": "metal", "group": "metal", "enabled": True},
            {"id": "oil", "group": "oil", "enabled": True},
        ]
        bot.current_routine_index = 1
        bot.current_routine_task_id = "wood"
        bot.routine_next_run = {}
        bot.routine_deployment_blocked_until = 0.0
        bot.routine_completed_steps = {"create_squad"}
        bot.routine_current_action_count = 4
        bot.routine_current_had_action = True
        bot.routine_action_counts = {}
        bot.routine_idle_confirmation_count = 0
        bot.routine_home_recovery_attempted = False
        bot.routine_idle_guard_visible = False
        bot.routine_idle_outside_since = 0.0
        bot.routine_idle_recovery_attempted = False
        bot.routine_forced_task_queue = []
        bot.routine_forced_task_active_id = None
        bot.routine_forced_task_return_index = None
        bot.routine_only_task_id = None
        bot._return_to_main_screen = lambda **_kwargs: True
        bot.set_status_message = lambda *_args, **_kwargs: None
        bot.save_config = lambda: None

        bot._defer_current_routine_no_squad(now=100.0)

        self.assertEqual(bot.routine_deployment_blocked_until, 0.0)
        self.assertEqual(bot.current_routine_index, 2)
        self.assertEqual(bot.routine_next_run["wood"], 160.0)

    def test_busy_squad_keeps_dispatch_until_full_radar_in_place(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_tasks = [
            {
                "id": "radar_marches",
                "group": "marches",
                "enabled": True,
                "settings": {"dispatch_until_full": True},
            },
            {"id": "radar_rewards", "group": "rewards", "enabled": True},
        ]
        bot.current_routine_index = 0
        bot.current_routine_task_id = "radar_marches"
        bot.routine_next_run = {}
        bot.routine_completed_steps = {
            "radar_marker",
            "radar_forward",
            "radar_action",
            "radar_squad",
        }
        bot.routine_current_action_count = 2
        bot.routine_action_counts = {"radar_dispatches": 2}
        bot.routine_radar_pending_marker_key = ("marker", 10, 20)
        bot.routine_action_failure_reason = ""
        bot.routine_idle_confirmation_count = 0
        bot.routine_home_recovery_attempted = False
        bot.routine_idle_guard_visible = False
        bot.routine_idle_outside_since = 0.0
        bot.routine_idle_recovery_attempted = False
        bot.routine_last_action_time = 0.0
        bot.get_routine_task = lambda task_id: next(
            task for task in bot.routine_tasks if task["id"] == task_id
        )
        bot._return_to_main_screen = lambda **_kwargs: True
        bot.set_status_message = lambda *_args, **_kwargs: None
        bot.save_config = lambda: None
        completed = []
        followups = []
        bot._finish_current_routine = lambda now, **_kwargs: completed.append(now)
        bot._queue_post_radar_followups = lambda task, now: followups.append(
            (task["id"], now)
        )
        sleeps = []
        bot._interruptible_sleep = sleeps.append

        bot._defer_current_routine_no_squad(now=100.0)

        self.assertEqual(bot.current_routine_index, 0)
        self.assertEqual(bot.current_routine_task_id, "radar_marches")
        self.assertEqual(bot.routine_next_run["radar_marches"], 115.0)
        self.assertIsNone(bot.routine_radar_pending_marker_key)
        self.assertEqual(bot.routine_completed_steps, set())
        self.assertEqual(bot.routine_action_counts["radar_dispatches"], 2)
        self.assertEqual(sleeps, [15.0])
        self.assertEqual(completed, [])

        bot._defer_current_routine_no_squad(now=115.0)

        self.assertEqual(completed, [115.0])
        self.assertEqual(followups, [("radar_marches", 115.0)])
        self.assertNotIn(
            "_no_squad_confirmations",
            bot.routine_tasks[0]["settings"],
        )

    def test_full_ordinary_marches_defer_remaining_resources_and_finish_pass(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_tasks = [
            {"id": "metal", "group": "metal", "enabled": True, "uses_march": True},
            {"id": "oil", "group": "oil", "enabled": True, "uses_march": True},
        ]
        bot.groups = {"metal": True, "oil": True}
        bot.routine_next_run = {"metal": 0.0, "oil": 0.0}
        bot.current_routine_index = 0
        bot.routine_pass_completed = False
        bot.routine_max_marches = 5
        bot.routine_only_task_id = None
        bot.routine_forced_task_queue = []
        bot.routine_forced_task_active_id = None
        bot.routine_forced_task_return_index = None
        bot.routine_radar_return_hold = False
        bot.routine_radar_in_progress_seen = False
        bot.get_routine_task = lambda task_id: next(
            task for task in bot.routine_tasks if task["id"] == task_id
        )
        bot.get_routine_task_name = lambda task: task["id"]
        statuses = []
        bot.set_status_message = lambda message, **_kwargs: statuses.append(message)
        bot.save_config = lambda: None

        self.assertTrue(
            bot._defer_due_ordinary_marches_when_full(
                bot.routine_tasks,
                now=100.0,
                active_marches=5,
            )
        )

        self.assertEqual(bot.routine_next_run, {"metal": 160.0, "oil": 160.0})
        self.assertEqual(bot.current_routine_index, 0)
        self.assertTrue(bot.routine_pass_completed)
        self.assertIn("metal, oil", statuses[-1])

    def test_full_marches_never_defer_radar_block(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_tasks = [
            {
                "id": "radar_marches",
                "group": "radar",
                "enabled": True,
                "uses_march": True,
            },
        ]
        bot.routine_next_run = {"radar_marches": 0.0}
        bot.current_routine_index = 0
        bot.routine_max_marches = 5
        bot.routine_only_task_id = None
        bot.routine_forced_task_queue = []
        bot.routine_radar_return_hold = False

        self.assertFalse(
            bot._defer_due_ordinary_marches_when_full(
                bot.routine_tasks,
                now=100.0,
                active_marches=5,
            )
        )
        self.assertEqual(bot.routine_next_run["radar_marches"], 0.0)

    def test_missing_radar_opener_is_allowed_only_with_visual_fallback(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_mode = True
        task = {
            "id": "radar_rewards",
            "group": "Radar rewards",
            "settings": {"visual_fallback": True},
        }
        bot._scheduler_routine_tasks = lambda: [task]
        image = {
            "uid": str(uuid.uuid5(PROFILE_NAMESPACE, "radar_rewards:open_radar")),
            "group": "Radar rewards",
            "path": "Z:/definitely-missing/radar-opener.png",
        }

        self.assertTrue(bot._missing_template_uses_visual_fallback(image))
        task["settings"]["visual_fallback"] = False
        self.assertFalse(bot._missing_template_uses_visual_fallback(image))

    def test_start_routines_resets_all_selected_deadlines(self):
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
        bot.routine_pass_completed = True
        bot.get_routine_templates = lambda _task, active_only=True: [object()]
        bot.get_current_account = lambda: None
        bot.start = lambda: True

        self.assertTrue(bot.start_routines())
        self.assertEqual(bot.routine_next_run["radar_rewards"], 0.0)
        self.assertEqual(bot.routine_next_run["radar_quick"], 0.0)
        self.assertEqual(bot.routine_next_run["radar_marches"], 0.0)
        self.assertEqual(bot.routine_next_run["vip_rewards"], 0.0)
        self.assertFalse(bot.routine_pass_completed)

    def test_last_saved_task_marks_pass_complete_for_immediate_rotation(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_tasks = [
            {"id": "food", "enabled": True},
            {"id": "oil", "enabled": True},
        ]
        bot.current_routine_index = 1
        bot.routine_only_task_id = None
        bot.routine_forced_task_active_id = None
        bot.routine_forced_task_queue = []
        bot.routine_forced_task_return_index = None
        bot.routine_radar_in_progress_seen = False
        bot.routine_pass_completed = False

        bot._advance_routine_after_outcome(bot.routine_tasks[1], 100.0)

        self.assertEqual(bot.current_routine_index, 0)
        self.assertTrue(bot.routine_pass_completed)

    def test_autostart_resume_preserves_deadlines_and_queue_index(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_tasks = [
            {
                "id": "vip_rewards",
                "group": "VIP",
                "enabled": True,
            },
            {
                "id": "oil",
                "group": "Нефть",
                "enabled": True,
            },
        ]
        bot.groups = {}
        bot.routine_next_run = {
            "vip_rewards": 1000.0,
            "oil": 2000.0,
        }
        bot.current_routine_index = 1
        bot.routine_pass_completed = True
        bot.get_routine_templates = lambda _task, active_only=True: [object()]
        bot.get_current_account = lambda: None
        bot.start = lambda: True

        self.assertTrue(bot.start_routines(resume=True))
        self.assertEqual(bot.routine_next_run["vip_rewards"], 1000.0)
        self.assertEqual(bot.routine_next_run["oil"], 2000.0)
        self.assertEqual(bot.current_routine_index, 1)
        self.assertTrue(bot.routine_pass_completed)

    def test_manual_restart_during_forced_login_preserves_return_task(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_tasks = [
            {
                "id": "game_login",
                "group": "login",
                "enabled": True,
            },
            {
                "id": "completed_tasks",
                "group": "tasks",
                "enabled": True,
            },
        ]
        bot.groups = {}
        bot.routine_next_run = {
            "game_login": 0.0,
            "completed_tasks": 1234.0,
        }
        bot.current_routine_index = 0
        bot.routine_pass_completed = False
        bot.routine_forced_task_queue = []
        bot.routine_forced_task_active_id = "game_login"
        bot.routine_forced_task_return_index = 1
        bot.routine_radar_dispatched_this_pass = False
        bot.routine_radar_return_hold = False
        bot.routine_radar_return_active_seen = False
        bot.get_routine_templates = lambda _task, active_only=True: [object()]
        bot.get_current_account = lambda: None
        bot.start = lambda: True

        self.assertTrue(bot.start_routines(resume=False))
        self.assertEqual(bot.current_routine_index, 0)
        self.assertEqual(bot.routine_next_run["completed_tasks"], 1234.0)
        self.assertEqual(bot.routine_forced_task_active_id, "game_login")
        self.assertEqual(bot.routine_forced_task_return_index, 1)

    def test_launcher_recovery_login_returns_to_interrupted_queue_task(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.current_routine_task_id = None
        bot.account_rotation_enabled = False
        bot.routine_only_task_id = None
        bot.routine_forced_task_queue = []
        bot.routine_forced_task_active_id = None
        bot.routine_forced_task_return_index = None
        bot.routine_radar_return_hold = False
        bot.routine_radar_in_progress_seen = False
        bot.routine_deployment_blocked_until = 0.0
        bot.routine_max_marches = 5
        bot.current_routine_index = 1
        bot.routine_pass_completed = False
        bot.routine_next_run = {
            "game_login": 3600.0,
            "heal": 0.0,
        }
        bot.routine_tasks = [
            {
                "id": "game_login",
                "group": "login",
                "enabled": True,
                "uses_march": False,
            },
            {
                "id": "heal",
                "group": "heal",
                "enabled": True,
                "uses_march": False,
            },
        ]
        bot.groups = {"login": True, "heal": True}
        bot.search_images = [{"group": "heal", "enabled": True}]
        bot.lang = "ru"
        bot.input_backend = "adb"
        bot.adb_client = SimpleNamespace(
            current_foreground_package=lambda: "com.ldmnq.launcher3"
        )
        bot.get_active_marches = lambda _now: 0
        bot._account_rotation_switch_due = lambda _now: False
        bot._release_radar_return_hold = lambda *_args: False
        bot._try_return_camped_zombie_march = lambda *_args: False
        bot._clear_routine_coordinate_blocks = lambda _task: None
        bot._launch_game_for_login = lambda: True
        bot.set_status_message = lambda *_args, **_kwargs: None

        task = bot._begin_due_routine(100.0)

        self.assertEqual(task["id"], "game_login")
        self.assertEqual(bot.current_routine_index, 0)
        self.assertEqual(bot.routine_forced_task_active_id, "game_login")
        self.assertEqual(bot.routine_forced_task_return_index, 1)

        bot._advance_routine_after_outcome(task, 101.0)

        self.assertEqual(bot.current_routine_index, 1)
        self.assertIsNone(bot.routine_forced_task_active_id)
        self.assertIsNone(bot.routine_forced_task_return_index)

    def test_autostart_resume_does_not_restore_single_dispatch_hold(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_tasks = [
            {
                "id": "radar_marches",
                "group": "Радар - задания с отрядом",
                "enabled": True,
                "settings": {"dispatch_until_full": True},
            },
            {
                "id": "radar_rewards",
                "group": "Радар - награды",
                "enabled": True,
            },
        ]
        bot.groups = {}
        bot.routine_next_run = {
            "radar_marches": 300.0,
            "radar_rewards": 0.0,
        }
        bot.current_routine_index = 0
        bot.routine_pass_completed = False
        bot.routine_radar_dispatched_this_pass = True
        bot.routine_radar_return_hold = False
        bot.routine_radar_return_active_seen = False
        bot.get_routine_templates = lambda _task, active_only=True: [object()]
        bot.get_current_account = lambda: None
        bot.start = lambda: True

        self.assertTrue(bot.start_routines(resume=True))
        self.assertFalse(bot.routine_radar_return_hold)
        self.assertTrue(bot.routine_radar_dispatched_this_pass)
        self.assertEqual(bot.current_routine_index, 0)
        self.assertEqual(bot.routine_next_run["radar_marches"], 300.0)

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

    def test_marches_mode_confirms_narrow_world_squad_march_button(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_completed_steps = {"radar_open", "radar_action"}
        frames = iter(
            [
                np.zeros((720, 1280, 3), dtype=np.uint8),
                np.ones((720, 1280, 3), dtype=np.uint8),
            ]
        )
        bot._capture_screen_bgr = lambda force=False: (next(frames), (0, 0))
        bot._template_uid_is_visible = lambda _uid: False
        bot._world_map_visible_in_frame = lambda _frame: True
        calls = []
        bot._tap_radar_fallback = (
            lambda target, label, runtime_step, marker=False:
            calls.append((target, runtime_step, marker)) or True
        )
        confirmed = []
        finished = []
        bot._confirm_pending_radar_marker = lambda: confirmed.append(True)
        bot.set_status_message = lambda *_args, **_kwargs: None
        bot._finish_current_routine = lambda now=None: finished.append(now)
        bot._return_to_main_screen = lambda **_kwargs: True
        bot.routine_action_counts = {}
        bot.save_config = lambda: None
        bot.routine_radar_dispatched_this_pass = False
        bot.routine_radar_in_progress_seen = False
        task = {
            "id": "radar_marches",
            "settings": {"visual_fallback": True},
        }

        with patch(
            "buzzbot_app.detect_radar_deployment_prompt_target",
            return_value=None,
        ), patch(
            "buzzbot_app.detect_radar_squad_march_target",
            side_effect=[(970, 240), None],
        ):
            self.assertTrue(bot._try_radar_visual_fallback(task))

        self.assertEqual(calls, [((970, 240), "radar_march", False)])
        self.assertTrue(bot.routine_radar_dispatched_this_pass)
        self.assertTrue(bot.routine_radar_in_progress_seen)
        self.assertNotIn("radar_march", bot.routine_completed_steps)
        self.assertEqual(confirmed, [True])
        self.assertEqual(len(finished), 0)
        self.assertEqual(bot.routine_action_counts["radar_dispatches"], 1)

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

    def test_active_countdown_guard_never_closes_a_rewards_card(self):
        bot = AutoClicker.__new__(AutoClicker)
        captures = []
        bot._capture_screen_bgr = lambda force=False: captures.append(force)

        self.assertFalse(
            bot._try_radar_in_progress_card_fallback({"id": "radar_rewards"})
        )
        self.assertEqual(captures, [])

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

    def test_radar_idle_recovery_rechecks_a_late_settlement_transition(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_idle_recovery_attempted = False
        bot.routine_completed_steps = {"radar_open", "radar_marker", "radar_forward"}
        bot.routine_radar_pending_marker_key = None
        bot.routine_radar_marker_failure_counts = {}
        bot.routine_idle_guard_visible = False
        bot.routine_idle_outside_since = 20.0
        bot.routine_last_action_time = 0.0
        bot.blocked_coords = {}
        bot.set_status_message = lambda *_args, **_kwargs: None
        bot.get_routine_task_name = lambda _task: "Радар"
        bot._interruptible_sleep = lambda _seconds: None
        recoveries = iter((False, True))
        bot._return_to_main_screen = lambda **_kwargs: next(recoveries)

        self.assertTrue(
            bot._try_recover_current_routine_idle_screen({"id": "radar_marches"})
        )
        self.assertEqual(bot.routine_completed_steps, set())

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

    def test_return_shelter_continues_after_dispatched_radar_march(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.player_width = 1280
        bot.player_height = 720
        bot.adb_client = SimpleNamespace(tap=lambda *_args: None)
        bot.current_routine_task_id = "radar_marches"
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
        bot.routine_action_counts = {}
        bot.save_config = lambda: None
        finishes = []
        bot._finish_current_routine = lambda now=None: finishes.append(now)
        image = {
            "action": "radar_return_shelter",
            "last_used": 0.0,
            "delay": 0.0,
        }

        self.assertTrue(bot._execute_action(image, SimpleNamespace(x=100, y=100)))

        self.assertEqual(len(finishes), 0)
        self.assertNotIn("radar_march", bot.routine_completed_steps)
        self.assertEqual(bot.routine_action_counts["radar_dispatches"], 1)
        self.assertTrue(bot.routine_radar_in_progress_seen)

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
