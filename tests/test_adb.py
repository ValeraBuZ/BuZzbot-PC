import subprocess
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from buzzbot.adb import AdbClient, AdbError


class FakeResult:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class AdbClientTests(unittest.TestCase):
    def make_client(self, runner):
        client = AdbClient.__new__(AdbClient)
        client.adb_path = __import__("pathlib").Path("adb.exe")
        client.serial = "emulator-5556"
        client._runner = runner
        return client

    def test_connection_uses_selected_serial(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return FakeResult(stdout="device\n")

        client = self.make_client(runner)
        self.assertTrue(client.is_available())
        self.assertEqual(calls[0][0], ["adb.exe", "-s", "emulator-5556", "get-state"])

    def test_responsive_connection_requires_working_shell(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            if command[-1] == "get-state":
                return FakeResult(stdout="device\n")
            return FakeResult(stdout="buzzbot_ready\n")

        client = self.make_client(runner)
        self.assertTrue(client.is_responsive())
        self.assertEqual(
            calls[1][0],
            ["adb.exe", "-s", "emulator-5556", "shell", "echo", "buzzbot_ready"],
        )

    def test_responsive_connection_rejects_visible_but_stalled_device(self):
        def runner(command, **_kwargs):
            if command[-1] == "get-state":
                return FakeResult(stdout="device\n")
            raise subprocess.TimeoutExpired(command, 4)

        self.assertFalse(self.make_client(runner).is_responsive())

    def test_screenshot_is_decoded_to_bgr(self):
        source = np.zeros((4, 6, 3), dtype=np.uint8)
        source[:, :] = (12, 34, 56)
        ok, encoded = cv2.imencode(".png", source)
        self.assertTrue(ok)

        def runner(_command, **_kwargs):
            return FakeResult(stdout=encoded.tobytes(), stderr=b"")

        frame = self.make_client(runner).screenshot_bgr()
        self.assertEqual(frame.shape, (4, 6, 3))
        self.assertEqual(tuple(frame[0, 0]), (12, 34, 56))

    def test_failed_command_raises_readable_error(self):
        def runner(_command, **_kwargs):
            return FakeResult(stderr="device offline", returncode=1)

        with self.assertRaisesRegex(AdbError, "device offline"):
            self.make_client(runner).tap(10, 20)

    def test_swipe_uses_selected_serial_and_duration(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return FakeResult()

        self.make_client(runner).swipe(10, 20, 30, 40, duration_ms=650)
        self.assertEqual(
            calls[0][0],
            [
                "adb.exe",
                "-s",
                "emulator-5556",
                "shell",
                "input",
                "swipe",
                "10",
                "20",
                "30",
                "40",
                "650",
            ],
        )

    def test_keyevent_uses_selected_serial(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return FakeResult()

        self.make_client(runner).keyevent(67)
        self.assertEqual(
            calls[0][0],
            ["adb.exe", "-s", "emulator-5556", "shell", "input", "keyevent", "67"],
        )

    def test_reads_focused_android_edit_text_value(self):
        client = self.make_client(lambda *_args, **_kwargs: FakeResult())
        client.ui_xml = lambda: (
            "<hierarchy><node class='android.widget.EditText' focused='true' "
            "text='2850'/><node class='android.widget.Button' focused='false' "
            "text='OK'/></hierarchy>"
        )

        self.assertEqual(client.focused_edit_text_value(), "2850")

    def test_missing_focused_android_edit_text_returns_none(self):
        client = self.make_client(lambda *_args, **_kwargs: FakeResult())
        client.ui_xml = lambda: "<hierarchy><node class='android.widget.EditText' focused='false' text='10'/></hierarchy>"

        self.assertIsNone(client.focused_edit_text_value())

    @patch("buzzbot.adb.subprocess.Popen")
    def test_private_text_is_sent_through_stdin_not_command_line(self, popen):
        process = popen.return_value
        process.communicate.return_value = (b"", b"")
        process.returncode = 0
        client = self.make_client(lambda *_args, **_kwargs: FakeResult())

        client.input_private_text("secret-123")

        command = popen.call_args.args[0]
        payload = process.communicate.call_args.args[0]
        self.assertEqual(command, ["adb.exe", "-s", "emulator-5556", "shell"])
        self.assertNotIn("secret-123", " ".join(command))
        self.assertNotIn(b"secret-123", payload)
        self.assertIn(b"base64 -d", payload)

    @patch("buzzbot.adb.subprocess.Popen")
    def test_private_email_uses_android_at_key_without_exposing_value(self, popen):
        process = popen.return_value
        process.communicate.return_value = (b"", b"")
        process.returncode = 0
        client = self.make_client(lambda *_args, **_kwargs: FakeResult())

        client.input_private_text("person@example.com")

        command = popen.call_args.args[0]
        payload = process.communicate.call_args.args[0]
        self.assertNotIn("person@example.com", " ".join(command))
        self.assertNotIn(b"person@example.com", payload)
        self.assertIn(b"KEYCODE_AT", payload)

    def test_current_foreground_package_reads_focused_window(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            if "window" in command:
                return FakeResult(
                    stdout=(
                        "mCurrentFocus=Window{42 u0 "
                        "com.igg.android.doomsdaylastsurvivors/.MainActivity}"
                    )
                )
            return FakeResult()

        package = self.make_client(runner).current_foreground_package()
        self.assertEqual(package, "com.igg.android.doomsdaylastsurvivors")
        self.assertEqual(calls[0][0][-3:], ["dumpsys", "window", "windows"])

    def test_current_foreground_package_falls_back_to_resumed_activity(self):
        def runner(command, **_kwargs):
            if "window" in command:
                return FakeResult(stdout="")
            return FakeResult(
                stdout="topResumedActivity=ActivityRecord{1 u0 com.android.launcher3/.Launcher}"
            )

        self.assertEqual(
            self.make_client(runner).current_foreground_package(),
            "com.android.launcher3",
        )

    def test_launch_package_uses_selected_emulator(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return FakeResult(stdout="Events injected: 1\n")

        self.make_client(runner).launch_package("com.igg.android.doomsdaylastsurvivors")
        self.assertEqual(
            calls[0][0],
            [
                "adb.exe",
                "-s",
                "emulator-5556",
                "shell",
                "monkey",
                "-p",
                "com.igg.android.doomsdaylastsurvivors",
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ],
        )

    def test_force_stop_package_uses_selected_emulator(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return FakeResult()

        self.make_client(runner).force_stop_package("com.igg.android.doomsdaylastsurvivors")
        self.assertEqual(
            calls[0][0],
            [
                "adb.exe",
                "-s",
                "emulator-5556",
                "shell",
                "am",
                "force-stop",
                "com.igg.android.doomsdaylastsurvivors",
            ],
        )

    def test_list_devices_ignores_configured_serial(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return FakeResult(
                stdout="List of devices attached\nemulator-5560 device product:test model:test\noffline-1 offline\n"
            )

        client = self.make_client(runner)
        self.assertEqual(client.list_devices(), ["emulator-5560"])
        self.assertEqual(calls[0][0], ["adb.exe", "devices", "-l"])
        self.assertEqual(client.serial, "emulator-5556")

    def test_restart_server_clears_stale_daemon_without_serial(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return FakeResult()

        client = self.make_client(runner)
        client.restart_server()

        self.assertEqual(calls[0][0], ["adb.exe", "kill-server"])
        self.assertEqual(calls[1][0], ["adb.exe", "start-server"])
        self.assertEqual(client.serial, "emulator-5556")

    def test_restart_server_force_clears_matching_adb_after_start_timeout(self):
        calls = []
        start_attempts = 0

        def runner(command, **kwargs):
            nonlocal start_attempts
            calls.append((command, kwargs))
            if command[-1] == "start-server":
                start_attempts += 1
                if start_attempts == 1:
                    raise subprocess.TimeoutExpired(command, 10)
            return FakeResult()

        client = self.make_client(runner)
        with patch.object(client, "_terminate_stale_adb_processes", return_value=True) as terminate:
            client.restart_server()

        terminate.assert_called_once_with()
        self.assertEqual(
            [call[0] for call in calls],
            [
                ["adb.exe", "kill-server"],
                ["adb.exe", "start-server"],
                ["adb.exe", "start-server"],
            ],
        )
        self.assertEqual(client.serial, "emulator-5556")

    def test_connect_uses_tcp_address_without_selected_serial(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return FakeResult(stdout="connected to 127.0.0.1:5559\n")

        client = self.make_client(runner)
        self.assertIn("connected", client.connect("127.0.0.1:5559"))
        self.assertEqual(calls[0][0], ["adb.exe", "connect", "127.0.0.1:5559"])
        self.assertEqual(client.serial, "emulator-5556")

    def test_ui_xml_is_read_and_removed(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            stdout = '<hierarchy text="Verify it&apos;s you" />' if "cat" in command else ""
            return FakeResult(stdout=stdout)

        xml = self.make_client(runner).ui_xml()
        self.assertIn("Verify", xml)
        remote_path = calls[0][0][-1]
        self.assertTrue(remote_path.startswith("/data/local/tmp/buzzbot_ui_"))
        self.assertEqual(calls[0][0][-3:-1], ["rm", "-f"])
        self.assertEqual(
            calls[1][0][-4:-1],
            ["uiautomator", "dump", "--compressed"],
        )
        self.assertEqual(calls[2][0][-2:], ["cat", remote_path])
        self.assertEqual(calls[3][0][-3:], ["rm", "-f", remote_path])

    @patch("buzzbot.adb.time.sleep", return_value=None)
    def test_ui_xml_retries_when_dump_file_is_delayed(self, _sleep):
        calls = []
        cat_count = 0

        def runner(command, **kwargs):
            nonlocal cat_count
            calls.append((command, kwargs))
            if "cat" in command:
                cat_count += 1
                if cat_count == 1:
                    return FakeResult(returncode=1, stderr="No such file or directory")
                return FakeResult(stdout='<hierarchy rotation="0" />')
            return FakeResult()

        xml = self.make_client(runner).ui_xml()

        self.assertIn("hierarchy", xml)
        self.assertEqual(cat_count, 2)
        _sleep.assert_called_once()

    @patch("buzzbot.adb.os.name", "nt")
    def test_windows_commands_do_not_open_a_console(self):
        calls = []

        def runner(_command, **kwargs):
            calls.append(kwargs)
            return FakeResult(stdout="device\n")

        self.make_client(runner).is_available()
        self.assertEqual(
            calls[0]["creationflags"],
            getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )


if __name__ == "__main__":
    unittest.main()
