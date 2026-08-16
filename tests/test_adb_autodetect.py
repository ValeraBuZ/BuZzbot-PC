import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from buzzbot_app import AutoClicker


class AdbAutoDetectTests(unittest.TestCase):
    def test_screen_backend_does_not_force_adb_during_environment_check(self):
        bot = AutoClicker.__new__(AutoClicker)
        bot.input_backend = "screen"
        bot.environment_ready = False
        bot.player_index = 5
        bot.player_name = "Phoenix675"
        bot.get_display_profile = Mock(
            return_value=SimpleNamespace(width=1280, height=720)
        )
        bot.set_status_message = Mock()
        bot._show_notification = Mock()
        bot.check_adb_connection = Mock(side_effect=AssertionError("ADB must not run"))
        bot._refresh_adb_client = Mock()

        self.assertTrue(bot.check_runtime_environment(notify=False))
        self.assertEqual(bot.input_backend, "screen")
        self.assertTrue(bot.environment_ready)
        bot.check_adb_connection.assert_not_called()
        bot._refresh_adb_client.assert_not_called()
        bot.set_status_message.assert_called_once_with(
            "Экранный режим | шаблоны 1280x720 | готово",
            force=True,
        )

    @patch("buzzbot_app.bridged_adb_serial_for_index", return_value=None)
    @patch("buzzbot_app.AdbClient")
    def test_configured_profile_never_adopts_another_single_device(self, adb_client, _bridged):
        probe = adb_client.return_value
        probe.list_devices.return_value = ["emulator-5562"]

        target = SimpleNamespace(index=5, adb_serial="emulator-5564")
        other = SimpleNamespace(index=4, adb_serial="emulator-5562")
        bot = AutoClicker.__new__(AutoClicker)
        bot.adb_path = "adb.exe"
        bot.adb_serial = "emulator-5564"
        bot.get_adb_repair_target = Mock(return_value=target)
        bot.get_current_account = Mock(return_value={"ldplayer_index": 5})
        bot._ldplayer_instances = Mock(return_value=("ldconsole.exe", [other, target]))
        bot._adopt_adb_serial = Mock()

        self.assertFalse(bot._auto_detect_adb_connection())
        bot._adopt_adb_serial.assert_not_called()

    @patch("buzzbot_app.bridged_adb_serial_for_index", return_value="192.168.0.53:5555")
    @patch("buzzbot_app.AdbClient")
    def test_configured_profile_adopts_matching_bridged_device(self, adb_client, _bridged):
        probe = adb_client.return_value
        probe.list_devices.side_effect = [[], [], ["192.168.0.53:5555"]]

        target = SimpleNamespace(index=5, adb_serial="emulator-5564")
        bot = AutoClicker.__new__(AutoClicker)
        bot.adb_path = "adb.exe"
        bot.adb_serial = "emulator-5564"
        bot.get_adb_repair_target = Mock(return_value=target)
        bot.get_current_account = Mock(return_value={"ldplayer_index": 5})
        bot._ldplayer_instances = Mock(return_value=("ldconsole.exe", [target]))
        bot._adopt_adb_serial = Mock()

        self.assertTrue(bot._auto_detect_adb_connection())
        probe.connect.assert_any_call("127.0.0.1:5565")
        probe.connect.assert_any_call("192.168.0.53:5555")
        bot._adopt_adb_serial.assert_called_once_with("192.168.0.53:5555", 5)


if __name__ == "__main__":
    unittest.main()
