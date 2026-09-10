from types import SimpleNamespace
import threading
import unittest
from unittest.mock import Mock, call, patch

from buzzbot.display import make_display_profile
from buzzbot.state import BotState
from buzzbot_app import AutoClicker, _BotActionInterrupted


class ActionFollowupTests(unittest.TestCase):
    def make_action_bot(self, backend="adb"):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = backend
        bot.adb_client = Mock()
        bot._thread = threading.current_thread()
        bot.stop_event = threading.Event()
        bot.stop_hotkey_pressed = False
        bot._set_state(BotState.RUNNING)
        bot.get_display_profile = Mock(return_value=make_display_profile(1280, 720))
        bot._resolve_action_numbers = Mock(return_value=[])
        bot._resource_result_level_rejected = Mock(return_value=False)
        bot._invalidate_capture = Mock()
        bot.set_status_message = Mock()
        bot.cycle_mode = False
        bot.sleep_found = 0
        return bot

    @staticmethod
    def interrupt(bot, reason):
        if reason == "pause":
            bot._set_state(BotState.PAUSED)
        elif reason == "hotkey":
            bot.stop_hotkey_pressed = True
        else:
            bot.stop_event.set()

    def test_thread_start_failure_releases_device_and_restores_stopped_state(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "adb"
        bot.adb_serial = "test-device"
        bot.player_index = None
        bot.stop_event = threading.Event()
        bot.stop_event.set()
        bot._thread = None
        bot._set_state(BotState.STOPPED)
        bot.check_runtime_environment = Mock(return_value=True)
        bot.work_area_type = "full"
        bot.blocked_coords = []
        bot.routine_mode = False
        bot.search_images = [{"enabled": True, "group": None, "path": __file__, "description": "template"}]
        bot.groups = {}
        bot.device_lease = None
        bot.root = None
        bot.tr = lambda key, **kwargs: key
        bot.set_status_message = Mock()
        with patch("buzzbot_app.DeviceLease") as lease_type, patch("buzzbot_app.threading.Thread") as thread_type:
            lease = lease_type.return_value
            lease.acquire.return_value = True
            thread_type.return_value.start.side_effect = RuntimeError("cannot start worker")
            with self.assertLogs("BuZzbot", level="ERROR"), self.assertRaisesRegex(RuntimeError, "cannot start worker"):
                bot.start()
            lease.acquire.assert_called_once_with()
            lease.release.assert_called_once_with()
        self.assertTrue(bot.stop_event.is_set())
        self.assertEqual(bot.state, BotState.STOPPED)
        self.assertFalse(bot.is_running)
        self.assertFalse(bot.is_paused)
        self.assertIsNone(bot.device_lease)

    def test_interrupted_worker_never_starts_backend_input(self):
        for backend in ("adb", "screen"):
            for reason in ("stop", "pause", "hotkey"):
                with self.subTest(backend=backend, reason=reason):
                    bot = self.make_action_bot(backend)
                    self.interrupt(bot, reason)
                    with patch("buzzbot_app.pyautogui") as screen:
                        with self.assertRaises(_BotActionInterrupted):
                            bot._execute_action({"action": "click"}, SimpleNamespace(x=100, y=200))
                    self.assertEqual(bot.adb_client.mock_calls, [])
                    self.assertEqual(screen.mock_calls, [])
                    bot._resolve_action_numbers.assert_not_called()

    def test_click_sequence_stops_after_first_click(self):
        for backend in ("adb", "screen"):
            for reason in ("stop", "pause"):
                with self.subTest(backend=backend, reason=reason):
                    bot = self.make_action_bot(backend)
                    image = {"action": "click", "click_sequence": [(20, 0), (0, 30)]}
                    with patch("buzzbot_app.pyautogui") as screen:
                        click = bot.adb_client.tap if backend == "adb" else screen.click
                        click.side_effect = lambda *args, bot=bot, reason=reason: self.interrupt(bot, reason)
                        with self.assertRaises(_BotActionInterrupted):
                            bot._execute_action(image, SimpleNamespace(x=100, y=200))
                    self.assertEqual(click.call_count, 1)
                    screen.moveRel.assert_not_called()
                    bot.adb_client.input_text.assert_not_called()

    def test_adb_double_click_stops_before_second_tap(self):
        for reason in ("stop", "pause"):
            with self.subTest(reason=reason):
                bot = self.make_action_bot()
                bot.adb_client.tap.side_effect = lambda *args, bot=bot, reason=reason: self.interrupt(bot, reason)
                with patch("buzzbot_app.pyautogui") as screen:
                    with self.assertRaises(_BotActionInterrupted):
                        bot._execute_action({"action": "double_click"}, SimpleNamespace(x=100, y=200))
                bot.adb_client.tap.assert_called_once_with(100, 200)
                self.assertEqual(screen.mock_calls, [])

    def test_active_worker_still_completes_adb_sequence_and_double_click(self):
        cases = (
            ({"action": "click", "click_sequence": [(20, 0), (0, 30)]}, [(100, 200), (120, 200), (120, 230)]),
            ({"action": "double_click"}, [(100, 200), (100, 200)]),
        )
        for config, coordinates in cases:
            with self.subTest(config=config):
                bot = self.make_action_bot()
                config.update(description="template", delay=0)
                with patch.object(bot, "_interruptible_sleep"), patch("buzzbot_app.pyautogui") as screen:
                    self.assertTrue(bot._execute_action(config, SimpleNamespace(x=100, y=200)))
                self.assertEqual(bot.adb_client.tap.call_args_list, [call(*point) for point in coordinates])
                self.assertEqual(screen.mock_calls, [])


if __name__ == "__main__":
    unittest.main()
