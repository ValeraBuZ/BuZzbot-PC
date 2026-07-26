import threading
import unittest

import numpy as np

from buzzbot_app import AutoClicker


class FakeHealingAdbClient:
    def __init__(self, available_rows=4, reset_succeeds=True, reported_value=None):
        self.available_row_y = {173, 263, 353, 443}
        self.available_row_y = set(sorted(self.available_row_y)[:available_rows])
        self.reset_succeeds = reset_succeeds
        self.reported_value = reported_value
        self.selection_cleared = False
        self.editor_open = False
        self.taps = []
        self.inputs = []
        self.current_input = ""
        self.clear_calls = 0
        self.unsafe_ok_taps = 0

    def tap(self, x, y):
        self.taps.append((x, y))
        if (x, y) == (1195, 468):
            self.selection_cleared = self.reset_succeeds
        elif x == 1085 and y in {173, 263, 353, 443}:
            self.editor_open = y in self.available_row_y
            self.current_input = "0"
        elif (x, y) == (1198, 669):
            if not self.editor_open:
                self.unsafe_ok_taps += 1
            self.editor_open = False

    def clear_focused_text(self, _max_characters):
        self.clear_calls += 1
        self.current_input = ""

    def input_text(self, value):
        self.inputs.append(str(value))
        self.current_input = str(value)

    def focused_edit_text_value(self):
        if not self.editor_open:
            return None
        if self.reported_value is not None:
            return str(self.reported_value)
        return self.current_input

    def keyevent(self, _keycode):
        self.editor_open = False


class HealingWorkflowTests(unittest.TestCase):
    def make_bot(self, available_rows=4, reset_succeeds=True, reported_value=None):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = FakeHealingAdbClient(
            available_rows=available_rows,
            reset_succeeds=reset_succeeds,
            reported_value=reported_value,
        )
        bot.stop_event = threading.Event()
        bot.stop_hotkey_pressed = False
        bot._invalidate_capture = lambda: None
        bot._interruptible_sleep = lambda _seconds: None
        bot.set_status_message = lambda *args, **kwargs: None

        def capture_screen_bgr(force=False):
            frame = np.full((720, 1280, 3), (35, 45, 55), dtype=np.uint8)
            if bot.adb_client.editor_open:
                frame[616:720, :] = (250, 250, 250)
            elif not bot.adb_client.selection_cleared:
                frame[160:185, 765:1010] = (35, 180, 55)
                frame[592:642, 900:1155] = (30, 180, 240)
            return frame, (0, 0)

        bot._capture_screen_bgr = capture_screen_bgr
        initial_frame, _origin = capture_screen_bgr(force=True)
        return bot, initial_frame

    def test_enters_four_quotas_only_while_editor_is_visible(self):
        bot, frame = self.make_bot()

        self.assertTrue(bot._configure_healing_troop_count(2000, frame))
        self.assertEqual(bot.adb_client.inputs, ["500", "500", "500", "500"])
        self.assertEqual(bot.adb_client.clear_calls, 4)
        self.assertEqual(bot.adb_client.unsafe_ok_taps, 0)
        self.assertEqual(bot.adb_client.taps[0], (1195, 468))

    def test_limit_is_redistributed_when_only_one_troop_row_is_available(self):
        bot, frame = self.make_bot(available_rows=1)

        self.assertTrue(bot._configure_healing_troop_count(2000, frame))
        self.assertEqual(bot.adb_client.inputs, ["500", "2000"])
        self.assertEqual(bot.adb_client.unsafe_ok_taps, 0)

    def test_no_editable_rows_aborts_without_blind_ok_tap(self):
        bot, frame = self.make_bot(available_rows=0)

        self.assertFalse(bot._configure_healing_troop_count(2000, frame))
        self.assertEqual(bot.adb_client.inputs, [])
        self.assertEqual(bot.adb_client.unsafe_ok_taps, 0)

    def test_failed_global_reset_aborts_before_editing_rows(self):
        bot, frame = self.make_bot(reset_succeeds=False)

        self.assertFalse(bot._configure_healing_troop_count(2000, frame))
        self.assertEqual(bot.adb_client.inputs, [])
        self.assertEqual(bot.adb_client.taps, [(1195, 468)])

    def test_mismatched_android_editor_value_aborts_before_ok(self):
        bot, frame = self.make_bot(reported_value="206001")

        self.assertFalse(bot._configure_healing_troop_count(2000, frame))
        self.assertEqual(bot.adb_client.inputs, ["500"])
        self.assertNotIn((1198, 669), bot.adb_client.taps)
        self.assertEqual(bot.adb_client.unsafe_ok_taps, 0)


if __name__ == "__main__":
    unittest.main()
