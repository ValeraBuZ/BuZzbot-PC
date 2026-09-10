from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from buzzbot.matching import settlement_building_catalogue_is_visible
from buzzbot_app import AutoClicker


FIXTURE = Path(__file__).parent / 'assets/merchant/catalogue_shop_limit.png'


class MerchantCatalogueFollowupTests(unittest.TestCase):
    def setUp(self):
        for name, value in (
            ('mysterious_merchant_screen_is_visible', False),
            ('detect_mysterious_merchant_absent_ok_target', None),
        ):
            patcher = patch(f'buzzbot_app.{name}', return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch('buzzbot_app.logger')
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_bot(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = 'adb'
        bot.adb_client = Mock()
        bot.routine_completed_steps = {
            'merchant_build_menu_open', 'merchant_catalog_economy_selected',
            'merchant_catalog_reset', 'merchant_catalog_scrolled',
            'merchant_shop_card_tapped', 'merchant_catalog_selection_marker_checked',
            'merchant_arrival_marker_checked', 'merchant_event_panel_checked',
        }
        bot._capture_screen_bgr = Mock(return_value=(cv2.imread(str(FIXTURE)), (0, 0)))
        bot._is_settlement_screen_visible = Mock(return_value=False)
        bot._is_main_screen_visible = Mock(return_value=False)
        bot._switch_to_settlement_screen = Mock(return_value=True)
        bot._tap_routine_fallback = Mock(return_value=True)
        bot._save_routine_calibration_frame = Mock()
        bot._invalidate_capture = Mock()
        bot._interruptible_sleep = Mock()
        bot.set_status_message = Mock()
        bot.routine_merchant_scan_index = 17
        bot.click_count = 0
        return bot

    @staticmethod
    def tick(bot):
        return bot._try_mysterious_merchant_visual_fallback({'id': 'mysterious_merchant', 'settings': {}})

    @staticmethod
    def settlement(bot):
        bot._capture_screen_bgr.return_value = (np.zeros((720, 1280, 3), dtype=np.uint8), (0, 0))
        bot._is_settlement_screen_visible.return_value = True

    def test_real_maxed_card_preserves_first_result_and_does_not_claim_focus(self):
        bot = self.make_bot()
        self.assertTrue(settlement_building_catalogue_is_visible(bot._capture_screen_bgr.return_value[0]))
        self.assertTrue(self.tick(bot))
        self.assertIn('merchant_catalogue_focus_unconfirmed', bot.routine_completed_steps)
        self.assertNotIn('merchant_shop_building_tapped', bot.routine_completed_steps)
        self.assertEqual(bot._tap_routine_fallback.call_args.args[1][0], 'merchant_close_build_menu')
        self.settlement(bot)
        self.assertTrue(self.tick(bot))
        saved = [call for call in bot._save_routine_calibration_frame.call_args_list
                 if call.args[1] == 'catalogue_selection_result']
        self.assertEqual(len(saved), 1)
        bot.adb_client.swipe.assert_not_called()

    def test_unfocused_catalogue_recenters_before_resuming_existing_scan(self):
        bot = self.make_bot()
        self.tick(bot)
        self.settlement(bot)
        self.assertTrue(self.tick(bot))
        self.assertEqual(bot._tap_routine_fallback.call_args.args[0], (65, 655))
        self.assertNotIn('merchant_selected_building_revealed', bot.routine_completed_steps)
        bot._is_main_screen_visible.return_value = True
        bot._is_settlement_screen_visible.return_value = False
        self.assertTrue(self.tick(bot))
        bot._switch_to_settlement_screen.assert_called_once()
        self.assertIn('merchant_search_recentered', bot.routine_completed_steps)
        self.assertIn('merchant_selected_building_revealed', bot.routine_completed_steps)
        self.assertEqual(bot.routine_merchant_scan_index, 0)
        bot.adb_client.swipe.assert_not_called()

    def test_unconfirmed_world_transition_does_not_pan_or_repeat_region_input(self):
        bot = self.make_bot()
        self.tick(bot)
        self.settlement(bot)
        self.tick(bot)
        bot._tap_routine_fallback.reset_mock()
        self.assertFalse(self.tick(bot))
        self.assertNotIn('merchant_search_recentered', bot.routine_completed_steps)
        self.assertEqual(bot.routine_merchant_scan_index, 17)
        bot._tap_routine_fallback.assert_not_called()
        bot._switch_to_settlement_screen.assert_not_called()
        bot.adb_client.swipe.assert_not_called()

    def test_settlement_wins_when_shared_home_markers_also_match(self):
        bot = self.make_bot()
        self.tick(bot)
        self.settlement(bot)
        bot._is_main_screen_visible.return_value = True
        bot._tap_routine_fallback.reset_mock()

        self.assertTrue(self.tick(bot))

        bot._tap_routine_fallback.assert_called_once()
        self.assertEqual(bot._tap_routine_fallback.call_args.args[0], (65, 655))
        self.assertIn('merchant_recenter_world_requested', bot.routine_completed_steps)
        self.assertNotIn('merchant_search_recentered', bot.routine_completed_steps)
        self.assertNotIn('merchant_selected_building_revealed', bot.routine_completed_steps)
        bot._switch_to_settlement_screen.assert_not_called()
        bot.adb_client.swipe.assert_not_called()

    def test_shared_home_marker_does_not_confirm_unfinished_world_transition(self):
        bot = self.make_bot()
        self.tick(bot)
        self.settlement(bot)
        self.tick(bot)
        bot._tap_routine_fallback.reset_mock()
        bot._is_main_screen_visible.return_value = True

        self.assertFalse(self.tick(bot))

        self.assertNotIn('merchant_search_recentered', bot.routine_completed_steps)
        self.assertEqual(bot.routine_merchant_scan_index, 17)
        bot._tap_routine_fallback.assert_not_called()
        bot._switch_to_settlement_screen.assert_not_called()
        bot.adb_client.swipe.assert_not_called()

    def test_failed_return_to_settlement_does_not_start_scan(self):
        bot = self.make_bot()
        self.tick(bot)
        self.settlement(bot)
        bot._is_main_screen_visible.return_value = True
        bot._is_settlement_screen_visible.return_value = False
        bot._switch_to_settlement_screen.return_value = False
        self.assertFalse(self.tick(bot))
        self.assertNotIn('merchant_search_recentered', bot.routine_completed_steps)
        self.assertEqual(bot.routine_merchant_scan_index, 17)
        bot.adb_client.swipe.assert_not_called()

    def test_positive_selection_marker_still_wins_before_recenter(self):
        bot = self.make_bot()
        self.tick(bot)
        self.settlement(bot)
        bot.routine_completed_steps.discard('merchant_catalog_selection_marker_checked')
        with patch('buzzbot_app.detect_merchant_shop_building_target', return_value=((500, 400), .95)):
            self.assertTrue(self.tick(bot))
        self.assertIn('merchant_shop_building_tapped', bot.routine_completed_steps)
        self.assertEqual(bot.routine_merchant_shop_target, (500, 400))
        self.assertNotIn('merchant_recenter_world_requested', bot.routine_completed_steps)
        bot._switch_to_settlement_screen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
