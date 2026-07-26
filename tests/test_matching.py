import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from buzzbot.matching import (
    TemplateCache,
    detect_alliance_marked_project_target,
    detect_blank_webview_close_target,
    detect_collective_tutorial_continue_target,
    detect_finished_healing_target,
    detect_login_saved_account_continue_target,
    detect_login_session_expired_ok_target,
    detect_prize_hunt_squad_confirmation_target,
    detect_radar_card_action_target,
    detect_radar_notification_targets,
    detect_radar_world_action_target,
    healing_auto_fill_is_checked,
    healing_number_editor_is_open,
    healing_selection_is_empty,
    imread_unicode,
    radar_marker_has_notification,
    zombie_camp_checkbox_is_checked,
)


class UnicodeImageReadTests(unittest.TestCase):
    def test_reads_png_from_non_ascii_windows_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_dir = Path(temp_dir) / "Русские шаблоны"
            image_dir.mkdir()
            image_path = image_dir / "кнопка.png"
            source = np.full((12, 18, 3), (15, 80, 220), dtype=np.uint8)
            success, encoded = cv2.imencode(".png", source)
            self.assertTrue(success)
            encoded.tofile(image_path)

            color = imread_unicode(image_path)
            gray = TemplateCache().get_gray(str(image_path))

            self.assertEqual(color.shape, source.shape)
            self.assertEqual(gray.shape, source.shape[:2])

    def test_missing_image_returns_none(self):
        self.assertIsNone(imread_unicode("missing-template.png"))


class DynamicGameControlTests(unittest.TestCase):
    def test_detects_expired_login_ok_button_only(self):
        frame = np.full((720, 1280, 3), (55, 70, 90), dtype=np.uint8)
        cv2.rectangle(frame, (320, 165), (960, 575), (120, 135, 150), thickness=-1)
        cv2.rectangle(frame, (507, 484), (773, 530), (35, 185, 245), thickness=-1)

        self.assertEqual(detect_login_session_expired_ok_target(frame), (640, 508))

        no_dialog = np.full((720, 1280, 3), (55, 70, 90), dtype=np.uint8)
        cv2.circle(no_dialog, (550, 550), 45, (35, 185, 245), thickness=-1)
        self.assertIsNone(detect_login_session_expired_ok_target(no_dialog))

    def test_detects_saved_igg_account_continue_button(self):
        frame = np.full((720, 1280, 3), 245, dtype=np.uint8)
        frame[90:274, 238:1043] = (70, 70, 70)
        frame[294:360, 238:1043] = (45, 205, 255)
        frame[379:445, 238:1043] = (215, 215, 215)

        self.assertEqual(
            detect_login_saved_account_continue_target(frame),
            (640, 326),
        )

        frame[294:360, 238:1043] = (215, 215, 215)
        self.assertIsNone(detect_login_saved_account_continue_target(frame))

    def test_detects_blank_login_webview_close_button_only(self):
        blank_webview = np.full((720, 1280, 3), 255, dtype=np.uint8)
        cv2.line(blank_webview, (1234, 22), (1258, 46), (115, 115, 115), 3)
        cv2.line(blank_webview, (1258, 22), (1234, 46), (115, 115, 115), 3)

        self.assertEqual(
            detect_blank_webview_close_target(blank_webview),
            (1246, 34),
        )
        self.assertIsNone(
            detect_blank_webview_close_target(np.full((720, 1280, 3), 255, dtype=np.uint8))
        )
        self.assertIsNone(
            detect_blank_webview_close_target(np.full((720, 1280, 3), 60, dtype=np.uint8))
        )

    def test_blank_login_webview_target_scales_to_device(self):
        blank_webview = np.full((360, 640, 3), 255, dtype=np.uint8)
        cv2.line(blank_webview, (617, 11), (629, 23), (115, 115, 115), 2)
        cv2.line(blank_webview, (629, 11), (617, 23), (115, 115, 115), 2)
        self.assertEqual(
            detect_blank_webview_close_target(blank_webview),
            (623, 17),
        )

    def test_detects_collective_tutorial_overlay_only(self):
        frame = np.full((720, 1280, 3), (80, 105, 75), dtype=np.uint8)
        frame[560:720] = (35, 38, 42)
        cv2.rectangle(frame, (930, 160), (1260, 570), (180, 25, 210), thickness=-1)

        self.assertEqual(
            detect_collective_tutorial_continue_target(frame),
            (640, 650),
        )

        no_dialog = frame.copy()
        no_dialog[560:720] = (120, 140, 100)
        self.assertIsNone(detect_collective_tutorial_continue_target(no_dialog))

        later_page = frame.copy()
        later_page[130:590, 870:1280] = (80, 105, 75)
        later_page[560:720] = (20, 22, 24)
        self.assertEqual(
            detect_collective_tutorial_continue_target(later_page),
            (640, 650),
        )

    def test_detects_prize_hunt_squad_confirmation_only(self):
        frame = np.full((720, 1280, 3), (70, 90, 105), dtype=np.uint8)
        cv2.rectangle(frame, (315, 160), (965, 215), (45, 70, 95), thickness=-1)
        cv2.rectangle(frame, (350, 215), (930, 475), (145, 160, 175), thickness=-1)
        cv2.rectangle(frame, (640, 480), (930, 535), (25, 185, 245), thickness=-1)

        self.assertEqual(
            detect_prize_hunt_squad_confirmation_target(frame),
            (784, 508),
        )
        self.assertIsNone(
            detect_prize_hunt_squad_confirmation_target(
                np.full((720, 1280, 3), (70, 90, 105), dtype=np.uint8)
            )
        )

        scaled = cv2.resize(frame, (640, 360), interpolation=cv2.INTER_AREA)
        self.assertEqual(
            detect_prize_hunt_squad_confirmation_target(scaled),
            (392, 254),
        )

    def test_detects_marked_alliance_project_and_ignores_other_red_shapes(self):
        frame = np.full((720, 1280, 3), (45, 50, 55), dtype=np.uint8)
        cv2.circle(frame, (474, 263), 7, (10, 25, 230), thickness=-1)
        cv2.rectangle(frame, (650, 470), (675, 475), (10, 25, 230), thickness=-1)
        cv2.circle(frame, (1210, 55), 7, (10, 25, 230), thickness=-1)

        self.assertEqual(
            detect_alliance_marked_project_target(frame),
            (419, 263),
        )

    def test_alliance_marker_target_scales_back_to_the_device_frame(self):
        frame = np.full((360, 640, 3), (45, 50, 55), dtype=np.uint8)
        cv2.circle(frame, (237, 132), 4, (10, 25, 230), thickness=-1)

        target = detect_alliance_marked_project_target(frame)

        self.assertIsNotNone(target)
        self.assertTrue(205 <= target[0] <= 215)
        self.assertTrue(128 <= target[1] <= 136)

    def test_detects_radar_notification_dots_and_targets_the_markers(self):
        frame = np.full((720, 1280, 3), (55, 70, 75), dtype=np.uint8)
        cv2.circle(frame, (700, 200), 8, (10, 20, 200), thickness=-1)
        cv2.circle(frame, (720, 325), 8, (10, 20, 200), thickness=-1)

        self.assertEqual(
            detect_radar_notification_targets(frame),
            [(676, 230), (696, 356)],
        )

    def test_radar_marker_requires_a_notification_dot(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        marker_bbox = (630, 190, 90, 100)
        cv2.circle(frame, (700, 200), 8, (10, 20, 200), thickness=-1)

        self.assertTrue(radar_marker_has_notification(frame, marker_bbox))
        self.assertFalse(radar_marker_has_notification(frame, (480, 170, 90, 100)))

    def test_detects_enabled_radar_card_and_world_buttons(self):
        frame = np.full((720, 1280, 3), (45, 55, 65), dtype=np.uint8)
        self.assertIsNone(detect_radar_card_action_target(frame))
        self.assertIsNone(detect_radar_world_action_target(frame))

        cv2.rectangle(frame, (112, 597), (376, 645), (25, 185, 245), thickness=-1)
        cv2.rectangle(frame, (855, 496), (1081, 543), (25, 185, 245), thickness=-1)
        self.assertEqual(detect_radar_card_action_target(frame), (244, 621))
        world_target = detect_radar_world_action_target(frame)
        self.assertIsNotNone(world_target)
        self.assertTrue(940 <= world_target[0] <= 990)
        self.assertTrue(510 <= world_target[1] <= 535)

    def test_detects_only_checked_game_options(self):
        frame = np.full((720, 1280, 3), (35, 45, 55), dtype=np.uint8)
        self.assertFalse(zombie_camp_checkbox_is_checked(frame))
        self.assertFalse(healing_auto_fill_is_checked(frame))

        cv2.line(frame, (812, 514), (818, 523), (20, 210, 80), thickness=3)
        cv2.line(frame, (818, 523), (828, 509), (20, 210, 80), thickness=3)
        cv2.line(frame, (805, 676), (810, 683), (220, 220, 220), thickness=3)
        cv2.line(frame, (810, 683), (820, 670), (220, 220, 220), thickness=3)
        self.assertTrue(zombie_camp_checkbox_is_checked(frame))
        self.assertTrue(healing_auto_fill_is_checked(frame))

    def test_healing_checkbox_border_is_not_mistaken_for_checkmark(self):
        frame = np.full((720, 1280, 3), (35, 45, 55), dtype=np.uint8)
        cv2.rectangle(frame, (797, 662), (826, 690), (220, 220, 220), thickness=2)

        self.assertFalse(healing_auto_fill_is_checked(frame))

    def test_detects_healing_numeric_editor_only_with_bright_footer(self):
        frame = np.full((720, 1280, 3), (35, 45, 55), dtype=np.uint8)
        self.assertFalse(healing_number_editor_is_open(frame))

        frame[616:720, :] = (250, 250, 250)
        self.assertTrue(healing_number_editor_is_open(frame))

    def test_confirms_empty_healing_selection_only_with_disabled_button(self):
        frame = np.full((720, 1280, 3), (35, 45, 55), dtype=np.uint8)
        frame[592:642, 900:1155] = (70, 70, 70)
        self.assertTrue(healing_selection_is_empty(frame))

        selected = frame.copy()
        selected[160:185, 765:1010] = (35, 180, 55)
        self.assertFalse(healing_selection_is_empty(selected))

        enabled_button = frame.copy()
        enabled_button[592:642, 900:1155] = (30, 180, 240)
        self.assertFalse(healing_selection_is_empty(enabled_button))

    def test_detects_finished_healing_portrait_cluster(self):
        frame = np.full((720, 1280, 3), (55, 70, 75), dtype=np.uint8)
        for left in (238, 262, 286):
            cv2.rectangle(
                frame,
                (left, 192),
                (left + 23, 231),
                (15, 25, 220),
                thickness=3,
            )
        cv2.rectangle(
            frame,
            (608, 244),
            (635, 275),
            (15, 25, 220),
            thickness=3,
        )

        self.assertEqual(detect_finished_healing_target(frame), (274, 212))

    def test_finished_healing_target_rejects_isolated_red_controls(self):
        frame = np.full((720, 1280, 3), (55, 70, 75), dtype=np.uint8)
        cv2.rectangle(
            frame,
            (608, 244),
            (635, 283),
            (15, 25, 220),
            thickness=3,
        )
        cv2.circle(frame, (700, 200), 10, (15, 25, 220), thickness=-1)

        self.assertIsNone(detect_finished_healing_target(frame))

    def test_finished_healing_target_scales_to_device_frame(self):
        frame = np.full((720, 1280, 3), (55, 70, 75), dtype=np.uint8)
        for left in (405, 429, 453):
            cv2.rectangle(
                frame,
                (left, 314),
                (left + 23, 353),
                (15, 25, 220),
                thickness=3,
            )
        scaled = cv2.resize(frame, (640, 360), interpolation=cv2.INTER_AREA)

        target = detect_finished_healing_target(scaled)
        self.assertIsNotNone(target)
        self.assertTrue(219 <= target[0] <= 221)
        self.assertTrue(166 <= target[1] <= 168)

    def test_detects_single_bronze_finished_healing_marker(self):
        frame = np.full((720, 1280, 3), (70, 70, 70), dtype=np.uint8)
        cv2.rectangle(
            frame,
            (725, 136),
            (766, 177),
            (35, 80, 145),
            thickness=3,
        )

        self.assertEqual(detect_finished_healing_target(frame), (746, 157))


if __name__ == "__main__":
    unittest.main()
