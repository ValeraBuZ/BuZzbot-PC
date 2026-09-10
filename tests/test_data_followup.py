import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from buzzbot.routines import LEGACY_RADAR_TEMPLATE_UIDS
from buzzbot.storage import save_json_with_backup
from buzzbot.training_profiles import read_training_profile
from tools.install_training_profile import install_profile


def make_manifest():
    return {
        "format": "doomsday-training-profile",
        "groups": {"Radar": True},
        "routine_max_marches": 5,
        "routine_tasks": [{"id": "radar", "group": "Radar"}],
        "images": [{"uid": "new-template", "group": "Radar", "path": "templates/image.png"}],
    }


def write_profile(path, manifest):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("profile.json", json.dumps(manifest))
        archive.writestr("templates/image.png", b"template-bytes")


def make_installation(root):
    legacy = root / "img" / "legacy.png"
    legacy.parent.mkdir()
    legacy.write_bytes(b"valuable-old-template")
    config = {
        "images": [{"uid": next(iter(LEGACY_RADAR_TEMPLATE_UIDS)), "group": "Radar", "path": "img/legacy.png"}],
        "groups": {"Radar": True},
    }
    config_path = root / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return config_path, legacy


class DataFollowupTests(unittest.TestCase):
    def test_bundled_profile_installs_all_templates(self):
        profile = Path(__file__).resolve().parents[1] / "profiles/BuZzbot_PC_1280x720.zip"
        with zipfile.ZipFile(profile) as archive:
            manifest = read_training_profile(archive)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path, legacy = make_installation(root)
            install_profile(profile, root)
            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(len(config["images"]), len(manifest["images"]))
            self.assertTrue(all((root / image["path"]).is_file() for image in config["images"]))
            self.assertFalse(legacy.exists())

    def test_invalid_manifest_cannot_delete_installed_legacy_templates(self):
        mutations = (
            lambda data: data["images"][0].pop("uid"),
            lambda data: data["images"][0].pop("group"),
            lambda data: data["images"][0].update(group=[]),
            lambda data: data["routine_tasks"][0].pop("group"),
            lambda data: data.pop("routine_max_marches"),
            lambda data: data["images"].append(dict(data["images"][0])),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config_path, legacy = make_installation(root)
                original = config_path.read_bytes()
                manifest = make_manifest()
                mutate(manifest)
                profile = root / "profile.zip"
                write_profile(profile, manifest)
                with self.assertRaises(ValueError):
                    install_profile(profile, root)
                self.assertEqual(config_path.read_bytes(), original)
                self.assertEqual(legacy.read_bytes(), b"valuable-old-template")
                self.assertFalse((root / "img/radar").exists())

    def test_invalid_existing_config_is_rejected_before_template_changes(self):
        for field, value in (("groups", []), ("group_schedules", None), ("group_execution", [])):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config_path, legacy = make_installation(root)
                config = json.loads(config_path.read_text())
                config[field] = value
                config_path.write_text(json.dumps(config), encoding="utf-8")
                original = config_path.read_bytes()
                profile = root / "profile.zip"
                write_profile(profile, make_manifest())
                with self.assertRaises(ValueError):
                    install_profile(profile, root)
                self.assertEqual(config_path.read_bytes(), original)
                self.assertTrue(legacy.exists())
                self.assertFalse((root / "img/radar").exists())

    def test_failed_config_save_retains_legacy_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path, legacy = make_installation(root)
            original = config_path.read_bytes()
            profile = root / "profile.zip"
            write_profile(profile, make_manifest())
            with patch("tools.install_training_profile.save_json_with_backup", side_effect=PermissionError("locked")):
                with self.assertRaises(PermissionError):
                    install_profile(profile, root)
            self.assertEqual(config_path.read_bytes(), original)
            self.assertEqual(legacy.read_bytes(), b"valuable-old-template")

    def test_successful_install_updates_config_then_removes_legacy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path, legacy = make_installation(root)
            profile = root / "profile.zip"
            write_profile(profile, make_manifest())
            install_profile(profile, root)
            config = json.loads(config_path.read_text())
            self.assertEqual([image["uid"] for image in config["images"]], ["new-template"])
            self.assertEqual((root / config["images"][0]["path"]).read_bytes(), b"template-bytes")
            self.assertFalse(legacy.exists())
            self.assertEqual(len(list((root / "backups/config").glob("*.json"))), 1)

    def test_reused_legacy_filename_is_not_removed_after_install(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path, legacy = make_installation(root)
            config = json.loads(config_path.read_text())
            config["images"][0]["path"] = "img/radar/new-template.png"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            replacement = root / config["images"][0]["path"]
            replacement.parent.mkdir()
            legacy.rename(replacement)
            profile = root / "profile.zip"
            write_profile(profile, make_manifest())
            install_profile(profile, root)
            self.assertEqual(replacement.read_bytes(), b"template-bytes")

    def test_archive_extension_cannot_create_windows_alternate_data_stream(self):
        manifest = make_manifest()
        manifest["images"][0]["path"] = "templates/image.png:secret"
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("profile.json", json.dumps(manifest))
            archive.writestr("templates/image.png:secret", b"secret")
        with zipfile.ZipFile(stream) as archive, self.assertRaises(ValueError):
            read_training_profile(archive)

    def test_invalid_backup_count_does_not_replace_original_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            original = b'{"valuable": "original"}'
            path.write_bytes(original)
            with self.assertRaises(ValueError):
                save_json_with_backup(path, {"valuable": "new"}, keep_backups="invalid")
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse((path.parent / "backups").exists())


if __name__ == "__main__":
    unittest.main()
