import threading
import unittest
from unittest.mock import patch

import numpy as np
import cv2
from pathlib import Path
from buzzbot.igg_identity import read_sdk_igg_id

from buzzbot_app import AutoClicker


class AccountIdentityVerificationTests(unittest.TestCase):
    # Accessibility order is intentionally the opposite of screen order.
    CHOOSER_XML = (
        '<hierarchy><node class="android.widget.TextView" '
        'text="IGG ID: 9999999999" bounds="[400,300][800,350]"/>'
        '<node class="android.widget.TextView" '
        'text="IGG ID: 1234567890" bounds="[400,150][800,200]"/></hierarchy>'
    )
    def make_bot(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.account_switch_selected_at = 1.0
        bot.account_switch_error = ""
        bot.account_switch_auto_login_attempted = True
        bot.account_profiles = [{"id": "target", "verified_igg_id": "1234567890"}]
        bot.routine_completed_steps = {
            "account_switch_igg_login_submitted", "account_switch_igg_id_selected"
        }
        bot._is_game_home_visible = lambda: True
        bot._return_to_main_screen = lambda **kwargs: True
        bot._invalidate_capture = lambda: None
        bot._interruptible_sleep = lambda seconds: None
        bot.messages = []
        bot.set_status_message = lambda message, **kwargs: bot.messages.append(message)
        bot.stop_event = threading.Event()
        task = {
            "id": "__account_switch__",
            "settings": {
                "target_account_id": "target", "login_method": "igg",
                "_expected_igg_id": "1234567890", "_identity_check_started": True,
                "_identity_check_started_at": 90.0,
            },
        }
        return bot, task

    @patch("buzzbot_app.time.time", return_value=100.0)
    @patch("buzzbot_app.read_game_igg_id", return_value="1234567890")
    def test_success_requires_two_readings_and_matching_target(self, reader, clock):
        bot, task = self.make_bot()
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        self.assertTrue(bot._try_account_switch_verify_identity(task, frame))
        self.assertFalse(bot._account_switch_main_screen_confirmed(task))
        self.assertTrue(bot._try_account_switch_verify_identity(task, frame))
        self.assertTrue(bot._account_switch_main_screen_confirmed(task))
        self.assertEqual(reader.call_count, 2)
        self.assertEqual(task["settings"]["_verified_igg_id"], "1234567890")

    @patch("buzzbot_app.time.time", return_value=100.0)
    @patch("buzzbot_app.read_game_igg_id", return_value="1234567890")
    def test_matching_id_without_home_return_cannot_release_queue(self, reader, clock):
        bot, task = self.make_bot()
        bot._return_to_main_screen = lambda **kwargs: False
        for _ in range(2):
            self.assertTrue(bot._try_account_switch_verify_identity(task, None))
        self.assertFalse(bot._account_switch_main_screen_confirmed(task))
        self.assertNotIn("_verified_igg_id", task["settings"])

    @patch("buzzbot_app.time.time", return_value=100.0)
    @patch("buzzbot_app.read_game_igg_id", return_value="1234567890")
    def test_same_id_can_be_verified_from_account_panel_without_final_ok(self, reader, clock):
        bot, task = self.make_bot()
        task["settings"].pop("_identity_check_started")
        bot._is_game_home_visible = lambda: False
        self.assertTrue(bot._try_account_switch_verify_identity(task, None))
        self.assertFalse(bot._account_switch_main_screen_confirmed(task))
        self.assertTrue(bot._try_account_switch_verify_identity(task, None))
        bot._is_game_home_visible = lambda: True
        self.assertTrue(bot._account_switch_main_screen_confirmed(task))
        self.assertEqual(reader.call_count, 2)

    @patch("buzzbot_app.time.time", return_value=100.0)
    @patch("buzzbot_app.read_game_igg_id", return_value=None)
    @patch("buzzbot_app.detect_account_details_close_target", return_value=None)
    @patch("buzzbot_app.detect_settings_close_target", return_value=None)
    @patch("buzzbot_app.detect_commander_profile_back_target", return_value=None)
    def test_verification_owns_transitional_frames_without_accepting_stale_reading(self, *mocks):
        bot, task = self.make_bot()
        task["settings"]["_identity_candidate"] = "1234567890"
        bot._is_game_home_visible = lambda: False
        self.assertTrue(bot._try_account_switch_verify_identity(task, None))
        self.assertNotIn("_identity_candidate", task["settings"])
        self.assertFalse(bot._account_switch_main_screen_confirmed(task))

    def test_old_same_account_shortcut_and_bare_success_step_are_rejected(self):
        bot, task = self.make_bot()
        bot.routine_completed_steps.add("account_switch_igg_same_id_verified")
        self.assertFalse(bot._account_switch_main_screen_confirmed(task))
        bot.routine_completed_steps.add("account_switch_igg_loaded_id_verified")
        self.assertFalse(bot._account_switch_main_screen_confirmed(task))
        task["settings"]["_verified_igg_id"] = "9999999999"
        self.assertFalse(bot._account_switch_main_screen_confirmed(task))

    @patch("buzzbot_app.time.time", return_value=100.0)
    @patch("buzzbot_app.read_game_igg_id", return_value="9999999999")
    def test_wrong_account_retries_once_then_reports_failure(self, reader, clock):
        bot, task = self.make_bot()
        for _ in range(2):
            bot._try_account_switch_verify_identity(task, None)
        self.assertTrue(task["settings"]["_identity_retry"])
        self.assertEqual(bot.account_switch_selected_at, 0.0)
        self.assertFalse(bot.account_switch_auto_login_attempted)
        self.assertFalse(bot._account_switch_main_screen_confirmed(task))
        # The retry reauthenticates and starts a fresh account-panel check.
        bot.account_switch_selected_at = 1.0
        bot.routine_completed_steps = {"account_switch_igg_id_selected"}
        task["settings"].update({
            "_identity_check_started": True, "_identity_check_started_at": 90.0,
        })
        for _ in range(2):
            bot._try_account_switch_verify_identity(task, None)
        self.assertIn("другой IGG ID", bot.account_switch_error)
        self.assertFalse(bot._account_switch_main_screen_confirmed(task))

    @patch("buzzbot_app.time.time", return_value=140.0)
    def test_unreadable_identity_has_a_bounded_failure(self, clock):
        bot, task = self.make_bot()
        self.assertTrue(bot._try_account_switch_verify_identity(task, None))
        self.assertIn("не удалось прочитать ID", bot.account_switch_error)
        self.assertFalse(bot._account_switch_main_screen_confirmed(task))

    @patch("buzzbot_app.time.time", return_value=100.0)
    def test_unknown_target_never_accepts_arbitrary_home_screen(self, clock):
        for method in ("igg", "google"):
            with self.subTest(method=method):
                bot, task = self.make_bot()
                task["settings"]["login_method"] = method
                task["settings"].pop("_expected_igg_id")
                self.assertTrue(bot._try_account_switch_verify_identity(task, None))
                self.assertIn("неизвестен IGG ID", bot.account_switch_error)
                self.assertFalse(bot._account_switch_main_screen_confirmed(task))

    @patch("buzzbot_app.time.time", return_value=100.0)
    def test_stale_profile_before_sdk_selection_is_not_checked(self, clock):
        bot, task = self.make_bot()
        bot.routine_completed_steps.discard("account_switch_igg_id_selected")
        with patch("buzzbot_app.read_game_igg_id") as reader:
            self.assertFalse(bot._try_account_switch_verify_identity(task, None))
            reader.assert_not_called()

    def chooser_bot(self):
        bot, task = self.make_bot()
        bot.input_backend = "adb"
        bot.adb_client = type("ChooserAdb", (), {"ui_xml": lambda adb: self.CHOOSER_XML})()
        bot.routine_completed_steps = {"account_switch_igg_login_submitted"}
        bot.taps = []
        bot._tap_routine_fallback = lambda target, *args: bot.taps.append(target) or True
        task["settings"]["chooser_index"] = 1
        # Isolate the selected-row boundary; game verification has separate tests.
        bot.stop_event.set()
        return bot, task

    def test_expected_id_matches_the_clicked_row_in_screen_order(self):
        bot, task = self.chooser_bot()
        self.assertTrue(bot._try_account_switch_igg_id_selection(task))
        self.assertEqual(bot.taps, [(600, 175)])
        self.assertEqual(task["settings"]["_expected_igg_id"], "1234567890")
        self.assertNotIn("_verified_igg_id", task["settings"])

    def test_bound_profile_selects_exact_id_instead_of_stale_row_number(self):
        bot, task = self.chooser_bot()
        task["settings"]["chooser_index"] = 2
        self.assertTrue(bot._try_account_switch_igg_id_selection(task))
        self.assertEqual(bot.taps, [(600, 175)])
        self.assertEqual(bot.account_switch_error, "")

    def test_absent_bound_id_never_clicks_another_row(self):
        bot, task = self.chooser_bot()
        bot.account_profiles[0]["verified_igg_id"] = "7777777777"
        self.assertTrue(bot._try_account_switch_igg_id_selection(task))
        self.assertEqual(bot.taps, [])
        self.assertIn("не соответствует", bot.account_switch_error)

    def test_unbound_profile_cannot_learn_an_unauthenticated_sdk_identity(self):
        bot, task = self.chooser_bot()
        bot.account_profiles[0].pop("verified_igg_id")
        bot.routine_completed_steps.clear()
        self.assertTrue(bot._try_account_switch_igg_id_selection(task))
        self.assertEqual(bot.taps, [])
        self.assertIn("учётными данными", bot.account_switch_error)

    def test_unbound_profile_can_verify_sdk_identity_after_target_login(self):
        bot, task = self.chooser_bot()
        bot.account_profiles[0].pop("verified_igg_id")
        self.assertTrue(bot._try_account_switch_igg_id_selection(task))
        self.assertEqual(bot.taps, [(600, 175)])
        self.assertEqual(task["settings"]["_expected_igg_id"], "1234567890")
        self.assertNotIn("verified_igg_id", bot.account_profiles[0])

    def test_sdk_image_reader_requires_the_real_single_row_screen(self):
        frame = cv2.imread(str(Path(__file__).parent/'assets/accounts/sdk_single_id.png'))
        self.assertEqual(read_sdk_igg_id(frame), '2097367404')
        self.assertIsNone(read_sdk_igg_id(np.zeros_like(frame)))
        frame[147:176, 340:345] = 255
        self.assertIsNone(read_sdk_igg_id(frame))

    @patch('buzzbot_app.time.time', return_value=100.0)
    @patch('buzzbot_app.detect_game_event_overlay_close_target', return_value=(1137,134))
    def test_late_event_banner_is_closed_during_identity_check(self, *_mocks):
        bot, task = self.make_bot()
        taps=[]
        bot._tap_routine_fallback=lambda point,*args:taps.append(point) or True
        self.assertTrue(bot._try_account_switch_verify_identity(task, None))
        self.assertEqual(taps, [(1137,134)])
        self.assertFalse(bot._account_switch_main_screen_confirmed(task))

    def test_inaccessible_sdk_requires_two_matching_images_and_existing_binding(self):
        frame = cv2.imread(str(Path(__file__).parent/'assets/accounts/sdk_single_id.png'))
        for bound, readings, should_tap in [
            ('2097367404', ['2097367404','2097367404'], True),
            ('1234567890', ['2097367404','2097367404'], False),
            ('2097367404', ['2097367404','2097367405'], False),
            ('', ['2097367404','2097367404'], False),
        ]:
            with self.subTest(bound=bound, readings=readings):
                bot, task = self.chooser_bot()
                bot.account_profiles[0]['verified_igg_id'] = bound
                bot.adb_client.ui_xml = lambda: '<hierarchy/>'
                bot._capture_screen_bgr = lambda **kwargs: (frame.copy(),(0,0))
                with patch('buzzbot_app.read_sdk_igg_id', side_effect=readings):
                    bot._try_account_switch_igg_id_selection(task)
                self.assertEqual(bool(bot.taps), should_tap)
                if should_tap:
                    self.assertEqual(task['settings']['_expected_igg_id'], bound)
                    self.assertNotIn('_verified_igg_id', task['settings'])


if __name__ == "__main__":
    unittest.main()
