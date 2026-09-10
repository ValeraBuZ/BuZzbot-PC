import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from buzzbot import remote_control, remote_hub


class RemoteFollowupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def client(self, result=None, *, opener=None, access_handler=None, command_handler=None):
        body = json.dumps(result or {"ok": True}).encode()
        return remote_control.RemoteControlClient(
            remote_control.RemoteSettings(
                enabled=True, hub_url="https://hub.example", device_id="device-one"
            ),
            "test-token-with-at-least-24-characters", lambda: {},
            command_handler or Mock(return_value=True), access_handler or Mock(),
            state_path=self.directory / "client.json",
            urlopen=opener or (lambda *args, **kwargs: io.BytesIO(body)),
        )

    def store(self):
        return remote_hub.RemoteHubStore(self.directory / "hub.json", time_fn=lambda: 100.0)

    def test_manual_checkin_reply_is_discarded_after_stop_and_restart(self):
        requested, release, fresh_requested = threading.Event(), threading.Event(), threading.Event()
        calls, errors = [], []

        def opener(*args, **kwargs):
            calls.append(True)
            if len(calls) == 1:
                requested.set()
                if not release.wait(3):
                    raise TimeoutError("test response was not released")
                result = {"ok": True, "command": {"id": 1, "action": "start"}}
            else:
                fresh_requested.set()
                result = {"ok": True}
            return io.BytesIO(json.dumps(result).encode())

        commands = Mock(return_value=True)
        client = self.client(opener=opener, command_handler=commands)

        def manual_checkin():
            try:
                client.checkin_once()
            except Exception as exc:
                errors.append(exc)

        manual = threading.Thread(target=manual_checkin)
        manual.start()
        try:
            self.assertTrue(requested.wait(2))
            client.stop(timeout=0)
            self.assertTrue(client.start())
            release.set()
            manual.join(timeout=3)
            self.assertTrue(fresh_requested.wait(2))
        finally:
            release.set()
            manual.join(timeout=3)
            client.stop()
        self.assertFalse(manual.is_alive())
        self.assertEqual(errors, [])
        commands.assert_not_called()

    def test_denial_is_delivered_even_if_state_disk_write_fails_and_is_retried(self):
        changes = Mock()
        client = self.client({"ok": True, "access_allowed": False}, access_handler=changes)
        with patch.object(remote_control, "_atomic_write_json", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                client.checkin_once()
        changes.assert_called_once_with(False)
        self.assertFalse(client.access_allowed)
        client.checkin_once()
        self.assertFalse(json.loads(client.state_path.read_text())["access_allowed"])
        changes.assert_called_once_with(False)

    def test_access_handler_failure_is_retried_on_next_reply(self):
        changes = Mock(side_effect=[RuntimeError("queue unavailable"), None])
        client = self.client({"ok": True, "access_allowed": False}, access_handler=changes)
        with self.assertRaises(RuntimeError):
            client.checkin_once()
        client.checkin_once()
        self.assertEqual(changes.call_count, 2)
        self.assertFalse(client.access_allowed)

    def test_failed_command_state_is_saved_before_next_acknowledgement(self):
        command = {"id": 1, "action": "pause"}
        requests = []

        def opener(http_request, **kwargs):
            requests.append(json.loads(http_request.data))
            if len(requests) == 2:
                self.assertEqual(json.loads(client.state_path.read_text())["last_command_id"], 1)
            return io.BytesIO(json.dumps({"ok": True, "command": command}).encode())

        commands = Mock(return_value=True)
        client = self.client(opener=opener, command_handler=commands)
        with patch.object(remote_control, "_atomic_write_json", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                client.checkin_once()
        client.checkin_once()
        commands.assert_called_once_with("pause")
        self.assertEqual(requests[-1]["ack_command_id"], 1)

    def test_access_callback_stop_prevents_later_command_from_same_reply(self):
        commands = Mock(return_value=True)
        client = self.client(
            {"ok": True, "access_allowed": False, "command": {"id": 1, "action": "start"}},
            command_handler=commands,
        )
        client.access_handler = lambda allowed: client.stop(timeout=0)
        client.checkin_once()
        commands.assert_not_called()
        self.assertFalse(client.connected)

    def test_command_callback_stop_does_not_restore_connected_state(self):
        client = self.client({"ok": True, "command": {"id": 1, "action": "stop"}})
        client.command_handler = lambda action: client.stop(timeout=0)
        client.checkin_once()
        self.assertFalse(client.connected)

    def test_failed_hub_command_write_does_not_publish_command_or_consume_id(self):
        store = self.store()
        store.checkin({"device_id": "device-one"})
        with patch.object(remote_hub, "_atomic_write_json", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                store.set_command("device-one", "start")
        self.assertIsNone(store.list_devices()[0]["command"])
        self.assertEqual(store.set_command("device-one", "pause")["id"], 1)

    def test_failed_hub_access_write_does_not_publish_uncommitted_access(self):
        store = self.store()
        store.checkin({"device_id": "device-one"})
        store.set_access("device-one", False)
        with patch.object(remote_hub, "_atomic_write_json", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                store.set_access("device-one", True)
        self.assertFalse(store.checkin({"device_id": "device-one"})["access_allowed"])
        restored = remote_hub.RemoteHubStore(store.path)
        self.assertFalse(restored.list_devices()[0]["access_allowed"])

    def test_failed_hub_checkin_does_not_drop_pending_command(self):
        store = self.store()
        store.checkin({"device_id": "device-one"})
        command = store.set_command("device-one", "pause")
        with patch.object(remote_hub, "_atomic_write_json", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                store.checkin({"device_id": "device-one", "ack_command_id": command["id"]})
        self.assertEqual(store.list_devices()[0]["command"], command)

    def test_failed_initial_hub_checkin_does_not_register_device(self):
        store = self.store()
        with patch.object(remote_hub, "_atomic_write_json", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                store.checkin({"device_id": "device-one"})
        self.assertEqual(store.list_devices(), [])

    def test_nonfinite_acknowledgement_is_a_bad_request(self):
        store = self.store()
        with self.assertRaises(ValueError):
            store.checkin({"device_id": "device-one", "ack_command_id": float("inf")})
        self.assertEqual(store.list_devices(), [])


if __name__ == "__main__":
    unittest.main()
