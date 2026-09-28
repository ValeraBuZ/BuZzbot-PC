import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

import numpy as np

from buzzbot.display import make_display_profile
from buzzbot_app import AutoClicker


class RadarMarkerConfirmationTests(unittest.TestCase):
    def make_bot(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = Mock()
        bot.stop_event = threading.Event()
        bot.stop_hotkey_pressed = False
        bot._check_worker_interrupted = Mock()
        bot.get_display_profile = Mock(return_value=make_display_profile(1280, 720))
        bot._resolve_action_numbers = Mock(return_value=[])
        bot._resource_result_level_rejected = Mock(return_value=False)
        bot.frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        bot._capture_screen_bgr = Mock(return_value=(bot.frame, (0, 0)))
        # Another identical marker can remain on the radar behind the card.
        bot._locate_image = Mock(return_value=(SimpleNamespace(x=604, y=239), (590, 225, 30, 30), 0.99))
        bot._invalidate_capture = Mock()
        bot.set_status_message = Mock()
        bot._interruptible_sleep = Mock()
        bot.current_routine_task_id = "radar_quick"
        bot.routine_completed_steps = set()
        bot.cycle_mode = False
        bot.sleep_found = 0
        return bot

    def execute_marker(self, bot):
        image = {
            "uid": "db635c87-12d0-5e44-9be4-1e33d17b00d2",
            "action": "click",
            "runtime_step": "radar_marker",
            "description": "Select automobile radar task",
            "confirm_disappears": True,
            "delay": 0,
        }
        with patch("buzzbot_app.logger"):
            return bot._execute_action(image, SimpleNamespace(x=547, y=440))

    def test_open_card_confirms_marker_even_when_identical_marker_remains(self):
        bot = self.make_bot()
        with patch("buzzbot_app.radar_task_card_is_visible", return_value=True) as visible:
            self.assertTrue(self.execute_marker(bot))
        bot.adb_client.tap.assert_called_once_with(547, 440)
        bot._capture_screen_bgr.assert_called_once_with(force=True)
        self.assertIs(visible.call_args.args[0], bot.frame)
        bot._locate_image.assert_not_called()

    def test_missing_card_stops_after_four_fresh_confirmation_attempts(self):
        bot = self.make_bot()
        with patch("buzzbot_app.radar_task_card_is_visible", return_value=False) as visible:
            self.assertFalse(self.execute_marker(bot))
        bot.adb_client.tap.assert_called_once_with(547, 440)
        self.assertEqual(bot._capture_screen_bgr.call_args_list, [call(force=True)] * 4)
        self.assertEqual(visible.call_count, 4)
        bot._locate_image.assert_not_called()
        self.assertFalse(any("Отправка похода" in str(c) for c in bot.set_status_message.call_args_list))

    def test_stop_during_fresh_capture_does_not_confirm_open_card(self):
        bot = self.make_bot()

        def stop_during_capture(**kwargs):
            bot.stop_event.set()
            return bot.frame, (0, 0)

        bot._capture_screen_bgr.side_effect = stop_during_capture
        with patch("buzzbot_app.radar_task_card_is_visible", return_value=True):
            self.assertFalse(self.execute_marker(bot))
        bot._capture_screen_bgr.assert_called_once_with(force=True)
        bot.adb_client.tap.assert_called_once_with(547, 440)
        bot._locate_image.assert_not_called()


if __name__ == "__main__":
    unittest.main()
