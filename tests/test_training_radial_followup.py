from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import cv2

from buzzbot.display import make_display_profile
from buzzbot.matching import detect_training_radial_action_target, imread_unicode
from buzzbot_app import AutoClicker


ASSETS = Path(__file__).parent / "assets/training"
TRAINING_IDS = ("train_infantry", "train_riders", "train_shooters", "train_vehicles")


class TrainingRadialDetectorTests(unittest.TestCase):
    def test_live_max_level_barracks_action_moves_left_when_upgrade_is_absent(self):
        frame = imread_unicode(ASSETS / "max_level_radial.png")
        self.assertEqual(detect_training_radial_action_target(frame, (608, 210)), (711, 498))

    def test_live_lower_level_barracks_keeps_its_actual_action_position(self):
        frame = imread_unicode(ASSETS / "upgrade_radial.png")
        self.assertEqual(detect_training_radial_action_target(frame, (608, 210)), (755, 482))

    def test_settlement_without_label_and_unverified_title_are_rejected(self):
        frame = imread_unicode(ASSETS / "occupied_settlement.png")
        self.assertIsNone(detect_training_radial_action_target(frame, (608, 210)))
        self.assertIsNone(detect_training_radial_action_target(frame, None))
        self.assertIsNone(detect_training_radial_action_target(None, (608, 210)))
        frame = imread_unicode(ASSETS / "max_level_radial.png")
        self.assertIsNone(detect_training_radial_action_target(frame, (100, 100)))

    def test_display_scaling_preserves_the_recognized_action(self):
        frame = imread_unicode(ASSETS / "max_level_radial.png")
        for scale in (0.75, 1.5):
            with self.subTest(scale=scale):
                scaled = cv2.resize(frame, (round(1280 * scale), round(720 * scale)))
                target = detect_training_radial_action_target(scaled, (608 * scale, 210 * scale))
                self.assertIsNotNone(target)
                self.assertLessEqual(abs(target[0] - 711 * scale), 1)
                self.assertLessEqual(abs(target[1] - 498 * scale), 1)


class TrainingRadialRuntimeTests(unittest.TestCase):
    def setUp(self):
        log_patch = patch("buzzbot_app.logger")
        log_patch.start()
        self.addCleanup(log_patch.stop)

    def make_bot(self, task_id="train_infantry", *, title_visible=True, confirms_form=True):
        task = {"id": task_id, "settings": {"max_queue_checks": 5}}
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = Mock()
        bot._check_worker_interrupted = Mock()
        bot.get_display_profile = Mock(return_value=make_display_profile(1280, 720))
        bot._resolve_action_numbers = Mock(return_value=[])
        bot._resource_result_level_rejected = Mock(return_value=False)
        frame = imread_unicode(ASSETS / "max_level_radial.png")
        bot._capture_screen_bgr = Mock(return_value=(frame, (0, 0)))
        bot._invalidate_capture = Mock()
        bot._interruptible_sleep = Mock()
        bot.set_status_message = Mock()
        bot.get_routine_task_name = Mock(return_value="Training")
        bot.get_routine_task = Mock(return_value=task)
        bot.current_routine_task_id = task_id
        bot.routine_completed_steps = set()
        bot.routine_action_counts = {}
        bot.click_count = 0
        bot.sleep_found = 0
        state = {"title": title_visible, "form": False}
        match = ({"runtime_step": "building"}, SimpleNamespace(x=608, y=210), (530, 203, 154, 16), 0.95)

        def visible(_task, step):
            return match if state["form" if step == "train" else "title"] else None

        def tap(x, y):
            if (x, y) == (42, 330):
                state["title"] = True
            elif (x, y) == (711, 498) and confirms_form:
                state["form"] = True

        bot._training_step_visible = Mock(side_effect=visible)
        bot.adb_client.tap.side_effect = tap
        return bot, task, state

    def queue_image(self):
        return {"action": "select_training_queue", "runtime_step": "queue", "delay": 0,
                "click_offset": (0, 0), "limit_key": "max_queue_checks"}

    def test_live_title_click_opens_actual_label_instead_of_old_title_offset(self):
        for task_id in TRAINING_IDS:
            with self.subTest(task_id=task_id):
                bot, _task, _state = self.make_bot(task_id)
                image = {"action": "click", "runtime_step": "building", "click_offset": (150, 277)}
                self.assertTrue(bot._execute_action(image, SimpleNamespace(x=608, y=210)))
                bot.adb_client.tap.assert_called_once_with(711, 498)
                self.assertEqual(bot.routine_completed_steps, {"queue", "building"})

    def test_already_selected_barracks_opens_before_overview_can_cycle_it(self):
        bot, _task, _state = self.make_bot()
        self.assertTrue(bot._execute_action(self.queue_image(), SimpleNamespace(x=42, y=330)))
        bot.adb_client.tap.assert_called_once_with(711, 498)
        self.assertEqual(bot.routine_completed_steps, {"queue", "building"})

    def test_overview_selects_barracks_then_opens_and_verifies_troop_form(self):
        bot, _task, _state = self.make_bot(title_visible=False)
        self.assertTrue(bot._execute_action(self.queue_image(), SimpleNamespace(x=42, y=330)))
        self.assertEqual([call.args for call in bot.adb_client.tap.call_args_list], [(42, 330), (711, 498)])
        self.assertIn("building", bot.routine_completed_steps)
        self.assertNotIn("train", bot.routine_completed_steps)

    def test_unchanged_barracks_after_radial_click_is_not_completed_building(self):
        bot, _task, _state = self.make_bot(confirms_form=False)
        bot.routine_completed_steps.add("building")  # stale state from the old title click
        self.assertFalse(bot._execute_action(self.queue_image(), SimpleNamespace(x=42, y=330)))
        bot.adb_client.tap.assert_called_once_with(711, 498)
        self.assertNotIn("building", bot.routine_completed_steps)
        self.assertNotIn("train", bot.routine_completed_steps)

    def test_wrong_barracks_title_blocks_training_even_if_label_is_visible(self):
        bot, _task, _state = self.make_bot(title_visible=False)
        image = {"action": "click", "runtime_step": "building", "click_offset": (150, 277)}
        self.assertFalse(bot._execute_action(image, SimpleNamespace(x=608, y=210)))
        bot.adb_client.tap.assert_not_called()

    def test_queue_cannot_click_over_an_already_open_training_form(self):
        bot, _task, state = self.make_bot()
        state["form"] = True
        self.assertFalse(bot._execute_action(self.queue_image(), SimpleNamespace(x=42, y=330)))
        bot.adb_client.tap.assert_not_called()

    def test_missing_train_label_does_not_fall_back_to_calibrated_coordinates(self):
        bot, task, _state = self.make_bot()
        bot._capture_screen_bgr.return_value = (imread_unicode(ASSETS / "occupied_settlement.png"), (0, 0))
        self.assertFalse(bot._open_training_from_barracks(task))
        bot.adb_client.tap.assert_not_called()
        self.assertNotIn("building", bot.routine_completed_steps)

    def test_repeated_radial_failures_defer_with_unconfirmed_form_reason(self):
        bot, task, _state = self.make_bot(confirms_form=False)
        bot._defer_current_routine_unavailable = Mock()
        for _ in range(5):
            self.assertTrue(bot._try_training_catalogue_fallback(task))
        bot._defer_current_routine_unavailable.assert_called_once()
        reason = bot._defer_current_routine_unavailable.call_args.args[0]
        self.assertIn("не удалось подтвердить форму", reason)
        self.assertNotIn("building", bot.routine_completed_steps)

    def test_queue_check_limit_is_not_reported_as_proof_of_busy_queues(self):
        for task_id in TRAINING_IDS:
            with self.subTest(task_id=task_id):
                bot, task, _state = self.make_bot(task_id)
                bot.routine_next_run = {}
                bot.routine_current_action_count = 5
                bot.routine_only_task_id = None
                bot._return_to_main_screen = Mock(return_value=True)
                bot._advance_routine_after_outcome = Mock()
                bot.save_config = Mock()
                bot._defer_current_routine_unavailable("max_queue_checks", now=100, retry_delay=60)
                self.assertEqual(bot.routine_last_outcome["outcome"], "deferred_unavailable")
                self.assertIn("не удалось подтвердить", bot.routine_last_outcome["reason"])
                self.assertNotEqual(bot.routine_last_outcome["reason"], "max_queue_checks")
                self.assertEqual(bot.routine_next_run[task_id], 160)

    def test_start_requires_the_requested_troop_form(self):
        bot, _task, _state = self.make_bot()
        self.assertFalse(bot._execute_action({"action": "train_highest"}, SimpleNamespace(x=200, y=40)))
        bot.adb_client.tap.assert_not_called()


if __name__ == "__main__":
    unittest.main()
