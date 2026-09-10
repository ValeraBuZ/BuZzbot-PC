from pathlib import Path
import shlex
import subprocess
import unittest
from unittest.mock import Mock, patch

from buzzbot.adb import AdbClient, AdbError


class AdbRegressionTests(unittest.TestCase):
    def make_client(self, runner=None):
        client = AdbClient.__new__(AdbClient)
        client.adb_path = Path("adb.exe")
        client.serial = "emulator-5556"
        client._runner = runner or Mock(return_value=Mock(returncode=0, stdout="", stderr=""))
        return client

    def test_device_enumeration_does_not_change_target_of_concurrent_tap(self):
        calls = []
        def runner(command, **kwargs):
            calls.append(command)
            if "devices" in command:
                client.tap(10, 20)
            return Mock(returncode=0, stdout="", stderr="")
        client = self.make_client(runner)
        client.list_devices()
        self.assertNotIn("-s", calls[0])
        self.assertEqual(calls[1][:3], ["adb.exe", "-s", "emulator-5556"])
        self.assertEqual(client.serial, "emulator-5556")

    def test_input_is_one_quoted_remote_shell_argument(self):
        client = self.make_client()
        text = "team'; echo UNEXPECTED; # & $value"
        client.input_text(text)
        command = client._runner.call_args.args[0]
        self.assertEqual(shlex.split(" ".join(command[4:])), ["input", "text", text.replace(" ", "%s")])

    @patch("buzzbot.adb.subprocess.Popen")
    def test_private_input_timeout_kills_and_reaps_process(self, popen):
        process = popen.return_value
        process.communicate.side_effect = [subprocess.TimeoutExpired("adb", 10), (b"", b"")]
        with self.assertRaises(AdbError):
            self.make_client().input_private_text("dummy-secret")
        process.kill.assert_called_once()
        self.assertEqual(process.communicate.call_count, 2)

    @patch("buzzbot.adb.subprocess.Popen")
    def test_private_input_error_does_not_expose_echoed_secret(self, popen):
        process = popen.return_value
        process.returncode = 1
        process.communicate.return_value = (b"", b"failed: dummy-secret")
        with self.assertRaises(AdbError) as raised:
            self.make_client().input_private_text("dummy-secret")
        self.assertNotIn("dummy-secret", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
