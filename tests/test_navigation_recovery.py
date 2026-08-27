import unittest

import numpy as np

from buzzbot_app import AutoClicker


class FakeAdbClient:
    def __init__(self):
        self.taps = []
        self.keys = []

    def tap(self, x, y):
        self.taps.append((x, y))

    def keyevent(self, key):
        self.keys.append(key)


class NavigationRecoveryTests(unittest.TestCase):
    def test_settlement_switch_closes_covering_chat_after_blocked_tap(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = FakeAdbClient()
        bot._capture_screen_bgr = lambda force=False: (
            np.zeros((720, 1280, 3), dtype=np.uint8),
            (0, 0),
        )
        settlement_checks = iter((False, False, False, False, False, True))
        bot._is_settlement_screen_visible = lambda: next(settlement_checks)
        bot._is_main_screen_visible = lambda: True
        bot._interruptible_sleep = lambda _seconds: None
        bot._invalidate_capture = lambda: None
        bot.set_status_message = lambda *_args, **_kwargs: None

        self.assertTrue(bot._switch_to_settlement_screen())
        self.assertEqual(bot.adb_client.taps, [(65, 655)])
        self.assertEqual(bot.adb_client.keys, [4])


if __name__ == "__main__":
    unittest.main()
