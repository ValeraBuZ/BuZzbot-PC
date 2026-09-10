import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import call, patch

from buzzbot.storage import atomic_write_json, save_json_with_backup


def windows_denial(code):
    error = PermissionError(13, "mock temporary access denial")
    error.winerror = code
    return error


class StorageRetryTests(unittest.TestCase):
    def test_transient_windows_denial_reuses_complete_fsynced_document_and_one_backup(self):
        real_replace = os.replace
        real_fsync = os.fsync
        for code in (5, 32, 33):
            with self.subTest(winerror=code), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "config.json"
                original = b'{"valuable": "old"}\n'
                path.write_bytes(original)
                sources = []
                def replace(source, destination, *, sources=sources, path=path, original=original, code=code):
                    sources.append(Path(source))
                    self.assertEqual(path.read_bytes(), original)
                    self.assertEqual(json.loads(Path(source).read_text(encoding="utf-8")), {"valuable": "new"})
                    self.assertEqual(fsync.call_count, 1)
                    if len(sources) < 4:
                        raise windows_denial(code)
                    return real_replace(source, destination)
                with (
                    patch("buzzbot.storage.sys.platform", "win32"),
                    patch("buzzbot.storage.os.replace", side_effect=replace) as replaced,
                    patch("buzzbot.storage.os.fsync", wraps=real_fsync) as fsync,
                    patch("buzzbot.storage.time.sleep") as sleep,
                ):
                    self.assertEqual(save_json_with_backup(path, {"valuable": "new"}), path)
                self.assertEqual(replaced.call_count, 4)
                self.assertEqual(len(set(sources)), 1)
                self.assertEqual(sleep.call_args_list, [call(.05), call(.10), call(.20)])
                self.assertLess(sum(item.args[0] for item in sleep.call_args_list), 1)
                self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"valuable": "new"})
                backups = list((Path(directory) / "backups/config").glob("*.json"))
                self.assertEqual(len(backups), 1)
                self.assertEqual(backups[0].read_bytes(), original)
                self.assertEqual(list(Path(directory).glob(".config.json.*.tmp")), [])

    def test_permanent_windows_denial_raises_last_error_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            original = b'{"important": "keep"}\n'
            path.write_bytes(original)
            failures = [windows_denial(5) for _ in range(4)]
            with (
                patch("buzzbot.storage.sys.platform", "win32"),
                patch("buzzbot.storage.os.replace", side_effect=failures) as replaced,
                patch("buzzbot.storage.time.sleep") as sleep,
                patch("buzzbot.storage._trim_old_files") as trim,
                self.assertRaises(PermissionError) as raised,
            ):
                save_json_with_backup(path, {"important": "replacement"})
            self.assertIs(raised.exception, failures[-1])
            self.assertEqual(replaced.call_count, 4)
            self.assertEqual(sleep.call_count, 3)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(directory).glob(".config.json.*.tmp")), [])
            trim.assert_not_called()
            backups = list((Path(directory) / "backups/config").glob("*.json"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original)

    def test_non_windows_platform_does_not_retry_permission_errors(self):
        for platform in ("linux", "darwin"):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "config.json"
                error = windows_denial(32)
                with (
                    patch("buzzbot.storage.sys.platform", platform),
                    patch("buzzbot.storage.os.replace", side_effect=error) as replaced,
                    patch("buzzbot.storage.time.sleep") as sleep,
                    self.assertRaises(PermissionError) as raised,
                ):
                    atomic_write_json(path, {"new": True})
                self.assertIs(raised.exception, error)
                replaced.assert_called_once()
                sleep.assert_not_called()
                self.assertFalse(path.exists())
                self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_other_permission_and_io_errors_are_not_retried(self):
        other_io = OSError(28, "mock disk full")
        other_io.winerror = 5
        for error in (PermissionError("no winerror"), windows_denial(87), other_io):
            with self.subTest(error_type=type(error).__name__, winerror=getattr(error, "winerror", None)):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "config.json"
                    path.write_text("{}", encoding="utf-8")
                    with (
                        patch("buzzbot.storage.sys.platform", "win32"),
                        patch("buzzbot.storage.os.replace", side_effect=error) as replaced,
                        patch("buzzbot.storage.time.sleep") as sleep,
                        self.assertRaises(OSError) as raised,
                    ):
                        atomic_write_json(path, {"new": True})
                    self.assertIs(raised.exception, error)
                    replaced.assert_called_once()
                    sleep.assert_not_called()
                    self.assertEqual(path.read_text(encoding="utf-8"), "{}")

    def test_fsync_failure_is_not_retried_as_a_replace_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{"old": true}', encoding="utf-8")
            failure = windows_denial(5)
            with (
                patch("buzzbot.storage.sys.platform", "win32"),
                patch("buzzbot.storage.os.fsync", side_effect=failure),
                patch("buzzbot.storage.os.replace") as replaced,
                patch("buzzbot.storage.time.sleep") as sleep,
                self.assertRaises(PermissionError) as raised,
            ):
                atomic_write_json(path, {"new": True})
            self.assertIs(raised.exception, failure)
            replaced.assert_not_called()
            sleep.assert_not_called()
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"old": True})
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_uncontended_replace_does_not_sleep_or_duplicate_fsync(self):
        real_replace = os.replace
        real_fsync = os.fsync
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            with (
                patch("buzzbot.storage.sys.platform", "win32"),
                patch("buzzbot.storage.os.replace", wraps=real_replace) as replaced,
                patch("buzzbot.storage.os.fsync", wraps=real_fsync) as fsync,
                patch("buzzbot.storage.time.sleep") as sleep,
            ):
                atomic_write_json(path, {"new": True})
            replaced.assert_called_once()
            fsync.assert_called_once()
            sleep.assert_not_called()
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"new": True})


if __name__ == "__main__":
    unittest.main()
