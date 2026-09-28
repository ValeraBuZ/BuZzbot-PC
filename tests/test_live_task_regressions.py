from pathlib import Path
import unittest

import cv2

from buzzbot.igg_identity import read_game_igg_id, selected_sdk_igg_id
from buzzbot.matching import (
    detect_merchant_free_refresh_target, detect_truck_active_detail_back_target,
    detect_truck_personal_slot_target, truck_express_overview_is_visible,
    detect_radar_complete_all_target, detect_radar_task_pin_targets,
)
from buzzbot_app import AutoClicker


ASSETS = Path(__file__).parent / "assets"


class LiveTaskRegressionTests(unittest.TestCase):
    def frame(self, name):
        result = cv2.imread(str(ASSETS / name))
        self.assertIsNotNone(result)
        return result

    def test_free_refresh_and_paid_refresh_are_distinguished(self):
        self.assertIsNotNone(detect_merchant_free_refresh_target(self.frame("merchant/free_refresh.png")))
        self.assertIsNone(detect_merchant_free_refresh_target(self.frame("merchant/merchant_grid.png")))

    def test_occupied_alliance_truck_does_not_hide_personal_overview(self):
        frame = self.frame("trucks/alliance_busy.png")
        self.assertTrue(truck_express_overview_is_visible(frame))
        self.assertIsNone(detect_truck_active_detail_back_target(frame))

    def test_unlocked_third_truck_is_dispatched(self):
        frame = self.frame("trucks/third_slot.png")
        self.assertEqual(detect_truck_personal_slot_target(frame), (207, 410))
        # The first two cards are unavailable; the third remains unlocked.
        frame[365:476, 30:932] = 0
        self.assertEqual(detect_truck_personal_slot_target(frame), (497, 551))

    def test_account_id_is_read_exactly_from_two_real_panels(self):
        self.assertEqual(read_game_igg_id(self.frame("accounts/igg5_account.png")), "2097378622")
        self.assertEqual(read_game_igg_id(self.frame("accounts/igg7_account.png")), "2115346649")
        self.assertIsNone(read_game_igg_id(self.frame("trucks/alliance_busy.png")))

    def test_sdk_identity_handles_webview_nodes_without_logging_credentials(self):
        xml = '<hierarchy><node class="android.view.View" text="IGG ID: 2097378622" bounds="[261,149][894,176]"/></hierarchy>'
        self.assertEqual(selected_sdk_igg_id(xml), "2097378622")
        self.assertIsNone(selected_sdk_igg_id(xml, 2))
        self.assertIsNone(selected_sdk_igg_id("broken"))

    def test_radar_missions_without_notification_dots_are_found(self):
        targets = detect_radar_task_pin_targets(self.frame("radar/complete_all_locked.png"))
        self.assertEqual(len(targets), 7)
        self.assertIn((838, 228), targets)

    def test_locked_radar_pass_is_not_activated(self):
        self.assertIsNone(detect_radar_complete_all_target(self.frame("radar/complete_all_locked.png")))

    def test_wrong_loaded_account_retries_instead_of_advancing_profile(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.account_switch_selected_at = 1.0
        bot.account_switch_auto_login_attempted = True
        bot.routine_completed_steps = {"account_switch_igg_game_confirmed", "account_switch_igg_id_selected"}
        bot._return_to_main_screen = lambda **kwargs: True
        bot._invalidate_capture = lambda: None
        bot._interruptible_sleep = lambda _seconds: None
        bot.set_status_message = lambda *_args, **_kwargs: None
        settings = {"login_method": "igg", "_expected_igg_id": "2115346649", "_identity_check_started": True}
        task = {"id": "__account_switch__", "settings": settings}
        self.assertTrue(bot._try_account_switch_verify_identity(task, self.frame("accounts/igg5_account.png")))
        self.assertEqual(bot.account_switch_selected_at, 1.0)
        self.assertTrue(bot._try_account_switch_verify_identity(task, self.frame("accounts/igg5_account.png")))
        self.assertEqual(bot.account_switch_selected_at, 0.0)
        self.assertTrue(settings["_identity_retry"])
        self.assertNotIn("account_switch_igg_loaded_id_verified", bot.routine_completed_steps)

    def test_same_account_requires_identity_and_completed_authentication(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.account_switch_selected_at = 1.0
        bot._is_game_home_visible = lambda: True
        bot.routine_completed_steps = {"account_switch_igg_id_selected", "account_switch_igg_login_submitted"}
        task = {"settings": {"login_method": "igg", "_expected_igg_id": "2097378622"}}
        self.assertFalse(bot._account_switch_main_screen_confirmed(task))
        bot.routine_completed_steps.add("account_switch_igg_same_id_verified")
        self.assertFalse(bot._account_switch_main_screen_confirmed(task))
        bot.routine_completed_steps.remove("account_switch_igg_login_submitted")
        self.assertFalse(bot._account_switch_main_screen_confirmed(task))
        bot.routine_completed_steps.add("account_switch_igg_loaded_id_verified")
        task["settings"]["_verified_igg_id"] = "2097378622"
        self.assertTrue(bot._account_switch_main_screen_confirmed(task))
