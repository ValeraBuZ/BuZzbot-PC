import unittest

import cv2
import numpy as np
from unittest.mock import patch

from buzzbot_app import AutoClicker


class MarchCountingTests(unittest.TestCase):
    def make_bot(self, deadlines=(), observed=None):
        bot = AutoClicker.__new__(AutoClicker)
        bot.routine_march_deadlines = list(deadlines)
        bot.routine_max_marches = 5
        bot.routine_confirmed_march_floor = 0
        bot.routine_display_active_marches = 0
        bot.routine_march_observer_grace_until = 0.0
        bot._ensure_routine_march_context = lambda: False
        bot._detect_observed_marches = lambda: observed
        bot.save_config = lambda: None
        return bot

    def test_updated_game_counter_is_not_counted_twice(self):
        bot = self.make_bot(observed=1)

        self.assertTrue(bot._register_routine_march({"march_duration_minutes": 10}, now=100.0))

        self.assertEqual(len(bot.routine_march_deadlines), 1)
        self.assertEqual(bot.routine_confirmed_march_floor, 1)

    def test_returned_squad_reduces_local_count_after_send(self):
        bot = self.make_bot(deadlines=(1000.0, 1000.0, 1000.0), observed=1)

        self.assertTrue(bot._register_routine_march({"march_duration_minutes": 10}, now=100.0))

        self.assertEqual(len(bot.routine_march_deadlines), 1)
        self.assertEqual(bot.routine_confirmed_march_floor, 1)

    def test_local_count_advances_when_game_counter_is_unavailable(self):
        bot = self.make_bot(deadlines=(1000.0,), observed=None)

        self.assertTrue(bot._register_routine_march({"march_duration_minutes": 10}, now=100.0))

        self.assertEqual(len(bot.routine_march_deadlines), 2)
        self.assertEqual(bot.routine_confirmed_march_floor, 2)

    def test_observed_preexisting_marches_are_adopted_after_send(self):
        bot = self.make_bot(observed=4)

        self.assertTrue(bot._register_routine_march({"march_duration_minutes": 10}, now=100.0))

        self.assertEqual(len(bot.routine_march_deadlines), 4)
        self.assertEqual(bot.routine_confirmed_march_floor, 4)

    def test_visible_partial_count_replaces_stale_full_reservation(self):
        for observed in (2, 3, 4):
            with self.subTest(observed=observed):
                bot = self.make_bot(deadlines=(1000.0,) * 5, observed=observed)
                bot.routine_confirmed_march_floor = 5
                bot.routine_march_observer_grace_until = 300.0

                self.assertEqual(bot.get_active_marches(now=100.0), observed)
                self.assertEqual(len(bot.routine_march_deadlines), observed)

    def test_transient_zero_after_send_does_not_drop_the_new_march(self):
        bot = self.make_bot(deadlines=(1000.0,), observed=0)
        bot.routine_confirmed_march_floor = 1
        bot.routine_march_observer_grace_until = 108.0

        self.assertEqual(bot.get_active_marches(now=103.0), 1)
        self.assertEqual(len(bot.routine_march_deadlines), 1)
        self.assertEqual(bot.get_active_marches(now=109.0), 0)
        self.assertEqual(bot.routine_march_deadlines, [])

    def test_world_map_without_deployment_panel_requires_stable_zero(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.search_images = [{
            "path": "observer.png",
            "observer_only": True,
            "march_count": 1,
            "observer_confidence": 0.70,
        }]
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        template = np.tile(np.arange(80, dtype=np.uint8), (38, 1))

        class Cache:
            def get_gray(self, _path):
                return template

        bot.template_cache = Cache()
        bot._capture_screen_bgr = lambda force=False: (frame, (0, 0))
        bot._world_map_visible_in_frame = lambda _frame: True

        with patch("buzzbot_app.time.monotonic", side_effect=(100.0, 103.0, 106.0)):
            self.assertIsNone(bot._detect_observed_marches())
            self.assertIsNone(bot._detect_observed_marches())
            self.assertEqual(bot._detect_observed_marches(), 0)

    def test_lower_positive_count_requires_stable_observation(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.search_images = [{
            "path": "observer-4.png",
            "observer_only": True,
            "march_count": 4,
            "observer_confidence": 0.70,
        }]
        bot.routine_display_active_marches = 5
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        template = np.tile(np.arange(80, dtype=np.uint8), (38, 1))
        frame[150:188, 1194:1274] = cv2.cvtColor(template, cv2.COLOR_GRAY2BGR)

        class Cache:
            def get_gray(self, _path):
                return template

        bot.template_cache = Cache()
        bot._capture_screen_bgr = lambda force=False: (frame, (0, 0))

        with patch("buzzbot_app.time.monotonic", side_effect=(100.0, 101.0, 102.1)):
            self.assertEqual(bot._detect_observed_marches(), 5)
            self.assertEqual(bot._detect_observed_marches(), 5)
            self.assertEqual(bot._detect_observed_marches(), 4)


if __name__ == "__main__":
    unittest.main()
