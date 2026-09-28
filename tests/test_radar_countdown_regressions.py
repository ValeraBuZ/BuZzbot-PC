"""Distinguish a radar event's expiry from an already-running mission."""

from pathlib import Path
import unittest

import cv2

from buzzbot.matching import (
    detect_radar_card_action_target,
    imread_unicode,
    radar_card_has_active_countdown,
)


class RadarCountdownRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        # Real capture: the available boss event has "ВПЕРЕД" and the same
        # 01:45:40 expiry as the overview's event refresh countdown.
        cls.available_card = imread_unicode(
            root / "tests/assets/radar/available_event_expiry.png"
        )
        # Existing runtime template captured from an active card. Positive
        # frames below are composites, not claimed to be live screenshots.
        cls.in_progress_label = imread_unicode(
            root / "buzzbot/assets/radar/in_progress_label.png"
        )

    def test_available_event_expiry_does_not_defer_an_unstarted_mission(self):
        self.assertIsNotNone(self.available_card)
        for size in ((1280, 720), (640, 360), (1920, 1080)):
            with self.subTest(size=size):
                frame = cv2.resize(self.available_card, size)
                self.assertIsNotNone(detect_radar_card_action_target(frame))
                self.assertFalse(radar_card_has_active_countdown(frame))

    def test_explicit_in_progress_card_retains_countdown_detection(self):
        self.assertIsNotNone(self.in_progress_label)
        frame = self.available_card.copy()
        height, width = self.in_progress_label.shape[:2]
        frame[595:595 + height, 180:180 + width] = self.in_progress_label
        for size in ((1280, 720), (640, 360), (1920, 1080)):
            with self.subTest(size=size):
                self.assertTrue(
                    radar_card_has_active_countdown(cv2.resize(frame, size))
                )

    def test_in_progress_text_elsewhere_does_not_mark_the_card_active(self):
        frame = self.available_card.copy()
        height, width = self.in_progress_label.shape[:2]
        frame[595:595 + height, 800:800 + width] = self.in_progress_label
        self.assertFalse(radar_card_has_active_countdown(frame))


if __name__ == "__main__":
    unittest.main()
