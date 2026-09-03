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
    detect_equipment_report_close_target,
    detect_equipment_report_free_reward_target,
    detect_game_event_overlay_close_target,
    detect_merchant_shop_building_target,
    detect_merchant_shop_feature_target,
    detect_mysterious_merchant_absent_ok_target,
    equipment_report_screen_is_visible,
    detect_shop_selection_marker_target,
    detect_shop_radial_action_target,
    detect_igg_game_login_ok_target,
    detect_igg_id_selection_target,
    detect_login_saved_account_continue_target,
    mysterious_merchant_screen_is_visible,
    settlement_building_catalogue_is_visible,
    detect_account_settings_back_target,
    detect_account_details_close_target,
    detect_settings_close_target,
    detect_settlement_event_panel_collapse_target,
    detect_truck_personal_slot_target,
    detect_truck_active_detail_back_target,
    detect_truck_escort_confirmation_target,
    detect_truck_ready_collection_target,
    detect_truck_start_dispatch_target,
    detect_login_session_expired_ok_target,
    detect_prize_hunt_squad_confirmation_target,
    detect_processing_factory_target,
    detect_radar_card_action_target,
    detect_radar_deployment_prompt_target,
    detect_radar_squad_march_target,
    detect_radar_notification_targets,
    detect_research_action_target,
    research_branch_is_selected,
    research_progress_bar_is_active,
    research_radial_menu_is_visible,
    research_tree_progress_is_active,
    research_tree_is_visible,
    radar_overview_is_visible,
    detect_radar_pass_purchase_cancel_target,
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
    radar_card_has_active_countdown,
    radar_marker_has_notification,
    stamina_dialog_is_visible,
    truck_alliance_escort_is_visible,
    truck_arrival_reward_is_visible,
    truck_express_overview_is_visible,
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
    def test_detects_processing_factory_furnace_cluster(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        furnace_color = (0, 120, 255)
        for left, top in ((760, 480), (810, 460), (855, 500), (802, 525)):
            cv2.rectangle(frame, (left, top), (left + 36, top + 26), furnace_color, -1)

        target = detect_processing_factory_target(frame)

        self.assertIsNotNone(target)
        self.assertLess(abs(target[0] - 825), 12)
        self.assertLess(abs(target[1] - 527), 15)

    def test_processing_factory_requires_furnace_cluster(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        cv2.rectangle(frame, (760, 480), (796, 506), (0, 120, 255), -1)

        self.assertIsNone(detect_processing_factory_target(frame))

    def test_processing_factory_rejects_bottom_hud_cluster(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        for left, top in ((180, 630), (220, 610), (265, 640), (215, 675)):
            cv2.rectangle(frame, (left, top), (left + 36, top + 26), (0, 120, 255), -1)

        self.assertIsNone(detect_processing_factory_target(frame))

    def test_processing_factory_rejects_diagonal_shelter_wall_lights(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        furnace_color = (0, 120, 255)
        for left, top, width, height in (
            (838, 136, 57, 36),
            (825, 168, 19, 21),
            (781, 171, 47, 42),
            (749, 219, 27, 23),
        ):
            cv2.rectangle(
                frame,
                (left, top),
                (left + width - 1, top + height - 1),
                furnace_color,
                -1,
            )

        self.assertIsNone(detect_processing_factory_target(frame))

    @staticmethod
    def equipment_report_frame(active_cards=(460, 590, 723)):
        frame = np.full((720, 1280, 3), (18, 20, 22), dtype=np.uint8)
        cv2.rectangle(frame, (160, 35), (1119, 304), (190, 195, 200), -1)
        cv2.rectangle(frame, (155, 305), (1124, 699), (28, 30, 165), -1)
        cv2.rectangle(frame, (1071, 45), (1127, 99), (35, 175, 225), -1)
        for center_x in (460, 590, 723, 854, 985):
            color = (35, 175, 225) if center_x in active_cards else (105, 110, 115)
            cv2.rectangle(
                frame,
                (center_x - 50, 198),
                (center_x + 49, 293),
                color,
                8,
            )
        return frame

    def test_equipment_report_collects_only_illuminated_upper_rewards(self):
        frame = self.equipment_report_frame()

        self.assertTrue(equipment_report_screen_is_visible(frame))
        self.assertEqual(
            detect_equipment_report_free_reward_target(frame),
            (460, 245),
        )
        self.assertIsNone(detect_equipment_report_close_target(frame))

        cv2.rectangle(frame, (410, 198), (509, 293), (105, 110, 115), 8)
        self.assertEqual(
            detect_equipment_report_free_reward_target(frame),
            (590, 245),
        )

    def test_equipment_report_closes_only_after_free_rewards_are_gone(self):
        frame = self.equipment_report_frame(active_cards=())

        self.assertIsNone(detect_equipment_report_free_reward_target(frame))
        self.assertEqual(detect_equipment_report_close_target(frame), (1099, 72))
        self.assertEqual(
            detect_equipment_report_close_target(cv2.resize(frame, (640, 360))),
            (550, 36),
        )
        self.assertFalse(
            equipment_report_screen_is_visible(
                np.full_like(frame, (18, 20, 22))
            )
        )

    def test_detects_mysterious_merchant_away_dialog(self):
        frame = np.full((720, 1280, 3), (45, 50, 48), dtype=np.uint8)
        cv2.rectangle(frame, (330, 205), (950, 565), (155, 165, 175), -1)
        cv2.rectangle(frame, (507, 484), (773, 534), (35, 175, 235), -1)

        self.assertEqual(
            detect_mysterious_merchant_absent_ok_target(frame),
            (640, 509),
        )
        self.assertIsNone(
            detect_mysterious_merchant_absent_ok_target(
                np.full_like(frame, (45, 50, 48))
            )
        )

    def test_shop_action_detector_uses_gold_marker_above_building(self):
        marker_path = (
            Path(__file__).resolve().parents[1]
            / "img"
            / "system"
            / "merchant_catalog_selection_marker.jpg"
        )
        marker = cv2.imread(str(marker_path), cv2.IMREAD_COLOR)
        frame = np.full((720, 1280, 3), (60, 80, 65), dtype=np.uint8)
        resized = cv2.resize(marker, (78, 77), interpolation=cv2.INTER_CUBIC)
        frame[274:351, 677:755] = resized
        # A round bottom-HUD control must never win over the local Shop marker.
        cv2.circle(frame, (966, 644), 48, (190, 185, 165), thickness=-1)

        target = detect_shop_selection_marker_target(frame, (716, 423), marker)

        self.assertIsNotNone(target)
        self.assertLess(abs(target[0] - 716), 5)
        self.assertLess(abs(target[1] - 312), 5)

    def test_shop_radial_detector_selects_middle_action(self):
        frame = np.full((720, 1280, 3), (60, 80, 65), dtype=np.uint8)
        for center in ((711, 367), (879, 367), (711, 474), (879, 474)):
            cv2.ellipse(
                frame,
                center,
                (19, 14),
                0,
                0,
                360,
                (45, 225, 85),
                thickness=-1,
            )
        cv2.circle(frame, (795, 519), 24, (225, 215, 190), thickness=4)
        cv2.line(frame, (783, 519), (807, 519), (35, 35, 35), thickness=5)

        target = detect_shop_radial_action_target(frame, (800, 410))

        self.assertIsNotNone(target)
        self.assertLessEqual(abs(target[0] - 795), 2)
        self.assertLessEqual(abs(target[1] - 519), 2)

    def test_shop_radial_detector_tracks_catalogue_high_camera_position(self):
        frame = np.full((720, 1280, 3), (60, 80, 65), dtype=np.uint8)
        # Catalogue selection can leave Shop near the top of the settlement.
        # These coordinates mirror the live IGG 4 failure where the fixed
        # y>=280 mask removed the entire selected-building marker.
        for center in ((367, 148), (486, 148), (333, 176), (484, 230)):
            cv2.ellipse(
                frame,
                center,
                (14, 10),
                0,
                0,
                360,
                (45, 225, 85),
                thickness=-1,
            )
        cv2.circle(frame, (410, 275), 24, (225, 215, 190), thickness=4)
        cv2.line(frame, (398, 275), (422, 275), (35, 35, 35), thickness=5)

        target = detect_shop_radial_action_target(frame, (424, 194))

        self.assertIsNotNone(target)
        self.assertLessEqual(abs(target[0] - 410), 2)
        self.assertLessEqual(abs(target[1] - 275), 2)

    def test_shop_radial_detector_rejects_two_action_equipment_repair_menu(self):
        frame = np.full((720, 1280, 3), (60, 80, 65), dtype=np.uint8)
        for center in ((885, 315), (1037, 315), (885, 383), (1037, 383)):
            cv2.ellipse(
                frame,
                center,
                (19, 14),
                0,
                0,
                360,
                (45, 225, 85),
                thickness=-1,
            )
        cv2.circle(frame, (901, 445), 24, (225, 215, 190), thickness=4)
        cv2.circle(frame, (1031, 445), 24, (225, 215, 190), thickness=4)

        self.assertIsNone(detect_shop_radial_action_target(frame, (961, 349)))

    def test_merchant_shop_features_survive_isometric_camera_shift(self):
        template_path = (
            Path(__file__).resolve().parents[1]
            / "img"
            / "system"
            / "merchant_shop_building.jpg"
        )
        template = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
        self.assertIsNotNone(template)
        frame = np.full((720, 1280, 3), (60, 80, 65), dtype=np.uint8)
        height, width = template.shape[:2]
        source = np.float32(
            [[0, 0], [width, 0], [width, height], [0, height]]
        )
        destination = np.float32(
            [[430, 240], [603, 244], [598, 360], [426, 355]]
        )
        homography = cv2.getPerspectiveTransform(source, destination)
        warped = cv2.warpPerspective(template, homography, (1280, 720))
        mask = cv2.warpPerspective(
            np.full((height, width), 255, dtype=np.uint8),
            homography,
            (1280, 720),
        )
        frame[mask > 0] = warped[mask > 0]

        target, inliers = detect_merchant_shop_feature_target(frame, template)

        self.assertIsNotNone(target)
        self.assertGreaterEqual(inliers, 10)
        self.assertLess(abs(target[0] - 514), 10)
        self.assertLess(abs(target[1] - 300), 10)

    def test_merchant_shop_sign_requires_a_strong_exact_match(self):
        sign_path = Path(__file__).resolve().parents[1] / "img" / "system" / "merchant_shop_sign.jpg"
        sign = cv2.imread(str(sign_path), cv2.IMREAD_COLOR)
        self.assertIsNotNone(sign)
        frame = np.full((720, 1280, 3), 45, dtype=np.uint8)
        y, x = 280, 510
        frame[y:y + sign.shape[0], x:x + sign.shape[1]] = sign

        target, score = detect_merchant_shop_building_target(frame, sign)

        self.assertIsNotNone(target)
        self.assertGreaterEqual(score, 0.44)
        self.assertLess(abs(target[0] - (x + sign.shape[1] // 2)), 4)
        self.assertLess(abs(target[1] - (y + sign.shape[0] // 2 + 35)), 4)

    def test_merchant_shop_sign_rejects_unrelated_radial_screen(self):
        sign_path = Path(__file__).resolve().parents[1] / "img" / "system" / "merchant_shop_sign.jpg"
        sign = cv2.imread(str(sign_path), cv2.IMREAD_COLOR)
        frame = np.full((720, 1280, 3), (55, 90, 75), dtype=np.uint8)
        cv2.circle(frame, (480, 330), 65, (190, 190, 190), thickness=8)
        cv2.line(frame, (430, 280), (530, 380), (20, 20, 20), thickness=9)

        target, score = detect_merchant_shop_building_target(frame, sign)

        self.assertIsNone(target)
        self.assertLess(score, 0.44)

    def test_merchant_detector_rejects_building_catalogue_cards(self):
        hsv = np.full((720, 1280, 3), (20, 100, 100), dtype=np.uint8)
        hsv[90:590, 0:155] = (0, 100, 100)
        hsv[185:325, :] = (20, 100, 50)
        hsv[330:700, :] = (20, 20, 180)
        frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

        self.assertFalse(mysterious_merchant_screen_is_visible(frame))
        self.assertTrue(settlement_building_catalogue_is_visible(frame))

    def test_building_catalogue_detector_rejects_settlement(self):
        frame = np.full((720, 1280, 3), (20, 30, 25), dtype=np.uint8)

        self.assertFalse(settlement_building_catalogue_is_visible(frame))

    def test_merchant_detector_accepts_dark_offer_grid(self):
        hsv = np.full((720, 1280, 3), (20, 100, 100), dtype=np.uint8)
        hsv[90:590, 0:155] = (0, 100, 100)
        frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

        self.assertTrue(mysterious_merchant_screen_is_visible(frame))

    def test_detects_research_collect_or_confirm_button(self):
        frame = np.full((720, 1280, 3), (35, 40, 45), dtype=np.uint8)
        cv2.rectangle(frame, (855, 554), (1118, 604), (35, 180, 235), thickness=-1)

        self.assertEqual(detect_research_action_target(frame), (986, 579))
        self.assertEqual(
            detect_research_action_target(cv2.resize(frame, (640, 360))),
            (493, 289),
        )

    def test_research_action_detector_ignores_small_gold_decoration(self):
        frame = np.full((720, 1280, 3), (35, 40, 45), dtype=np.uint8)
        cv2.rectangle(frame, (1000, 560), (1050, 595), (35, 180, 235), thickness=-1)

        self.assertIsNone(detect_research_action_target(frame))

    def test_research_action_detector_ignores_tree_progress_ribbon(self):
        frame = np.full((720, 1280, 3), (35, 40, 45), dtype=np.uint8)
        # A right-edge tree node exposes a long gold strip that is clipped by
        # the action search area. It must not be accepted as Collect/Start.
        cv2.rectangle(frame, (848, 515), (1180, 561), (35, 180, 235), thickness=-1)

        self.assertIsNone(detect_research_action_target(frame))

    def test_detects_active_research_progress_bar(self):
        frame = np.full((720, 1280, 3), (35, 40, 45), dtype=np.uint8)
        cv2.rectangle(frame, (579, 406), (635, 413), (40, 210, 70), thickness=-1)
        cv2.rectangle(frame, (636, 406), (729, 413), (5, 5, 5), thickness=-1)

        self.assertTrue(research_progress_bar_is_active(frame))
        self.assertTrue(
            research_progress_bar_is_active(cv2.resize(frame, (640, 360)))
        )
        self.assertFalse(
            research_progress_bar_is_active(np.full_like(frame, (35, 40, 45)))
        )

    def test_research_radial_menu_requires_local_change(self):
        before = np.full((720, 1280, 3), (70, 85, 95), dtype=np.uint8)
        unrelated_animation = before.copy()
        unrelated_animation[40:180, 300:700] = (180, 80, 40)
        radial = before.copy()
        radial[365:450, 745:835] = (25, 170, 220)

        self.assertFalse(
            research_radial_menu_is_visible(before, unrelated_animation)
        )
        self.assertTrue(research_radial_menu_is_visible(before, radial))

    def test_research_tree_guard_is_branch_and_language_independent(self):
        tree = np.full((720, 1280, 3), (90, 110, 120), dtype=np.uint8)
        tree[90:650, 120:1160] = (35, 38, 42)
        tree[100:610, 35:110] = (30, 33, 36)
        settlement = np.full((720, 1280, 3), (85, 115, 90), dtype=np.uint8)

        self.assertTrue(research_tree_is_visible(tree))
        self.assertFalse(research_tree_is_visible(settlement))

    def test_research_branch_selection_uses_highlighted_side_tab(self):
        frame = np.full((720, 1280, 3), (35, 38, 42), dtype=np.uint8)
        cv2.rectangle(frame, (40, 125), (102, 215), (35, 155, 220), thickness=-1)
        cv2.rectangle(frame, (40, 255), (102, 345), (75, 75, 75), thickness=-1)

        self.assertTrue(research_branch_is_selected(frame, "economy"))
        self.assertFalse(research_branch_is_selected(frame, "war"))

        cv2.rectangle(frame, (40, 125), (102, 215), (75, 75, 75), thickness=-1)
        cv2.rectangle(frame, (40, 255), (102, 345), (35, 155, 220), thickness=-1)
        self.assertFalse(research_branch_is_selected(frame, "economy"))
        self.assertTrue(research_branch_is_selected(frame, "war"))

    def test_detects_active_countdown_in_open_research_tree(self):
        tree = np.full((720, 1280, 3), (90, 110, 120), dtype=np.uint8)
        tree[90:650, 120:1160] = (35, 38, 42)
        tree[100:610, 35:110] = (30, 33, 36)
        cv2.rectangle(tree, (430, 85), (790, 102), (5, 5, 5), thickness=-1)
        cv2.rectangle(tree, (432, 87), (485, 100), (35, 180, 235), thickness=-1)
        cv2.rectangle(tree, (800, 70), (944, 110), (35, 180, 235), thickness=-1)

        self.assertTrue(research_tree_progress_is_active(tree))

        tree[70:111, 800:945] = (35, 38, 42)
        self.assertFalse(research_tree_progress_is_active(tree))

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
        cv2.rectangle(frame, (150, 70), (1130, 570), (150, 80, 35), thickness=-1)
        cv2.line(frame, (1136, 95), (1168, 129), (45, 180, 220), thickness=7)
        cv2.line(frame, (1168, 95), (1136, 129), (45, 180, 220), thickness=7)
        cv2.rectangle(frame, (473, 580), (807, 636), (45, 180, 235), thickness=-1)

        self.assertEqual(detect_game_event_overlay_close_target(frame), (1152, 112))
        self.assertIsNone(
            detect_game_event_overlay_close_target(np.full_like(frame, (25, 30, 35)))
        )

    def test_detects_lower_blocking_game_event_overlay_close(self):
        frame = np.full((720, 1280, 3), (25, 30, 35), dtype=np.uint8)
        cv2.rectangle(frame, (150, 70), (1130, 570), (150, 80, 35), thickness=-1)
        cv2.line(frame, (1074, 149), (1108, 183), (45, 180, 220), thickness=7)
        cv2.line(frame, (1108, 149), (1074, 183), (45, 180, 220), thickness=7)
        cv2.rectangle(frame, (473, 580), (807, 636), (45, 180, 235), thickness=-1)

        self.assertEqual(detect_game_event_overlay_close_target(frame), (1091, 166))

    def test_event_calendar_is_not_a_blocking_overlay(self):
        frame = np.full((720, 1280, 3), (25, 30, 35), dtype=np.uint8)
        cv2.rectangle(frame, (280, 45), (1240, 660), (135, 175, 205), thickness=-1)
        cv2.rectangle(frame, (1020, 70), (1225, 220), (105, 155, 195), thickness=-1)
        cv2.rectangle(frame, (473, 580), (807, 636), (45, 180, 235), thickness=-1)

        self.assertIsNone(detect_game_event_overlay_close_target(frame))

    def test_detects_expanded_settlement_event_panel_toggle(self):
        frame = np.full((720, 1280, 3), (70, 80, 85), dtype=np.uint8)
        cv2.rectangle(frame, (451, 58), (474, 107), (25, 28, 30), thickness=-1)
        cv2.line(frame, (458, 74), (468, 82), (185, 190, 195), thickness=4)
        cv2.line(frame, (468, 82), (458, 90), (185, 190, 195), thickness=4)

        self.assertEqual(
            detect_settlement_event_panel_collapse_target(frame),
            (463, 83),
        )
        self.assertEqual(
            detect_settlement_event_panel_collapse_target(
                cv2.resize(frame, (640, 360))
            ),
            (232, 42),
        )

    def test_rejects_collapsed_settlement_event_panel_toggle(self):
        frame = np.full((720, 1280, 3), (70, 80, 85), dtype=np.uint8)
        cv2.rectangle(frame, (451, 58), (474, 107), (25, 28, 30), thickness=-1)
        cv2.line(frame, (468, 74), (458, 82), (185, 190, 195), thickness=4)
        cv2.line(frame, (458, 82), (468, 90), (185, 190, 195), thickness=4)

        self.assertIsNone(detect_settlement_event_panel_collapse_target(frame))

    def test_personal_truck_detector_ignores_alliance_plus(self):
        frame = np.full((720, 1280, 3), (55, 60, 58), dtype=np.uint8)
        for center_x, center_y in ((640, 190), (207, 410)):
            cv2.line(frame, (center_x - 28, center_y), (center_x + 28, center_y), (205, 205, 200), 12)
            cv2.line(frame, (center_x, center_y - 28), (center_x, center_y + 28), (205, 205, 200), 12)
        self.assertEqual(detect_truck_personal_slot_target(frame), (207, 410))

    def test_personal_truck_detector_does_not_return_upper_alliance_slot(self):
        frame = np.full((720, 1280, 3), (55, 60, 58), dtype=np.uint8)
        cv2.line(frame, (612, 190), (668, 190), (205, 205, 200), 12)
        cv2.line(frame, (640, 162), (640, 218), (205, 205, 200), 12)
        self.assertIsNone(detect_truck_personal_slot_target(frame))

    def test_personal_truck_detector_resumes_unsent_truck(self):
        frame = np.full((720, 1280, 3), (55, 60, 58), dtype=np.uint8)
        cv2.putText(frame, "NOT SENT", (90, 462), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (30, 30, 220), 3)
        self.assertEqual(detect_truck_personal_slot_target(frame), (207, 410))

    def test_detects_alliance_escort_ticket_screen(self):
        frame = np.full((720, 1280, 3), (45, 55, 45), dtype=np.uint8)
        cv2.putText(frame, "0/1", (385, 190), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (30, 30, 230), 4)
        self.assertTrue(truck_alliance_escort_is_visible(frame))

    def test_detects_truck_overview_and_personal_start_button(self):
        overview = np.full((720, 1280, 3), (55, 60, 58), dtype=np.uint8)
        cv2.rectangle(overview, (850, 14), (1060, 66), (35, 115, 185), -1)
        cv2.line(overview, (612, 190), (668, 190), (205, 205, 200), 12)
        cv2.line(overview, (640, 162), (640, 218), (205, 205, 200), 12)
        self.assertTrue(truck_express_overview_is_visible(overview))

        dispatch = np.full((720, 1280, 3), (45, 50, 45), dtype=np.uint8)
        cv2.rectangle(dispatch, (435, 558), (837, 613), (35, 180, 235), -1)
        self.assertEqual(detect_truck_start_dispatch_target(dispatch), (640, 585))
        self.assertFalse(truck_express_overview_is_visible(dispatch))

    def test_detects_personal_truck_escort_confirmation(self):
        formation = np.full((720, 1280, 3), (45, 50, 45), dtype=np.uint8)
        cv2.rectangle(formation, (815, 585), (1190, 646), (45, 130, 190), -1)
        self.assertEqual(detect_truck_escort_confirmation_target(formation), (1000, 616))

        no_button = np.full((720, 1280, 3), (45, 50, 45), dtype=np.uint8)
        self.assertIsNone(detect_truck_escort_confirmation_target(no_button))

    def test_detects_arrived_personal_truck_reward_overlay(self):
        reward = np.full((720, 1280, 3), (28, 31, 34), dtype=np.uint8)
        cv2.rectangle(reward, (90, 208), (1190, 229), (25, 120, 205), -1)
        cv2.rectangle(reward, (535, 248), (745, 287), (225, 225, 225), -1)
        self.assertTrue(truck_arrival_reward_is_visible(reward))

        overview = np.full((720, 1280, 3), (55, 60, 58), dtype=np.uint8)
        cv2.rectangle(overview, (850, 14), (1060, 66), (35, 115, 185), -1)
        cv2.line(overview, (612, 190), (668, 190), (205, 205, 200), 12)
        cv2.line(overview, (640, 162), (640, 218), (205, 205, 200), 12)
        self.assertFalse(truck_arrival_reward_is_visible(overview))

    def test_detects_active_personal_truck_detail_back_arrow(self):
        detail = np.full((720, 1280, 3), (45, 50, 45), dtype=np.uint8)
        cv2.rectangle(detail, (1100, 150), (1190, 220), (40, 80, 120), -1)
        cv2.line(detail, (1155, 165), (1132, 181), (40, 155, 220), 8)
        cv2.line(detail, (1132, 181), (1155, 197), (40, 155, 220), 8)
        self.assertEqual(detect_truck_active_detail_back_target(detail), (1143, 181))
        self.assertIsNone(detect_truck_ready_collection_target(detail))

        cv2.rectangle(detail, (780, 550), (1150, 615), (35, 180, 235), -1)
        self.assertEqual(detect_truck_ready_collection_target(detail), (965, 582))

    def test_event_detail_gold_text_is_not_a_blocking_overlay_close(self):
        frame = np.full((720, 1280, 3), (25, 30, 35), dtype=np.uint8)
        cv2.rectangle(frame, (150, 70), (1130, 570), (150, 80, 35), thickness=-1)
        cv2.rectangle(frame, (473, 580), (807, 636), (45, 180, 235), thickness=-1)
        for left, width, height in (
            (1118, 19, 11),
            (1140, 9, 15),
            (1152, 8, 11),
            (1162, 8, 15),
            (1172, 8, 11),
            (1182, 11, 14),
        ):
            cv2.rectangle(
                frame,
                (left, 126),
                (left + width, 126 + height),
                (45, 180, 220),
                thickness=-1,
            )

        self.assertIsNone(detect_game_event_overlay_close_target(frame))

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

        title_screen = np.full((720, 1280, 3), (25, 35, 45), dtype=np.uint8)
        cv2.rectangle(
            title_screen,
            (507, 443),
            (773, 489),
            (35, 185, 245),
            thickness=-1,
        )
        self.assertIsNone(detect_login_session_expired_ok_target(title_screen))

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

        frame[26:286, 808:1274] = (35, 35, 35)
        frame[12:82, 12:90] = (25, 25, 25)
        cv2.circle(frame, (47, 45), 28, (24, 105, 145), thickness=-1)
        self.assertEqual(detect_commander_profile_back_target(frame), (47, 45))

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

    def test_detects_wide_marked_alliance_project_ribbon(self):
        frame = np.full((720, 1280, 3), (45, 50, 55), dtype=np.uint8)
        cv2.rectangle(frame, (343, 151), (499, 188), (20, 45, 210), thickness=-1)

        self.assertEqual(
            detect_alliance_marked_project_target(frame),
            (326, 170),
        )

    def test_detects_live_marked_ribbon_split_by_light_text(self):
        frame = np.full((720, 1280, 3), (45, 50, 55), dtype=np.uint8)
        cv2.rectangle(frame, (395, 428), (489, 443), (20, 45, 210), thickness=-1)
        cv2.rectangle(frame, (413, 447), (476, 466), (20, 45, 210), thickness=-1)

        self.assertEqual(
            detect_alliance_marked_project_target(frame),
            (347, 436),
        )

    def test_detects_radar_notification_dots_and_targets_the_markers(self):
        frame = np.full((720, 1280, 3), (55, 70, 75), dtype=np.uint8)
        cv2.circle(frame, (700, 200), 8, (10, 20, 200), thickness=-1)
        cv2.circle(frame, (720, 325), 8, (10, 20, 200), thickness=-1)

        self.assertEqual(
            detect_radar_notification_targets(frame),
            [(676, 230), (696, 356)],
        )

    def test_detects_radar_overview_from_stable_chrome(self):
        frame = np.full((720, 1280, 3), (45, 55, 65), dtype=np.uint8)
        cv2.rectangle(frame, (10, 10), (75, 75), (20, 180, 240), thickness=-1)
        cv2.rectangle(frame, (980, 25), (1230, 55), (40, 190, 70), thickness=-1)
        cv2.rectangle(frame, (30, 535), (170, 695), (20, 180, 240), thickness=-1)

        self.assertTrue(radar_overview_is_visible(frame))
        self.assertFalse(radar_overview_is_visible(np.zeros_like(frame)))

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

    def test_detects_active_radar_card_countdown(self):
        frame = np.full((720, 1280, 3), (190, 205, 215), dtype=np.uint8)
        for x in (302, 315, 334, 347, 367, 380):
            cv2.rectangle(frame, (x, 356), (x + 8, 370), (35, 35, 35), thickness=-1)

        self.assertTrue(radar_card_has_active_countdown(frame))
        self.assertTrue(
            radar_card_has_active_countdown(cv2.resize(frame, (640, 360)))
        )

    def test_rejects_radar_card_without_six_digit_countdown(self):
        frame = np.full((720, 1280, 3), (190, 205, 215), dtype=np.uint8)
        for x in (302, 315, 334, 347):
            cv2.rectangle(frame, (x, 356), (x + 8, 370), (35, 35, 35), thickness=-1)

        self.assertFalse(radar_card_has_active_countdown(frame))

    def test_detects_only_cancel_on_radar_pass_purchase_dialog(self):
        frame = np.full((720, 1280, 3), (35, 45, 55), dtype=np.uint8)
        cv2.rectangle(frame, (335, 210), (945, 470), (205, 205, 205), thickness=-1)
        cv2.rectangle(frame, (360, 480), (630, 535), (95, 100, 110), thickness=-1)
        cv2.rectangle(frame, (650, 480), (920, 535), (25, 185, 245), thickness=-1)

        self.assertEqual(detect_radar_pass_purchase_cancel_target(frame), (496, 508))
        self.assertEqual(
            detect_radar_pass_purchase_cancel_target(cv2.resize(frame, (640, 360))),
            (248, 254),
        )

        cv2.rectangle(frame, (650, 480), (920, 535), (95, 100, 110), thickness=-1)
        self.assertIsNone(detect_radar_pass_purchase_cancel_target(frame))

    def test_detects_radar_deployment_prompt_create_squad(self):
        frame = np.full((720, 1280, 3), (35, 45, 55), dtype=np.uint8)
        cv2.rectangle(frame, (835, 40), (1105, 310), (190, 190, 190), thickness=-1)
        cv2.rectangle(frame, (860, 180), (1085, 235), (20, 180, 240), thickness=-1)
        cv2.rectangle(frame, (860, 240), (1085, 295), (20, 180, 240), thickness=-1)

        self.assertEqual(detect_radar_deployment_prompt_target(frame), (970, 210))
        self.assertEqual(
            detect_radar_deployment_prompt_target(cv2.resize(frame, (640, 360))),
            (485, 105),
        )

    def test_rejects_single_radar_world_button_as_deployment_prompt(self):
        frame = np.full((720, 1280, 3), (35, 45, 55), dtype=np.uint8)
        cv2.rectangle(frame, (835, 40), (1105, 310), (190, 190, 190), thickness=-1)
        cv2.rectangle(frame, (860, 180), (1085, 235), (20, 180, 240), thickness=-1)

        self.assertIsNone(detect_radar_deployment_prompt_target(frame))

    def test_detects_narrow_world_squad_march_button(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[40:310, 835:1105] = (180, 180, 180)
        frame[65:550, 1135:1278] = (35, 35, 35)
        frame[218:263, 875:1065] = (20, 180, 230)

        self.assertEqual(detect_radar_squad_march_target(frame), (970, 240))
        self.assertEqual(
            detect_radar_squad_march_target(cv2.resize(frame, (640, 360))),
            (485, 120),
        )

    def test_rejects_march_button_without_squad_roster(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[40:310, 835:1105] = (180, 180, 180)
        frame[65:550, 1135:1278] = (150, 170, 180)
        frame[218:263, 875:1065] = (20, 180, 230)

        self.assertIsNone(detect_radar_squad_march_target(frame))

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

    def test_back_confirmation_rejects_single_connection_error_ok_button(self):
        frame = np.full((720, 1280, 3), (35, 45, 55), dtype=np.uint8)
        frame[210:470, 330:950] = (210, 215, 220)
        cv2.rectangle(frame, (508, 482), (772, 535), (20, 180, 245), -1)
        self.assertIsNone(detect_back_confirmation_cancel_target(frame))

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

        dark_caption_strip = selected.copy()
        dark_caption_strip[658:705, 575:1160] = (30, 180, 240)
        dark_caption_strip[658:705, 575:985] = (45, 45, 45)
        self.assertTrue(healing_troop_form_is_visible(dark_caption_strip))

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

    def test_finished_healing_target_rejects_upper_event_tile(self):
        frame = np.full((720, 1280, 3), (70, 70, 70), dtype=np.uint8)
        cv2.rectangle(
            frame,
            (830, 136),
            (872, 178),
            (35, 80, 145),
            thickness=-1,
        )
        cv2.circle(frame, (851, 157), 16, (225, 225, 225), thickness=-1)
        cv2.rectangle(
            frame,
            (848, 142),
            (854, 172),
            (20, 25, 220),
            thickness=-1,
        )
        cv2.rectangle(
            frame,
            (839, 154),
            (863, 160),
            (20, 25, 220),
            thickness=-1,
        )

        self.assertIsNone(detect_finished_healing_target(frame))


if __name__ == "__main__":
    unittest.main()
