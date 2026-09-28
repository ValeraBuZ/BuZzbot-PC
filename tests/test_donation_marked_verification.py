from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import cv2
import numpy as np

from buzzbot.display import make_display_profile
from buzzbot.matching import (
    alliance_marked_project_is_visible, detect_alliance_marked_project_target,
    imread_unicode, radar_task_card_is_visible,
)
from buzzbot_app import AutoClicker


ASSETS = Path(__file__).parent / 'assets'


class MarkedDonationVerificationTests(unittest.TestCase):
    def setUp(self):
        self.tree = imread_unicode(ASSETS / 'alliance_donations/marked_tree.png')
        self.project = imread_unicode(ASSETS / 'alliance_donations/marked_project.png')

    def test_real_marked_label_selects_correct_project_at_both_brightnesses(self):
        for brightness in (1.0, 0.55):
            frame = (self.tree * brightness).astype(np.uint8)
            target = detect_alliance_marked_project_target(frame)
            self.assertIsNotNone(target)
            self.assertTrue(650 <= target[0] <= 715 and 565 <= target[1] <= 635)

    def test_real_marked_label_scales_with_device(self):
        for width, height in ((960, 540), (1920, 1080)):
            target = detect_alliance_marked_project_target(cv2.resize(self.tree, (width, height)))
            self.assertIsNotNone(target)
            self.assertLess(abs(target[0] - 688 * width / 1280), 5)
            self.assertLess(abs(target[1] - 598 * height / 720), 5)

    def test_opened_project_requires_marked_label_and_donation_panel(self):
        self.assertTrue(alliance_marked_project_is_visible(self.project))
        self.assertFalse(alliance_marked_project_is_visible(self.tree))
        unmarked = self.project.copy()
        unmarked[100:155, 390:565] = 0
        self.assertFalse(alliance_marked_project_is_visible(unmarked))

    def test_exhausted_marked_project_is_recognized_with_disabled_resource_button(self):
        exhausted = self.project.copy()
        exhausted[490:525, 1040:1140] = imread_unicode(ASSETS / 'alliance_donations/counter_zero.png')
        exhausted[557:606, 859:1121] = (55, 55, 55)
        self.assertTrue(alliance_marked_project_is_visible(exhausted))

    def make_bot(self, after):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = 'adb'
        bot.adb_client = Mock()
        bot._check_worker_interrupted = Mock()
        bot.get_display_profile = Mock(return_value=make_display_profile(1280, 720))
        bot._resolve_action_numbers = Mock(return_value=[])
        bot._resource_result_level_rejected = Mock(return_value=False)
        bot._capture_screen_bgr = Mock(side_effect=[(self.tree, (0, 0))] + [(after, (0, 0))] * 4)
        bot._invalidate_capture = Mock()
        bot._save_routine_calibration_frame = Mock()
        bot._interruptible_sleep = Mock()
        bot.set_status_message = Mock()
        bot.sleep_found = 0
        return bot

    def test_click_is_confirmed_only_when_marked_project_actually_opens(self):
        for after, expected in ((self.project, True), (self.tree, False)):
            bot = self.make_bot(after)
            config = {'action': 'alliance_marked_project', 'delay': 0}
            self.assertEqual(bot._execute_action(config, SimpleNamespace(x=500, y=300)), expected)
            self.assertEqual(bot.adb_client.tap.call_count, 1)
            self.assertEqual('last_used' in config, expected)

    def test_clipboard_distinguishes_open_card_from_real_radar_overview(self):
        self.assertTrue(radar_task_card_is_visible(imread_unicode(ASSETS / 'radar/available_event_expiry.png')))
        self.assertFalse(radar_task_card_is_visible(imread_unicode(ASSETS / 'radar/overview_stopped.png')))


if __name__ == '__main__':
    unittest.main()
