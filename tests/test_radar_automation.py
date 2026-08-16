import unittest
from types import SimpleNamespace

import numpy as np

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


if __name__ == "__main__":
    unittest.main()
