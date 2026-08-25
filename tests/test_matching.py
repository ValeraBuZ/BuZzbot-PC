import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from buzzbot.matching import (
    TemplateCache,
    detect_alliance_marked_project_target,
    detect_back_confirmation_cancel_target,
    detect_blank_webview_close_target,
    detect_camped_march_card_targets,
    detect_collective_tutorial_continue_target,
    detect_commander_profile_back_target,
    detect_finished_healing_target,
    detect_game_event_overlay_close_target,
    detect_igg_game_login_ok_target,
    detect_igg_id_selection_target,
    detect_login_saved_account_continue_target,
    detect_account_settings_back_target,
    detect_account_details_close_target,
    detect_settings_close_target,
    detect_login_session_expired_ok_target,
    detect_prize_hunt_squad_confirmation_target,
    detect_radar_card_action_target,
    detect_radar_notification_targets,
    detect_radar_world_action_target,
    detect_lowest_stamina_refill_target,
    detect_march_retreat_target,
    detect_stamina_refill_target,
    healing_auto_fill_is_checked,
    healing_number_editor_is_open,
    healing_selection_is_empty,
    healing_troop_form_is_visible,
    imread_unicode,
    radar_category_has_notification,
    radar_marker_has_notification,
    stamina_dialog_is_visible,
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
    def test_detects_igg_id_selection_webview(self):
        frame = np.full((720, 1280, 3), 250, dtype=np.uint8)
        cv2.rectangle(frame, (0, 0), (1279, 67), (238, 238, 238), thickness=-1)
        cv2.line(frame, (42, 20), (27, 34), (55, 55, 55), thickness=4)
        cv2.line(frame, (27, 34), (42, 48), (55, 55, 55), thickness=4)
        cv2.line(frame, (1234, 21), (1257, 47), (100, 100, 100), thickness=3)
        cv2.line(frame, (1257, 21), (1234, 47), (100, 100, 100), thickness=3)
        cv2.putText(frame, "Select IGG ID", (535, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (35, 35, 35), 2)
        cv2.rectangle(frame, (239, 131), (1041, 192), (215, 215, 215), thickness=1)
        cv2.putText(frame, "IGG ID", (263, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (45, 45, 45), 2)
        cv2.putText(frame, "Create new IGG ID", (836, 235), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 125, 0), 2)

        self.assertEqual(detect_igg_id_selection_target(frame), (640, 162))
        self.assertEqual(
            detect_igg_id_selection_target(cv2.resize(frame, (640, 360))),
            (320, 81),
        )
        self.assertIsNone(detect_igg_id_selection_target(np.full_like(frame, 250)))

    def test_detects_blocking_game_event_overlay_close(self):
        frame = np.full((720, 1280, 3), (25, 30, 35), dtype=np.uint8)
        cv2.rectangle(frame, (150, 70), (1130, 570), (35, 95, 150), thickness=-1)
        cv2.line(frame, (1136, 95), (1168, 129), (45, 180, 220), thickness=7)
        cv2.line(frame, (1168, 95), (1136, 129), (45, 180, 220), thickness=7)
        cv2.rectangle(frame, (473, 580), (807, 636), (45, 180, 235), thickness=-1)

        self.assertEqual(detect_game_event_overlay_close_target(frame), (1152, 112))
        self.assertIsNone(
            detect_game_event_overlay_close_target(np.full_like(frame, (25, 30, 35)))
        )

    def test_detects_final_igg_game_confirmation(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        cv2.rectangle(frame, (320, 164), (960, 574), (205, 205, 205), thickness=-1)
        cv2.rectangle(frame, (363, 484), (629, 533), (80, 105, 125), thickness=-1)
        cv2.rectangle(frame, (652, 484), (917, 533), (45, 185, 240), thickness=-1)

        self.assertEqual(detect_igg_game_login_ok_target(frame), (784, 508))
        self.assertIsNone(detect_igg_game_login_ok_target(np.zeros_like(frame)))

        lighter_overlay = frame.copy()
        lighter_overlay[:150, :] = 50
        self.assertEqual(detect_igg_game_login_ok_target(lighter_overlay), (784, 508))

    @staticmethod
    def stamina_dialog_frame(width=1280, height=720):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        cv2.rectangle(frame, (1030, 74), (1085, 120), (0, 150, 210), thickness=-1)
        cv2.rectangle(frame, (210, 160), (305, 245), (20, 180, 40), thickness=-1)
        for x1, y1, x2, y2 in (
            (868, 326, 1068, 370),
            (868, 433, 1068, 477),
            (868, 539, 1068, 581),
        ):
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 180, 255), thickness=-1)
        cv2.rectangle(frame, (210, 285), (305, 385), (20, 180, 40), thickness=-1)
        if (width, height) != (1280, 720):
            frame = cv2.resize(frame, (width, height))
        return frame

    def test_detects_safe_50_stamina_item(self):
        self.assertTrue(stamina_dialog_is_visible(self.stamina_dialog_frame()))
        self.assertEqual(
            detect_stamina_refill_target(self.stamina_dialog_frame()),
            (968, 348),
        )

    def test_detects_100_and_500_stamina_items(self):
        frame = self.stamina_dialog_frame()

        self.assertEqual(detect_stamina_refill_target(frame, 100), (968, 454))
        self.assertEqual(detect_stamina_refill_target(frame, 500), (968, 559))

    def test_skips_exhausted_stamina_item_button(self):
        frame = self.stamina_dialog_frame()
        cv2.rectangle(frame, (850, 324), (1090, 372), (85, 85, 85), thickness=-1)

        self.assertIsNone(detect_stamina_refill_target(frame, 50))
        self.assertEqual(detect_stamina_refill_target(frame, 100), (968, 454))

    def test_detects_lowest_visible_button_after_1000_scroll(self):
        frame = self.stamina_dialog_frame()
        cv2.rectangle(frame, (868, 600), (1068, 638), (0, 180, 255), thickness=-1)

        self.assertEqual(detect_lowest_stamina_refill_target(frame), (968, 620))

    def test_scales_stamina_item_target(self):
        self.assertEqual(
            detect_stamina_refill_target(self.stamina_dialog_frame(640, 360)),
            (484, 174),
        )

    def test_rejects_single_generic_gold_button(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        cv2.rectangle(frame, (868, 326), (1068, 370), (0, 180, 255), thickness=-1)

        self.assertIsNone(detect_stamina_refill_target(frame))
        self.assertFalse(stamina_dialog_is_visible(frame))

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

    def test_detects_account_settings_back_button_only(self):
        frame = np.full((720, 1280, 3), 160, dtype=np.uint8)
        frame[86:668, 133:1147] = (35, 35, 35)
        frame[594:643, 507:773] = (45, 180, 235)

        self.assertEqual(detect_account_settings_back_target(frame), (640, 618))

        frame[594:643, 507:773] = (35, 35, 35)
        self.assertIsNone(detect_account_settings_back_target(frame))

    def test_detects_outer_account_details_close_button(self):
        frame = np.full((720, 1280, 3), (35, 35, 35), dtype=np.uint8)
        for top, bottom in ((158, 191), (229, 263), (371, 406)):
            frame[top:bottom, 950:1130] = (45, 180, 235)

        self.assertEqual(detect_account_details_close_target(frame), (1133, 43))

        frame[229:263, 950:1130] = (35, 35, 35)
        self.assertIsNone(detect_account_details_close_target(frame))

    def test_detects_root_settings_close_button(self):
        frame = np.full((720, 1280, 3), (25, 25, 25), dtype=np.uint8)
        for left, right in ((188, 387), (430, 629), (670, 869), (910, 1110)):
            frame[118:263, left:right] = (65, 80, 95)

        self.assertEqual(detect_settings_close_target(frame), (1133, 43))

        frame[118:263, 670:869] = (25, 25, 25)
        self.assertIsNone(detect_settings_close_target(frame))

    def test_detects_commander_profile_back_button(self):
        frame = np.full((720, 1280, 3), (130, 130, 130), dtype=np.uint8)
        frame[26:286, 808:1274] = (35, 35, 35)
        cv2.circle(frame, (47, 45), 28, (30, 150, 220), thickness=-1)

        self.assertEqual(detect_commander_profile_back_target(frame), (47, 45))

        frame[26:286, 808:1274] = (130, 130, 130)
        self.assertIsNone(detect_commander_profile_back_target(frame))

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

    def test_detects_radar_category_notification_for_matching_task(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        cv2.circle(frame, (1249, 141), 8, (10, 20, 200), thickness=-1)

        self.assertTrue(radar_category_has_notification(frame, "radar_quick"))
        self.assertFalse(radar_category_has_notification(frame, "radar_marches"))
        self.assertFalse(radar_category_has_notification(frame, "radar_rewards"))

        cv2.circle(frame, (1249, 246), 8, (10, 20, 200), thickness=-1)
        self.assertTrue(radar_category_has_notification(frame, "radar_marches"))

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

    def test_detects_camped_march_cards_but_not_other_statuses(self):
        frame = np.full((720, 1280, 3), (35, 45, 55), dtype=np.uint8)
        cv2.rectangle(frame, (1172, 260), (1268, 329), (180, 180, 220), thickness=2)
        cv2.rectangle(frame, (1240, 301), (1259, 319), (220, 180, 20), thickness=-1)
        cv2.rectangle(frame, (1240, 371), (1259, 389), (20, 20, 220), thickness=-1)

        self.assertEqual(detect_camped_march_card_targets(frame), [(1218, 292)])

    def test_rejects_cyan_world_text_without_march_card(self):
        frame = np.full((720, 1280, 3), (35, 45, 55), dtype=np.uint8)
        cv2.rectangle(frame, (1240, 231), (1259, 249), (220, 180, 20), thickness=-1)

        self.assertEqual(detect_camped_march_card_targets(frame), [])

    def test_detects_selected_march_retreat_action(self):
        frame = np.full((720, 1280, 3), (35, 45, 55), dtype=np.uint8)
        self.assertIsNone(detect_march_retreat_target(frame))

        cv2.circle(frame, (582, 456), 38, (40, 145, 205), thickness=-1)
        cv2.circle(frame, (696, 456), 38, (40, 145, 205), thickness=-1)
        target = detect_march_retreat_target(frame)
        self.assertIsNotNone(target)
        self.assertLessEqual(abs(target[0] - 696), 8)
        self.assertLessEqual(abs(target[1] - 456), 8)

    def test_detects_moved_retreat_action_pair(self):
        frame = np.full((720, 1280, 3), (35, 45, 55), dtype=np.uint8)
        cv2.circle(frame, (445, 519), 28, (40, 145, 205), thickness=-1)
        cv2.circle(frame, (531, 519), 28, (40, 145, 205), thickness=-1)

        target = detect_march_retreat_target(frame)
        self.assertIsNotNone(target)
        self.assertLessEqual(abs(target[0] - 531), 8)
        self.assertLessEqual(abs(target[1] - 519), 8)

    def test_rejects_asymmetric_world_map_circle_pair(self):
        frame = np.full((720, 1280, 3), (35, 45, 55), dtype=np.uint8)
        cv2.circle(frame, (775, 502), 35, (40, 145, 205), thickness=-1)
        cv2.circle(frame, (841, 512), 43, (40, 145, 205), thickness=-1)

        self.assertIsNone(detect_march_retreat_target(frame))

    def test_detects_back_confirmation_cancel_without_matching_world_map(self):
        frame = np.full((720, 1280, 3), (35, 45, 55), dtype=np.uint8)
        self.assertIsNone(detect_back_confirmation_cancel_target(frame))

        frame[210:470, 330:950] = (210, 215, 220)
        frame[482:535, 360:632] = (80, 95, 110)
        frame[482:535, 650:920] = (20, 180, 245)
        self.assertEqual(detect_back_confirmation_cancel_target(frame), (495, 509))

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

    def test_detects_healing_form_with_disabled_heal_button(self):
        frame = np.full((720, 1280, 3), (35, 45, 55), dtype=np.uint8)
        cv2.rectangle(
            frame,
            (230, 140),
            (630, 380),
            (20, 30, 220),
            thickness=-1,
        )
        cv2.circle(
            frame,
            (275, 570),
            52,
            (20, 30, 220),
            thickness=-1,
        )
        frame[592:642, 900:1155] = (70, 70, 70)

        self.assertTrue(healing_troop_form_is_visible(frame))

        empty_after_collection = frame.copy()
        cv2.circle(
            empty_after_collection,
            (275, 570),
            52,
            (30, 180, 240),
            thickness=-1,
        )
        self.assertTrue(healing_troop_form_is_visible(empty_after_collection))

        alternate_troop = np.full(
            (720, 1280, 3),
            (35, 45, 55),
            dtype=np.uint8,
        )
        cv2.circle(
            alternate_troop,
            (275, 570),
            52,
            (40, 150, 40),
            thickness=-1,
        )
        alternate_troop[658:705, 575:1160] = (30, 180, 240)
        alternate_troop[592:642, 900:1155] = (70, 70, 70)
        self.assertTrue(healing_troop_form_is_visible(alternate_troop))

        selected = frame.copy()
        cv2.circle(
            selected,
            (275, 570),
            52,
            (30, 180, 240),
            thickness=-1,
        )
        selected[592:642, 900:1155] = (30, 180, 240)
        self.assertTrue(healing_troop_form_is_visible(selected))

        unrelated = np.full((720, 1280, 3), (35, 45, 55), dtype=np.uint8)
        cv2.rectangle(
            unrelated,
            (230, 140),
            (630, 380),
            (20, 30, 220),
            thickness=-1,
        )
        self.assertFalse(healing_troop_form_is_visible(unrelated))

    def test_detects_finished_healing_portrait_cluster(self):
        frame = np.full((720, 1280, 3), (55, 70, 75), dtype=np.uint8)
        for left in (238, 262, 286):
            cv2.rectangle(
                frame,
                (left + 3, 195),
                (left + 20, 228),
                (110, 35, 90),
                thickness=-1,
            )
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
                (left + 3, 317),
                (left + 20, 350),
                (110, 35, 90),
                thickness=-1,
            )
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

    def test_rejects_single_dark_wounded_troop_marker(self):
        frame = np.full((720, 1280, 3), (70, 70, 70), dtype=np.uint8)
        cv2.rectangle(
            frame,
            (728, 139),
            (763, 174),
            (110, 35, 90),
            thickness=-1,
        )
        cv2.rectangle(
            frame,
            (725, 136),
            (766, 177),
            (45, 95, 130),
            thickness=3,
        )

        self.assertIsNone(detect_finished_healing_target(frame))

    def test_detects_single_red_finished_healing_marker_without_purple(self):
        frame = np.full((720, 1280, 3), (70, 70, 70), dtype=np.uint8)
        cv2.rectangle(
            frame,
            (572, 276),
            (614, 316),
            (15, 25, 220),
            thickness=-1,
        )
        cv2.rectangle(
            frame,
            (578, 282),
            (608, 310),
            (45, 55, 65),
            thickness=-1,
        )

        self.assertEqual(detect_finished_healing_target(frame), (594, 296))

    def test_detects_white_medic_finished_healing_marker(self):
        frame = np.full((720, 1280, 3), (70, 70, 70), dtype=np.uint8)
        cv2.rectangle(
            frame,
            (574, 272),
            (616, 314),
            (35, 80, 145),
            thickness=-1,
        )
        cv2.circle(frame, (595, 293), 16, (225, 225, 225), thickness=-1)
        cv2.rectangle(
            frame,
            (592, 278),
            (598, 308),
            (20, 25, 220),
            thickness=-1,
        )
        cv2.rectangle(
            frame,
            (583, 290),
            (607, 296),
            (20, 25, 220),
            thickness=-1,
        )

        self.assertEqual(detect_finished_healing_target(frame), (596, 294))

    def test_rejects_bronze_wounded_troop_portrait_core(self):
        frame = np.full((720, 1280, 3), (70, 70, 70), dtype=np.uint8)
        cv2.rectangle(
            frame,
            (258, 230),
            (299, 279),
            (110, 35, 90),
            thickness=-1,
        )
        cv2.rectangle(
            frame,
            (268, 240),
            (289, 269),
            (35, 80, 145),
            thickness=-1,
        )

        self.assertIsNone(detect_finished_healing_target(frame))

    def test_finished_healing_target_rejects_oil_factory_palette(self):
        frame = np.full((720, 1280, 3), (45, 65, 75), dtype=np.uint8)
        for left in (238, 262, 286):
            cv2.rectangle(
                frame,
                (left, 120),
                (left + 23, 159),
                (15, 25, 220),
                thickness=3,
            )
            cv2.rectangle(
                frame,
                (left + 4, 124),
                (left + 19, 155),
                (35, 80, 145),
                thickness=-1,
            )

        self.assertIsNone(detect_finished_healing_target(frame))


if __name__ == "__main__":
    unittest.main()
