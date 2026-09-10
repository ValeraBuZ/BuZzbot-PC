import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from buzzbot.training_profiles import read_training_profile, safe_profile_component
from tools.install_training_profile import install_profile


def profile_bytes(uid="safe-id", task_id="task", group="Аккаунт: пример"):
    manifest = {
        "format": "doomsday-training-profile",
        "groups": {group: True}, "routine_max_marches": 5,
        "routine_tasks": [{"id": task_id, "group": group}],
        "images": [{"uid": uid, "group": group, "path": "templates/image.png"}],
    }
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("profile.json", json.dumps(manifest))
        archive.writestr("templates/image.png", b"example")
    return stream.getvalue()


class ProfileSafetyTests(unittest.TestCase):
    def test_bundled_profile_still_validates(self):
        path = Path(__file__).resolve().parents[1] / "profiles/BuZzbot_PC_1280x720.zip"
        with zipfile.ZipFile(path) as archive:
            manifest = read_training_profile(archive)
        self.assertGreater(len(manifest["images"]), 20)

    def test_windows_paths_and_device_names_are_rejected(self):
        for value in ("../escape", "..\\escape", "C:\\escape", "file:stream", "NUL", "con.txt", ".", "..", "trailing."):
            with self.subTest(value=value), self.assertRaises(ValueError):
                safe_profile_component(value)

    def test_display_group_with_colon_remains_supported(self):
        with zipfile.ZipFile(io.BytesIO(profile_bytes())) as archive:
            manifest = read_training_profile(archive)
        self.assertIn("Аккаунт: пример", manifest["groups"])

    def test_installer_rejects_traversal_without_changing_config(self):
        for arguments in ({"uid": "../../escape"}, {"task_id": "../../escape"}, {"group": ".."}):
            with self.subTest(arguments=arguments), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                original = '{"images": [], "groups": {"original": true}}'
                (root / "config.json").write_text(original, encoding="utf-8")
                profile = root / "profile.zip"
                profile.write_bytes(profile_bytes(**arguments))
                with self.assertRaises(ValueError):
                    install_profile(profile, root)
                self.assertEqual((root / "config.json").read_text(), original)
                self.assertFalse((root / "img").exists())

    def test_manifest_with_wrong_top_level_type_is_rejected(self):
        for value in (None, [], "invalid", 42):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as archive:
                archive.writestr("profile.json", json.dumps(value))
            with zipfile.ZipFile(stream) as archive, self.assertRaises(ValueError):
                read_training_profile(archive)


if __name__ == "__main__":
    unittest.main()
