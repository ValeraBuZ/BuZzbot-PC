from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import uuid
import zipfile

import cv2
import numpy as np

from buzzbot.matching import detect_alliance_donation_entry_target, imread_unicode
from buzzbot.routines import PROFILE_NAMESPACE
from buzzbot_app import AutoClicker


ROOT = Path(__file__).resolve().parents[1]
ENTRY_UID = str(uuid.uuid5(PROFILE_NAMESPACE, "alliance_donations:open_alliance"))
ENTRY_PATH = ROOT / "img/alliance_donations" / f"{ENTRY_UID}.png"
FIXTURE = ROOT / "tests/assets/alliance_donations/entry_red_warning.png"


class DonationEntryTests(unittest.TestCase):
    def setUp(self):
        self.frame = imread_unicode(FIXTURE)
        # The distributed profile contains the byte-identical canonical image;
        # tests must not depend on the user's generated runtime img directory.
        with zipfile.ZipFile(ROOT / "profiles/BuZzbot_PC_1280x720.zip") as archive:
            data = archive.read(f"templates/{ENTRY_UID}.png")
        self.template = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        self.assertIsNotNone(self.frame)
        self.assertIsNotNone(self.template)

    def test_real_warning_badge_misses_full_template_but_stable_icon_passes(self):
        score = cv2.minMaxLoc(cv2.matchTemplate(self.frame, self.template, cv2.TM_CCOEFF_NORMED))[1]
        self.assertLess(score, .88)
        self.assertEqual(detect_alliance_donation_entry_target(self.frame, self.template), (968, 654))

    def test_resolution_scaling_preserves_full_icon_click_centre(self):
        for width, height in ((960, 540), (1920, 1080)):
            with self.subTest(width=width):
                target = detect_alliance_donation_entry_target(cv2.resize(self.frame, (width, height)), self.template)
                self.assertIsNotNone(target)
                self.assertLessEqual(abs(target[0] - round(968 * width / 1280)), 1)
                self.assertLessEqual(abs(target[1] - round(654 * height / 720)), 1)

    def test_unchanged_icon_uses_same_centre(self):
        frame = np.zeros_like(self.frame)
        frame[627:681, 940:997] = self.template
        self.assertEqual(detect_alliance_donation_entry_target(frame, self.template), (968, 654))

    def test_other_navigation_button_and_displaced_alliance_are_rejected(self):
        for other_x in (740, 840, 1040, 1140):
            with self.subTest(button=other_x):
                frame = np.zeros_like(self.frame)
                frame[595:705, 915:1020] = self.frame[595:705, other_x:other_x + 105]
                self.assertIsNone(detect_alliance_donation_entry_target(frame, self.template))
        outside = np.zeros_like(self.frame)
        outside[300:354, 400:457] = self.template
        self.assertIsNone(detect_alliance_donation_entry_target(outside, self.template))

    def test_custom_threshold_is_not_lowered_and_invalid_images_fail_closed(self):
        self.assertIsNone(detect_alliance_donation_entry_target(self.frame, self.template, .995))
        for threshold in (None, "bad", float("nan"), float("inf")):
            self.assertIsNone(detect_alliance_donation_entry_target(self.frame, self.template, threshold))
        for frame, template in ((None, self.template), (self.frame, None),
                                (self.frame, self.template[:22]),
                                (self.frame, np.zeros_like(self.template))):
            with self.subTest(frame_none=frame is None):
                self.assertIsNone(detect_alliance_donation_entry_target(frame, template))

    def make_bot(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.routine_current_had_action = False
        bot.routine_donation_entry_attempted = False
        bot.routine_completed_steps = set()
        bot.get_routine_templates = Mock(return_value=[{"uid": ENTRY_UID, "path": str(ENTRY_PATH), "confidence": .88}])
        bot._is_game_home_visible = Mock(return_value=True)
        bot._capture_screen_bgr = Mock(return_value=(self.frame, (0, 0)))
        bot.template_cache = SimpleNamespace(get_color=Mock(return_value=self.template))
        bot._check_worker_interrupted = Mock()
        bot._tap_routine_fallback = Mock(return_value=True)
        return bot

    def test_entry_is_one_attempt_without_claiming_task_completion(self):
        bot = self.make_bot()
        self.assertTrue(bot._try_alliance_donations_entry_fallback({"id": "alliance_donations"}))
        self.assertFalse(bot._try_alliance_donations_entry_fallback({"id": "alliance_donations"}))
        bot._tap_routine_fallback.assert_called_once()
        self.assertEqual(bot._tap_routine_fallback.call_args.args[0], (968, 654))
        self.assertEqual(bot.routine_completed_steps, set())
        bot._check_worker_interrupted.assert_called_once()

    def test_non_home_and_other_tasks_or_disabled_entry_never_click(self):
        for kind in ("non_home", "other_task", "disabled", "already_progressed"):
            with self.subTest(kind=kind):
                bot = self.make_bot()
                task = {"id": "alliance_donations"}
                if kind == "non_home":
                    bot._is_game_home_visible.return_value = False
                elif kind == "other_task":
                    task["id"] = "alliance_gifts"
                elif kind == "disabled":
                    bot.get_routine_templates.return_value = []
                else:
                    bot.routine_current_had_action = True
                self.assertFalse(bot._try_alliance_donations_entry_fallback(task))
                bot._tap_routine_fallback.assert_not_called()

    def test_desktop_crop_origin_is_added_once(self):
        bot = self.make_bot()
        bot.input_backend = "desktop"
        bot._capture_screen_bgr.return_value = self.frame, (100, 50)
        self.assertTrue(bot._try_alliance_donations_entry_fallback({"id": "alliance_donations"}))
        self.assertEqual(bot._tap_routine_fallback.call_args.args[0], (1068, 704))

    def test_stop_or_pause_guard_prevents_entry(self):
        bot = self.make_bot()
        bot._check_worker_interrupted.side_effect = RuntimeError("worker interrupted")
        with self.assertRaises(RuntimeError):
            bot._try_alliance_donations_entry_fallback({"id": "alliance_donations"})
        bot._tap_routine_fallback.assert_not_called()
        self.assertFalse(bot.routine_donation_entry_attempted)


if __name__ == "__main__":
    unittest.main()
