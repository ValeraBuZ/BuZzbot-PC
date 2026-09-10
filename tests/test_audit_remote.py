import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock

from buzzbot.remote_control import RemoteControlClient, RemoteControlError, RemoteSettings
from buzzbot.remote_hub import RemoteHubRequestHandler, RemoteHubRunner
from buzzbot.updater import fetch_update_manifest, UpdateError


class RemoteRegressionTests(unittest.TestCase):
    def make_client(self, directory, opener, handler=None):
        return RemoteControlClient(
            RemoteSettings(enabled=True, hub_url="https://hub.example", device_id="test"),
            "test-secret-at-least-24-characters", lambda: {}, handler or (lambda action: True),
            lambda allowed: None, state_path=Path(directory) / "state.json", urlopen=opener,
        )

    def test_nonobject_hub_response_has_readable_error(self):
        for value in ([], None, 42, "invalid"):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                client = self.make_client(directory, lambda *args, **kwargs: io.BytesIO(json.dumps(value).encode()))
                with self.assertRaises(RemoteControlError):
                    client.checkin_once()

    def test_string_access_flag_does_not_grant_access(self):
        with tempfile.TemporaryDirectory() as directory:
            body = json.dumps({"ok": True, "access_allowed": "false"}).encode()
            client = self.make_client(directory, lambda *args, **kwargs: io.BytesIO(body))
            client.access_allowed = False
            with self.assertRaises(RemoteControlError):
                client.checkin_once()
            self.assertFalse(client.access_allowed)

    def test_slow_stopped_client_cannot_restart_or_execute_late_command(self):
        with tempfile.TemporaryDirectory() as directory:
            requested, release = threading.Event(), threading.Event()
            body = json.dumps({"ok": True, "command": {"id": 1, "action": "start"}}).encode()
            def opener(*args, **kwargs):
                requested.set()
                release.wait(3)
                return io.BytesIO(body)
            commands = []
            client = self.make_client(directory, opener, lambda action: commands.append(action) or True)
            self.assertTrue(client.start())
            thread = client._thread
            try:
                self.assertTrue(requested.wait(2))
                client.stop(timeout=0.01)
                self.assertIs(client._thread, thread)
                self.assertFalse(client.start())
            finally:
                release.set()
                thread.join(timeout=3)
                client.stop(timeout=0.1)
            self.assertFalse(thread.is_alive())
            self.assertEqual(commands, [])
            self.assertEqual(client.last_command_id, 0)
            self.assertFalse(client.connected)

    def test_parallel_checkins_execute_command_once(self):
        with tempfile.TemporaryDirectory() as directory:
            handling, release, second_request = threading.Event(), threading.Event(), threading.Event()
            requests = []
            commands, errors = [], []
            body = json.dumps({"ok": True, "command": {"id": 1, "action": "pause"}}).encode()
            def opener(*args, **kwargs):
                requests.append(True)
                if len(requests) == 2:
                    second_request.set()
                return io.BytesIO(body)
            def handler(action):
                commands.append(action)
                handling.set()
                release.wait(3)
                return True
            client = self.make_client(directory, opener, handler)
            def check():
                try:
                    client.checkin_once()
                except Exception as exc:
                    errors.append(exc)
            first, second = threading.Thread(target=check), threading.Thread(target=check)
            first.start()
            try:
                self.assertTrue(handling.wait(2))
                second.start()
                self.assertFalse(second_request.wait(0.1))
            finally:
                release.set()
                first.join(timeout=3)
                if second.ident is not None:
                    second.join(timeout=3)
            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(commands, ["pause"])

    def test_unstarted_hub_does_not_call_blocking_shutdown(self):
        runner = RemoteHubRunner.__new__(RemoteHubRunner)
        runner.server = Mock()
        runner._thread = None
        runner.stop()
        runner.server.shutdown.assert_not_called()
        runner.server.server_close.assert_called_once()

    def test_nonascii_authorization_is_rejected_without_type_error(self):
        handler = RemoteHubRequestHandler.__new__(RemoteHubRequestHandler)
        handler.headers = {"Authorization": "Bearer \u00ff"}
        handler.server = Mock(auth_token="ascii-token")
        self.assertFalse(handler._authorized())

    def test_bad_heartbeat_uses_default(self):
        for value in ("broken", {}, float("inf"), float("nan")):
            with self.subTest(value=value):
                self.assertEqual(RemoteSettings(heartbeat_seconds=value).normalized().heartbeat_seconds, 10.0)

    def test_nonobject_update_manifest_has_domain_error(self):
        for value in ([], None, "invalid", 42):
            with self.subTest(value=value), self.assertRaises(UpdateError):
                fetch_update_manifest(opener=lambda *args, **kwargs: io.BytesIO(json.dumps(value).encode()))


if __name__ == "__main__":
    unittest.main()
