from pathlib import Path
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from buzzbot.matching import detect_game_server_connection_error, imread_unicode


ASSETS = Path(__file__).parent / "assets"


class ServerConnectionErrorDetectorTests(unittest.TestCase):
    def setUp(self):
        # Actual title error; only the two generic text/button regions remain.
        self.frame = imread_unicode(ASSETS / "accounts/server_connection_error.png")
        self.assertIsNotNone(self.frame)

    def test_real_error_and_exit_label_are_recognized(self):
        self.assertIs(detect_game_server_connection_error(self.frame), True)

    def test_supported_resolution_scaling_keeps_both_text_anchors(self):
        for size in ((960, 540), (1920, 1080)):
            with self.subTest(size=size):
                self.assertTrue(detect_game_server_connection_error(cv2.resize(self.frame, size)))

    def test_either_missing_anchor_rejects_recovery(self):
        for top, bottom in ((515, 571), (596, 657)):
            with self.subTest(masked_top=top):
                frame = self.frame.copy()
                frame[top:bottom] = 0
                self.assertFalse(detect_game_server_connection_error(frame))

    def test_error_code_or_message_line_missing_is_not_the_exact_error(self):
        for top, bottom in ((524, 547), (547, 569)):
            with self.subTest(masked_top=top):
                frame = self.frame.copy()
                frame[top:bottom, 425:825] = 0
                self.assertFalse(detect_game_server_connection_error(frame))

    def test_error_with_unlabelled_gold_button_is_rejected(self):
        frame = self.frame.copy()
        frame[596:657, 515:750] = (130, 162, 187)
        self.assertFalse(detect_game_server_connection_error(frame))

    def test_error_with_different_real_gold_button_is_rejected(self):
        frame = self.frame.copy()
        other = imread_unicode(ASSETS / "accounts/server_different_gold_button.png")
        self.assertIsNotNone(other)
        frame[596:657] = other[596:657]
        self.assertFalse(detect_game_server_connection_error(frame))

    def test_anchors_outside_their_expected_regions_are_rejected(self):
        for dx, dy in ((0, -150), (200, 0)):
            with self.subTest(dx=dx, dy=dy):
                displaced = cv2.warpAffine(self.frame, np.float32([[1, 0, dx], [0, 1, dy]]), (1280, 720))
                self.assertFalse(detect_game_server_connection_error(displaced))

    def test_real_sdk_update_loading_and_promo_do_not_restart_game(self):
        # These crops retain only generic UI; no login values or account HUD.
        for name in ("sdk_error", "update_chooser", "ordinary_loading", "different_gold_button"):
            frame = imread_unicode(ASSETS / f"accounts/server_{name}.png")
            self.assertIsNotNone(frame)
            with self.subTest(screen=name):
                self.assertFalse(detect_game_server_connection_error(frame))

    def test_real_home_navigation_and_blank_frames_are_rejected(self):
        home = imread_unicode(ASSETS / "alliance_donations/entry_red_warning.png")
        self.assertIsNotNone(home)
        self.assertFalse(detect_game_server_connection_error(home))
        for value in (0, 127, 255):
            with self.subTest(value=value):
                self.assertFalse(detect_game_server_connection_error(np.full_like(self.frame, value)))

    def test_invalid_frames_fail_closed(self):
        for frame in (None, "image", np.zeros((0, 0, 3), np.uint8),
                      np.zeros((720, 1280), np.uint8), np.zeros((720, 1280, 4), np.uint8),
                      np.zeros((720, 1280, 3), np.float32)):
            with self.subTest(shape=getattr(frame, "shape", None)):
                self.assertFalse(detect_game_server_connection_error(frame))

    def test_missing_or_unusable_bundled_anchor_fails_closed(self):
        for replacement in (None, np.zeros((45, 364, 3), np.uint8),
                            np.zeros((100, 800, 3), np.uint8)):
            with self.subTest(missing=replacement is None), patch(
                "buzzbot.matching.imread_unicode", return_value=replacement,
            ):
                self.assertFalse(detect_game_server_connection_error(self.frame))


if __name__ == "__main__":
    unittest.main()
