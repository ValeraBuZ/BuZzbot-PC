from pathlib import Path
import unittest

import cv2
import numpy as np

from buzzbot.matching import detect_shop_radial_action_target, imread_unicode


FIXTURES = Path(__file__).parent / 'assets/merchant'
ASSETS = Path(__file__).parents[1] / 'buzzbot/assets/merchant'


class MerchantScaleFollowupTests(unittest.TestCase):
    def test_live_large_menu_selects_ordinary_shop_instead_of_armory_or_beast(self):
        frame = imread_unicode(FIXTURES / 'large_shop_radial.png')
        target = detect_shop_radial_action_target(frame, (395, 396))
        self.assertIsNotNone(target)
        self.assertLess(np.linalg.norm(np.array(target) - (326, 535)), 5)
        self.assertLess(target[0], 380)  # Armory is x=440; Beast Shop is x=540.

    def test_visible_armory_and_beast_shop_cannot_replace_hidden_ordinary_action(self):
        frame = imread_unicode(FIXTURES / 'large_shop_radial.png')
        frame[492:609, 265:386] = 0
        self.assertIsNone(detect_shop_radial_action_target(frame, (395, 396)))

    def test_unselected_shop_facade_is_not_a_radial_menu(self):
        frame = imread_unicode(FIXTURES / 'unselected_shop.png')
        self.assertIsNone(detect_shop_radial_action_target(frame, (532, 351)))

    def test_absent_or_unrelated_title_blocks_large_action_label(self):
        frame = imread_unicode(FIXTURES / 'large_shop_radial.png')
        frame[230:278] = 0
        self.assertIsNone(detect_shop_radial_action_target(frame, (395, 396)))
        repair = imread_unicode(FIXTURES / 'equipment_repair.jpg')
        frame[:] = 0
        height, width = repair.shape[:2]
        frame[250:250 + height, 400:400 + width] = repair
        self.assertIsNone(detect_shop_radial_action_target(frame, (480, 340)))

    @staticmethod
    def labelled_frame(title_scale, action_scale, *, action_x=580):
        frame = np.full((720, 1280, 3), 35, dtype=np.uint8)
        for name, scale, center in (
            ('merchant_building_title.png', title_scale, (630, 235)),
            ('merchant_shop_action_label.png', action_scale, (action_x, 545)),
        ):
            template = imread_unicode(ASSETS / name)
            template = cv2.resize(template, None, fx=scale, fy=scale)
            height, width = template.shape[:2]
            left, top = center[0] - width // 2, center[1] - height // 2
            frame[top:top + height, left:left + width] = template
        return frame

    def test_title_and_action_must_have_one_coherent_ui_scale(self):
        for title_scale, action_scale in ((1.3, 1.0), (1.0, 1.3)):
            with self.subTest(title_scale=title_scale, action_scale=action_scale):
                frame = self.labelled_frame(title_scale, action_scale)
                self.assertIsNone(detect_shop_radial_action_target(frame, (640, 360)))

    def test_matched_scale_also_scales_label_to_button_distance(self):
        for scale in (1.0, 1.3):
            with self.subTest(scale=scale):
                frame = self.labelled_frame(scale, scale)
                target = detect_shop_radial_action_target(frame, (640, 360))
                self.assertIsNotNone(target)
                self.assertLessEqual(abs(target[0] - 580), 1)
                self.assertLessEqual(abs(target[1] - (545 - 40 * scale)), 1)

    def test_identical_word_to_the_right_is_not_the_ordinary_shop_action(self):
        for scale in (1.0, 1.3):
            with self.subTest(scale=scale):
                frame = self.labelled_frame(scale, scale, action_x=780)
                self.assertIsNone(detect_shop_radial_action_target(frame, (640, 360)))

    def test_display_scaling_keeps_large_menu_selection(self):
        frame = imread_unicode(FIXTURES / 'large_shop_radial.png')
        for scale in (0.75, 1.5):
            with self.subTest(scale=scale):
                resized = cv2.resize(frame, (round(1280 * scale), round(720 * scale)))
                target = detect_shop_radial_action_target(resized, (395 * scale, 396 * scale))
                self.assertIsNotNone(target)
                self.assertLess(np.linalg.norm(np.array(target) - (326 * scale, 535 * scale)), 5)


if __name__ == '__main__':
    unittest.main()
