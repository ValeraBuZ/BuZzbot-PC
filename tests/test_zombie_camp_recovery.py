import threading
import unittest

import cv2
import numpy as np

from buzzbot_app import AutoClicker


class FakeAdbClient:
    def __init__(self):
        self.taps = []

    def tap(self, x, y):
        self.taps.append((int(x), int(y)))


class ZombieCampRecoveryTests(unittest.TestCase):
    @staticmethod
    def frame(*, camp=False, retreat=False):
        frame = np.full((720, 1280, 3), (35, 45, 55), dtype=np.uint8)
        if camp:
            cv2.rectangle(frame, (1240, 301), (1259, 319), (220, 180, 20), thickness=-1)
        if retreat:
            cv2.circle(frame, (696, 456), 31, (40, 145, 205), thickness=-1)
        return frame

    def make_bot(self, frames):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = FakeAdbClient()
        bot.stop_event = threading.Event()
        bot.stop_hotkey_pressed = False
        bot.zombie_camp_scan_next_at = 0.0
        bot.current_routine_task_id = None
        bot.routine_only_task_id = None
        bot.groups = {"Убийство зомби": True}
        bot.get_routine_task = lambda task_id: {
            "id": task_id,
            "group": "Убийство зомби",
            "enabled": True,
            "settings": {},
        }
        bot._world_map_visible_in_frame = lambda _frame: True
        captures = iter((frame, (0, 0)) for frame in frames)
        bot._capture_screen_bgr = lambda **_kwargs: next(captures)
        bot._interruptible_sleep = lambda _seconds: None
        bot._invalidate_capture = lambda: None
        bot.set_status_message = lambda *_args, **_kwargs: None
        return bot

    def test_returns_only_a_confirmed_camped_march(self):
        bot = self.make_bot(
            [
                self.frame(camp=True),
                self.frame(camp=True),
                self.frame(camp=True, retreat=True),
                self.frame(camp=False),
            ]
        )

        self.assertTrue(bot._try_return_camped_zombie_march(5, now=100.0))
        self.assertEqual(bot.adb_client.taps, [(1218, 292), (640, 360), (696, 456)])

    def test_does_not_tap_retreat_without_confirmed_action(self):
        bot = self.make_bot(
            [
                self.frame(camp=True),
                self.frame(camp=True),
                self.frame(camp=True),
                self.frame(camp=True),
            ]
        )

        self.assertFalse(bot._try_return_camped_zombie_march(5, now=100.0))
        self.assertEqual(bot.adb_client.taps, [(1218, 292), (640, 360), (640, 360)])


if __name__ == "__main__":
    unittest.main()
