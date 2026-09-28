import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from pathlib import Path
import cv2

import tests.test_zombie_search as zombie_fixture
from buzzbot.routines import no_action_retry_delay, next_run_after_finish
from buzzbot.matching import collective_target_busy_is_visible


class CollectiveTransitionRetryTests(unittest.TestCase):
    def make_bot(self, step="rally"):
        bot = zombie_fixture.ZombieSearchTests().make_bot()
        bot.cycle_mode = False
        bot.current_routine_task_id = "collective_mind"
        image = dict(zombie_fixture.ZombieSearchTests.search_image(), action="click",
                     runtime_step=step, group="collective", description=step)
        successor = {"runtime_step": {"rally": "confirm_rally", "confirm_rally": "march"}[step],
                     "group": "collective"}
        bot.search_images = [image, successor]
        bot._validate_detected_match = Mock(return_value=(True, ""))
        bot._capture_screen_bgr = lambda **kwargs: (None, (0, 0))
        return bot, image, successor

    @staticmethod
    def visible(x=903, y=280):
        return SimpleNamespace(x=x, y=y), (x-40, y-20, 80, 40), 0.99

    def test_ignored_rally_click_retries_fresh_button_then_confirms_next_screen(self):
        bot, image, successor = self.make_bot()
        def locate(candidate):
            if candidate is image:
                return self.visible(420, 530)  # Card moved; old coordinate is unsafe.
            return self.visible() if len(bot.adb_client.taps) == 2 else (None, None, 0)
        bot._locate_image = locate
        self.assertTrue(bot._execute_action(image, SimpleNamespace(x=1079, y=542)))
        self.assertEqual(bot.adb_client.taps, [(1079, 542), (420, 530)])

    def test_already_open_next_screen_does_not_repeat_rally(self):
        bot, image, successor = self.make_bot()
        bot._locate_image = lambda candidate: self.visible()
        self.assertTrue(bot._execute_action(image, SimpleNamespace(x=1079, y=542)))
        self.assertEqual(len(bot.adb_client.taps), 1)

    def test_rally_still_visible_is_not_success_and_attempts_are_bounded(self):
        bot, image, successor = self.make_bot()
        bot._locate_image = lambda candidate: (self.visible(1079, 542) if candidate is image
                                                else (None, None, 0))
        self.assertFalse(bot._execute_action(image, SimpleNamespace(x=1079, y=542)))
        self.assertEqual(len(bot.adb_client.taps), 3)
        self.assertEqual(bot.routine_action_failure_reason, "collective_transition")

    def test_unknown_screen_never_receives_a_blind_retry(self):
        bot, image, successor = self.make_bot()
        bot._locate_image = lambda candidate: (None, None, 0)
        self.assertFalse(bot._execute_action(image, SimpleNamespace(x=1079, y=542)))
        self.assertEqual(len(bot.adb_client.taps), 1)

    def test_confirm_time_requires_squad_screen(self):
        for squad_open in (True, False):
            with self.subTest(squad_open=squad_open):
                bot, image, successor = self.make_bot("confirm_rally")
                bot._locate_image = lambda candidate: (self.visible() if candidate is image or squad_open
                                                        else (None, None, 0))
                self.assertEqual(bot._execute_action(image, SimpleNamespace(x=903, y=280)), squad_open)

    def test_stop_interrupts_confirmation_without_additional_taps(self):
        bot, image, successor = self.make_bot()
        bot._locate_image = lambda candidate: (None, None, 0)
        bot._interruptible_sleep = lambda seconds: bot.stop_event.set()
        self.assertFalse(bot._execute_action(image, SimpleNamespace(x=1079, y=542)))
        self.assertEqual(len(bot.adb_client.taps), 1)

    def test_failed_attempt_retries_soon_but_success_keeps_configured_interval(self):
        task = {"id": "collective_mind", "interval_minutes": 5, "settings": {"repeat": True}}
        self.assertEqual(no_action_retry_delay(task), 30)
        self.assertEqual(next_run_after_finish(task, 1000), 1300)

    def test_real_busy_message_lowers_next_search_without_repeated_rally_taps(self):
        bot, image, successor = self.make_bot()
        frame = cv2.imread(str(Path(__file__).parent / "assets/collective/target_busy.jpg"))
        bot._capture_screen_bgr = lambda **kwargs: (frame, (0, 0))
        bot._locate_image = Mock()
        self.assertFalse(bot._execute_action(image, SimpleNamespace(x=1079, y=542)))
        self.assertEqual(bot.routine_action_failure_reason, "collective_target_busy")
        self.assertEqual(len(bot.adb_client.taps), 1)
        bot._locate_image.assert_not_called()
        bot._current_task_settings = lambda: {"level": 7}
        _, key = bot._hunt_context("collective_mind")
        bot.hunt_found_levels = {key: 7}
        bot._defer_collective_busy_target()
        self.assertEqual(bot.hunt_search_levels[key], 6)
        self.assertEqual(bot.hunt_found_levels, {})
        self.assertEqual(bot.deferred_unavailable[-1][1], 5)

    def test_busy_at_lowest_level_resets_ceiling_and_waits_instead_of_spinning(self):
        bot, image, successor = self.make_bot()
        bot._current_task_settings = lambda: {"level": 6}
        _, key = bot._hunt_context("collective_mind")
        bot.hunt_found_levels = {key: 1}
        bot._defer_collective_busy_target()
        self.assertEqual(bot.hunt_search_levels[key], 6)
        self.assertEqual(bot.deferred_unavailable[-1][1], 60)

    def test_busy_detector_rejects_normal_cards_stamina_and_world_map(self):
        assets = Path(__file__).parent / "assets"
        for name, expected in (("collective/target_busy.jpg", True),
                               ("collective/target_card.jpg", False),
                               ("collective/stamina_toast.png", False),
                               ("zombie/march_dispatched.jpg", False)):
            frame = cv2.imread(str(assets / name))
            for scale in (1.0, 0.75):
                with self.subTest(name=name, scale=scale):
                    self.assertEqual(collective_target_busy_is_visible(
                        cv2.resize(frame, None, fx=scale, fy=scale)), expected)


if __name__ == "__main__":
    unittest.main()
