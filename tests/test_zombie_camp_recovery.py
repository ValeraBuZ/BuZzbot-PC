import threading
import unittest
from pathlib import Path

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
            cv2.rectangle(frame, (1172, 260), (1268, 329), (180, 180, 220), thickness=2)
            cv2.rectangle(frame, (1240, 301), (1259, 319), (220, 180, 20), thickness=-1)
        if retreat:
            real = cv2.imread(str(Path(__file__).parent / "assets/marches/camped_retreat.png"))
            frame[420:482, 545:735] = real[420:482, 545:735]
        return frame

    def make_bot(self, frames):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_client = FakeAdbClient()
        bot.stop_event = threading.Event()
        bot.stop_hotkey_pressed = False
        bot.zombie_camp_scan_next_at = 0.0
        bot.zombie_camp_blocked_until = 0.0
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
                self.frame(camp=True, retreat=True),
                self.frame(camp=True, retreat=True),
                self.frame(camp=False),
            ]
        )

        self.assertTrue(bot._try_return_camped_zombie_march(5, now=100.0))
        self.assertEqual(bot.adb_client.taps[0], (1218, 292))
        self.assertLessEqual(abs(bot.adb_client.taps[1][0] - 696), 8)
        self.assertLessEqual(abs(bot.adb_client.taps[1][1] - 456), 8)

    def test_returns_real_unselected_camp_and_confirms_actual_return(self):
        directory = Path(__file__).parent / "assets/marches"
        bot = self.make_bot([
            cv2.imread(str(directory / name)) for name in (
                "camped_unselected.png", "camped_selected.png",
                "camped_selected.png", "retreat_returning.png",
            )
        ])
        self.assertTrue(bot._try_return_camped_zombie_march(1, now=100.0))
        self.assertEqual(bot.adb_client.taps, [(1218, 222), (696, 456)])

    def test_blocks_dispatch_without_confirmed_retreat_action(self):
        bot = self.make_bot(
            [
                self.frame(camp=True),
                self.frame(camp=True),
                self.frame(camp=True),
            ]
        )

        self.assertTrue(bot._try_return_camped_zombie_march(5, now=100.0))
        self.assertEqual(bot.adb_client.taps, [(1218, 292), (1218, 292)])
        self.assertTrue(bot._try_return_camped_zombie_march(5, now=101.0))

    def test_zoomed_out_camp_returns_and_releases_next_hunt(self):
        directory=Path(__file__).parent/'assets/marches'
        selected=cv2.imread(str(directory/'camped_zoomed_out.png'))
        returning=cv2.imread(str(directory/'retreat_returning.png'))
        bot=self.make_bot([selected,selected,selected,returning,returning])
        self.assertTrue(bot._try_return_camped_zombie_march(1,now=100))
        self.assertEqual(bot.adb_client.taps,[(1218,222),(450,544)])
        self.assertFalse(bot._try_return_camped_zombie_march(1,now=bot.zombie_camp_scan_next_at+1))
        self.assertEqual(bot.zombie_camp_blocked_until,0)

    def test_blocks_dispatch_when_retreat_does_not_remove_camp(self):
        bot = self.make_bot(
            [
                self.frame(camp=True),
                self.frame(camp=True, retreat=True),
                self.frame(camp=True, retreat=True),
                *(self.frame(camp=True) for _ in range(10)),
            ]
        )

        self.assertTrue(bot._try_return_camped_zombie_march(5, now=100.0))
        self.assertEqual(bot.adb_client.taps[0], (1218, 292))
        self.assertLessEqual(abs(bot.adb_client.taps[1][0] - 696), 8)
        self.assertLessEqual(abs(bot.adb_client.taps[1][1] - 456), 8)
        self.assertGreater(bot.zombie_camp_blocked_until, 100.0)

    def test_does_not_tap_retreat_if_action_disappears_before_confirmation(self):
        bot = self.make_bot([
            self.frame(camp=True),
            self.frame(camp=True, retreat=True),
            self.frame(camp=True),
        ])
        self.assertTrue(bot._try_return_camped_zombie_march(5, now=100.0))
        self.assertEqual(bot.adb_client.taps, [(1218, 292)])


if __name__ == "__main__":
    unittest.main()
