"""Purchases require observed currency icons on the selected merchant page."""

from pathlib import Path
import unittest

import cv2

from buzzbot.matching import (
    detect_mysterious_merchant_non_gem_offer_targets,
    detect_shop_merchant_tab_target,
    imread_unicode,
    mysterious_merchant_screen_is_visible,
)


ASSETS = Path(__file__).parent / "assets/merchant"


class MerchantCurrencyVerificationTests(unittest.TestCase):
    def frame(self, filename="resource_prices.png"):
        frame = imread_unicode(ASSETS / filename)
        self.assertIsNotNone(frame)
        return frame

    def test_real_food_and_wood_prices_are_selected_at_supported_resolutions(self):
        frame = self.frame()
        for size, expected in (
            ((1280, 720), [(678, 387), (986, 387), (370, 552)]),
            ((640, 360), [(339, 194), (493, 194), (185, 276)]),
            ((1920, 1080), [(1018, 580), (1480, 580), (556, 828)]),
        ):
            with self.subTest(size=size):
                resized = cv2.resize(frame, size)
                self.assertTrue(mysterious_merchant_screen_is_visible(resized))
                self.assertEqual(detect_mysterious_merchant_non_gem_offer_targets(resized), expected)

    def test_scrolled_real_resource_prices_keep_their_new_positions(self):
        frame = self.frame()
        frame[155:549, 145:1075] = frame[191:585, 145:1075].copy()
        frame[549:585, 145:1075] = (25, 25, 25)
        self.assertEqual(detect_mysterious_merchant_non_gem_offer_targets(frame),
                         [(678, 351), (986, 351), (370, 516)])

    def test_gold_bars_without_currency_icons_and_amounts_are_rejected(self):
        frame = self.frame()
        for x1, y1, x2, y2 in ((601, 369, 756, 406), (909, 369, 1064, 406), (293, 534, 448, 572)):
            frame[y1:y2, x1:x2] = (40, 170, 215)
        self.assertTrue(mysterious_merchant_screen_is_visible(frame))
        self.assertEqual(detect_mysterious_merchant_non_gem_offer_targets(frame), [])

    def test_amounts_without_recognized_resource_icons_are_rejected(self):
        frame = self.frame()
        for x1, y1, y2 in ((601, 369, 406), (909, 369, 406), (293, 534, 572)):
            frame[y1:y2, x1 + 3:x1 + 52] = (40, 170, 215)
        self.assertEqual(detect_mysterious_merchant_non_gem_offer_targets(frame), [])

    def test_resource_icons_without_visible_amounts_are_rejected(self):
        frame = self.frame()
        for x1, y1, y2 in ((601, 369, 406), (909, 369, 406), (293, 534, 572)):
            frame[y1:y2, x1 + 52:x1 + 150] = (40, 170, 215)
        self.assertEqual(detect_mysterious_merchant_non_gem_offer_targets(frame), [])

    def test_real_gem_prices_and_paid_footer_are_not_purchasable(self):
        for filename in ("merchant_grid.png", "free_refresh.png"):
            with self.subTest(filename=filename):
                frame = self.frame(filename)
                self.assertTrue(mysterious_merchant_screen_is_visible(frame))
                self.assertEqual(detect_mysterious_merchant_non_gem_offer_targets(frame), [])

    def test_vip_resources_do_not_become_merchant_offers(self):
        frame = self.frame("vip_grid.png")
        self.assertFalse(mysterious_merchant_screen_is_visible(frame))
        self.assertEqual(detect_mysterious_merchant_non_gem_offer_targets(frame), [])
        self.assertEqual(detect_shop_merchant_tab_target(frame), (68, 424))

    def test_stale_merchant_title_with_inactive_tab_is_not_a_merchant_page(self):
        frame = self.frame("vip_grid.png")
        merchant = self.frame()
        frame[55:98, 140:480] = merchant[55:98, 140:480]
        self.assertFalse(mysterious_merchant_screen_is_visible(frame))
        self.assertEqual(detect_mysterious_merchant_non_gem_offer_targets(frame), [])

    def test_active_tab_alone_does_not_override_another_shop_title(self):
        frame = self.frame("vip_grid.png")
        merchant = self.frame()
        frame[365:478, 15:125] = merchant[365:478, 15:125]
        self.assertFalse(mysterious_merchant_screen_is_visible(frame))
        self.assertEqual(detect_mysterious_merchant_non_gem_offer_targets(frame), [])


if __name__ == "__main__":
    unittest.main()
