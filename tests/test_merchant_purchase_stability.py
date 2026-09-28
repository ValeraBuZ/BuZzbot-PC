import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import cv2
import numpy as np

from buzzbot_app import AutoClicker


class MerchantPurchaseStabilityTests(unittest.TestCase):
    def test_real_resource_offer_passes_both_frames(self):
        frame = cv2.imread(str(Path(__file__).parent / "assets/merchant/resource_prices.png"))
        self.assertIsNotNone(frame)
        bot = AutoClicker.__new__(AutoClicker)
        bot._interruptible_sleep = Mock()
        bot.stop_event = threading.Event()
        bot._capture_screen_bgr = Mock(return_value=(frame.copy(), (0, 0)))
        self.assertIsNotNone(bot._verify_merchant_purchase_target(frame, (678, 387)))

    def test_real_vip_store_cannot_confirm_a_merchant_purchase(self):
        frame = cv2.imread(str(Path(__file__).parent / "assets/merchant/vip_grid.png"))
        self.assertIsNotNone(frame)
        bot = AutoClicker.__new__(AutoClicker)
        bot._capture_screen_bgr = Mock()
        self.assertIsNone(bot._verify_merchant_purchase_target(frame, (370, 269)))
        bot._capture_screen_bgr.assert_not_called()

    def test_stop_while_fresh_frame_arrives_prevents_purchase(self):
        frame = cv2.imread(str(Path(__file__).parent / "assets/merchant/resource_prices.png"))
        bot = AutoClicker.__new__(AutoClicker)
        bot.stop_event = threading.Event()
        bot._interruptible_sleep = Mock()
        def stopped_capture(**kwargs):
            bot.stop_event.set()
            return frame.copy(), (0, 0)
        bot._capture_screen_bgr = stopped_capture
        self.assertIsNone(bot._verify_merchant_purchase_target(frame, (678, 387)))

    def verify(self, before, after, target_sets, stopped=False):
        bot = AutoClicker.__new__(AutoClicker)
        bot.stop_event = threading.Event()
        if stopped:
            bot.stop_event.set()
        bot._interruptible_sleep = Mock()
        bot._capture_screen_bgr = Mock(return_value=(after, (0, 0)))
        with patch("buzzbot_app.mysterious_merchant_screen_is_visible", return_value=True), patch(
            "buzzbot_app.detect_mysterious_merchant_non_gem_offer_targets", side_effect=target_sets
        ):
            return bot._verify_merchant_purchase_target(before, (370, 387)), bot

    def test_same_resource_price_requires_a_fresh_frame(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        result, bot = self.verify(frame, frame.copy(), [[(370, 387)], [(370, 387)]])
        self.assertIsNotNone(result)
        bot._capture_screen_bgr.assert_called_once_with(force=True)

    def test_offer_moved_by_scroll_is_not_clicked_at_old_coordinate(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        result, _ = self.verify(frame, frame.copy(), [[(370, 387)], [(370, 269)]])
        self.assertIsNone(result)

    def test_changed_price_is_not_clicked_even_when_button_stays_in_place(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        changed = frame.copy()
        changed[369:405, 275:465] = 255
        result, _ = self.verify(frame, changed, [[(370, 387)], [(370, 387)]])
        self.assertIsNone(result)

    def test_price_without_allowed_resource_is_not_clicked(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        result, _ = self.verify(frame, frame.copy(), [[(370, 387)], []])
        self.assertIsNone(result)

    def test_stop_during_confirmation_prevents_purchase(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        result, bot = self.verify(frame, frame.copy(), [[(370, 387)]], stopped=True)
        self.assertIsNone(result)
        bot._capture_screen_bgr.assert_not_called()


if __name__ == "__main__":
    unittest.main()
